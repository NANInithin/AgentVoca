"""Orchestrator — coordinates the voice dictation pipeline.

The orchestrator owns the application state machine, subscribes to events
from the event bus, drives the ASR → cleanup → insertion pipeline, and
emits events at every stage boundary. It implements the retry policy and
fallback paths defined in the architecture spec (§6.3, §7, §8).

v2 adds the streaming coordinator: when ``asr.streaming`` is enabled, audio
chunks arriving during recording are streamed to the ASR provider and partial
transcripts are published live. The v1 batch path remains as the fallback
when streaming is disabled.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, AsyncIterator, Optional

from agentvoca.asr.base import ASRProvider
from agentvoca.cleanup.base import CleanupProvider
from agentvoca.commands.processor import DefaultCommandProcessor
from agentvoca.config.schema import FullConfig
from agentvoca.context.active_app import ActiveAppDetector
from agentvoca.context.language import LanguageResolver
from agentvoca.context.profiles import ProfileResolver
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import (
    AudioChunkEvent,
    CleanedTextEvent,
    CommandRecognizedEvent,
    ContextResolvedEvent,
    CorrectionLearnedEvent,
    ErrorEvent,
    InsertionCompleteEvent,
    PartialTranscriptEvent,
    RecordingStoppedEvent,
    SegmentFinalizedEvent,
    StateChangedEvent,
    TimingEvent,
    TranscriptEvent,
    VisionExtractedEvent,
    WarmupCompleteEvent,
)
from agentvoca.core.registry import ProviderRegistry
from agentvoca.core.state_machine import StateMachine
from agentvoca.core.types import (
    AppState,
    CleanupContext,
    InsertionResult,
    TranscriptSegment,
    VisionContext,
)
from agentvoca.insertion.base import InsertionStrategy
from agentvoca.utils.errors import ASRError, CleanupError, VisionError
from agentvoca.vision.anchors import AnchorSplicer
from agentvoca.vocab.adaptive import AdaptiveStore
from agentvoca.vocab.dictionary import VocabularyDictionary
from agentvoca.vocab.snippets import SnippetExpander

if TYPE_CHECKING:
    from agentvoca.capture.screenshot import ScreenshotCapturer
    from agentvoca.vision.base import VisionProvider

logger = logging.getLogger(__name__)

# How long the pipeline waits for an in-flight screenshot snip to finish
# before draining captures (the user may still be dragging a selection).
_VISION_CAPTURE_GRACE_S = 2.0

# ── Retry Policy (§6.3) ─────────────────────────────────────────────

_ASR_RETRIES = 1
_ASR_RETRY_DELAY_S = 0.5

_CLEANUP_RETRIES = 1
_CLEANUP_RETRY_DELAY_S = 0.2

_ERROR_TIMEOUT_S = 5.0

# Sentinel to signal end of streaming audio
_STREAM_END = object()


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
        screenshot_capturer: Optional["ScreenshotCapturer"] = None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._event_bus = event_bus
        self._screenshot_capturer = screenshot_capturer

        self._state_machine = StateMachine()
        self._last_transcript: Optional[str] = None

        # Lazy-initialized providers (set up in ``start()``)
        self._asr_provider: Optional[ASRProvider] = None
        self._cleanup_provider: Optional[CleanupProvider] = None
        self._insertion_strategy: Optional[InsertionStrategy] = None

        # Background task tracking
        self._running = False
        self._error_timer_task: Optional[asyncio.Task[None]] = None

        # Pipeline state (v1 batch path)
        self._current_audio_bytes: Optional[bytes] = None
        self._current_sample_rate: int = 0
        self._current_transcript: Optional[str] = None
        self._cleanup_success: bool = False

        # Vocabulary and snippets
        self._vocab: Optional[VocabularyDictionary] = None
        self._snippets: Optional[SnippetExpander] = None
        self._adaptive_store: Optional[AdaptiveStore] = None
        self._command_processor: Optional[DefaultCommandProcessor] = None

        # ── v2: Adaptive correction tracking ────────────────────────
        self._potential_wrong_term: Optional[str] = None
        self._undo_timestamp: float = 0

        # ── v2 streaming state ──────────────────────────────────────
        self._streaming_enabled: bool = False
        self._stream_queue: asyncio.Queue[bytes | object] = asyncio.Queue()
        self._stream_task: Optional[asyncio.Task[None]] = None
        self._stream_final_segment: Optional[TranscriptSegment] = None
        self._stream_final_event: asyncio.Event = asyncio.Event()

        # ── v2 pipelined cleanup state (WB-04) ──────────────────────
        self._pipelined_cleanup_enabled: bool = False
        self._cleaned_segments: list[str] = []
        self._pipelined_cleanup_tasks: list[asyncio.Task[None]] = []

        # ── v2 context engine state (CX-05) ─────────────────────────
        self._active_app_detector: Optional[ActiveAppDetector] = None
        self._profile_resolver: Optional[ProfileResolver] = None
        self._language_resolver: Optional[LanguageResolver] = None
        self._context_enabled: bool = False
        self._resolved_style: Optional[str] = None
        self._resolved_app_name: Optional[str] = None
        self._resolved_language: Optional[str] = None

        # ── v3 vision (screenshot-to-text) state ────────────────────
        self._vision_enabled: bool = False
        self._vision_provider: Optional["VisionProvider"] = None
        self._anchor_splicer: Optional[AnchorSplicer] = None

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

        # v2: detect streaming mode
        self._streaming_enabled = self._asr_provider.supports_streaming()

        # v2: detect pipelined cleanup eligibility (WB-04)
        self._pipelined_cleanup_enabled = (
            self._streaming_enabled
            and self._config.cleanup.streaming
            and self._config.cleanup.style != "technical"
        )

        # Register event bus subscriptions
        self._event_bus.subscribe(RecordingStoppedEvent, self._on_recording_stopped)

        # v2: subscribe to audio chunk events for streaming
        if self._streaming_enabled:
            self._event_bus.subscribe(AudioChunkEvent, self._on_audio_chunk)

        # v2: subscribe to segment finalized for pipelined cleanup
        if self._pipelined_cleanup_enabled:
            self._event_bus.subscribe(SegmentFinalizedEvent, self._on_segment_finalized)

        # v2: Initialize context engine (CX-05)
        self._context_enabled = self._config.context.enabled
        if self._context_enabled:
            self._active_app_detector = ActiveAppDetector()
            self._profile_resolver = ProfileResolver(profiles=dict(self._config.context.profiles))
            self._language_resolver = LanguageResolver()
            if self._active_app_detector.is_available():
                logger.info("Context engine enabled with app detection")
            else:
                logger.warning(
                    "Context engine enabled but app detection not available on this platform"
                )

        # v3: Initialize vision (screenshot-to-text)
        self._vision_enabled = self._config.vision.enabled
        if self._vision_enabled:
            self._vision_provider = self._registry.get_vision(self._config.vision)
            self._anchor_splicer = AnchorSplicer(self._config.vision.anchor_phrases)
            if not self._vision_provider.is_available():
                logger.warning(
                    "Vision provider '%s' reports unavailable at startup",
                    self._vision_provider.get_name(),
                )
            if self._screenshot_capturer is None or not self._screenshot_capturer.is_available():
                logger.warning(
                    "Vision enabled but screenshot capture is unavailable on this platform"
                )
            logger.info("Vision enabled (provider=%s)", self._vision_provider.get_name())

        # v2: background warm-up
        if self._config.asr.warm_up:
            asyncio.create_task(self._run_warmup())

        self._running = True
        logger.info(
            "Orchestrator started. ASR=%s Cleanup=%s Insertion=%s Streaming=%s Vision=%s",
            self._asr_provider.get_name(),
            self._cleanup_provider.get_name(),
            self._insertion_strategy.get_name(),
            self._streaming_enabled,
            self._vision_enabled,
        )

    async def stop(self) -> None:
        """Clean up resources and stop all background tasks."""
        logger.info("Orchestrator stopping…")
        self._running = False

        # Cancel streaming task if active
        self._cancel_streaming_task()

        # Cancel pipelined cleanup tasks
        for task in self._pipelined_cleanup_tasks:
            if not task.done():
                task.cancel()
        self._pipelined_cleanup_tasks.clear()

        # Cancel error timer if active
        if self._error_timer_task is not None and not self._error_timer_task.done():
            self._error_timer_task.cancel()
            self._error_timer_task = None

        logger.info("Orchestrator stopped")

    def _init_vocab_snippets(self) -> None:
        """Initialize vocabulary dictionary and snippet expander from config."""
        vocab_cfg = self._config.vocabulary
        snippet_cfg = self._config.snippets
        adaptive_cfg = self._config.adaptive
        commands_cfg = self._config.commands

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

        # v2: Initialize adaptive store and merge learned vocab
        if adaptive_cfg.enabled:
            self._adaptive_store = AdaptiveStore(
                learned_vocab_path=adaptive_cfg.learned_vocab_path,
                promote_threshold=adaptive_cfg.promote_threshold,
            )
            learned_terms = self._adaptive_store.get_terms()
            if learned_terms:
                self._vocab.add_terms(learned_terms)

            learned_mappings = self._adaptive_store.get_mappings()
            self._vocab.add_mappings(learned_mappings)

            if learned_terms or learned_mappings:
                logger.info(
                    "Learned vocabulary merged (%d terms, %d mappings)",
                    len(learned_terms),
                    len(learned_mappings),
                )

        if snippet_cfg.path:
            try:
                self._snippets = SnippetExpander(path=snippet_cfg.path)
                logger.info("Snippets loaded (%d triggers)", len(self._snippets.mapping))
            except Exception:
                logger.exception("Failed to load snippets")
                self._snippets = SnippetExpander()
        else:
            self._snippets = SnippetExpander()

        # v2: Initialize command processor
        if commands_cfg.enabled:
            self._command_processor = DefaultCommandProcessor(phrase_overrides=commands_cfg.phrases)
            logger.info("Voice commands enabled")

    # ── v2: Background warm-up ──────────────────────────────────────

    async def _run_warmup(self) -> None:
        """Run background warm-up and emit ``WarmupCompleteEvent``."""
        t0 = time.perf_counter()
        asr_ready = False
        cleanup_ready = False

        try:
            if self._asr_provider is not None:
                await self._asr_provider.warm_up()
                asr_ready = True
        except Exception:
            logger.exception("ASR warm-up failed")

        try:
            if self._cleanup_provider is not None:
                await self._cleanup_provider.warm_up()
                cleanup_ready = True
        except Exception:
            logger.exception("Cleanup warm-up failed")

        # v3: warm the vision provider's connection pool too (best-effort).
        if self._vision_enabled and self._vision_provider is not None:
            try:
                await self._vision_provider.warm_up()
            except Exception:
                logger.exception("Vision warm-up failed")

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        self._event_bus.publish(
            WarmupCompleteEvent(
                asr_ready=asr_ready,
                cleanup_ready=cleanup_ready,
                duration_ms=elapsed_ms,
            )
        )
        logger.info(
            "Warm-up complete in %d ms (asr=%s, cleanup=%s)",
            elapsed_ms,
            asr_ready,
            cleanup_ready,
        )

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

        # v2: Track for adaptive correction heuristic
        if self._last_transcript:
            self._potential_wrong_term = self._last_transcript
            self._undo_timestamp = time.perf_counter()
            logger.debug(
                "Undo detected; tracking '%s' for potential correction", self._potential_wrong_term
            )

        return await self._insertion_strategy.undo_last()

    # ── v2: Streaming Event Handlers ─────────────────────────────────

    async def _on_audio_chunk(self, event: AudioChunkEvent) -> None:
        """Handle an incoming audio chunk for streaming ASR.

        Audio chunks are published by the AudioChunker during recording.
        They are fed into the streaming queue for the ASR provider.

        The streaming task is started lazily on the first non-flush chunk,
        ensuring it is active before significant audio arrives.
        """
        if not self._streaming_enabled:
            return

        if event.is_flush:
            # Forward any remaining audio in the flush delta before signalling
            # end-of-stream, so the last partial seconds are not lost.
            if event.data:
                self._stream_queue.put_nowait(event.data)
            self._stream_queue.put_nowait(_STREAM_END)
        else:
            # Lazy-start the streaming task on first chunk.
            # Read sample_rate from the event here — _current_sample_rate is
            # still 0 at this point (RecordingStoppedEvent has not fired yet).
            if self._stream_task is None:
                self._current_sample_rate = event.sample_rate
                self._stream_task = asyncio.create_task(self._run_streaming_asr())

            self._stream_queue.put_nowait(event.data)

    # ── v2: Context Resolution (CX-05) ─────────────────────────────────

    def _resolve_context(self) -> None:
        """Resolve the current context and fold into cleanup hints.

        Called before each cleanup pass. The resolved style overrides the
        global configured style when context is enabled and detection succeeds.
        """
        self._resolved_style = None
        self._resolved_app_name = None
        self._resolved_language = None

        if not self._context_enabled:
            return

        app_name: Optional[str] = None
        window_title: Optional[str] = None

        if self._active_app_detector is not None and self._active_app_detector.is_available():
            app_name, window_title = self._active_app_detector.detect()

        if app_name and self._profile_resolver is not None:
            resolved_style = self._profile_resolver.resolve(app_name)
        else:
            resolved_style = None

        if self._language_resolver is not None:
            language = self._language_resolver.get_hint()
        else:
            language = None

        # Publish for observability
        self._event_bus.publish(
            ContextResolvedEvent(
                app_name=app_name,
                style=resolved_style,
                language=language,
            )
        )

        self._resolved_style = resolved_style
        self._resolved_app_name = app_name
        self._resolved_language = language

        logger.info(
            "Context resolved: app=%r  style=%s  language=%s",
            app_name,
            resolved_style or "(global)",
            language or "auto",
        )

    # ── v2: Pipelined Cleanup Handler (WB-04) ────────────────────────

    async def _on_segment_finalized(self, event: SegmentFinalizedEvent) -> None:
        """Handle a finalized segment from streaming ASR for pipelined cleanup.

        When ``cleanup.streaming`` is enabled and style is not ``technical``,
        each finalized segment is submitted to cleanup while the user is still
        speaking. Cleaned segments are accumulated; on recording stop only the
        trailing segment needs processing.
        """
        if not self._pipelined_cleanup_enabled:
            return

        text = event.text
        if not text.strip():
            return

        task = asyncio.create_task(self._clean_segment(text, event.index))
        self._pipelined_cleanup_tasks.append(task)

    async def _clean_segment(self, text: str, index: int) -> None:
        """Clean a single finalized segment and store the result."""
        assert self._cleanup_provider is not None

        cleanup_context = CleanupContext(
            style=self._config.cleanup.style,
            preserve_code=self._config.cleanup.preserve_code,
        )
        try:
            cleaned = await self._cleanup_provider.rewrite(text, context=cleanup_context)
            self._cleaned_segments.append(cleaned)
            logger.debug("Segment %d cleaned: %s", index, cleaned[:50])
        except Exception:
            logger.debug("Segment %d cleanup failed, using raw", index)
            self._cleaned_segments.append(text)

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
        """Execute the full ASR → vocabulary → snippets → cleanup → insertion pipeline.

        When streaming is enabled and a streaming task is active, it first
        waits for the streaming final segment before proceeding with the
        v1 pipeline stages (vocab → snippets → cleanup → insertion).

        When pipelined cleanup is active (``cleanup.streaming`` enabled and
        style ≠ ``technical``), accumulated segment cleanups are joined and
          only the trailing portion needs processing at stop time.
        """
        try:
            # If streaming was active, wait for the final segment
            if self._streaming_enabled and self._stream_task is not None:
                await self._stream_final_event.wait()
                self._stream_final_event.clear()

                if self._stream_final_segment is not None:
                    text = self._stream_final_segment.text
                    self._current_transcript = text
                    self._event_bus.publish(TranscriptEvent(text=text, is_final=True))

                    result = self._state_machine.transition("TranscriptEvent", is_final=True)
                    if result.transitioned:
                        self._emit_state_change("transcribing", result.new_state)

                    # WB-04: if pipelined cleanup was active, join accumulated segments.
                    # When screenshots were captured we skip this fast path and fall
                    # through to the unified path so vision splicing + a final cleanup
                    # (with preserve_code) run over the whole merged text.
                    if (
                        self._pipelined_cleanup_enabled
                        and self._cleaned_segments
                        and not self._has_screenshots()
                    ):
                        # Wait for any in-flight segment cleanups to complete
                        for task in self._pipelined_cleanup_tasks:
                            if not task.done():
                                await task
                        self._pipelined_cleanup_tasks.clear()

                        # v2: Voice commands on the final joined text?
                        # Or maybe commands should have been handled per-segment?
                        # The spec says "on the final transcript".

                        # Step 1.5: Commands and Adaptive Vocab
                        should_stop, text = self._process_commands_and_adaptive(text)
                        if should_stop:
                            return

                        # Clean the trailing portion
                        trailing_clean = await self._run_cleanup(text)

                        # Join all cleaned segments: accumulated + trailing
                        all_cleaned = self._cleaned_segments + [trailing_clean]
                        cleaned_text = " ".join(all_cleaned)

                        # Apply vocabulary + snippets on top
                        corrected_text = self._apply_vocabulary(cleaned_text)
                        expanded_text = self._expand_snippets(corrected_text)
                        await self._run_insertion(expanded_text)
                        return
                else:
                    # No final segment = error path
                    logger.warning("Streaming produced no final segment, falling back to batch")
                    await self._run_asr()
            else:
                # v1 batch path
                await self._run_asr()

            text = self._current_transcript or ""

            # Step 1.5: Commands and Adaptive Vocab
            should_stop, text = self._process_commands_and_adaptive(text)
            if should_stop:
                return

            # Step 2: Vocabulary substitution
            corrected_text = self._apply_vocabulary(text)

            # Step 3: Snippet expansion
            expanded_text = self._expand_snippets(corrected_text)

            # Step 3.5: v3 vision — splice screenshot extractions at anchors
            expanded_text, had_vision = await self._apply_vision(expanded_text)

            # Step 4: Cleanup (force preserve_code when vision content is present
            # so markdown tables and values survive the rewrite)
            cleaned_text = await self._run_cleanup(expanded_text, force_preserve_code=had_vision)

            # Step 5: Insertion
            await self._run_insertion(cleaned_text)

        except Exception:
            logger.exception("Unhandled pipeline error")
            self._transition_or_emit_error("pipeline", "Unhandled pipeline error", False)
        finally:
            # Always reset streaming state so the next dictation starts clean.
            # Without this, _stream_task stays non-None and the second
            # streaming dictation would hang forever on _stream_final_event.
            self._reset_streaming_state()

    def _process_commands_and_adaptive(self, text: str) -> tuple[bool, str]:
        """Check for voice commands and adaptive vocabulary corrections.

        Returns:
            (should_stop_pipeline, text_to_continue_with)
        """
        # Adaptive vocab correction check
        self._check_for_correction(text)

        # Voice commands
        return self._run_commands(text)

    def _run_commands(self, transcript: str) -> tuple[bool, str]:
        """Run command processor on the transcript.

        Returns (should_stop_pipeline, remaining_text).
        """
        if self._command_processor is None or not transcript:
            return False, transcript

        result = self._command_processor.process(transcript)
        if not result.matched:
            return False, transcript

        self._event_bus.publish(
            CommandRecognizedEvent(action=result.action, original_text=transcript)
        )  # type: ignore
        logger.info("Voice command recognized: %s", result.action)

        if result.action == "newline":
            asyncio.create_task(self._insertion_strategy.insert("\n"))  # type: ignore
        elif result.action == "paragraph":
            asyncio.create_task(self._insertion_strategy.insert("\n\n"))  # type: ignore
        elif result.action in ("delete_last", "undo"):
            asyncio.create_task(self.undo_last_insertion())
        elif result.action == "capitalize":
            if result.remaining_text:
                return False, result.remaining_text.capitalize()
            elif self._last_transcript:
                asyncio.create_task(self._redo_capitalized(self._last_transcript))
                return True, ""

        if result.remaining_text:
            return False, result.remaining_text

        return True, ""

    async def _redo_capitalized(self, text: str) -> None:
        """Undo last insertion and re-insert it capitalized."""
        if await self.undo_last_insertion():
            await self._run_insertion(text.capitalize())

    def _check_for_correction(self, transcript: str) -> None:
        """Check if the current transcript is a correction of a recently undone insertion."""
        if not self._adaptive_store or not self._potential_wrong_term:
            return

        elapsed = time.perf_counter() - self._undo_timestamp
        # 30 seconds — generous enough for streaming + CPU pipelines where the
        # full speak→transcribe cycle can take 10–15 s.
        if elapsed > 30.0:
            logger.info(
                "Adaptive: correction window expired (%.1f s since undo) — ignoring", elapsed
            )
            self._potential_wrong_term = None
            return

        wrong = self._potential_wrong_term
        right = transcript.strip()

        if wrong.lower() == right.lower():
            # Same text re-dictated — not a real correction, clear and move on.
            logger.debug("Adaptive: same text re-dictated, not a correction")
            self._potential_wrong_term = None
            return

        logger.info(
            "Adaptive: recording correction '%s' → '%s' (%.1f s elapsed)", wrong, right, elapsed
        )
        promoted = self._adaptive_store.record_correction(wrong, right)

        self._event_bus.publish(CorrectionLearnedEvent(wrong=wrong, right=right, promoted=promoted))

        if promoted:
            logger.info("Adaptive: promoted '%s' → '%s' to live vocabulary", wrong, right)
            if self._vocab:
                self._vocab.add_mapping(wrong, right)

        self._potential_wrong_term = None

    # ── Pipeline Steps ───────────────────────────────────────────────

    async def _run_asr(self) -> None:
        """Transcribe the captured audio with retry logic (§6.3).

        Uses the v1 batch path (``transcribe_audio``). The streaming path
        is handled separately via ``_run_streaming_asr``.
        """
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

    async def _run_cleanup(self, transcript: str, force_preserve_code: bool = False) -> str:
        """Clean the transcript with retry logic (§6.3).

        Args:
            transcript: Text to clean.
            force_preserve_code: When True, force ``preserve_code`` on regardless
                of config — used when spliced screenshot extractions (markdown
                tables, values) must survive the rewrite intact.
        """
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

        # Resolve context before building CleanupContext
        self._resolve_context()
        style = self._resolved_style if self._resolved_style else self._config.cleanup.style

        preserve_code = self._config.cleanup.preserve_code or force_preserve_code
        cleanup_context = CleanupContext(
            style=style,
            preserve_code=preserve_code,
            app_name=self._resolved_app_name,
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
            from agentvoca.insertion.clipboard import (  # noqa: PLC0415
                ClipboardInsertionStrategy,
            )

            clipboard = ClipboardInsertionStrategy(self._config.insertion)
            return await clipboard.insert(text)
        except Exception as exc:
            logger.warning("Clipboard fallback failed: %s", exc)
            return InsertionResult(success=False, method_used="clipboard", error=str(exc))

    # ── Streaming ASR ─────────────────────────────────────────────────

    async def _run_streaming_asr(self) -> None:
        """Background task that consumes audio chunks from the queue and
        feeds them to the ASR provider's ``stream_transcribe``.

        Yields partial transcripts as ``PartialTranscriptEvent`` and stores
        the final segment for the pipeline.
        """
        assert self._asr_provider is not None

        self._stream_final_segment = None
        self._stream_final_event.clear()

        # Create an async iterator from the queue
        async def audio_chunk_iter() -> AsyncIterator[bytes]:
            while True:
                item = await self._stream_queue.get()
                if item is _STREAM_END:
                    return
                yield item  # type: ignore[misc]

        segment_index = 0
        try:
            async for segment in self._asr_provider.stream_transcribe(
                audio_chunk_iter(),
                sample_rate=self._current_sample_rate,
            ):
                # CX-04: Feed detected language to language resolver
                if segment.language_detected and self._language_resolver is not None:
                    self._language_resolver.update(segment.language_detected)

                if segment.is_final:
                    self._stream_final_segment = segment
                    self._event_bus.publish(
                        SegmentFinalizedEvent(text=segment.text, index=segment_index)
                    )
                else:
                    # Publish partial transcript for live overlay
                    self._event_bus.publish(PartialTranscriptEvent(text=segment.text))
                    segment_index += 1
        except Exception:
            logger.exception("Streaming ASR failed")

        # Signal that the streaming task is complete
        self._stream_final_event.set()

    def _cancel_streaming_task(self) -> None:
        """Cancel the active streaming task if one exists."""
        if self._stream_task is not None and not self._stream_task.done():
            self._stream_task.cancel()
            self._stream_task = None

    def _reset_streaming_state(self) -> None:
        """Reset all per-recording streaming and pipelined-cleanup state.

        Safe to call from the loop thread between dictations. Cancels any
        lingering streaming task, clears the final segment/event, drains the
        chunk queue, and clears accumulated cleaned segments.
        """
        self._cancel_streaming_task()
        self._stream_task = None
        self._stream_final_segment = None
        self._stream_final_event.clear()
        self._cleaned_segments = []
        for task in self._pipelined_cleanup_tasks:
            if not task.done():
                task.cancel()
        self._pipelined_cleanup_tasks = []
        # Drain any leftover chunk-queue items from a cancelled recording.
        while True:
            try:
                self._stream_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def prepare_for_recording(self) -> None:
        """Reset streaming state at the start of a new recording.

        Called (scheduled on the loop) when recording starts so that a prior
        cancelled or completed streaming session cannot leak stale state into
        the next dictation.
        """
        self._reset_streaming_state()
        # v3: drop any screenshots left over from a prior/cancelled session.
        if self._screenshot_capturer is not None:
            self._screenshot_capturer.clear()

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

    # ── v3: Vision (screenshot-to-text) ──────────────────────────────

    def _has_screenshots(self) -> bool:
        """Return True if vision is on and screenshots are queued/in flight."""
        return (
            self._vision_enabled
            and self._screenshot_capturer is not None
            and self._screenshot_capturer.has_pending()
        )

    async def _apply_vision(self, text: str) -> tuple[str, bool]:
        """Extract any captured screenshots and splice them into ``text``.

        Returns ``(text, had_vision)`` where ``had_vision`` is True only when at
        least one extraction was spliced in. The spoken ``text`` doubles as the
        extraction instruction so the VLM infers the output format.
        """
        if (
            not self._vision_enabled
            or self._screenshot_capturer is None
            or self._vision_provider is None
            or self._anchor_splicer is None
        ):
            return text, False

        # The user may still be dragging a selection — wait briefly off-loop.
        if self._screenshot_capturer.has_pending():
            await asyncio.to_thread(self._screenshot_capturer.wait_idle, _VISION_CAPTURE_GRACE_S)

        shots = self._screenshot_capturer.drain()
        if not shots:
            return text, False

        t0 = time.perf_counter()
        context = VisionContext(
            instruction=text,
            preserve_code=self._config.cleanup.preserve_code,
            app_name=self._resolved_app_name,
            output_format=self._config.vision.output_format,
        )

        extractions: list[str] = []
        for shot in shots:
            try:
                extracted = await self._vision_provider.extract(
                    shot, instruction=text, context=context
                )
            except VisionError as exc:
                logger.warning("Vision extraction failed for a screenshot: %s", exc)
                continue
            if extracted and extracted.strip():
                extractions.append(extracted.strip())

        if not extractions:
            return text, False

        spliced, anchors_matched = self._anchor_splicer.splice(text, extractions)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        self._event_bus.publish(TimingEvent(stage="vision", duration_ms=elapsed_ms))
        self._event_bus.publish(
            VisionExtractedEvent(
                count=len(extractions),
                anchors_matched=anchors_matched,
                latency_ms=elapsed_ms,
            )
        )
        logger.info(
            "Vision: %d screenshot(s) extracted, %d anchor(s) matched (%d ms)",
            len(extractions),
            anchors_matched,
            elapsed_ms,
        )
        return spliced, True

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

    # ── Hot-apply (v0.3.5 settings UI) ─────────────────────────────────
    #
    # ``apply_config_update`` is called by ``main.py`` after the user saves a
    # change in the settings window. Fields classified as hot by
    # ``setup.controllers.restart_policy`` are re-applied here without
    # restarting the pipeline; restart-only fields are ignored (the UI shows
    # a "restart required" banner so the user can do it themselves).

    def apply_config_update(self, new_config: "FullConfig") -> None:
        """Hot-apply every supported field from ``new_config``.

        Restart-only fields (ASR provider, audio device, etc.) are skipped.
        The caller is expected to surface the restart-required paths to the
        user via the settings window's banner.

        Args:
            new_config: The freshly-saved config.
        """
        from agentvoca.setup.controllers.restart_policy import is_hot_field  # noqa: PLC0415

        # ── Vocabulary: rebuild the in-memory dictionary ────────────────
        if is_hot_field("vocabulary.path") or is_hot_field("vocabulary.inline"):
            try:
                self._vocab = VocabularyDictionary(
                    path=new_config.vocabulary.path,
                    terms=new_config.vocabulary.inline,
                )
                # Re-merge any learned mappings (adaptive store may have
                # promoted corrections since last reload).
                if self._adaptive_store is not None:
                    self._vocab.add_mappings(self._adaptive_store.get_mappings())
                logger.info("Vocabulary reloaded (%d terms)", len(self._vocab.terms))
            except Exception:
                logger.exception("Failed to reload vocabulary; keeping old one")

        # ── Snippets: rebuild the expander ──────────────────────────────
        if is_hot_field("snippets.path"):
            try:
                self._snippets = SnippetExpander(path=new_config.snippets.path)
                logger.info("Snippets reloaded (%d triggers)", len(self._snippets.mapping))
            except Exception:
                logger.exception("Failed to reload snippets; keeping old ones")

        # ── Cleanup provider: re-instantiate ───────────────────────────
        if any(
            is_hot_field(f)
            for f in (
                "cleanup.provider",
                "cleanup.model",
                "cleanup.endpoint",
                "cleanup.api_key_env",
                "cleanup.style",
                "cleanup.preserve_code",
                "cleanup.custom_prompt_path",
                "cleanup.warm_up",
            )
        ):
            try:
                self._cleanup_provider = self._registry.get_cleanup(new_config.cleanup)
                if not self._cleanup_provider.is_available():
                    logger.warning(
                        "New cleanup provider '%s' reports unavailable",
                        self._cleanup_provider.get_name(),
                    )
                else:
                    logger.info("Cleanup provider reloaded: %s", self._cleanup_provider.get_name())
            except Exception:
                logger.exception("Failed to reload cleanup provider; keeping old one")

        # ── Adaptive / context / commands / vision: mostly lazy, but
        # replace the command processor and adaptive store eagerly so any
        # newly-loaded phrases/mappings take effect on the next dictation.
        if is_hot_field("commands.enabled") or is_hot_field("commands.phrases"):
            self._command_processor = DefaultCommandProcessor(
                phrase_overrides=new_config.commands.phrases
            )

        if (
            is_hot_field("adaptive.enabled")
            or is_hot_field("adaptive.promote_threshold")
            or is_hot_field("adaptive.learned_vocab_path")
        ):
            self._adaptive_store = AdaptiveStore(
                learned_vocab_path=new_config.adaptive.learned_vocab_path,
                promote_threshold=new_config.adaptive.promote_threshold,
            )

        if is_hot_field("context.enabled") or is_hot_field("context.profiles"):
            self._context_enabled = new_config.context.enabled
            if self._context_enabled and self._profile_resolver is not None:
                self._profile_resolver = ProfileResolver(profiles=dict(new_config.context.profiles))

        # Vision's runtime knobs (anchors, output_format, timeout) are read
        # lazily from ``self._config`` by ``_apply_vision``, so re-saving
        # the config instance is sufficient — no further action needed here.
