"""Tests for config schema and loader.

Covers all validation rules from Section 5.2 of the architecture spec.
"""

import os
from pathlib import Path

import pydantic
import pytest
import yaml

from agentvoca.config.loader import load_config, load_config_from_dict
from agentvoca.config.schema import (
    AppConfig,
    AudioConfig,
    CleanupConfig,
    FullConfig,
    HotkeysConfig,
    InsertionConfig,
    SnippetsConfig,
    VocabularyConfig,
)
from agentvoca.utils.errors import ConfigError

# ── Fixture helpers ────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "configs"


def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Default values ─────────────────────────────────────────────────


class TestDefaults:
    def test_app_config_defaults(self):
        c = AppConfig()
        assert c.profile == "standard"
        assert c.language == "auto"
        assert c.mode == "toggle"
        assert c.debug is False

    def test_audio_config_defaults(self):
        c = AudioConfig()
        assert c.input_device == "default"
        assert c.sample_rate == 16000
        assert c.channels == 1
        assert c.vad_enabled is True
        assert c.silence_timeout_ms == 900
        assert c.max_recording_duration_s == 120

    def test_asr_config_requires_provider(self):
        with pytest.raises((ConfigError, pydantic.ValidationError)):
            FullConfig(asr={"model": "large-v3"})

    def test_cleanup_config_defaults(self):
        c = CleanupConfig()
        assert c.provider == "rules"
        assert c.style == "standard"
        assert c.preserve_code is True

    def test_insertion_config_defaults(self):
        c = InsertionConfig()
        assert c.strategy == "keyboard"
        assert c.clipboard_fallback is True
        assert c.delay_between_chars_ms == 0

    def test_hotkeys_config_defaults(self):
        c = HotkeysConfig()
        assert c.toggle_recording == "ctrl+space"
        assert c.open_settings == "ctrl+alt+comma"
        assert c.cancel == "escape"
        assert c.insert_last_transcript is None

    def test_vocabulary_config_defaults(self):
        c = VocabularyConfig()
        assert c.path is None
        assert c.inline == []

    def test_snippets_config_defaults(self):
        c = SnippetsConfig()
        assert c.path is None


# ── Valid configs ──────────────────────────────────────────────────


class TestValidConfigs:
    def test_minimal_config(self):
        """A minimal config with only the required field should load."""
        data = _load_fixture("valid_minimal.yaml")
        config = load_config_from_dict(data)
        assert config.asr.provider == "faster_whisper"
        assert config.asr.model == "large-v3"
        # All other fields get defaults
        assert config.app.profile == "standard"
        assert config.audio.sample_rate == 16000
        assert config.cleanup.provider == "rules"
        assert config.insertion.strategy == "keyboard"

    def test_full_config(self):
        """A full config with all fields should load cleanly."""
        os.environ["OPENAI_API_KEY"] = "sk-test-placeholder"
        try:
            data = _load_fixture("valid_full.yaml")
            config = load_config_from_dict(data)
            assert config.app.profile == "technical"
            assert config.app.debug is True
            assert config.audio.sample_rate == 44100
            assert config.audio.silence_timeout_ms == 500
            assert config.asr.provider == "openai_compatible"
            assert config.asr.endpoint == "https://api.openai.com/v1"
            assert config.cleanup.style == "professional"
            assert config.insertion.delay_between_chars_ms == 5
            assert config.hotkeys.toggle_recording == "ctrl+shift+space"
            assert config.vocabulary.inline == ["PyTorch", "CUDA", "API"]
        finally:
            del os.environ["OPENAI_API_KEY"]

    def test_example_config(self):
        """config.example.yaml should load without errors."""
        config = load_config("config.example.yaml")
        assert config.asr.provider == "faster_whisper"
        assert config.cleanup.provider == "rules"

    def test_local_example_config(self):
        """examples/config.local.yaml should load without errors."""
        config = load_config("examples/config.local.yaml")
        assert config.asr.provider == "faster_whisper"
        assert config.app.profile == "technical"

    def test_openai_example_config(self):
        """examples/config.openai.yaml should load without errors."""
        os.environ["OPENAI_API_KEY"] = "sk-test-placeholder"
        try:
            config = load_config("examples/config.openai.yaml")
            assert config.asr.provider == "faster_whisper"
            assert config.cleanup.provider == "openai_compatible"
            assert config.cleanup.endpoint == "https://api.openai.com/v1"
        finally:
            del os.environ["OPENAI_API_KEY"]

    def test_ollama_example_config(self):
        """examples/config.ollama.yaml should load without errors."""
        config = load_config("examples/config.ollama.yaml")
        assert config.asr.provider == "faster_whisper"
        assert config.cleanup.endpoint == "http://localhost:11434/v1"
        # api_key_env is null (~) so no env-var check triggered
        assert config.cleanup.api_key_env is None


