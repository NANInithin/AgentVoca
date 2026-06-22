"""Unit tests for the screenshot capturer (v3)."""

from __future__ import annotations

import struct

from agentvoca.capture.screenshot import ScreenshotCapturer, _png_dimensions
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import ScreenshotCapturedEvent


def _fake_png(width: int = 3, height: int = 4) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"  # bit depth, colour type, etc.
    )


def test_png_dimensions_parses_ihdr() -> None:
    assert _png_dimensions(_fake_png(640, 480)) == (640, 480)


def test_png_dimensions_non_png_returns_none() -> None:
    assert _png_dimensions(b"not a png") == (None, None)


def test_capture_appends_and_publishes() -> None:
    bus = EventBus()
    events: list[ScreenshotCapturedEvent] = []
    bus.subscribe(ScreenshotCapturedEvent, events.append)

    cap = ScreenshotCapturer(event_bus=bus)
    cap._capture_bytes = lambda: _fake_png(100, 50)  # type: ignore[method-assign]

    cap.capture()
    assert cap.wait_idle(timeout=5.0) is True

    shots = cap.drain()
    assert len(shots) == 1
    assert shots[0].startswith(b"\x89PNG")
    assert len(events) == 1
    assert events[0].index == 0
    assert (events[0].width, events[0].height) == (100, 50)
    # Drained — nothing left.
    assert cap.has_pending() is False
    assert cap.drain() == []


def test_multiple_captures_preserve_order() -> None:
    bus = EventBus()
    cap = ScreenshotCapturer(event_bus=bus)
    counter = {"n": 0}

    def _grab() -> bytes:
        counter["n"] += 1
        return _fake_png(counter["n"], counter["n"])

    cap._capture_bytes = _grab  # type: ignore[method-assign]

    cap.capture()
    assert cap.wait_idle(timeout=5.0)
    cap.capture()
    assert cap.wait_idle(timeout=5.0)

    shots = cap.drain()
    assert len(shots) == 2


def test_cancelled_capture_produces_nothing() -> None:
    bus = EventBus()
    events: list[ScreenshotCapturedEvent] = []
    bus.subscribe(ScreenshotCapturedEvent, events.append)
    cap = ScreenshotCapturer(event_bus=bus)
    cap._capture_bytes = lambda: None  # type: ignore[method-assign]

    cap.capture()
    assert cap.wait_idle(timeout=5.0)
    assert cap.drain() == []
    assert events == []


def test_clear_discards_queue() -> None:
    bus = EventBus()
    cap = ScreenshotCapturer(event_bus=bus)
    cap._capture_bytes = lambda: _fake_png()  # type: ignore[method-assign]
    cap.capture()
    assert cap.wait_idle(timeout=5.0)
    cap.clear()
    assert cap.drain() == []
    assert cap.has_pending() is False
