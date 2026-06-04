"""Persistent asyncio event loop running on a background thread.

The desktop app's main thread runs the Qt event loop (``app.exec()``), so there
is no asyncio loop running there. Several v2 features rely on
``asyncio.create_task`` / background tasks that need a *persistent* running
loop:

* background warm-up (orchestrator ``start()``),
* streaming ASR consumer and the audio chunker loop,
* voice-command insertion and the error-reset timer.

Running pipeline coroutines via a fresh ``asyncio.run()`` per event (the old
behavior) cancels any task they spawn the instant that ephemeral loop closes.
This helper runs a single long-lived loop on a daemon thread and lets other
threads (Qt, the sounddevice audio callback) submit work to it thread-safely.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class AsyncLoopThread:
    """A single asyncio event loop owned by a dedicated daemon thread."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="agentvoca-asyncio", daemon=True)
        self._started = threading.Event()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._started.set()
        try:
            self._loop.run_forever()
        finally:
            # Cancel anything still pending, then close the loop.
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                logger.debug("Error draining async loop tasks", exc_info=True)
            finally:
                self._loop.close()

    def start(self) -> None:
        """Start the loop thread and block until the loop is running."""
        self._thread.start()
        self._started.wait()
        logger.debug("Async loop thread started")

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """The underlying event loop (running on the background thread)."""
        return self._loop

    def submit(self, coro: Coroutine[Any, Any, Any]) -> Future:
        """Schedule a coroutine on the loop from any thread.

        Returns a ``concurrent.futures.Future``. Call ``.result()`` to block
        until it completes (do not call ``.result()`` from the loop thread).
        """
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def call_soon(self, fn: Callable[..., Any], *args: Any) -> None:
        """Schedule a plain callable to run on the loop thread."""
        self._loop.call_soon_threadsafe(fn, *args)

    def stop(self) -> None:
        """Stop the loop and join the thread."""
        if self._thread.is_alive():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=3.0)
        logger.debug("Async loop thread stopped")
