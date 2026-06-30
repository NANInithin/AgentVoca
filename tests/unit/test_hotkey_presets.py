"""Tests for the hotkey_presets module."""

from __future__ import annotations

from agentvoca.setup.controllers.hotkey_presets import (
    ALL_ACTIONS,
    CUSTOM,
    PRESETS,
    action_by_field,
    find_preset,
    labels_for_dropdown,
    value_for_label,
    warning_for,
)


def test_presets_include_disabled_sentinel():
    assert any(p.value is None for p in PRESETS)


def test_presets_have_unique_labels():
    labels = [p.label for p in PRESETS]
    assert len(labels) == len(set(labels))


def test_find_preset_returns_disabled_for_none():
    preset = find_preset(None)
    assert preset is not None
    assert preset.value is None
    assert preset.label == "(disabled)"


def test_find_preset_returns_none_for_unknown_value():
    assert find_preset("ctrl+weird-key-99") is None


def test_labels_match_presets_order():
    labels = labels_for_dropdown()
    assert labels == [p.label for p in PRESETS]


def test_value_for_label_returns_DISABLED_for_disabled_label():
    assert value_for_label("(disabled)") is None


def test_value_for_label_returns_CUSTOM_for_unknown_label():
    assert value_for_label("Not in the list") == CUSTOM


def test_value_for_label_round_trips_every_preset():
    for preset in PRESETS:
        assert value_for_label(preset.label) == preset.value


def test_warning_for_returns_known_warning():
    # Preset warning is generic ("widely used"); the label is a separate UI string.
    assert "widely used" in (warning_for("ctrl+space") or "").lower()


def test_warning_for_returns_None_for_no_warning():
    assert warning_for("escape") is None


def test_all_actions_cover_every_hotkey_field():
    fields = {a.config_field for a in ALL_ACTIONS}
    assert "hotkeys.toggle_recording" in fields
    assert "hotkeys.open_settings" in fields
    assert "hotkeys.cancel" in fields
    assert "hotkeys.undo" in fields
    assert "hotkeys.insert_last_transcript" in fields
    assert "hotkeys.capture_screenshot" in fields


def test_all_actions_have_unique_config_fields():
    fields = [a.config_field for a in ALL_ACTIONS]
    assert len(fields) == len(set(fields))


def test_toggle_recording_is_required():
    toggle = action_by_field("hotkeys.toggle_recording")
    assert toggle is not None
    assert toggle.required is True


def test_action_by_field_returns_None_for_unknown():
    assert action_by_field("hotkeys.does_not_exist") is None
