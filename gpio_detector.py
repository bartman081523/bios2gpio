#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
GPIO table detection module.
"""

import struct
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from platforms.alderlake import GPIO_GROUPS, AlderLakeGpioPadConfig, ALDERLAKE_GPIO_SIGNATURE

logger = logging.getLogger(__name__)


class GPIOTableDetector:
    def __init__(self, platform='alderlake'):
        self.platform = platform
        if platform == 'alderlake':
            self.gpio_groups = GPIO_GROUPS
            self.pad_config_class = AlderLakeGpioPadConfig
            self.expected_entry_sizes = [8, 12, 16]
            self.signature = ALDERLAKE_GPIO_SIGNATURE
        else:
            raise ValueError(f"Unsupported platform: {platform}")

    def scan_for_signature(self, data: bytes, entry_size: int) -> List[Dict]:
        tables = []
        if not self.signature: return []

        data_len = len(data)
        sig_len = len(self.signature)
        stride = entry_size

        for offset in range(0, data_len - (stride * sig_len), 4):
            match = True
            for i, expected in enumerate(self.signature):
                try:
                    p_off = offset + i * stride
                    dw0 = struct.unpack('<I', data[p_off:p_off+4])[0]
                    mode = (dw0 >> 10) & 0xF
                    if mode != expected['mode']:
                        match = False
                        break
                except:
                    match = False
                    break

            if match:
                logger.info(f"SIGNATURE MATCH at offset 0x{offset:x} (entry size {entry_size})")
                current_offset = offset
                entries = []
                invalid_streak = 0

                # Cap at 320. Z690 is ~250-280.
                while current_offset + entry_size <= data_len and len(entries) < 320:
                    entry_data = data[current_offset:current_offset + entry_size]
                    pad_config = self.pad_config_class(entry_data)

                    if self._is_valid_pad_config(pad_config):
                        entries.append({
                            'offset': current_offset,
                            'config': pad_config
                        })
                        current_offset += entry_size
                        invalid_streak = 0
                    else:
                        invalid_streak += 1
                        if invalid_streak > 2: break
                        current_offset += entry_size

                logger.info(f"  -> Extracted {len(entries)} entries")

                # Only keep tables that look like full GPIO configs (>100 pads)
                # or reasonably large fragments (>20)
                if len(entries) >= 20:
                    table_info = {
                        'offset': offset,
                        'entry_size': entry_size,
                        'entry_count': len(entries),
                        'total_size': len(entries) * entry_size,
                        'entries': entries,
                        'confidence': 100.0,
                        'is_signature_match': True
                    }
                    tables.append(table_info)

        return tables

    def scan_for_tables(self, data: bytes, min_entries: int = 10) -> List[Dict]:
        for entry_size in [8, 12, 16]:
            sig_tables = self.scan_for_signature(data, entry_size)
            if sig_tables:
                logger.info(f"Found {len(sig_tables)} tables via signature matching")
                return sig_tables

        tables = []
        for entry_size in self.expected_entry_sizes:
            detected = self._scan_fixed_size_entries(data, entry_size, min_entries)
            tables.extend(detected)
        return tables

    def _scan_fixed_size_entries(self, data: bytes, entry_size: int, min_entries: int) -> List[Dict]:
        tables = []
        data_len = len(data)
        offset = 0
        while offset < data_len - (entry_size * min_entries):
            valid_count = 0
            current_offset = offset
            entries = []
            while current_offset + entry_size <= data_len:
                try:
                    if entry_size >= 8:
                        pad_config = self.pad_config_class(data[current_offset:current_offset + entry_size])
                        if self._is_valid_pad_config(pad_config):
                            valid_count += 1
                            entries.append({'offset': current_offset, 'config': pad_config})
                            current_offset += entry_size
                        else: break
                    else: break
                except: break
            if valid_count >= min_entries and valid_count < 350:
                tables.append({
                    'offset': offset, 'entry_size': entry_size, 'entry_count': valid_count,
                    'total_size': valid_count*entry_size, 'entries': entries,
                    'confidence': self._calculate_confidence(entries)
                })
                offset = current_offset
            else: offset += 4
        return tables

    def _is_valid_pad_config(self, config: AlderLakeGpioPadConfig) -> bool:
        if config.dw0 == 0 and config.dw1 == 0: return False
        if config.dw0 == 0xFFFFFFFF or config.dw1 == 0xFFFFFFFF: return False
        try:
            if config.get_pad_mode().value > 7: return False
        except: return False
        return True

    def _calculate_confidence(self, entries: List[Dict]) -> float:
        if not entries or len(entries) > 350: return 0.0
        return min(len(entries)/100.0, 1.0)

    def filter_best_tables(self, tables: List[Dict], max_tables: int = 3) -> List[Dict]:
        sig_matches = [t for t in tables if t.get('is_signature_match')]
        if sig_matches:
            # CRITICAL FIX:
            # Z690 usually has ~252 pads.
            # Sort by deviation from 252.
            # Pick ONLY the single best one to avoid merging garbage.
            sig_matches.sort(key=lambda x: abs(x['entry_count'] - 252))

            best_match = sig_matches[0]
            logger.info(f"Winner: Table with {best_match['entry_count']} entries (Offset {best_match['offset']:x})")

            return [best_match] # Return list with single item

        return sorted(tables, key=lambda t: t['confidence'], reverse=True)[:max_tables]

    def scan_file(self, file_path: Path, min_entries: int = 10) -> List[Dict]:
        try:
            with open(file_path, 'rb') as f: data = f.read()
            tables = self.scan_for_tables(data, min_entries)
            for table in tables:
                table['file'] = str(file_path)
                table['file_size'] = len(data)
            return tables
        except: return []