# ── Audio validation ───────────────────────────────────────────────


class TestAudioValidation:
    def test_sample_rate_too_high(self):
        with pytest.raises(ConfigError) as exc:
            AudioConfig(sample_rate=96000)
        assert "outside the supported range" in str(exc.value)

    def test_sample_rate_too_low(self):
        with pytest.raises(ConfigError) as exc:
            AudioConfig(sample_rate=4000)
        assert "outside the supported range" in str(exc.value)

    def test_sample_rate_valid_edge_high(self):
        c = AudioConfig(sample_rate=48000)
        assert c.sample_rate == 48000

    def test_sample_rate_valid_edge_low(self):
        c = AudioConfig(sample_rate=8000)
        assert c.sample_rate == 8000

    def test_silence_timeout_zero(self):
        with pytest.raises(ConfigError) as exc:
            AudioConfig(silence_timeout_ms=0)
        assert "must be > 0" in str(exc.value)

    def test_silence_timeout_negative(self):
        with pytest.raises(ConfigError) as exc:
            AudioConfig(silence_timeout_ms=-1)
        assert "must be > 0" in str(exc.value)

    def test_silence_timeout_valid(self):
        c = AudioConfig(silence_timeout_ms=100)
        assert c.silence_timeout_ms == 100

    def test_invalid_sample_rate_from_fixture(self):
        data = _load_fixture("invalid_sample_rate.yaml")
        with pytest.raises(ConfigError) as exc:
            load_config_from_dict(data)
        assert "outside the supported range" in str(exc.value)

    def test_invalid_silence_timeout_from_fixture(self):
        data = _load_fixture("invalid_silence_timeout.yaml")
        with pytest.raises(ConfigError) as exc:
            load_config_from_dict(data)
        assert "must be > 0" in str(exc.value)


# ── Hotkey validation ──────────────────────────────────────────────


class TestHotkeyValidation:
    def test_valid_hotkeys(self):
        HotkeysConfig(toggle_recording="ctrl+space")
        HotkeysConfig(toggle_recording="alt+shift+f1")
        HotkeysConfig(toggle_recording="cmd+ctrl+alt+shift+escape")
        HotkeysConfig(open_settings="ctrl+alt+comma")
        HotkeysConfig(cancel="escape")
        HotkeysConfig(insert_last_transcript="ctrl+shift+v")

    def test_invalid_modifier(self):
        with pytest.raises(ConfigError) as exc:
            HotkeysConfig(toggle_recording="super+x")
        assert "Invalid hotkey" in str(exc.value)

    def test_invalid_key_name(self):
        with pytest.raises(ConfigError) as exc:
            HotkeysConfig(cancel="ctrl+foobar")
        assert "Invalid hotkey" in str(exc.value)

    def test_missing_key(self):
        with pytest.raises(ConfigError) as exc:
            HotkeysConfig(open_settings="ctrl+")
        assert "Invalid hotkey" in str(exc.value)

    def test_invalid_hotkey_from_fixture(self):
        data = _load_fixture("invalid_hotkey.yaml")
        with pytest.raises(ConfigError) as exc:
            load_config_from_dict(data)
        assert "Invalid hotkey" in str(exc.value)

    def test_valid_with_number_key(self):
        c = HotkeysConfig(toggle_recording="ctrl+7")
        assert c.toggle_recording == "ctrl+7"


# ── Required field validation ──────────────────────────────────────


