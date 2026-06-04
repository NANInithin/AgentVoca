"""Audio capture using sounddevice.

Captures microphone audio with configurable device, sample rate, and
channels. Supports push-to-talk, toggle, and auto-stop modes. Emits
``AudioFrameEvent`` and ``RecordingStoppedEvent`` on the event bus.
"""

from __future__ import annotations

import asyncio
import logging
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

        # Async queue for delivering audio frames to the event bus
        self._frame_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._frame_task: Optional[asyncio.Task[None]] = None

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
            logger.info("Audio input stream started")
        except Exception as exc:
            raise AudioError(f"Failed to open audio input: {exc}") from exc

    def stop(self) -> None:
        """Close the audio input stream."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            logger.info("Audio input stream stopped")

    # ── Recording Control ──────────────────────────────────────────────

    def start_recording(self) -> None:
        """Begin capturing audio into the internal buffer."""
        self._audio_buffer = []
        self._recording = True
        self._stop_requested = False
        self._record_start_time = time.time()
        self._last_speech_time = time.time()
        # v2: start the streaming chunker on the persistent loop.
        if self._chunker is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(self._chunker.start)
        logger.debug("Recording started")

    def stop_recording(self) -> None:
        """Stop capturing audio and emit ``RecordingStoppedEvent``."""
        if not self._recording:
            return
        self._recording = False
        self._stop_requested = True

        # v2: flush + stop the streaming chunker (emits the final flush chunk).
        if self._chunker is not None and self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._chunker.stop(flush=True), self._loop)

        duration_ms = int((time.time() - self._record_start_time) * 1000)
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
        """Stop recording and discard the audio buffer."""
        self._recording = False
        self._stop_requested = True
        self._audio_buffer = []
        # v2: stop the chunker WITHOUT flushing so no final segment is produced.
        if self._chunker is not None and self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._chunker.stop(flush=False), self._loop)
        logger.debug("Recording cancelled")

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

        # VAD-based silence detection for auto-stop
        if self._vad is not None and self._vad.is_available:
            self._vad.process_chunk(audio_bytes, timestamp_ms)
            if not self._vad.is_speech(audio_bytes):
                # Silence detected — check timeout
                silence_ms = int((time.time() - self._last_speech_time) * 1000)
                if silence_ms >= self._silence_timeout_ms:
                    self.stop_recording()
            else:
                self._last_speech_time = time.time()

        # Max duration check
        elapsed_s = time.time() - self._record_start_time
        if elapsed_s >= self._max_duration_s:
            logger.info("Max recording duration reached (%d s)", self._max_duration_s)
            self.stop_recording()
