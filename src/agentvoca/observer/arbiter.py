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
from typing import AsyncIterator, Callable, Optional

from agentvoca.asr.base import ASRProvider
from agentvoca.core.types import TranscriptSegment

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
    session_id: int | None = None


class ASRArbiter:
    """Serialise access to a single ``ASRProvider``, dictation first.

    Args:
        provider: The shared ASR provider. One instance serves both clients.
        queue_depth: Capacity of the ambient queue. Default 16. On
            overflow the oldest job is dropped.
    """

    def __init__(
        self,
        provider: ASRProvider,
        queue_depth: int = 16,
        is_session_current: Callable[[int], bool] | None = None,
    ) -> None:
        self._provider = provider
        self._queue: asyncio.Queue[_AmbientJob | None] = asyncio.Queue(maxsize=queue_depth)
        self._dictation_idle = asyncio.Event()
        self._dictation_idle.set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: Optional[asyncio.Task[None]] = None
        self._on_text: Optional[OnText] = None
        self._dropped: int = 0
        self._provider_lock = asyncio.Lock()
        self._active_ambient: asyncio.Task | None = None
        self._active_session_id: int | None = None
        self._on_drop: Callable[[int], None] | None = None
        self._is_session_current = is_session_current

    def set_on_drop(self, callback: Callable[[int], None]) -> None:
        self._on_drop = callback

    def _note_drop(self) -> None:
        self._dropped += 1
        if self._on_drop is not None:
            try:
                self._on_drop(1)
            except Exception:
                logger.debug("Ambient drop callback failed", exc_info=True)

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
            active = self._active_ambient
            if active is not None and not active.done():
                active.cancel()
                await asyncio.gather(active, return_exceptions=True)
            async with self._provider_lock:
                result = await self._provider.transcribe_audio(audio, sample_rate, context=context)
        finally:
            self._dictation_idle.set()
        # ``transcribe_audio`` always returns a final segment.
        return result.text

    async def stream_priority(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int,
        context: object | None = None,
    ) -> AsyncIterator[TranscriptSegment]:
        """Keep ambient ASR off the shared provider for an entire dictation stream."""
        self._dictation_idle.clear()
        try:
            active = self._active_ambient
            if active is not None and not active.done():
                active.cancel()
                await asyncio.gather(active, return_exceptions=True)
            async with self._provider_lock:
                async for segment in self._provider.stream_transcribe(
                    audio_stream, sample_rate, context=context
                ):
                    yield segment
        finally:
            self._dictation_idle.set()

    # ── Ambient path ───────────────────────────────────────────────

    def submit_ambient(
        self,
        audio: bytes,
        ts_ms: int,
        duration_ms: int,
        sample_rate: int,
        context: object | None = None,
        session_id: int | None = None,
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
            session_id=session_id,
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
            self._note_drop()
            return
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            self._note_drop()
            return
        self._note_drop()

    def discard_session(self, session_id: int) -> None:
        """Cancel ambient work belonging to a closed Observer session."""
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._discard_session_on_loop, session_id)
            except RuntimeError:
                pass

    def _discard_session_on_loop(self, session_id: int) -> None:
        if self._active_session_id == session_id and self._active_ambient is not None:
            self._active_ambient.cancel()
        retained: list[_AmbientJob | None] = []
        while True:
            try:
                job = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._queue.task_done()
            if job is None or job.session_id != session_id:
                retained.append(job)
        for job in retained:
            self._queue.put_nowait(job)

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
                self._queue.task_done()
                return
            try:
                while True:
                    await self._dictation_idle.wait()
                    async with self._provider_lock:
                        if not self._dictation_idle.is_set():
                            continue
                        self._active_ambient = asyncio.create_task(
                            self._provider.transcribe_audio(
                                job.audio, job.sample_rate, context=job.context
                            )
                        )
                        self._active_session_id = job.session_id
                        try:
                            segment = await self._active_ambient
                        except asyncio.CancelledError:
                            if asyncio.current_task().cancelling():
                                raise
                            segment = None
                        finally:
                            self._active_ambient = None
                            self._active_session_id = None
                        break
                if (
                    segment is not None
                    and self._on_text is not None
                    and (
                        job.session_id is None
                        or self._is_session_current is None
                        or self._is_session_current(job.session_id)
                    )
                ):
                    try:
                        self._on_text(segment.text, job.ts_ms, job.duration_ms)
                    except Exception:
                        logger.debug("on_text callback raised", exc_info=True)
            except Exception:
                logger.debug("Ambient transcription failed", exc_info=True)
            finally:
                self._queue.task_done()
