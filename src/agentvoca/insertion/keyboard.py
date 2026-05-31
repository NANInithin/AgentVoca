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
from agentvoca.insertion.platform.windows import is_windows

logger = logging.getLogger(__name__)


class KeyboardInsertionStrategy(InsertionStrategy):
    """Inserts text character-by-character via keyboard simulation.

    Args:
        config: Insertion configuration block.
    """

    def __init__(self, config: InsertionConfig) -> None:
        self._config = config
        self._last_text: Optional[str] = None

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
        """Attempt to undo the last insertion by sending Ctrl+Z / Cmd+Z.

        Returns:
            True if the undo was sent.
        """
        try:
            modifier = "command" if is_macos() else "ctrl"
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: pyautogui.hotkey(modifier, "z"),
            )
            logger.debug("Sent undo hotkey")
            return True
        except Exception as exc:
            logger.warning("Undo failed: %s", exc)
            return False
