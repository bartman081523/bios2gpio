#!/usr/bin/env python3
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class GPIOComposer:
    def __init__(self, platform: str = 'alderlake'):
        self.platform = platform

    def parse_reference_header(self, filepath: Path) -> Optional[Dict[str, int]]:
        """Parses the reference gpio.h file."""
        modes = {}
        # Regex for standard macros: PAD_CFG_NF(GPP_A0, ..., NF1)
        regex = re.compile(r'^\s*PAD_CFG_([A-Z0-9_]+)\s*\(([^,]+),')
        # Regex for VGPIO macros: _PAD_CFG_STRUCT(VGPIO_0, PAD_FUNC(NF1)...)
        vgpio_regex = re.compile(r'^\s*_PAD_CFG_STRUCT\s*\(([^,]+),\s*(.+?),')

        try:
            with open(filepath, 'r') as f:
                for line in f:
                    match = regex.match(line)
                    if match:
                        pad = match.group(2).strip()
                        # Simple mode extraction
                        mode = 0
                        if 'NF' in match.group(1):
                            parts = line.split(',')
                            if len(parts) >= 4 and 'NF' in parts[3]:
                                try: 
                                    mode_str = parts[3].strip().replace('NF', '').replace(')', '')
                                    mode = int(mode_str)
                                except: 
                                    mode = 1
                            else: 
                                mode = 1
                        modes[pad] = mode
                        continue

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
            logger.error(f"Failed to parse reference: {e}")
            return None
        return modes

    def _get_mode(self, pad: Dict[str, Any]) -> int:
        """Extract integer mode from pad configuration."""
        if isinstance(pad.get('mode'), str) and pad['mode'].startswith('NF'):
            try: 
                return int(pad['mode'][2:])
            except: 
                return 1
        return 0

    def _calculate_score(self, state: Dict[str, Any], reference: Dict[str, int]) -> int:
        """Calculate how many pads in state match the reference mode."""
        score = 0
        for name, mode in reference.items():
            if name in state:
                if self._get_mode(state[name]) == mode:
                    score += 1
        return score

    def compose_oracle(self, parsed_tables: List[Dict[str, Any]], reference_path: Path) -> Dict[str, Any]:
        """
        Compose GPIO state using a reference file (Oracle Composition).
        Reconstructs the state by selecting the best values from all available tables.
        """
        reference = self.parse_reference_header(reference_path)
        if not reference:
            logger.error("Reference parsing failed, aborting composition.")
            return {}

        logger.info(f"Loaded {len(reference)} reference pads for Oracle Composition")

        # 1. Identify Base Table
        # Pick the table that matches the reference best
        base_table = None
        best_score = -1
        
        for t in parsed_tables:
            score = 0
            for p in t['pads']:
                if p['name'] in reference and self._get_mode(p) == reference[p['name']]:
                    score += 1
            if score > best_score:
                best_score = score
                base_table = t
        
        if not base_table:
            logger.warning("No suitable base table found.")
            return {}

        logger.info(f"Selected Base Table #{base_table['id']} (Score: {best_score})")

        # 2. Composition Loop
        # Start with Base State
        current_state = {p['name']: p for p in base_table['pads']}
        applied_tables = [base_table['id']]

        logger.info("Starting Oracle Composition...")

        # Iterate through all tables and apply ONLY the pads that match the reference
        # This effectively "cherry-picks" the correct configurations
        for t in parsed_tables:
            if t['id'] in applied_tables: continue

            useful = False
            for p in t['pads']:
                # Skip empty entries
                if p.get('dw0') == '0x00000000' and p.get('dw1') == '0x00000000': continue

                name = p['name']
                if name in reference:
                    # Check if this pad matches the reference
                    if self._get_mode(p) == reference[name]:
                        # Check if it improves the current state
                        current_match = (name in current_state and self._get_mode(current_state[name]) == reference[name])
                        if not current_match:
                            current_state[name] = p
                            useful = True

            if useful:
                applied_tables.append(t['id'])

        final_score = self._calculate_score(current_state, reference)
        logger.info(f"Final Composite Score: {final_score}/{len(reference)}")
        
        return current_state

    def compose_blind(self, parsed_tables: List[Dict[str, Any]], ghidra_metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Compose GPIO state without a reference (Blind Composition).
        Uses heuristics or Ghidra metadata to determine table layering.
        """
        # TODO: Implement blind composition logic
        logger.warning("Blind composition not yet implemented.")
        return {}
