"""Integration tests for the v3 vision splice in the orchestrator pipeline."""

from __future__ import annotations

from typing import AsyncIterator, Optional

import pytest

from agentvoca.asr.base import ASRProvider
from agentvoca.cleanup.base import CleanupProvider
from agentvoca.config.schema import (
    ASRConfig,
    CleanupConfig,
    FullConfig,
    InsertionConfig,
    VisionConfig,
)
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import RecordingStoppedEvent, VisionExtractedEvent
from agentvoca.core.orchestrator import Orchestrator
from agentvoca.core.registry import ProviderRegistry
from agentvoca.core.types import (
    CleanupContext,
    InsertionResult,
    TranscriptSegment,
)
from agentvoca.insertion.base import InsertionStrategy
from agentvoca.vision.base import VisionProvider


class MockASR(ASRProvider):
    def __init__(self, config: ASRConfig) -> None:
        self.config = config
        self.text = "make a table as in the attached screenshot"

    def get_name(self) -> str:
        return "mock_asr"

    def is_available(self) -> bool:
        return True

    async def transcribe_audio(self, audio_bytes, sample_rate, context=None) -> TranscriptSegment:
        return TranscriptSegment(text=self.text, is_final=True)

    async def stream_transcribe(
        self, audio_stream: AsyncIterator[bytes], sample_rate, context=None
    ) -> AsyncIterator[TranscriptSegment]:
        yield TranscriptSegment(text=self.text, is_final=True)


class MockCleanup(CleanupProvider):
    def __init__(self, config: CleanupConfig) -> None:
        self.config = config
        self.last_context: Optional[CleanupContext] = None

    def get_name(self) -> str:
        return "mock_cleanup"

    def is_available(self) -> bool:
        return True

    async def rewrite(self, transcript: str, context: Optional[CleanupContext] = None) -> str:
        self.last_context = context
        return transcript  # pass through so we can assert on spliced content


class MockInsertion(InsertionStrategy):
    def __init__(self, config: InsertionConfig) -> None:
        self.config = config
        self.inserted: list[str] = []

    def get_name(self) -> str:
        return "mock_insert"

    def is_available(self) -> bool:
        return True

    async def insert(self, text: str) -> InsertionResult:
        self.inserted.append(text)
        return InsertionResult(success=True, method_used="keyboard")

    async def undo_last(self) -> bool:
        return True


class FakeVision(VisionProvider):
    def __init__(self, config: VisionConfig) -> None:
        self.config = config
        self.calls: list[str] = []

    def get_name(self) -> str:
        return "fake_vision"

    def is_available(self) -> bool:
        return True

    async def extract(self, image_data, instruction, context=None, mime_type="image/png") -> str:
        self.calls.append(instruction)
        return "| Item | Cost |\n|---|---|\n| Lunch | 12 |"


class FakeCapturer:
    """Minimal capturer stub implementing the orchestrator's interface."""

    def __init__(self, shots: Optional[list[bytes]] = None) -> None:
        self._shots = shots or []
        self.cleared = False

    def is_available(self) -> bool:
        return True

    def has_pending(self) -> bool:
        return bool(self._shots)

    def wait_idle(self, timeout: float) -> bool:
        return True

    def drain(self) -> list[bytes]:
        shots = self._shots
        self._shots = []
        return shots

    def clear(self) -> None:
        self.cleared = True
        self._shots = []


def _config(vision_enabled: bool = True) -> FullConfig:
    return FullConfig(
        asr=ASRConfig(provider="mock_asr"),
        cleanup=CleanupConfig(provider="mock_cleanup"),
        insertion=InsertionConfig(strategy="keyboard"),
        vision=VisionConfig(enabled=vision_enabled, provider="fake_vision"),
    )


def _registry() -> ProviderRegistry:
    reg = ProviderRegistry()
    reg.register_asr("mock_asr", MockASR)
    reg.register_cleanup("mock_cleanup", MockCleanup)
    reg.register_insertion("keyboard", MockInsertion)
    reg.register_vision("fake_vision", FakeVision)
    return reg


async def _make_orch(capturer, vision_enabled: bool = True):
    bus = EventBus()
    orch = Orchestrator(
        config=_config(vision_enabled),
        registry=_registry(),
        event_bus=bus,
        screenshot_capturer=capturer,
    )
    await orch.start()
    return orch, bus


@pytest.mark.asyncio
async def test_pipeline_splices_extraction_at_anchor():
    cap = FakeCapturer(shots=[b"\x89PNGfake"])
    orch, bus = await _make_orch(cap)

    vision_events: list[VisionExtractedEvent] = []
    bus.subscribe(VisionExtractedEvent, vision_events.append)

    insertion = orch._insertion_strategy
    cleanup = orch._cleanup_provider

    await orch._on_recording_stopped(
        RecordingStoppedEvent(audio_bytes=b"\x00\x00" * 16000, duration_ms=1000, sample_rate=16000)
    )

    assert insertion.inserted, "nothing was inserted"
    final = insertion.inserted[-1]
    assert "| Item | Cost |" in final
    assert "the attached screenshot" not in final  # anchor consumed
    # Vision forced preserve_code on the cleanup pass.
    assert cleanup.last_context is not None
    assert cleanup.last_context.preserve_code is True
    assert vision_events and vision_events[0].anchors_matched == 1
    await orch.stop()


@pytest.mark.asyncio
async def test_no_screenshots_is_noop():
    cap = FakeCapturer(shots=[])
    orch, _ = await _make_orch(cap)
    text, had = await orch._apply_vision("plain dictation, no anchors")
    assert had is False
    assert text == "plain dictation, no anchors"
    await orch.stop()


@pytest.mark.asyncio
async def test_vision_disabled_is_noop():
    cap = FakeCapturer(shots=[b"\x89PNGfake"])
    orch, _ = await _make_orch(cap, vision_enabled=False)
    text, had = await orch._apply_vision("see this screenshot")
    assert had is False
    assert text == "see this screenshot"
    await orch.stop()


@pytest.mark.asyncio
async def test_extraction_appended_when_no_anchor():
    cap = FakeCapturer(shots=[b"\x89PNGfake"])
    orch, _ = await _make_orch(cap)
    text, had = await orch._apply_vision("here are the figures")
    assert had is True
    assert text.startswith("here are the figures")
    assert "| Item | Cost |" in text
    await orch.stop()


@pytest.mark.asyncio
async def test_instruction_passed_to_vision_provider():
    cap = FakeCapturer(shots=[b"\x89PNGfake"])
    orch, _ = await _make_orch(cap)
    await orch._apply_vision("summarise the chart")
    assert orch._vision_provider.calls == ["summarise the chart"]
    await orch.stop()
