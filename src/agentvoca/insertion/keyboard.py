"""Keyboard insertion strategy.

Types text into the active application using platform keyboard simulation
via pyautogui.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import pyautogui

from agentvoca.config.schema import InsertionConfig
from agentvoca.core.types import InsertionResult
from agentvoca.insertion.base import InsertionStrategy
from agentvoca.insertion.platform.macos import is_macos
from agentvoca.insertion.platform.windows import focus_window, get_foreground_hwnd, is_windows

logger = logging.getLogger(__name__)


class KeyboardInsertionStrategy(InsertionStrategy):
    """Inserts text character-by-character via keyboard simulation.

    Args:
        config: Insertion configuration block.
    """

    def __init__(self, config: InsertionConfig) -> None:
        self._config = config
        self._last_text: Optional[str] = None
        # Win32 handle of the window that received the last insertion.
        # Saved so undo_last() can refocus the correct window even if the
        # user switched focus before pressing the undo hotkey.
        self._last_hwnd: int = 0

        # PyAutoGUI safety settings
        pyautogui.FAILSAFE = True
        # Duration between key presses (seconds)
        self._type_interval = max(0.001, config.delay_between_chars_ms / 1000.0)

    def get_name(self) -> str:
        return "keyboard"

    def is_available(self) -> bool:
        """Return True if we can simulate keyboard on this platform."""
        if is_macos():
            from agentvoca.insertion.platform.macos import (
                has_accessibility_permissions,  # noqa: PLC0415
            )

            return has_accessibility_permissions()
        if is_windows():
            return True
        # Linux or other — best effort
        return True

    async def insert(self, text: str) -> InsertionResult:
        """Type the text at the current cursor position.

        Args:
            text: The text to insert.

        Returns:
            ``InsertionResult`` indicating success or failure.
        """
        if not text:
            return InsertionResult(success=True, method_used="keyboard")

        # Save the focused window NOW before any key events are sent.
        # undo_last() needs this handle to refocus the correct window.
        self._last_hwnd = get_foreground_hwnd()

        # pyautogui.typewrite() only handles ASCII keystrokes and silently drops
        # newlines. Use clipboard paste for non-ASCII or multi-line text so that
        # formatted output (numbered lists, paragraphs) arrives intact.
        if not text.isascii() or "\n" in text:
            logger.debug("Non-ASCII text detected — using clipboard for insertion")
            from agentvoca.insertion.clipboard import ClipboardInsertionStrategy  # noqa: PLC0415

            return await ClipboardInsertionStrategy(self._config).insert(text)

        self._last_text = text

        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: pyautogui.typewrite(text, interval=self._type_interval),
            )
            logger.debug("Inserted %d chars via keyboard", len(text))
            return InsertionResult(success=True, method_used="keyboard")
        except Exception as exc:
            logger.warning("Keyboard insertion failed: %s", exc)
            return InsertionResult(
                success=False,
                method_used="keyboard",
                error=str(exc),
            )

    async def undo_last(self) -> bool:
        """Remove the last inserted text.

        Strategy (in order):
        1. Refocus the window that received the insertion (using its saved
           Win32 handle) so the keystrokes go to the right place even if
           the user switched focus after dictating.
        2. Send Backspace × len(last_text) to remove exactly what was typed.
           This is more reliable than Ctrl+Z because it does not depend on
           the target app's undo stack or undo support.
        3. Fall back to Ctrl+Z when the inserted text length is unknown
           (e.g. clipboard path or non-ASCII text).
        """
        count = len(self._last_text) if self._last_text else 0
        hwnd = self._last_hwnd
        loop = asyncio.get_running_loop()

        try:
            # Step 1: refocus the insertion window on Windows.
            if hwnd and is_windows():
                await loop.run_in_executor(None, lambda: focus_window(hwnd))
                # Brief pause so the window activation settles before we type.
                await asyncio.sleep(0.08)

            # Step 2: remove the text.
            if count > 0:
                await loop.run_in_executor(
                    None,
                    lambda: pyautogui.press("backspace", presses=count, interval=0.0, _pause=False),
                )
                logger.debug("Undid %d chars via backspace", count)
                self._last_text = None
            else:
                # Fallback: Ctrl+Z / Cmd+Z for clipboard-inserted text.
                modifier = "command" if is_macos() else "ctrl"
                await loop.run_in_executor(None, lambda: pyautogui.hotkey(modifier, "z"))
                logger.debug("Sent undo hotkey (fallback — text length unknown)")

            return True
        except Exception as exc:
            logger.warning("Undo failed: %s", exc)
            return False
