"""Unit tests for the StateMachine.

Covers every transition in the architecture spec §6.2, including fallback
paths, cancel actions, and error recovery.
"""

import pytest

from agentvoca.core.state_machine import StateMachine


class TestStateMachineInitialState:
    """The machine starts in ``idle``."""

    def test_initial_state_is_idle(self) -> None:
        sm = StateMachine()
        assert sm.state == "idle"

    def test_custom_initial_state(self) -> None:
        sm = StateMachine(initial_state="recording")
        assert sm.state == "recording"

    def test_invalid_initial_state_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid initial state"):
            StateMachine(initial_state="invalid_state")


class TestTransitionsFromIdle:
    """§6.2 transitions starting from ``idle``."""

    def test_idle_to_recording_toggle_mode(self) -> None:
        sm = StateMachine()
        result = sm.transition("HotkeyEvent", action="toggle_recording", mode="toggle")

        assert result.transitioned is True
        assert result.new_state == "recording"
        assert "start_audio_capture" in result.side_effects
        assert "show_recording_indicator" in result.side_effects

    def test_idle_to_recording_push_to_talk(self) -> None:
        sm = StateMachine()
        result = sm.transition("HotkeyEvent", action="toggle_recording", mode="push_to_talk")

        assert result.transitioned is True
        assert result.new_state == "recording"
        assert "start_audio_capture" in result.side_effects
        # push_to_talk does NOT show recording indicator per spec
        assert "show_recording_indicator" not in result.side_effects

    def test_idle_to_recording_auto_stop_mode(self) -> None:
        sm = StateMachine()
        result = sm.transition("HotkeyEvent", action="toggle_recording", mode="auto_stop")

        assert result.transitioned is True
        assert result.new_state == "recording"
        assert "show_recording_indicator" in result.side_effects

    def test_idle_to_inserting_reinsert(self) -> None:
        sm = StateMachine()
        result = sm.transition(
            "HotkeyEvent",
            action="insert_last",
            last_transcript_available=True,
        )

        assert result.transitioned is True
        assert result.new_state == "inserting"
        assert "insert_last_transcript" in result.side_effects

    def test_idle_no_transition_for_unrelated_event(self) -> None:
        sm = StateMachine()
        result = sm.transition("UnknownEvent")
        assert result.transitioned is False
        assert result.new_state == "idle"
        assert result.side_effects == []


class TestTransitionsFromRecording:
    """§6.2 transitions starting from ``recording``."""

    def test_recording_to_transcribing_toggle(self) -> None:
        sm = StateMachine(initial_state="recording")
        result = sm.transition("HotkeyEvent", action="toggle_recording", mode="toggle")

        assert result.transitioned is True
        assert result.new_state == "transcribing"
        assert "stop_audio_capture" in result.side_effects

    def test_recording_to_transcribing_push_to_talk(self) -> None:
        sm = StateMachine(initial_state="recording")
        result = sm.transition("HotkeyEvent", action="toggle_recording", mode="push_to_talk")

        assert result.transitioned is True
        assert result.new_state == "transcribing"
        assert "stop_audio_capture" in result.side_effects

    def test_recording_to_transcribing_vad_silence(self) -> None:
        sm = StateMachine(initial_state="recording")
        result = sm.transition(
            "VADSpeechEvent",
            is_speech=False,
            silence_timeout_reached=True,
        )

        assert result.transitioned is True
        assert result.new_state == "transcribing"
        assert "emit_recording_stopped" in result.side_effects

    def test_recording_to_transcribing_duration_exceeded(self) -> None:
        sm = StateMachine(initial_state="recording")
        result = sm.transition("DurationEvent")

        assert result.transitioned is True
        assert result.new_state == "transcribing"

    def test_recording_to_idle_cancel(self) -> None:
        sm = StateMachine(initial_state="recording")
        result = sm.transition("HotkeyEvent", action="cancel")

        assert result.transitioned is True
        assert result.new_state == "idle"
        assert "cancel_recording" in result.side_effects


