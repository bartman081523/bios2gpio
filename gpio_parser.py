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

        for idx, entry in enumerate(table['entries']):
            config = entry['config']

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
        Merge multiple tables. For this single-table-winner logic, just return the winner.
        """
        if not parsed_data['tables']:
            return []

        # The detector now filters to only 1 winner table.
        # Just take its pads.
        pads = parsed_data['tables'][0]['pads']

        # Sort by name for clean output
        merged_list = sorted(pads, key=lambda p: p['name'])

        logger.info(f"Merged to {len(merged_list)} unique pads")
        return merged_list
