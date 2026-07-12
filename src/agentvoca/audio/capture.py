"""Audio capture using sounddevice.

Captures microphone audio with configurable device, sample rate, and
channels. Supports push-to-talk, toggle, and auto-stop modes. Emits
``AudioFrameEvent`` and ``RecordingStoppedEvent`` on the event bus.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import Optional

import numpy as np
import sounddevice as sd

from agentvoca.audio.chunker import AudioChunker
from agentvoca.audio.devices import select_device
from agentvoca.audio.vad import VAD
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import RecordingStoppedEvent
from agentvoca.utils.errors import AudioError

logger = logging.getLogger(__name__)


class AudioCapture:
    """Captures microphone audio and emits events on the event bus.

    Args:
        event_bus: Shared event bus for publishing audio events.
        sample_rate: Sample rate in Hz (default 16000).
        channels: Number of input channels (default 1).
        device_name: Device name substring or ``"default"``.
        vad: Optional VAD instance for silence detection.
        silence_timeout_ms: Silence duration before auto-stop (ms).
        max_duration_s: Maximum recording duration in seconds.
        frames_per_buffer: Number of frames per audio callback.
    """

    def __init__(
        self,
        event_bus: EventBus,
        sample_rate: int = 16000,
        channels: int = 1,
        device_name: str = "default",
        vad: Optional[VAD] = None,
        silence_timeout_ms: int = 900,
        max_duration_s: int = 120,
        frames_per_buffer: int = 1024,
        chunker: Optional[AudioChunker] = None,
        loop: Optional["asyncio.AbstractEventLoop"] = None,
    ) -> None:
        self._event_bus = event_bus
        self._sample_rate = sample_rate
        self._channels = channels
        self._device_name = device_name
        self._vad = vad
        self._silence_timeout_ms = silence_timeout_ms
        self._max_duration_s = max_duration_s
        self._frames_per_buffer = frames_per_buffer
        self._chunker = chunker
        # Persistent asyncio loop used to drive the (async) chunker lifecycle
        # from this (Qt/audio) thread. None disables streaming chunking.
        self._loop = loop

        self._stream: Optional[sd.InputStream] = None
        self._recording = False
        self._stop_requested = False
        self._audio_buffer: list[bytes] = []
        self._record_start_time: float = 0.0
        self._last_speech_time: float = 0.0

        # ── R2: VAD worker thread scaffolding ──────────────────────────
        # The audio callback thread must do near-zero work, so silero
        # inference runs on a dedicated daemon thread (``agentvoca-vad``).
        # The callback writes (audio_bytes, timestamp_ms) tuples into the
        # thread-safe queue (drop-on-full) and reads a cached bool that
        # the worker keeps current.  GIL keeps both the queue-put and the
        # bool read/write atomic for our purposes.  64-deep queue bounds
        # staleness at ~4 s in the worst case (drop-on-full fallback in
        # the callback).
        self._vad_queue: "queue.Queue[tuple[bytes, int] | None]" = queue.Queue(maxsize=64)
        # Optimistic default so we never trigger auto-stop before the
        # worker has produced its first result.
        self._last_vad_speech: bool = True
        self._vad_thread: Optional[threading.Thread] = None

    # ── Lifecycle ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Open the audio input stream.

        Raises:
            AudioError: If the selected device cannot be opened.
        """
        device = select_device(self._device_name)
        if device is None:
            raise AudioError(f"No audio input device found (configured: {self._device_name!r})")

        device_index = device["index"]
        logger.info(
            "Opening audio input: device=%s (index=%d) rate=%d channels=%d",
            device["name"],
            device_index,
            self._sample_rate,
            self._channels,
        )

        try:
            self._stream = sd.InputStream(
                device=device_index,
                samplerate=self._sample_rate,
                channels=self._channels,
                blocksize=self._frames_per_buffer,
                dtype="float32",
                callback=self._audio_callback,
            )
            self._stream.start()

            # R2: spawn the VAD worker thread alongside the audio stream.
            # Inference runs here, not on the audio callback.
            if self._vad is not None:
                self._vad_thread = threading.Thread(
                    target=self._vad_worker, name="agentvoca-vad", daemon=True
                )
                self._vad_thread.start()

            logger.info("Audio input stream started")
        except Exception as exc:
            raise AudioError(f"Failed to open audio input: {exc}") from exc

    def stop(self) -> None:
        """Close the audio input stream and join the VAD worker (R2)."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            logger.info("Audio input stream stopped")

        if self._vad_thread is not None:
            # Sentinel None terminates the worker's ``while True`` loop after
            # any items already in the queue are drained (FIFO order).
            self._vad_queue.put(None)
            self._vad_thread.join(timeout=2.0)
            self._vad_thread = None

    # ── Recording Control ──────────────────────────────────────────────

    def start_recording(self) -> None:
        """Begin capturing audio into the internal buffer."""
        self._audio_buffer = []
        self._recording = True
        self._stop_requested = False
        self._record_start_time = time.time()
        self._last_speech_time = time.time()

        # R2: drain any stale items the VAD worker hasn't consumed yet
        # from a prior recording, and reset the cached bool to optimistic.
        # Items the worker has already popped via Queue.get() but not yet
        # finished processing are dropped; their effect is bounded by the
        # queue depth and self-corrects as soon as the callback feeds the
        # first chunk of the new dictation (~64 ms later).
        self._last_vad_speech = True
        while not self._vad_queue.empty():
            try:
                self._vad_queue.get_nowait()
            except queue.Empty:
                break

        # v2: start the streaming chunker on the persistent loop.
        if self._chunker is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(self._chunker.start)
        logger.debug("Recording started")

    def stop_recording(self) -> None:
        """Stop capturing audio and emit ``RecordingStoppedEvent``.

        Cheap (callback-safe): flips flags and schedules the buffer join
        plus event publish on the asyncio loop thread. Falls back to
        inline finalization when no loop was provided (tests, headless use).
        The heavy ``b"".join(self._audio_buffer)`` runs on the loop thread
        instead of the audio callback (R3).
        """
        if not self._recording:
            return
        self._recording = False
        self._stop_requested = True

        # v2: flush + stop the streaming chunker (emits the final flush chunk).
        if self._chunker is not None and self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._chunker.stop(flush=True), self._loop)

        duration_ms = int((time.time() - self._record_start_time) * 1000)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._finalize_stop, duration_ms)
        else:
            self._finalize_stop(duration_ms)

    def _finalize_stop(self, duration_ms: int) -> None:
        """Join the buffer and publish ``RecordingStoppedEvent`` (loop thread).

        Runs after the chunker-flush coroutine has been enqueued on the same
        loop, so the AudioChunkEvent(is_flush=True) is processed before this
        publish — same ordering as the previous inline implementation.
        """
        audio_bytes = b"".join(self._audio_buffer) if self._audio_buffer else b""
        self._event_bus.publish(
            RecordingStoppedEvent(
                audio_bytes=audio_bytes,
                duration_ms=duration_ms,
                sample_rate=self._sample_rate,
            )
        )
        logger.debug("Recording stopped (%d ms, %d bytes)", duration_ms, len(audio_bytes))

    def cancel_recording(self) -> None:
        """Stop recording and discard the audio buffer.

        R6: only schedule the chunker stop if we were actively recording.
        Cancel-after-stop is harmless on this side (the buffer clear is a
        no-op on an already-cleared list) but the orchestrator side
        ``cancel()`` does the real work of tearing down the in-flight
        pipeline task and resetting streaming state.
        """
        was_recording = self._recording
        self._recording = False
        self._stop_requested = True
        self._audio_buffer = []
        if was_recording and self._chunker is not None and self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._chunker.stop(flush=False), self._loop)
        logger.debug("Recording cancelled (was_recording=%s)", was_recording)

    @property
    def is_recording(self) -> bool:
        """Return True if currently recording."""
        return self._recording

    # ── Audio Callback ─────────────────────────────────────────────────

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        timestamp: sd.CallbackStop,
        status: sd.CallbackFlags,
    ) -> None:
        """Callback invoked by sounddevice for each audio block."""
        if status:
            logger.debug("Audio callback status: %s", status)

        if not self._recording:
            return

        audio_bytes = indata.tobytes()
        timestamp_ms = int(time.time() * 1000)

        self._audio_buffer.append(audio_bytes)

        # Feed audio to chunker for streaming ASR (v2)
        if self._chunker is not None and self._chunker.is_running:
            self._chunker.add_audio(audio_bytes)

        # VAD-based silence detection for auto-stop (R2: inference off-thread).
        # The callback only enqueues the block and reads the cached bool
        # verbatim — silero never blocks the audio thread.  Drop-on-full
        # when the worker is behind so the callback never waits.
        if self._vad is not None and self._vad.is_available:
            try:
                self._vad_queue.put_nowait((audio_bytes, timestamp_ms))
            except queue.Full:
                pass  # worker is behind; skipping a block is harmless
            if self._last_vad_speech:
                self._last_speech_time = time.time()
            else:
                silence_ms = int((time.time() - self._last_speech_time) * 1000)
                if silence_ms >= self._silence_timeout_ms:
                    self.stop_recording()

        # Max duration check
        elapsed_s = time.time() - self._record_start_time
        if elapsed_s >= self._max_duration_s:
            logger.info("Max recording duration reached (%d s)", self._max_duration_s)
            self.stop_recording()

    # ── VAD worker thread (R2) ─────────────────────────────────────────────

    def _vad_worker(self) -> None:
        """Dedicated daemon thread: silero inference + speech-state cache update.

        Exits when the audio stream closes (None sentinel from ``stop()``).
        Subsequent chunks are pulled one at a time via ``Queue.get()``; a
        try/except guards each inference so a single bad chunk cannot
        terminate the loop and silently disable auto-stop.
        """
        while True:
            item = self._vad_queue.get()
            if item is None:
                return
            audio_bytes, timestamp_ms = item
            if self._vad is None or not self._vad.is_available:
                continue
            try:
                # process_chunk returns is_speech and publishes
                # VADSpeechEvent on a transition (from this worker thread,
                # which is the same cross-thread publication pattern the
                # audio callback used previously — EventBus handles it).
                self._last_vad_speech = self._vad.process_chunk(audio_bytes, timestamp_ms)
            except Exception:
                logger.debug("VAD worker inference failed", exc_info=True)
                # Fail open, same fallback behaviour VAD.is_speech uses.
                self._last_vad_speech = True
