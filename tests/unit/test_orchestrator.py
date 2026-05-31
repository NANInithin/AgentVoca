"""Unit tests for the Orchestrator pipeline coordinator.

Tests cover:
- Lifecycle: start/stop, provider loading, event bus subscriptions.
- Happy path: full ASR → cleanup → insertion → idle cycle.
- Fallback paths: cleanup error → raw fallback, insertion failure with clipboard fallback.
- Error paths: ASR retries exhausted → error → timeout → idle.
- Event emissions: TimingEvent, TranscriptEvent, CleanedTextEvent, InsertionCompleteEvent,
  StateChangedEvent, ErrorEvent.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

import pytest

from agentvoca.asr.base import ASRProvider
from agentvoca.cleanup.base import CleanupProvider
from agentvoca.config.schema import (
    ASRConfig,
    CleanupConfig,
    FullConfig,
    InsertionConfig,
)
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import (
    CleanedTextEvent,
    ErrorEvent,
    InsertionCompleteEvent,
    RecordingStoppedEvent,
    StateChangedEvent,
    TimingEvent,
    TranscriptEvent,
)
from agentvoca.core.orchestrator import Orchestrator
from agentvoca.core.registry import ProviderRegistry
from agentvoca.core.types import (
    ASRContext,
    CleanupContext,
    InsertionResult,
    TranscriptSegment,
)
from agentvoca.insertion.base import InsertionStrategy
from agentvoca.utils.errors import ASRError, CleanupError

# ── Mock Providers ──────────────────────────────────────────────────


class MockASR(ASRProvider):
    """Configurable mock ASR provider."""

    def __init__(self, config: ASRConfig) -> None:
        self.config = config
        self.fail_count = 0
        self.available = True

    def get_name(self) -> str:
        return "mock_asr"

    def is_available(self) -> bool:
        return self.available

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> TranscriptSegment:
        if self.fail_count > 0:
            self.fail_count -= 1
            raise ASRError("Mock ASR failure")
        return TranscriptSegment(text="hello world this is a test", is_final=True)

    async def stream_transcribe(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> AsyncIterator[TranscriptSegment]:
        yield TranscriptSegment(text="hello world this is a test", is_final=True)


class MockCleanup(CleanupProvider):
    """Configurable mock cleanup provider."""

    def __init__(self, config: CleanupConfig) -> None:
        self.config = config
        self.fail_count = 0
        self.available = True

    def get_name(self) -> str:
        return "mock_cleanup"

    def is_available(self) -> bool:
        return self.available

    async def rewrite(
        self,
        transcript: str,
        context: Optional[CleanupContext] = None,
    ) -> str:
        if self.fail_count > 0:
            self.fail_count -= 1
            raise CleanupError("Mock cleanup failure")
        return transcript.upper()


class MockInsertion(InsertionStrategy):
    """Configurable mock insertion strategy."""

    def __init__(self, config: InsertionConfig) -> None:
        self.config = config
        self.fail_insert = False
        self.insert_count = 0
        self.undo_count = 0

    def get_name(self) -> str:
        return "mock_insert"

    def is_available(self) -> bool:
        return True

    async def insert(self, text: str) -> InsertionResult:
        self.insert_count += 1
        if self.fail_insert:
            return InsertionResult(
                success=False, method_used="keyboard", error="Mock insertion failure"
            )
        return InsertionResult(success=True, method_used="keyboard")

    async def undo_last(self) -> bool:
        self.undo_count += 1
        return True


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def minimal_config() -> FullConfig:
    """Return a minimal valid config for testing."""
    return FullConfig(
        asr=ASRConfig(provider="mock_asr"),
        cleanup=CleanupConfig(provider="mock_cleanup"),
        insertion=InsertionConfig(strategy="keyboard"),
    )


@pytest.fixture
def registry() -> ProviderRegistry:
    """Return a registry with mock providers registered."""
    reg = ProviderRegistry()
    reg.register_asr("mock_asr", MockASR)
    reg.register_cleanup("mock_cleanup", MockCleanup)
    reg.register_insertion("keyboard", MockInsertion)
    return reg


@pytest.fixture
def event_bus() -> EventBus:
    """Return a fresh event bus."""
    return EventBus()


@pytest.fixture
def recording_stopped_event() -> RecordingStoppedEvent:
    """Return a standard recording stopped event."""
    return RecordingStoppedEvent(
        audio_bytes=b"\x00\x00" * 16000,
        duration_ms=1000,
        sample_rate=16000,
    )


@pytest.fixture
async def orchestrator(
    minimal_config: FullConfig,
    registry: ProviderRegistry,
    event_bus: EventBus,
) -> AsyncIterator[Orchestrator]:
    """Return a started orchestrator."""
    orch = Orchestrator(config=minimal_config, registry=registry, event_bus=event_bus)
    await orch.start()
    yield orch
    await orch.stop()


# ── Collected Events Helper ─────────────────────────────────────────


class EventCollector:
    """Collects events of a specific type from an event bus."""

    def __init__(self, bus: EventBus, event_type: type) -> None:
        self.events: list = []
        bus.subscribe(event_type, self._collect)

    def _collect(self, event: object) -> None:
        self.events.append(event)

    def clear(self) -> None:
        self.events.clear()


# ── Tests ───────────────────────────────────────────────────────────


class TestOrchestratorLifecycle:
    """Orchestrator start/stop behavior."""

    async def test_start_initializes_providers(self, orchestrator: Orchestrator) -> None:
        assert orchestrator._asr_provider is not None
        assert orchestrator._cleanup_provider is not None
        assert orchestrator._insertion_strategy is not None
        assert orchestrator.get_state() == "idle"

    async def test_stop_cleans_up(self, orchestrator: Orchestrator) -> None:
        await orchestrator.stop()
        assert orchestrator._running is False

    async def test_initial_state_is_idle(self, orchestrator: Orchestrator) -> None:
        assert orchestrator.get_state() == "idle"

    async def test_get_last_transcript_returns_none_initially(
        self, orchestrator: Orchestrator
    ) -> None:
        assert orchestrator.get_last_transcript() is None


class TestOrchestratorHappyPath:
    """Full successful pipeline cycle."""

    async def test_full_cycle(
        self,
        orchestrator: Orchestrator,
        event_bus: EventBus,
        recording_stopped_event: RecordingStoppedEvent,
    ) -> None:
        """ASR → cleanup → insertion → idle."""
        state_changes = EventCollector(event_bus, StateChangedEvent)
        timing_events = EventCollector(event_bus, TimingEvent)
        transcript_events = EventCollector(event_bus, TranscriptEvent)

        event_bus.publish(recording_stopped_event)
        await asyncio.sleep(0.1)

        assert orchestrator.get_state() == "idle"
        assert any(e.stage == "asr" for e in timing_events.events)
        assert len(transcript_events.events) == 1
        assert transcript_events.events[0].text == "hello world this is a test"
        assert transcript_events.events[0].is_final is True
        assert len(state_changes.events) >= 1
        assert orchestrator.get_last_transcript() is not None

    async def test_cleanup_applied(
        self,
        orchestrator: Orchestrator,
        event_bus: EventBus,
        recording_stopped_event: RecordingStoppedEvent,
    ) -> None:
        """Cleaned text should be uppercase (as per MockCleanup)."""
        cleaned_events = EventCollector(event_bus, CleanedTextEvent)

        event_bus.publish(recording_stopped_event)
        await asyncio.sleep(0.1)

        assert len(cleaned_events.events) == 1
        cleaned = cleaned_events.events[0]
        assert cleaned.text == "HELLO WORLD THIS IS A TEST"
        assert cleaned.used_fallback is False

    async def test_insertion_complete_event_emitted(
        self,
        orchestrator: Orchestrator,
        event_bus: EventBus,
        recording_stopped_event: RecordingStoppedEvent,
    ) -> None:
        insert_events = EventCollector(event_bus, InsertionCompleteEvent)

        event_bus.publish(recording_stopped_event)
        await asyncio.sleep(0.1)

        assert len(insert_events.events) >= 1
        last_insert = insert_events.events[-1]
        assert last_insert.success is True
        assert last_insert.method_used == "keyboard"


class TestOrchestratorFallbackPaths:
    """Fallback behavior per §8."""

    async def test_cleanup_fallback_uses_raw_transcript(
        self,
        minimal_config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
        recording_stopped_event: RecordingStoppedEvent,
    ) -> None:
        cleanup_cls = registry._cleanup["mock_cleanup"]

        class FailingCleanup(cleanup_cls):  # type: ignore
            async def rewrite(
                self,
                transcript: str,
                context: Optional[CleanupContext] = None,
            ) -> str:
                raise CleanupError("Always fails")

        registry.register_cleanup("mock_cleanup", FailingCleanup)

        orch = Orchestrator(config=minimal_config, registry=registry, event_bus=event_bus)
        await orch.start()

        cleaned_events = EventCollector(event_bus, CleanedTextEvent)

        event_bus.publish(recording_stopped_event)
        await asyncio.sleep(1.0)

        assert len(cleaned_events.events) >= 1
        fallback_events = [e for e in cleaned_events.events if e.used_fallback]
        assert len(fallback_events) >= 1
        assert fallback_events[-1].text == "hello world this is a test"

        await orch.stop()

    async def test_insertion_clipboard_fallback(
        self,
        minimal_config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
        recording_stopped_event: RecordingStoppedEvent,
    ) -> None:
        """When keyboard insertion fails, clipboard fallback is attempted."""
        insert_cls = registry._insertion["keyboard"]

        class FailingInsert(insert_cls):  # type: ignore
            async def insert(self, text: str) -> InsertionResult:
                return InsertionResult(
                    success=False, method_used="keyboard", error="Insert failure"
                )

        registry.register_insertion("keyboard", FailingInsert)

        orch = Orchestrator(config=minimal_config, registry=registry, event_bus=event_bus)
        await orch.start()

        event_bus.publish(recording_stopped_event)
        await asyncio.sleep(1.0)

        # The clipboard fallback now attempts a real ClipboardInsertionStrategy
        # which may succeed or fail depending on environment. Either way
        # the pipeline should complete.
        final_state = orch.get_state()
        assert final_state in ("idle", "error"), f"Expected idle or error, got {final_state}"

        await orch.stop()


class TestOrchestratorErrorPaths:
    """Error handling and recovery."""

    async def test_asr_retries_exhausted_goes_to_error(
        self,
        minimal_config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
        recording_stopped_event: RecordingStoppedEvent,
    ) -> None:
        asr_cls = registry._asr["mock_asr"]

        class FailingASR(asr_cls):  # type: ignore
            async def transcribe_audio(
                self,
                audio_bytes: bytes,
                sample_rate: int,
                context: Optional[ASRContext] = None,
            ) -> TranscriptSegment:
                raise ASRError("Always fails")

        registry.register_asr("mock_asr", FailingASR)

        orch = Orchestrator(config=minimal_config, registry=registry, event_bus=event_bus)
        await orch.start()

        error_events = EventCollector(event_bus, ErrorEvent)

        event_bus.publish(recording_stopped_event)
        await asyncio.sleep(1.5)

        assert orch.get_state() == "error"
        assert len(error_events.events) >= 1
        assert error_events.events[0].stage == "asr"
        assert error_events.events[0].recoverable is False

        await asyncio.sleep(5.5)
        assert orch.get_state() == "idle"

        await orch.stop()

    async def test_insertion_error_no_clipboard_fallback(
        self,
        minimal_config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
        recording_stopped_event: RecordingStoppedEvent,
    ) -> None:
        config = FullConfig(
            asr=ASRConfig(provider="mock_asr"),
            cleanup=CleanupConfig(provider="mock_cleanup"),
            insertion=InsertionConfig(strategy="keyboard", clipboard_fallback=False),
        )

        insert_cls = registry._insertion["keyboard"]

        class FailingInsert(insert_cls):  # type: ignore
            async def insert(self, text: str) -> InsertionResult:
                return InsertionResult(success=False, method_used="keyboard", error="Always fails")

        registry.register_insertion("keyboard", FailingInsert)

        orch = Orchestrator(config=config, registry=registry, event_bus=event_bus)
        await orch.start()

        error_events = EventCollector(event_bus, ErrorEvent)
        insert_events = EventCollector(event_bus, InsertionCompleteEvent)

        event_bus.publish(recording_stopped_event)
        await asyncio.sleep(2.0)

        final_state = orch.get_state()
        assert final_state == "error", (
            f"Expected error, got {final_state}. "
            f"InsertionComplete events: {len(insert_events.events)}. "
            f"Error events: {len(error_events.events)}"
        )
        assert len(error_events.events) >= 1
        assert error_events.events[-1].stage == "insertion"

        await orch.stop()


class TestOrchestratorEvents:
    """Verify correct events are emitted."""

    async def test_timing_events_emitted(
        self,
        orchestrator: Orchestrator,
        event_bus: EventBus,
        recording_stopped_event: RecordingStoppedEvent,
    ) -> None:
        timing_events = EventCollector(event_bus, TimingEvent)

        event_bus.publish(recording_stopped_event)
        await asyncio.sleep(0.1)

        stages = {e.stage for e in timing_events.events}
        assert "asr" in stages
        assert "cleanup" in stages
        assert "insertion" in stages

    async def test_state_changes_emitted(
        self,
        orchestrator: Orchestrator,
        event_bus: EventBus,
        recording_stopped_event: RecordingStoppedEvent,
    ) -> None:
        state_changes = EventCollector(event_bus, StateChangedEvent)

        event_bus.publish(recording_stopped_event)
        await asyncio.sleep(0.1)

        assert len(state_changes.events) >= 1


class TestOrchestratorVocabularySnippets:
    """Vocabulary and snippets are now real implementations."""

    async def test_vocabulary_stub_returns_original(self, orchestrator: Orchestrator) -> None:
        result = orchestrator._apply_vocabulary("hello world")
        # With no vocabulary configured, returns the original
        assert result == "hello world"

    async def test_snippet_stub_returns_original(self, orchestrator: Orchestrator) -> None:
        result = orchestrator._expand_snippets("hello world")
        # With no snippets configured, returns the original
        assert result == "hello world"
