#!/usr/bin/env python3
import sys
import logging
import argparse
from pathlib import Path
import re

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gpio_detector import GPIOTableDetector
from gpio_parser import GPIOParser
from uefi_extractor import UEFIExtractor
from platforms import GPIO_MODULE_PATTERNS

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def parse_reference_header(filepath):
    """
    Parses the reference gpio.h file (from inteltool/intelp2m) to get the Ground Truth.
    Returns a dict: {pad_name: {mode: int, dw0: int, dw1: int, ...}}
    For now, we focus on 'mode' as the primary differentiator, but we can expand.
    """
    modes = {}
    # Regex for standard PAD_CFG_* macros
    regex = re.compile(r'^\s*PAD_CFG_([A-Z0-9_]+)\s*\(([^,]+),')
    
    # Regex for _PAD_CFG_STRUCT (VGPIOs)
    vgpio_regex = re.compile(r'^\s*_PAD_CFG_STRUCT\s*\(([^,]+),\s*(.+?),')

    try:
        with open(filepath, 'r') as f:
            for line in f:
                # Standard macros
                match = regex.match(line)
                if match:
                    mtype = match.group(1)
                    pad = match.group(2).strip()
                    mode = 0 # Default GPIO

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
                    modes[pad] = {'mode': mode, 'raw_line': line.strip()}
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
                    elif 'PAD_FUNC(GPIO)' in config_str:
                        mode = 0
                        
                    modes[pad] = {'mode': mode, 'raw_line': line.strip()}

    except Exception as e:
        logger.error(f"Failed to parse reference header: {e}")
        return None

    return modes

def analyze_deltas(bios_path, reference_path):
    logger.info(f"Analyzing deltas: BIOS={bios_path}, Ref={reference_path}")
    
    # 1. Get Reference State
    reference = parse_reference_header(reference_path)
    if not reference:
        logger.error("Could not parse reference file.")
        return
    logger.info(f"Loaded {len(reference)} reference pads.")

    # 2. Extract and Detect Tables
    extractor = UEFIExtractor(str(bios_path), "temp_work_dir")
    # We assume extraction works or we use raw file if it's a binary dump
    # For simplicity, let's try to scan the file directly first if it's a ROM
    # But GPIOTableDetector usually needs the specific module or BIOS region.
    # Let's use the logic from bios2gpio.py to get the best scan targets.
    
    files_to_scan = []
    if bios_path.suffix.lower() in ['.rom', '.bin']:
        if extractor.check_dependencies():
            bios_region = extractor.get_bios_region()
            if bios_region and bios_region.exists():
                files_to_scan.append(bios_region)
            else:
                # Fallback to scanning the whole file if extraction fails or region not found
                files_to_scan.append(bios_path)
        else:
             files_to_scan.append(bios_path)
    else:
        files_to_scan.append(bios_path)

    detector = GPIOTableDetector(platform='alderlake')
    all_tables = []
    
    for f in files_to_scan:
        logger.info(f"Scanning {f}...")
        tables = detector.scan_file(f, min_entries=10)
        all_tables.extend(tables)
        
    logger.info(f"Found {len(all_tables)} candidate tables.")
    
    # 3. Identify the "Base Table" (Highest Score)
    parser = GPIOParser(platform='alderlake')
    
    table_scores = []
    
    for i, table in enumerate(all_tables):
        pads = parser.parse_table(table)
        score = 0
        matches = []
        mismatches = []
        
        for pad in pads:
            name = pad['name']
            if name in reference:
                ref_mode = reference[name]['mode']
                
                # Extract mode from pad config
                pad_mode = 0
                if pad['mode'].startswith('NF'):
                    try: pad_mode = int(pad['mode'][2:])
                    except: pad_mode = 1
                
                if pad_mode == ref_mode:
                    score += 1
                    matches.append(name)
                else:
                    mismatches.append({'name': name, 'bios': pad_mode, 'ref': ref_mode})
        
        # Calculate coverage
        coverage = score / len(reference) if reference else 0
        
        table_data = {
            'id': i,
            'offset': table['offset'],
            'count': table['entry_count'],
            'score': score,
            'coverage': coverage,
            'matches': set(matches),
            'mismatches': mismatches,
            'pads': pads
        }
        table_scores.append(table_data)

    # Sort by score
    table_scores.sort(key=lambda x: x['score'], reverse=True)
    
    if not table_scores:
        logger.error("No tables found.")
        return

    base_table = table_scores[0]
    logger.info(f"\n=== Base Table Candidate ===")
    logger.info(f"Table #{base_table['id']} at 0x{base_table['offset']:x} (Size {base_table['count']})")
    logger.info(f"Score: {base_table['score']} / {len(reference)} ({base_table['coverage']*100:.1f}%)")
    
    # 4. Delta Analysis
    # Find pads that are WRONG in Base Table but CORRECT in other tables
    
    missing_pads = set(reference.keys()) - base_table['matches']
    logger.info(f"\n=== Delta Analysis ===")
    logger.info(f"Base table missed {len(missing_pads)} pads.")
    
    # Analyze which tables fix these misses
    fixers = {} # pad_name -> list of table_ids that have it correct
    
    for pad_name in missing_pads:
        fixers[pad_name] = []
        ref_mode = reference[pad_name]['mode']
        
        for t in table_scores:
            # Check if this table has the pad and it matches reference
            # We need to find the pad in the table's parsed data
            # Optimization: create a dict for each table? For now linear search is fine for 35 tables
            
            found = False
            for p in t['pads']:
                if p['name'] == pad_name:
                    p_mode = 0
                    if p['mode'].startswith('NF'):
                        try: p_mode = int(p['mode'][2:])
                        except: p_mode = 1
                    
                    if p_mode == ref_mode:
                        fixers[pad_name].append(t['id'])
                        found = True
                    break
    
    # Report findings
    solved_count = 0
    unsolved_count = 0
    
    logger.info("\n--- Pads fixed by other tables ---")
    for pad in sorted(missing_pads):
        if fixers[pad]:
            solved_count += 1
            tables_str = ", ".join([f"#{tid}" for tid in fixers[pad]])
            logger.info(f"[FIXED] {pad}: Correct in tables [{tables_str}]")
        else:
            unsolved_count += 1
            logger.info(f"[MISSING] {pad}: Not found correctly in ANY table")

    logger.info(f"\nSummary:")
    logger.info(f"Base Table Score: {base_table['score']}")
    logger.info(f"Recoverable via Deltas: {solved_count}")
    logger.info(f"Truly Missing (Code/Dynamic): {unsolved_count}")
    logger.info(f"Potential Composite Score: {base_table['score'] + solved_count} / {len(reference)}")

    # 5. Identify "Delta Tables"
    # Which tables provide the most fixes?
    table_utility = {}
    for pad, tids in fixers.items():
        for tid in tids:
            table_utility[tid] = table_utility.get(tid, 0) + 1
            
    sorted_utility = sorted(table_utility.items(), key=lambda x: x[1], reverse=True)
    
    logger.info("\n--- Most Useful Delta Tables ---")
    for tid, count in sorted_utility:
        t = next(t for t in table_scores if t['id'] == tid)
        logger.info(f"Table #{tid} (Offset 0x{t['offset']:x}): Contributes {count} fixes")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--bios', required=True)
    parser.add_argument('--reference', required=True)
    args = parser.parse_args()
    
    analyze_deltas(Path(args.bios), Path(args.reference))
