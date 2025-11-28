#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
Alder Lake / Z690 GPIO platform definitions.

This module defines the GPIO pad configuration structures and metadata
specific to Intel Alder Lake platforms (12th gen Core, Z690/H670/B660 chipsets).

Based on:
- Intel Alder Lake PCH Datasheet
- coreboot util/intelp2m/platforms/adl/
- coreboot util/inteltool/gpio.c
"""

import struct
from typing import Dict, List, Tuple, Optional
from enum import IntEnum


class PadMode(IntEnum):
    """GPIO pad mode selection"""
    GPIO = 0
    NF1 = 1  # Native Function 1
    NF2 = 2
    NF3 = 3
    NF4 = 4
    NF5 = 5
    NF6 = 6
    NF7 = 7


class PadDirection(IntEnum):
    """GPIO direction for GPIO mode"""
    INPUT = 0
    OUTPUT = 1


class PadPull(IntEnum):
    """Termination/Pull resistor configuration (DW1[13:10])"""
    NONE = 0x0
    DN_5K = 0x2   # Pull-down 5K
    DN_20K = 0x4  # Pull-down 20K
    UP_1K = 0x9   # Pull-up 1K
    UP_2K = 0xB   # Pull-up 2K
    UP_5K = 0xA   # Pull-up 5K
    UP_20K = 0xC  # Pull-up 20K
    UP_1K_2K = 0xD  # Pull-up 1K + 2K (1.5K effective)
    NATIVE = 0xF


class PadReset(IntEnum):
    """Reset domain configuration (DW0[31:30])"""
    PWROK = 0b00    # RSMRST / Power Good
    DEEP = 0b01     # Deep sleep reset
    PLTRST = 0b10   # Platform reset
    RSMRST = 0b11   # Resume reset


class PadTrigger(IntEnum):
    """Interrupt trigger type (DW0[27:25])"""
    LEVEL = 0b00
    EDGE_SINGLE = 0b01
    OFF = 0b10
    EDGE_BOTH = 0b11


class RxTxConfig(IntEnum):
    """RX/TX buffer configuration (DW0[9:8])"""
    TX_RX_ENABLE = 0b00
    TX_DISABLE = 0b01
    RX_DISABLE = 0b10
    TX_RX_DISABLE = 0b11


class PadOwner(IntEnum):
    """Pad ownership"""
    ACPI = 0
    GPIO_DRIVER = 1


# Alder Lake DW0/DW1 Masks (from intelp2m)
# These define which bits are valid/used in each register
DW0_MASK = (0b1 << 27) | (0b1 << 24) | (0b11 << 21) | (0b1111 << 16) | 0b11111100
DW1_MASK = 0xFDFFC3FF


# GPIO Community and Group definitions for Alder Lake PCH-P/M/S
# Based on Intel Alder Lake PCH datasheet

GPIO_GROUPS = {
    # Community 0
    'GPP_I': {'community': 0, 'group': 0, 'pad_start': 0, 'pad_count': 23},
    'GPP_R': {'community': 0, 'group': 1, 'pad_start': 23, 'pad_count': 22},
    'GPP_J': {'community': 0, 'group': 2, 'pad_start': 45, 'pad_count': 12},
    'VGPIO': {'community': 0, 'group': 3, 'pad_start': 57, 'pad_count': 38},
    'VGPIO_0': {'community': 0, 'group': 4, 'pad_start': 95, 'pad_count': 12},

    # Community 1
    'GPP_B': {'community': 1, 'group': 0, 'pad_start': 0, 'pad_count': 24},
    'GPP_G': {'community': 1, 'group': 1, 'pad_start': 24, 'pad_count': 8},
    'GPP_H': {'community': 1, 'group': 2, 'pad_start': 32, 'pad_count': 24},

    # Community 2
    'GPD': {'community': 2, 'group': 0, 'pad_start': 0, 'pad_count': 13},

    # Community 3
    'GPP_A': {'community': 3, 'group': 0, 'pad_start': 0, 'pad_count': 15},
    'GPP_C': {'community': 3, 'group': 1, 'pad_start': 15, 'pad_count': 24},
    'VGPIO_PCIE': {'community': 3, 'group': 2, 'pad_start': 39, 'pad_count': 80},

    # Community 4
    'GPP_S': {'community': 4, 'group': 0, 'pad_start': 0, 'pad_count': 8},
    'GPP_E': {'community': 4, 'group': 1, 'pad_start': 8, 'pad_count': 22},
    'GPP_K': {'community': 4, 'group': 2, 'pad_start': 30, 'pad_count': 12},
    'GPP_F': {'community': 4, 'group': 3, 'pad_start': 42, 'pad_count': 24},

    # Community 5
    'GPP_D': {'community': 5, 'group': 0, 'pad_start': 0, 'pad_count': 24},
}

# Order of Physical GPIO Groups in the monolithic BIOS table
# Virtual groups (VGPIO*) are excluded as they are not present in the 8-byte config table.
ALDERLAKE_S_GROUPS_ORDER = [
    # Community 0
    ('GPP_I', 23),
    ('GPP_R', 22),
    ('GPP_J', 12),

    # Community 1
    ('GPP_B', 24),
    ('GPP_G', 8),
    ('GPP_H', 24),

    # Community 2
    ('GPD', 13),

    # Community 3
    ('GPP_A', 15),
    ('GPP_C', 24),

    # Community 4
    ('GPP_S', 8),
    ('GPP_E', 22),
    ('GPP_K', 12),
    ('GPP_F', 24),

    # Community 5
    ('GPP_D', 24),
]

# Signature for Z690/Alder Lake GPIO Table (Start of GPP_I)
# GPP_I0: GPIO, GPP_I1-I4: NF1 (DDSP_HPD)
ALDERLAKE_GPIO_SIGNATURE = [
    {'mode': 0, 'reset': 2}, # GPP_I0
    {'mode': 1, 'reset': 2}, # GPP_I1
    {'mode': 1, 'reset': 2}, # GPP_I2
    {'mode': 1, 'reset': 2}, # GPP_I3
    {'mode': 1, 'reset': 2}, # GPP_I4
]


class AlderLakeGpioPadConfig:
    """
    Represents a single GPIO pad configuration entry as found in vendor BIOS.

    The structure matches the hardware PADCFG registers:
    - DW0: Pad mode, reset config, RX/TX state, output value, interrupt routing
    - DW1: Interrupt config, termination, ownership
    - DW2/DW3: Additional settings (may not always be present)

    Bitfield definitions based on Intel Alder Lake PCH datasheet and intelp2m.
    """

    # DW0 bit definitions (based on Intel PCH datasheet + intelp2m)
    DW0_PADRST_CFG_SHIFT = 30
    DW0_PADRST_CFG_MASK = 0x3 << DW0_PADRST_CFG_SHIFT

    DW0_RXPADSTSEL_SHIFT = 29
    DW0_RXPADSTSEL_MASK = 0x1 << DW0_RXPADSTSEL_SHIFT

    DW0_RXRAW1_SHIFT = 28
    DW0_RXRAW1_MASK = 0x1 << DW0_RXRAW1_SHIFT

    DW0_RXEVCFG_SHIFT = 25
    DW0_RXEVCFG_MASK = 0x3 << DW0_RXEVCFG_SHIFT

    DW0_PREGFRXSEL_SHIFT = 24
    DW0_PREGFRXSEL_MASK = 0x1 << DW0_PREGFRXSEL_SHIFT

    DW0_RXINV_SHIFT = 23
    DW0_RXINV_MASK = 0x1 << DW0_RXINV_SHIFT

    DW0_RXTXENCFG_SHIFT = 21
    DW0_RXTXENCFG_MASK = 0x3 << DW0_RXTXENCFG_SHIFT

    DW0_GPIROUTIOXAPIC_SHIFT = 20
    DW0_GPIROUTIOXAPIC_MASK = 0x1 << DW0_GPIROUTIOXAPIC_SHIFT

    DW0_GPIROUTSCI_SHIFT = 19
    DW0_GPIROUTSCI_MASK = 0x1 << DW0_GPIROUTSCI_SHIFT

    DW0_GPIROUTSMI_SHIFT = 18
    DW0_GPIROUTSMI_MASK = 0x1 << DW0_GPIROUTSMI_SHIFT

    DW0_GPIROUTNMI_SHIFT = 17
    DW0_GPIROUTNMI_MASK = 0x1 << DW0_GPIROUTNMI_SHIFT

    DW0_PMODE_SHIFT = 10
    DW0_PMODE_MASK = 0xF << DW0_PMODE_SHIFT  # 4 bits for mode (0-7 used)

    DW0_GPIORXTXDIS_SHIFT = 8
    DW0_GPIORXTXDIS_MASK = 0x3 << DW0_GPIORXTXDIS_SHIFT

    DW0_GPIORXSTATE_SHIFT = 1
    DW0_GPIORXSTATE_MASK = 0x1 << DW0_GPIORXSTATE_SHIFT

    DW0_GPIOTXSTATE_SHIFT = 0
    DW0_GPIOTXSTATE_MASK = 0x1 << DW0_GPIOTXSTATE_SHIFT

    # DW1 bit definitions
    DW1_PADTOL_SHIFT = 25
    DW1_PADTOL_MASK = 0x1 << DW1_PADTOL_SHIFT

    DW1_IOSTANDBY_SHIFT = 14
    DW1_IOSTANDBY_MASK = 0xF << DW1_IOSTANDBY_SHIFT

    DW1_TERM_SHIFT = 10
    DW1_TERM_MASK = 0xF << DW1_TERM_SHIFT

    DW1_IOSTANDBYTERM_SHIFT = 8
    DW1_IOSTANDBYTERM_MASK = 0x3 << DW1_IOSTANDBYTERM_SHIFT

    DW1_INTSEL_SHIFT = 0
    DW1_INTSEL_MASK = 0xFF << DW1_INTSEL_SHIFT

    def __init__(self, raw_bytes: bytes, offset: int = 0):
        """
        Parse a GPIO pad configuration from raw bytes.

        Args:
            raw_bytes: Raw binary data containing the pad config
            offset: Offset into raw_bytes where this pad config starts
        """
        if len(raw_bytes) < offset + 8:
            raise ValueError("Insufficient data for GPIO pad config")

        # Most vendor BIOS tables store at minimum DW0 and DW1
        self.dw0 = struct.unpack('<I', raw_bytes[offset:offset+4])[0]
        self.dw1 = struct.unpack('<I', raw_bytes[offset+4:offset+8])[0]

        # DW2/DW3 may be present in some implementations
        self.dw2 = 0
        self.dw3 = 0
        if len(raw_bytes) >= offset + 16:
            self.dw2 = struct.unpack('<I', raw_bytes[offset+8:offset+12])[0]
            self.dw3 = struct.unpack('<I', raw_bytes[offset+12:offset+16])[0]

    def get_pad_mode(self) -> PadMode:
        """Extract pad mode from DW0[12:10]"""
        mode_val = (self.dw0 & self.DW0_PMODE_MASK) >> self.DW0_PMODE_SHIFT
        try:
            return PadMode(mode_val)
        except ValueError:
            return PadMode.GPIO

    def get_rxtx_config(self) -> RxTxConfig:
        """Extract RX/TX buffer configuration from DW0[9:8]"""
        val = (self.dw0 & self.DW0_GPIORXTXDIS_MASK) >> self.DW0_GPIORXTXDIS_SHIFT
        try:
            return RxTxConfig(val)
        except ValueError:
            return RxTxConfig.TX_RX_ENABLE

    def get_direction(self) -> PadDirection:
        """Get GPIO direction (only meaningful in GPIO mode)"""
        rxtx = self.get_rxtx_config()

        # TX enabled, RX disabled = Output
        if rxtx == RxTxConfig.RX_DISABLE:
            return PadDirection.OUTPUT
        # Otherwise input (or bidirectional, treat as input)
        else:
            return PadDirection.INPUT

    def get_output_value(self) -> int:
        """Get output value (0 or 1) for output pads"""
        return 1 if (self.dw0 & self.DW0_GPIOTXSTATE_MASK) else 0

    def get_reset_config(self) -> PadReset:
        """Extract reset domain configuration from DW0[31:30]"""
        reset_val = (self.dw0 & self.DW0_PADRST_CFG_MASK) >> self.DW0_PADRST_CFG_SHIFT
        try:
            return PadReset(reset_val)
        except ValueError:
            return PadReset.PLTRST

    def get_termination(self) -> PadPull:
        """Extract termination/pull configuration from DW1[13:10]"""
        term_val = (self.dw1 & self.DW1_TERM_MASK) >> self.DW1_TERM_SHIFT
        try:
            return PadPull(term_val)
        except ValueError:
            return PadPull.NONE

    def get_trigger_type(self) -> PadTrigger:
        """Extract interrupt trigger type from DW0[27:25]"""
        trig_val = (self.dw0 & self.DW0_RXEVCFG_MASK) >> self.DW0_RXEVCFG_SHIFT
        try:
            return PadTrigger(trig_val)
        except ValueError:
            return PadTrigger.OFF

    def has_interrupt(self) -> bool:
        """Check if pad has interrupt routing enabled"""
        return ((self.dw0 & self.DW0_GPIROUTIOXAPIC_MASK) != 0 or
                (self.dw0 & self.DW0_GPIROUTSCI_MASK) != 0 or
                (self.dw0 & self.DW0_GPIROUTSMI_MASK) != 0 or
                (self.dw0 & self.DW0_GPIROUTNMI_MASK) != 0)

    def get_interrupt_type(self) -> str:
        """Determine interrupt routing type"""
        if self.dw0 & self.DW0_GPIROUTIOXAPIC_MASK:
            return 'APIC'
        elif self.dw0 & self.DW0_GPIROUTSCI_MASK:
            return 'SCI'
        elif self.dw0 & self.DW0_GPIROUTSMI_MASK:
            return 'SMI'
        elif self.dw0 & self.DW0_GPIROUTNMI_MASK:
            return 'NMI'
        return 'NONE'

    def get_rx_invert(self) -> bool:
        """Check if RX is inverted (DW0[23])"""
        return (self.dw0 & self.DW0_RXINV_MASK) != 0

    def validate(self) -> bool:
        """
        Validate this pad configuration looks reasonable.

        Returns:
            True if configuration appears valid
        """
        # Check DW0 and DW1 aren't all zeros or all ones
        if self.dw0 == 0 and self.dw1 == 0:
            return False
        if self.dw0 == 0xFFFFFFFF or self.dw1 == 0xFFFFFFFF:
            return False

        # Issue #1 Fix: Check raw bits directly to avoid Enum masking
        
        # Check pad mode (DW0[12:10]) is in valid range (0-7)
        # The mask is 0x1C00 (0b1110000000000)
        mode_raw = (self.dw0 >> 10) & 0x7  # 3 bits
        # Bit 13 is reserved/unused for mode in this context, but let's check the full nibble if needed
        # Actually DW0_PMODE_MASK is 0xF << 10 (bits 13:10). 
        # Valid modes are 0-7, so bit 13 (value 8) must be 0.
        mode_full_nibble = (self.dw0 >> 10) & 0xF
        if mode_full_nibble > 7:
            return False

        # Check reset config (DW0[31:30]) is in valid range (0-3)
        # 2 bits, so it's always 0-3, but we check for consistency if needed.
        # Actually, all 2-bit values are valid Enum members (PWROK, DEEP, PLTRST, RSMRST).
        # So this check is tautological unless we forbid specific resets for specific modes?
        # For now, just ensuring it's extracted correctly is enough, but let's keep the check structure.
        reset_raw = (self.dw0 >> 30) & 0x3
        
        # Check for reserved bits or impossible combinations
        # Example: If Pad Mode is GPIO (0), Direction cannot be both Input and Output disabled?
        # Actually, TX_DISABLE | RX_DISABLE (0b11) is valid (Hi-Z).
        
        # Heuristic: If DW0 has bits set that are marked as 'Reserved' in datasheet
        # DW0 Mask: (0b1 << 27) | (0b1 << 24) | (0b11 << 21) | (0b1111 << 16) | 0b11111100
        # This mask seems to define *valid* bits?
        # Let's use the inverse check if we trust the mask.
        # The mask in line 84 seems to be "bits that ARE used/valid".
        # DW0_MASK = (0b1 << 27) | (0b1 << 24) | (0b11 << 21) | (0b1111 << 16) | 0b11111100
        # It misses bits 31:30 (Reset), 29:28 (Rx Raw), 25 (RxEv), 10:13 (Mode), etc.
        # The mask definition seems incomplete or specific to a certain register view.
        # Let's rely on the explicit checks for now.

        return True

    def to_dict(self) -> Dict:
        """Convert to dictionary representation"""
        return {
            'dw0': f'0x{self.dw0:08x}',
            'dw1': f'0x{self.dw1:08x}',
            'mode': self.get_pad_mode().name,
            'direction': self.get_direction().name if self.get_pad_mode() == PadMode.GPIO else 'N/A',
            'output_value': self.get_output_value() if self.get_direction() == PadDirection.OUTPUT else None,
            'reset': self.get_reset_config().name,
            'termination': self.get_termination().name,
            'interrupt': self.get_interrupt_type(),
            'trigger': self.get_trigger_type().name if self.has_interrupt() else 'N/A',
            'rx_invert': self.get_rx_invert(),
        }


def get_pad_name(group: str, index: int) -> str:
    if group.startswith('VGPIO'):
        if group == 'VGPIO':
            return f'VGPIO_{index}'
        elif group == 'VGPIO_0':
            return f'VGPIO_USB_{index}'
        elif group == 'VGPIO_PCIE':
            return f'VGPIO_PCIE_{index}'
    return f'{group}{index}'


def resolve_global_pad_name(global_index: int) -> Tuple[str, int]:
    """
    Map a global linear index to a (group, local_index) tuple
    based on the physical layout of the extracted table.
    """
    current_idx = 0

    for group_name, count in ALDERLAKE_S_GROUPS_ORDER:
        if global_index < current_idx + count:
            local_index = global_index - current_idx
            return (group_name, local_index)
        current_idx += count

    return (None, None)


def find_group_for_pad(pad_number: int, community: int) -> Optional[Tuple[str, int]]:
    """Legacy helper."""
    for group_name, info in GPIO_GROUPS.items():
        if info['community'] != community:
            continue

        if info['pad_start'] <= pad_number < info['pad_start'] + info['pad_count']:
            local_index = pad_number - info['pad_start']
            return (group_name, local_index)

    return None


# Known UEFI module names/patterns that typically contain GPIO configuration
# Note: Only verified patterns are included. Unverified FSP GUIDs have been removed.
#       These patterns are derived from:
#       - coreboot util/intelp2m/ source code
#       - Intel FSP documentation
#       - Real BIOS image analysis
GPIO_MODULE_PATTERNS = [
    'Gpio',
    'GPIO',
    'PchInit',
    'PchGpio',
    'SiliconInit',
    'GpioInit',
    'PlatformGpio',
    'PchSmi',
]

KNOWN_FSP_GUIDS = []
