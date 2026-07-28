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

    # -- v2: streaming and warm-up (all optional, default to v1 behavior) --
    streaming: bool = False
    streaming_model: Optional[str] = None
    streaming_chunk_ms: int = 500
    streaming_window_s: int = 8
    warm_up: bool = True

    @field_validator("streaming_chunk_ms")
    @classmethod
    def _validate_streaming_chunk_ms(cls, value: int) -> int:
        if value < 100 or value > 2000:
            raise ConfigError(f"streaming_chunk_ms {value} outside [100, 2000].")
        return value

    @field_validator("streaming_model")
    @classmethod
    def _validate_streaming_model(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            valid_sizes = {"tiny", "base", "small", "medium", "large-v3"}
            if value not in valid_sizes:
                raise ConfigError(
                    f"Unknown streaming_model '{value}'. Valid: {', '.join(sorted(valid_sizes))}."
                )
        return value


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

    # -- v2: streaming cleanup and warm-up (optional, default to v1 behavior) --
    streaming: bool = False
    warm_up: bool = True

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
    capture_screenshot: Optional[str] = None  # v3: snip a screenshot during dictation
    toggle_observer: Optional[str] = None  # v0.4.0: Observer start/stop
    pause_observer: Optional[str] = None  # v0.4.0: Observer pause/resume

    @field_validator("toggle_recording", "open_settings", "cancel")
    @classmethod
    def _validate_hotkey(cls, value: str) -> str:
        return _validate_hotkey(value, cls.__name__)

    @field_validator(
        "insert_last_transcript",
        "undo",
        "capture_screenshot",
        "toggle_observer",
        "pause_observer",
    )
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


class ContextConfig(BaseModel):
    """Context engine configuration (v2)."""

    enabled: bool = False
    read_screen: bool = False
    read_clipboard: bool = False
    profiles: dict[str, str] = Field(default_factory=dict)


class CommandsConfig(BaseModel):
    """Voice commands configuration (v2)."""

    enabled: bool = False
    phrases: dict[str, str] = Field(default_factory=dict)


class AdaptiveConfig(BaseModel):
    """Adaptive vocabulary configuration (v2)."""

    enabled: bool = False
    promote_threshold: int = 3
    learned_vocab_path: Optional[str] = None

    @field_validator("promote_threshold")
    @classmethod
    def _validate_promote_threshold(cls, value: int) -> int:
        if value < 2:
            raise ConfigError("adaptive.promote_threshold must be >= 2.")
        return value


class VisionConfig(BaseModel):
    """Vision / screenshot-to-text configuration (v3).

    When enabled, a dedicated hotkey snips a screenshot mid-dictation; a
    vision-language model extracts its content (tables, descriptions, values)
    into markdown/text, which is spliced into the dictated text at spoken
    anchor phrases (or appended at the end).
    """

    enabled: bool = False
    provider: str = "openai_compatible"
    endpoint: Optional[str] = None
    api_key_env: Optional[str] = None  # name of env var, not the key itself
    model: Optional[str] = None
    capture_timeout_s: int = 30  # how long to wait for the user to finish snipping
    # Spoken phrases that mark where extracted content is spliced. Empty → use
    # the built-in defaults (see vision/anchors.py).
    anchor_phrases: list[str] = Field(default_factory=list)
    output_format: Literal["auto", "markdown", "plain"] = "auto"
    extra: dict = Field(default_factory=dict)

    @field_validator("capture_timeout_s")
    @classmethod
    def _validate_capture_timeout(cls, value: int) -> int:
        if value < 1 or value > 300:
            raise ConfigError("vision.capture_timeout_s must be in [1, 300].")
        return value


# ── v0.4.0: Observer mode config ────────────────────────────────────
# The schema here is a verbatim copy of v0.4.0-contracts.md §2 — every
# field, default, and constraint. Tracks 2 and 3 read from this model
# without changing it.

_DEFAULT_EXCLUDE_APPS = [
    "1Password.exe",
    "KeePass.exe",
    "KeePassXC.exe",
    "Bitwarden.exe",
    "Signal.exe",
    "Dashlane.exe",
    "LastPass.exe",
]
_DEFAULT_EXCLUDE_TITLES = [
    "*InPrivate*",
    "*Incognito*",
    "*Private Browsing*",
    "*Password*",
]


class ObserverStorageConfig(BaseModel):
    """Where Observer writes its DB, blobs, and exports.

    Attributes:
        dir: Root directory. Stored as written; expanded at use time so
            the settings UI can round-trip the user's literal string.
        retention_days: Sessions older than this are purged at startup.
            0 disables auto-purge entirely.
        max_session_mb: Per-session blob cap; capture stops once exceeded.
    """

    dir: str = "~/.agentvoca/observer"
    retention_days: int = 7
    max_session_mb: int = 500

    @field_validator("retention_days")
    @classmethod
    def _validate_retention_days(cls, value: int) -> int:
        if value < 0:
            raise ConfigError("observer.storage.retention_days must be >= 0 (0 disables purge).")
        return value

    @field_validator("max_session_mb")
    @classmethod
    def _validate_max_session_mb(cls, value: int) -> int:
        if value < 1 or value > 10_000:
            raise ConfigError("observer.storage.max_session_mb must be in [1, 10000].")
        return value


class ObserverTriggersConfig(BaseModel):
    """Keyframe trigger configuration.

    Each source is individually toggleable. ``speech_onset`` is the trigger
    that grounds an utterance to a screen and is the most valuable for the
    v0.5.0 Agent (D9). Defaults to True.
    """

    window_change: bool = True
    scroll_settle: bool = True
    click_selection: bool = True
    speech_onset: bool = True  # D9 — flag to owner
    scroll_settle_ms: int = 600
    min_interval_ms: int = 4000
    max_keyframes_per_min: int = 4

    @field_validator("scroll_settle_ms")
    @classmethod
    def _validate_scroll_settle_ms(cls, value: int) -> int:
        if value < 100 or value > 5000:
            raise ConfigError("observer.triggers.scroll_settle_ms must be in [100, 5000].")
        return value

    @field_validator("min_interval_ms")
    @classmethod
    def _validate_min_interval_ms(cls, value: int) -> int:
        if value < 500 or value > 60_000:
            raise ConfigError("observer.triggers.min_interval_ms must be in [500, 60000].")
        return value

    @field_validator("max_keyframes_per_min")
    @classmethod
    def _validate_max_keyframes_per_min(cls, value: int) -> int:
        if value < 1 or value > 60:
            raise ConfigError("observer.triggers.max_keyframes_per_min must be in [1, 60].")
        return value


class ObserverScreenConfig(BaseModel):
    """Screen capture scope and encoding.

    v0.4.0 accepts ``scope == "active_window"`` only (D6). Full-screen
    capture is targeted for v0.4.1.
    """

    scope: Literal["active_window"] = "active_window"
    max_width_px: int = 1280
    jpeg_quality: int = 75
    dedup_phash_distance: int = 6

    @field_validator("max_width_px")
    @classmethod
    def _validate_max_width_px(cls, value: int) -> int:
        if value < 640 or value > 3840:
            raise ConfigError("observer.screen.max_width_px must be in [640, 3840].")
        return value

    @field_validator("jpeg_quality")
    @classmethod
    def _validate_jpeg_quality(cls, value: int) -> int:
        if value < 40 or value > 95:
            raise ConfigError("observer.screen.jpeg_quality must be in [40, 95].")
        return value

    @field_validator("dedup_phash_distance")
    @classmethod
    def _validate_dedup_phash_distance(cls, value: int) -> int:
        if value < 0 or value > 32:
            raise ConfigError(
                "observer.screen.dedup_phash_distance must be in [0, 32] (0 disables dedup)."
            )
        return value


class ObserverOCRConfig(BaseModel):
    """OCR provider configuration.

    ``api_key_env`` is the **name** of an environment variable, never the
    key itself. The model validator in ``FullConfig`` refuses to load
    a remote provider when the env var is missing (when observer is enabled).
    """

    provider: str = "rapidocr"
    endpoint: Optional[str] = None
    api_key_env: Optional[str] = None  # env var name, never the key
    model: Optional[str] = None
    max_queue: int = 32

    @field_validator("max_queue")
    @classmethod
    def _validate_max_queue(cls, value: int) -> int:
        if value < 4 or value > 256:
            raise ConfigError("observer.ocr.max_queue must be in [4, 256].")
        return value


class ObserverSelectionConfig(BaseModel):
    """Highlighted-text capture configuration.

    ``method == "uia"`` uses Windows UI Automation ``TextPattern``
    (read-only, never touches the clipboard). ``"ocr_rect"`` falls back to
    OCR over the active selection rectangle. ``"none"`` disables selection
    capture entirely (e.g. on macOS where UIA is unavailable).
    """

    enabled: bool = True
    method: Literal["uia", "ocr_rect", "none"] = "uia"
    max_chars: int = 4000

    @field_validator("max_chars")
    @classmethod
    def _validate_max_chars(cls, value: int) -> int:
        if value < 100 or value > 100_000:
            raise ConfigError("observer.selection.max_chars must be in [100, 100000].")
        return value


class ObserverCompileConfig(BaseModel):
    """Session compiler configuration.

    ``provider == "rules"`` is the zero-config default (no API key
    required). ``output_dir`` is stored as written; when left at its
    default sentinel the model validator resolves it to
    ``<observer.storage.dir>/exports``.
    """

    provider: str = "rules"
    endpoint: Optional[str] = None
    api_key_env: Optional[str] = None
    model: Optional[str] = None
    formats: list[str] = Field(default_factory=lambda: ["markdown", "json"])
    output_dir: str = ""  # resolved by ObserverConfig._resolve_output_dir

    @field_validator("formats")
    @classmethod
    def _validate_formats(cls, value: list[str]) -> list[str]:
        if not value:
            raise ConfigError("observer.compile.formats must be non-empty.")
        allowed = {"markdown", "json"}
        bad = [f for f in value if f not in allowed]
        if bad:
            raise ConfigError(
                f"observer.compile.formats contains invalid entries {bad!r}; "
                f"allowed values are {sorted(allowed)}."
            )
        # Preserve insertion order, but de-duplicate so ["json", "json"] is fine.
        seen: list[str] = []
        for f in value:
            if f not in seen:
                seen.append(f)
        return seen


class ObserverPrivacyConfig(BaseModel):
    """Foreground exclusion lists. Glob patterns, case-insensitive on Windows.

    When the foreground app or window title matches, Observer pauses and
    records a ``pause_start``/``pause_end`` pair — nothing is captured.
    """

    exclude_apps: list[str] = Field(default_factory=lambda: list(_DEFAULT_EXCLUDE_APPS))
    exclude_title_patterns: list[str] = Field(default_factory=lambda: list(_DEFAULT_EXCLUDE_TITLES))


class ObserverConfig(BaseModel):
    """Master Observer configuration.

    The block is fully additive: an existing config without an ``observer:``
    key loads unchanged with ``enabled = False`` and all defaults.
    """

    enabled: bool = False
    storage: ObserverStorageConfig = Field(default_factory=ObserverStorageConfig)
    triggers: ObserverTriggersConfig = Field(default_factory=ObserverTriggersConfig)
    screen: ObserverScreenConfig = Field(default_factory=ObserverScreenConfig)
    ocr: ObserverOCRConfig = Field(default_factory=ObserverOCRConfig)
    selection: ObserverSelectionConfig = Field(default_factory=ObserverSelectionConfig)
    compile: ObserverCompileConfig = Field(default_factory=ObserverCompileConfig)
    privacy: ObserverPrivacyConfig = Field(default_factory=ObserverPrivacyConfig)

    @model_validator(mode="after")
    def _resolve_output_dir(self) -> "ObserverConfig":
        """Resolve ``compile.output_dir`` against ``storage.dir`` when empty.

        The empty string is a sentinel for "use the default"; storing the
        resolved value here means downstream code can use it verbatim
        without re-implementing the resolution rule.
        """
        if self.compile.output_dir == "":
            base = self.storage.dir.rstrip("/").rstrip("\\")
            self.compile.output_dir = f"{base}/exports"
        return self


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

    # -- v2: new config blocks (all optional with v1-equivalent defaults) --
    context: ContextConfig = Field(default_factory=ContextConfig)
    commands: CommandsConfig = Field(default_factory=CommandsConfig)
    adaptive: AdaptiveConfig = Field(default_factory=AdaptiveConfig)

    # -- v3: screenshot-to-text vision (optional, off by default) --
    vision: VisionConfig = Field(default_factory=VisionConfig)

    # -- v0.4.0: Observer mode (optional, off by default) --
    observer: ObserverConfig = Field(default_factory=ObserverConfig)

    @model_validator(mode="after")
    def _validate_api_key_env(self) -> "FullConfig":
        """Check that api_key_env vars are set when a provider is remote.

        A provider is considered 'remote' when ``endpoint`` is set.
        """
        if self.asr.endpoint is not None and self.asr.api_key_env is not None:
            if self.asr.api_key_env not in os.environ:
                raise ConfigError(
                    f"ASR provider '{self.asr.provider}' requires an API key. "
                    f"Set env var '{self.asr.api_key_env}'."
                )

        if self.cleanup.endpoint is not None and self.cleanup.api_key_env is not None:
            if self.cleanup.api_key_env not in os.environ:
                raise ConfigError(
                    f"Cleanup provider '{self.cleanup.provider}' requires an API key. "
                    f"Set env var '{self.cleanup.api_key_env}'."
                )

        # v3: only enforce the vision key when the feature is turned on.
        if self.vision.enabled and self.vision.api_key_env:
            if self.vision.endpoint is not None and self.vision.api_key_env not in os.environ:
                raise ConfigError(
                    f"Vision provider '{self.vision.provider}' requires an API key. "
                    f"Set env var '{self.vision.api_key_env}' or disable vision."
                )

        # v0.4.0: only enforce Observer provider keys when Observer is on, and
        # only when the provider is remote (endpoint is set). Local defaults
        # (rapidocr, rules) must work with no env vars at all, even when
        # Observer is enabled — that is the zero-config property the release
        # rests on.
        if self.observer.enabled:
            for name, block in (
                ("OCR", self.observer.ocr),
                ("compiler", self.observer.compile),
            ):
                if block.endpoint is not None and block.api_key_env:
                    if block.api_key_env not in os.environ:
                        raise ConfigError(
                            f"Observer {name} provider '{block.provider}' requires an API key. "
                            f"Set env var '{block.api_key_env}' or disable observer."
                        )

        return self
