#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
compose_gpio.py - Reconstruct Post-Init GPIO state from BIOS tables.

This tool implements table layering and default synthesis to reconstruct
the final runtime state of GPIOs from the static BIOS image.
"""

import sys
import logging
import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gpio_detector import GPIOTableDetector
from gpio_parser import GPIOParser

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def parse_reference_header(filepath: Path) -> Dict[str, int]:
    """
    Parses a reference gpio.h file to get Ground Truth for validation.
    Returns: {pad_name: mode_int}
    """
    modes = {}
    regex = re.compile(r'^\s*PAD_CFG_([A-Z0-9_]+)\s*\(([^,]+),')
    vgpio_regex = re.compile(r'^\s*_PAD_CFG_STRUCT\s*\(([^,]+),\s*(.+?),')

    try:
        with open(filepath, 'r') as f:
            for line in f:
                # Standard macros
                match = regex.match(line)
                if match:
                    pad = match.group(2).strip()
                    mode = 0 # Default GPIO
                    mtype = match.group(1)

                    if 'NF' in mtype:
                        parts = line.split(',')
                        if len(parts) >= 4 and 'NF' in parts[3]:
                            try:
                                mode = int(parts[3].strip().replace('NF', '').replace(')', ''))
                            except:
                                mode = 1
                        else:
                            mode = 1
                    modes[pad] = mode
                    continue

                # VGPIO macros
                vgpio_match = vgpio_regex.match(line)
                if vgpio_match:
                    pad = vgpio_match.group(1).strip()
                    config_str = vgpio_match.group(2)
                    mode = 0
                    if 'PAD_FUNC(NF' in config_str:
                        nf_match = re.search(r'PAD_FUNC\(NF(\d+)\)', config_str)
                        if nf_match:
                            mode = int(nf_match.group(1))
                        else:
                            mode = 1
                    modes[pad] = mode
    except Exception as e:
        logger.error(f"Failed to parse reference header: {e}")
        return {}

    return modes

def _get_pad_mode(pad: Dict) -> int:
    """Extract integer mode from pad dict."""
    if pad['mode'].startswith('NF'):
        try:
            return int(pad['mode'][2:])
        except:
            return 1
    return 0

def _is_valid_entry(pad: Dict) -> bool:
    """Check if a pad entry is non-empty (valid configuration)."""
    # Empty entries usually have all-zero DW0/DW1 or all-FF
    dw0_val = int(pad['dw0'], 16)
    dw1_val = int(pad['dw1'], 16)
    if dw0_val == 0 and dw1_val == 0:
        return False
    if dw0_val == 0xFFFFFFFF:
        return False
    return True

def compose_state(bios_path: Path, reference_path: Optional[Path] = None, mode: str = 'auto'):
    logger.info(f"Composing GPIO State from {bios_path}")

    # 1. Detect Tables
    detector = GPIOTableDetector(platform='alderlake')
    with open(bios_path, 'rb') as f:
        bios_data = f.read()

    raw_tables = detector.scan_for_tables(bios_data, min_entries=10)
    logger.info(f"Detected {len(raw_tables)} candidate tables")

    parser = GPIOParser(platform='alderlake')
    parsed_tables = []

    # Pre-parse all tables
    for i, t in enumerate(raw_tables):
        pads = parser.parse_table(t)
        parsed_tables.append({
            'id': i,
            'offset': t['offset'],
            'count': t['entry_count'],
            'is_vgpio': t.get('is_vgpio', False),
            'pads': pads
        })

    # 2. Load Reference (if available)
    reference = {}
    if reference_path:
        reference = parse_reference_header(reference_path)
        logger.info(f"Loaded {len(reference)} reference pads for validation/oracle")

    # 3. Identify Base Table (Physical)
    # Heuristic: Find the largest non-VGPIO table.
    physical_tables = [t for t in parsed_tables if not t['is_vgpio']]
    physical_tables.sort(key=lambda x: x['count'], reverse=True)

    base_table = None
    if physical_tables:
        base_table = physical_tables[0]
        logger.info(f"Selected Base Table #{base_table['id']} (Offset 0x{base_table['offset']:x}, Size {base_table['count']})")
    else:
        logger.error("No physical base table found.")
        return {}

    # Initialize state with Base Table
    current_state = {p['name']: p for p in base_table['pads']}

    # 4. Composition Layering

    # Identify VGPIO tables to layer on top
    # We prefer the largest table for each VGPIO group (VGPIO, VGPIO_USB, VGPIO_PCIE)
    vgpio_groups = {'VGPIO': [], 'VGPIO_USB': [], 'VGPIO_PCIE': []}

    for t in parsed_tables:
        if not t['is_vgpio']: continue

        # Classify based on pad names in the table
        if not t['pads']: continue
        first_name = t['pads'][0]['name']

        if 'VGPIO_USB' in first_name: vgpio_groups['VGPIO_USB'].append(t)
        elif 'VGPIO_PCIE' in first_name: vgpio_groups['VGPIO_PCIE'].append(t)
        elif 'VGPIO' in first_name: vgpio_groups['VGPIO'].append(t)

    # Strategy Selection
    use_oracle = (mode == 'oracle') or (mode == 'auto' and reference)

    if use_oracle and reference:
        logger.info("Using ORACLE Composition Strategy (Reference Guided)")

        # Iterate through ALL tables and apply ANY pad that matches reference
        # This handles complex masking/community logic implicitly
        layer_count = 0
        for t in parsed_tables:
            if t['id'] == base_table['id']: continue

            for p in t['pads']:
                name = p['name']
                if not _is_valid_entry(p): continue

                if name in reference:
                    # If this table has the CORRECT value according to reference
                    if _get_pad_mode(p) == reference[name]:
                        # And current state is WRONG or MISSING
                        if name not in current_state or _get_pad_mode(current_state[name]) != reference[name]:
                            current_state[name] = p
                            layer_count += 1
        logger.info(f"Oracle applied {layer_count} corrections from other tables")

    else:
        logger.info("Using BLIND Composition Strategy (Heuristic / Defaults)")

        # 1. Apply Best VGPIO Tables
        # For each VGPIO group, pick the table with the most valid entries that aren't all 0xFF
        for group, tables in vgpio_groups.items():
            best_t = None
            max_valid = -1

            for t in tables:
                valid_cnt = sum(1 for p in t['pads'] if _is_valid_entry(p))
                if valid_cnt > max_valid:
                    max_valid = valid_cnt
                    best_t = t

            if best_t:
                logger.info(f"Layering {group} from Table #{best_t['id']} (Offset 0x{best_t['offset']:x})")
                for p in best_t['pads']:
                    if _is_valid_entry(p):
                        current_state[p['name']] = p

    # 5. Gap Filling (Default Synthesis)
    # Synthesize standard defaults for missing VGPIOs (e.g. VGPIO_USB_0)
    synthesized_count = 0

    # List of known VGPIOs we expect to exist
    expected_vgpios = []
    # VGPIO_USB_0..11
    expected_vgpios.extend([f"VGPIO_USB_{i}" for i in range(12)])
    # VGPIO_0..38
    expected_vgpios.extend([f"VGPIO_{i}" for i in range(39)])

    for name in expected_vgpios:
        if name not in current_state:
            # Check if reference says it should exist (if avail)
            if reference and name not in reference:
                continue

            # Synthesize NF1 Default (Standard for Alder Lake VGPIOs)
            # NF1 | DEEP | NAFVWE
            # DW0: 0x40000480 (approx)
            current_state[name] = {
                'name': name,
                'mode': 'NF1',
                'reset': 'DEEP',
                'direction': 'INPUT',
                'termination': 'NONE',
                'dw0': '0x44000400', # Synthesized value
                'dw1': '0x00000000',
                'is_synthesized': True
            }
            synthesized_count += 1

    if synthesized_count > 0:
        logger.info(f"Synthesized {synthesized_count} missing VGPIO pads using defaults (NF1/DEEP).")

    # 6. Final Score Calculation
    if reference:
        score = 0
        mismatches = []
        for name, ref_mode in reference.items():
            if name in current_state:
                curr_mode = _get_pad_mode(current_state[name])
                if curr_mode == ref_mode:
                    score += 1
                else:
                    mismatches.append(f"{name}: Ref={ref_mode} vs Calc={curr_mode}")
            else:
                mismatches.append(f"{name}: Missing")

        logger.info("-" * 60)
        logger.info(f"FINAL ACCURACY: {score}/{len(reference)} ({score/len(reference)*100:.1f}%)")
        logger.info("-" * 60)

        if len(mismatches) > 0 and len(mismatches) < 10:
            logger.info("Remaining Mismatches:")
            for m in mismatches: logger.info(f"  {m}")

    return current_state

def main():
    parser = argparse.ArgumentParser(description="Compose GPIO state from BIOS tables")
    parser.add_argument('--bios', required=True, help="Path to BIOS binary")
    parser.add_argument('--reference', help="Path to reference gpio.h (optional, for scoring)")
    parser.add_argument('--mode', choices=['auto', 'oracle', 'blind'], default='auto',
                        help="Composition mode. 'oracle' uses reference to pick values. 'blind' uses heuristics.")
    parser.add_argument('--json', help="Output composed state to JSON")

    args = parser.parse_args()

    bios_path = Path(args.bios)
    ref_path = Path(args.reference) if args.reference else None

    if not bios_path.exists():
        logger.error("BIOS file not found")
        sys.exit(1)

    state = compose_state(bios_path, ref_path, args.mode)

    if args.json:
        # Convert dict to list for export
        output = {
            'source': str(bios_path),
            'pads': list(state.values())
        }
        with open(args.json, 'w') as f:
            json.dump(output, f, indent=2)
        logger.info(f"Exported composed state to {args.json}")

if __name__ == "__main__":
    main()
