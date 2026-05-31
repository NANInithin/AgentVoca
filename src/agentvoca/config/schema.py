"""Pydantic models for agentvoca configuration.

All config sections are validated at load time. See Section 5 of
the architecture spec for details.
"""

import os
import re
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from agentvoca.utils.errors import ConfigError

# ── Hotkey validation ──────────────────────────────────────────────
_VALID_MODIFIERS = {"ctrl", "alt", "shift", "cmd", "win"}
_HOTKEY_RE = re.compile(
    r"^((?:ctrl|alt|shift|cmd|win)\+)*(?:[a-zA-Z0-9]|escape|space|comma|period|slash|backslash|"
    r"tab|enter|backspace|delete|home|end|page_up|page_down|left|right|up|down|"
    r"f[1-9]|f1[0-9]|f2[0-4])$",
    re.IGNORECASE,
)


def _validate_hotkey(value: str, field_name: str) -> str:
    """Validate a hotkey string and raise ConfigError if invalid."""
    if not _HOTKEY_RE.match(value):
        raise ConfigError(f"Invalid hotkey '{value}' in hotkeys.{field_name}.")
    parts = value.lower().split("+")
    for part in parts[:-1]:
        if part not in _VALID_MODIFIERS:
            raise ConfigError(f"Invalid hotkey '{value}' in hotkeys.{field_name}.")
    return value


# ── Config Models ──────────────────────────────────────────────────


class AppConfig(BaseModel):
    """Application-level settings."""

    profile: Literal["raw", "light", "standard", "technical", "professional", "custom"] = "standard"
    language: str = "auto"
    mode: Literal["push_to_talk", "toggle", "auto_stop"] = "toggle"
    debug: bool = False


class AudioConfig(BaseModel):
    """Audio capture settings."""

    input_device: str = "default"
    sample_rate: int = 16000
    channels: int = 1
    vad_enabled: bool = True
    silence_timeout_ms: int = 900
    max_recording_duration_s: int = 120

    @field_validator("sample_rate")
    @classmethod
    def _validate_sample_rate(cls, value: int) -> int:
        if value < 8000 or value > 48000:
            raise ConfigError(f"Sample rate {value} is outside the supported range [8000, 48000].")
        return value

    @field_validator("silence_timeout_ms")
    @classmethod
    def _validate_silence_timeout(cls, value: int) -> int:
        if value <= 0:
            raise ConfigError("audio.silence_timeout_ms must be > 0.")
        return value


class ASRConfig(BaseModel):
    """ASR provider configuration."""

    provider: str  # required; must match a registered name (validated in loader)
    model: Optional[str] = None
    endpoint: Optional[str] = None
    api_key_env: Optional[str] = None  # name of env var, not the key itself
    language_hint: Optional[str] = None
    extra: dict = Field(default_factory=dict)


class CleanupConfig(BaseModel):
    """Cleanup provider configuration."""

    provider: str = "rules"  # "none" | "rules" | registered name
    model: Optional[str] = None
    endpoint: Optional[str] = None
    api_key_env: Optional[str] = None
    style: str = "standard"
    preserve_code: bool = True
    custom_prompt_path: Optional[str] = None
    extra: dict = Field(default_factory=dict)

    @field_validator("custom_prompt_path")
    @classmethod
    def _validate_custom_prompt_path(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not Path(value).is_file():
            raise ConfigError(f"Cleanup prompt file not found: {value}")
        return value


class InsertionConfig(BaseModel):
    """Text insertion configuration."""

    strategy: Literal["keyboard", "clipboard"] = "keyboard"
    clipboard_fallback: bool = True
    delay_between_chars_ms: int = 0


class HotkeysConfig(BaseModel):
    """Hotkey binding configuration."""

    toggle_recording: str = "ctrl+space"
    open_settings: str = "ctrl+alt+comma"
    insert_last_transcript: Optional[str] = None
    undo: Optional[str] = None  # e.g. "ctrl+alt+z" — reverts last insertion
    cancel: str = "escape"

    @field_validator("toggle_recording", "open_settings", "cancel")
    @classmethod
    def _validate_hotkey(cls, value: str) -> str:
        return _validate_hotkey(value, cls.__name__)

    @field_validator("insert_last_transcript", "undo")
    @classmethod
    def _validate_optional_hotkey(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            _validate_hotkey(value, "insert_last_transcript")
        return value


class VocabularyConfig(BaseModel):
    """Vocabulary/substitution settings."""

    path: Optional[str] = None  # path to vocab.txt, one term per line
    inline: list[str] = Field(default_factory=list)


class SnippetsConfig(BaseModel):
    """Snippet expansion settings."""

    path: Optional[str] = None  # path to snippets.yaml


class FullConfig(BaseModel):
    """Top-level configuration model combining all sections."""

    app: AppConfig = Field(default_factory=AppConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    asr: ASRConfig
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)
    insertion: InsertionConfig = Field(default_factory=InsertionConfig)
    hotkeys: HotkeysConfig = Field(default_factory=HotkeysConfig)
    vocabulary: VocabularyConfig = Field(default_factory=VocabularyConfig)
    snippets: SnippetsConfig = Field(default_factory=SnippetsConfig)

    @model_validator(mode="after")
    def _validate_api_key_env(self) -> "FullConfig":
        """Check that api_key_env vars are set when a provider is remote.

        A provider is considered 'remote' when ``endpoint`` is set.
        """
        # ASR
        if self.asr.endpoint is not None and self.asr.api_key_env is not None:
            if self.asr.api_key_env not in os.environ:
                raise ConfigError(
                    f"ASR provider '{self.asr.provider}' requires an API key. "
                    f"Set env var '{self.asr.api_key_env}'."
                )

        # Cleanup
        if self.cleanup.endpoint is not None and self.cleanup.api_key_env is not None:
            if self.cleanup.api_key_env not in os.environ:
                raise ConfigError(
                    f"Cleanup provider '{self.cleanup.provider}' requires an API key. "
                    f"Set env var '{self.cleanup.api_key_env}'."
                )

        return self
