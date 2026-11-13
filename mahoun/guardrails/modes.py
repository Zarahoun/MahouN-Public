"""
Guard Mode Configuration
=======================
Defines modes for runtime invariant enforcement.
"""

import os
from enum import Enum


class GuardMode(Enum):
    """Guard enforcement modes"""
    OFF = "OFF"      # No enforcement
    WARN = "WARN"    # Log warnings only
    STRICT = "STRICT"  # Raise exceptions
    AUDIT = "AUDIT"    # Same as STRICT, but with extra logging


def get_guard_mode() -> GuardMode:
    """
    Load guard mode from environment variable.
    
    Environment variable: MAHOUN_GUARD_MODE
    Default: STRICT
    
    Returns:
        GuardMode enum value
    """
    mode_str = os.getenv("MAHOUN_GUARD_MODE", "STRICT").upper()
    
    try:
        return GuardMode(mode_str)
    except ValueError:
        # Invalid mode, default to STRICT
        return GuardMode.STRICT

