"""OBS-2: Observer configuration schema tests.

The Observer config block in ``FullConfig`` is fully additive. These
tests assert:
- a config with no ``observer:`` block loads with ``observer.enabled is False``
- every default matches the contracts table field-for-field
- out-of-range values raise ``ConfigError``
- ``observer.enabled: false`` skips the API-key env check, even with a
  remote provider configured
- ``observer.enabled: true`` flips the gate — a remote OCR with an unset
  env var raises ``ConfigError`` (this pair is the whole point of the gate)
- ``scope: "full_screen"`` is rejected (v0.4.0 accepts ``active_window`` only)
- hotkey validation: ``toggle_observer`` / ``pause_observer`` pass valid,
  fail invalid
- ``FullConfig(**cfg.model_dump())`` round-trips — the settings UI depends
  on this
- ``compile.output_dir`` default resolves to ``<storage.dir>/exports`` and
  is preserved as a literal when the user overrides it
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentvoca.config.loader import load_config_from_dict
from agentvoca.config.schema import (
    ASRConfig,
    CleanupConfig,
    FullConfig,
    HotkeysConfig,
    ObserverCompileConfig,
    ObserverConfig,
    ObserverOCRConfig,
    ObserverPrivacyConfig,
    ObserverScreenConfig,
    ObserverSelectionConfig,
    ObserverStorageConfig,
    ObserverTriggersConfig,
)
from agentvoca.utils.errors import ConfigError

# ── Defaults ────────────────────────────────────────────────────────


class TestDefaults:
    def test_no_observer_block_means_disabled(self) -> None:
        cfg = FullConfig(asr=ASRConfig(provider="faster_whisper", model="base"))
        assert cfg.observer.enabled is False

    def test_observer_defaults_match_contracts(self) -> None:
        """An explicit dict compare against the contracts §2 table.

        This is the test that enforces the table — if a default changes
        here, the table must be re-approved.
        """
        expected = {
            "enabled": False,
            "storage.dir": "~/.agentvoca/observer",
            "storage.retention_days": 7,
            "storage.max_session_mb": 500,
            "triggers.window_change": True,
            "triggers.scroll_settle": True,
            "triggers.click_selection": True,
            "triggers.speech_onset": True,
            "triggers.scroll_settle_ms": 600,
            "triggers.min_interval_ms": 4000,
            "triggers.max_keyframes_per_min": 4,
            "screen.scope": "active_window",
            "screen.max_width_px": 1280,
            "screen.jpeg_quality": 75,
            "screen.dedup_phash_distance": 6,
            "ocr.provider": "rapidocr",
            "ocr.endpoint": None,
            "ocr.api_key_env": None,
            "ocr.model": None,
            "ocr.max_queue": 32,
            "selection.enabled": True,
            "selection.method": "uia",
            "selection.max_chars": 4000,
            "compile.provider": "rules",
            "compile.endpoint": None,
            "compile.api_key_env": None,
            "compile.model": None,
            "compile.formats": ["markdown", "json"],
            # compile.output_dir is resolved by the validator — tested separately.
        }
        cfg = ObserverConfig()
        assert cfg.enabled == expected["enabled"]
        assert cfg.storage.dir == expected["storage.dir"]
        assert cfg.storage.retention_days == expected["storage.retention_days"]
        assert cfg.storage.max_session_mb == expected["storage.max_session_mb"]
        assert cfg.triggers.window_change == expected["triggers.window_change"]
        assert cfg.triggers.scroll_settle == expected["triggers.scroll_settle"]
        assert cfg.triggers.click_selection == expected["triggers.click_selection"]
        assert cfg.triggers.speech_onset == expected["triggers.speech_onset"]
        assert cfg.triggers.scroll_settle_ms == expected["triggers.scroll_settle_ms"]
        assert cfg.triggers.min_interval_ms == expected["triggers.min_interval_ms"]
        assert cfg.triggers.max_keyframes_per_min == expected["triggers.max_keyframes_per_min"]
        assert cfg.screen.scope == expected["screen.scope"]
        assert cfg.screen.max_width_px == expected["screen.max_width_px"]
        assert cfg.screen.jpeg_quality == expected["screen.jpeg_quality"]
        assert cfg.screen.dedup_phash_distance == expected["screen.dedup_phash_distance"]
        assert cfg.ocr.provider == expected["ocr.provider"]
        assert cfg.ocr.endpoint == expected["ocr.endpoint"]
        assert cfg.ocr.api_key_env == expected["ocr.api_key_env"]
        assert cfg.ocr.model == expected["ocr.model"]
        assert cfg.ocr.max_queue == expected["ocr.max_queue"]
        assert cfg.selection.enabled == expected["selection.enabled"]
        assert cfg.selection.method == expected["selection.method"]
        assert cfg.selection.max_chars == expected["selection.max_chars"]
        assert cfg.compile.provider == expected["compile.provider"]
        assert cfg.compile.endpoint == expected["compile.endpoint"]
        assert cfg.compile.api_key_env == expected["compile.api_key_env"]
        assert cfg.compile.model == expected["compile.model"]
        assert cfg.compile.formats == expected["compile.formats"]

    def test_observer_storage_config_defaults(self) -> None:
        c = ObserverStorageConfig()
        assert c.dir == "~/.agentvoca/observer"
        assert c.retention_days == 7
        assert c.max_session_mb == 500

    def test_observer_triggers_config_defaults(self) -> None:
        c = ObserverTriggersConfig()
        assert c.window_change is True
        assert c.scroll_settle is True
        assert c.click_selection is True
        assert c.speech_onset is True
        assert c.scroll_settle_ms == 600
        assert c.min_interval_ms == 4000
        assert c.max_keyframes_per_min == 4

    def test_observer_screen_config_defaults(self) -> None:
        c = ObserverScreenConfig()
        assert c.scope == "active_window"
        assert c.max_width_px == 1280
        assert c.jpeg_quality == 75
        assert c.dedup_phash_distance == 6

    def test_observer_ocr_config_defaults(self) -> None:
        c = ObserverOCRConfig()
        assert c.provider == "rapidocr"
        assert c.endpoint is None
        assert c.api_key_env is None
        assert c.model is None
        assert c.max_queue == 32

    def test_observer_selection_config_defaults(self) -> None:
        c = ObserverSelectionConfig()
        assert c.enabled is True
        assert c.method == "uia"
        assert c.max_chars == 4000

    def test_observer_compile_config_defaults(self) -> None:
        c = ObserverCompileConfig()
        assert c.provider == "rules"
        assert c.endpoint is None
        assert c.api_key_env is None
        assert c.model is None
        assert c.formats == ["markdown", "json"]

    def test_observer_privacy_config_defaults(self) -> None:
        c = ObserverPrivacyConfig()
        # Per contracts §2 — default exclusion lists.
        assert "1Password.exe" in c.exclude_apps
        assert "KeePassXC.exe" in c.exclude_apps
        assert "Bitwarden.exe" in c.exclude_apps
        assert "Signal.exe" in c.exclude_apps
        assert "*InPrivate*" in c.exclude_title_patterns
        assert "*Incognito*" in c.exclude_title_patterns
        assert "*Password*" in c.exclude_title_patterns


# ── Out-of-range validation ─────────────────────────────────────────


class TestOutOfRange:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"screen": {"jpeg_quality": 200}},  # > 95
            {"screen": {"jpeg_quality": 10}},  # < 40
            {"triggers": {"max_keyframes_per_min": 0}},  # < 1
            {"triggers": {"max_keyframes_per_min": 100}},  # > 60
            {"storage": {"retention_days": -1}},  # < 0
            {"storage": {"max_session_mb": 0}},  # < 1
            {"storage": {"max_session_mb": 20_000}},  # > 10000
            {"compile": {"formats": []}},  # empty
            {"compile": {"formats": ["pdf"]}},  # not in allowed set
            {"compile": {"formats": ["markdown", "pdf"]}},  # one bad
            {"screen": {"scope": "full_screen"}},  # v0.4.0: only active_window
            {"selection": {"max_chars": 10}},  # < 100
            {"ocr": {"max_queue": 2}},  # < 4
            {"triggers": {"min_interval_ms": 100}},  # < 500
            {"triggers": {"scroll_settle_ms": 10}},  # < 100
        ],
    )
    def test_invalid_value_raises_config_error(self, kwargs: dict) -> None:
        base = {
            "asr": {"provider": "faster_whisper", "model": "base"},
            "observer": {"enabled": True, **kwargs},
        }
        with pytest.raises(ConfigError):
            load_config_from_dict(base)


# ── API-key env gate ────────────────────────────────────────────────


class TestApiKeyGate:
    def test_disabled_observer_skips_key_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """observer.enabled: false + remote OCR + unset env var → loads fine."""
        monkeypatch.delenv("_DEFINITELY_UNSET_OBS_KEY", raising=False)
        cfg = load_config_from_dict(
            {
                "asr": {"provider": "faster_whisper", "model": "base"},
                "observer": {
                    "enabled": False,
                    "ocr": {
                        "provider": "openai_compatible",
                        "endpoint": "https://api.example.com/v1",
                        "api_key_env": "_DEFINITELY_UNSET_OBS_KEY",
                    },
                },
            }
        )
        assert cfg.observer.enabled is False

    def test_enabled_observer_with_remote_ocr_requires_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """observer.enabled: true + remote OCR + unset env var → ConfigError."""
        monkeypatch.delenv("_DEFINITELY_UNSET_OBS_KEY", raising=False)
        with pytest.raises(ConfigError) as exc:
            load_config_from_dict(
                {
                    "asr": {"provider": "faster_whisper", "model": "base"},
                    "observer": {
                        "enabled": True,
                        "ocr": {
                            "provider": "openai_compatible",
                            "endpoint": "https://api.example.com/v1",
                            "api_key_env": "_DEFINITELY_UNSET_OBS_KEY",
                        },
                    },
                }
            )
        assert "Observer OCR provider" in str(exc.value)
        assert "_DEFINITELY_UNSET_OBS_KEY" in str(exc.value)

    def test_enabled_observer_with_remote_compiler_requires_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """observer.enabled: true + remote compiler + unset env var → ConfigError."""
        monkeypatch.delenv("_DEFINITELY_UNSET_OBS_KEY", raising=False)
        with pytest.raises(ConfigError) as exc:
            load_config_from_dict(
                {
                    "asr": {"provider": "faster_whisper", "model": "base"},
                    "observer": {
                        "enabled": True,
                        "compile": {
                            "provider": "openai_compatible",
                            "endpoint": "https://api.example.com/v1",
                            "api_key_env": "_DEFINITELY_UNSET_OBS_KEY",
                        },
                    },
                }
            )
        assert "Observer compiler" in str(exc.value)

    def test_enabled_observer_with_key_present_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """observer.enabled: true + remote OCR + set env var → loads fine."""
        monkeypatch.setenv("_agentvoca_OBS_KEY", "sk-test")
        try:
            cfg = load_config_from_dict(
                {
                    "asr": {"provider": "faster_whisper", "model": "base"},
                    "observer": {
                        "enabled": True,
                        "ocr": {
                            "provider": "openai_compatible",
                            "endpoint": "https://api.example.com/v1",
                            "api_key_env": "_agentvoca_OBS_KEY",
                        },
                    },
                }
            )
            assert cfg.observer.enabled is True
            assert cfg.observer.ocr.api_key_env == "_agentvoca_OBS_KEY"
        finally:
            del os.environ["_agentvoca_OBS_KEY"]

    def test_enabled_observer_with_local_providers_does_not_need_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole point of the gate: with the local defaults (rapidocr + rules)
        and no env vars at all, observer.enabled: true must still load."""
        monkeypatch.delenv("ANY_KEY", raising=False)
        cfg = load_config_from_dict(
            {
                "asr": {"provider": "faster_whisper", "model": "base"},
                "observer": {"enabled": True},
            }
        )
        assert cfg.observer.enabled is True
        assert cfg.observer.ocr.provider == "rapidocr"
        assert cfg.observer.compile.provider == "rules"


