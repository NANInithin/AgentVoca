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

import logging
from typing import Iterable

logger = logging.getLogger(__name__)

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
        # v0.4.0: Observer master switch and storage dir both require
        # a restart — the controller owns a long-lived ObserverStore
        # bound to the dir, and turning the feature on/off re-creates
        # the capture + compile subsystems in main.py.
        "observer.enabled",
        "observer.storage",
        "observer.storage.dir",
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
        "hotkeys.toggle_observer",
        "hotkeys.pause_observer",
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
        # v0.4.0: Observer runtime knobs are picked up the next time
        # a session is started, not the next time the user opens
        # settings. The capture subsystem reads them from the
        # controller's draft on each start.
        "observer.triggers",
        "observer.triggers.window_change",
        "observer.triggers.scroll_settle",
        "observer.triggers.click_selection",
        "observer.triggers.speech_onset",
        "observer.triggers.scroll_settle_ms",
        "observer.triggers.min_interval_ms",
        "observer.triggers.max_keyframes_per_min",
        "observer.screen",
        "observer.screen.scope",
        "observer.screen.max_width_px",
        "observer.screen.jpeg_quality",
        "observer.screen.dedup_phash_distance",
        "observer.ocr",
        "observer.ocr.provider",
        "observer.ocr.endpoint",
        "observer.ocr.api_key_env",
        "observer.ocr.model",
        "observer.ocr.max_queue",
        "observer.selection",
        "observer.selection.enabled",
        "observer.selection.method",
        "observer.selection.max_chars",
        "observer.compile",
        "observer.compile.provider",
        "observer.compile.endpoint",
        "observer.compile.api_key_env",
        "observer.compile.model",
        "observer.compile.formats",
        "observer.privacy",
        "observer.privacy.exclude_apps",
        "observer.privacy.exclude_title_patterns",
    }
)


def _classify(path: str) -> str | None:
    """Classify ``path`` as ``"hot"``, ``"restart"``, or ``None`` (unknown).

    ``_diff_paths`` (config_controller.py) yields both a list field's own
    path (e.g. ``"vocabulary.inline"``) and per-index paths for any entries
    that changed (e.g. ``"vocabulary.inline.1"``, or for a list of dicts,
    ``"context.profiles.0.name"``). Only the bare field is enumerated in
    ``_HOT_FIELDS``/``_RESTART_FIELDS``, so we walk from the full path up to
    its shortest prefix and classify by the first (i.e. longest) prefix that
    is known — this is the "matches the literal key and any prefix under
    it" behavior described in the module docstring.
    """
    parts = path.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in _HOT_FIELDS:
            return "hot"
        if candidate in _RESTART_FIELDS:
            return "restart"
    return None


def is_restart_field(path: str) -> bool:
    """Return True if the field at dotted ``path`` requires an app restart."""
    return _classify(path) == "restart"


def is_hot_field(path: str) -> bool:
    """Return True if the field at dotted ``path`` can be applied live."""
    return _classify(path) == "hot"


def partition(changed_paths: Iterable[str]) -> tuple[list[str], list[str]]:
    """Split a set of changed paths into (hot, restart).

    Paths not classified either way (even after prefix matching, see
    ``_classify``) default to restart to fail safe, and are logged at
    WARNING so a missing classification surfaces during development instead
    of silently producing a misleading "restart required" banner for a
    field that may not actually need one.
    """
    hot: list[str] = []
    restart: list[str] = []
    for path in changed_paths:
        classification = _classify(path)
        if classification == "hot":
            hot.append(path)
        else:
            if classification is None:
                logger.warning(
                    "Config field '%s' changed but is not classified as hot "
                    "or restart; defaulting to restart. Add it to "
                    "restart_policy._HOT_FIELDS or _RESTART_FIELDS to silence.",
                    path,
                )
            restart.append(path)
    return hot, restart


def all_known_paths() -> tuple[frozenset[str], frozenset[str]]:
    """Return the full (hot, restart) classification — useful for tests."""
    return _HOT_FIELDS, _RESTART_FIELDS
