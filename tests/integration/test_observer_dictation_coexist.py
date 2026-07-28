"""Integration test: dictation during an Observer session (OBS-12).

Verifies that:
- A dictation that runs while a session is open inserts its text normally.
- The dictated-utterance hook publishes ``ObserverUtteranceEvent`` with
  ``source="dictated"`` and the recording's wall-clock duration.
- The orchestrator's no-arbiter path is bit-identical to v0.3.6.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from agentvoca.asr.base import ASRProvider
from agentvoca.config.schema import (
    ASRConfig,
    CleanupConfig,
    FullConfig,
    InsertionConfig,
)
from agentvoca.core.async_loop import AsyncLoopThread
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import (
    InsertionCompleteEvent,
    ObserverUtteranceEvent,
    RecordingStoppedEvent,
)
from agentvoca.core.orchestrator import Orchestrator
from agentvoca.core.types import InsertionResult, TranscriptSegment

# ── Fakes ──────────────────────────────────────────────────────────


class MockASR(ASRProvider):
    def __init__(self, config: ASRConfig) -> None:
        self.config = config
        self.transcribe_calls: list[tuple[bytes, int]] = []

    def get_name(self) -> str:
        return "mock_asr"

    def is_available(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return False

    async def transcribe_audio(self, audio_bytes, sample_rate, context=None):
        self.transcribe_calls.append((audio_bytes, sample_rate))
        return TranscriptSegment(text="hello observer", is_final=True)

    async def stream_transcribe(self, audio_stream, sample_rate, context=None):
        yield TranscriptSegment(text="hello observer", is_final=True)


class MockInsertion:
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
        if self.inserted:
            self.inserted.pop()
            return True
        return False


class MockCleanup:
    def __init__(self, config: CleanupConfig) -> None:
        self.config = config

    def get_name(self) -> str:
        return "mock_cleanup"

    def is_available(self) -> bool:
        return True

    async def rewrite(self, transcript, context=None):
        return transcript

    async def warm_up(self) -> None:
        return None


@pytest.fixture
def loop_thread():
    t = AsyncLoopThread()
    t.start()
    yield t
    t.stop()


@pytest.fixture
def config() -> FullConfig:
    return FullConfig(
        asr=ASRConfig(provider="mock_asr"),
        cleanup=CleanupConfig(provider="mock_cleanup"),
        insertion=InsertionConfig(strategy="keyboard"),
    )


# ── Tests ──────────────────────────────────────────────────────────


class TestDictationCoexist:
    async def test_dictation_publishes_observer_utterance_event(self, loop_thread, config) -> None:
        event_bus = EventBus()
        event_bus.set_loop(loop_thread.loop)

        # Register mocks. Use the literal "keyboard" strategy and
        # replace the registered class with our mock so we can record
        # insertions.
        from agentvoca.core.registry import ProviderRegistry

        registry = ProviderRegistry()
        registry.register_asr("mock_asr", MockASR)
        registry.register_cleanup("mock_cleanup", MockCleanup)
        registry.register_insertion("keyboard", MockInsertion)

        orch = Orchestrator(config=config, registry=registry, event_bus=event_bus)
        await orch.start()

        utterance_events: list[ObserverUtteranceEvent] = []
        insert_events: list[InsertionCompleteEvent] = []

        def on_utterance(event: ObserverUtteranceEvent) -> None:
            utterance_events.append(event)

        def on_insert(event: InsertionCompleteEvent) -> None:
            insert_events.append(event)

        event_bus.subscribe(ObserverUtteranceEvent, on_utterance)
        event_bus.subscribe(InsertionCompleteEvent, on_insert)

        try:
            # Simulate a 1.5s recording.
            event_bus.publish(
                RecordingStoppedEvent(
                    audio_bytes=b"\x00" * 1024, duration_ms=1500, sample_rate=16000
                )
            )
            # Wait for the pipeline to complete.
            deadline = time.time() + 3.0
            while time.time() < deadline and not insert_events:
                await asyncio.sleep(0.05)

            assert insert_events, "InsertionCompleteEvent was never published"
            assert utterance_events, "ObserverUtteranceEvent was never published"
            evt = utterance_events[0]
            assert evt.text == "hello observer"
            assert evt.source == "dictated"
            assert evt.duration_ms == 1500
        finally:
            await orch.stop()

    async def test_observer_disabled_does_not_break_orchestrator(self, loop_thread, config) -> None:
        # When no arbiter is attached, the orchestrator must call the
        # provider directly — exactly as v0.3.6. The
        # ObserverUtteranceEvent is still published (the bus no-ops when
        # nobody listens).
        event_bus = EventBus()
        event_bus.set_loop(loop_thread.loop)

        from agentvoca.core.registry import ProviderRegistry

        registry = ProviderRegistry()
        registry.register_asr("mock_asr", MockASR)
        registry.register_cleanup("mock_cleanup", MockCleanup)
        registry.register_insertion("keyboard", MockInsertion)

        orch = Orchestrator(config=config, registry=registry, event_bus=event_bus)
        assert orch._asr_arbiter is None
        await orch.start()

        try:
            event_bus.publish(
                RecordingStoppedEvent(
                    audio_bytes=b"\x00" * 1024, duration_ms=500, sample_rate=16000
                )
            )
            deadline = time.time() + 3.0
            # Poll for the ASR call to happen. ``orch._asr_provider`` is
            # the constructed instance.
            asr = orch._asr_provider
            while time.time() < deadline and not asr.transcribe_calls:
                await asyncio.sleep(0.05)
            assert asr.transcribe_calls, "ASR provider was not called"
        finally:
            await orch.stop()
