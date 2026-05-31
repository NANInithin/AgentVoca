"""State machine for the voice dictation pipeline.

Implements the exact state transition table defined in the architecture
spec (§6.2). The state machine is a pure validator — it accepts a current
state and an event, checks conditions, and returns the resulting state
along with symbolic side-effect names. The orchestrator is responsible
for executing the actual side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentvoca.core.types import AppState

# Re-export the AppState type for convenience.
# Allowed state values.
STATES: set[str] = {"idle", "recording", "transcribing", "cleaning", "inserting", "error"}

# Side-effect strings the orchestrator must implement.
SideEffect = str


@dataclass
class TransitionRule:
    """A single entry in the transition table."""

    from_state: str
    event_type: str  # e.g. "HotkeyEvent", "VADSpeechEvent", etc.
    condition: str | None = None  # Named condition key; None means "always"
    to_state: str | None = None  # None means "unchanged / no transition"


@dataclass
class TransitionResult:
    """Result of evaluating a transition.

    Attributes:
        new_state: The state the machine transitions to, or the current
            state if no matching transition is found.
        side_effects: List of side-effect strings for the orchestrator
            to execute.
        transitioned: True if a matching transition rule was applied.
    """

    new_state: str
    side_effects: list[str] = field(default_factory=list)
    transitioned: bool = False


class InvalidTransitionError(Exception):
    """Raised when a transition is requested that is not allowed from the
    current state."""


# ── Transition Table (declarative, matches §6.2) ────────────────────

_TRANSITIONS: list[TransitionRule] = [
    # idle → recording
    TransitionRule("idle", "HotkeyEvent", "toggle_recording__toggle_or_auto_stop", "recording"),
    TransitionRule("idle", "HotkeyEvent", "toggle_recording__push_to_talk", "recording"),
    # idle → inserting (re-insert last transcript)
    TransitionRule("idle", "HotkeyEvent", "insert_last__available", "inserting"),
    # recording → transcribing
    TransitionRule("recording", "HotkeyEvent", "toggle_recording__toggle", "transcribing"),
    TransitionRule("recording", "HotkeyEvent", "toggle_recording__push_to_talk", "transcribing"),
    TransitionRule("recording", "VADSpeechEvent", "silence_timeout", "transcribing"),
    TransitionRule("recording", "DurationEvent", "always", "transcribing"),
    # recording → idle (cancel)
    TransitionRule("recording", "HotkeyEvent", "cancel", "idle"),
    # transcribing → cleaning
    TransitionRule("transcribing", "TranscriptEvent", "final", "cleaning"),
    # transcribing → error
    TransitionRule("transcribing", "ErrorEvent", "asr_retries_exhausted", "error"),
    # transcribing → idle (cancel)
    TransitionRule("transcribing", "HotkeyEvent", "cancel", "idle"),
    # cleaning → inserting (success or cleanup_error fallback)
    TransitionRule("cleaning", "CleanedTextEvent", "success", "inserting"),
    TransitionRule("cleaning", "ErrorEvent", "cleanup_error", "inserting"),
    # cleaning → idle (cancel)
    TransitionRule("cleaning", "HotkeyEvent", "cancel", "idle"),
    # inserting → idle (success)
    TransitionRule("inserting", "InsertionCompleteEvent", "success", "idle"),
    # inserting → idle (clipboard fallback)
    TransitionRule("inserting", "InsertionCompleteEvent", "clipboard_fallback", "idle"),
    # inserting → error (no clipboard fallback)
    TransitionRule("inserting", "InsertionCompleteEvent", "no_clipboard_fallback", "error"),
    # error → idle
    TransitionRule("error", "TimeoutEvent", "always", "idle"),
    TransitionRule("error", "HotkeyEvent", "cancel", "idle"),
    # any → unchanged (open_settings is handled separately, non-blocking)
    TransitionRule("any", "HotkeyEvent", "open_settings", None),
]


# ── Side Effects (mapped from §6.2) ─────────────────────────────────


def _side_effects_for(from_state: str, to_state: str, condition: str | None) -> list[str]:
    """Return the list of side-effect symbolic names for a matched transition.

    These are looked up by the orchestrator to determine what work to do.
    """
    effects: list[str] = []

    # ── idle → recording ─────────────────────────────────────────────
    if from_state == "idle" and to_state == "recording":
        effects.append("start_audio_capture")
        if condition == "toggle_recording__toggle_or_auto_stop":
            effects.append("show_recording_indicator")

    # ── idle → inserting (re-insert) ─────────────────────────────────
    elif from_state == "idle" and to_state == "inserting":
        effects.append("insert_last_transcript")

    # ── recording → transcribing ─────────────────────────────────────
    elif from_state == "recording" and to_state == "transcribing":
        effects.append("stop_audio_capture")
        effects.append("emit_recording_stopped")

    # ── recording → idle (cancel) ────────────────────────────────────
    elif from_state == "recording" and to_state == "idle":
        effects.append("cancel_recording")

    # ── transcribing → cleaning ──────────────────────────────────────
    elif from_state == "transcribing" and to_state == "cleaning":
        effects.append("submit_to_cleanup")

    # ── transcribing → error ─────────────────────────────────────────
    elif from_state == "transcribing" and to_state == "error":
        effects.append("emit_asr_error")
        effects.append("notify_user")

    # ── transcribing → idle (cancel) ─────────────────────────────────
    elif from_state == "transcribing" and to_state == "idle":
        effects.append("discard_transcript")

    # ── cleaning → inserting ─────────────────────────────────────────
    elif from_state == "cleaning" and to_state == "inserting":
        if condition == "cleanup_error":
            effects.append("use_raw_fallback")
            effects.append("log_cleanup_warning")
        effects.append("start_insertion")

    # ── cleaning → idle (cancel) ─────────────────────────────────────
    elif from_state == "cleaning" and to_state == "idle":
        effects.append("discard_transcript")

    # ── inserting → idle ─────────────────────────────────────────────
    elif from_state == "inserting" and to_state == "idle":
        if condition == "success":
            effects.append("store_last_transcript")
            effects.append("hide_indicator")
        elif condition == "clipboard_fallback":
            effects.append("clipboard_insert")
            effects.append("notify_clipboard_used")

    # ── inserting → error ────────────────────────────────────────────
    elif from_state == "inserting" and to_state == "error":
        effects.append("emit_insertion_error")

    # ── error → idle ─────────────────────────────────────────────────
    elif from_state == "error" and to_state == "idle":
        effects.append("reset")

    return effects


# ── State Machine ────────────────────────────────────────────────────


class StateMachine:
    """Pure state machine for the dictation pipeline.

    Usage::

        sm = StateMachine()
        result = sm.transition("HotkeyEvent", action="toggle_recording", mode="toggle")
        if result.transitioned:
            print(result.new_state, result.side_effects)
    """

    def __init__(self, initial_state: AppState = "idle") -> None:
        if initial_state not in STATES:
            raise ValueError(f"Invalid initial state: {initial_state!r}")
        self._state: str = initial_state

    @property
    def state(self) -> str:
        """Return the current state."""
        return self._state

    def reset(self, to_state: AppState = "idle") -> None:
        """Force-reset the machine to a given state."""
        if to_state not in STATES:
            raise ValueError(f"Invalid state: {to_state!r}")
        self._state = to_state

    def transition(
        self,
        event_type: str,
        **context: Any,
    ) -> TransitionResult:
        """Evaluate a single event against the transition table.

        Args:
            event_type: The type/name of the event (e.g. ``"HotkeyEvent"``).
            **context: Key-value pairs that determine which condition
                matches. See the condition functions below.

        Returns:
            A ``TransitionResult`` with the resulting state and side effects.
            If no rule matches, returns the current state with
            ``transitioned=False``.
        """
        best: TransitionRule | None = None
        best_condition: str | None = None

        for rule in _TRANSITIONS:
            if rule.from_state != "any" and rule.from_state != self._state:
                continue
            if rule.event_type != event_type:
                continue
            if rule.condition is not None and not self._eval_condition(rule.condition, context):
                continue
            # First-match wins (rules are ordered by priority)
            best = rule
            best_condition = rule.condition
            break

        if best is None:
            return TransitionResult(
                new_state=self._state,
                side_effects=[],
                transitioned=False,
            )

        new_state = best.to_state if best.to_state is not None else self._state
        side_effects = _side_effects_for(self._state, new_state, best_condition)

        # Mutate internal state
        self._state = new_state

        return TransitionResult(
            new_state=new_state,
            side_effects=side_effects,
            transitioned=(new_state != self._state or side_effects != []),
        )

    # ── Condition evaluators ─────────────────────────────────────────

    @staticmethod
    def _eval_condition(condition: str, context: dict[str, Any]) -> bool:
        """Evaluate a named condition against the provided context dict.

        Each ``if`` branch corresponds to one row in §6.2.
        """
        ctx = context  # shorthand

        if condition == "toggle_recording__toggle_or_auto_stop":
            return ctx.get("action") == "toggle_recording" and ctx.get("mode") in (
                "toggle",
                "auto_stop",
            )

        if condition == "toggle_recording__push_to_talk":
            return ctx.get("action") == "toggle_recording" and ctx.get("mode") == "push_to_talk"

        if condition == "toggle_recording__toggle":
            return ctx.get("action") == "toggle_recording" and ctx.get("mode") == "toggle"

        if condition == "insert_last__available":
            return (
                ctx.get("action") == "insert_last" and ctx.get("last_transcript_available") is True
            )

        if condition == "silence_timeout":
            return ctx.get("is_speech") is False and ctx.get("silence_timeout_reached") is True

        if condition == "always":
            return True

        if condition == "cancel":
            return ctx.get("action") == "cancel"

        if condition == "final":
            return ctx.get("is_final") is True

        if condition == "asr_retries_exhausted":
            return ctx.get("retries_exhausted") is True and ctx.get("stage") == "asr"

        if condition == "cleanup_error":
            return ctx.get("stage") == "cleanup"

        if condition == "success":
            return ctx.get("success") is True

        if condition == "clipboard_fallback":
            return ctx.get("success") is False and ctx.get("clipboard_fallback") is True

        if condition == "no_clipboard_fallback":
            return ctx.get("success") is False and ctx.get("clipboard_fallback") is False

        if condition == "open_settings":
            return ctx.get("action") == "open_settings"

        # Unknown condition -> False (safe default)
        return False
