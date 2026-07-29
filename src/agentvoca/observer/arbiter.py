"""ASR arbiter for Observer mode (v0.4.0, OBS-12).

Serialises access to a single ``ASRProvider`` between the dictation and
ambient paths. Dictation always wins; ambient simply lags while a
dictation is in flight, and a fresh ambient queue overflow drops the
oldest job (a stale utterance is worth less than a fresh one).

Threading
---------
- ``transcribe_priority`` is an ``async`` coroutine called from the
  asyncio loop. It toggles the ``_dictation_idle`` ``asyncio.Event`` so
  the ambient worker pauses for the duration of the dictation.
- ``submit_ambient`` is a sync method called from any thread (typically
  the ``observer-ambient`` worker). It uses
  ``loop.call_soon_threadsafe`` to enqueue, because ``asyncio.Queue`` is
  not thread-safe.
- The single worker coroutine runs on the asyncio loop and pulls from
  the queue, awaiting the idle event before each transcription.

Why one ASR instance (D10)
--------------------------
The 400 MB RSS budget forbids loading a second model. The arbiter is
the gate that makes one ASR model safe to share.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from agentvoca.asr.base import ASRProvider

logger = logging.getLogger(__name__)

OnText = Callable[[str, int, int], None]
"""Called from the loop thread with ``(text, ts_ms, duration_ms)`` for
each completed ambient transcription.

The callback must not raise. Errors are logged and swallowed; the
arbiter's job is to keep the worker alive no matter what the consumer
does."""


@dataclass
class _AmbientJob:
    """A queued ambient transcription request."""

    audio: bytes
    ts_ms: int
    duration_ms: int
    sample_rate: int
    context: object | None = None


class ASRArbiter:
    """Serialise access to a single ``ASRProvider``, dictation first.

    Args:
        provider: The shared ASR provider. One instance serves both clients.
        queue_depth: Capacity of the ambient queue. Default 16. On
            overflow the oldest job is dropped.
    """

    def __init__(self, provider: ASRProvider, queue_depth: int = 16) -> None:
        self._provider = provider
        self._queue: asyncio.Queue[_AmbientJob | None] = asyncio.Queue(maxsize=queue_depth)
        self._dictation_idle = asyncio.Event()
        self._dictation_idle.set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: Optional[asyncio.Task[None]] = None
        self._on_text: Optional[OnText] = None
        self._dropped: int = 0

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(self, on_text: OnText) -> None:
        """Bind the result callback and start the worker coroutine.

        Idempotent. The loop is captured on first call. ``on_text`` is
        called from the worker coroutine for every successful
        transcription; the caller is responsible for any cross-thread
        dispatch it needs.
        """
        if self._task is not None and not self._task.done():
            self._on_text = on_text
            return
        self._on_text = on_text
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise RuntimeError("ASRArbiter.start must be called from the asyncio loop") from exc
        self._task = self._loop.create_task(self._worker(), name="asr-arbiter-ambient")
        logger.debug("ASRArbiter started (queue_depth=%d)", self._queue.maxsize)

    async def stop(self) -> None:
        """Drain the worker and stop it. Idempotent."""
        if self._task is None:
            return
        # Put the stop sentinel; the worker exits at its next iteration.
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            # Worst case: replace one item with the sentinel.
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(None)
            except asyncio.QueueFull:
                pass
        try:
            await asyncio.wait_for(self._task, timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._task.cancel()
        self._task = None
        logger.debug("ASRArbiter stopped")

    # ── Dictation path ─────────────────────────────────────────────

    async def transcribe_priority(
        self,
        audio: bytes,
        sample_rate: int,
        context: object | None = None,
    ) -> str:
        """Dictation path. Blocks ambient for the duration of the call.

        The try/finally around the event ensures a raising provider does
        not leave ambient starved forever.
        """
        self._dictation_idle.clear()
        try:
            result = await self._provider.transcribe_audio(audio, sample_rate, context=context)
        finally:
            self._dictation_idle.set()
        # ``transcribe_audio`` always returns a final segment.
        return result.text

    # ── Ambient path ───────────────────────────────────────────────

    def submit_ambient(
        self,
        audio: bytes,
        ts_ms: int,
        duration_ms: int,
        sample_rate: int,
        context: object | None = None,
    ) -> bool:
        """Enqueue an ambient job. Returns False if the enqueue failed.

        On overflow the OLDEST job is dropped (a stale utterance is worth
        less than a fresh one). Thread-safe; typically called from the
        ``observer-ambient`` worker thread.
        """
        job = _AmbientJob(
            audio=audio,
            ts_ms=ts_ms,
            duration_ms=duration_ms,
            sample_rate=sample_rate,
            context=context,
        )
        if self._loop is None:
            # No loop yet (start() was not called). The worker is not
            # running; we drop silently. The wiring in main.py is
            # responsible for calling start() before submit_ambient
            # ever fires.
            return False
        try:
            self._loop.call_soon_threadsafe(self._enqueue_via_loop, job)
            return True
        except RuntimeError:
            return False

    def _enqueue_via_loop(self, job: _AmbientJob) -> None:
        """Loop-thread enqueue with oldest-drop on overflow.

        Every overflow increments ``self._dropped`` — the caller records
        a ``gap`` event so the compiled output can say "audio dropped
        here" honestly.
        """
        try:
            self._queue.put_nowait(job)
            return
        except asyncio.QueueFull:
            pass
        # Drop oldest, then re-enqueue. The drop is what we count.
        try:
            self._queue.get_nowait()
        except asyncio.QueueEmpty:
            self._dropped += 1
            return
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            self._dropped += 1
            return
        self._dropped += 1

    @property
    def dropped_count(self) -> int:
        """Number of ambient jobs dropped due to queue overflow."""
        return self._dropped

    # ── Worker ─────────────────────────────────────────────────────

    async def _worker(self) -> None:
        """Owned by the asyncio loop. Drains the ambient queue."""
        while True:
            job = await self._queue.get()
            if job is None:
                return
            # Dictation always wins — wait here, not in submit_ambient.
            await self._dictation_idle.wait()
            try:
                segment = await self._provider.transcribe_audio(
                    job.audio, job.sample_rate, context=job.context
                )
            except Exception:
                logger.debug("Ambient transcription failed", exc_info=True)
                self._queue.task_done()
                continue
            if self._on_text is not None:
                try:
                    self._on_text(segment.text, job.ts_ms, job.duration_ms)
                except Exception:
                    logger.debug("on_text callback raised", exc_info=True)
            self._queue.task_done()
