"""Audio chunker — emits raw audio deltas during recording.

The chunker feeds incoming PCM audio into the event bus as ``AudioChunkEvent``
at a configurable cadence.  Each event carries only the *new* audio since the
previous emission (a delta), NOT a rolling window.  The streaming ASR provider
(``FasterWhisperProvider.stream_transcribe``) builds its own rolling window
from the accumulated deltas so that the transcription model always has enough
context.

Why deltas, not windows
-----------------------
An earlier design emitted the rolling window (last N seconds) with every chunk.
``stream_transcribe`` naively appended every chunk into ``full_buffer``, so
after 30 seconds × 60 chunks × 8-second window = ~480 seconds of duplicate
audio accumulated.  The final accurate-pass then transcribed that garbage,
producing hallucinated repetitions and multi-minute hangs.

Sending deltas means ``full_buffer`` in ``stream_transcribe`` is simply the
real recorded audio and the rolling-window view is a cheap slice of that buffer.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import AudioChunkEvent

logger = logging.getLogger(__name__)


class AudioChunker:
    """Emits raw audio delta ``AudioChunkEvent`` s during recording.

    Args:
        event_bus: Shared event bus for publishing chunk events.
        chunk_ms: Interval between emissions in milliseconds (100–2000).
        window_s: Informational — the rolling-window size the downstream
            streaming ASR will use.  The chunker itself no longer applies
            the window; it only emits deltas.
        sample_rate: Sample rate of the audio data in Hz.
    """

    def __init__(
        self,
        event_bus: EventBus,
        chunk_ms: int = 500,
        window_s: int = 8,
        sample_rate: int = 16000,
    ) -> None:
        self._event_bus = event_bus
        self._chunk_ms = max(100, min(2000, chunk_ms))
        self._window_s = max(0, window_s)
        self._sample_rate = sample_rate
        self._buffer = bytearray()
        self._last_emit_pos: int = 0  # bytes emitted so far (for delta)
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._start_time_ms: int = 0

    @property
    def is_running(self) -> bool:
        """True if the chunker is actively emitting chunks."""
        return self._running

    def start(self) -> None:
        """Begin the chunk emission loop."""
        self._buffer.clear()
        self._last_emit_pos = 0
        self._running = True
        self._start_time_ms = int(time.time() * 1000)
        self._task = asyncio.create_task(self._chunk_loop())
        logger.debug(
            "Chunker started (chunk_ms=%d, window_s=%d)",
            self._chunk_ms,
            self._window_s,
        )

    def add_audio(self, data: bytes) -> None:
        """Feed incoming audio data into the chunker buffer.

        Args:
            data: Raw PCM float32 audio bytes.
        """
        if not self._running:
            return
        self._buffer.extend(data)

    async def stop(self, flush: bool = True) -> None:
        """Stop the chunker and optionally flush remaining audio.

        When ``flush`` is True (normal stop) emits a final delta chunk with
        ``is_flush=True`` so the streaming ASR can finalize.  Any audio added
        since the last regular emission is included.

        When ``flush`` is False (cancel) no final chunk is emitted.
        """
        self._running = False

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if flush:
            now_ms = int(time.time() * 1000)
            delta = self._get_delta()
            logger.debug("Chunker flushed %d bytes", len(delta))
            # Always emit the flush event (even if delta is empty) so the
            # streaming task knows the recording has ended.
            self._event_bus.publish(
                AudioChunkEvent(
                    data=delta,
                    sample_rate=self._sample_rate,
                    timestamp_ms=now_ms,
                    is_flush=True,
                )
            )

    def reset(self) -> None:
        """Clear the internal buffer without stopping."""
        self._buffer.clear()
        self._last_emit_pos = 0
        self._start_time_ms = 0

    def _get_delta(self) -> bytes:
        """Return new audio since the last emission and compact the buffer.

        ``end`` is snapshotted before the ``del``: ``add_audio`` may append from
        the audio thread between the two statements, and deleting only
        ``[:end]`` guarantees those new bytes survive. Both the slice-read
        and the delete are single GIL-held bytearray operations, so no torn
        state is possible (R5).
        """
        end = len(self._buffer)
        delta = bytes(self._buffer[self._last_emit_pos:end])
        del self._buffer[:end]
        self._last_emit_pos = 0
        return delta

    async def _chunk_loop(self) -> None:
        """Emit audio deltas at the configured cadence."""
        try:
            while self._running:
                await asyncio.sleep(self._chunk_ms / 1000.0)

                if not self._running:
                    break

                delta = self._get_delta()
                if not delta:
                    continue

                now_ms = int(time.time() * 1000)
                self._event_bus.publish(
                    AudioChunkEvent(
                        data=delta,
                        sample_rate=self._sample_rate,
                        timestamp_ms=now_ms,
                        is_flush=False,
                    )
                )
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Chunker loop error")
