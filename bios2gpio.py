#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
bios2gpio - Extract GPIO configuration from vendor BIOS images
"""

import sys
import argparse
import logging
import re
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from uefi_extractor import UEFIExtractor
from gpio_detector import GPIOTableDetector
from gpio_parser import GPIOParser
from gpio_generator import GPIOGenerator
from platforms import GPIO_MODULE_PATTERNS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

def parse_calibration_header(filepath):
    """Parses a gpio.h file to extract expected pad modes for calibration."""
    modes = {}
    regex = re.compile(r'^\s*PAD_CFG_([A-Z0-9_]+)\s*\(([^,]+),')

    macro_map = {
        'GPO': 0, 'GPI': 0, 'NF': 1 # Default NF1
    }

    try:
        with open(filepath, 'r') as f:
            for line in f:
                match = regex.match(line)
                if match:
                    mtype = match.group(1)
                    pad = match.group(2).strip()
                    mode = 0

                    if 'NF' in mtype:
                        # Try to find NFx arg
                        parts = line.split(',')
                        if len(parts) >= 4 and 'NF' in parts[3]:
                            try:
                                mode = int(parts[3].strip().replace('NF', '').replace(')', ''))
                            except:
                                mode = 1
                        else:
                            mode = 1

                    modes[pad] = mode
    except Exception as e:
        logger.error(f"Failed to parse calibration header: {e}")
        return None

    return modes

def main():
    parser = argparse.ArgumentParser(
        description='Extract GPIO configuration from vendor BIOS images'
    )

    parser.add_argument('--platform', default='alderlake', choices=['alderlake'])
    parser.add_argument('--input', '-i', required=True)
    parser.add_argument('--output', '-o')
    parser.add_argument('--json', '-j')
    parser.add_argument('--report', '-r')
    parser.add_argument('--work-dir', '-w')
    parser.add_argument('--min-entries', type=int, default=10)
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--calibrate-with', help='Path to reference gpio.h for scoring candidates')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input file not found: {args.input}")
        return 1

    logger.info(f"bios2gpio - Extracting GPIO from {input_path}")
    logger.info(f"Platform: {args.platform}")

    try:
        # Step 1: Extract UEFI modules
        logger.info("Step 1: Extracting UEFI modules...")
        extractor = UEFIExtractor(str(input_path), args.work_dir)
        if not extractor.check_dependencies(): return 1

        bios_region = extractor.get_bios_region()
        modules = extractor.find_modules(GPIO_MODULE_PATTERNS)
        all_binaries = extractor.get_all_binary_files()

        # Step 2: Detect GPIO tables
        logger.info("Step 2: Detecting GPIO tables...")
        detector = GPIOTableDetector(platform=args.platform)

        files_to_scan = []
        
        # Priority 1: Scan the BIOS region file (contains all GPIO tables)
        if bios_region and bios_region.exists():
            files_to_scan.append(bios_region)
            logger.info(f"Scanning BIOS region: {bios_region}")
        # Priority 2: If no BIOS region, scan GPIO-specific modules
        elif modules:
            files_to_scan.extend([m['path'] for m in modules])
            logger.info(f"Scanning {len(modules)} GPIO modules")
        # Fallback: Scan all binaries (slow)
        else:
            files_to_scan.extend(all_binaries[:50])  # Limit to first 50 to avoid excessive scanning
            logger.info(f"Scanning first 50 binary files")
        
        files_to_scan = list(set(files_to_scan))

        logger.info(f"Scanning {len(files_to_scan)} files...")
        all_tables = []
        for file_path in files_to_scan:
            tables = detector.scan_file(file_path, min_entries=args.min_entries)
            all_tables.extend(tables)

        if not all_tables:
            logger.error("No GPIO tables found")
            return 1

        logger.info(f"Detected {len(all_tables)} potential tables")

        # CALIBRATION LOGIC
        if args.calibrate_with:
            ref_modes = parse_calibration_header(args.calibrate_with)
            if ref_modes:
                logger.info(f"Calibrating against {len(ref_modes)} reference pads...")
                parser = GPIOParser(platform=args.platform)

                best_score = -1
                best_table = None

                for table in all_tables:
                    # Parse this table
                    pads = parser.parse_table(table)

                    # Score it
                    score = 0
                    for pad in pads:
                        name = pad['name']
                        if name in ref_modes:
                            # Mode match?
                            ext_mode = 0
                            if pad['mode'].startswith('NF'):
                                try: ext_mode = int(pad['mode'][2:])
                                except: ext_mode = 1

                            if ext_mode == ref_modes[name]:
                                score += 1

                    # Normalize score by table size to penalize garbage
                    accuracy = score / len(ref_modes) if ref_modes else 0
                    logger.info(f"Table at {table['offset']:x} (Size {table['entry_count']}): Score {score} ({accuracy*100:.1f}%)")

                    if score > best_score:
                        best_score = score
                        best_table = table

                if best_table:
                    logger.info(f"CALIBRATION WINNER: Table at {best_table['offset']:x} with score {best_score}")
                    best_tables = [best_table]
                else:
                    best_tables = detector.filter_best_tables(all_tables)
            else:
                best_tables = detector.filter_best_tables(all_tables)
        else:
            best_tables = detector.filter_best_tables(all_tables)

        # Step 3: Parse
        logger.info("Step 3: Parsing GPIO configurations...")
        parser = GPIOParser(platform=args.platform)
        parsed_data = parser.parse_multiple_tables(best_tables)
        merged_pads = parser.merge_tables(parsed_data)

        logger.info(f"Merged to {len(merged_pads)} unique pads")

        # Step 4: Generate
        generator = GPIOGenerator(platform=args.platform)
        if args.json:
            parsed_data['pads'] = merged_pads
            parser.export_json(parsed_data, Path(args.json))
        if args.output:
            generator.generate_coreboot_header(merged_pads, Path(args.output))

        return 0

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.verbose)
        return 1

if __name__ == '__main__':
    sys.exit(main())
