"""Tests for the first_run module."""

from __future__ import annotations

import json

import pytest

from agentvoca.setup.first_run import (
    AppState,
    config_exists,
    config_path,
    load_state,
    mark_first_run_complete,
    set_wizard_auto_open,
    state_path,
    write_state,
)


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Redirect ``Path.home()`` and AGENTVOCA_CONFIG to a temp dir."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("AGENTVOCA_CONFIG", raising=False)
    return tmp_path


def test_load_state_returns_defaults_when_file_missing(isolated_home):
    state = load_state()
    assert state.wizard_auto_open is True
    assert state.first_run_complete is False
    assert state.last_wizard_version == ""


def test_write_then_load_round_trips(isolated_home):
    state = AppState(
        wizard_auto_open=False,
        last_wizard_version="0.3.5",
        first_run_complete=True,
    )
    write_state(state)
    loaded = load_state()
    assert loaded.wizard_auto_open is False
    assert loaded.last_wizard_version == "0.3.5"
    assert loaded.first_run_complete is True


def test_load_state_handles_corrupt_file(isolated_home):
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not valid json {{{", encoding="utf-8")
    state = load_state()
    assert state.wizard_auto_open is True
    assert state.first_run_complete is False


def test_load_state_handles_non_dict_file(isolated_home):
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    state = load_state()
    assert state.wizard_auto_open is True


def test_set_wizard_auto_open_persists(isolated_home):
    set_wizard_auto_open(False)
    assert load_state().wizard_auto_open is False
    set_wizard_auto_open(True)
    assert load_state().wizard_auto_open is True


def test_mark_first_run_complete_persists(isolated_home):
    mark_first_run_complete("0.3.5")
    state = load_state()
    assert state.first_run_complete is True
    assert state.last_wizard_version == "0.3.5"


def test_config_exists_detects_file(isolated_home):
    assert config_exists() is False
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("asr:\n  provider: faster_whisper\n", encoding="utf-8")
    assert config_exists() is True


def test_config_exists_detects_env_override(isolated_home, monkeypatch):
    monkeypatch.setenv("AGENTVOCA_CONFIG", "/some/other/path.yaml")
    assert config_exists() is True