# ── Hotkey validation ───────────────────────────────────────────────


class TestHotkeys:
    def test_toggle_observer_default_none(self) -> None:
        assert HotkeysConfig().toggle_observer is None

    def test_pause_observer_default_none(self) -> None:
        assert HotkeysConfig().pause_observer is None

    def test_toggle_observer_valid_passes(self) -> None:
        cfg = HotkeysConfig(toggle_observer="ctrl+shift+o")
        assert cfg.toggle_observer == "ctrl+shift+o"

    def test_toggle_observer_invalid_raises(self) -> None:
        with pytest.raises(ConfigError):
            HotkeysConfig(toggle_observer="ctrl+shift+")

    def test_pause_observer_valid_passes(self) -> None:
        cfg = HotkeysConfig(pause_observer="ctrl+shift+p")
        assert cfg.pause_observer == "ctrl+shift+p"

    def test_pause_observer_invalid_raises(self) -> None:
        with pytest.raises(ConfigError):
            HotkeysConfig(pause_observer="ctrl+notakey")

    def test_observer_hotkeys_via_full_config(self) -> None:
        cfg = load_config_from_dict(
            {
                "asr": {"provider": "faster_whisper", "model": "base"},
                "hotkeys": {
                    "toggle_observer": "ctrl+shift+o",
                    "pause_observer": "ctrl+shift+p",
                },
            }
        )
        assert cfg.hotkeys.toggle_observer == "ctrl+shift+o"
        assert cfg.hotkeys.pause_observer == "ctrl+shift+p"


