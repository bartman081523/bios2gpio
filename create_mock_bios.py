#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
Create a mock BIOS image with embedded GPIO table for testing.
"""

import struct
import sys
from pathlib import Path

def create_mock_gpio_table():
    """Create a mock GPIO configuration table"""
    entries = []
    
    # Create some realistic-looking GPIO configurations
    # Each entry is 8 bytes: DW0 (4 bytes) + DW1 (4 bytes)
    
    # GPP_B0 - GPIO input, PLTRST, no termination
    dw0 = 0x00000200  # RX enabled, TX disabled, mode=GPIO
    dw1 = 0x80000000  # PLTRST reset
    entries.append(struct.pack('<II', dw0, dw1))
    
    # GPP_B1 - GPIO output = 1, PLTRST
    dw0 = 0x00000101  # TX enabled, RX disabled, output=1, mode=GPIO
    dw1 = 0x80000000  # PLTRST reset
    entries.append(struct.pack('<II', dw0, dw1))
    
    # GPP_B2 - Native function NF1, PLTRST
    dw0 = 0x00000400  # Mode = NF1 (1 << 10)
    dw1 = 0x80000000  # PLTRST reset
    entries.append(struct.pack('<II', dw0, dw1))
    
    # GPP_B3 - GPIO input with pull-up 20K
    dw0 = 0x00000200  # RX enabled, TX disabled
    dw1 = 0x80001800  # PLTRST, termination = UP_20K (6 << 10)
    entries.append(struct.pack('<II', dw0, dw1))
    
    # Add more entries to meet minimum threshold (>100 for standard tables)
    for i in range(4, 150):
        # Mix of GPIO and native functions
        if i % 3 == 0:
            # Native function
            dw0 = 0x00000400  # NF1
            dw1 = 0x80000000
        else:
            # GPIO input
            dw0 = 0x00000200
            dw1 = 0x80000000
        entries.append(struct.pack('<II', dw0, dw1))
    
    return b''.join(entries)

def create_mock_vgpio_table():
    """Create a mock VGPIO configuration table (Stride 20, NAFVWE, DEEP)"""
    entries = []
    
    # Create 38 entries (typical VGPIO table size)
    for i in range(38):
        # DW0: 
        # Bit 31:30 = 01 (DEEP reset)
        # Bit 27 = 1 (NAFVWE)
        # Bit 10 = 0 (GPIO) or 1 (NF1)
        
        mode = 0 if i % 2 == 0 else 1
        
        dw0 = (1 << 30) | (1 << 27) | (mode << 10)
        dw1 = 0x00000000
        
        # VGPIOs often have 20 bytes (DW0-DW4) or 12/16 bytes
        # We'll use 20 bytes to match the detector's VGPIO logic
        entry = struct.pack('<IIIII', dw0, dw1, 0, 0, 0)
        entries.append(entry)
        
    return b''.join(entries)

def create_mock_bios():
    """Create a mock BIOS image with GPIO table embedded"""
    
    # Create a simple binary blob
    # Header (256 bytes of padding)
    header = b'\x00' * 256
    
    # Standard GPIO table (Stride 8)
    gpio_table = create_mock_gpio_table()
    
    # Padding between tables
    padding1 = b'\xFF' * 1024
    
    # VGPIO table (Stride 20)
    vgpio_table = create_mock_vgpio_table()
    
    # More padding
    padding2 = b'\xFF' * 1024
    
    # Combine
    mock_bios = header + gpio_table + padding1 + vgpio_table + padding2
    
    return mock_bios

def main():
    output_file = Path(__file__).parent / 'test_mock_bios.bin'
    
    print("Creating mock BIOS image for testing...")
    mock_bios = create_mock_bios()
    
    with open(output_file, 'wb') as f:
        f.write(mock_bios)
    
    print(f"Created: {output_file}")
    print(f"Size: {len(mock_bios)} bytes")
    print("\nYou can test with:")
    print(f"  python3 bios2gpio.py --input {output_file.name} --output test_gpio.h --verbose")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
