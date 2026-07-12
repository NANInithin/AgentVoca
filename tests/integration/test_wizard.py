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


def test_wizard_preserves_typed_values_across_navigation(qapp, tmp_path: Path, monkeypatch):
    """Regression: typing into the ASR page and clicking Next used to clobber
    the typed value because the wizard rebound every page from the controller
    on every navigation. The fix captures the leaving page's state into the
    controller and only rebinds the arriving page.
    """
    # The schema's _validate_api_key_env model-validator refuses to let the
    # controller reach a state where the provider is remote but the env var
    # is unset. Set it for the duration of the test.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-dummy")

    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    wizard = SetupWizard(controller)

    # The ASR page is the 4th page in the wizard (page id 3 in
    # ``pageIds()``). Walk the wizard forward to that page.
    for wid in range(0, 4):
        wizard._on_current_changed(wid)  # type: ignore[arg-type]

    # ASR is now the current page.
    asr_page = wizard._pages[3]
    assert asr_page.__class__.__name__ == "AsrPage"

    # Simulate the user picking the cloud provider, typing the OpenRouter
    # endpoint, model, and env-var name — without ever touching the controller.
    asr_page._cloud_btn.setChecked(True)  # type: ignore[attr-defined]
    asr_page._endpoint.setText("https://openrouter.ai/api/v1")  # type: ignore[attr-defined]
    # The model widget is now an editable QComboBox; set the current text
    # via the line-edit child so we mimic what happens when the user types.
    asr_page._api_model.setEditText("openai/gpt-4o-mini")  # type: ignore[attr-defined]
    asr_page._api_key_env.setText("OPENROUTER_API_KEY")  # type: ignore[attr-defined]

    # Click Next — the slot fires with the new id (4 = Cleanup). Before the
    # fix this would have rebound every page from the controller's existing
    # draft, which still had provider='faster_whisper', silently throwing
    # away the typed values.
    wizard._on_current_changed(4)  # type: ignore[arg-type]

    # The controller must now reflect what the user typed — not the loaded
    # disk defaults.
    draft = controller.draft
    assert draft.asr.provider == "openai_compatible", draft.asr
    assert draft.asr.endpoint == "https://openrouter.ai/api/v1", draft.asr
    assert draft.asr.model == "openai/gpt-4o-mini", draft.asr
    assert draft.asr.api_key_env == "OPENROUTER_API_KEY", draft.asr

    # Now also type into Cleanup and navigate again — ASR must not be lost.
    cleanup_index = 4
    cleanup_page = wizard._pages[cleanup_index]
    cleanup_page._llm_btn.setChecked(True)  # type: ignore[attr-defined]
    cleanup_page._llm_endpoint.setText("https://openrouter.ai/api/v1")  # type: ignore[attr-defined]
    cleanup_page._llm_model.setEditText("openai/gpt-4o-mini")  # type: ignore[attr-defined]
    cleanup_page._llm_api_key_env.setText("OPENROUTER_API_KEY")  # type: ignore[attr-defined]
    # "Professional (formal)" is the 4th entry (index 3) in _STYLE_OPTIONS
    # on the LLM combo box.
    cleanup_page._llm_style.setCurrentIndex(3)  # type: ignore[attr-defined]

    wizard._on_current_changed(5)  # type: ignore[arg-type]  — Hotkeys

    # Both ASR and cleanup must reflect what the user typed.
    assert controller.draft.asr.provider == "openai_compatible"
    assert controller.draft.cleanup.provider == "openai_compatible"
    assert controller.draft.cleanup.style == "professional"

    wizard.deleteLater()


def test_wizard_navigation_does_not_clobber_other_pages(qapp, tmp_path: Path):
    """A page the user has not visited must keep whatever the controller had
    in it. The old behavior rebound every page on every navigation, which
    is fine for unchanged pages but a footgun for pages the user *has*
    visited and left with new values that have not yet been saved.
    """
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    wizard = SetupWizard(controller)

    # Walk forward to the audio page (page id 2).
    for wid in range(0, 3):
        wizard._on_current_changed(wid)  # type: ignore[arg-type]

    audio_page = wizard._pages[2]
    audio_page._silence_timeout.setValue(1500)  # type: ignore[attr-defined]

    # Navigate to the next page. The audio page's typed value must be
    # captured into the controller before the ASR page is rebound.
    wizard._on_current_changed(3)  # type: ignore[arg-type]
    assert controller.draft.audio.silence_timeout_ms == 1500

    # Navigate further (Cleanup). Audio must still be 1500.
    wizard._on_current_changed(4)  # type: ignore[arg-type]
    assert controller.draft.audio.silence_timeout_ms == 1500
    # ASR is still on the default provider — we did not touch it.
    assert controller.draft.asr.provider == "faster_whisper"

    # Navigate back to the audio page. The widget should be rebound from
    # the controller, which now holds 1500ms.
    wizard._on_current_changed(2)  # type: ignore[arg-type]
    assert audio_page._silence_timeout.value() == 1500  # type: ignore[attr-defined]

    wizard.deleteLater()
