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
        """
        Initialize GPIO table detector.
        
        Args:
            platform: Platform name (currently only 'alderlake' supported)
        """
        self.platform = platform
        
        # Platform-specific configuration
        if platform == 'alderlake':
            self.gpio_groups = GPIO_GROUPS
            self.pad_config_class = AlderLakeGpioPadConfig
            # Typical pad config sizes:
            # 8 bytes: DW0+DW1 (standard GPIOs)
            # 12 bytes: DW0+DW1+DW2 (some VGPIOs)
            # 16 bytes: DW0+DW1+DW2+DW3 (full config)
            # 20 bytes: Extended format (rare)
            self.expected_entry_sizes = [8, 12, 16, 20]
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
                    # Check if this is a VGPIO table
                    is_vgpio = self._is_vgpio_table(entries)
                    
                    table_info = {
                        'offset': offset,
                        'entry_size': entry_size,
                        'entry_count': len(entries),
                        'total_size': len(entries) * entry_size,
                        'entries': entries,
                        'confidence': 100.0,
                        'is_signature_match': True,
                        'is_vgpio': is_vgpio
                    }
                    tables.append(table_info)

        return tables

    def scan_for_tables(self, data: bytes, min_entries: int = 10) -> List[Dict]:
        """
        Scan for GPIO tables using multiple strategies.
        
        Returns both signature-matched standard GPIO tables and VGPIO tables.
        """
        all_tables = []
        
        # Strategy 1: Signature matching for standard GPIOs (8-byte stride)
        for entry_size in [8, 12, 16]:
            sig_tables = self.scan_for_signature(data, entry_size)
            if sig_tables:
                logger.info(f"Found {len(sig_tables)} tables via signature matching (stride {entry_size})")
                all_tables.extend(sig_tables)
        
        # Check if we found VGPIOs in signature matching
        vgpio_tables_found = [t for t in all_tables if t.get('is_vgpio')]
        standard_tables_found = [t for t in all_tables if not t.get('is_vgpio') and t['entry_count'] > 200]
        
        # If we already found standard GPIOs and some VGPIOs via signature matching,
        # skip the expensive pattern scan to save time
        if standard_tables_found and vgpio_tables_found:
            logger.info(f"Signature matching found {len(standard_tables_found)} standard + {len(vgpio_tables_found)} VGPIO tables, skipping pattern scan")
            return all_tables
        
        # Strategy 2: Pattern scanning for VGPIOs and other tables
        # Only scan if we didn't find VGPIOs yet, or if we need more coverage
        logger.info("Running pattern scan to find additional tables...")
        for entry_size in self.expected_entry_sizes:
            detected = self._scan_fixed_size_entries(data, entry_size, min_entries)
            # Filter out duplicates (tables at same offset)
            for table in detected:
                is_duplicate = any(
                    t['offset'] == table['offset'] and t['entry_size'] == table['entry_size']
                    for t in all_tables
                )
                if not is_duplicate:
                    all_tables.append(table)
        
        return all_tables

    def _scan_fixed_size_entries(self, data: bytes, entry_size: int, min_entries: int) -> List[Dict]:
        """Scan for fixed-size GPIO table entries"""
        tables = []
        data_len = len(data)
        offset = 0
        
        # For VGPIO detection, we're specifically looking for small tables
        # Skip large scans if we're looking for VGPIOs
        max_scan_entries = 350
        
        while offset < data_len - (entry_size * min_entries):
            valid_count = 0
            current_offset = offset
            entries = []
            
            while current_offset + entry_size <= data_len and valid_count < max_scan_entries:
                try:
                    if entry_size >= 8:
                        pad_config = self.pad_config_class(data[current_offset:current_offset + entry_size])
                        if self._is_valid_pad_config(pad_config):
                            valid_count += 1
                            entries.append({'offset': current_offset, 'config': pad_config})
                            current_offset += entry_size
                        else:
                            break
                    else:
                        break
                except:
                    break
            
            if valid_count >= min_entries and valid_count < max_scan_entries:
                # Check if this is a VGPIO table
                is_vgpio = self._is_vgpio_table(entries)
                
                # Only keep VGPIO tables or large standard tables
                # Skip medium-sized non-VGPIO tables to reduce noise
                if is_vgpio or valid_count > 100:
                    table_info = {
                        'offset': offset,
                        'entry_size': entry_size,
                        'entry_count': valid_count,
                        'total_size': valid_count * entry_size,
                        'entries': entries,
                        'confidence': self._calculate_confidence(entries),
                        'is_vgpio': is_vgpio
                    }
                    tables.append(table_info)
                
                offset = current_offset
            else:
                offset += 4
        
        return tables

    def _is_valid_pad_config(self, config: AlderLakeGpioPadConfig) -> bool:
        """Check if a pad config looks valid"""
        return config.validate()
    
    def _is_vgpio_table(self, entries: List[Dict]) -> bool:
        """
        Detect if a table likely contains VGPIOs based on characteristics.
        
        VGPIOs typically have:
        - NAFVWE bit set (DW0[27])
        - DEEP reset (DW0[31:30] = 0b01)
        - Mode GPIO (0) or NF1 (1)
        - Specific table sizes: 38 (VGPIO), 12 (VGPIO_USB), 80 (VGPIO_PCIE)
        """
        if not entries:
            return False
        
        entry_count = len(entries)
        
        # Check for known VGPIO table sizes
        vgpio_sizes = [12, 38, 80]  # VGPIO_USB, VGPIO, VGPIO_PCIE
        size_match = any(abs(entry_count - size) <= 2 for size in vgpio_sizes)
        
        # Check characteristics of first few entries
        nafvwe_count = 0
        deep_reset_count = 0
        
        for entry in entries[:min(10, len(entries))]:
            config = entry['config']
            
            # Check for NAFVWE bit (DW0[27])
            if config.dw0 & (1 << 27):
                nafvwe_count += 1
            
            # Check for DEEP reset (0b01 in DW0[31:30])
            reset_val = (config.dw0 >> 30) & 0x3
            if reset_val == 0b01:
                deep_reset_count += 1
        
        # If most entries have NAFVWE or DEEP reset, likely VGPIO
        sample_size = min(10, len(entries))
        nafvwe_ratio = nafvwe_count / sample_size if sample_size > 0 else 0
        deep_ratio = deep_reset_count / sample_size if sample_size > 0 else 0
        
        is_vgpio = (size_match and (nafvwe_ratio > 0.5 or deep_ratio > 0.7))
        
        if is_vgpio:
            logger.debug(f"VGPIO table detected: {entry_count} entries, NAFVWE={nafvwe_ratio:.1%}, DEEP={deep_ratio:.1%}")
        
        return is_vgpio

    def _calculate_confidence(self, entries: List[Dict]) -> float:
        if not entries or len(entries) > 350: return 0.0
        return min(len(entries)/100.0, 1.0)

    def filter_best_tables(self, tables: List[Dict], max_tables: int = 3) -> List[Dict]:
        """
        Filter and return the best GPIO tables.
        
        Returns both the best standard GPIO table and any VGPIO tables found.
        """
        # Separate signature matches, VGPIOs, and regular tables
        sig_matches = [t for t in tables if t.get('is_signature_match')]
        vgpio_tables = [t for t in tables if t.get('is_vgpio')]
        regular_tables = [t for t in tables if not t.get('is_signature_match') and not t.get('is_vgpio')]
        
        result = []
        
        # Priority 1: Signature match (best standard GPIO table)
        if sig_matches:
            # Z690 usually has ~252 pads
            # Sort by deviation from 252 and pick the best one
            sig_matches.sort(key=lambda x: abs(x['entry_count'] - 252))
            best_match = sig_matches[0]
            logger.info(f"Winner: Table with {best_match['entry_count']} entries (Offset {best_match['offset']:x})")
            result.append(best_match)
        elif regular_tables:
            # No signature match, use highest confidence regular table
            regular_tables.sort(key=lambda t: t['confidence'], reverse=True)
            result.append(regular_tables[0])
        
        # Priority 2: Add VGPIO tables
        if vgpio_tables:
            # Sort VGPIOs by size to get them in order (VGPIO_USB=12, VGPIO=38, VGPIO_PCIE=80)
            vgpio_tables.sort(key=lambda t: t['entry_count'])
            logger.info(f"Found {len(vgpio_tables)} VGPIO table(s):")
            for vt in vgpio_tables:
                logger.info(f"  VGPIO table: {vt['entry_count']} entries at offset 0x{vt['offset']:x}, stride={vt['entry_size']}")
                result.append(vt)
        
        return result

    def scan_file(self, file_path: Path, min_entries: int = 10) -> List[Dict]:
        try:
            with open(file_path, 'rb') as f: data = f.read()
            tables = self.scan_for_tables(data, min_entries)
            for table in tables:
                table['file'] = str(file_path)
                table['file_size'] = len(data)
            return tables
        except: return []
