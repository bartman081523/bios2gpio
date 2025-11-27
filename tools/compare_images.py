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

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.extractor import UEFIExtractor
from src.core.detector import GPIOTableDetector
from src.core.parser import GPIOParser

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
        
        # 2. Detect - scan BIOS region directly
        detector = GPIOTableDetector(platform=platform)
        files_to_scan = []
        if bios_region and bios_region.exists(): 
            files_to_scan.append(bios_region)
        
        if not files_to_scan:
            logger.error(f"  No BIOS region extracted from {image_path.name}")
            return {}

        all_tables = []
        for file_path in files_to_scan:
            tables = detector.scan_file(file_path)
            all_tables.extend(tables)

        if not all_tables:
            logger.error(f"  No GPIO tables found in {image_path.name}")
            return {}

        # 3. Select Best Tables (Winner + VGPIOs)
        # We trust the detector's internal sorting (signature match + size heuristic)
        best_tables = detector.filter_best_tables(all_tables)
        if not best_tables:
            logger.error(f"  No valid tables found in {image_path.name}")
            return {}

        logger.info(f"  Found {len(best_tables)} tables.")

        # 4. Parse and Merge
        parser = GPIOParser(platform=platform)
        parsed_data = parser.parse_multiple_tables(best_tables)
        pads_list = parser.merge_tables(parsed_data)

        # Convert to dict keyed by name for comparison
        return {pad['name']: pad for pad in pads_list}

    except Exception as e:
        logger.error(f"  Extraction failed: {e}")
        return {}
    finally:
        # cleanup handled by UEFIExtractor destructor, but explicit check helps
        pass

def compare_pads_by_type(pads_a: Dict[str, Any], pads_b: Dict[str, Any]) -> tuple:
    """
    Separate and compare physical GPIOs from VGPIOs.
    
    Returns: (physical_pads_a, physical_pads_b, vgpio_pads_a, vgpio_pads_b)
    """
    physical_a = {k: v for k, v in pads_a.items() if not v.get('is_vgpio', False)}
    physical_b = {k: v for k, v in pads_b.items() if not v.get('is_vgpio', False)}
    vgpio_a = {k: v for k, v in pads_a.items() if v.get('is_vgpio', False)}
    vgpio_b = {k: v for k, v in pads_b.items() if v.get('is_vgpio', False)}
    
    return physical_a, physical_b, vgpio_a, vgpio_b

def compare_pad_set(pads_a: Dict[str, Any], pads_b: Dict[str, Any], name_a: str, name_b: str) -> Dict[str, int]:
    """
    Compare a set of pads and return statistics.
    
    Returns: dict with 'matches', 'mismatches', 'missing_a', 'missing_b'
    """
    all_keys = sorted(set(pads_a.keys()) | set(pads_b.keys()))
    
    matches = 0
    mismatches = 0
    missing_a = 0
    missing_b = 0
    
    diffs_detail = []

    for name in all_keys:
        pad_a = pads_a.get(name)
        pad_b = pads_b.get(name)

        if not pad_a:
            missing_a += 1
            diffs_detail.append((name, 'MISSING_A', f'(Not in {name_a})', 'Present'))
            continue
        if not pad_b:
            missing_b += 1
            diffs_detail.append((name, 'MISSING_B', 'Present', f'(Not in {name_b})'))
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
                if pad_a.get('termination') != pad_b.get('termination'):
                    diffs.append(('Term', pad_a['termination'], pad_b['termination']))
                else:
                    diffs.append(('Raw', 'DW0/1 Diff', 'DW0/1 Diff'))

        if diffs:
            mismatches += 1
            for field, val_a, val_b in diffs:
                diffs_detail.append((name, field, str(val_a), str(val_b)))
        else:
            matches += 1
    
    return {
        'matches': matches,
        'mismatches': mismatches,
        'missing_a': missing_a,
        'missing_b': missing_b,
        'total': len(all_keys),
        'details': diffs_detail
    }

