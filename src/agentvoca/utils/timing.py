"""Stage timer context manager that emits TimingEvent.

Used to measure and log per-stage latency in the dictation pipeline.
"""

import time
from contextlib import contextmanager
from typing import Generator, Optional

from agentvoca.core.events import TimingEvent


class StageTimer:
    """Context manager that measures elapsed time for a pipeline stage.

    Usage:
        timer = StageTimer()
        with timer("asr"):
            await asr_provider.transcribe_audio(...)
        # timer.duration_ms is set, timer.event carries the result
    """

    def __init__(self, event_bus: Optional["EventBus"] = None) -> None:  # noqa: F821
        self._event_bus = event_bus
        self._stage: Optional[str] = None
        self._start: Optional[float] = None
        self.duration_ms: Optional[float] = None
        self.event: Optional[TimingEvent] = None

    @contextmanager
    def measure(self, stage: str) -> Generator[None, None, None]:
        """Measure the duration of a pipeline stage.

        Args:
            stage: Name of the stage (e.g., "asr", "cleanup", "insertion").

        Yields:
            None; the context manager records the elapsed time on exit.

        The duration and corresponding TimingEvent are available as
        ``timer.duration_ms`` and ``timer.event`` after the context exits.
        """
        self._stage = stage
        self._start = time.monotonic()
        self.duration_ms = None
        self.event = None
        try:
            yield
        finally:
            elapsed = time.monotonic() - (self._start or time.monotonic())
            self.duration_ms = round(elapsed * 1000, 1)
            self.event = TimingEvent(
                stage=stage,
                duration_ms=self.duration_ms,
            )
            if self._event_bus is not None:
                self._event_bus.publish(self.event)

    def __call__(self, stage: str) -> Generator[None, None, None]:
        """Convenience: call timer(stage) instead of timer.measure(stage)."""
        return self.measure(stage)
