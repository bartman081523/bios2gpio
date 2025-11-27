#!/usr/bin/env python3
import sys
import logging
import argparse
from pathlib import Path
import json

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gpio_detector import GPIOTableDetector
from gpio_parser import GPIOParser
from uefi_extractor import UEFIExtractor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def parse_reference_header(filepath):
    """Parses the reference gpio.h file."""
    import re
    modes = {}
    regex = re.compile(r'^\s*PAD_CFG_([A-Z0-9_]+)\s*\(([^,]+),')
    vgpio_regex = re.compile(r'^\s*_PAD_CFG_STRUCT\s*\(([^,]+),\s*(.+?),')

    try:
        with open(filepath, 'r') as f:
            for line in f:
                match = regex.match(line)
                if match:
                    pad = match.group(2).strip()
                    # Simple mode extraction for now
                    mode = 0
                    if 'NF' in match.group(1):
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
        return None
    return modes

def compose_state(bios_path, reference_path=None):
    logger.info(f"Composing GPIO State from {bios_path}")

    # 1. Detect Tables
    detector = GPIOTableDetector(platform='alderlake')
    tables = detector.scan_file(Path(bios_path), min_entries=10)
    logger.info(f"Found {len(tables)} tables")

    parser = GPIOParser(platform='alderlake')
    parsed_tables = []
    for i, t in enumerate(tables):
        pads = parser.parse_table(t)
        parsed_tables.append({'id': i, 'offset': t['offset'], 'pads': pads, 'count': len(pads)})

    # 2. Load Reference (if available, for training/verification)
    reference = None
    if reference_path:
        reference = parse_reference_header(reference_path)
        logger.info(f"Loaded {len(reference)} reference pads")

    # 3. Identify Base Table (Largest/Best Score)
    # Heuristic: Largest table is usually the base
    # Refined Heuristic: If reference exists, pick highest score. If not, pick largest.

    base_table = None
    if reference:
        best_score = -1
        for t in parsed_tables:
            score = 0
            for p in t['pads']:
                if p['name'] in reference and _get_mode(p) == reference[p['name']]:
                    score += 1
            if score > best_score:
                best_score = score
                base_table = t
        logger.info(f"Selected Base Table #{base_table['id']} (Score: {best_score})")
    else:
        # Sort by size
        parsed_tables.sort(key=lambda x: x['count'], reverse=True)
        base_table = parsed_tables[0]
        logger.info(f"Selected Base Table #{base_table['id']} (Size: {base_table['count']})")

    # 4. Composition Loop
    # Start with Base State
    current_state = {p['name']: p for p in base_table['pads']}

    # If we have reference, we can greedily apply tables that improve the score
    applied_tables = [base_table['id']]
    # Oracle Composition (Reference-Guided)
    # Assumption: The BIOS applies tables with masking or specific logic we can't fully emulate yet.
    # We use the reference to pick the correct values from the available tables.

    logger.info("Starting Oracle Composition...")

    # Iterate through all tables and apply ONLY the pads that match the reference
    for t in parsed_tables:
        if t['id'] in applied_tables: continue

        useful = False
        for p in t['pads']:
            # Skip empty
            if p['dw0'] == '0x00000000' and p['dw1'] == '0x00000000': continue

            name = p['name']
            if name in reference:
                # Check if this pad matches the reference
                if _get_mode(p) == reference[name]:
                    # Check if it improves the current state
                    current_match = (name in current_state and _get_mode(current_state[name]) == reference[name])
                    if not current_match:
                        current_state[name] = p
                        useful = True

        if useful:
            # We don't mark the whole table as applied in the traditional sense,
            # but we record it contributed.
            applied_tables.append(t['id'])

    final_score = _calculate_score(current_state, reference)
    logger.info(f"Final Composite Score: {final_score}/{len(reference)}")

    if 'VGPIO_USB_1' in current_state:
        usb1 = current_state['VGPIO_USB_1']
        logger.info(f"VGPIO_USB_1 found in Table #{usb1.get('table_index', 'Unknown')}: DW0={usb1['dw0']}, DW1={usb1['dw1']}")
    else:
        logger.info("VGPIO_USB_1 NOT found in current state.")

    if reference:
        # Conflict Analysis
        logger.info("\n=== Conflict Analysis ===")
        missing_pads = []
        for name, mode in reference.items():
            if name in current_state:
                if _get_mode(current_state[name]) != mode:
                    missing_pads.append(name)
            else:
                missing_pads.append(name)

        logger.info(f"Remaining Missing Pads: {len(missing_pads)}")

        # Check if these pads exist in any unused table
        for pad in missing_pads:
            potential_tables = []
            for t in parsed_tables:
                # Check if this table has the correct value for this pad
                for p in t['pads']:
                    if p['name'] == pad and _get_mode(p) == reference[pad]:
                        # Calculate what would happen if we applied this table
                        # How many existing correct pads would it break?
                        broken_count = 0
                        fixed_count = 0 # Should be at least 1 (this pad)

                        for tp in t['pads']:
                            if tp['name'] in reference:
                                current_val_correct = (tp['name'] in current_state and _get_mode(current_state[tp['name']]) == reference[tp['name']])
                                new_val_correct = (_get_mode(tp) == reference[tp['name']])

                                if current_val_correct and not new_val_correct:
                                    broken_count += 1
                                if not current_val_correct and new_val_correct:
                                    fixed_count += 1

                        potential_tables.append({'id': t['id'], 'broken': broken_count, 'fixed': fixed_count})

            # Sort by least broken
            potential_tables.sort(key=lambda x: x['broken'])
            if potential_tables:
                best = potential_tables[0]
                logger.info(f"Pad {pad} could be fixed by Table #{best['id']} (Fixes {best['fixed']}, Breaks {best['broken']})")

                # Detailed debug for the first few interesting cases
                if best['broken'] > 0 and best['broken'] < 10:
                    # Re-calculate to find names
                    t = next(t for t in parsed_tables if t['id'] == best['id'])
                    broken_names = []
                    for tp in t['pads']:
                        if tp['name'] in reference:
                            current_val_correct = (tp['name'] in current_state and _get_mode(current_state[tp['name']]) == reference[tp['name']])
                            new_val_correct = (_get_mode(tp) == reference[tp['name']])
                            if current_val_correct and not new_val_correct:
                                broken_names.append(tp['name'])
                    logger.info(f"    -> Breaks: {', '.join(broken_names)}")
            else:
                logger.info(f"Pad {pad} is NOT found correctly in any remaining table (or was never found).")


    else:
        logger.info("No reference provided. Cannot perform heuristic composition without ground truth yet.")
        # TODO: Implement "Blind Composition" based on heuristics (e.g. "VGPIO tables override Base")

    return current_state

def _get_mode(pad):
    if pad['mode'].startswith('NF'):
        try: return int(pad['mode'][2:])
        except: return 1
    return 0

def _calculate_score(state, reference):
    score = 0
    for name, mode in reference.items():
        if name in state:
            if _get_mode(state[name]) == mode:
                score += 1
    return score

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--bios', required=True)
    parser.add_argument('--reference')
    args = parser.parse_args()

    compose_state(args.bios, args.reference)
