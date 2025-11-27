#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
Comprehensive test suite for compare_images.py falsification logic.

This test suite validates that compare_images.py correctly separates
physical GPIO from VGPIO comparisons, enabling proper falsification testing
of the claim: "Two BIOS images have identical physical GPIOs."
"""

import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Setup imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


@pytest.fixture
def mock_physical_gpio_identical():
    """Mock pad dict: identical physical GPIOs"""
    return {
        'GPP_B0': {
            'name': 'GPP_B0',
            'mode': 'GPIO',
            'direction': 'INPUT',
            'output_value': 0,
            'reset': 'PLTRST',
            'termination': 'NONE',
            'dw0': 0x00000200,
            'dw1': 0x80000000,
            'is_vgpio': False
        },
        'GPP_B1': {
            'name': 'GPP_B1',
            'mode': 'GPIO',
            'direction': 'OUTPUT',
            'output_value': 1,
            'reset': 'PLTRST',
            'termination': 'NONE',
            'dw0': 0x00000101,
            'dw1': 0x80000000,
            'is_vgpio': False
        },
        'GPP_B2': {
            'name': 'GPP_B2',
            'mode': 'NF1',
            'direction': None,
            'output_value': None,
            'reset': 'PLTRST',
            'termination': 'NONE',
            'dw0': 0x00000400,
            'dw1': 0x80000000,
            'is_vgpio': False
        }
    }

@pytest.fixture
def mock_physical_gpio_different():
    """Mock pad dict: different physical GPIOs"""
    return {
        'GPP_B0': {
            'name': 'GPP_B0',
            'mode': 'GPIO',
            'direction': 'OUTPUT',  # DIFFERENT
            'output_value': 1,      # DIFFERENT
            'reset': 'PLTRST',
            'termination': 'NONE',
            'dw0': 0x00000101,      # DIFFERENT
            'dw1': 0x80000000,
            'is_vgpio': False
        },
        'GPP_B1': {
            'name': 'GPP_B1',
            'mode': 'GPIO',
            'direction': 'INPUT',   # DIFFERENT
            'output_value': 0,      # DIFFERENT
            'reset': 'PLTRST',
            'termination': 'NONE',
            'dw0': 0x00000200,      # DIFFERENT
            'dw1': 0x80000000,
            'is_vgpio': False
        },
        'GPP_B2': {
            'name': 'GPP_B2',
            'mode': 'NF2',          # DIFFERENT
            'direction': None,
            'output_value': None,
            'reset': 'PLTRST',
            'termination': 'NONE',
            'dw0': 0x00000800,      # DIFFERENT
            'dw1': 0x80000000,
            'is_vgpio': False
        }
    }

@pytest.fixture
def mock_vgpio_identical():
    """Mock pad dict: identical VGPIOs"""
    return {
        'VGPIO0': {
            'name': 'VGPIO0',
            'mode': 'GPIO',
            'direction': 'INPUT',
            'reset': 'DEEP',
            'dw0': 0x48000000,
            'dw1': 0x00000000,
            'is_vgpio': True
        },
        'VGPIO1': {
            'name': 'VGPIO1',
            'mode': 'NF1',
            'direction': None,
            'reset': 'DEEP',
            'dw0': 0x48000400,
            'dw1': 0x00000000,
            'is_vgpio': True
        }
    }

@pytest.fixture
def mock_vgpio_different():
    """Mock pad dict: different VGPIOs"""
    return {
        'VGPIO0': {
            'name': 'VGPIO0',
            'mode': 'NF1',          # DIFFERENT
            'direction': None,
            'reset': 'DEEP',
            'dw0': 0x48000400,      # DIFFERENT
            'dw1': 0x00010000,      # DIFFERENT
            'is_vgpio': True
        },
        'VGPIO1': {
            'name': 'VGPIO1',
            'mode': 'GPIO',         # DIFFERENT
            'direction': 'OUTPUT',  # DIFFERENT
            'reset': 'DEEP',
            'dw0': 0x48000000,      # DIFFERENT
            'dw1': 0x00010000,      # DIFFERENT
            'is_vgpio': True
        }
    }


class TestCompareImagesFalsification:
    """Test suite for compare_images.py falsification framework"""

    def test_physical_gpio_identical_vgpio_identical(self, 
                                                     mock_physical_gpio_identical,
                                                     mock_vgpio_identical):
        """
        TEST CASE 1: Both physical GPIO and VGPIO are identical.
        
        Expected: 100% match for both physical and VGPIO
        This is the null case - should pass without issues.
        """
        from tools.compare_images import compare_pads_by_type, compare_pad_set
        
        # Combine all pads
        all_pads_a = {**mock_physical_gpio_identical, **mock_vgpio_identical}
        all_pads_b = {**mock_physical_gpio_identical, **mock_vgpio_identical}
        
        # Separate by type
        phys_a, phys_b, vgpio_a, vgpio_b = compare_pads_by_type(all_pads_a, all_pads_b)
        
        # Compare
        phys_stats = compare_pad_set(phys_a, phys_b, "image_a", "image_b")
        vgpio_stats = compare_pad_set(vgpio_a, vgpio_b, "image_a", "image_b")
        
        # Assertions
        assert phys_stats['matches'] == phys_stats['total'], \
            "Physical GPIO should be 100% identical"
        assert phys_stats['mismatches'] == 0, \
            "Physical GPIO should have zero mismatches"
        assert vgpio_stats['matches'] == vgpio_stats['total'], \
            "VGPIO should be 100% identical"
        assert vgpio_stats['mismatches'] == 0, \
            "VGPIO should have zero mismatches"

    def test_physical_gpio_identical_vgpio_different(self, 
                                                      mock_physical_gpio_identical,
                                                      mock_vgpio_identical,
                                                      mock_vgpio_different):
        """
        TEST CASE 2 (CRITICAL): Physical GPIO identical but VGPIO different.
        
        This is the KEY FALSIFICATION TEST. If compare_images.py reports
        ambiguous percentages instead of clearly separating physical vs VGPIO,
        the tool fails its falsification requirement.
        
        Expected: 
        - Physical GPIO: 100% match
        - VGPIO: 0% match
        """
        from tools.compare_images import compare_pads_by_type, compare_pad_set
        
        # Combine: identical physical, different VGPIO
        all_pads_a = {**mock_physical_gpio_identical, **mock_vgpio_identical}
        all_pads_b = {**mock_physical_gpio_identical, **mock_vgpio_different}
        
        # Separate by type
        phys_a, phys_b, vgpio_a, vgpio_b = compare_pads_by_type(all_pads_a, all_pads_b)
        
        # Compare
        phys_stats = compare_pad_set(phys_a, phys_b, "image_a", "image_b")
        vgpio_stats = compare_pad_set(vgpio_a, vgpio_b, "image_a", "image_b")
        
        # Critical assertions
        assert phys_stats['matches'] == phys_stats['total'], \
            "FALSIFICATION FAILURE: Physical GPIO should be 100% identical"
        assert phys_stats['mismatches'] == 0, \
            "FALSIFICATION FAILURE: Physical GPIO should have zero mismatches"
        
        assert vgpio_stats['mismatches'] > 0, \
            "FALSIFICATION VERIFICATION: VGPIO should show differences"
        # VGPIO may not be 0% if some entries match by chance, but should be partial
        assert vgpio_stats['matches'] < vgpio_stats['total'], \
            "FALSIFICATION VERIFICATION: VGPIO should have mismatches"

    def test_physical_gpio_different_vgpio_identical(self, 
                                                      mock_physical_gpio_identical,
                                                      mock_physical_gpio_different,
                                                      mock_vgpio_identical):
        """
        TEST CASE 3: Physical GPIO different but VGPIO identical.
        
        Expected:
        - Physical GPIO: 0% match (or partial)
        - VGPIO: 100% match
        """
        from tools.compare_images import compare_pads_by_type, compare_pad_set
        
        # Combine: different physical, identical VGPIO
        all_pads_a = {**mock_physical_gpio_identical, **mock_vgpio_identical}
        all_pads_b = {**mock_physical_gpio_different, **mock_vgpio_identical}
        
        # Separate by type
        phys_a, phys_b, vgpio_a, vgpio_b = compare_pads_by_type(all_pads_a, all_pads_b)
        
        # Compare
        phys_stats = compare_pad_set(phys_a, phys_b, "image_a", "image_b")
        vgpio_stats = compare_pad_set(vgpio_a, vgpio_b, "image_a", "image_b")
        
        # Physical should differ
        assert phys_stats['mismatches'] > 0, \
            "Physical GPIO should show differences"
        
        # VGPIO should match
        assert vgpio_stats['matches'] == vgpio_stats['total'], \
            "VGPIO should be 100% identical"
        assert vgpio_stats['mismatches'] == 0, \
            "VGPIO should have zero mismatches"

    def test_compare_pad_set_returns_statistics(self, mock_physical_gpio_identical):
        """
        TEST CASE 4: Verify compare_pad_set returns proper statistics.
        
        The compare_pad_set function must return a dict with:
        - matches: count of identical pads
        - mismatches: count of different pads
        - missing_a: pads missing in first image
        - missing_b: pads missing in second image
        - total: total unique pad names
        - details: list of differences
        """
        from tools.compare_images import compare_pad_set
        
        stats = compare_pad_set(mock_physical_gpio_identical, 
                               mock_physical_gpio_identical,
                               "img_a", "img_b")
        
        # Verify structure
        assert 'matches' in stats, "Missing 'matches' key"
        assert 'mismatches' in stats, "Missing 'mismatches' key"
        assert 'missing_a' in stats, "Missing 'missing_a' key"
        assert 'missing_b' in stats, "Missing 'missing_b' key"
        assert 'total' in stats, "Missing 'total' key"
        assert 'details' in stats, "Missing 'details' key"
        
        # Verify types
        assert isinstance(stats['matches'], int), "matches should be int"
        assert isinstance(stats['mismatches'], int), "mismatches should be int"
        assert isinstance(stats['total'], int), "total should be int"
        assert isinstance(stats['details'], list), "details should be list"

    def test_missing_pads_tracked(self, mock_physical_gpio_identical):
        """
        TEST CASE 5: Verify missing pads are properly tracked.
        
        If one image is missing a pad, it should be reported as missing_a or missing_b.
        """
        from tools.compare_images import compare_pad_set
        
        # Create subset
        subset = dict(list(mock_physical_gpio_identical.items())[:2])
        full = mock_physical_gpio_identical
        
        stats = compare_pad_set(full, subset, "full", "subset")
        
        # Should have missing_b pads
        assert stats['missing_b'] > 0, \
            "Should detect pads missing in subset"
        assert stats['total'] == len(full), \
            "Total should be union of both sets"

    def test_raw_register_comparison_catches_differences(self):
        """
        TEST CASE 6: Verify that raw DW0/DW1 register comparison catches 
        differences that might be missed by logical field comparison.
        
        This is the "Ultimate Truth" - even if mode/direction/etc look OK,
        different raw values mean different hardware config.
        """
        from tools.compare_images import compare_pad_set
        
        # Pad A: looks like GPIO input
        pad_a = {
            'GPP_B0': {
                'name': 'GPP_B0',
                'mode': 'GPIO',
                'direction': 'INPUT',
                'dw0': 0x00000200,
                'dw1': 0x80000000,
                'is_vgpio': False
            }
        }
        
        # Pad B: same logical config but different termination bits in raw DW1
        pad_b = {
            'GPP_B0': {
                'name': 'GPP_B0',
                'mode': 'GPIO',
                'direction': 'INPUT',
                'dw0': 0x00000200,
                'dw1': 0x80001800,  # DIFFERENT termination in raw register
                'is_vgpio': False
            }
        }
        
        stats = compare_pad_set(pad_a, pad_b, "a", "b")
        
        # Should detect difference
        assert stats['mismatches'] > 0, \
            "Should detect raw register differences even if logical fields match"


class TestMockBIOSGeneration:
    """Test suite for mock BIOS generation"""

    def test_create_mock_bios_standard(self):
        """Verify standard mock BIOS is created"""
        from tools.create_mock_bios import create_mock_bios
        
        bios = create_mock_bios("standard", "standard", 20)
        
        assert isinstance(bios, bytes), "Should return bytes"
        assert len(bios) > 1000, "Should have reasonable size"

    def test_create_mock_bios_variants(self):
        """Verify different BIOS variants are created"""
        from tools.create_mock_bios import create_mock_bios
        
        bios_std = create_mock_bios("standard", "standard", 20)
        bios_var = create_mock_bios("variant_b", "variant_b", 20)
        
        # Variants should be different
        assert bios_std != bios_var, \
            "Different variants should produce different binaries"

    def test_create_mock_bios_different_strides(self):
        """Verify VGPIO stride variations work"""
        from tools.create_mock_bios import create_mock_bios
        
        for stride in [12, 16, 20]:
            bios = create_mock_bios("standard", "standard", stride)
            assert isinstance(bios, bytes), f"Should work with stride {stride}"
            assert len(bios) > 0, f"Should produce output for stride {stride}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
