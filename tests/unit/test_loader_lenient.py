"""Unit tests for the lenient config loader.

``load_config_lenient`` is the entry-point used by ``main.py`` when the
saved config might be broken (typically a missing API-key env var). It
must return a usable ``FullConfig`` plus a warning string, so the wizard
can be opened instead of the process exiting with code 1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentvoca.config.loader import load_config_lenient
from agentvoca.utils.errors import ConfigError


def test_lenient_load_passes_through_valid_config(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "asr:\n  provider: faster_whisper\n  model: base\n",
        encoding="utf-8",
    )
    config, warning = load_config_lenient(config_file)
    assert warning is None
    assert config.asr.provider == "faster_whisper"
    assert config.asr.model == "base"


def test_lenient_load_returns_warning_for_missing_api_key_env(tmp_path: Path, monkeypatch):
    """The classic case: a previously-saved remote config without its key."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "asr:\n"
        "  provider: openai_compatible\n"
        "  endpoint: https://openrouter.ai/api/v1\n"
        "  api_key_env: OPENROUTER_API_KEY\n"
        "  model: openai/gpt-4o-mini\n"
        "cleanup:\n"
        "  provider: openai_compatible\n"
        "  endpoint: https://openrouter.ai/api/v1\n"
        "  api_key_env: OPENROUTER_API_KEY\n"
        "  model: openai/gpt-4o-mini\n",
        encoding="utf-8",
    )
    config, warning = load_config_lenient(config_file)
    # The strict loader would have raised ConfigError; the lenient one
    # returns the parsed config + a human-readable warning.
    assert warning is not None
    assert "OPENROUTER_API_KEY" in warning
    # The config itself still has the user's saved values — we did not
    # silently swap in defaults.
    assert config.asr.provider == "openai_compatible"
    assert config.asr.endpoint == "https://openrouter.ai/api/v1"
    assert config.asr.api_key_env == "OPENROUTER_API_KEY"
    assert config.cleanup.provider == "openai_compatible"


def test_lenient_load_succeeds_when_key_is_present(tmp_path: Path, monkeypatch):
    """If the env var is set, the lenient loader returns no warning."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "asr:\n"
        "  provider: openai_compatible\n"
        "  endpoint: https://openrouter.ai/api/v1\n"
        "  api_key_env: OPENROUTER_API_KEY\n"
        "  model: openai/gpt-4o-mini\n"
        "cleanup:\n"
        "  provider: openai_compatible\n"
        "  endpoint: https://openrouter.ai/api/v1\n"
        "  api_key_env: OPENROUTER_API_KEY\n"
        "  model: openai/gpt-4o-mini\n",
        encoding="utf-8",
    )
    config, warning = load_config_lenient(config_file)
    assert warning is None
    assert config.asr.provider == "openai_compatible"


def test_lenient_load_falls_back_to_defaults_on_structural_error(tmp_path: Path, monkeypatch):
    """If the YAML is parseable but the schema is unsatisfiable, the loader
    should still return *something* sensible (a hard default) plus a warning
    so the wizard can show the real problem.
    """
    # Force the strict validator to fail on something unrelated to API keys:
    # an invalid hotkey. The lenient loader will hit the validator failure
    # and fall through to its hard-default path.
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "asr:\n"
        "  provider: faster_whisper\n"
        "  model: base\n"
        "hotkeys:\n"
        "  toggle_recording: this-is-not-a-valid-hotkey\n",
        encoding="utf-8",
    )
    config, warning = load_config_lenient(config_file)
    assert warning is not None
    # Even on a hard fall-back, we still produce a usable FullConfig so
    # the wizard can render and the user can correct the problem.
    assert config.asr.provider == "faster_whisper"


def test_lenient_load_raises_on_missing_file(tmp_path: Path):
    """A truly missing file is still a hard error — there is no way to
    be lenient about a file that does not exist.
    """
    with pytest.raises(ConfigError):
        load_config_lenient(tmp_path / "nope.yaml")
