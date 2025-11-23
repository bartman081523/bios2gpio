#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
GPIO parser module.

Parses detected GPIO tables and converts to structured data.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from platforms.alderlake import (
    AlderLakeGpioPadConfig,
    GPIO_GROUPS,
    get_pad_name,
    resolve_global_pad_name,
    PadMode,
)

logger = logging.getLogger(__name__)


class GPIOParser:
    """Parses GPIO configuration tables into structured data"""

    def __init__(self, platform='alderlake'):
        """
        Initialize GPIO parser.
        """
        self.platform = platform

        if platform == 'alderlake':
            self.gpio_groups = GPIO_GROUPS
            self.pad_config_class = AlderLakeGpioPadConfig
        else:
            raise ValueError(f"Unsupported platform: {platform}")

    def parse_table(self, table: Dict, community: int = 0) -> List[Dict]:
        """
        Parse a detected GPIO table into structured pad configurations.
        """
        parsed_pads = []
        is_vgpio = table.get('is_vgpio', False)
        entry_count = table['entry_count']
        
        # Determine VGPIO group based on size
        vgpio_group = None
        if is_vgpio:
            if 10 <= entry_count <= 14:
                vgpio_group = 'VGPIO_0'  # VGPIO_USB
            elif 35 <= entry_count <= 42:
                vgpio_group = 'VGPIO'
            elif 75 <= entry_count <= 85:
                vgpio_group = 'VGPIO_PCIE'
            logger.info(f"Detected VGPIO table: {vgpio_group} ({entry_count} entries)")

        for idx, entry in enumerate(table['entries']):
            config = entry['config']

            # Handle VGPIO tables
            if is_vgpio and vgpio_group:
                group_name = vgpio_group
                local_idx = idx
                pad_name = get_pad_name(group_name, local_idx)
            else:
                # Use global resolution based on physical table order
                group_name, local_idx = resolve_global_pad_name(idx)
                
                if group_name:
                    pad_name = get_pad_name(group_name, local_idx)
                else:
                    pad_name = f'UNKNOWN_{idx}'

            # Skip unknown pads (padding at end of table)
            if 'UNKNOWN' in pad_name:
                continue

            pad_info = {
                'index': idx,
                'name': pad_name,
                'group': group_name,
                'local_index': local_idx,
                'offset': entry['offset'],
                'is_vgpio': is_vgpio,
                **config.to_dict()
            }
            parsed_pads.append(pad_info)

        logger.info(f"Parsed {len(parsed_pads)} pads from table")
        return parsed_pads

    def _guess_pad_identity(self, index: int, community: int,
                           config: AlderLakeGpioPadConfig) -> tuple:
        """Deprecated local guesser."""
        return (None, None)

    def parse_multiple_tables(self, tables: List[Dict],
                             community_hints: Optional[List[int]] = None) -> Dict:
        """
        Parse multiple GPIO tables.
        """
        results = {
            'platform': self.platform,
            'tables': []
        }

        for idx, table in enumerate(tables):
            # Ignore hints, use global parser
            parsed_pads = self.parse_table(table)

            table_result = {
                'table_index': idx,
                'offset': table['offset'],
                'entry_count': table['entry_count'],
                'confidence': table['confidence'],
                'file': table.get('file', 'unknown'),
                'is_vgpio': table.get('is_vgpio', False),
                'pads': parsed_pads,
            }

            results['tables'].append(table_result)

        return results

    def export_json(self, parsed_data: Dict, output_path: Path):
        """Export parsed data to JSON file."""
        with open(output_path, 'w') as f:
            json.dump(parsed_data, f, indent=2)
        logger.info(f"Exported GPIO data to {output_path}")

    def merge_tables(self, parsed_data: Dict) -> List[Dict]:
        """
        Merge multiple tables (standard + VGPIOs).
        
        Returns all pads from all tables, sorted by group and name.
        """
        if not parsed_data['tables']:
            return []

        all_pads = []
        pad_names_seen = set()
        
        # Collect pads from all tables
        for table in parsed_data['tables']:
            for pad in table['pads']:
                # Avoid duplicates (same pad name)
                if pad['name'] not in pad_names_seen:
                    all_pads.append(pad)
                    pad_names_seen.add(pad['name'])
                else:
                    logger.debug(f"Skipping duplicate pad: {pad['name']}")

        # Sort by group order, then by name
        # Define group priority for sorting
        group_order = {
            'GPP_I': 0, 'GPP_R': 1, 'GPP_J': 2,
            'GPP_B': 3, 'GPP_G': 4, 'GPP_H': 5,
            'GPD': 6,
            'GPP_A': 7, 'GPP_C': 8,
            'GPP_S': 9, 'GPP_E': 10, 'GPP_K': 11, 'GPP_F': 12,
            'GPP_D': 13,
            'VGPIO': 14, 'VGPIO_0': 15, 'VGPIO_PCIE': 16
        }
        
        def sort_key(pad):
            group = pad.get('group', 'UNKNOWN')
            priority = group_order.get(group, 99)
            return (priority, pad['name'])
        
        merged_list = sorted(all_pads, key=sort_key)

        logger.info(f"Merged to {len(merged_list)} unique pads from {len(parsed_data['tables'])} table(s)")
        return merged_list
