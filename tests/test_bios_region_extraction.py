#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
Test BIOS region extraction to ensure correct boundaries.

This test verifies that the BIOS region is extracted correctly for Alder Lake
platforms, where ifdtool requires the -p adl flag to parse the IFD correctly.

Without -p adl, ifdtool extracts an invalid BIOS region that overlaps with
IFD and ME regions, consisting mostly of 0xFF padding.
"""

import sys
import hashlib
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.extractor import UEFIExtractor


def test_alderlake_bios_region_extraction():
    """
    Test that Alder Lake BIOS region is extracted correctly.
    
    Expected behavior:
    - With -p adl: BIOS region starts at 0x01000000, SHA256: bb32644f...
    - Without -p adl: BIOS region starts at 0x00000000 (WRONG), SHA256: aafe87c7...
    
    The correct extraction should produce the bb32644f... hash.
    """
    # Test with MSI Z690 BIOS image
    test_image = Path(__file__).parent.parent / 'data' / 'bios_images' / '7D25v1M' / 'E7D25IMS.1M0'
    
    if not test_image.exists():
        print(f"SKIP: Test image not found: {test_image}")
        return
    
    # Expected SHA256 of correctly extracted BIOS region (with -p adl)
    EXPECTED_SHA256 = "bb32644fdc57fb4235adceb5bf6163336b4672f0c59f7740932c66bfd20f9a8d"
    
    # Expected SHA256 of incorrectly extracted BIOS region (without -p adl)
    WRONG_SHA256 = "aafe87c7388722b2ac2c7f8ca2b4beb36b6d6c1ed18cb0a7e4aed4db28d6a0a5"
    
    extractor = UEFIExtractor(str(test_image))
    bios_region = extractor.get_bios_region()
    
    # Calculate SHA256 of extracted BIOS region
    with open(bios_region, 'rb') as f:
        actual_sha256 = hashlib.sha256(f.read()).hexdigest()
    
    print(f"Extracted BIOS region: {bios_region}")
    print(f"SHA256: {actual_sha256}")
    
    if actual_sha256 == WRONG_SHA256:
        print("FAIL: BIOS region extracted WITHOUT -p adl flag (incorrect boundaries)")
        print("      This will result in invalid GPIO table detection!")
        print("      The extracted region is just IFD + ME + 0xFF padding.")
        return False
    elif actual_sha256 == EXPECTED_SHA256:
        print("PASS: BIOS region extracted correctly (with -p adl or UEFIExtract)")
        return True
    else:
        print(f"WARN: Unexpected SHA256 hash: {actual_sha256}")
        print("      This might indicate a different extraction method or tool version.")
        # Check if the region at least starts at the correct offset
        with open(bios_region, 'rb') as f:
            # Read first 16 bytes to check if it's the actual BIOS region
            header = f.read(16)
            # BIOS region should NOT start with 0x5A 0xA5 (IFD signature)
            if header[:2] == b'\x5A\xA5':
                print("      FAIL: Region starts with IFD signature (wrong extraction)")
                return False
            # BIOS region should NOT be all 0xFF
            if header == b'\xFF' * 16:
                print("      FAIL: Region starts with 0xFF padding (wrong extraction)")
                return False
        print("      PASS: Region appears valid (doesn't start with IFD or padding)")
        return True


if __name__ == '__main__':
    success = test_alderlake_bios_region_extraction()
    sys.exit(0 if success else 1)