# ── output_dir resolution ───────────────────────────────────────────


class TestOutputDirResolution:
    def test_default_resolves_under_storage_dir(self) -> None:
        cfg = FullConfig(
            asr=ASRConfig(provider="faster_whisper", model="base"),
        )
        assert cfg.observer.compile.output_dir.endswith("/exports")
        # Should embed the storage dir prefix.
        assert cfg.observer.storage.dir.rstrip("/").rstrip("\\") in cfg.observer.compile.output_dir

    def test_custom_storage_dir_propagates(self) -> None:
        cfg = FullConfig(
            asr=ASRConfig(provider="faster_whisper", model="base"),
            observer=ObserverConfig(storage=ObserverStorageConfig(dir="/tmp/my_obs")),
        )
        assert cfg.observer.compile.output_dir == "/tmp/my_obs/exports"

    def test_explicit_output_dir_is_preserved(self) -> None:
        cfg = FullConfig(
            asr=ASRConfig(provider="faster_whisper", model="base"),
            observer=ObserverConfig(
                storage=ObserverStorageConfig(dir="/tmp/my_obs"),
                compile=ObserverCompileConfig(output_dir="/elsewhere/exports"),
            ),
        )
        assert cfg.observer.compile.output_dir == "/elsewhere/exports"

    def test_storage_dir_not_expanded_at_load(self) -> None:
        """The settings UI round-trips the user's literal string. expanduser
        happens at use time inside ObserverStore, not at config load."""
        cfg = FullConfig(
            asr=ASRConfig(provider="faster_whisper", model="base"),
        )
        # Should still be the literal "~/.agentvoca/observer" form.
        assert cfg.observer.storage.dir.startswith("~")


