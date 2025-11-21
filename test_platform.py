#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
Simple test to verify platform definitions and GPIO parsing.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from platforms.alderlake import AlderLakeGpioPadConfig, get_pad_name, GPIO_GROUPS

def test_pad_config_parsing():
    """Test GPIO pad configuration parsing"""
    print("Testing GPIO pad configuration parsing...")
    
    # Example DW0/DW1 values from a typical GPIO output pad
    # GPO, output=1, PLTRST, no termination
    dw0 = 0x00000001  # TX state = 1, mode = GPIO
    dw1 = 0x80000000  # Reset = PLTRST (10b << 30)
    
    # Create test data
    test_data = dw0.to_bytes(4, 'little') + dw1.to_bytes(4, 'little')
    
    # Parse
    config = AlderLakeGpioPadConfig(test_data)
    
    print(f"  DW0: 0x{config.dw0:08x}")
    print(f"  DW1: 0x{config.dw1:08x}")
    print(f"  Mode: {config.get_pad_mode().name}")
    print(f"  Direction: {config.get_direction().name}")
    print(f"  Output value: {config.get_output_value()}")
    print(f"  Reset: {config.get_reset_config().name}")
    print(f"  Termination: {config.get_termination().name}")
    
    assert config.get_pad_mode().name == 'GPIO'
    assert config.get_output_value() == 1
    print("  ✓ Basic parsing works\n")

def test_pad_naming():
    """Test pad name generation"""
    print("Testing pad name generation...")
    
    # Test standard GPIO groups
    assert get_pad_name('GPP_B', 0) == 'GPP_B0'
    assert get_pad_name('GPP_B', 12) == 'GPP_B12'
    assert get_pad_name('GPP_D', 5) == 'GPP_D5'
    
    # Test virtual GPIOs
    assert get_pad_name('VGPIO', 0) == 'VGPIO_0'
    assert get_pad_name('VGPIO_PCIE', 10) == 'VGPIO_PCIE_10'
    
    print("  ✓ Pad naming works\n")

def test_gpio_groups():
    """Test GPIO group definitions"""
    print("Testing GPIO group definitions...")
    
    # Check some key groups exist
    assert 'GPP_A' in GPIO_GROUPS
    assert 'GPP_B' in GPIO_GROUPS
    assert 'GPP_D' in GPIO_GROUPS
    assert 'GPD' in GPIO_GROUPS
    
    # Check group structure
    gpp_b = GPIO_GROUPS['GPP_B']
    assert gpp_b['community'] == 1
    assert gpp_b['pad_count'] == 24
    
    print(f"  Total GPIO groups defined: {len(GPIO_GROUPS)}")
    print(f"  Communities: {sorted(set(g['community'] for g in GPIO_GROUPS.values()))}")
    print("  ✓ GPIO groups defined correctly\n")

def main():
    print("=" * 60)
    print("bios2gpio Platform Definition Tests")
    print("=" * 60)
    print()
    
    try:
        test_pad_config_parsing()
        test_pad_naming()
        test_gpio_groups()
        
        print("=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
