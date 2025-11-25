#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
compare_images.py - Compare GPIO configurations between two vendor BIOS images.
Splits analysis into Physical and Virtual domains to validate board compatibility.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from uefi_extractor import UEFIExtractor
from gpio_detector import GPIOTableDetector
from gpio_parser import GPIOParser
from bios2gpio import compose_gpio_state

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def extract_best_state(image_path: Path, platform: str) -> Dict[str, Any]:
    """Runs the full detection & blind composition pipeline on an image."""
    logger.info(f"Extracting from: {image_path.name}...")
    try:
        extractor = UEFIExtractor(str(image_path))
        bios_region = extractor.get_bios_region()

        detector = GPIOTableDetector(platform=platform)
        # Scan only BIOS region for speed and accuracy (assuming monolithic table)
        raw_tables = detector.scan_file(bios_region, min_entries=10)

        if not raw_tables:
            logger.error(f"No tables found in {image_path.name}")
            return {}

        # Use detector to find the best physical base table
        filtered = detector.filter_best_tables(raw_tables)
        if not filtered:
            return {}
        base_table = filtered[0]

        # Run Blind Composition (no reference, no ghidra for now)
        # We wrap the result list back to a dict for easy comparison
        pads_list = compose_gpio_state(raw_tables, base_table, None, None)
        return {p['name']: p for p in pads_list}

    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return {}

def compare_subset(pads_a, pads_b, subset_names, label):
    """Compare a specific subset of pads (Physical or VGPIO)."""
    matches = 0
    mismatches = 0
    missing_a = 0
    missing_b = 0

    diffs = []

    for name in subset_names:
        pa = pads_a.get(name)
        pb = pads_b.get(name)

        if not pa: missing_a += 1; continue
        if not pb: missing_b += 1; continue

        # Compare critical fields
        # We compare Mode, and if Mode==GPIO, we compare Direction/Output
        # We ignore Reset usually as it's often same, but let's be strict

        match = True
        # Mode check (NF1 vs GPIO)
        if pa['mode'] != pb['mode']: match = False

        # If GPIO, check direction/value
        if match and pa['mode'] == 'GPIO':
            if pa.get('direction') != pb.get('direction'): match = False
            if pa.get('output_value') != pb.get('output_value'): match = False

        if match:
            matches += 1
        else:
            mismatches += 1
            diffs.append(f"{name}: A={pa['mode']}/{pa.get('direction','')} vs B={pb['mode']}/{pb.get('direction','')}")

    total = matches + mismatches + missing_a + missing_b
    if total == 0: return

    print(f"\n--- {label} Comparison ---")
    print(f"Total Pads: {total}")
    print(f"Identical:  {matches} ({matches/total*100:.1f}%)")
    print(f"Mismatches: {mismatches}")
    if diffs:
        print("  Sample Mismatches:")
        for d in diffs[:5]: print(f"    {d}")
    if missing_a: print(f"  Missing in A: {missing_a}")
    if missing_b: print(f"  Missing in B: {missing_b}")

def main():
    parser = argparse.ArgumentParser(description="Compare GPIOs between two BIOS images")
    parser.add_argument("--image-a", "-a", required=True, help="Reference BIOS image (e.g. MSI)")
    parser.add_argument("--image-b", "-b", required=True, help="Target BIOS image (e.g. ASRock)")
    parser.add_argument("--platform", default="alderlake")
    args = parser.parse_args()

    path_a = Path(args.image_a)
    path_b = Path(args.image_b)

    pads_a = extract_best_state(path_a, args.platform)
    pads_b = extract_best_state(path_b, args.platform)

    if not pads_a or not pads_b:
        return 1

    # Separate keys
    all_keys = set(pads_a.keys()) | set(pads_b.keys())

    physical_keys = sorted([k for k in all_keys if 'VGPIO' not in k])
    virtual_keys = sorted([k for k in all_keys if 'VGPIO' in k])

    print("\n" + "="*60)
    print(f"COMPARISON: {path_a.name} (A) vs {path_b.name} (B)")
    print("="*60)

    compare_subset(pads_a, pads_b, physical_keys, "PHYSICAL GPIOs (Unvirtual)")
    compare_subset(pads_a, pads_b, virtual_keys, "VIRTUAL GPIOs (VGPIO)")

    print("\n" + "="*60)

    # Heuristic Verdict
    phys_match_rate = 0
    phys_common = set(physical_keys) & set(pads_a.keys()) & set(pads_b.keys())
    if phys_common:
        matches = sum(1 for k in phys_common if pads_a[k]['mode'] == pads_b[k]['mode']) # Simple mode check
        phys_match_rate = matches / len(phys_common)

    if phys_match_rate > 0.98:
        print("VERDICT: Boards likely share the same physical layout.")
        print("You can trust the 'Unvirtual' GPIOs extracted from ASRock.")
    else:
        print("VERDICT: Significant physical differences detected.")
        print("Verify schematic or use caution.")

if __name__ == '__main__':
    sys.exit(main())
