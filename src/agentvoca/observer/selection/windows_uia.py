"""Windows UI Automation selection reader (v0.4.0, OBS-18).

Reads the user's current text selection via ``IUIAutomationTextPattern``
on the foreground element. NEVER touches the clipboard, NEVER injects
keystrokes — that is the whole point of choosing UIA over the
``Ctrl+C`` / clipboard approach (D5).

Threading
---------
One long-lived ``observer-selection`` thread, COM initialised once
via ``CoInitializeEx(COINIT_APARTMENTTHREADED)``. Per-call threads
would pay COM init every time and risk apartment mismatches (RK5).
The hard ``timeout_ms`` cap is enforced via a single-worker
``ThreadPoolExecutor`` + ``future.result(timeout=…)``; on
``TimeoutError`` we return None and let the caller fall back to
OCR-rect.
"""

from __future__ import annotations

import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Optional

from agentvoca.context.active_app import ActiveAppDetector
from agentvoca.observer.models import Selection
from agentvoca.observer.selection.base import SelectionReader

logger = logging.getLogger(__name__)

# Threshold for UIA calls: a slow app or hung window must not block
# the capture thread. 250 ms mirrors the spec.
_DEFAULT_TIMEOUT_MS = 250

# Pattern ID from IUIAutomation: TextPattern = 10014.
_UIA_TextPatternId = 10014

# COINIT_APARTMENTTHREADED = 0x2
_COINIT_APARTMENTTHREADED = 0x2


class WindowsUIASelectionReader(SelectionReader):
    """Read selection via UI Automation TextPattern on the focused element.

    Args:
        max_chars: Truncate the selection text to at most this many
            characters. Set ``truncated=True`` on the result when cut.
        active_app: Optional detector for app name + window title, so
            the result carries foreground context.
        timeout_ms: Default per-call timeout. RK4 — some apps hang.
    """

    def __init__(
        self,
        max_chars: int = 4000,
        active_app: Optional[ActiveAppDetector] = None,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    ) -> None:
        self._max_chars = max_chars
        self._active_app = active_app
        self._timeout_ms = timeout_ms
        # The executor is created lazily on first call so the
        # Windows-only comtypes dependency is not paid at import time
        # on macOS/Linux (the registry never registers the UIA
        # reader there).
        self._executor: Optional[ThreadPoolExecutor] = None
        # Track which foreground app names we have already logged a
        # timeout for, so a slow app does not flood DEBUG output.
        self._timed_out_apps: set[str] = set()
        self._timed_out_lock = threading.Lock()
        # COM apartment is per-thread; the worker thread inits once.
        self._com_inited = False
        self._com_lock = threading.Lock()
        # Availability is decided on first call (a working UIA env is
        # the common case on Windows).
        self._checked_availability: bool = False
        self._available: bool = False

    def is_available(self) -> bool:
        """True if UIA is importable on this platform.

        On non-Windows the constructor never gets called (the
        registry only resolves ``windows_uia`` on ``sys_platform ==
        'win32'``); this method exists for the ABC contract.
        """
        if sys.platform != "win32":
            return False
        if not self._checked_availability:
            try:
                import comtypes  # noqa: F401, PLC0415

                self._available = True
            except Exception:
                self._available = False
            self._checked_availability = True
        return self._available

    def read_selection(self, timeout_ms: int = _DEFAULT_TIMEOUT_MS) -> Optional[Selection]:
        if not self.is_available():
            return None
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="observer-selection"
            )
        timeout_s = (timeout_ms if timeout_ms is not None else self._timeout_ms) / 1000.0
        future = self._executor.submit(self._read_sync)
        try:
            return future.result(timeout=timeout_s)
        except FuturesTimeout:
            self._log_timeout()
            return None
        except Exception:
            logger.debug("UIA read_selection raised", exc_info=True)
            return None

    def _read_sync(self) -> Optional[Selection]:
        """The actual UIA call, on a worker thread with COM init."""
        with self._com_lock:
            if not self._com_inited:
                self._init_com()
        try:
            text = self._get_text()
        except Exception:
            self._log_timeout()
            return None
        if not text or not text.strip():
            return None
        truncated = len(text) > self._max_chars
        if truncated:
            text = text[: self._max_chars]
        app_name: Optional[str] = None
        window_title: Optional[str] = None
        if self._active_app is not None:
            try:
                app_name, window_title = self._active_app.detect()
            except Exception:
                logger.debug("active-app detect failed in UIA read", exc_info=True)
        return Selection(
            text=text,
            method="uia",
            app_name=app_name,
            window_title=window_title,
            truncated=truncated,
        )

    def _init_com(self) -> None:
        """Initialise COM as apartment-threaded for this worker.

        Idempotent: a second call on the same thread is a no-op.
        """
        try:
            import ctypes

            ctypes.windll.ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
            self._com_inited = True
        except Exception:
            logger.debug("COM init failed in UIA reader", exc_info=True)
            self._com_inited = False

    def _get_text(self) -> Optional[str]:
        """Call into UIA. Returns the selected text, or None on failure."""
        try:
            import comtypes  # noqa: PLC0415
            from comtypes import GUID  # noqa: PLC0415
            from comtypes.client import CreateObject  # noqa: PLC0415
        except Exception as exc:
            logger.debug("UIA: comtypes import failed: %s", exc)
            self._available = False
            return None

        # IUIAutomation interface ID and TextPattern.
        IUIAutomation_IID = GUID("{30CBE57D-9FB4-11D2-9268-00C04C796984}")
        UIA_TextPatternId = _UIA_TextPatternId

        try:
            automation = CreateObject(
                comtypes.CoCreateInstance(
                    comtypes.client.GetModule(
                        ("{30CBE57D-9FB4-11D2-9268-00C04C796984}", 1, 0)
                    ).IUIAutomation,
                    interface=IUIAutomation_IID,
                )
            )
        except Exception as exc:
            logger.debug("UIA: CoCreateInstance failed: %s", exc)
            self._available = False
            return None

        try:
            focused = automation.GetFocusedElement()
        except Exception as exc:
            logger.debug("UIA: GetFocusedElement failed: %s", exc)
            return None
        if focused is None:
            return None
        try:
            pattern = focused.GetCurrentPattern(UIA_TextPatternId)
        except Exception as exc:
            logger.debug("UIA: GetCurrentPattern failed: %s", exc)
            return None
        if pattern is None:
            return None
        try:
            selection = pattern.GetSelection()
        except Exception as exc:
            logger.debug("UIA: GetSelection failed: %s", exc)
            return None
        if selection is None:
            return None
        try:
            length = selection.Length
        except Exception as exc:
            logger.debug("UIA: Length failed: %s", exc)
            return None
        if not length:
            return None
        # Pull the first range only — multi-range selection is rare
        # and not worth a UIA round-trip per range.
        try:
            text_range = selection.GetTextElement(0)
        except Exception as exc:
            logger.debug("UIA: GetTextElement failed: %s", exc)
            return None
        if text_range is None:
            return None
        try:
            return str(text_range.GetText(-1))  # -1 = no limit; we cap below
        except Exception as exc:
            logger.debug("UIA: GetText failed: %s", exc)
            return None

    def _log_timeout(self) -> None:
        """Log a timeout once per foreground app (RK4)."""
        app_name = None
        if self._active_app is not None:
            try:
                app_name, _ = self._active_app.detect()
            except Exception:
                pass
        if app_name is None:
            app_name = "<unknown>"
        with self._timed_out_lock:
            if app_name in self._timed_out_apps:
                return
            self._timed_out_apps.add(app_name)
        logger.debug("UIA read_selection timed out for app %s", app_name)
