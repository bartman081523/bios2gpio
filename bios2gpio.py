#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
bios2gpio - Extract GPIO configuration from vendor BIOS images
"""

import sys
import argparse
import logging
import os
import re
import shutil
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from uefi_extractor import UEFIExtractor
from gpio_detector import GPIOTableDetector
from gpio_parser import GPIOParser
from gpio_generator import GPIOGenerator
from platforms import GPIO_MODULE_PATTERNS
from ghidra_runner import run_ghidra_analysis

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

def find_ghidra_home():
    """Attempts to find Ghidra installation path."""
    # Check subfolder
    local_ghidra = Path(__file__).parent / "ghidra"
    if (local_ghidra / "support" / "analyzeHeadless").exists():
        return str(local_ghidra)

    # Check PATH
    headless_path = shutil.which("analyzeHeadless")
    if headless_path:
        # analyzeHeadless is usually in $GHIDRA_HOME/support/analyzeHeadless
        return str(Path(headless_path).parent.parent)

    return None

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

                # Handle _PAD_CFG_STRUCT for VGPIOs
                # _PAD_CFG_STRUCT(VGPIO_PCIE_0, PAD_FUNC(NF1) | PAD_RESET(DEEP) | PAD_CFG0_NAFVWE_ENABLE, 0),
                vgpio_match = re.match(r'^\s*_PAD_CFG_STRUCT\s*\(([^,]+),\s*(.+?),', line)
                if vgpio_match:
                    pad = vgpio_match.group(1).strip()
                    config_str = vgpio_match.group(2)
                    mode = 0 # Default GPIO

                    if 'PAD_FUNC(NF' in config_str:
                        # Extract NF number
                        nf_match = re.search(r'PAD_FUNC\(NF(\d+)\)', config_str)
                        if nf_match:
                            mode = int(nf_match.group(1))
                        else:
                            mode = 1 # Assume NF1 if not specified number
                    elif 'PAD_FUNC(GPIO)' in config_str:
                        mode = 0

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

    # Ghidra integration arguments
    parser.add_argument('--analyze-ghidra', action='store_true', help='Run Ghidra headless analysis to find GPIO loops')
    parser.add_argument('--no-ghidra', action='store_true', help='Disable Ghidra analysis even if detected')
    parser.add_argument('--ghidra-home', help='Path to Ghidra installation root')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Auto-detect Ghidra if not explicitly configured
    if not args.ghidra_home:
        found_home = find_ghidra_home()
        if found_home:
            args.ghidra_home = found_home
            if not args.no_ghidra and not args.analyze_ghidra:
                logger.info(f"Ghidra detected at {args.ghidra_home}. Enabling analysis.")
                args.analyze_ghidra = True

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

        # GHIDRA ANALYSIS LOGIC
        if args.analyze_ghidra:
            if not args.ghidra_home:
                logger.error("Ghidra analysis requested but GHIDRA_HOME not found/specified.")
                return 1

            logger.info(f"Starting Ghidra Analysis using {args.ghidra_home}...")

            # Identify candidates for Ghidra analysis
            # We prefer PE32 modules like PchInitDxe, GpioInit, etc.
            candidates = []

            def is_valid_binary(path):
                # Only accept .efi/.pe32 files, or body.bin inside a PE32 section
                if path.suffix.lower() in ['.efi', '.pe32']:
                    return True
                if path.name.lower() == 'body.bin':
                    # Check if parent directory indicates a PE32 section
                    # UEFIExtract usually names it "PE32 image section"
                    return 'pe32 image section' in path.parent.name.lower()
                return False

            if modules:
                for m in modules:
                    p = Path(m['path'])
                    if is_valid_binary(p):
                        candidates.append(p)
            else:
                # Fallback: try to find files with 'PchInit' or 'Gpio' in name
                for b in all_binaries:
                    if ('Init' in b.name or 'Gpio' in b.name) and is_valid_binary(b):
                        candidates.append(b)

            if not candidates:
                logger.error("No suitable modules found for Ghidra analysis.")
                return 1

            logger.info(f"Found {len(candidates)} candidate modules for analysis.")

            success_count = 0
            for cand in candidates:
                logger.info(f"Analyzing {cand.name}...")
                if run_ghidra_analysis(cand, ghidra_home=args.ghidra_home):
                    success_count += 1
                else:
                    logger.warning(f"Analysis failed for {cand.name}")

            logger.info(f"Ghidra analysis completed. Successful: {success_count}/{len(candidates)}")
            # For now, we don't stop here, we continue to the standard detection
            # In the future, we could use the Ghidra output to seed the detector

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
        # Strategy: Calibrate to find the best PHYSICAL GPIO table (8-byte stride)
        # but keep ALL VGPIO tables (12/16-byte stride) for complete coverage
        if args.calibrate_with:
            ref_modes = parse_calibration_header(args.calibrate_with)
            if ref_modes:
                logger.info(f"Calibrating against {len(ref_modes)} reference pads...")
                parser = GPIOParser(platform=args.platform)

                # Separate physical GPIO tables from VGPIO tables
                physical_tables = []
                vgpio_tables = []

                for table in all_tables:
                    # Use is_vgpio flag if available, otherwise check entry_size AND entry_count
                    is_vgpio = table.get('is_vgpio', False)

                    # If not explicitly marked as VGPIO, check if it could be one based on size
                    if not is_vgpio and table.get('entry_size', 8) > 8:
                        # Double-check: only classify as VGPIO if size matches known VGPIO ranges
                        # VGPIO_USB: 12-14 entries
                        # VGPIO: 37-38 entries
                        # VGPIO_PCIE: 78-81 entries
                        count = table.get('entry_count', 0)
                        is_vgpio = (10 <= count <= 15) or (35 <= count <= 40) or (75 <= count <= 85)

                    if is_vgpio:
                        table['is_vgpio'] = True
                        vgpio_tables.append(table)
                    else:
                        physical_tables.append(table)

                logger.info(f"Found {len(physical_tables)} physical GPIO tables and {len(vgpio_tables)} VGPIO tables")

                # Calibrate physical GPIO tables
                best_score = -1
                best_physical_table = None

                for table in physical_tables:
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
                    logger.info(f"Physical GPIO Table at {table['offset']:x} (Size {table['entry_count']}): Score {score} ({accuracy*100:.1f}%)")

                    if score > best_score:
                        best_score = score
                        best_physical_table = table

                # Calibrate VGPIO tables
                # Group by type
                vgpio_groups = {
                    'VGPIO_USB': [],   # 10-15 entries
                    'VGPIO': [],       # 35-42 entries
                    'VGPIO_PCIE': []   # 75-85 entries
                }

                for table in vgpio_tables:
                    count = table.get('entry_count', 0)
                    if 10 <= count <= 15:
                        vgpio_groups['VGPIO_USB'].append(table)
                    elif 35 <= count <= 42:
                        vgpio_groups['VGPIO'].append(table)
                    elif 75 <= count <= 85:
                        vgpio_groups['VGPIO_PCIE'].append(table)

                best_vgpio_tables = []

                for group_name, candidates in vgpio_groups.items():
                    if not candidates:
                        continue

                    best_group_score = -1
                    best_group_table = None

                    for table in candidates:
                        # Parse this table (parser handles VGPIO naming based on size)
                        pads = parser.parse_table(table)

                        # Score it
                        score = 0
                        valid_pads = 0
                        for pad in pads:
                            name = pad['name']
                            if name in ref_modes:
                                valid_pads += 1
                                # Mode match?
                                ext_mode = 0
                                if pad['mode'].startswith('NF'):
                                    try: ext_mode = int(pad['mode'][2:])
                                    except: ext_mode = 1

                                if ext_mode == ref_modes[name]:
                                    score += 1

                        # For VGPIO, we care about how many valid pads we found that match the reference
                        logger.info(f"{group_name} Candidate at {table['offset']:x} (Size {table['entry_count']}): Score {score}/{valid_pads}")

                        if score > best_group_score:
                            best_group_score = score
                            best_group_table = table

                    if best_group_table:
                        logger.info(f"Selected best {group_name} table at {best_group_table['offset']:x} with score {best_group_score}")
                        best_vgpio_tables.append(best_group_table)

                if best_physical_table:
                    logger.info(f"CALIBRATION WINNER (Physical GPIO): Table at {best_physical_table['offset']:x} with score {best_score}")
                    # Use the best physical table + best VGPIO tables
                    best_tables = [best_physical_table] + best_vgpio_tables
                    logger.info(f"Using {len(best_tables)} tables total (1 physical + {len(best_vgpio_tables)} VGPIO)")
                else:
                    logger.warning("Calibration failed to find a valid physical table, using all detected tables")
                    best_tables = all_tables
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
