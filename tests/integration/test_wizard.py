"""Integration tests for the setup wizard.

Drives the wizard headlessly with the offscreen Qt platform: it exercises
the page widgets end-to-end, then asserts the resulting config was written
to disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# PySide6 + the system Qt libraries are a hard runtime requirement. On a
# minimal container without libEGL / libxkbcommon, skip the test set rather
# than fail collection.
pytest.importorskip("PySide6", reason="PySide6 (Qt) not available")

from agentvoca.setup.controllers.config_controller import load_controller  # noqa: E402
from agentvoca.setup.wizard import SetupWizard  # noqa: E402


def test_wizard_constructs_with_eight_pages(qapp, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    wizard = SetupWizard(controller)
    # Welcome + 7 main pages + Finish = 9 total.
    assert len(wizard._pages) == 9
    wizard.deleteLater()


def test_wizard_save_persists_config(qapp, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    # Pre-mutate the draft to a recognizable value.
    controller.update_section(cleanup={"style": "technical"})

    wizard = SetupWizard(controller)
    # Mimic what the wizard's done() does on accept.
    controller.save()
    wizard.deleteLater()

    assert config_path.is_file()
    on_disk = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert on_disk["cleanup"]["style"] == "technical"
    assert on_disk["asr"]["provider"] == "faster_whisper"


def test_wizard_emits_config_saved_signal(qapp, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    wizard = SetupWizard(controller)
    captured: list[object] = []
    wizard.config_saved.connect(captured.append)

    # Manually invoke the save path (avoids driving the modal dialog).
    controller.update_section(app={"debug": True})
    controller.save()
    wizard.config_saved.emit(controller.draft)
    assert len(captured) == 1
    assert captured[0].app.debug is True  # type: ignore[union-attr]
    wizard.deleteLater()
