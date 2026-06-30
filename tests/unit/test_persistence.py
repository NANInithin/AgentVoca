"""Tests for the persistence module."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agentvoca.config.schema import ASRConfig, FullConfig
from agentvoca.setup.persistence import (
    load_from_disk,
    save_to_disk,
    save_to_disk_preserving,
    serialize,
)
from agentvoca.utils.errors import ConfigError


def test_serialize_round_trips_through_yaml(tmp_path: Path):
    config = FullConfig(asr=ASRConfig(provider="faster_whisper", model="base"))
    dumped = yaml.safe_dump(serialize(config), sort_keys=False)
    # Sort_keys=False preserves order; check key presence.
    assert "asr:" in dumped
    assert "provider: faster_whisper" in dumped


def test_save_to_disk_writes_yaml(tmp_path: Path):
    path = tmp_path / "config.yaml"
    config = FullConfig(asr=ASRConfig(provider="faster_whisper", model="base"))
    save_to_disk(config, path)
    assert path.is_file()
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["asr"]["provider"] == "faster_whisper"


def test_save_to_disk_creates_parent_dirs(tmp_path: Path):
    path = tmp_path / "nested" / "deeper" / "config.yaml"
    config = FullConfig(asr=ASRConfig(provider="faster_whisper", model="base"))
    save_to_disk(config, path)
    assert path.is_file()


def test_save_to_disk_makes_backup_when_existing(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("asr:\n  provider: faster_whisper\n  model: tiny\n", encoding="utf-8")
    config = FullConfig(asr=ASRConfig(provider="faster_whisper", model="base"))
    backup = save_to_disk(config, path)
    assert backup.exists()
    assert "tiny" in backup.read_text(encoding="utf-8")
    # The new file should be the new config.
    assert "base" in path.read_text(encoding="utf-8")


def test_save_to_disk_no_backup_when_no_existing(tmp_path: Path):
    path = tmp_path / "config.yaml"
    config = FullConfig(asr=ASRConfig(provider="faster_whisper", model="base"))
    backup = save_to_disk(config, path)
    assert backup == Path()


def test_save_to_disk_preserving_keeps_unknown_keys(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "asr:\n  provider: faster_whisper\n  model: base\nfuture_field: 42\n",
        encoding="utf-8",
    )
    new_config = FullConfig(asr=ASRConfig(provider="faster_whisper", model="large-v3"))
    save_to_disk_preserving(new_config, path)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["asr"]["model"] == "large-v3"
    assert loaded["future_field"] == 42


def test_load_from_disk_uses_loader(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("asr:\n  provider: faster_whisper\n  model: small\n", encoding="utf-8")
    config = load_from_disk(path)
    assert config.asr.model == "small"


def test_load_from_disk_raises_on_missing(tmp_path: Path):
    with pytest.raises(ConfigError):
        load_from_disk(tmp_path / "missing.yaml")
