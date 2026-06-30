"""Tests for the ConfigController."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agentvoca.config.schema import ASRConfig, FullConfig
from agentvoca.setup.controllers.config_controller import (
    defaults_controller,
    load_controller,
)


def test_controller_loads_from_file(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "asr:\n  provider: faster_whisper\n  model: small\n",
        encoding="utf-8",
    )
    c = load_controller(path)
    assert c.draft.asr.model == "small"
    assert c.is_dirty() is False


def test_controller_falls_back_to_defaults_when_missing(tmp_path: Path):
    c = load_controller(tmp_path / "nope.yaml")
    assert c.draft.asr.provider == "faster_whisper"
    assert c.draft.asr.model == "base"


def test_controller_marks_dirty_after_update(tmp_path: Path):
    c = load_controller(tmp_path / "nope.yaml")
    c.update_section(cleanup={"style": "technical"})
    assert c.is_dirty() is True
    assert "cleanup.style" in c.changed_paths()


def test_controller_save_persists_to_disk(tmp_path: Path):
    path = tmp_path / "config.yaml"
    c = load_controller(path)
    c.update_section(cleanup={"style": "technical"})
    result = c.save()
    assert result.success
    on_disk = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert on_disk["cleanup"]["style"] == "technical"


def test_controller_save_returns_hot_and_restart_paths(tmp_path: Path):
    c = load_controller(tmp_path / "nope.yaml")
    c.update_section(cleanup={"style": "technical"}, asr={"model": "large-v3"})
    result = c.save()
    assert result.success
    assert "cleanup.style" in result.hot_paths
    assert "asr.model" in result.restart_paths


def test_controller_save_makes_backup(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "asr:\n  provider: faster_whisper\n  model: tiny\n",
        encoding="utf-8",
    )
    c = load_controller(path)
    c.update_section(asr={"model": "base"})
    result = c.save()
    assert result.success
    assert result.backup_path.exists()
    assert "tiny" in result.backup_path.read_text(encoding="utf-8")


def test_controller_update_section_rejects_invalid_value(tmp_path: Path):
    """A field that violates the schema raises during update_section."""
    from agentvoca.utils.errors import ConfigError

    c = load_controller(tmp_path / "nope.yaml")
    with pytest.raises(ConfigError):
        c.update_section(asr={"streaming_chunk_ms": 10})


def test_controller_validate_detects_drift(tmp_path: Path):
    """Drift between dict and pydantic state is caught by validate()."""
    c = load_controller(tmp_path / "nope.yaml")
    # Bypass update_section's validation by writing the dump directly.
    c._draft_dump["asr"]["streaming_chunk_ms"] = 5
    ok, err = c.validate()
    assert ok is False
    assert err is not None
    assert "streaming_chunk_ms" in err or "100" in err


def test_controller_revert_restores_original(tmp_path: Path):
    c = load_controller(tmp_path / "nope.yaml")
    c.update_section(cleanup={"style": "technical"})
    assert c.is_dirty()
    c.revert()
    assert c.is_dirty() is False
    assert c.draft.cleanup.style == "standard"


def test_controller_replace_draft_replaces_entire_config(tmp_path: Path):
    c = load_controller(tmp_path / "nope.yaml")
    fresh = FullConfig(asr=ASRConfig(provider="faster_whisper", model="tiny"))
    c.replace_draft(fresh)
    assert c.draft.asr.model == "tiny"


def test_defaults_controller_uses_zero_config_defaults(tmp_path: Path):
    c = defaults_controller(tmp_path / "x.yaml")
    assert c.draft.asr.provider == "faster_whisper"
    assert c.draft.asr.model == "base"
    assert c.draft.cleanup.provider == "rules"


def test_controller_changed_paths_include_top_level_for_dict_changes(tmp_path: Path):
    c = load_controller(tmp_path / "nope.yaml")
    c.update_section(vocabulary={"inline": ["PyTorch", "CUDA"]})
    paths = c.changed_paths()
    # Top-level diff: vocabulary.inline is detected.
    assert "vocabulary.inline" in paths or "vocabulary" in paths