def print_comparison_section(section_name: str, stats: Dict[str, int], name_a: str, name_b: str):
    """Print a formatted comparison section for a specific pad type"""
    print("\n" + "="*80)
    print(f"{section_name} COMPARISON")
    print("="*80)
    
    if stats['total'] == 0:
        print(f"(No {section_name.lower()} pads found)")
        return
    
    print(f"{'Pad Name':<20} | {'Field':<10} | {name_a[:18]:<20} | {name_b[:18]:<20}")
    print("-" * 80)
    
    for detail in stats['details']:
        name, field, val_a, val_b = detail
        print(f"{name:<20} | {field:<10} | {str(val_a):<20} | {str(val_b):<20}")
    
    print("-" * 80)
    print(f"Total Pads: {stats['total']}")
    print(f"Identical:  {stats['matches']:4d} ({stats['matches']/stats['total']*100:5.1f}%)")
    print(f"Different:  {stats['mismatches']:4d} ({stats['mismatches']/stats['total']*100:5.1f}%)")
    if stats['missing_a'] > 0:
        print(f"Missing in {name_a}: {stats['missing_a']}")
    if stats['missing_b'] > 0:
        print(f"Missing in {name_b}: {stats['missing_b']}")

def compare_pads(pads_a: Dict[str, Any], pads_b: Dict[str, Any], name_a: str, name_b: str):
    """
    Compare two sets of pads with SEPARATION of physical GPIO and VGPIO comparisons.
    
    This is the core falsification method: it separates physical GPIO configuration
    from VGPIO configuration to allow independent verification of each type.
    """
    
    # Separate physical GPIO from VGPIO
    physical_a, physical_b, vgpio_a, vgpio_b = compare_pads_by_type(pads_a, pads_b)
    
    print("\n" + "="*90)
    print(f"COMPREHENSIVE GPIO COMPARISON: {name_a} vs {name_b}")
    print("="*90)
    
    # Compare physical GPIOs
    physical_stats = compare_pad_set(physical_a, physical_b, name_a, name_b)
    print_comparison_section("PHYSICAL GPIO", physical_stats, name_a, name_b)
    
    # Compare VGPIOs
    vgpio_stats = compare_pad_set(vgpio_a, vgpio_b, name_a, name_b)
    print_comparison_section("VGPIO", vgpio_stats, name_a, name_b)
    
    # Overall summary with clear separation
    print("\n" + "="*90)
    print("FALSIFICATION SUMMARY")
    print("="*90)
    
    if physical_stats['total'] > 0:
        phys_identical = (physical_stats['matches'] == physical_stats['total'] and 
                         physical_stats['missing_a'] == 0 and physical_stats['missing_b'] == 0)
        print(f"Physical GPIO Status: {'✓ IDENTICAL' if phys_identical else '✗ DIFFERENT'}")
        print(f"  Matching: {physical_stats['matches']}/{physical_stats['total']} pads")
    
    if vgpio_stats['total'] > 0:
        vgpio_identical = (vgpio_stats['matches'] == vgpio_stats['total'] and 
                          vgpio_stats['missing_a'] == 0 and vgpio_stats['missing_b'] == 0)
        print(f"VGPIO Status:        {'✓ IDENTICAL' if vgpio_identical else '✗ DIFFERENT'}")
        print(f"  Matching: {vgpio_stats['matches']}/{vgpio_stats['total']} pads")
    
    # Final verdict
    print("\n" + "-"*90)
    all_identical = (physical_stats['total'] > 0 and physical_stats['mismatches'] == 0 and 
                     physical_stats['missing_a'] == 0 and physical_stats['missing_b'] == 0 and
                     vgpio_stats['total'] == 0)  # Also OK if no VGPIOs
    
    if all_identical:
        print(">>> CONCLUSION: Physical GPIO configurations are BIT-IDENTICAL. <<<")
        print(">>> You can safely use the exact same gpio.h for both boards. <<<")
    elif (physical_stats['total'] > 0 and physical_stats['mismatches'] == 0 and 
          physical_stats['missing_a'] == 0 and physical_stats['missing_b'] == 0):
        print(">>> CONCLUSION: Physical GPIOs are IDENTICAL but VGPIOs differ. <<<")
        print(">>> Board-specific VGPIO configuration (e.g., USB routing) differs. <<<")
    else:
        print(">>> CONCLUSION: Physical GPIO configurations DIFFER significantly. <<<")
    
    print("="*90)

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
