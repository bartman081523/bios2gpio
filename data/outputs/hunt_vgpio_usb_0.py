#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
Hunt for VGPIO_USB_0 in the BIOS.

This script scans all detected tables and looks for entries that could be VGPIO_USB_0
based on the expected configuration: NF1 mode, DEEP reset, NAFVWE enabled.
"""

import logging
from gpio_detector import GPIOTableDetector
from gpio_parser import GPIOParser
from uefi_extractor import UEFIExtractor
from platforms.alderlake import AlderLakeGpioPadConfig

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def main():
    bios_path = 'E7D25IMS.1M0'
    
    # Expected configuration for VGPIO_USB_0
    # PAD_FUNC(NF1) | PAD_RESET(DEEP) | PAD_CFG0_NAFVWE_ENABLE
    # Mode: NF1 (1), Reset: DEEP (1), NAFVWE: bit 7
    expected_mode = 1
    expected_reset = 1
    
    logger.info("Detecting GPIO tables...")
    detector = GPIOTableDetector('alderlake')
    
    with open(bios_path, 'rb') as f:
        bios_data = f.read()
    
    all_tables = detector.scan_for_tables(bios_data)
    
    logger.info(f"Found {len(all_tables)} tables")
    
    parser = GPIOParser()
    
    # Look for VGPIO_0 tables (10-14 entries)
    vgpio_usb_tables = []
    for table in all_tables:
        if table.get('is_vgpio', False) and 10 <= table['entry_count'] <= 14:
            vgpio_usb_tables.append(table)
    
    logger.info(f"Found {len(vgpio_usb_tables)} VGPIO_0 (USB) tables")
    
    # Parse each and look for the first entry
    for idx, table in enumerate(vgpio_usb_tables):
        parsed = parser.parse_table(table)
        
        if not parsed:
            continue
        
        # Check the first entry (should be VGPIO_USB_0)
        first_pad = parsed[0]
        
        logger.info(f"\nTable #{idx} at 0x{table['offset']:x} ({table['entry_count']} entries)")
        logger.info(f"  First pad: {first_pad['name']}")
        logger.info(f"  DW0: {first_pad['dw0']}, DW1: {first_pad['dw1']}")
        logger.info(f"  Mode: {first_pad['mode']}, Reset: {first_pad['reset']}")
        
        # Check if it matches expected config
        if first_pad['mode'] == 'NF1' and first_pad['reset'] == 'DEEP':
            logger.info(f"  *** CANDIDATE for VGPIO_USB_0! ***")
            
            # Print all pads in this table
            logger.info(f"  All pads in this table:")
            for p in parsed:
                logger.info(f"    {p['name']}: Mode={p['mode']}, Reset={p['reset']}, DW0={p['dw0']}")

if __name__ == '__main__':
    main()
