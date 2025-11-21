#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
calibrate_offsets.py - Advanced Ground Truth Finder
Finds the exact location of a GPIO table by matching it against a reference gpio.h.
"""

import struct
import sys
import re
from pathlib import Path

# Regex to parse gpio.h macros
MACRO_REGEX = re.compile(r'^\s*PAD_CFG_([A-Z0-9_]+)\s*\(([^,]+),')

# Map macro types to expected Mode (0=GPIO, 1=NF1, etc.)
# This is a heuristic; specific macros might override, but this captures 95% of cases.
MACRO_TO_MODE = {
    'GPO': 0,
    'GPI': 0,
    'GPI_TRIG_OWN': 0,
    'GPI_SCI': 0,
    'GPI_SMI': 0,
    'GPI_APIC': 0,
    'GPI_APIC_LOW': 0,
    'GPI_APIC_HIGH': 0,
    'NF': 1, # Default to NF1 if not specified, logic below handles explicit NFx
}

def parse_gpio_h(filepath):
    """Parses gpio.h to get a list of (PadName, ExpectedMode)."""
    pads = []
    with open(filepath, 'r') as f:
        for line in f:
            match = MACRO_REGEX.match(line)
            if match:
                macro_type = match.group(1)
                pad_name = match.group(2).strip()

                mode = 0 # Default GPIO

                # Handle PAD_CFG_NF(..., NFx)
                if macro_type == 'NF':
                    # Extract the last argument for NF number
                    args = line.split('(')[1].split(')')[0].split(',')
                    if len(args) >= 4:
                        nf_arg = args[3].strip()
                        if nf_arg.startswith('NF'):
                            try:
                                mode = int(nf_arg[2:])
                            except:
                                mode = 1
                    else:
                        mode = 1
                else:
                    # Handle standard macros
                    for key, val in MACRO_TO_MODE.items():
                        if macro_type.startswith(key):
                            mode = val
                            break

                pads.append({'name': pad_name, 'mode': mode})
    return pads

def scan_binary(binary_path, expected_pads):
    """Scans binary for the sequence of modes found in expected_pads."""
    with open(binary_path, 'rb') as f:
        data = f.read()

    print(f"Binary size: {len(data)} bytes")
    print(f"Searching for {len(expected_pads)} pads...")

    # We search for a specific fingerprint: a sequence of 8 pads
    # Why 8? Long enough to be unique, short enough to fit in a small table segment.
    # We try multiple windows in case the start of the table is missing/different.

    fingerprint_len = 8
    found_candidates = []

    # Scan strides (8, 12, 16 bytes per entry)
    for stride in [8, 12, 16]:
        print(f"Scanning stride {stride}...")

        # We'll slide a window over the binary
        # Mask for Mode in DW0: (val >> 10) & 0xF

        # We only match the first N pads from the header
        target_modes = [p['mode'] for p in expected_pads[:fingerprint_len]]

        for offset in range(0, len(data) - (stride * fingerprint_len), 4):
            match = True
            raw_values = []

            for i, target_mode in enumerate(target_modes):
                p_off = offset + (i * stride)
                dw0 = struct.unpack('<I', data[p_off:p_off+4])[0]
                dw1 = struct.unpack('<I', data[p_off+4:p_off+8])[0]

                # Extract mode
                actual_mode = (dw0 >> 10) & 0xF

                if actual_mode != target_mode:
                    match = False
                    break

                raw_values.append((dw0, dw1))

            if match:
                # We found a candidate!
                # Let's see how far the match extends beyond the fingerprint
                extension_match = 0
                for i in range(fingerprint_len, len(expected_pads)):
                    p_off = offset + (i * stride)
                    if p_off + 8 > len(data): break

                    dw0 = struct.unpack('<I', data[p_off:p_off+4])[0]
                    mode = (dw0 >> 10) & 0xF
                    if mode == expected_pads[i]['mode']:
                        extension_match += 1
                    else:
                        # Allow a few mismatches (padding/reordering)
                        if extension_match > 20: # If we already matched 20, strictness drops
                            continue
                        else:
                            break

                total_score = fingerprint_len + extension_match

                found_candidates.append({
                    'offset': offset,
                    'stride': stride,
                    'score': total_score,
                    'raw_sample': raw_values
                })

    # Sort by score (longest match)
    found_candidates.sort(key=lambda x: x['score'], reverse=True)

    if not found_candidates:
        print("No matching table found.")
        return

    best = found_candidates[0]
    print("\n" + "="*60)
    print(f"BEST MATCH FOUND")
    print("="*60)
    print(f"Offset:       0x{best['offset']:x}")
    print(f"Stride:       {best['stride']} bytes")
    print(f"Match Length: {best['score']} pads")

    # Dump detailed analysis of the first few entries
    print("\nDetailed Analysis of First 10 Entries:")
    print(f"{'Idx':<4} {'Pad Name':<15} {'ExpMode':<8} {'ActMode':<8} {'DW0 (Raw)':<12} {'DW1 (Raw)':<12} {'Match?'}")
    print("-" * 80)

    start_off = best['offset']
    stride = best['stride']

    for i in range(min(20, len(expected_pads))):
        p_off = start_off + (i * stride)
        dw0 = struct.unpack('<I', data[p_off:p_off+4])[0]
        dw1 = struct.unpack('<I', data[p_off+4:p_off+8])[0]

        act_mode = (dw0 >> 10) & 0xF
        exp_mode = expected_pads[i]['mode']
        pad_name = expected_pads[i]['name']

        match_str = "YES" if act_mode == exp_mode else "NO"

        # Check reserved bits (30, 31)
        reserved_flags = (dw0 >> 30) & 0x3
        flags_str = f"(Flags: {reserved_flags})" if reserved_flags else ""

        print(f"{i:<4} {pad_name:<15} {exp_mode:<8} {act_mode:<8} 0x{dw0:08x}   0x{dw1:08x}   {match_str} {flags_str}")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: calibrate_offsets.py <binary> <gpio.h>")
        sys.exit(1)

    pads = parse_gpio_h(sys.argv[2])
    print(f"Loaded {len(pads)} pads from header.")
    scan_binary(sys.argv[1], pads)
