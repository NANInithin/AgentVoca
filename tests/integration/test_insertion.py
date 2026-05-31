"""Integration tests for insertion strategies via the full pipeline.

Verifies that keyboard and clipboard strategies insert text correctly
through the orchestrator, using mock providers for ASR and cleanup.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional
from unittest.mock import MagicMock, patch

import pytest

from agentvoca.asr.base import ASRProvider
from agentvoca.cleanup.base import CleanupProvider
from agentvoca.config.schema import ASRConfig, CleanupConfig, FullConfig, InsertionConfig
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import InsertionCompleteEvent, RecordingStoppedEvent
from agentvoca.core.orchestrator import Orchestrator
from agentvoca.core.registry import ProviderRegistry
from agentvoca.core.types import ASRContext, CleanupContext, TranscriptSegment

# ── Minimal mock providers ──────────────────────────────────────────


class _MockASR(ASRProvider):
    def __init__(self, config: ASRConfig) -> None:
        self._config = config

    def get_name(self) -> str:
        return "mock_asr"

    def is_available(self) -> bool:
        return True

    async def transcribe_audio(
        self, audio_bytes: bytes, sample_rate: int, context: Optional[ASRContext] = None
    ) -> TranscriptSegment:
        return TranscriptSegment(text="hello world", is_final=True)

    async def stream_transcribe(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> AsyncIterator[TranscriptSegment]:
        yield TranscriptSegment(text="hello world", is_final=True)


class _MockCleanup(CleanupProvider):
    def __init__(self, config: CleanupConfig) -> None:
        self._config = config

    def get_name(self) -> str:
        return "mock_cleanup"

    def is_available(self) -> bool:
        return True

    async def rewrite(self, transcript: str, context: Optional[CleanupContext] = None) -> str:
        return transcript


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def audio_bytes() -> bytes:
    return b"\x00" * 16000 * 4  # 1 second of silent float32


@pytest.fixture
def recording_event(audio_bytes: bytes) -> RecordingStoppedEvent:
    return RecordingStoppedEvent(audio_bytes=audio_bytes, duration_ms=1000, sample_rate=16000)


def _make_registry(insertion_cls: type) -> ProviderRegistry:
    reg = ProviderRegistry()
    reg.register_asr("mock_asr", _MockASR)
    reg.register_cleanup("mock_cleanup", _MockCleanup)
    reg.register_insertion("keyboard", insertion_cls)
    return reg


def _make_config(strategy: str = "keyboard") -> FullConfig:
    return FullConfig(
        asr=ASRConfig(provider="mock_asr"),
        cleanup=CleanupConfig(provider="mock_cleanup"),
        insertion=InsertionConfig(strategy=strategy, clipboard_fallback=False),
    )


# ── Tests ────────────────────────────────────────────────────────────


class TestKeyboardInsertion:
    """Keyboard strategy inserts ASCII text via pyautogui.typewrite."""

    @patch("agentvoca.insertion.keyboard.pyautogui.typewrite")
    async def test_ascii_text_uses_typewrite(
        self, mock_typewrite: MagicMock, recording_event: RecordingStoppedEvent
    ) -> None:
        bus = EventBus()
        registry = _make_registry(
            __import__(
                "agentvoca.insertion.keyboard", fromlist=["KeyboardInsertionStrategy"]
            ).KeyboardInsertionStrategy
        )
        orch = Orchestrator(config=_make_config(), registry=registry, event_bus=bus)
        await orch.start()

        events: list[InsertionCompleteEvent] = []
        bus.subscribe(InsertionCompleteEvent, events.append)

        bus.publish(recording_event)
        await asyncio.sleep(0.2)

        mock_typewrite.assert_called_once()
        assert any(e.success for e in events)

        await orch.stop()

    @patch("agentvoca.insertion.clipboard.pyperclip.copy")
    @patch("agentvoca.insertion.clipboard.pyautogui.hotkey")
    async def test_unicode_text_uses_clipboard(
        self, mock_hotkey: MagicMock, mock_copy: MagicMock
    ) -> None:
        """Non-ASCII text bypasses typewrite and goes via clipboard."""
        from agentvoca.config.schema import InsertionConfig
        from agentvoca.insertion.keyboard import KeyboardInsertionStrategy

        config = InsertionConfig(strategy="keyboard")
        strategy = KeyboardInsertionStrategy(config)

        result = await strategy.insert("నమస్కారం")  # Telugu

        assert result.success is True
        assert result.method_used == "clipboard"
        mock_copy.assert_called_once_with("నమస్కారం")

    @patch("agentvoca.insertion.clipboard.pyperclip.copy")
    @patch("agentvoca.insertion.clipboard.pyautogui.hotkey")
    async def test_multiline_text_uses_clipboard(
        self, mock_hotkey: MagicMock, mock_copy: MagicMock
    ) -> None:
        """Text containing newlines bypasses typewrite and goes via clipboard."""
        from agentvoca.config.schema import InsertionConfig
        from agentvoca.insertion.keyboard import KeyboardInsertionStrategy

        config = InsertionConfig(strategy="keyboard")
        strategy = KeyboardInsertionStrategy(config)
        text = "1. First\n2. Second\n3. Third"

        result = await strategy.insert(text)

        assert result.success is True
        assert result.method_used == "clipboard"
        mock_copy.assert_called_once_with(text)


class TestClipboardInsertion:
    """Clipboard strategy writes to clipboard and sends paste hotkey."""

    @patch("agentvoca.insertion.clipboard.pyperclip.copy")
    @patch("agentvoca.insertion.clipboard.pyautogui.hotkey")
    async def test_insert_copies_and_pastes(
        self, mock_hotkey: MagicMock, mock_copy: MagicMock
    ) -> None:
        from agentvoca.config.schema import InsertionConfig
        from agentvoca.insertion.clipboard import ClipboardInsertionStrategy

        config = InsertionConfig(strategy="clipboard")
        strategy = ClipboardInsertionStrategy(config)

        result = await strategy.insert("some text")

        assert result.success is True
        assert result.method_used == "clipboard"
        mock_copy.assert_called_once_with("some text")
        mock_hotkey.assert_called_once()

    @patch("agentvoca.insertion.clipboard.pyperclip.copy")
    @patch("agentvoca.insertion.clipboard.pyautogui.hotkey")
    async def test_unicode_inserts_correctly(
        self, mock_hotkey: MagicMock, mock_copy: MagicMock
    ) -> None:
        from agentvoca.config.schema import InsertionConfig
        from agentvoca.insertion.clipboard import ClipboardInsertionStrategy

        config = InsertionConfig(strategy="clipboard")
        strategy = ClipboardInsertionStrategy(config)

        result = await strategy.insert("こんにちは")

        assert result.success is True
        mock_copy.assert_called_once_with("こんにちは")

    async def test_empty_text_is_trivial_success(self) -> None:
        from agentvoca.config.schema import InsertionConfig
        from agentvoca.insertion.clipboard import ClipboardInsertionStrategy

        config = InsertionConfig(strategy="clipboard")
        strategy = ClipboardInsertionStrategy(config)
        result = await strategy.insert("")
        assert result.success is True

    @patch("agentvoca.insertion.clipboard.pyperclip.copy", side_effect=RuntimeError("no clipboard"))
    async def test_clipboard_error_returns_failure(self, mock_copy: MagicMock) -> None:
        from agentvoca.config.schema import InsertionConfig
        from agentvoca.insertion.clipboard import ClipboardInsertionStrategy

        config = InsertionConfig(strategy="clipboard")
        strategy = ClipboardInsertionStrategy(config)
        result = await strategy.insert("text")
        assert result.success is False
        assert "no clipboard" in (result.error or "")
