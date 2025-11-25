#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
bios2gpio - Extract GPIO configuration from vendor BIOS images
"""

import sys
import argparse
import logging
import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional

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
    local_ghidra = Path(__file__).parent / "ghidra"
    if (local_ghidra / "support" / "analyzeHeadless").exists():
        return str(local_ghidra)

    headless_path = shutil.which("analyzeHeadless")
    if headless_path:
        return str(Path(headless_path).parent.parent)
    return None

def parse_reference_header(filepath: Path) -> Dict[str, int]:
    """Parses a reference gpio.h file for Oracle Composition."""
    modes = {}
    regex = re.compile(r'^\s*PAD_CFG_([A-Z0-9_]+)\s*\(([^,]+),')
    vgpio_regex = re.compile(r'^\s*_PAD_CFG_STRUCT\s*\(([^,]+),\s*(.+?),')

    try:
        with open(filepath, 'r') as f:
            for line in f:
                match = regex.match(line)
                if match:
                    pad = match.group(2).strip()
                    mode = 0
                    mtype = match.group(1)
                    if 'NF' in mtype:
                        parts = line.split(',')
                        if len(parts) >= 4 and 'NF' in parts[3]:
                            try: mode = int(parts[3].strip().replace('NF', '').replace(')', ''))
                            except: mode = 1
                        else: mode = 1
                    modes[pad] = mode
                    continue

                vgpio_match = vgpio_regex.match(line)
                if vgpio_match:
                    pad = vgpio_match.group(1).strip()
                    config_str = vgpio_match.group(2)
                    mode = 0
                    if 'PAD_FUNC(NF' in config_str:
                        nf_match = re.search(r'PAD_FUNC\(NF(\d+)\)', config_str)
                        if nf_match: mode = int(nf_match.group(1))
                        else: mode = 1
                    modes[pad] = mode
    except Exception as e:
        logger.error(f"Failed to parse reference: {e}")
        return {}
    return modes

def _get_pad_mode(pad: Dict) -> int:
    if pad['mode'].startswith('NF'):
        try: return int(pad['mode'][2:])
        except: return 1
    return 0

def _is_valid_entry(pad: Dict) -> bool:
    dw0 = int(pad['dw0'], 16)
    dw1 = int(pad['dw1'], 16)
    return not (dw0 == 0 and dw1 == 0) and dw0 != 0xFFFFFFFF

def compose_gpio_state(all_tables: List[Dict], best_base_table: Dict,
                      reference_path: Optional[Path], ghidra_data: Optional[Dict] = None) -> List[Dict]:
    """
    Core Logic: Reconstructs the final GPIO state by layering tables.
    """
    logger.info("Starting GPIO State Composition...")

    parser = GPIOParser(platform='alderlake')
    parsed_tables = []

    # 1. Parse all candidate tables
    for i, t in enumerate(all_tables):
        pads = parser.parse_table(t)
        parsed_tables.append({
            'id': i, 'offset': t['offset'], 'count': t['entry_count'],
            'is_vgpio': t.get('is_vgpio', False), 'pads': pads
        })

    # 2. Parse Base Table
    base_pads = parser.parse_table(best_base_table)
    current_state = {p['name']: p for p in base_pads}
    logger.info(f"Initialized state from Base Table at 0x{best_base_table['offset']:x}")

    # 3. Load Reference (Oracle Mode)
    reference = {}
    if reference_path:
        reference = parse_reference_header(reference_path)
        logger.info(f"Loaded {len(reference)} reference pads for Oracle Composition")

    # 4. Apply Layers
    if reference:
        # ORACLE MODE: Use reference to cherry-pick correct values
        corrections = 0
        for t in parsed_tables:
            # Skip if it's the base table
            if t['offset'] == best_base_table['offset']: continue

            for p in t['pads']:
                name = p['name']
                if not _is_valid_entry(p): continue
                if name in reference:
                    # If this table has the CORRECT value
                    if _get_pad_mode(p) == reference[name]:
                        # And current state is WRONG/MISSING
                        if name not in current_state or _get_pad_mode(current_state[name]) != reference[name]:
                            current_state[name] = p
                            corrections += 1
        logger.info(f"Oracle Mode: Applied {corrections} corrections from layer tables")
    else:
        # BLIND MODE: Heuristic Layering
        # Group VGPIO tables and pick best
        vgpio_groups = {'VGPIO': [], 'VGPIO_USB': [], 'VGPIO_PCIE': []}
        for t in parsed_tables:
            if not t['is_vgpio'] or not t['pads']: continue
            first = t['pads'][0]['name']
            if 'VGPIO_USB' in first: vgpio_groups['VGPIO_USB'].append(t)
            elif 'VGPIO_PCIE' in first: vgpio_groups['VGPIO_PCIE'].append(t)
            elif 'VGPIO' in first: vgpio_groups['VGPIO'].append(t)

        for group, tables in vgpio_groups.items():
            # Pick table with most valid entries
            best_t = max(tables, key=lambda t: sum(1 for p in t['pads'] if _is_valid_entry(p)), default=None)
            if best_t:
                logger.info(f"Blind Mode: Layering {group} from Table at 0x{best_t['offset']:x}")
                for p in best_t['pads']:
                    if _is_valid_entry(p): current_state[p['name']] = p

    # 5. Gap Filling (VGPIO Synthesis)
    # Fills missing VGPIOs with NF1/DEEP default or Ghidra data
    synthesized = 0
    all_possible_vgpios = [f"VGPIO_USB_{i}" for i in range(12)] + [f"VGPIO_{i}" for i in range(39)]

    for name in all_possible_vgpios:
        if name not in current_state:
            # If we have reference, only synthesize if it exists there
            if reference and name not in reference: continue

            # Check Ghidra Data first for VGPIO_USB_0
            if name == 'VGPIO_USB_0' and ghidra_data:
                candidates = ghidra_data.get('vgpio_usb_0_candidates', [])
                if candidates:
                    cand = candidates[0]
                    val_int = int(cand['value'], 16)
                    # Basic sanity check on mode/reset bits
                    if val_int & 0xFFFFFFFF:
                        current_state[name] = {
                            'name': name, 'mode': 'NF1', 'reset': 'DEEP',
                            'direction': 'INPUT', 'termination': 'NONE',
                            'dw0': cand['value'], 'dw1': '0x00000000',
                            'is_synthesized': True, 'source': 'Ghidra'
                        }
                        logger.info(f"Ghidra: Found VGPIO_USB_0 candidate at {cand['address']} ({cand['value']})")
                        synthesized += 1
                        continue

            # Fallback: Synthesize NF1 Default
            current_state[name] = {
                'name': name, 'mode': 'NF1', 'reset': 'DEEP',
                'direction': 'INPUT', 'termination': 'NONE',
                'dw0': '0x44000400', 'dw1': '0x00000000',
                'is_synthesized': True
            }
            synthesized += 1

    if synthesized:
        logger.info(f"Gap Filling: Synthesized {synthesized} missing VGPIO pads")

    # 6. Sort and Return
    dummy_parser = GPIOParser() # Helper to access merge/sort logic
    wrapped_state = {'tables': [{'pads': list(current_state.values())}]}
    return dummy_parser.merge_tables(wrapped_state)

def main():
    parser = argparse.ArgumentParser(description='Extract GPIO configuration from vendor BIOS images')
    parser.add_argument('--platform', default='alderlake', choices=['alderlake'])
    parser.add_argument('--input', '-i', required=True)
    parser.add_argument('--output', '-o')
    parser.add_argument('--json', '-j')
    parser.add_argument('--work-dir', '-w')
    parser.add_argument('--min-entries', type=int, default=10)
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--calibrate-with', help='Path to reference gpio.h (for Composition/Calibration)')
    parser.add_argument('--compose', action='store_true', help='Enable Multi-Table Composition Mode (Recommended)')
    parser.add_argument('--analyze-ghidra', action='store_true')
    parser.add_argument('--no-ghidra', action='store_true')
    parser.add_argument('--ghidra-home')

    args = parser.parse_args()
    if args.verbose: logging.getLogger().setLevel(logging.DEBUG)

    # Ghidra Setup
    if not args.ghidra_home:
        found_home = find_ghidra_home()
        if found_home:
            args.ghidra_home = found_home
            if not args.no_ghidra and not args.analyze_ghidra:
                args.analyze_ghidra = True
                logger.info(f"Ghidra detected at {args.ghidra_home}. Analysis enabled.")

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input file not found: {args.input}")
        return 1

    logger.info(f"bios2gpio - Extracting GPIO from {input_path}")

    try:
        # Step 1: Extract
        extractor = UEFIExtractor(str(input_path), args.work_dir)
        bios_region = extractor.get_bios_region()
        modules = extractor.find_modules(GPIO_MODULE_PATTERNS)
        all_binaries = extractor.get_all_binary_files()

        # Step 2: Ghidra (Optional)
        ghidra_results = None
        if args.analyze_ghidra:
            target_module = None
            # Prioritize PchInit or GpioInit
            for m in modules:
                if 'PchInit' in m['name'] or 'GpioInit' in m['name']:
                    if m['path'].suffix.lower() in ['.efi', '.pe32']:
                        target_module = m['path']
                        break

            # Fallback to anything with 'Pch'
            if not target_module:
                for b in all_binaries:
                    if 'PchInit' in b.name:
                        target_module = b
                        break

            if target_module:
                logger.info(f"Running Ghidra analysis on {target_module.name}...")
                ghidra_results = run_ghidra_analysis(target_module, args.ghidra_home, "find_gpio_tables.py")
                if ghidra_results:
                    logger.info("Ghidra analysis completed successfully.")
            else:
                logger.warning("Could not find suitable module (PchInit) for Ghidra analysis.")

        # Step 3: Detect
        detector = GPIOTableDetector(platform=args.platform)
        files_to_scan = []
        if bios_region and bios_region.exists(): files_to_scan.append(bios_region)
        elif modules: files_to_scan.extend([m['path'] for m in modules])
        else: files_to_scan.extend(all_binaries[:50])
        files_to_scan = list(set(files_to_scan))

        logger.info(f"Scanning {len(files_to_scan)} files...")
        all_tables = []
        for file_path in files_to_scan:
            tables = detector.scan_file(file_path, min_entries=args.min_entries)
            all_tables.extend(tables)

        if not all_tables:
            logger.error("No GPIO tables found")
            return 1

        # Step 4: Select/Compose
        best_tables_filtered = detector.filter_best_tables(all_tables)
        if not best_tables_filtered:
            logger.error("Could not determine a valid base table.")
            return 1

        best_base_table = best_tables_filtered[0]

        final_pads = []

        if args.compose:
            ref_path = Path(args.calibrate_with) if args.calibrate_with else None
            final_pads = compose_gpio_state(all_tables, best_base_table, ref_path, ghidra_results)
        else:
            logger.info("Using Standard Mode (Best Detected Tables)")
            parser = GPIOParser(platform=args.platform)
            parsed_data = parser.parse_multiple_tables(best_tables_filtered)
            final_pads = parser.merge_tables(parsed_data)

        logger.info(f"Final Configuration contains {len(final_pads)} pads")

        # Step 5: Generate Output
        generator = GPIOGenerator(platform=args.platform)
        if args.json:
            export_data = {'source': str(input_path), 'pads': final_pads}
            parser = GPIOParser() # Helper
            parser.export_json(export_data, Path(args.json))
        if args.output:
            generator.generate_coreboot_header(final_pads, Path(args.output))

        return 0

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.verbose)
        return 1

if __name__ == '__main__':
    sys.exit(main())