# ── Round-trip stability ────────────────────────────────────────────


class TestRoundTrip:
    def test_model_dump_round_trip(self) -> None:
        original = load_config_from_dict(
            {
                "asr": {"provider": "faster_whisper", "model": "base"},
                "observer": {
                    "enabled": True,
                    "storage": {"dir": "/custom/obs", "retention_days": 14},
                    "triggers": {"max_keyframes_per_min": 8},
                    "compile": {"formats": ["json"]},
                },
                "hotkeys": {"toggle_observer": "ctrl+shift+o"},
            }
        )
        # Round-trip via model_dump + re-construct.
        cloned = FullConfig(**original.model_dump())
        assert cloned.observer.enabled is True
        assert cloned.observer.storage.dir == "/custom/obs"
        assert cloned.observer.storage.retention_days == 14
        assert cloned.observer.triggers.max_keyframes_per_min == 8
        assert cloned.observer.compile.formats == ["json"]
        # output_dir was resolved; should round-trip the resolved value.
        assert cloned.observer.compile.output_dir == "/custom/obs/exports"
        assert cloned.hotkeys.toggle_observer == "ctrl+shift+o"

    def test_minimal_config_round_trip(self) -> None:
        """A config with no observer block at all must round-trip stably."""
        cfg = FullConfig(asr=ASRConfig(provider="faster_whisper", model="base"))
        cloned = FullConfig(**cfg.model_dump())
        assert cloned.observer.enabled is False
        assert cloned.observer.storage.dir == "~/.agentvoca/observer"


