"""Foreground application detection per platform.

Uses ``ctypes`` (Windows: user32) to detect the currently active application
name and window title. Best-effort, returns ``(None, None)`` on any failure.
"""

from __future__ import annotations

import logging
import platform
from typing import Optional

logger = logging.getLogger(__name__)


class ActiveAppDetector:
    """Detects the foreground application and window title.

    Platform support:
        - Windows: Uses ``ctypes`` + ``user32`` (no new dependencies).
        - macOS: Uses ``pyobjc`` (only pulled on macOS).
        - Other: Always returns ``(None, None)``.
    """

    def __init__(self) -> None:
        self._platform = platform.system()
        self._available = self._check_available()

    def _check_available(self) -> bool:
        """Check if platform detection APIs are accessible."""
        if self._platform == "Windows":
            try:
                import ctypes  # noqa: F401

                return True
            except Exception:
                return False
        elif self._platform == "Darwin":
            try:
                import AppKit  # noqa: F401

                return True
            except Exception:
                return False
        return False

    def is_available(self) -> bool:
        """Return True if foreground detection works on this platform."""
        return self._available

    def detect(self) -> tuple[Optional[str], Optional[str]]:
        """Detect the current foreground app and window title.

        Returns:
            A tuple ``(app_name, window_title)`` or ``(None, None)`` on failure.
        """
        if not self._available:
            return None, None

        try:
            if self._platform == "Windows":
                return self._detect_windows()
            elif self._platform == "Darwin":
                return self._detect_macos()
        except Exception:
            logger.debug("Foreground app detection failed", exc_info=True)

        return None, None

    def _detect_windows(self) -> tuple[Optional[str], Optional[str]]:
        """Detect foreground app on Windows using ctypes + user32.

        Retrieves the window title (up to 512 chars) and the process name
        from the foreground window.
        """
        import ctypes
        from ctypes import wintypes

        # Get handle to foreground window
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None, None

        # Get window title
        length = 512
        title_buf = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, title_buf, length)
        window_title = title_buf.value or None

        # Get process ID and process name
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # Open process and get its executable name
        # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return window_title, None

        try:
            exe_buf = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(260)
            kernel32.QueryFullProcessImageNameW(handle, 0, exe_buf, ctypes.byref(size))
            full_path = exe_buf.value or ""
            # Extract just the executable name
            app_name = full_path.rsplit("\\", 1)[-1] if "\\" in full_path else full_path
        except Exception:
            app_name = None
        finally:
            kernel32.CloseHandle(handle)

        return app_name, window_title

    def _detect_macos(self) -> tuple[Optional[str], Optional[str]]:
        """Detect foreground app on macOS using AppKit.

        Requires pyobjc (only available on macOS).
        """
        try:
            from AppKit import NSWorkspace  # noqa: PLC0415

            workspace = NSWorkspace.sharedWorkspace()
            app = workspace.frontmostApplication()
            if app is None:
                return None, None

            app_name = app.localizedName() or None
            # macOS doesn't provide window title through this simple path
            # without additional accessibility APIs; return app name only
            return app_name, None
        except Exception:
            logger.debug("macOS foreground detection failed", exc_info=True)
            return None, None
