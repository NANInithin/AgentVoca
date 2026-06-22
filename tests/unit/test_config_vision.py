"""Unit tests for v3 vision configuration."""

import os

import pytest

from agentvoca.config.loader import load_config_from_dict
from agentvoca.config.schema import ASRConfig, FullConfig, VisionConfig
from agentvoca.utils.errors import ConfigError


def test_vision_defaults_off() -> None:
    cfg = FullConfig(asr=ASRConfig(provider="faster_whisper", model="base"))
    assert cfg.vision.enabled is False
    assert cfg.vision.provider == "openai_compatible"
    assert cfg.vision.output_format == "auto"
    assert cfg.vision.capture_timeout_s == 30


def test_capture_timeout_bounds() -> None:
    with pytest.raises(ConfigError):
        VisionConfig(capture_timeout_s=0)
    with pytest.raises(ConfigError):
        VisionConfig(capture_timeout_s=999)


def test_capture_screenshot_hotkey_validated() -> None:
    cfg = load_config_from_dict(
        {
            "asr": {"provider": "faster_whisper", "model": "base"},
            "hotkeys": {"capture_screenshot": "ctrl+shift+s"},
        }
    )
    assert cfg.hotkeys.capture_screenshot == "ctrl+shift+s"


def test_invalid_capture_hotkey_rejected() -> None:
    with pytest.raises(ConfigError):
        load_config_from_dict(
            {
                "asr": {"provider": "faster_whisper", "model": "base"},
                "hotkeys": {"capture_screenshot": "ctrl+notakey"},
            }
        )


def test_enabled_vision_requires_api_key_when_endpoint_set() -> None:
    # enabled + remote endpoint + api_key_env pointing at an unset var → error.
    with pytest.raises(ConfigError):
        load_config_from_dict(
            {
                "asr": {"provider": "faster_whisper", "model": "base"},
                "vision": {
                    "enabled": True,
                    "endpoint": "https://api.example.com/v1",
                    "api_key_env": "_DEFINITELY_UNSET_VISION_KEY",
                },
            }
        )


def test_disabled_vision_skips_api_key_check() -> None:
    # Disabled vision must not enforce the key even if api_key_env is unset.
    cfg = load_config_from_dict(
        {
            "asr": {"provider": "faster_whisper", "model": "base"},
            "vision": {
                "enabled": False,
                "endpoint": "https://api.example.com/v1",
                "api_key_env": "_DEFINITELY_UNSET_VISION_KEY",
            },
        }
    )
    assert cfg.vision.enabled is False


def test_enabled_vision_with_key_present_ok() -> None:
    os.environ["_agentvoca_VISION_CFG_KEY"] = "sk-test"
    try:
        cfg = load_config_from_dict(
            {
                "asr": {"provider": "faster_whisper", "model": "base"},
                "vision": {
                    "enabled": True,
                    "endpoint": "https://api.example.com/v1",
                    "api_key_env": "_agentvoca_VISION_CFG_KEY",
                },
            }
        )
        assert cfg.vision.enabled is True
    finally:
        del os.environ["_agentvoca_VISION_CFG_KEY"]
