#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
gpio_comparator.py - Compare extracted GPIO configurations against reference.

This tool compares GPIO configurations extracted by bios2gpio against
a reference (either an existing coreboot gpio.h or another JSON dump).
It is used to validate the extraction accuracy.
"""

import argparse
import json
import re
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Regex for parsing coreboot GPIO macros
# Matches: PAD_CFG_MACRO(PAD_NAME, ARG1, ARG2, ...) and _PAD_CFG_STRUCT
MACRO_REGEX = re.compile(r'^\s*(_?PAD_CFG_[A-Z0-9_]+|_PAD_CFG_STRUCT)\s*\((.+)\)\s*,?\s*(?:/\*.*?\*/)?\s*$')

def parse_gpio_h(file_path: Path) -> Dict[str, Dict]:
    """
    Parse a coreboot gpio.h file into a dictionary of pads.

    Args:
        file_path: Path to gpio.h

    Returns:
        Dict mapping pad name to configuration dict
    """
    pads = {}

    with open(file_path, 'r') as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        match = MACRO_REGEX.match(line)
        if match:
            macro_name = match.group(1)
            args_str = match.group(2)

            # Split args by comma, respecting parentheses (simple version)
            # This handles simple macros. Complex logic like (A | B) might need more robust parsing
            args = [a.strip() for a in args_str.split(',')]

            if not args:
                continue

            pad_name = args[0]

            # Basic interpretation based on macro type
            config = {
                'macro': macro_name,
                'args': args,
                'name': pad_name
            }

            # Handle _PAD_CFG_STRUCT (VGPIOs)
            if macro_name == '_PAD_CFG_STRUCT':
                # _PAD_CFG_STRUCT(pad_name, flags, dw1)
                # Parse flags to extract mode
                if len(args) > 1:
                    flags = args[1]
                    if 'PAD_FUNC(GPIO)' in flags:
                        config['mode'] = 'GPIO'
                        # Determine direction from buffer config
                        if 'PAD_BUF(RX_DISABLE)' in flags or 'RX_DISABLE' in flags:
                            config['direction'] = 'OUTPUT'
                        elif 'PAD_BUF(TX_DISABLE)' in flags or 'TX_DISABLE' in flags:
                            config['direction'] = 'INPUT'
                        else:
                            config['direction'] = 'INPUT'  # Default
                    elif 'PAD_FUNC(NF' in flags:
                        # Extract NF number
                        nf_match = re.search(r'PAD_FUNC\((NF\d+)\)', flags)
                        if nf_match:
                            config['mode'] = nf_match.group(1)
                        else:
                            config['mode'] = 'NF'
            # Handle standard macros
            elif 'GPO' in macro_name:
                config['mode'] = 'GPIO'
                config['direction'] = 'OUTPUT'
                if len(args) > 1:
                    config['output_value'] = 1 if args[1] == '1' else 0
            elif 'GPI' in macro_name:
                config['mode'] = 'GPIO'
                config['direction'] = 'INPUT'
            elif 'NF' in macro_name:
                # PAD_CFG_NF(pad, term, rst, func)
                if len(args) >= 4:
                    config['mode'] = args[3] # NF1, NF2, etc.
                else:
                    config['mode'] = 'NF'

            pads[pad_name] = config

    return pads

def load_json(file_path: Path) -> Dict[str, Dict]:
    """
    Load GPIO data from JSON file.

    Args:
        file_path: Path to JSON file

    Returns:
        Dict mapping pad name to configuration dict
    """
    with open(file_path, 'r') as f:
        data = json.load(f)

    pads = {}

    # Handle both raw output and normalized output
    pad_list = data.get('pads', [])
    if not pad_list and 'tables' in data:
        # Fallback: use first table if 'pads' not present
        pad_list = data['tables'][0].get('pads', [])

    for pad in pad_list:
        name = pad.get('name')
        if name:
            pads[name] = pad

    return pads

def compare_pads(extracted: Dict[str, Dict], reference: Dict[str, Dict]) -> Dict:
    """
    Compare extracted pads against reference.

    Args:
        extracted: Extracted pad dict
        reference: Reference pad dict

    Returns:
        Comparison statistics and mismatch details
    """
    results = {
        'total_ref': len(reference),
        'total_ext': len(extracted),
        'exact_matches': [],
        'partial_matches': [],
        'mismatches': [],
        'missing_in_extracted': [],
        'extra_in_extracted': []
    }

    # Check reference pads
    for name, ref_pad in reference.items():
        if name not in extracted:
            results['missing_in_extracted'].append(name)
            continue

        ext_pad = extracted[name]

        # Comparison logic
        # 1. Compare Mode
        ref_mode = ref_pad.get('mode')
        ext_mode = ext_pad.get('mode')

        # Normalize modes for comparison
        if ref_mode and ext_mode:
            match = (ref_mode == ext_mode)
            # Allow NFx vs NF mismatch if one is generic
            if not match and 'NF' in ref_mode and 'NF' in ext_mode:
                match = True

            if match:
                # If mode matches, check direction for GPIOs
                if ref_mode == 'GPIO':
                    ref_dir = ref_pad.get('direction')
                    ext_dir = ext_pad.get('direction')
                    if ref_dir and ext_dir and ref_dir != ext_dir:
                        results['partial_matches'].append({
                            'pad': name,
                            'issue': f"Direction mismatch: Ref={ref_dir}, Ext={ext_dir}"
                        })
                        continue

                results['exact_matches'].append(name)
            else:
                results['mismatches'].append({
                    'pad': name,
                    'issue': f"Mode mismatch: Ref={ref_mode}, Ext={ext_mode}"
                })
        else:
             # Loose comparison if mode missing
             results['exact_matches'].append(name)

    # Check for extra pads
    for name in extracted:
        if name not in reference:
            results['extra_in_extracted'].append(name)

    return results

def print_report(results: Dict):
    """Print human-readable comparison report"""
    print("=" * 60)
    print("GPIO Comparison Report")
    print("=" * 60)
    print(f"Reference Pads: {results['total_ref']}")
    print(f"Extracted Pads: {results['total_ext']}")
    print("-" * 60)

    n_exact = len(results['exact_matches'])
    n_partial = len(results['partial_matches'])
    n_mismatch = len(results['mismatches'])
    n_missing = len(results['missing_in_extracted'])
    n_extra = len(results['extra_in_extracted'])

    score = (n_exact + n_partial * 0.5) / results['total_ref'] * 100 if results['total_ref'] > 0 else 0

    print(f"Exact Matches:      {n_exact:4d} ({n_exact/results['total_ref']*100:.1f}%)")
    print(f"Partial Matches:    {n_partial:4d}")
    print(f"Mismatches:         {n_mismatch:4d}")
    print(f"Missing:            {n_missing:4d}")
    print(f"Extras:             {n_extra:4d}")
    print("-" * 60)
    print(f"Overall Match Score: {score:.1f}%")
    print("=" * 60)

    if results['mismatches']:
        print("\nMismatches (Critical):")
        for item in results['mismatches'][:10]:
            print(f"  {item['pad']}: {item['issue']}")
        if len(results['mismatches']) > 10:
            print(f"  ... and {len(results['mismatches']) - 10} more")

    if results['partial_matches']:
        print("\nPartial Matches (Check details):")
        for item in results['partial_matches'][:5]:
            print(f"  {item['pad']}: {item['issue']}")

    if results['missing_in_extracted']:
        print("\nMissing in Extraction (Potential detection failure):")
        print("  " + ", ".join(results['missing_in_extracted'][:10]) + ("..." if len(results['missing_in_extracted']) > 10 else ""))

def main():
    parser = argparse.ArgumentParser(description='Compare extracted GPIOs against reference')
    parser.add_argument('--extracted', '-e', required=True, help='Extracted JSON file')
    parser.add_argument('--reference', '-r', required=True, help='Reference JSON or gpio.h file')
    parser.add_argument('--output', '-o', help='Output report file')

    args = parser.parse_args()

    # Load extracted data
    try:
        extracted_pads = load_json(Path(args.extracted))
    except Exception as e:
        logger.error(f"Failed to load extracted JSON: {e}")
        return 1

    # Load reference data
    ref_path = Path(args.reference)
    try:
        if ref_path.suffix == '.h':
            reference_pads = parse_gpio_h(ref_path)
        else:
            reference_pads = load_json(ref_path)
    except Exception as e:
        logger.error(f"Failed to load reference file: {e}")
        return 1

    # Compare
    results = compare_pads(extracted_pads, reference_pads)

    # Output
    print_report(results)

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)

    return 0 if len(results['mismatches']) == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
