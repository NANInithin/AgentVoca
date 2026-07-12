"""Clipboard insertion strategy.

Writes text to the system clipboard and sends the paste hotkey
(Ctrl+V on Windows, Cmd+V on macOS).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import pyautogui
import pyperclip

from agentvoca.config.schema import InsertionConfig
from agentvoca.core.types import InsertionResult
from agentvoca.insertion._executor import get_input_executor
from agentvoca.insertion.base import InsertionStrategy
from agentvoca.insertion.platform.macos import is_macos

logger = logging.getLogger(__name__)


class ClipboardInsertionStrategy(InsertionStrategy):
    """Inserts text by writing to clipboard and sending paste hotkey.

    Args:
        config: Insertion configuration block.
    """

    def __init__(self, config: InsertionConfig) -> None:
        self._config = config
        self._last_text: Optional[str] = None

    def get_name(self) -> str:
        return "clipboard"

    def is_available(self) -> bool:
        """Clipboard is always available on supported platforms."""
        try:
            pyperclip.copy("")
            return True
        except Exception:
            return False

    async def insert(self, text: str) -> InsertionResult:
        """Write ``text`` to clipboard and send paste hotkey.

        Args:
            text: The text to insert.

        Returns:
            ``InsertionResult`` indicating success or failure.
        """
        if not text:
            return InsertionResult(success=True, method_used="clipboard")

        self._last_text = text

        try:
            # Write to clipboard
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(get_input_executor(), lambda: pyperclip.copy(text))
            # Allow clipboard to settle
            await asyncio.sleep(0.05)

            # Send paste hotkey
            modifier = "command" if is_macos() else "ctrl"
            await asyncio.get_running_loop().run_in_executor(
                get_input_executor(), lambda: pyautogui.hotkey(modifier, "v")
            )

            logger.debug("Inserted %d chars via clipboard", len(text))
            return InsertionResult(success=True, method_used="clipboard")

        except Exception as exc:
            logger.warning("Clipboard insertion failed: %s", exc)
            return InsertionResult(
                success=False,
                method_used="clipboard",
                error=str(exc),
            )

    async def undo_last(self) -> bool:
        """Undo clipboard paste by sending Ctrl+Z / Cmd+Z.

        Returns:
            True if the undo was sent.
        """
        try:
            modifier = "command" if is_macos() else "ctrl"
            await asyncio.get_running_loop().run_in_executor(
                get_input_executor(), lambda: pyautogui.hotkey(modifier, "z")
            )
            return True
        except Exception as exc:
            logger.warning("Clipboard undo failed: %s", exc)
            return False
