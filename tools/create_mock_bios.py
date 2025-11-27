#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
Create mock BIOS images with embedded GPIO tables for comprehensive testing.

This tool generates multiple test variants to enable falsification testing of
the compare_images.py tool, specifically verifying that it correctly separates
physical GPIO from VGPIO comparisons.
"""

import struct
import sys
from pathlib import Path
from typing import Tuple

def create_mock_gpio_table(variant: str = "standard") -> bytes:
    """
    Create a mock GPIO configuration table.
    
    Args:
        variant: Type of GPIO table:
            - "standard": Default GPIO table with typical configs
            - "variant_a": Physical GPIO table variant A
            - "variant_b": Physical GPIO table variant B (different from A)
    """
    entries = []
    
    if variant == "standard" or variant == "variant_a":
        # Standard GPIO table - GPP_B group style configurations
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
    
    elif variant == "variant_b":
        # Different physical GPIO configuration - GPP_B with changes
        # CRITICAL TEST CASE: Different physical GPIO config
        
        # GPP_B0 - GPIO OUTPUT (different from variant_a which is INPUT)
        dw0 = 0x00000101  # TX enabled, output=1 (DIFFERENT!)
        dw1 = 0x80000000
        entries.append(struct.pack('<II', dw0, dw1))
        
        # GPP_B1 - GPIO INPUT (different from variant_a which is OUTPUT)
        dw0 = 0x00000200  # RX enabled (DIFFERENT!)
        dw1 = 0x80000000
        entries.append(struct.pack('<II', dw0, dw1))
        
        # GPP_B2 - Native function NF2 (different from variant_a's NF1)
        dw0 = 0x00000800  # Mode = NF2 (DIFFERENT!)
        dw1 = 0x80000000
        entries.append(struct.pack('<II', dw0, dw1))
        
        # GPP_B3 - GPIO input without pull-up (different from variant_a's UP_20K)
        dw0 = 0x00000200  # RX enabled, TX disabled
        dw1 = 0x80000000  # PLTRST, no termination (DIFFERENT!)
        entries.append(struct.pack('<II', dw0, dw1))
        
        # Add more entries
        for i in range(4, 150):
            if i % 4 == 0:
                # Different mix
                dw0 = 0x00000800  # NF2
                dw1 = 0x80000000
            else:
                dw0 = 0x00000200
                dw1 = 0x80000000
            entries.append(struct.pack('<II', dw0, dw1))
    
    return b''.join(entries)

def create_mock_vgpio_table(variant: str = "standard", stride: int = 20) -> bytes:
    """
    Create a mock VGPIO configuration table.
    
    Args:
        variant: Type of VGPIO table:
            - "standard": Standard VGPIO table
            - "variant_a": VGPIO variant A
            - "variant_b": VGPIO variant B (different from A)
        stride: Entry size in bytes (12, 16, or 20 for VGPIO testing)
    """
    entries = []
    
    # Create 38 entries (typical VGPIO table size)
    entry_count = 38
    
    if variant == "standard" or variant == "variant_a":
        # Standard VGPIO configuration
        for i in range(entry_count):
            # DW0: 
            # Bit 31:30 = 01 (DEEP reset)
            # Bit 27 = 1 (NAFVWE)
            # Bit 10 = 0 (GPIO) or 1 (NF1)
            
            mode = 0 if i % 2 == 0 else 1
            
            dw0 = (1 << 30) | (1 << 27) | (mode << 10)
            dw1 = 0x00000000
            
            # Create variable-length entry based on stride
            if stride == 12:
                entry = struct.pack('<III', dw0, dw1, 0)
            elif stride == 16:
                entry = struct.pack('<IIII', dw0, dw1, 0, 0)
            else:  # stride == 20
                entry = struct.pack('<IIIII', dw0, dw1, 0, 0, 0)
            
            entries.append(entry)
    
    elif variant == "variant_b":
        # Different VGPIO configuration - critical for falsification test
        # This allows testing: "Physical GPIO identical, VGPIO different"
        for i in range(entry_count):
            # Different mode pattern
            mode = 1 if i % 2 == 0 else 0  # REVERSED!
            
            dw0 = (1 << 30) | (1 << 27) | (mode << 10)
            dw1 = 0x00010000  # DIFFERENT register value
            
            if stride == 12:
                entry = struct.pack('<III', dw0, dw1, 0)
            elif stride == 16:
                entry = struct.pack('<IIII', dw0, dw1, 0, 0)
            else:
                entry = struct.pack('<IIIII', dw0, dw1, 0, 0, 0)
            
            entries.append(entry)
    
    return b''.join(entries)

def create_mock_invalid_gpio_table(variant: str = "invalid_mode") -> bytes:
    """
    Create a mock GPIO table with INVALID entries to test validation logic.
    
    Args:
        variant: Type of invalidity:
            - "invalid_mode": Mode > 7
            - "invalid_reset": Reset > 3 (impossible with 2 bits, but maybe reserved bits set?)
                              Actually reset is 2 bits, so 0-3 are always valid integers.
                              But we can test if we can force other bits? No, mask is 2 bits.
                              So "invalid_reset" is hard to generate unless we assume logic checks for specific values.
            - "all_ones": 0xFFFFFFFF
            - "all_zeros": 0x00000000
    """
    entries = []
    
    if variant == "invalid_mode":
        # Generate entries with Mode = 8 (1000 binary)
        # DW0[13:10] = 1000
        for i in range(50):
            dw0 = (8 << 10) | (1 << 30) # Mode 8, Reset 1
            dw1 = 0
            entries.append(struct.pack('<II', dw0, dw1))
            
    elif variant == "all_ones":
        for i in range(50):
            entries.append(struct.pack('<II', 0xFFFFFFFF, 0xFFFFFFFF))
            
    elif variant == "all_zeros":
        for i in range(50):
            entries.append(struct.pack('<II', 0, 0))
            
    return b''.join(entries)

def create_mock_bios(variant_physical: str = "standard", 
                     variant_vgpio: str = "standard", 
                     vgpio_stride: int = 20) -> bytes:
    """
    Create a mock BIOS image with GPIO table embedded.
    
    Args:
        variant_physical: Physical GPIO variant ("standard", "variant_a", "variant_b")
        variant_vgpio: VGPIO variant ("standard", "variant_a", "variant_b")
        vgpio_stride: VGPIO entry stride (12, 16, or 20 bytes)
    
    Returns:
        Complete mock BIOS binary
    """
    
    # Create a simple binary blob
    # Header (256 bytes of padding)
    header = b'\x00' * 256
    
    # Standard GPIO table (Stride 8)
    gpio_table = create_mock_gpio_table(variant_physical)
    
    # Padding between tables
    padding1 = b'\xFF' * 1024
    
    # VGPIO table with specified stride
    vgpio_table = create_mock_vgpio_table(variant_vgpio, vgpio_stride)
    
    # More padding
    padding2 = b'\xFF' * 1024
    
    # Combine
    mock_bios = header + gpio_table + padding1 + vgpio_table + padding2
    
    return mock_bios

def main():
    output_dir = Path(__file__).parent.parent / 'data' / 'bios_images'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Test scenarios for falsification testing
    scenarios = [
        {
            'name': 'test_identical_physical_identical_vgpio',
            'description': 'Identical physical GPIO + identical VGPIO (should match 100%)',
            'physical': 'standard',
            'vgpio': 'standard',
            'stride': 20
        },
        {
            'name': 'test_identical_physical_different_vgpio',
            'description': 'Identical physical GPIO + DIFFERENT VGPIO (physical 100%, VGPIO 0%)',
            'physical': 'standard',
            'vgpio': 'variant_b',
            'stride': 20
        },
        {
            'name': 'test_different_physical_identical_vgpio',
            'description': 'DIFFERENT physical GPIO + identical VGPIO',
            'physical': 'variant_b',
            'vgpio': 'standard',
            'stride': 20
        },
        {
            'name': 'test_vgpio_stride_12',
            'description': 'VGPIO with 12-byte stride (VGPIO_USB)',
            'physical': 'standard',
            'vgpio': 'standard',
            'stride': 12
        },
        {
            'name': 'test_vgpio_stride_16',
            'description': 'VGPIO with 16-byte stride',
            'physical': 'standard',
            'vgpio': 'standard',
            'stride': 16
        },
        {
            'name': 'test_variant_a_physical',
            'description': 'Physical GPIO variant A for paired comparison',
            'physical': 'variant_a',
            'vgpio': 'standard',
            'stride': 20
        },
    ]
    
    print("Creating comprehensive mock BIOS test suite...")
    print(f"Output directory: {output_dir}\n")
    
    for scenario in scenarios:
        output_file = output_dir / f"{scenario['name']}.bin"
        
        print(f"Creating: {scenario['name']}")
        print(f"  {scenario['description']}")
        
        mock_bios = create_mock_bios(
            variant_physical=scenario['physical'],
            variant_vgpio=scenario['vgpio'],
            vgpio_stride=scenario['stride']
        )
        
        with open(output_file, 'wb') as f:
            f.write(mock_bios)
        
        print(f"  ✓ Created: {output_file} ({len(mock_bios)} bytes)\n")
    
    print("\nMock BIOS suite created successfully!")
    print("\nFalsification Test Instructions:")
    print("=" * 70)
    print("\n1. Test Case: Identical physical GPIO, different VGPIO")
    print("   python3 compare_images.py \\")
    print(f"     -a {output_dir}/test_identical_physical_identical_vgpio.bin \\")
    print(f"     -b {output_dir}/test_identical_physical_different_vgpio.bin \\")
    print("     --platform alderlake")
    print("\n   Expected: Physical GPIO: 100% match, VGPIO: 0% match")
    print("   This FALSIFIES the claim if physical shows 100% identical and VGPIO differs.\n")
    
    print("2. Test Case: Different physical GPIO")
    print("   python3 compare_images.py \\")
    print(f"     -a {output_dir}/test_identical_physical_identical_vgpio.bin \\")
    print(f"     -b {output_dir}/test_different_physical_identical_vgpio.bin \\")
    print("     --platform alderlake")
    print("\n   Expected: Physical GPIO: 0% match, VGPIO: 100% match\n")
    
    print("3. Test Case: Completely identical")
    print("   python3 compare_images.py \\")
    print(f"     -a {output_dir}/test_identical_physical_identical_vgpio.bin \\")
    print(f"     -b {output_dir}/test_identical_physical_identical_vgpio.bin \\")
    print("     --platform alderlake")
    print("\n   Expected: Both physical and VGPIO: 100% match\n")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())

