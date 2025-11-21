#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
Alder Lake / Z690 GPIO platform definitions.

This module defines the GPIO pad configuration structures and metadata
specific to Intel Alder Lake platforms (12th gen Core, Z690/H670/B660 chipsets).
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
    """Termination/Pull resistor configuration"""
    NONE = 0
    DN_5K = 1   # Pull-down 5K
    DN_20K = 2  # Pull-down 20K
    UP_1K = 3   # Pull-up 1K
    UP_2K = 4   # Pull-up 2K
    UP_5K = 5   # Pull-up 5K
    UP_20K = 6  # Pull-up 20K
    UP_1K_2K = 7  # Pull-up 1K + 2K
    NATIVE = 8


class PadReset(IntEnum):
    """Reset domain configuration"""
    PWROK = 0    # RSMRST
    DEEP = 1     # Deep sleep reset
    PLTRST = 2   # Platform reset
    RSMRST = 0   # Alias for PWROK


class PadTrigger(IntEnum):
    """Interrupt trigger type"""
    OFF = 0
    EDGE_SINGLE = 1
    EDGE_BOTH = 2
    LEVEL = 3


class PadOwner(IntEnum):
    """Pad ownership"""
    ACPI = 0
    GPIO_DRIVER = 1


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
    """

    # DW0 bit definitions
    DW0_RXPADSTSEL_MASK = 0x3 << 29
    DW0_RXRAW1_MASK = 0x1 << 28
    DW0_RXEVCFG_MASK = 0x3 << 25
    DW0_PREGFRXSEL_MASK = 0x1 << 24
    DW0_RXINV_MASK = 0x1 << 23
    DW0_GPIROUTIOXAPIC_MASK = 0x1 << 20
    DW0_GPIROUTSCI_MASK = 0x1 << 19
    DW0_GPIROUTSMI_MASK = 0x1 << 18
    DW0_GPIROUTNMI_MASK = 0x1 << 17
    DW0_PMODE_MASK = 0xF << 10
    DW0_GPIORXDIS_MASK = 0x1 << 9
    DW0_GPIOTXDIS_MASK = 0x1 << 8
    DW0_GPIORXSTATE_MASK = 0x1 << 1
    DW0_GPIOTXSTATE_MASK = 0x1 << 0

    # DW1 bit definitions
    DW1_PADRSTCFG_MASK = 0x3 << 30
    DW1_INTSEL_MASK = 0xFF << 0
    DW1_TERM_MASK = 0xF << 10

    def __init__(self, raw_bytes: bytes, offset: int = 0):
        if len(raw_bytes) < offset + 8:
            raise ValueError("Insufficient data for GPIO pad config")

        self.dw0 = struct.unpack('<I', raw_bytes[offset:offset+4])[0]
        self.dw1 = struct.unpack('<I', raw_bytes[offset+4:offset+8])[0]

        self.dw2 = 0
        self.dw3 = 0
        if len(raw_bytes) >= offset + 16:
            self.dw2 = struct.unpack('<I', raw_bytes[offset+8:offset+12])[0]
            self.dw3 = struct.unpack('<I', raw_bytes[offset+12:offset+16])[0]

    def get_pad_mode(self) -> PadMode:
        mode_val = (self.dw0 & self.DW0_PMODE_MASK) >> 10
        try:
            return PadMode(mode_val)
        except ValueError:
            return PadMode.GPIO

    def get_direction(self) -> PadDirection:
        tx_disabled = (self.dw0 & self.DW0_GPIOTXDIS_MASK) != 0
        rx_disabled = (self.dw0 & self.DW0_GPIORXDIS_MASK) != 0

        if not tx_disabled and rx_disabled:
            return PadDirection.OUTPUT
        else:
            return PadDirection.INPUT

    def get_output_value(self) -> int:
        return 1 if (self.dw0 & self.DW0_GPIOTXSTATE_MASK) else 0

    def get_reset_config(self) -> PadReset:
        reset_val = (self.dw1 & self.DW1_PADRSTCFG_MASK) >> 30
        try:
            return PadReset(reset_val)
        except ValueError:
            return PadReset.PLTRST

    def get_termination(self) -> PadPull:
        term_val = (self.dw1 & self.DW1_TERM_MASK) >> 10
        try:
            return PadPull(term_val)
        except ValueError:
            return PadPull.NONE

    def has_interrupt(self) -> bool:
        return ((self.dw0 & self.DW0_GPIROUTIOXAPIC_MASK) != 0 or
                (self.dw0 & self.DW0_GPIROUTSCI_MASK) != 0 or
                (self.dw0 & self.DW0_GPIROUTSMI_MASK) != 0 or
                (self.dw0 & self.DW0_GPIROUTNMI_MASK) != 0)

    def get_interrupt_type(self) -> str:
        if self.dw0 & self.DW0_GPIROUTIOXAPIC_MASK:
            return 'APIC'
        elif self.dw0 & self.DW0_GPIROUTSCI_MASK:
            return 'SCI'
        elif self.dw0 & self.DW0_GPIROUTSMI_MASK:
            return 'SMI'
        elif self.dw0 & self.DW0_GPIROUTNMI_MASK:
            return 'NMI'
        return 'NONE'

    def to_dict(self) -> Dict:
        return {
            'dw0': f'0x{self.dw0:08x}',
            'dw1': f'0x{self.dw1:08x}',
            'mode': self.get_pad_mode().name,
            'direction': self.get_direction().name if self.get_pad_mode() == PadMode.GPIO else 'N/A',
            'output_value': self.get_output_value() if self.get_direction() == PadDirection.OUTPUT else None,
            'reset': self.get_reset_config().name,
            'termination': self.get_termination().name,
            'interrupt': self.get_interrupt_type(),
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
GPIO_MODULE_PATTERNS = [
    'Gpio',
    'GPIO',
    'PchInit',
    'PchGpio',
    'SiliconInit',
    'GpioInit',
    'PlatformGpio',
    'PchSmi',
    # Known FSP GUIDs for Alder Lake
    '99C2CA49-5144-41A7-9925-1262C0321238',
    'DE23ACEE-CF55-4FB6-AA77-984AB53DE818',
    '1A425F84-4746-4DD8-86F5-5226AC068BCE',
]

KNOWN_FSP_GUIDS = []
