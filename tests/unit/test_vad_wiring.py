"""OBS-0: VAD wiring tests (pre-existing bug fix).

Verified problem (before the fix): ``AudioCapture.__init__`` accepted a
``vad`` parameter but ``_build_and_start_pipeline`` in ``main.py`` never
passed one. The result was that ``agentvoca-vad`` (R2) was never started
and ``VADSpeechEvent`` was never published; ``app.mode: auto_stop`` never
auto-stopped.

The fix lands the VAD construction in ``main._build_and_start_pipeline``
and passes the result to ``AudioCapture``. These tests assert the
*contract of the wiring* — that the pipeline builds correctly under every
shape of VAD availability — without requiring a real silero model.

All tests use ``agentvoca.main.main`` with the heavy collaborators faked
(``_install_fakes``-style approach adapted from
``test_main_startup.py``).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6", reason="PySide6 (Qt) not available")

import agentvoca.main as m  # noqa: E402


class _Recorder:
    """Record the kwargs the AudioCapture fake received."""

    def __init__(self) -> None:
        self.last_kwargs: dict | None = None


def _install_fakes(monkeypatch, audio_capture_kwargs_out: list[dict], vad_ctor: MagicMock):
    """Wire fakes for Qt, audio, VAD, hotkeys, etc.

    Args:
        audio_capture_kwargs_out: A list the AudioCapture fake appends the
            actual kwargs it was constructed with. Tests assert on it.
        vad_ctor: A MagicMock stand-in for the VAD class. Its ``return_value``
            is what main.py receives and passes through to AudioCapture.
    """

    class FakeApp:
        def __init__(self, *_a, **_k) -> None:
            pass

        def setQuitOnLastWindowClosed(self, _v: bool) -> None:
            pass

        def exec(self) -> int:
            return 0

        def quit(self) -> None:
            pass

    fake_qtwidgets = SimpleNamespace(QApplication=FakeApp)

    class FakeWizard:
        def __init__(self, *_a, **_k) -> None:
            self.config_saved = MagicMock()

        def exec(self) -> int:
            return 0

        def show(self) -> None:
            pass

        def raise_(self) -> None:
            pass

        def activateWindow(self) -> None:
            pass

        def close(self) -> None:
            pass

    class FakeOrchestrator:
        def __init__(self, *, config, **_k) -> None:
            self.config = config

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

    class FakeAudio:
        def __init__(self, *_a, **kwargs) -> None:
            self.is_recording = False
            audio_capture_kwargs_out.append(kwargs)

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    class FakeHotkeys:
        def __init__(self, *_a, **_k) -> None:
            pass

        def register(self, *_a, **_k) -> None:
            pass

        def unregister_all(self) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    fake_tray = SimpleNamespace(
        open_settings_action=SimpleNamespace(triggered=MagicMock()),
        open_wizard_action=SimpleNamespace(triggered=MagicMock()),
        quit_action=SimpleNamespace(triggered=MagicMock()),
        show_message=lambda *a, **k: None,
        # main.py calls this once it knows whether an ObserverController
        # was built (v0.4.0). Fakes must carry it or startup raises.
        set_observer_available=lambda *a, **k: None,
    )

    from agentvoca.setup.first_run import AppState

    monkeypatch.setattr(m, "load_state", lambda: AppState(wizard_auto_open=False))
    monkeypatch.setattr(m, "QtWidgets", fake_qtwidgets)
    monkeypatch.setattr(m, "SetupWizard", FakeWizard)
    monkeypatch.setattr(m, "SettingsWindow", MagicMock())
    monkeypatch.setattr(m, "Orchestrator", FakeOrchestrator)
    monkeypatch.setattr(m, "AudioCapture", FakeAudio)
    monkeypatch.setattr(m, "HotkeyManager", FakeHotkeys)
    monkeypatch.setattr(m, "StatusOverlay", lambda *a, **k: SimpleNamespace(stop=lambda: None))
    monkeypatch.setattr(m, "TrayApp", lambda *a, **k: fake_tray)
    monkeypatch.setattr(m, "VAD", vad_ctor)


def _write_minimal_config(path: Path) -> None:
    path.write_text("asr:\n  provider: faster_whisper\n  model: base\n", encoding="utf-8")


class _FakeVAD:
    """Models the real ``VAD`` contract, which a MagicMock does not.

    The distinction matters: constructing a ``VAD`` loads nothing, and
    ``is_available`` stays False until ``start()`` has been awaited. A
    MagicMock reports ``is_available`` True straight away, which is why
    the original tests here passed while auto-stop was dead in the real
    app — main.py never called ``start()``.

    Args:
        available_after_start: What ``is_available`` becomes once
            ``start()`` completes. False models a silero install that
            loads but cannot run.
        start_error: When set, ``start()`` raises it.
    """

    def __init__(
        self,
        *,
        available_after_start: bool = True,
        start_error: Exception | None = None,
    ) -> None:
        self._available_after_start = available_after_start
        self._start_error = start_error
        self.started = False
        self.is_available = False

    async def start(self) -> None:
        if self._start_error is not None:
            raise self._start_error
        self.started = True
        self.is_available = self._available_after_start


def test_vad_enabled_passes_vad_instance_to_audio_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """audio.vad_enabled: True + a healthy VAD → AudioCapture gets a non-None vad.

    Also pins the load: ``main`` must await ``VAD.start()``, or the
    instance it hands to AudioCapture reports ``is_available`` False for
    ever and the VAD worker discards every block.
    """
    vad_instance = _FakeVAD(available_after_start=True)
    vad_ctor = MagicMock(return_value=vad_instance)

    kwargs_out: list[dict] = []
    _install_fakes(monkeypatch, kwargs_out, vad_ctor)

    config_path = tmp_path / "config.yaml"
    _write_minimal_config(config_path)

    rc = m.main(["--config", str(config_path)])
    assert rc == 0
    assert len(kwargs_out) == 1, f"Expected 1 AudioCapture call, got {len(kwargs_out)}"
    assert kwargs_out[0].get("vad") is vad_instance, (
        f"Expected AudioCapture to receive the VAD instance, got {kwargs_out[0].get('vad')!r}"
    )
    assert vad_ctor.called, "VAD() was not constructed"
    assert vad_instance.started, "main() never awaited VAD.start() — silero is not loaded"
    assert vad_instance.is_available, "the VAD handed to AudioCapture is not usable"


def test_vad_disabled_passes_none_to_audio_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """audio.vad_enabled: False → AudioCapture gets vad=None; VAD() never called."""
    vad_ctor = MagicMock(name="VADClass")

    kwargs_out: list[dict] = []
    _install_fakes(monkeypatch, kwargs_out, vad_ctor)

    config_path = tmp_path / "config.yaml"
    _write_minimal_config(config_path)

    # Add audio.vad_enabled: false to the config.
    config_path.write_text(
        "asr:\n  provider: faster_whisper\n  model: base\naudio:\n  vad_enabled: false\n",
        encoding="utf-8",
    )

    rc = m.main(["--config", str(config_path)])
    assert rc == 0
    assert len(kwargs_out) == 1
    assert kwargs_out[0].get("vad") is None
    assert not vad_ctor.called, "VAD() was constructed despite vad_enabled=false"


def test_vad_init_failure_does_not_prevent_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If VAD() raises, main must still build the pipeline with vad=None.

    Fail-open is mandatory: VAD is a quality-of-life feature, not a
    prerequisite for the app to start.
    """
    vad_ctor = MagicMock(side_effect=RuntimeError("simulated silero load failure"))

    kwargs_out: list[dict] = []
    _install_fakes(monkeypatch, kwargs_out, vad_ctor)

    config_path = tmp_path / "config.yaml"
    _write_minimal_config(config_path)

    rc = m.main(["--config", str(config_path)])
    assert rc == 0, "main() must not crash when VAD construction fails"
    assert len(kwargs_out) == 1
    assert kwargs_out[0].get("vad") is None


