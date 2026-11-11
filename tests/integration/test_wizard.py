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


def test_wizard_asks_only_model_and_api_questions(qapp, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    wizard = SetupWizard(controller)
    names = [page.__class__.__name__ for page in wizard._pages]
    assert names == ["WelcomePage", "AsrPage", "CleanupPage"]

    asr_page, cleanup_page = wizard._pages[1], wizard._pages[2]
    # Tuning options stay in Settings; the wizard keeps model + API key.
    assert not asr_page._streaming.isVisibleTo(asr_page)  # type: ignore[attr-defined]
    assert asr_page._language_hint.isHidden()  # type: ignore[attr-defined]
    assert asr_page._api_key_env.isHidden()  # type: ignore[attr-defined]
    assert not asr_page._api_key.isHidden()  # type: ignore[attr-defined]
    assert cleanup_page._llm_prompt_path.isHidden()  # type: ignore[attr-defined]
    assert cleanup_page._llm_style.isHidden()  # type: ignore[attr-defined]
    assert not cleanup_page._llm_api_key.isHidden()  # type: ignore[attr-defined]
    wizard.deleteLater()


def test_provider_preset_fills_endpoint_and_key_name(qapp, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-dummy")
    controller = load_controller(tmp_path / "config.yaml")
    wizard = SetupWizard(controller)
    asr_page = wizard._pages[1]
    asr_page.load_from_controller()
    asr_page._cloud_btn.setChecked(True)  # type: ignore[attr-defined]
    preset = asr_page._preset  # type: ignore[attr-defined]
    preset.setCurrentIndex(preset.findText("Groq"))
    asr_page._api_model.setEditText("whisper-large-v3")  # type: ignore[attr-defined]
    asr_page.save_to_controller()
    assert controller.draft.asr.endpoint == "https://api.groq.com/openai/v1"
    assert controller.draft.asr.api_key_env == "GROQ_API_KEY"
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

    # Walk the wizard forward to the ASR page (page id 1).
    for wid in range(0, 2):
        wizard._on_current_changed(wid)  # type: ignore[arg-type]

    asr_page = wizard._pages[1]
    assert asr_page.__class__.__name__ == "AsrPage"

    # Simulate the user picking the cloud provider, typing the OpenRouter
    # endpoint, model, and env-var name — without ever touching the controller.
    asr_page._cloud_btn.setChecked(True)  # type: ignore[attr-defined]
    asr_page._endpoint.setText("https://openrouter.ai/api/v1")  # type: ignore[attr-defined]
    # The model widget is now an editable QComboBox; set the current text
    # via the line-edit child so we mimic what happens when the user types.
    asr_page._api_model.setEditText("openai/gpt-4o-mini")  # type: ignore[attr-defined]
    asr_page._api_key_env.setText("OPENROUTER_API_KEY")  # type: ignore[attr-defined]

    # Click Next — the slot fires with the new id (2 = Cleanup). Before the
    # fix this would have rebound every page from the controller's existing
    # draft, which still had provider='faster_whisper', silently throwing
    # away the typed values.
    wizard._on_current_changed(2)  # type: ignore[arg-type]

    # The controller must now reflect what the user typed — not the loaded
    # disk defaults.
    draft = controller.draft
    assert draft.asr.provider == "openai_compatible", draft.asr
    assert draft.asr.endpoint == "https://openrouter.ai/api/v1", draft.asr
    assert draft.asr.model == "openai/gpt-4o-mini", draft.asr
    assert draft.asr.api_key_env == "OPENROUTER_API_KEY", draft.asr

    # Now also type into Cleanup and navigate again — ASR must not be lost.
    cleanup_index = 2
    cleanup_page = wizard._pages[cleanup_index]
    cleanup_page._llm_btn.setChecked(True)  # type: ignore[attr-defined]
    cleanup_page._llm_endpoint.setText("https://openrouter.ai/api/v1")  # type: ignore[attr-defined]
    cleanup_page._llm_model.setEditText("openai/gpt-4o-mini")  # type: ignore[attr-defined]
    cleanup_page._llm_api_key_env.setText("OPENROUTER_API_KEY")  # type: ignore[attr-defined]
    # "Professional (formal)" is the 4th entry (index 3) in _STYLE_OPTIONS
    # on the LLM combo box.
    cleanup_page._llm_style.setCurrentIndex(3)  # type: ignore[attr-defined]

    wizard._on_current_changed(1)  # type: ignore[arg-type]  — back to ASR

    # Both ASR and cleanup must reflect what the user typed.
    assert controller.draft.asr.provider == "openai_compatible"
    assert controller.draft.cleanup.provider == "openai_compatible"
    assert controller.draft.cleanup.style == "professional"

    wizard.deleteLater()


def test_wizard_keeps_settings_it_does_not_ask_about(qapp, tmp_path: Path):
    """Options the wizard no longer shows keep whatever the config had."""
    config_path = tmp_path / "config.yaml"
    controller = load_controller(config_path)
    controller.update_section(audio={"silence_timeout_ms": 1500})
    controller.update_section(cleanup={"style": "technical"})
    wizard = SetupWizard(controller)

    for wid in range(0, 3):
        wizard._on_current_changed(wid)  # type: ignore[arg-type]
    for page in wizard._pages:
        page.save_to_controller()

    assert controller.draft.audio.silence_timeout_ms == 1500
    assert controller.draft.cleanup.style == "technical"
    assert controller.draft.asr.provider == "faster_whisper"
    wizard.deleteLater()
