"""Windows-specific helpers for text insertion.

Provides platform detection, foreground-window tracking so that undo
can target the correct window regardless of current focus, and the
appropriate paste modifier key (Ctrl).
"""

from __future__ import annotations

import ctypes
import logging
import platform

logger = logging.getLogger(__name__)

_PLATFORM = platform.system()


def is_windows() -> bool:
    """Return True if running on Windows."""
    return _PLATFORM == "Windows"


def paste_modifier_key() -> str:
    """Return the paste modifier key for Windows."""
    return "ctrl"


def get_foreground_hwnd() -> int:
    """Return the Win32 handle of the current foreground window, or 0."""
    if not is_windows():
        return 0
    try:
        return int(ctypes.windll.user32.GetForegroundWindow())
    except Exception:
        return 0


def focus_window(hwnd: int) -> bool:
    """Bring a window to the foreground by its handle.

    Uses AttachThreadInput + SetForegroundWindow + BringWindowToTop to
    bypass the focus-stealing restrictions Windows applies since XP.
    Returns True if the call succeeded, False on any error.
    """
    if not is_windows() or not hwnd:
        return False
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        current_tid = kernel32.GetCurrentThreadId()
        target_tid = user32.GetWindowThreadProcessId(hwnd, None)
        # Temporarily attach to the target thread's input queue so that
        # SetForegroundWindow is not silently ignored.
        user32.AttachThreadInput(current_tid, target_tid, True)
        try:
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
        finally:
            user32.AttachThreadInput(current_tid, target_tid, False)
        return True
    except Exception as exc:
        logger.debug("focus_window(%d) failed: %s", hwnd, exc)
        return False