class TestRequiredFields:
    def test_missing_asr_provider(self):
        data = _load_fixture("missing_required.yaml")
        with pytest.raises(ConfigError) as exc:
            load_config_from_dict(data)
        # Should mention 'asr.provider' missing
        msg = str(exc.value)
        assert "Field required" in msg or "provider" in msg.lower()

    def test_empty_config(self):
        with pytest.raises(ConfigError) as exc:
            load_config_from_dict({})
        msg = str(exc.value)
        assert "Field required" in msg or "provider" in msg.lower()


# ── Environment variable expansion ─────────────────────────────────


class TestEnvVarExpansion:
    def test_env_var_replaced(self):
        os.environ["_agentvoca_TEST_KEY"] = "test_value_xyz"
        try:
            config = load_config_from_dict(
                {
                    "asr": {"provider": "faster_whisper"},
                    "cleanup": {
                        "provider": "openai_compatible",
                        "endpoint": "https://example.com/v1",
                        "api_key_env": "_agentvoca_TEST_KEY",
                    },
                }
            )
            assert config.cleanup.api_key_env == "_agentvoca_TEST_KEY"
        finally:
            del os.environ["_agentvoca_TEST_KEY"]

    def test_env_var_missing_replaced_with_empty(self):
        """A missing env var should be replaced with empty string."""
        data = {
            "asr": {
                "provider": "faster_whisper",
                "endpoint": "https://${NONEXISTENT_VAR_12345}.com",
            }
        }
        config = load_config_from_dict(data)
        assert config.asr.endpoint == "https://.com"

    def test_config_file_with_env_var(self, tmp_path):
        """Test that load_config expands env vars in a real YAML file."""
        os.environ["_agentvoca_TEST_MODEL"] = "tiny.en"
        config_yaml = """
asr:
  provider: faster_whisper
  model: ${_agentvoca_TEST_MODEL}
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)
        try:
            config = load_config(str(config_file))
            assert config.asr.model == "tiny.en"
        finally:
            del os.environ["_agentvoca_TEST_MODEL"]


# ── API key environment variable validation ────────────────────────


class TestApiKeyValidation:
    def test_remote_asr_no_api_key_ok(self):
        """A remote provider with api_key_env=null should not require the env var."""
        config = load_config_from_dict(
            {
                "asr": {
                    "provider": "openai_compatible",
                    "endpoint": "https://api.openai.com/v1",
                    "api_key_env": None,
                }
            }
        )
        assert config.asr.api_key_env is None

    def test_remote_asr_with_api_key_set(self):
        """A remote provider with a set api_key_env should pass."""
        os.environ["_agentvoca_TEST_ASR_KEY"] = "sk-test123"
        try:
            config = load_config_from_dict(
                {
                    "asr": {
                        "provider": "openai_compatible",
                        "endpoint": "https://api.openai.com/v1",
                        "api_key_env": "_agentvoca_TEST_ASR_KEY",
                    }
                }
            )
            assert config.asr.api_key_env == "_agentvoca_TEST_ASR_KEY"
        finally:
            del os.environ["_agentvoca_TEST_ASR_KEY"]

    def test_remote_asr_with_api_key_missing(self):
        """A remote provider with a missing api_key_env should fail."""
        with pytest.raises(ConfigError) as exc:
            load_config_from_dict(
                {
                    "asr": {
                        "provider": "openai_compatible",
                        "endpoint": "https://api.openai.com/v1",
                        "api_key_env": "_agentvoca_MISSING_KEY_12345",
                    }
                }
            )
        assert "requires an API key" in str(exc.value)
        assert "Set env var" in str(exc.value)

    def test_remote_cleanup_with_api_key_missing(self):
        """A remote cleanup provider with a missing api_key_env should fail."""
        with pytest.raises(ConfigError) as exc:
            load_config_from_dict(
                {
                    "asr": {"provider": "faster_whisper"},
                    "cleanup": {
                        "provider": "openai_compatible",
                        "endpoint": "https://api.openai.com/v1",
                        "api_key_env": "_agentvoca_MISSING_CLEANUP_KEY",
                    },
                }
            )
        assert "requires an API key" in str(exc.value)

    def test_local_asr_no_endpoint_no_key(self):
        """A local ASR provider (no endpoint) should not require an API key."""
        config = load_config_from_dict(
            {
                "asr": {
                    "provider": "faster_whisper",
                }
            }
        )
        assert config.asr.provider == "faster_whisper"

    def test_local_cleanup_missing_key_not_checked(self):
        """A local cleanup provider (no endpoint) should not check api_key_env."""
        config = load_config_from_dict(
            {
                "asr": {"provider": "faster_whisper"},
                "cleanup": {
                    "provider": "rules",
                    "api_key_env": "SOME_MISSING_VAR",
                },
            }
        )
        assert config.cleanup.provider == "rules"


# ── File-based loading ─────────────────────────────────────────────


class TestFileLoading:
    def test_load_nonexistent_file(self):
        with pytest.raises(ConfigError) as exc:
            load_config("/nonexistent/path/config.yaml")
        assert "Config file not found" in str(exc.value)

    def test_load_invalid_yaml(self, tmp_path):
        config_file = tmp_path / "bad.yaml"
        config_file.write_text("{{ invalid yaml")
        with pytest.raises(ConfigError) as exc:
            load_config(str(config_file))
        assert "Invalid YAML" in str(exc.value)

    def test_load_empty_yaml(self, tmp_path):
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")
        with pytest.raises(ConfigError) as exc:
            load_config(str(config_file))
        assert "must contain a top-level mapping" in str(exc.value)

    def test_load_scalar_yaml(self, tmp_path):
        """A YAML file that parses to a string instead of a dict."""
        config_file = tmp_path / "scalar.yaml"
        config_file.write_text("just a string")
        with pytest.raises(ConfigError) as exc:
            load_config(str(config_file))
        assert "must contain a top-level mapping" in str(exc.value)

    def test_load_minimal_file(self):
        """Load the valid_minimal fixture from file."""
        fixture_path = FIXTURES_DIR / "valid_minimal.yaml"
        config = load_config(str(fixture_path))
        assert config.asr.provider == "faster_whisper"
        assert config.asr.model == "large-v3"


# ── Custom prompt path validation ─────────────────────────────────


class TestCustomPromptPath:
    def test_custom_prompt_path_missing(self, tmp_path):
        missing = tmp_path / "missing_prompt.txt"
        with pytest.raises(ConfigError) as exc:
            CleanupConfig(custom_prompt_path=str(missing))
        assert "Cleanup prompt file not found" in str(exc.value)

    def test_custom_prompt_path_exists(self, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("custom prompt")
        config = CleanupConfig(custom_prompt_path=str(prompt_file))
        assert config.custom_prompt_path == str(prompt_file)


# ── Strict vs lenient parsing ──────────────────────────────────────


class TestParsingStrictness:
    def test_extra_fields_ignored(self):
        """Extra fields in YAML should be ignored (strict=False)."""
        config = load_config_from_dict(
            {
                "asr": {"provider": "faster_whisper"},
                "unknown_section": {"foo": "bar"},
            }
        )
        assert config.asr.provider == "faster_whisper"
        # No error raised for unknown section

    def test_wrong_type_coerced_if_possible(self):
        """Numeric values in place of strings should be coerced."""
        config = load_config_from_dict(
            {
                "asr": {"provider": "faster_whisper"},
            }
        )
        assert config.asr.provider == "faster_whisper"


# ── Inline profile validation ──────────────────────────────────────


class TestProfileValidation:
    def test_valid_profiles(self):
        for profile in ("raw", "light", "standard", "technical", "professional", "custom"):
            c = AppConfig(profile=profile)
            assert c.profile == profile

    def test_invalid_profile(self):
        with pytest.raises((ConfigError, pydantic.ValidationError)):
            AppConfig(profile="invalid")


# ── Mode validation ────────────────────────────────────────────────


class TestModeValidation:
    def test_valid_modes(self):
        for mode in ("push_to_talk", "toggle", "auto_stop"):
            c = AppConfig(mode=mode)
            assert c.mode == mode

    def test_invalid_mode(self):
        with pytest.raises((ConfigError, pydantic.ValidationError)):
            AppConfig(mode="continuous")


# ── Insertion strategy validation ──────────────────────────────────


class TestInsertionStrategyValidation:
    def test_valid_strategies(self):
        for strategy in ("keyboard", "clipboard"):
            c = InsertionConfig(strategy=strategy)
            assert c.strategy == strategy

    def test_invalid_strategy(self):
        with pytest.raises((ConfigError, pydantic.ValidationError)):
            InsertionConfig(strategy="mouse")
