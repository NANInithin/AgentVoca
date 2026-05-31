"""Windows-specific helpers for text insertion.

Provides platform detection, UAC note, and the appropriate paste
modifier key (Ctrl) for Windows.
"""

from __future__ import annotations

import logging
import platform

logger = logging.getLogger(__name__)

_PLATFORM = platform.system()


def is_windows() -> bool:
    """Return True if running on Windows."""
    return _PLATFORM == "Windows"


def paste_modifier_key() -> str:
    """Return the paste modifier key for Windows.

    Returns:
        ``"ctrl"`` for Windows.
    """
    return "ctrl"