class TestTransitionsFromTranscribing:
    """§6.2 transitions starting from ``transcribing``."""

    def test_transcribing_to_cleaning_final_transcript(self) -> None:
        sm = StateMachine(initial_state="transcribing")
        result = sm.transition("TranscriptEvent", is_final=True)

        assert result.transitioned is True
        assert result.new_state == "cleaning"
        assert "submit_to_cleanup" in result.side_effects

    def test_transcribing_to_error_retries_exhausted(self) -> None:
        sm = StateMachine(initial_state="transcribing")
        result = sm.transition("ErrorEvent", retries_exhausted=True, stage="asr")

        assert result.transitioned is True
        assert result.new_state == "error"
        assert "emit_asr_error" in result.side_effects

    def test_transcribing_to_idle_cancel(self) -> None:
        sm = StateMachine(initial_state="transcribing")
        result = sm.transition("HotkeyEvent", action="cancel")

        assert result.transitioned is True
        assert result.new_state == "idle"
        assert "discard_transcript" in result.side_effects


class TestTransitionsFromCleaning:
    """§6.2 transitions starting from ``cleaning``."""

    def test_cleaning_to_inserting_success(self) -> None:
        sm = StateMachine(initial_state="cleaning")
        result = sm.transition("CleanedTextEvent", success=True)

        assert result.transitioned is True
        assert result.new_state == "inserting"
        assert "start_insertion" in result.side_effects
        assert "use_raw_fallback" not in result.side_effects

    def test_cleaning_to_inserting_fallback_on_cleanup_error(self) -> None:
        sm = StateMachine(initial_state="cleaning")
        result = sm.transition("ErrorEvent", stage="cleanup")

        assert result.transitioned is True
        assert result.new_state == "inserting"
        assert "use_raw_fallback" in result.side_effects
        assert "log_cleanup_warning" in result.side_effects
        assert "start_insertion" in result.side_effects

    def test_cleaning_to_idle_cancel(self) -> None:
        sm = StateMachine(initial_state="cleaning")
        result = sm.transition("HotkeyEvent", action="cancel")

        assert result.transitioned is True
        assert result.new_state == "idle"
        assert "discard_transcript" in result.side_effects


class TestTransitionsFromInserting:
    """§6.2 transitions starting from ``inserting``."""

    def test_inserting_to_idle_success(self) -> None:
        sm = StateMachine(initial_state="inserting")
        result = sm.transition("InsertionCompleteEvent", success=True)

        assert result.transitioned is True
        assert result.new_state == "idle"
        assert "store_last_transcript" in result.side_effects
        assert "hide_indicator" in result.side_effects

    def test_inserting_to_idle_clipboard_fallback(self) -> None:
        sm = StateMachine(initial_state="inserting")
        result = sm.transition(
            "InsertionCompleteEvent",
            success=False,
            clipboard_fallback=True,
        )

        assert result.transitioned is True
        assert result.new_state == "idle"
        assert "clipboard_insert" in result.side_effects
        assert "notify_clipboard_used" in result.side_effects

    def test_inserting_to_error_no_clipboard_fallback(self) -> None:
        sm = StateMachine(initial_state="inserting")
        result = sm.transition(
            "InsertionCompleteEvent",
            success=False,
            clipboard_fallback=False,
        )

        assert result.transitioned is True
        assert result.new_state == "error"
        assert "emit_insertion_error" in result.side_effects


class TestTransitionsFromError:
    """§6.2 transitions starting from ``error``."""

    def test_error_to_idle_timeout(self) -> None:
        sm = StateMachine(initial_state="error")
        result = sm.transition("TimeoutEvent")

        assert result.transitioned is True
        assert result.new_state == "idle"
        assert "reset" in result.side_effects

    def test_error_to_idle_cancel(self) -> None:
        sm = StateMachine(initial_state="error")
        result = sm.transition("HotkeyEvent", action="cancel")

        assert result.transitioned is True
        assert result.new_state == "idle"
        assert "reset" in result.side_effects


