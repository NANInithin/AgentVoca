"""Integration tests for the Observer settings page (OBS-27).

Drives the page headlessly: constructs the controller with a default
config, instantiates the page, mutates a few fields, calls save, and
checks the controller draft, restart classification, and re-load
round-trip.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6", reason="PySide6 (Qt) not available")

from agentvoca.setup.controllers.config_controller import load_controller  # noqa: E402
from agentvoca.setup.pages.observer_page import ObserverPage  # noqa: E402


@pytest.fixture(autouse=True)
def _force_offscreen_qt():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    yield


@pytest.fixture
def qapp():
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_page_loads_from_default_config(qapp, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    page = ObserverPage(controller)
    page.load_from_controller()
    # Defaults from the schema.
    assert page._enabled.isChecked() is False  # observer.enabled defaults to False
    assert page._retention_days.value() == 7
    assert page._trig_window.isChecked() is True
    assert page._trig_speech.isChecked() is True  # D9
    assert page._ocr_provider.currentData() == "rapidocr"
    assert page._compile_provider.currentData() == "rules"
    # Cloud warning is hidden when both providers are local.
    assert not page._cloud_warning.isVisible()


def test_page_save_round_trip_through_full_config(qapp, tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    page = ObserverPage(controller)
    page.load_from_controller()
    page._enabled.setChecked(True)
    page._retention_days.setValue(14)
    page._trig_speech.setChecked(False)
    page._compile_provider.setCurrentIndex(1)  # openai_compatible
    page._compile_endpoint.setText("https://api.example.com/v1")
    page._compile_model.setText("gpt-4o-mini")
    page._compile_api_key_env.setText("MY_LLM_KEY")
    # The full-config validator enforces the env var when
    # observer.compile.provider is remote. Set it for the test.
    monkeypatch.setenv("MY_LLM_KEY", "test-value")
    # Cloud warning should now be visible.
    page._update_cloud_warning()
    assert page._cloud_warning.isVisibleTo(page) or page._cloud_warning.isVisible()
    page.save_to_controller()
    draft = controller.draft.observer
    assert draft.enabled is True
    assert draft.storage.retention_days == 14
    assert draft.triggers.speech_onset is False
    assert draft.compile.provider == "openai_compatible"
    assert draft.compile.endpoint == "https://api.example.com/v1"
    assert draft.compile.model == "gpt-4o-mini"
    assert draft.compile.api_key_env == "MY_LLM_KEY"
    # Re-load to ensure no fields lost.
    page.load_from_controller()
    assert page._enabled.isChecked() is True
    assert page._retention_days.value() == 14
    assert page._trig_speech.isChecked() is False
    assert page._compile_provider.currentData() == "openai_compatible"
    assert page._compile_endpoint.text() == "https://api.example.com/v1"


def test_cloud_warning_appears_for_ocr_provider(qapp, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    page = ObserverPage(controller)
    page.load_from_controller()
    assert not page._cloud_warning.isVisibleTo(page)
    page._ocr_provider.setCurrentIndex(1)  # openai_compatible
    page._update_cloud_warning()
    assert page._cloud_warning.isVisibleTo(page)


def test_privacy_notice_visible_by_default(qapp, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    page = ObserverPage(controller)
    page.load_from_controller()
    # The page has a privacy notice widget as a child. We assert the
    # widget exists and is in the visible tree; ``isVisible`` requires
    # the page itself to be shown, which it is not in the harness.
    from PySide6 import QtWidgets

    notices = [
        w
        for w in page.findChildren(QtWidgets.QLabel)
        if "Observer records your microphone" in (w.text() or "")
    ]
    assert notices, "Privacy notice is missing from the page"
    # The widget is part of the layout (its parent is the page's body
    # layout, so it is reachable). The page makes it always visible by
    # default \u2014 a future contributor who folds it behind a checkbox
    # must update this test along with the privacy contract.
    assert not notices[0].isHidden(), "Privacy notice must be always-visible"


def test_exclusion_lists_round_trip_with_blank_lines(qapp, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    page = ObserverPage(controller)
    page.load_from_controller()
    # Replace with controlled input that has trailing blank lines.
    page._exclude_apps.setPlainText("chrome.exe\n\nfirefox.exe\n\n\n")
    page._exclude_titles.setPlainText("*InPrivate*\n\n*Password*\n")
    page.save_to_controller()
    apps = list(controller.draft.observer.privacy.exclude_apps)
    titles = list(controller.draft.observer.privacy.exclude_title_patterns)
    assert apps == ["chrome.exe", "firefox.exe"]
    assert titles == ["*InPrivate*", "*Password*"]


def test_restart_classification_for_observer_enabled(qapp, tmp_path: Path) -> None:
    """``observer.enabled`` is classified as restart-required by the policy."""
    from agentvoca.setup.controllers.restart_policy import is_restart_field

    assert is_restart_field("observer.enabled") is True
    # storage.dir too.
    assert is_restart_field("observer.storage.dir") is True
    # Triggers are hot.
    assert is_restart_field("observer.triggers.window_change") is False
    # Compile provider is hot.
    assert is_restart_field("observer.compile.provider") is False


def test_hotkeys_page_contains_observer_actions(qapp, tmp_path: Path) -> None:
    """The two Observer hotkeys appear as rows on the Hotkeys page."""
    from agentvoca.setup.pages.hotkeys_page import HotkeysPage

    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    page = HotkeysPage(controller)
    fields = [row[0] for row in page._rows]
    assert "hotkeys.toggle_observer" in fields
    assert "hotkeys.pause_observer" in fields
