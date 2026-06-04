"""Unit tests for AsyncLoopThread and EventBus loop routing (v2 wiring)."""

import threading
import time

import pytest

from agentvoca.core.async_loop import AsyncLoopThread
from agentvoca.core.event_bus import EventBus


@pytest.fixture
def loop_thread():
    lt = AsyncLoopThread()
    lt.start()
    yield lt
    lt.stop()


def test_submit_runs_coroutine_and_returns_result(loop_thread):
    async def add(a, b):
        return a + b

    fut = loop_thread.submit(add(2, 3))
    assert fut.result(timeout=2.0) == 5


def test_call_soon_runs_callable_on_loop(loop_thread):
    done = threading.Event()
    loop_thread.call_soon(done.set)
    assert done.wait(timeout=2.0)


def test_create_task_inside_submitted_coro_survives(loop_thread):
    """A task spawned by a coroutine must keep running on the persistent loop."""
    import asyncio

    result = {}

    async def background():
        await asyncio.sleep(0.05)
        result["ran"] = True

    async def parent():
        asyncio.create_task(background())
        # returns immediately; the task must not be cancelled

    loop_thread.submit(parent()).result(timeout=2.0)
    time.sleep(0.2)
    assert result.get("ran") is True


def test_event_bus_routes_async_handler_to_persistent_loop(loop_thread):
    """Publishing from a thread with no running loop routes to the loop."""
    bus = EventBus()
    bus.set_loop(loop_thread.loop)

    ran = threading.Event()

    class Ping:
        pass

    async def handler(_event):
        ran.set()

    bus.subscribe(Ping, handler)
    # Called from the main (test) thread — no running loop here.
    bus.publish(Ping())
    assert ran.wait(timeout=2.0)


def test_event_bus_without_loop_still_runs_async_handler():
    """With no persistent loop set, async handlers run synchronously."""
    bus = EventBus()
    ran = {}

    class Ping:
        pass

    async def handler(_event):
        ran["ok"] = True

    bus.subscribe(Ping, handler)
    bus.publish(Ping())  # falls back to asyncio.run
    assert ran.get("ok") is True
