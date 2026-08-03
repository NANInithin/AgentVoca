"""End-to-end wiring test for ``main._build_observer_capture``.

Regression cover for the v0.4.0 bug where Observer sessions started,
showed the on-screen indicator, ran, closed, compiled — and exported
"_No events were recorded in this session._" every time.

Two independent faults produced that:

1. ``ASRArbiter.start()`` was called from the Qt thread. It requires a
   *running* asyncio loop, so it raised, and the blanket ``except`` in
   the capture builder returned ``(None,) * 5`` — silently disabling
   every capture source, including the ones that had nothing to do with
   ASR.
2. Nothing ever connected the ``TriggerGate`` to the ``ScreenGrabber``,
   so even a healthy gate produced no keyframes, no OCR, and no
   selections.

The tests below call the real builder from a plain (non-loop) thread —
exactly how ``main()`` calls it — and assert that events actually land
in the store.
"""

from __future__ import annotations

import threading
import time

import pytest

import agentvoca.main as m
from agentvoca.config.schema import (
    ASRConfig,
    AudioConfig,
    CleanupConfig,
    FullConfig,
    InsertionConfig,
    ObserverConfig,
    ObserverOCRConfig,
    ObserverPrivacyConfig,
    ObserverSelectionConfig,
    ObserverStorageConfig,
    ObserverTriggersConfig,
)
from agentvoca.core.async_loop import AsyncLoopThread
from agentvoca.core.event_bus import EventBus
from agentvoca.core.types import TranscriptSegment
from agentvoca.observer.controller import ObserverController
from agentvoca.observer.models import OCRResult
from agentvoca.observer.ocr.base import OCRProvider
from agentvoca.observer.store import ObserverStore


class _StubASR:
    """Minimal ASR provider. Only needs to exist for the arbiter."""

    def get_name(self):
        return "stub"

    def is_available(self):
        return True

    def supports_streaming(self):
        return False

    async def transcribe_audio(self, audio, sample_rate, context=None):
        return TranscriptSegment(text="hello from ambient", is_final=True)


class _StubOrchestrator:
    """Carries the two attributes the capture builder reaches for."""

    def __init__(self) -> None:
        self._asr_provider = _StubASR()
        self.attached_arbiter = None

    def attach_asr_arbiter(self, arbiter) -> None:
        self.attached_arbiter = arbiter


class _StubOCR(OCRProvider):
    """Returns a fixed string so the keyframe row is easy to assert on."""

    async def extract(self, image_jpeg, *, hint=None):
        return OCRResult(text="OCR TEXT", confidence=0.9, latency_ms=1, engine="stub")


class _StubAudio:
    """Stands in for AudioCapture; records the ambient tap install."""

    def __init__(self) -> None:
        self.ambient_sink = None

    def set_ambient_sink(self, sink) -> None:
        self.ambient_sink = sink


class _StubRegistry:
    def __init__(self, ocr: OCRProvider | None) -> None:
        self._ocr = ocr

    def get_ocr(self, config):
        if self._ocr is None:
            raise RuntimeError("intentional OCR provider failure")
        return self._ocr


def _config(tmp_path) -> FullConfig:
    return FullConfig(
        asr=ASRConfig(provider="stub"),
        audio=AudioConfig(sample_rate=16000),
        cleanup=CleanupConfig(provider="rules"),
        insertion=InsertionConfig(strategy="keyboard"),
        observer=ObserverConfig(
            enabled=True,
            storage=ObserverStorageConfig(dir=str(tmp_path / "obs")),
            triggers=ObserverTriggersConfig(min_interval_ms=500, max_keyframes_per_min=60),
            ocr=ObserverOCRConfig(provider="stub"),
            # The UIA reader needs a real desktop; the noop reader keeps
            # this test honest about wiring without needing one.
            selection=ObserverSelectionConfig(method="none"),
            privacy=ObserverPrivacyConfig(
                exclude_apps=["secret.exe"],
                exclude_title_patterns=[],
            ),
        ),
    )


@pytest.fixture
def loop_thread():
    t = AsyncLoopThread()
    t.start()
    yield t
    t.stop()


@pytest.fixture
def store(tmp_path):
    s = ObserverStore(root=tmp_path / "obs")
    s.start()
    yield s
    s.stop()


def _build(cfg, loop_thread, store, *, orchestrator, registry, event_bus):
    """Call the builder the way main() does: from a non-loop thread."""
    controller = ObserverController(
        config=cfg,
        event_bus=event_bus,
        store=store,
        loop=loop_thread.loop,
    )
    audio = _StubAudio()
    result: dict = {}

    def _run() -> None:
        # A plain worker thread has no running asyncio loop — same as the
        # Qt main thread that main() builds from.
        result["capture"] = m._build_observer_capture(
            cfg=cfg,
            orchestrator=orchestrator,
            registry=registry,
            loop_thread=loop_thread,
            audio=audio,
            observer_controller=controller,
            event_bus=event_bus,
            store=store,
        )

    worker = threading.Thread(target=_run, name="test-qt-thread")
    worker.start()
    worker.join(timeout=15.0)
    assert not worker.is_alive(), "the capture builder hung"
    controller.attach_capture(*result["capture"])
    return controller, result["capture"], audio


