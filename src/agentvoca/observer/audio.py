"""Observer ambient listener (v0.4.0, OBS-11).

Segments the ambient mic tap into discrete utterances using a dedicated
VAD instance. The listener owns its own VAD — see
``docs/proposals/v0.4.0-observer-mode.md`` §3 for the design rationale.

Threading
---------
- ``feed()`` runs on the sounddevice callback thread. Strictly non-blocking:
  ``put_nowait`` with drop-on-full.
- The state machine, VAD inference, and the ``on_utterance`` / ``on_speech_onset``
  callbacks all run on the single ``observer-ambient`` worker thread.
- The caller wires ``on_utterance`` to the asyncio loop with
  ``run_coroutine_threadsafe`` when the ASR arbiter lands (OBS-12 / OBS-19).

Memory
------
An utterance capped at ``max_utterance_ms`` is at most ~1.9 MB at 16 kHz
float32 (1024 frames/block * 4 bytes/frame * ~470 blocks/30 s). The
pre-roll deque adds at most ``preroll_ms`` worth of blocks. Both bounded.
"""

from __future__ import annotations

import asyncio
import logging
import math
import queue
import threading
from collections import deque
from typing import Callable, Optional, Protocol

from agentvoca.audio.vad import VAD
from agentvoca.core.event_bus import EventBus

logger = logging.getLogger(__name__)

_SENTINEL_STOP = object()
_SENTINEL_FLUSH = object()


class VADLike(Protocol):
    """Anything the AmbientListener can use to detect speech in a block.

    The shipped ``agentvoca.audio.vad.VAD`` satisfies this; tests pass a
    scripted stub that returns a deterministic sequence of speech/silence
    decisions without loading silero.
    """

    @property
    def is_available(self) -> bool: ...
    def process_chunk(self, audio_bytes: bytes, timestamp_ms: int) -> bool: ...


