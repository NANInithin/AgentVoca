"""Unit tests for keyboard and clipboard insertion strategies.

Tests cover strategy instantiation, the ``insert()`` and ``undo_last()``
methods, and platform helper detection using mocked dependencies.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PySide6 import QtCore, QtWidgets

from agentvoca.config.schema import InsertionConfig
from agentvoca.insertion.clipboard import ClipboardInsertionStrategy
from agentvoca.insertion.clipboard_snapshot import _ClipboardBridge
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
        assert result is False
        mock_hotkey.assert_not_called()

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

    @patch("agentvoca.insertion.clipboard.restore_if_ours", new_callable=AsyncMock)
    @patch("agentvoca.insertion.clipboard.snapshot", new_callable=AsyncMock)
    @patch("agentvoca.insertion.clipboard.pyperclip.copy")
    @patch("agentvoca.insertion.clipboard.pyautogui.hotkey")
    async def test_insert_success(
        self,
        mock_hotkey: MagicMock,
        mock_copy: MagicMock,
        mock_snapshot: AsyncMock,
        mock_restore: AsyncMock,
    ) -> None:
        config = InsertionConfig(strategy="clipboard")
        strategy = ClipboardInsertionStrategy(config)
        mock_snapshot.return_value = {"text/html": b"<b>old</b>"}

        result = await strategy.insert("test text")

        assert result.success is True
        assert result.method_used == "clipboard"
        mock_copy.assert_called_once_with("test text")
        mock_hotkey.assert_called_once()
        mock_restore.assert_awaited_once_with("test text", {"text/html": b"<b>old</b>"})

    @patch("agentvoca.insertion.clipboard.snapshot", new_callable=AsyncMock)
    @patch(
        "agentvoca.insertion.clipboard.pyperclip.copy",
        side_effect=RuntimeError("Clipboard error"),
    )
    async def test_insert_failure(self, mock_copy: MagicMock, mock_snapshot: AsyncMock) -> None:
        config = InsertionConfig(strategy="clipboard")
        strategy = ClipboardInsertionStrategy(config)
        mock_snapshot.return_value = {}

        result = await strategy.insert("test")

        assert result.success is False
        assert result.method_used == "clipboard"
        assert "Clipboard error" in (result.error or "")

    async def test_insert_empty_string(self) -> None:
        config = InsertionConfig(strategy="clipboard")
        strategy = ClipboardInsertionStrategy(config)

        result = await strategy.insert("")
        assert result.success is True

    def test_clipboard_snapshot_restores_all_formats_only_when_still_ours(self) -> None:
        from concurrent.futures import Future

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        clipboard = app.clipboard()
        bridge = _ClipboardBridge()
        original = QtCore.QMimeData()
        original.setText("original")
        original.setHtml("<b>original</b>")
        clipboard.setMimeData(original)
        captured: Future = Future()
        bridge._execute("snapshot", None, captured)
        formats = captured.result()
        assert "text/html" in formats

        clipboard.setText("dictation")
        restored: Future = Future()
        bridge._execute("restore", ("dictation", formats), restored)
        assert restored.result() is True
        assert clipboard.mimeData().html() == "<b>original</b>"

        clipboard.setText("new user copy")
        skipped: Future = Future()
        bridge._execute("restore", ("dictation", formats), skipped)
        assert skipped.result() is False
        assert clipboard.text() == "new user copy"


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
        assert mac_paste_key() == "command"

    def test_win_paste_key(self) -> None:
        assert win_paste_key() == "ctrl"
