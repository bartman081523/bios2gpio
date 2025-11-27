#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""Platform package initialization"""

from .alderlake import (
    AlderLakeGpioPadConfig,
    GPIO_GROUPS,
    PadMode,
    PadDirection,
    PadPull,
    PadReset,
    get_pad_name,
    find_group_for_pad,
    GPIO_MODULE_PATTERNS,
)

__all__ = [
    'AlderLakeGpioPadConfig',
    'GPIO_GROUPS',
    'PadMode',
    'PadDirection',
    'PadPull',
    'PadReset',
    'get_pad_name',
    'find_group_for_pad',
    'GPIO_MODULE_PATTERNS',
]
