"""Tests for the restart_policy module."""

from __future__ import annotations

from agentvoca.setup.controllers.restart_policy import (
    all_known_paths,
    is_hot_field,
    is_restart_field,
    partition,
)


def test_asr_provider_requires_restart():
    assert is_restart_field("asr.provider")
    assert not is_hot_field("asr.provider")


def test_cleanup_provider_is_hot():
    assert is_hot_field("cleanup.provider")
    assert not is_restart_field("cleanup.provider")


def test_hotkeys_are_hot():
    for key in (
        "hotkeys.toggle_recording",
        "hotkeys.open_settings",
        "hotkeys.cancel",
        "hotkeys.undo",
        "hotkeys.insert_last_transcript",
        "hotkeys.capture_screenshot",
    ):
        assert is_hot_field(key), key


def test_audio_requires_restart():
    for key in (
        "audio.input_device",
        "audio.sample_rate",
        "audio.channels",
        "audio.vad_enabled",
        "audio.silence_timeout_ms",
        "audio.max_recording_duration_s",
    ):
        assert is_restart_field(key), key


def test_insertion_requires_restart():
    for key in (
        "insertion.strategy",
        "insertion.clipboard_fallback",
        "insertion.delay_between_chars_ms",
    ):
        assert is_restart_field(key), key


def test_vision_enable_requires_restart_but_runtime_knobs_are_hot():
    assert is_restart_field("vision.enabled")
    assert is_restart_field("vision.provider")
    assert is_restart_field("vision.endpoint")
    assert is_restart_field("vision.api_key_env")
    assert is_restart_field("vision.model")
    assert is_hot_field("vision.anchor_phrases")
    assert is_hot_field("vision.output_format")
    assert is_hot_field("vision.capture_timeout_s")


def test_partition_splits_correctly():
    paths = ["asr.provider", "cleanup.style", "hotkeys.toggle_recording", "audio.sample_rate"]
    hot, restart = partition(paths)
    assert "cleanup.style" in hot
    assert "hotkeys.toggle_recording" in hot
    assert "asr.provider" in restart
    assert "audio.sample_rate" in restart


def test_partition_defaults_unknown_to_restart():
    hot, restart = partition(["unknown.field"])
    assert "unknown.field" in restart
    assert "unknown.field" not in hot


def test_all_known_paths_cover_every_field():
    hot, restart = all_known_paths()
    assert "asr.provider" in restart
    assert "cleanup.provider" in hot
    assert "hotkeys.toggle_recording" in hot
    # No overlap.
    assert not (hot & restart)