def test_vad_unavailable_after_init_disables_vad(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAD starts successfully but ``is_available`` is still False → vad=None.

    A silero install that loads but reports unavailable (e.g. unsupported
    platform) should not block startup either.
    """
    vad_instance = _FakeVAD(available_after_start=False)
    vad_ctor = MagicMock(return_value=vad_instance)

    kwargs_out: list[dict] = []
    _install_fakes(monkeypatch, kwargs_out, vad_ctor)

    config_path = tmp_path / "config.yaml"
    _write_minimal_config(config_path)

    rc = m.main(["--config", str(config_path)])
    assert rc == 0
    assert vad_instance.started, "main() must still attempt the load before giving up"
    assert kwargs_out[0].get("vad") is None


def test_vad_load_failure_does_not_prevent_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``VAD.start()`` raising must degrade to vad=None, not crash startup.

    Construction succeeding and the model load failing are different
    failures; only the first was covered before.
    """
    vad_instance = _FakeVAD(start_error=RuntimeError("simulated silero load failure"))
    vad_ctor = MagicMock(return_value=vad_instance)

    kwargs_out: list[dict] = []
    _install_fakes(monkeypatch, kwargs_out, vad_ctor)

    config_path = tmp_path / "config.yaml"
    _write_minimal_config(config_path)

    rc = m.main(["--config", str(config_path)])
    assert rc == 0, "main() must not crash when the VAD model fails to load"
    assert kwargs_out[0].get("vad") is None


def test_audio_capture_regression_silence_triggers_stop_recording() -> None:
    """Regression: with a real VAD stub reporting silence past
    ``silence_timeout_ms``, ``stop_recording`` must fire.

    This is the behavior that has never worked end-to-end because the VAD
    was never wired in. We assert the AudioCapture contract directly with
    a stubbed VAD, mirroring the existing ``test_capture_vad_worker`` tests
    so the regression test is independent of main.py's wiring.
    """
    from unittest.mock import patch

    import numpy as np

    from agentvoca.audio.capture import AudioCapture
    from agentvoca.audio.vad import VAD
    from agentvoca.core.event_bus import EventBus

    event_bus = EventBus()

    speech_blocks = {"n": 0}

    def stubbed_is_speech(chunk: bytes) -> bool:
        speech_blocks["n"] += 1
        # Speech for the first 16 calls (~1 s of fake audio at 64 ms/block),
        # then silence — should trip auto-stop after silence_timeout_ms.
        return speech_blocks["n"] <= 16

    vad = VAD(event_bus=event_bus)
    vad._model = object()  # pretend silero loaded
    vad.is_speech = stubbed_is_speech  # type: ignore[assignment]

    stop_calls: list[None] = []
    original_stop = AudioCapture.stop_recording

    def spy_stop(self: AudioCapture) -> None:
        stop_calls.append(None)
        original_stop(self)

    with (
        patch("agentvoca.audio.capture.select_device") as mock_select,
        patch("agentvoca.audio.capture.sd.InputStream"),
        patch.object(AudioCapture, "stop_recording", spy_stop),
    ):
        mock_select.return_value = {"name": "Mock", "index": 0}
        capt = AudioCapture(
            event_bus=event_bus,
            vad=vad,
            silence_timeout_ms=200,  # short for test speed
            max_duration_s=600,
        )
        capt.start()
        capt.start_recording()
        # The fake VAD reports True for the first 16 calls, then False.
        for _ in range(20):
            capt._audio_callback(np.zeros((1024, 1), dtype=np.float32), 1024, None, None)
        # Give the worker a moment to flip the cached bool to silence.
        import time

        deadline = time.time() + 2.0
        while time.time() < deadline and capt._last_vad_speech:
            time.sleep(0.01)
        # Now wall-clock past silence_timeout_ms and a couple more blocks.
        time.sleep(0.3)
        for _ in range(3):
            capt._audio_callback(np.zeros((1024, 1), dtype=np.float32), 1024, None, None)
            if stop_calls:
                break

        assert stop_calls, "auto-stop never fired — VAD wiring regression"
        capt.stop()