class TestOpenSettingsNonBlocking:
    """The ``open_settings`` event does not change state from any state."""

    @pytest.mark.parametrize(
        "initial", ["idle", "recording", "transcribing", "cleaning", "inserting", "error"]
    )
    def test_open_settings_does_not_change_state(self, initial: str) -> None:
        sm = StateMachine(initial_state=initial)  # type: ignore[arg-type]
        result = sm.transition("HotkeyEvent", action="open_settings")

        assert result.new_state == initial
        assert result.side_effects == []
        # transitioned is True because the rule matched (side effects could exist)
        # but the state didn't change and side_effects is empty

    def test_open_settings_from_idle(self) -> None:
        sm = StateMachine()
        result = sm.transition("HotkeyEvent", action="open_settings")

        # State remains idle
        assert result.new_state == "idle"


class TestReset:
    """Force-reset the state machine."""

    def test_reset_to_idle(self) -> None:
        sm = StateMachine(initial_state="inserting")
        sm.reset("idle")
        assert sm.state == "idle"

    def test_reset_invalid_state(self) -> None:
        sm = StateMachine()
        with pytest.raises(ValueError, match="Invalid state"):
            sm.reset("nonexistent")


class TestFullCycle:
    """A complete happy-path dictation cycle."""

    def test_full_happy_path(self) -> None:
        sm = StateMachine()

        # idle → recording
        r1 = sm.transition("HotkeyEvent", action="toggle_recording", mode="toggle")
        assert r1.new_state == "recording"

        # recording → transcribing
        r2 = sm.transition("HotkeyEvent", action="toggle_recording", mode="toggle")
        assert r2.new_state == "transcribing"

        # transcribing → cleaning
        r3 = sm.transition("TranscriptEvent", is_final=True)
        assert r3.new_state == "cleaning"

        # cleaning → inserting
        r4 = sm.transition("CleanedTextEvent", success=True)
        assert r4.new_state == "inserting"

        # inserting → idle
        r5 = sm.transition("InsertionCompleteEvent", success=True)
        assert r5.new_state == "idle"


class TestFallbackCycle:
    """A cycle where cleanup fails and insertion uses clipboard."""

    def test_cleanup_fallback_then_clipboard_insert(self) -> None:
        sm = StateMachine()

        # idle → recording
        sm.transition("HotkeyEvent", action="toggle_recording", mode="toggle")
        # recording → transcribing
        sm.transition("HotkeyEvent", action="toggle_recording", mode="toggle")
        # transcribing → cleaning
        sm.transition("TranscriptEvent", is_final=True)

        # cleaning → inserting (with fallback because cleanup errored)
        result = sm.transition("ErrorEvent", stage="cleanup")
        assert result.new_state == "inserting"
        assert "use_raw_fallback" in result.side_effects

        # inserting → idle (clipboard fallback because keyboard insertion failed)
        result2 = sm.transition("InsertionCompleteEvent", success=False, clipboard_fallback=True)
        assert result2.new_state == "idle"
        assert "clipboard_insert" in result2.side_effects


class TestErrorRecovery:
    """Reach error state and recover to idle."""

    def test_asr_error_then_cancel_recovery(self) -> None:
        sm = StateMachine()

        # Drive to transcribing
        sm.transition("HotkeyEvent", action="toggle_recording", mode="toggle")
        sm.transition("HotkeyEvent", action="toggle_recording", mode="toggle")

        # ASR error → error
        r1 = sm.transition("ErrorEvent", retries_exhausted=True, stage="asr")
        assert r1.new_state == "error"

        # Cancel → idle
        r2 = sm.transition("HotkeyEvent", action="cancel")
        assert r2.new_state == "idle"
