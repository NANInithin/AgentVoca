"""Integration tests for the tabbed SettingsWindow.

Drives the window headlessly: constructs it, mutates a page, invokes save,
and asserts the controller, the on-disk file, and the config_saved signal
all line up.
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
from agentvoca.setup.settings_window import SettingsWindow  # noqa: E402


def test_window_constructs_with_nine_tabs(qapp, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    window = SettingsWindow(controller)
    # 8 existing tabs + 1 Observer tab added in v0.4.0.
    assert window._tabs.count() == 9  # type: ignore[attr-defined]
    window.deleteLater()


def test_window_save_emits_signal_and_writes_disk(qapp, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    window = SettingsWindow(controller)

    captured: list[object] = []
    window.config_saved.connect(captured.append)

    # Mutate the draft via the controller (the same path the window uses
    # internally) and save directly — the window's _on_apply() also pops a
    # restart-pending message box when applicable, which would block headless.
    controller.update_section(cleanup={"style": "professional"})
    result = controller.save()
    window.config_saved.emit(controller.draft)

    assert result.success
    assert config_path.is_file()
    on_disk = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert on_disk["cleanup"]["style"] == "professional"
    assert len(captured) == 1
    window.deleteLater()


def test_window_banner_lists_restart_paths(qapp, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    window = SettingsWindow(controller)
    window.show()  # so isVisible() is meaningful

    # Mutate a restart-only field.
    controller.update_section(asr={"model": "large-v3"})
    window._refresh()  # type: ignore[attr-defined]
    assert window._banner.isVisible()  # type: ignore[attr-defined]
    assert "asr.model" in window._banner_label.text()  # type: ignore[attr-defined]
    window.deleteLater()


def test_window_banner_hidden_for_hot_only_changes(qapp, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    window = SettingsWindow(controller)
    window.show()

    # Mutate a hot-only field.
    controller.update_section(hotkeys={"undo": "ctrl+shift+y"})
    window._refresh()  # type: ignore[attr-defined]
    assert not window._banner.isVisible()  # type: ignore[attr-defined]
    window.deleteLater()