def test_capture_builds_from_a_thread_without_a_running_loop(tmp_path, loop_thread, store):
    """The whole tuple must be live — this is the bug that shipped.

    ``ASRArbiter.start`` needs the loop thread. Called from here it used
    to raise and take every other capture source down with it.
    """
    cfg = _config(tmp_path)
    orchestrator = _StubOrchestrator()
    controller, capture, audio = _build(
        cfg,
        loop_thread,
        store,
        orchestrator=orchestrator,
        registry=_StubRegistry(_StubOCR(cfg.observer.ocr)),
        event_bus=EventBus(),
    )
    ambient, triggers, grabber, ocr, selection = capture

    assert ambient is not None, "ambient listener was not built"
    assert triggers is not None, "trigger engine was not built"
    assert grabber is not None, "screen grabber was not built"
    assert ocr is not None, "OCR provider was not built"
    assert selection is not None, "selection reader was not built"
    # The arbiter started on the loop thread and reached the orchestrator.
    assert orchestrator.attached_arbiter is not None
    # And the ambient tap is installed on the audio device.
    assert audio.ambient_sink is ambient
    controller.shutdown()


def test_ambient_ocr_failure_does_not_disable_the_rest(tmp_path, loop_thread, store):
    """A broken OCR provider costs OCR only, not the whole subsystem."""
    cfg = _config(tmp_path)
    controller, capture, _audio = _build(
        cfg,
        loop_thread,
        store,
        orchestrator=_StubOrchestrator(),
        registry=_StubRegistry(None),  # get_ocr raises
        event_bus=EventBus(),
    )
    ambient, triggers, grabber, ocr, selection = capture

    assert ocr is None
    assert ambient is not None
    assert triggers is not None
    assert grabber is not None
    assert selection is not None
    controller.shutdown()


def test_a_gate_request_produces_a_keyframe_row_with_ocr_text(
    tmp_path, loop_thread, store, monkeypatch
):
    """gate → grabber → blob → events row → OCR patch.

    None of this glue existed: the gate accepted requests and dropped
    them on the floor, so a session could only ever contain
    ``focus_change`` rows.
    """
    from PIL import Image

    from agentvoca.observer import screen as screen_module

    # Stub the platform layer: a fixed rect and a synthetic image, so the
    # test needs no desktop and no real window.
    monkeypatch.setattr(screen_module, "_active_window_rect_windows", lambda: (0, 0, 800, 600))
    monkeypatch.setattr(
        screen_module,
        "ImageGrab_grab",
        lambda *, bbox: Image.new("RGB", (bbox[2] - bbox[0], bbox[3] - bbox[1]), "white"),
    )

    cfg = _config(tmp_path)
    event_bus = EventBus()
    keyframe_events: list = []
    from agentvoca.core.events import ObserverKeyframeEvent

    event_bus.subscribe(ObserverKeyframeEvent, keyframe_events.append)

    controller, capture, _audio = _build(
        cfg,
        loop_thread,
        store,
        orchestrator=_StubOrchestrator(),
        registry=_StubRegistry(_StubOCR(cfg.observer.ocr)),
        event_bus=event_bus,
    )
    _ambient, triggers, _grabber, _ocr, _selection = capture

    assert controller.start_session() is True
    session_id = controller.sessions.current.id
    try:
        # ``start_session`` starts the trigger engine's poll thread, which
        # fires its own window_change on the first iteration — so a manual
        # request may legitimately be refused by ``min_interval_ms``. Keep
        # asking and wait for the row instead of assuming which one wins.
        # The capture worker and the OCR coroutine are both asynchronous,
        # so poll the store rather than sleeping a fixed amount.
        deadline = time.monotonic() + 15.0
        keyframes: list = []
        while time.monotonic() < deadline:
            triggers._gate.request("window_change")
            store.flush(timeout=2.0)
            bundle = store.load_bundle(session_id=session_id)
            keyframes = [e for e in bundle.events if e.kind == "keyframe"]
            if keyframes and keyframes[0].text:
                break
            time.sleep(0.05)
    finally:
        controller.stop_session()

    assert keyframes, "the gate accepted a request but no keyframe row was written"
    keyframe = keyframes[0]
    assert keyframe.meta["trigger"] == "window_change"
    assert keyframe.meta["width"] > 0 and keyframe.meta["height"] > 0
    # blob_path is relative to the storage dir so the archive can be moved.
    assert keyframe.blob_path.startswith("blobs/")
    assert (store.blobs_dir.parent / keyframe.blob_path).is_file()
    # OCR ran and patched the row in place.
    assert keyframe.text == "OCR TEXT"
    assert keyframe.meta["ocr_status"] == "ok"
    assert keyframe_events, "ObserverKeyframeEvent was never published"
    controller.shutdown()


def test_excluded_foreground_app_blocks_capture_and_records_the_pause(
    tmp_path, loop_thread, store, monkeypatch
):
    """The privacy exclusion list is enforced at the gate.

    It was configured but never wired, so ``exclude_apps`` had no effect
    on anything.
    """
    from agentvoca.context import active_app as active_app_module

    monkeypatch.setattr(
        active_app_module.ActiveAppDetector,
        "detect",
        lambda self: ("secret.exe", "Vault"),
    )

    cfg = _config(tmp_path)
    controller, capture, _audio = _build(
        cfg,
        loop_thread,
        store,
        orchestrator=_StubOrchestrator(),
        registry=_StubRegistry(_StubOCR(cfg.observer.ocr)),
        event_bus=EventBus(),
    )
    _ambient, triggers, _grabber, _ocr, _selection = capture

    assert controller.start_session() is True
    session_id = controller.sessions.current.id
    try:
        assert triggers._gate.request("window_change") is False
        store.flush(timeout=2.0)
        bundle = store.load_bundle(session_id=session_id)
    finally:
        controller.stop_session()

    assert not [e for e in bundle.events if e.kind == "keyframe"]
    pauses = [e for e in bundle.events if e.kind == "pause_start"]
    assert pauses, "an excluded app must record pause_start"
    assert pauses[0].meta["reason"] == "excluded_app"
    assert pauses[0].meta["pattern"] == "secret.exe"
    # The excluded app's window title must not be archived.
    assert pauses[0].window_title is None
    controller.shutdown()
