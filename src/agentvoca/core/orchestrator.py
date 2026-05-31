"""Orchestrator — coordinates the voice dictation pipeline.

The orchestrator owns the application state machine, subscribes to events
from the event bus, drives the ASR → cleanup → insertion pipeline, and
emits events at every stage boundary. It implements the retry policy and
fallback paths defined in the architecture spec (§6.3, §7, §8).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from agentvoca.asr.base import ASRProvider
from agentvoca.cleanup.base import CleanupProvider
from agentvoca.config.schema import FullConfig
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
from agentvoca.core.registry import ProviderRegistry
from agentvoca.core.state_machine import StateMachine
from agentvoca.core.types import AppState, CleanupContext, InsertionResult
from agentvoca.insertion.base import InsertionStrategy
from agentvoca.utils.errors import ASRError, CleanupError
from agentvoca.vocab.dictionary import VocabularyDictionary
from agentvoca.vocab.snippets import SnippetExpander

logger = logging.getLogger(__name__)

# ── Retry Policy (§6.3) ─────────────────────────────────────────────

_ASR_RETRIES = 1
_ASR_RETRY_DELAY_S = 0.5

_CLEANUP_RETRIES = 1
_CLEANUP_RETRY_DELAY_S = 0.2

_ERROR_TIMEOUT_S = 5.0


class Orchestrator:
    """Central coordinator for the voice dictation pipeline.

    Args:
        config: The validated application configuration.
        registry: Provider registry with registered factory classes.
        event_bus: Shared event bus for emitting and subscribing to events.
    """

    def __init__(
        self,
        config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        self._config = config
        self._registry = registry
        self._event_bus = event_bus

        self._state_machine = StateMachine()
        self._last_transcript: Optional[str] = None

        # Lazy-initialized providers (set up in ``start()``)
        self._asr_provider: Optional[ASRProvider] = None
        self._cleanup_provider: Optional[CleanupProvider] = None
        self._insertion_strategy: Optional[InsertionStrategy] = None

        # Background task tracking
        self._running = False
        self._error_timer_task: Optional[asyncio.Task[None]] = None

        # Pipeline state
        self._current_audio_bytes: Optional[bytes] = None
        self._current_sample_rate: int = 0
        self._current_transcript: Optional[str] = None
        self._cleanup_success: bool = False

        # Vocabulary and snippets
        self._vocab: Optional[VocabularyDictionary] = None
        self._snippets: Optional[SnippetExpander] = None

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        """Initialize providers, register event handlers, begin listening.

        Called once at application startup.
        """
        logger.info("Orchestrator starting…")

        # Build provider instances from config
        self._asr_provider = self._registry.get_asr(self._config.asr)
        self._cleanup_provider = self._registry.get_cleanup(self._config.cleanup)
        self._insertion_strategy = self._registry.get_insertion(self._config.insertion)

        # Check provider availability
        if not self._asr_provider.is_available():
            logger.warning(
                "ASR provider '%s' reports unavailable at startup",
                self._asr_provider.get_name(),
            )
        if not self._cleanup_provider.is_available():
            logger.warning(
                "Cleanup provider '%s' reports unavailable at startup",
                self._cleanup_provider.get_name(),
            )

        # Initialize vocabulary and snippets
        self._init_vocab_snippets()

        # Register event bus subscriptions
        self._event_bus.subscribe(RecordingStoppedEvent, self._on_recording_stopped)

        self._running = True
        logger.info(
            "Orchestrator started. ASR=%s Cleanup=%s Insertion=%s",
            self._asr_provider.get_name(),
            self._cleanup_provider.get_name(),
            self._insertion_strategy.get_name(),
        )

    async def stop(self) -> None:
        """Clean up resources and stop all background tasks."""
        logger.info("Orchestrator stopping…")
        self._running = False

        # Cancel error timer if active
        if self._error_timer_task is not None and not self._error_timer_task.done():
            self._error_timer_task.cancel()
            self._error_timer_task = None

        logger.info("Orchestrator stopped")

    def _init_vocab_snippets(self) -> None:
        """Initialize vocabulary dictionary and snippet expander from config."""
        vocab_cfg = self._config.vocabulary
        snippet_cfg = self._config.snippets

        if vocab_cfg.path or vocab_cfg.inline:
            try:
                self._vocab = VocabularyDictionary(
                    path=vocab_cfg.path,
                    terms=vocab_cfg.inline,
                )
                logger.info("Vocabulary loaded (%d terms)", len(self._vocab.terms))
            except Exception:
                logger.exception("Failed to load vocabulary")
                self._vocab = VocabularyDictionary()
        else:
            self._vocab = VocabularyDictionary()

        if snippet_cfg.path:
            try:
                self._snippets = SnippetExpander(path=snippet_cfg.path)
                logger.info("Snippets loaded (%d triggers)", len(self._snippets.mapping))
            except Exception:
                logger.exception("Failed to load snippets")
                self._snippets = SnippetExpander()
        else:
            self._snippets = SnippetExpander()

    # ── Public API ───────────────────────────────────────────────────

    def get_state(self) -> AppState:
        """Return the current application state."""
        return self._state_machine.state  # type: ignore[return-value]

    def get_last_transcript(self) -> Optional[str]:
        """Return the most recently inserted transcript, or None."""
        return self._last_transcript

    async def undo_last_insertion(self) -> bool:
        """Undo the most recently inserted text by sending Ctrl+Z / Cmd+Z.

        Returns True if the undo was sent, False if no insertion strategy is loaded.
        """
        if self._insertion_strategy is None:
            return False
        return await self._insertion_strategy.undo_last()

    # ── Event Handlers ───────────────────────────────────────────────

    async def _on_recording_stopped(self, event: RecordingStoppedEvent) -> None:
        """Handle the completion of audio recording.

        This is the primary entry point into the pipeline. The audio layer
        emits ``RecordingStoppedEvent`` when the user stops recording.
        """
        self._current_audio_bytes = event.audio_bytes
        self._current_sample_rate = event.sample_rate

        # Drive the state machine forward from its current position.
        if self._state_machine.state == "idle":
            r1 = self._state_machine.transition(
                "HotkeyEvent", action="toggle_recording", mode="toggle"
            )
            if r1.transitioned:
                self._emit_state_change("idle", "recording")

        if self._state_machine.state == "recording":
            result = self._state_machine.transition("DurationEvent")
            if result.transitioned:
                self._emit_state_change("recording", result.new_state)

        await self._run_pipeline()

    # ── Pipeline ─────────────────────────────────────────────────────

    async def _run_pipeline(self) -> None:
        """Execute the full ASR → vocabulary → snippets → cleanup → insertion pipeline."""
        try:
            # Step 1: ASR Transcription
            await self._run_asr()

            # Step 2: Vocabulary substitution
            corrected_text = self._apply_vocabulary(self._current_transcript or "")

            # Step 3: Snippet expansion
            expanded_text = self._expand_snippets(corrected_text)

            # Step 4: Cleanup
            cleaned_text = await self._run_cleanup(expanded_text)

            # Step 5: Insertion
            await self._run_insertion(cleaned_text)

        except Exception:
            logger.exception("Unhandled pipeline error")
            self._transition_or_emit_error("pipeline", "Unhandled pipeline error", False)

    # ── Pipeline Steps ───────────────────────────────────────────────

    async def _run_asr(self) -> None:
        """Transcribe the captured audio with retry logic (§6.3)."""
        assert self._asr_provider is not None
        assert self._current_audio_bytes is not None

        audio_bytes = self._current_audio_bytes
        sample_rate = self._current_sample_rate

        last_error: Optional[Exception] = None

        for attempt in range(1 + _ASR_RETRIES):
            t0 = time.perf_counter()
            try:
                segment = await self._asr_provider.transcribe_audio(audio_bytes, sample_rate)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)

                self._event_bus.publish(TimingEvent(stage="asr", duration_ms=elapsed_ms))
                self._event_bus.publish(TranscriptEvent(text=segment.text, is_final=True))

                self._current_transcript = segment.text

                result = self._state_machine.transition("TranscriptEvent", is_final=True)
                if result.transitioned:
                    self._emit_state_change("transcribing", result.new_state)

                return

            except ASRError as exc:
                last_error = exc
                logger.warning("ASR attempt %d/%d failed: %s", attempt + 1, 1 + _ASR_RETRIES, exc)
                if attempt < _ASR_RETRIES:
                    await asyncio.sleep(_ASR_RETRY_DELAY_S)

        # All retries exhausted
        logger.error("ASR failed after %d attempts", 1 + _ASR_RETRIES)
        self._state_machine.transition("ErrorEvent", retries_exhausted=True, stage="asr")
        self._emit_error(
            stage="asr",
            message=f"Transcription failed after {1 + _ASR_RETRIES} attempts. "
            f"Check ASR provider settings.",
            recoverable=False,
            detail=str(last_error) if last_error else None,
        )

    async def _run_cleanup(self, transcript: str) -> str:
        """Clean the transcript with retry logic (§6.3)."""
        assert self._cleanup_provider is not None

        if not self._cleanup_provider.is_available():
            logger.warning(
                "Cleanup provider '%s' not available; using raw transcript",
                self._cleanup_provider.get_name(),
            )
            self._event_bus.publish(
                CleanedTextEvent(text=transcript, used_fallback=True, latency_ms=0)
            )
            self._state_machine.transition("ErrorEvent", stage="cleanup")
            return transcript

        cleanup_context = CleanupContext(
            style=self._config.cleanup.style,
            preserve_code=self._config.cleanup.preserve_code,
        )

        for attempt in range(1 + _CLEANUP_RETRIES):
            t0 = time.perf_counter()
            try:
                cleaned = await self._cleanup_provider.rewrite(transcript, context=cleanup_context)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)

                self._event_bus.publish(TimingEvent(stage="cleanup", duration_ms=elapsed_ms))
                self._event_bus.publish(
                    CleanedTextEvent(text=cleaned, used_fallback=False, latency_ms=elapsed_ms)
                )

                self._state_machine.transition("CleanedTextEvent", success=True)
                self._cleanup_success = True
                return cleaned

            except CleanupError as exc:
                logger.warning(
                    "Cleanup attempt %d/%d failed: %s", attempt + 1, 1 + _CLEANUP_RETRIES, exc
                )
                if attempt < _CLEANUP_RETRIES:
                    await asyncio.sleep(_CLEANUP_RETRY_DELAY_S)

        logger.warning(
            "Cleanup failed after %d attempts; using raw transcript", 1 + _CLEANUP_RETRIES
        )
        self._event_bus.publish(CleanedTextEvent(text=transcript, used_fallback=True, latency_ms=0))
        self._state_machine.transition("ErrorEvent", stage="cleanup")
        self._cleanup_success = False
        return transcript

    async def _run_insertion(self, text: str) -> None:
        """Insert the final text with clipboard fallback (§8)."""
        assert self._insertion_strategy is not None

        current_state = self._state_machine.state
        t0 = time.perf_counter()

        # Step 1: Try the primary insertion strategy
        result = await self._insertion_strategy.insert(text)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        self._event_bus.publish(TimingEvent(stage="insertion", duration_ms=elapsed_ms))

        if result.success:
            self._last_transcript = text
            self._event_bus.publish(
                InsertionCompleteEvent(success=True, method_used=result.method_used)
            )
            self._state_machine.transition("InsertionCompleteEvent", success=True)
            self._emit_state_change(current_state, "idle")
            return

        # Step 2: Attempt clipboard fallback
        if self._config.insertion.clipboard_fallback:
            logger.info("Keyboard insertion failed; falling back to clipboard (%s)", result.error)
            t1 = time.perf_counter()

            self._event_bus.publish(
                InsertionCompleteEvent(success=False, method_used="keyboard", error=result.error)
            )
            await self._insertion_strategy.undo_last()

            clipboard_result = await self._try_clipboard_insert(text)
            elapsed_clipboard_ms = int((time.perf_counter() - t1) * 1000)
            self._event_bus.publish(
                TimingEvent(stage="clipboard_fallback", duration_ms=elapsed_clipboard_ms)
            )

            if clipboard_result.success:
                self._last_transcript = text
                self._event_bus.publish(
                    InsertionCompleteEvent(success=True, method_used="clipboard")
                )
                self._state_machine.transition(
                    "InsertionCompleteEvent", success=False, clipboard_fallback=True
                )
                self._emit_state_change(current_state, "idle")
                logger.info("Inserted via clipboard")
            else:
                self._event_bus.publish(
                    InsertionCompleteEvent(
                        success=False, method_used="clipboard", error=clipboard_result.error
                    )
                )
                self._state_machine.transition(
                    "InsertionCompleteEvent", success=False, clipboard_fallback=False
                )
                self._emit_error(
                    stage="insertion",
                    message="Both keyboard and clipboard insertion failed. "
                    f"Last error: {clipboard_result.error}",
                    recoverable=False,
                    detail=f"Keyboard: {result.error}; Clipboard: {clipboard_result.error}",
                )
        else:
            self._event_bus.publish(
                InsertionCompleteEvent(
                    success=False, method_used=result.method_used, error=result.error
                )
            )
            self._state_machine.transition(
                "InsertionCompleteEvent", success=False, clipboard_fallback=False
            )
            self._emit_error(
                stage="insertion", message=f"Insertion failed: {result.error}", recoverable=False
            )

    async def _try_clipboard_insert(self, text: str) -> InsertionResult:
        """Attempt clipboard-based insertion using the registered clipboard strategy."""
        try:
            from agentvoca.insertion.clipboard import (
                ClipboardInsertionStrategy,  # noqa: PLC0415
            )

            clipboard = ClipboardInsertionStrategy(self._config.insertion)
            return await clipboard.insert(text)
        except Exception as exc:
            logger.warning("Clipboard fallback failed: %s", exc)
            return InsertionResult(success=False, method_used="clipboard", error=str(exc))

    # ── Vocabulary and Snippets ─────────────────────────────────────

    def _apply_vocabulary(self, text: str) -> str:
        """Apply vocabulary substitutions to the transcript."""
        if self._vocab is not None:
            return self._vocab.apply(text)
        return text

    def _expand_snippets(self, text: str) -> str:
        """Expand snippet triggers in the transcript."""
        if self._snippets is not None:
            return self._snippets.expand(text)
        return text

    # ── Event Emission Helpers ───────────────────────────────────────

    def _emit_state_change(self, previous: str, current: str) -> None:
        """Publish a ``StateChangedEvent``."""
        self._event_bus.publish(StateChangedEvent(previous=previous, current=current))

    def _emit_error(
        self,
        stage: str,
        message: str,
        recoverable: bool,
        detail: Optional[str] = None,
    ) -> None:
        """Publish an ``ErrorEvent``."""
        self._event_bus.publish(
            ErrorEvent(stage=stage, message=message, recoverable=recoverable, detail=detail)
        )
        if not recoverable:
            self._schedule_error_timeout()

    def _transition_or_emit_error(self, stage: str, message: str, recoverable: bool) -> None:
        """Emit an error and transition state in one call."""
        self._emit_error(stage=stage, message=message, recoverable=recoverable)

    def _schedule_error_timeout(self) -> None:
        """Schedule a transition from error → idle after ``_ERROR_TIMEOUT_S``."""
        if self._error_timer_task is not None and not self._error_timer_task.done():
            self._error_timer_task.cancel()

        async def _timeout() -> None:
            await asyncio.sleep(_ERROR_TIMEOUT_S)
            if self._state_machine.state == "error":
                result = self._state_machine.transition("TimeoutEvent")
                if result.transitioned:
                    self._emit_state_change("error", "idle")
                self._current_audio_bytes = None
                self._current_transcript = None

        self._error_timer_task = asyncio.create_task(_timeout())
