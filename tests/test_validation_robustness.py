#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
Test suite for Issue #1: Validation Robustness
"""

import sys
import struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.platforms.alderlake import AlderLakeGpioPadConfig
from tools.create_mock_bios import create_mock_invalid_gpio_table

def test_validation_robustness():
    print("\n" + "="*80)
    print("TEST: Issue #1 - Validation Robustness")
    print("="*80)
    
    # Test 1: Invalid Mode (> 7)
    print("\n1. Testing Invalid Mode (Mode=8)...")
    invalid_mode_data = create_mock_invalid_gpio_table("invalid_mode")
    # Take first entry (8 bytes)
    entry_data = invalid_mode_data[:8]
    config = AlderLakeGpioPadConfig(entry_data)
    
    is_valid = config.validate()
    print(f"   Mode=8 (Raw DW0=0x{config.dw0:08x}) -> Valid? {is_valid}")
    
    if not is_valid:
        print("   ✅ CORRECT: Invalid mode rejected.")
    else:
        print("   ❌ FAILED: Invalid mode accepted!")
        return False

    # Test 2: All Zeros
    print("\n2. Testing All Zeros...")
    zeros_data = create_mock_invalid_gpio_table("all_zeros")
    entry_data = zeros_data[:8]
    config = AlderLakeGpioPadConfig(entry_data)
    
    is_valid = config.validate()
    print(f"   All Zeros -> Valid? {is_valid}")
    
    if not is_valid:
        print("   ✅ CORRECT: All zeros rejected.")
    else:
        print("   ❌ FAILED: All zeros accepted!")
        return False

    # Test 3: All Ones
    print("\n3. Testing All Ones...")
    ones_data = create_mock_invalid_gpio_table("all_ones")
    entry_data = ones_data[:8]
    config = AlderLakeGpioPadConfig(entry_data)
    
    is_valid = config.validate()
    print(f"   All Ones -> Valid? {is_valid}")
    
    if not is_valid:
        print("   ✅ CORRECT: All ones rejected.")
    else:
        print("   ❌ FAILED: All ones accepted!")
        return False

    return True

if __name__ == '__main__':
    if test_validation_robustness():
        print("\n✅ ALL VALIDATION TESTS PASSED")
        sys.exit(0)
    else:
        print("\n❌ VALIDATION TESTS FAILED")
        sys.exit(1)
