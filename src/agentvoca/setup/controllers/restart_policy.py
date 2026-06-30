"""Restart policy — classify every FullConfig field as hot-apply or restart.

A "hot" change can be applied while the app is running. A "restart" change
takes effect only on the next process start. This module is the single source
of truth so the wizard and the settings window report the same set.

The classification mirrors ``orchestrator.py`` lifecycle: anything that
requires re-instantiating providers, re-opening audio devices, or re-registering
hotkeys is restart. Anything that mutates objects the orchestrator already
holds a reference to (vocab dictionary, snippet expander, command processor,
adaptive store, vision anchor splicer, cleanup-provider instances already
built) is hot.
"""

from __future__ import annotations

from typing import Iterable

# Dotted paths are matched against ``FullConfig`` field paths, e.g.
# ``"asr.provider"`` matches both the literal key and any prefix under it.
# A change to any matching path is restart-only.
_RESTART_FIELDS: frozenset[str] = frozenset(
    {
        # ASR provider swap requires re-instantiation (faster_whisper loads
        # the model; openai_compatible builds a client).
        "asr.provider",
        "asr.model",
        "asr.endpoint",
        "asr.api_key_env",
        "asr.language_hint",
        "asr.extra",
        "asr.streaming",
        "asr.streaming_model",
        "asr.streaming_chunk_ms",
        "asr.streaming_window_s",
        "asr.warm_up",
        # Audio — sounddevice stream needs a restart.
        "audio.input_device",
        "audio.sample_rate",
        "audio.channels",
        "audio.vad_enabled",
        "audio.silence_timeout_ms",
        "audio.max_recording_duration_s",
        # Insertion strategy swap changes the implementation used at the
        # insert path. Clipboard-fallback flag and char delay are read on
        # every insert and could in principle be hot — keep restart for
        # consistency and to avoid surprising the user mid-dictation.
        "insertion.strategy",
        "insertion.clipboard_fallback",
        "insertion.delay_between_chars_ms",
        # Vision enable/disable constructs/destructs ScreenshotCapturer
        # and the vision provider — restart.
        "vision.enabled",
        "vision.provider",
        "vision.endpoint",
        "vision.api_key_env",
        "vision.model",
        # App-level flags affect the running state machine.
        "app.profile",
        "app.language",
        "app.mode",
        "app.debug",
    }
)

# Fields the orchestrator handles by re-reading its own state on the next
# dictation — explicitly enumerated so adding new fields to the schema forces
# us to make a decision rather than silently choosing one path.
_HOT_FIELDS: frozenset[str] = frozenset(
    {
        # Cleanup — runtime reload re-instantiates the cleanup provider.
        "cleanup.provider",
        "cleanup.model",
        "cleanup.endpoint",
        "cleanup.api_key_env",
        "cleanup.style",
        "cleanup.preserve_code",
        "cleanup.custom_prompt_path",
        "cleanup.extra",
        "cleanup.streaming",
        "cleanup.warm_up",
        # Hotkeys — HotkeyManager exposes unregister_all() + register().
        "hotkeys.toggle_recording",
        "hotkeys.open_settings",
        "hotkeys.insert_last_transcript",
        "hotkeys.undo",
        "hotkeys.cancel",
        "hotkeys.capture_screenshot",
        # Vocab & snippets — reloaded into existing objects.
        "vocabulary.path",
        "vocabulary.inline",
        "snippets.path",
        # Context — read fresh each cleanup pass.
        "context.enabled",
        "context.read_screen",
        "context.read_clipboard",
        "context.profiles",
        # Commands — read on each transcript.
        "commands.enabled",
        "commands.phrases",
        # Adaptive — read on each correction check.
        "adaptive.enabled",
        "adaptive.promote_threshold",
        "adaptive.learned_vocab_path",
        # Vision's runtime knobs are read lazily.
        "vision.capture_timeout_s",
        "vision.anchor_phrases",
        "vision.output_format",
    }
)


def is_restart_field(path: str) -> bool:
    """Return True if the field at dotted ``path`` requires an app restart."""
    return path in _RESTART_FIELDS


def is_hot_field(path: str) -> bool:
    """Return True if the field at dotted ``path`` can be applied live."""
    return path in _HOT_FIELDS


def partition(changed_paths: Iterable[str]) -> tuple[list[str], list[str]]:
    """Split a set of changed paths into (hot, restart).

    Paths not classified either way default to restart to fail safe.
    """
    hot: list[str] = []
    restart: list[str] = []
    for path in changed_paths:
        if is_hot_field(path):
            hot.append(path)
        else:
            restart.append(path)
    return hot, restart


def all_known_paths() -> tuple[frozenset[str], frozenset[str]]:
    """Return the full (hot, restart) classification — useful for tests."""
    return _HOT_FIELDS, _RESTART_FIELDS