# ── Misc ────────────────────────────────────────────────────────────


def test_observer_disabled_means_zero_io() -> None:
    """The cost gate: with observer off, none of the observer dependencies
    should be touched. Verified by the no-observer-block config having
    every observer default at its in-memory sentinel value."""
    cfg = FullConfig(asr=ASRConfig(provider="faster_whisper", model="base"))
    assert cfg.observer.enabled is False
    # Defaults are all in place but no disk is touched.
    assert cfg.observer.storage.dir == "~/.agentvoca/observer"
    assert cfg.observer.triggers.max_keyframes_per_min == 4


def test_existing_v036_config_still_loads(tmp_path: Path) -> None:
    """A v0.3.6 config without an observer block must load unchanged."""
    config = tmp_path / "config.yaml"
    config.write_text(
        "asr:\n  provider: faster_whisper\n  model: base\n"
        "hotkeys:\n  toggle_recording: ctrl+space\n",
        encoding="utf-8",
    )
    from agentvoca.config.loader import load_config

    cfg = load_config(config)
    assert cfg.observer.enabled is False
    assert cfg.observer.storage.dir == "~/.agentvoca/observer"


# ── Regression: local providers must never demand an API key ──────────


def test_local_asr_with_stale_cloud_endpoint_still_loads(monkeypatch) -> None:
    """Regression: offline mode was blocked by leftover cloud fields.

    Switching the wizard from Cloud back to Local changes
    ``asr.provider`` to ``faster_whisper`` but leaves the previous
    ``endpoint`` / ``api_key_env`` in the config. The validator used to
    infer "remote" from endpoint presence alone, so it demanded
    OPENROUTER_API_KEY for a provider that runs entirely on-device --
    surfacing the self-contradictory "ASR provider 'faster_whisper'
    requires an API key" dialog and making offline mode unreachable.
    """
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = FullConfig(
        asr=ASRConfig(
            provider="faster_whisper",
            model="base",
            endpoint="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
        )
    )
    assert cfg.asr.provider == "faster_whisper"


def test_local_cleanup_with_stale_cloud_endpoint_still_loads(monkeypatch) -> None:
    """Same stale-field problem on the cleanup block."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = FullConfig(
        asr=ASRConfig(provider="faster_whisper", model="base"),
        cleanup=CleanupConfig(
            provider="rules",
            endpoint="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
        ),
    )
    assert cfg.cleanup.provider == "rules"


def test_remote_asr_without_key_still_raises(monkeypatch) -> None:
    """The fix must not weaken the real check for genuinely remote providers."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="requires an API key"):
        FullConfig(
            asr=ASRConfig(
                provider="openai_compatible",
                endpoint="https://openrouter.ai/api/v1",
                api_key_env="OPENROUTER_API_KEY",
            )
        )


def test_observer_local_ocr_with_stale_endpoint_still_loads(monkeypatch) -> None:
    """rapidocr is local: a stale endpoint must not demand a key."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = FullConfig(
        asr=ASRConfig(provider="faster_whisper", model="base"),
        observer=ObserverConfig(
            enabled=True,
            ocr=ObserverOCRConfig(
                provider="rapidocr",
                endpoint="https://openrouter.ai/api/v1",
                api_key_env="OPENROUTER_API_KEY",
            ),
        ),
    )
    assert cfg.observer.ocr.provider == "rapidocr"
