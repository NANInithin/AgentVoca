"""Startup-ordering tests for ``agentvoca.main.main``.

The critical guarantee (fixed in v0.3.5): on a genuine first run — no config
file on disk — the heavy pipeline (ASR provider construction + model warm-up,
audio device, hotkeys) must not be built until *after* the user has completed
the setup wizard. Otherwise a user who is about to pick a cloud provider still
pays for a multi-second local Whisper model load first.

To assert the ordering without any real Qt / audio hardware / model download,
every heavy collaborator ``main`` reaches for is replaced with a lightweight
fake that records into a shared ``order`` list. What we assert is the relative
order of two events: the wizard's modal ``exec`` and the orchestrator's
``start`` (which is what triggers warm-up).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6", reason="PySide6 (Qt) not available")

import agentvoca.main as m  # noqa: E402


def _install_fakes(monkeypatch, order: list[str], *, wizard_saves: bool = False):
    """Replace every heavy collaborator in ``agentvoca.main`` with a fake.

    Returns a dict of the fake classes/instances so a test can make
    assertions about how they were used.
    """

    class FakeApp:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def setQuitOnLastWindowClosed(self, _value: bool) -> None:
            pass

        def exec(self) -> int:
            order.append("app.exec")
            return 0

        def quit(self) -> None:
            pass

    class FakeMessageBox:
        @staticmethod
        def warning(*_args, **_kwargs) -> None:
            order.append("messagebox.warning")

    fake_qtwidgets = SimpleNamespace(QApplication=FakeApp, QMessageBox=FakeMessageBox)

    class FakeWizard:
        last_instance: "FakeWizard | None" = None

        def __init__(self, controller, *_a, **_k) -> None:
            self._controller = controller
            self.config_saved = MagicMock()
            FakeWizard.last_instance = self

        def exec(self) -> int:
            order.append("wizard.exec")
            if wizard_saves:
                # Emulate the user picking a cloud provider and saving.
                from agentvoca.config.schema import ASRConfig

                self._controller.update_section(
                    asr=ASRConfig(
                        provider="openai_compatible",
                        model="openai/gpt-4o-mini",
                        endpoint="https://openrouter.ai/api/v1",
                        api_key_env="OPENROUTER_API_KEY",
                    ).model_dump()
                )
            return 0

        def show(self) -> None:
            order.append("wizard.show")

        def raise_(self) -> None:
            pass

        def activateWindow(self) -> None:
            pass

        def close(self) -> None:
            pass

    class FakeOrchestrator:
        last_config = None

        def __init__(self, *, config, **_k) -> None:
            FakeOrchestrator.last_config = config

        async def start(self) -> None:
            order.append("orchestrator.start")

        async def stop(self) -> None:
            pass

    class FakeAudio:
        def __init__(self, *_a, **_k) -> None:
            self.is_recording = False

        def start(self) -> None:
            order.append("audio.start")

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
            order.append("hotkeys.start")

        def stop(self) -> None:
            pass

    fake_tray = SimpleNamespace(
        open_settings_action=SimpleNamespace(triggered=MagicMock()),
        open_wizard_action=SimpleNamespace(triggered=MagicMock()),
        quit_action=SimpleNamespace(triggered=MagicMock()),
        show_message=lambda *a, **k: None,
    )

    # Keep state.json out of the picture (it lives in the real home dir):
    # auto-open defaults to True, which is what a fresh install would see.
    from agentvoca.setup.first_run import AppState

    monkeypatch.setattr(m, "load_state", lambda: AppState(wizard_auto_open=True))

    monkeypatch.setattr(m, "QtWidgets", fake_qtwidgets)
    monkeypatch.setattr(m, "SetupWizard", FakeWizard)
    monkeypatch.setattr(m, "SettingsWindow", MagicMock())
    monkeypatch.setattr(m, "Orchestrator", FakeOrchestrator)
    monkeypatch.setattr(m, "AudioCapture", FakeAudio)
    monkeypatch.setattr(m, "HotkeyManager", FakeHotkeys)
    monkeypatch.setattr(m, "StatusOverlay", lambda *a, **k: SimpleNamespace(stop=lambda: None))
    monkeypatch.setattr(m, "TrayApp", lambda *a, **k: fake_tray)

    return {"wizard": FakeWizard, "orchestrator": FakeOrchestrator}


def test_first_run_builds_pipeline_only_after_the_wizard(tmp_path: Path, monkeypatch):
    # The schema's _validate_api_key_env validator refuses a remote provider
    # with an unset key; set a dummy so the fake "save" can build the draft.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-dummy")

    order: list[str] = []
    fakes = _install_fakes(monkeypatch, order, wizard_saves=True)

    config_path = tmp_path / "config.yaml"  # does not exist -> first run
    assert not config_path.is_file()

    rc = m.main(["--config", str(config_path)])
    assert rc == 0

    # The modal wizard must run before the orchestrator (and hence warm-up).
    assert "wizard.exec" in order
    assert "orchestrator.start" in order
    assert order.index("wizard.exec") < order.index("orchestrator.start"), order
    assert order.index("wizard.exec") < order.index("audio.start"), order

    # And the pipeline is built from what the user chose in the wizard, not
    # the local-whisper default — so no local model would have been loaded.
    assert fakes["orchestrator"].last_config.asr.provider == "openai_compatible"


def test_first_run_does_not_also_auto_open_wizard_nonmodally(tmp_path: Path, monkeypatch):
    order: list[str] = []
    _install_fakes(monkeypatch, order, wizard_saves=False)

    config_path = tmp_path / "config.yaml"
    rc = m.main(["--config", str(config_path)])
    assert rc == 0

    # The first-run wizard is modal (exec); it must not *also* be shown
    # non-blocking afterwards.
    assert order.count("wizard.exec") == 1
    assert "wizard.show" not in order


def test_existing_config_starts_pipeline_without_a_modal_wizard(tmp_path: Path, monkeypatch):
    order: list[str] = []
    _install_fakes(monkeypatch, order, wizard_saves=False)

    # A minimal but valid existing config (local whisper needs no API key).
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "asr:\n  provider: faster_whisper\n  model: base\n",
        encoding="utf-8",
    )

    rc = m.main(["--config", str(config_path)])
    assert rc == 0

    # Not a first run: the pipeline starts, and the wizard is only auto-opened
    # non-blocking (show), never run modally (exec).
    assert "orchestrator.start" in order
    assert "wizard.exec" not in order
    assert "wizard.show" in order  # wizard_auto_open defaults to True
    # Pipeline built before the non-blocking wizard is shown.
    assert order.index("orchestrator.start") < order.index("wizard.show"), order


def test_existing_config_with_missing_api_key_does_not_crash(tmp_path: Path, monkeypatch):
    # Regression: an existing config that references an unset API-key env var
    # (e.g. OPENROUTER_API_KEY never set this session) must NOT crash on
    # startup. The lenient loader substitutes defaults, main surfaces a
    # warning dialog and opens the wizard so the user can fix it.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    order: list[str] = []
    _install_fakes(monkeypatch, order, wizard_saves=False)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "asr:\n  provider: faster_whisper\n  model: base\n"
        "cleanup:\n"
        "  provider: openai_compatible\n"
        "  model: openai/gpt-4o-mini\n"
        "  endpoint: https://openrouter.ai/api/v1\n"
        "  api_key_env: OPENROUTER_API_KEY\n",
        encoding="utf-8",
    )

    rc = m.main(["--config", str(config_path)])
    assert rc == 0  # started rather than crashing with ConfigError

    # The broken config opens the wizard modally (exec), before the pipeline
    # is built — so the user can fix it before any model warm-up.
    assert "wizard.exec" in order
    assert order.index("wizard.exec") < order.index("orchestrator.start"), order
    # The standalone "Config needs attention" message box is gone (the warning
    # is now an in-wizard banner), and the wizard is not *also* auto-opened.
    assert "messagebox.warning" not in order
    assert "wizard.show" not in order
    # And the app still started on lenient defaults.
    assert "orchestrator.start" in order
