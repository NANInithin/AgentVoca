"""macOS-specific helpers for text insertion.

Provides platform detection, accessibility permission checks, and
the appropriate paste modifier key (Cmd) for macOS.
"""

from __future__ import annotations

import logging
import platform

logger = logging.getLogger(__name__)

_PLATFORM = platform.system()


def is_macos() -> bool:
    """Return True if running on macOS."""
    return _PLATFORM == "Darwin"


def has_accessibility_permissions() -> bool:
    """Check whether the app has accessibility permissions on macOS.

    This is a best-effort check. In v1, it logs a warning if permissions
    are likely missing. A full check requires invoking macOS accessibility
    APIs via pyobjc or similar.

    Returns:
        True if we assume permissions are granted.
    """
    if not is_macos():
        return True

    # PyAutoGUI's locateOnScreen or similar could verify, but for v1
    # we assume the user has granted permissions.
    logger.info("Assuming macOS accessibility permissions are granted")
    return True


def paste_modifier_key() -> str:
    """Return the paste modifier key for macOS.

    Returns:
        ``"cmd"`` for macOS.
    """
    return "cmd"
