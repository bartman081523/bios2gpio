#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
compare_images.py - Compare GPIO configurations between two vendor BIOS images.

This tool extracts GPIO tables from two different BIOS images and performs
a pad-by-pad comparison to determine if they share the same configuration.
"""

import argparse
import logging
import sys
import shutil
from pathlib import Path
from typing import Dict, List, Any

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from uefi_extractor import UEFIExtractor
from gpio_detector import GPIOTableDetector
from gpio_parser import GPIOParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

def extract_pads_from_image(image_path: Path, platform: str) -> Dict[str, Any]:
    """
    Run the extraction pipeline on a single image and return the pad dict.
    """
    logger.info(f"Extracting from: {image_path.name}...")

    extractor = None
    try:
        # 1. Extract
        extractor = UEFIExtractor(str(image_path))
        bios_region = extractor.get_bios_region()
        modules = extractor.find_modules([]) # No pattern needed for raw scan fallback
        all_binaries = extractor.get_all_binary_files()

        # 2. Detect
        detector = GPIOTableDetector(platform=platform)
        files_to_scan = []
        if modules: files_to_scan.extend([m['path'] for m in modules])
        if bios_region and bios_region.exists(): files_to_scan.append(bios_region)
        if not modules: files_to_scan.extend(all_binaries)
        files_to_scan = list(set(files_to_scan))

        all_tables = []
        for file_path in files_to_scan:
            tables = detector.scan_file(file_path)
            all_tables.extend(tables)

        if not all_tables:
            logger.error(f"  No GPIO tables found in {image_path.name}")
            return {}

        # 3. Select Best Table (Winner)
        # We trust the detector's internal sorting (signature match + size heuristic)
        best_tables = detector.filter_best_tables(all_tables, max_tables=1)
        if not best_tables:
            logger.error(f"  No valid tables found in {image_path.name}")
            return {}

        winner = best_tables[0]
        logger.info(f"  Found table: {winner['entry_count']} entries at offset 0x{winner['offset']:x}")

        # 4. Parse
        parser = GPIOParser(platform=platform)
        pads_list = parser.parse_table(winner)

        # Convert to dict keyed by name for comparison
        return {pad['name']: pad for pad in pads_list}

    except Exception as e:
        logger.error(f"  Extraction failed: {e}")
        return {}
    finally:
        # cleanup handled by UEFIExtractor destructor, but explicit check helps
        pass

def compare_pads(pads_a: Dict[str, Any], pads_b: Dict[str, Any], name_a: str, name_b: str):
    """Compare two sets of pads and print a report."""

    all_keys = sorted(set(pads_a.keys()) | set(pads_b.keys()))

    matches = 0
    mismatches = 0
    missing_a = 0
    missing_b = 0

    print("\n" + "="*80)
    print(f"COMPARISON REPORT: {name_a} vs {name_b}")
    print("="*80)
    print(f"{'Pad Name':<15} | {'Param':<10} | {name_a[:15]:<18} | {name_b[:15]:<18}")
    print("-" * 80)

    # Fields to compare
    fields = ['mode', 'direction', 'output_value', 'reset', 'termination', 'dw0', 'dw1']

    for name in all_keys:
        pad_a = pads_a.get(name)
        pad_b = pads_b.get(name)

        if not pad_a:
            print(f"{name:<15} | {'MISSING':<10} | {'(Not present)':<18} | {'Present':<18}")
            missing_a += 1
            continue
        if not pad_b:
            print(f"{name:<15} | {'MISSING':<10} | {'Present':<18} | {'(Not present)':<18}")
            missing_b += 1
            continue

        # Compare fields
        diffs = []

        # Logical Check
        if pad_a['mode'] != pad_b['mode']:
            diffs.append(('Mode', pad_a['mode'], pad_b['mode']))
        elif pad_a['mode'] == 'GPIO':
            # If both GPIO, check direction/output
            if pad_a.get('direction') != pad_b.get('direction'):
                diffs.append(('Dir', pad_a.get('direction'), pad_b.get('direction')))
            if pad_a.get('output_value') != pad_b.get('output_value'):
                diffs.append(('Val', str(pad_a.get('output_value')), str(pad_b.get('output_value'))))

        if pad_a['reset'] != pad_b['reset']:
            diffs.append(('Reset', pad_a['reset'], pad_b['reset']))

        # Raw Register Check (Ultimate Truth)
        if pad_a['dw0'] != pad_b['dw0'] or pad_a['dw1'] != pad_b['dw1']:
            # If logical was same but raw diffs (e.g. termination or interrupt flags)
            if not diffs:
                if pad_a['termination'] != pad_b['termination']:
                    diffs.append(('Term', pad_a['termination'], pad_b['termination']))
                else:
                    diffs.append(('Raw', 'DW0/1 Diff', 'DW0/1 Diff'))

        if diffs:
            mismatches += 1
            for field, val_a, val_b in diffs:
                print(f"{name:<15} | {field:<10} | {str(val_a):<18} | {str(val_b):<18}")
        else:
            matches += 1

    print("-" * 80)
    total = len(all_keys)
    print(f"Total Pads: {total}")
    print(f"Identical:  {matches} ({matches/total*100:.1f}%)")
    print(f"Differences:{mismatches}")
    print(f"Unique {name_a}: {missing_b}")
    print(f"Unique {name_b}: {missing_a}")
    print("="*80)

    if mismatches == 0 and missing_a == 0 and missing_b == 0:
        print("\n>>> CONCLUSION: The GPIO configurations are BIT-IDENTICAL. <<<")
        print(">>> You can safely use the exact same gpio.h for both boards. <<<")
    elif mismatches < 5:
        print("\n>>> CONCLUSION: Extremely similar. Likely same reference code with minor tweaks. <<<")
    else:
        print("\n>>> CONCLUSION: Configurations differ significantly. <<<")

def main():
    parser = argparse.ArgumentParser(description="Compare GPIOs between two BIOS images")
    parser.add_argument("--image-a", "-a", required=True, help="First BIOS image")
    parser.add_argument("--image-b", "-b", required=True, help="Second BIOS image")
    parser.add_argument("--platform", default="alderlake")
    args = parser.parse_args()

    path_a = Path(args.image_a)
    path_b = Path(args.image_b)

    if not path_a.exists() or not path_b.exists():
        logger.error("Input files not found.")
        return 1

    pads_a = extract_pads_from_image(path_a, args.platform)
    pads_b = extract_pads_from_image(path_b, args.platform)

    if not pads_a or not pads_b:
        logger.error("Failed to extract pads from one or both images.")
        return 1

    compare_pads(pads_a, pads_b, path_a.name, path_b.name)
    return 0

if __name__ == '__main__':
    sys.exit(main())
