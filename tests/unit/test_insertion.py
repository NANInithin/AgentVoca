"""Unit tests for keyboard and clipboard insertion strategies.

Tests cover strategy instantiation, the ``insert()`` and ``undo_last()``
methods, and platform helper detection using mocked dependencies.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentvoca.config.schema import InsertionConfig
from agentvoca.insertion.clipboard import ClipboardInsertionStrategy
from agentvoca.insertion.keyboard import KeyboardInsertionStrategy
from agentvoca.insertion.platform.macos import is_macos
from agentvoca.insertion.platform.macos import paste_modifier_key as mac_paste_key
from agentvoca.insertion.platform.windows import is_windows
from agentvoca.insertion.platform.windows import paste_modifier_key as win_paste_key


class TestKeyboardInsertion:
    """Tests for KeyboardInsertionStrategy."""

    def test_get_name(self) -> None:
        config = InsertionConfig(strategy="keyboard")
        strategy = KeyboardInsertionStrategy(config)
        assert strategy.get_name() == "keyboard"

    def test_is_available_on_windows(self) -> None:
        config = InsertionConfig(strategy="keyboard")
        strategy = KeyboardInsertionStrategy(config)
        # On Windows, it should be available
        assert strategy.is_available() is True

    @patch("agentvoca.insertion.keyboard.pyautogui.typewrite")
    async def test_insert_success(self, mock_typewrite: MagicMock) -> None:
        config = InsertionConfig(strategy="keyboard")
        strategy = KeyboardInsertionStrategy(config)

        result = await strategy.insert("hello world")

        assert result.success is True
        assert result.method_used == "keyboard"
        mock_typewrite.assert_called_once_with(
            "hello world", interval=pytest.approx(0.0, abs=0.001)
        )

    @patch(
        "agentvoca.insertion.keyboard.pyautogui.typewrite",
        side_effect=RuntimeError("Mock failure"),
    )
    async def test_insert_failure(self, mock_typewrite: MagicMock) -> None:
        config = InsertionConfig(strategy="keyboard")
        strategy = KeyboardInsertionStrategy(config)

        result = await strategy.insert("hello")

        assert result.success is False
        assert result.method_used == "keyboard"
        assert "Mock failure" in (result.error or "")

    @patch("agentvoca.insertion.keyboard.pyautogui.hotkey")
    async def test_undo_last(self, mock_hotkey: MagicMock) -> None:
        config = InsertionConfig(strategy="keyboard")
        strategy = KeyboardInsertionStrategy(config)

        result = await strategy.undo_last()
        assert result is True

    async def test_insert_empty_string(self) -> None:
        config = InsertionConfig(strategy="keyboard")
        strategy = KeyboardInsertionStrategy(config)

        result = await strategy.insert("")
        assert result.success is True  # Empty text is trivially inserted


class TestClipboardInsertion:
    """Tests for ClipboardInsertionStrategy."""

    def test_get_name(self) -> None:
        config = InsertionConfig(strategy="clipboard")
        strategy = ClipboardInsertionStrategy(config)
        assert strategy.get_name() == "clipboard"

    @patch("agentvoca.insertion.clipboard.pyperclip.copy")
    @patch("agentvoca.insertion.clipboard.pyautogui.hotkey")
    async def test_insert_success(self, mock_hotkey: MagicMock, mock_copy: MagicMock) -> None:
        config = InsertionConfig(strategy="clipboard")
        strategy = ClipboardInsertionStrategy(config)

        result = await strategy.insert("test text")

        assert result.success is True
        assert result.method_used == "clipboard"
        mock_copy.assert_called_once_with("test text")
        mock_hotkey.assert_called_once()

    @patch(
        "agentvoca.insertion.clipboard.pyperclip.copy",
        side_effect=RuntimeError("Clipboard error"),
    )
    async def test_insert_failure(self, mock_copy: MagicMock) -> None:
        config = InsertionConfig(strategy="clipboard")
        strategy = ClipboardInsertionStrategy(config)

        result = await strategy.insert("test")

        assert result.success is False
        assert result.method_used == "clipboard"
        assert "Clipboard error" in (result.error or "")

    async def test_insert_empty_string(self) -> None:
        config = InsertionConfig(strategy="clipboard")
        strategy = ClipboardInsertionStrategy(config)

        result = await strategy.insert("")
        assert result.success is True


class TestPlatformHelpers:
    """Tests for platform detection utilities."""

    def test_is_macos(self) -> None:
        # is_macos returns True only on Darwin
        result = is_macos()
        import platform

        assert result == (platform.system() == "Darwin")

    def test_is_windows(self) -> None:
        result = is_windows()
        import platform

        assert result == (platform.system() == "Windows")

    def test_mac_paste_key(self) -> None:
        assert mac_paste_key() == "cmd"

    def test_win_paste_key(self) -> None:
        assert win_paste_key() == "ctrl"