class AmbientListener:
    """Turns the ambient mic tap into discrete utterances.

    Args:
        event_bus: The shared event bus (used for diagnostics; not required
            for emission — that goes through ``on_utterance``).
        loop: The asyncio loop on which transcription coroutines will be
            scheduled by the caller (passed back via ``on_utterance``).
        on_utterance: Called on the worker thread with
            ``(audio_bytes, ts_ms, duration_ms)`` for every emitted
            utterance. Exceptions are logged and swallowed.
        sample_rate: Audio sample rate in Hz. Default 16000.
        frames_per_block: Frames per sounddevice callback block. Default 1024.
        silence_timeout_ms: Silence duration that closes an utterance. Default 900.
        min_utterance_ms: Utterances shorter than this are dropped
            (coughs, chair creaks, keyboard noise). Default 400.
        max_utterance_ms: Cap on a single utterance's duration. Continuous
            speech past this emits and immediately re-enters SPEAKING.
        queue_depth: Depth of the audio block queue. 64 ≈ 4 s at 64 ms blocks.
        preroll_ms: Audio kept before the VAD speech flip so the first
            word is not clipped.
        on_speech_onset: Optional callable invoked exactly once per
            utterance at the IDLE→SPEAKING transition. Same thread as
            ``on_utterance``.
        vad: Optional VAD-like instance. ``None`` (default) creates an
            own VAD with no event bus (so it does not publish
            ``VADSpeechEvent`` — the dictation VAD owns that event).
    """

    def __init__(
        self,
        event_bus: EventBus,
        loop: asyncio.AbstractEventLoop,
        on_utterance: Callable[[bytes, int, int], None],
        *,
        sample_rate: int = 16000,
        frames_per_block: int = 1024,
        silence_timeout_ms: int = 900,
        min_utterance_ms: int = 400,
        max_utterance_ms: int = 30000,
        queue_depth: int = 64,
        preroll_ms: int = 300,
        on_speech_onset: Optional[Callable[[], None]] = None,
        vad: Optional[VADLike] = None,
    ) -> None:
        self._event_bus = event_bus
        self._loop = loop
        self._on_utterance = on_utterance
        self._sample_rate = sample_rate
        self._frames_per_block = frames_per_block
        self._block_duration_ms = (frames_per_block * 1000.0) / float(sample_rate)
        self._silence_timeout_ms = silence_timeout_ms
        self._min_utterance_ms = min_utterance_ms
        self._max_utterance_ms = max_utterance_ms
        self._on_speech_onset = on_speech_onset
        self._vad: Optional[VADLike] = vad
        self._owns_vad = vad is None
        # Pre-roll deque size in blocks. Ceil so a 300 ms preroll on 64 ms
        # blocks yields 5 blocks; the floor ensures at least one.
        preroll_blocks = max(1, int(math.ceil(preroll_ms / self._block_duration_ms)))
        self._preroll_blocks = preroll_blocks
        self._queue: queue.Queue = queue.Queue(maxsize=queue_depth)
        self._thread: Optional[threading.Thread] = None
        # State machine — only the worker thread touches these.
        self._state: str = "IDLE"
        self._preroll: deque[tuple[bytes, int]] = deque(maxlen=preroll_blocks)
        self._utterance: list[bytes] = []
        self._utterance_start_ts_ms: int = 0
        self._silence_start_ts_ms: Optional[int] = None
        self._last_ts_ms: int = 0
        self._utterance_count: int = 0

    # ── Public API ──────────────────────────────────────────────────

    def feed(self, audio_bytes: bytes, timestamp_ms: int) -> None:
        """AmbientSink impl. Runs on the sounddevice callback thread.

        Strictly non-blocking: ``put_nowait`` with drop-on-full.
        """
        try:
            self._queue.put_nowait((audio_bytes, timestamp_ms))
        except queue.Full:
            pass  # Worker is behind; drop the block. The 5% budget wins.

    def start(self) -> None:
        """Spawn the worker thread. Idempotent.

        Loads the own VAD if one was not injected. The injected path is
        used by tests to skip silero entirely.
        """
        if self._thread is not None and self._thread.is_alive():
            return
        if self._vad is None:
            # Own VAD — no event_bus so it does not publish VADSpeechEvent
            # (the dictation VAD owns that event on the main bus).
            self._vad = VAD(event_bus=None, sample_rate=self._sample_rate)
        self._thread = threading.Thread(
            target=self._worker_loop, name="observer-ambient", daemon=True
        )
        self._thread.start()
        logger.debug("AmbientListener started")

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the worker thread and release the own VAD if any."""
        if self._thread is None:
            return
        # Enqueue the stop sentinel. If the queue is full (worker behind),
        # drain pending items first so the sentinel lands at the head of
        # the worker's next iteration.
        try:
            self._queue.put_nowait(_SENTINEL_STOP)
        except queue.Full:
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            self._queue.put(_SENTINEL_STOP)
        self._thread.join(timeout=timeout)
        self._thread = None
        if self._owns_vad and self._vad is not None:
            stop = getattr(self._vad, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    logger.debug("VAD stop raised", exc_info=True)
        logger.debug("AmbientListener stopped")

    def flush(self) -> None:
        """Force-emit any in-progress utterance.

        Test barrier; also called at session stop so the user's last
        sentence is not lost.
        """
        # The flush sentinel is small; bypass the queue by replacing the
        # oldest item if needed.
        try:
            self._queue.put_nowait(_SENTINEL_FLUSH)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put(_SENTINEL_FLUSH)

    @property
    def utterance_count(self) -> int:
        """Number of utterances emitted since construction."""
        return self._utterance_count

    # ── Worker ──────────────────────────────────────────────────────

    def _ensure_vad_loaded(self) -> None:
        """Load the owned VAD's model. Runs on the worker thread.

        Constructing a ``VAD`` does not load silero — ``VAD.start()`` does,
        and ``is_available`` stays False until it has run. Without this
        the worker below discarded every single block at DEBUG level, so
        Observer heard nothing and every session exported as empty.

        The load takes ~1 s of torch work, which is why it happens here
        rather than in ``start()``: the Qt thread must not pay for it. An
        injected VAD belongs to the caller, who is responsible for having
        loaded it.
        """
        if not self._owns_vad or self._vad is None or self._vad.is_available:
            return
        start = getattr(self._vad, "start", None)
        if not callable(start):
            return
        try:
            asyncio.run(start())
        except Exception:
            logger.warning(
                "AmbientListener: silero VAD failed to load; ambient speech will not be segmented",
                exc_info=True,
            )

    def _worker_loop(self) -> None:
        """Owned by the worker thread. Drains the queue, runs VAD."""
        assert self._vad is not None
        self._ensure_vad_loaded()
        while True:
            item = self._queue.get()
            if item is _SENTINEL_STOP:
                # Drain any in-progress utterance before exiting.
                if self._state == "SPEAKING":
                    self._emit_utterance()
                return
            if item is _SENTINEL_FLUSH:
                if self._state == "SPEAKING":
                    self._emit_utterance()
                self._reset_to_idle()
                continue
            audio_bytes, ts_ms = item
            if not self._vad.is_available:
                # No VAD → cannot segment. Drop the block; this is a
                # misconfiguration logged at DEBUG.
                logger.debug("VAD unavailable in AmbientListener; dropping block")
                continue
            self._process_block(audio_bytes, ts_ms)

    def _process_block(self, audio_bytes: bytes, ts_ms: int) -> None:
        """One step of the state machine. Worker thread only."""
        self._last_ts_ms = ts_ms
        is_speech = self._vad.process_chunk(audio_bytes, ts_ms)
        if self._state == "IDLE":
            # Pre-roll holds the audio BEFORE the speech trigger. The
            # current block is the start of the speech and is appended
            # to the utterance below — do NOT also put it in pre-roll.
            if is_speech:
                # Transition IDLE→SPEAKING. Buffer starts with the
                # pre-roll so the first word is not clipped, then
                # includes the current block.
                self._utterance = [b for b, _ in self._preroll]
                self._utterance.append(audio_bytes)
                if self._preroll:
                    self._utterance_start_ts_ms = self._preroll[0][1]
                else:
                    self._utterance_start_ts_ms = ts_ms
                self._preroll.clear()
                self._silence_start_ts_ms = None
                self._state = "SPEAKING"
                if self._on_speech_onset is not None:
                    try:
                        self._on_speech_onset()
                    except Exception:
                        logger.debug("on_speech_onset raised", exc_info=True)
                return
            # Still idle and still silent — extend the pre-roll.
            self._preroll.append((audio_bytes, ts_ms))
            return
        # SPEAKING
        self._utterance.append(audio_bytes)
        if is_speech:
            self._silence_start_ts_ms = None
        else:
            if self._silence_start_ts_ms is None:
                self._silence_start_ts_ms = ts_ms
            if (ts_ms - self._silence_start_ts_ms) >= self._silence_timeout_ms:
                self._emit_utterance()
                self._reset_to_idle()
                return
        if (ts_ms - self._utterance_start_ts_ms) >= self._max_utterance_ms:
            # Continuous speech past the cap — emit and immediately
            # re-enter SPEAKING so a long monologue is split.
            self._emit_utterance()
            self._utterance = [audio_bytes]
            self._utterance_start_ts_ms = ts_ms
            self._silence_start_ts_ms = None

    def _emit_utterance(self) -> None:
        """Concatenate buffered blocks and call the user callback."""
        if not self._utterance:
            return
        audio = b"".join(self._utterance)
        duration_ms = max(0, self._last_ts_ms - self._utterance_start_ts_ms)
        if duration_ms < self._min_utterance_ms:
            logger.debug(
                "AmbientListener: dropping %d-ms utterance (below min_utterance_ms=%d)",
                duration_ms,
                self._min_utterance_ms,
            )
            self._utterance = []
            return
        self._utterance_count += 1
        try:
            self._on_utterance(audio, self._utterance_start_ts_ms, duration_ms)
        except Exception:
            logger.debug("on_utterance raised", exc_info=True)
        self._utterance = []

    def _reset_to_idle(self) -> None:
        self._state = "IDLE"
        self._utterance = []
        self._silence_start_ts_ms = None
        self._preroll.clear()
