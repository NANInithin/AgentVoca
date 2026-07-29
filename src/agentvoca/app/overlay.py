"""Minimal transparent status overlay showing recording state and interim transcript.

Uses PySide6 to create a small, always-on-top, frameless window that displays
the current app state and the latest transcript text. Subscribes to
``StateChangedEvent`` and ``TranscriptEvent`` to update the display.

v0.4.0 also ships ``ObserverIndicator`` \u2014 a separate, deliberately
non-dismissable, click-through badge that is visible for the entire
Observer session. It must not fight the dictation overlay for screen
position; it is offset to the left of ``StatusOverlay``.
"""

from __future__ import annotations

import logging
import time

from PySide6 import QtCore, QtWidgets

from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import (
    ObserverPausedEvent,
    ObserverSessionEndedEvent,
    ObserverSessionStartedEvent,
    PartialTranscriptEvent,
    StateChangedEvent,
    TranscriptEvent,
    WarmupCompleteEvent,
)

logger = logging.getLogger(__name__)

_STATE_LABELS: dict[str, str] = {
    "idle": "",
    "recording": "\U0001f3a4 Recording\u2026",
    "transcribing": "\u23f3 Transcribing\u2026",
    "cleaning": "\u2728 Cleaning\u2026",
    "inserting": "\U0001f4dd Inserting\u2026",
    "error": "\u26a0\ufe0f Error",
}


class StatusOverlay(QtWidgets.QWidget):
    """Minimal, always-on-top overlay showing dictation status.

    Event-bus handlers may be invoked from a background thread (the persistent
    asyncio loop or the audio callback). Qt widgets must only be touched from
    the GUI thread, so each handler simply emits a signal; the connected slot
    runs on the GUI thread (queued connection) and performs the actual update.

    Args:
        event_bus: Shared event bus for subscribing to state/transcript
            events.
    """

    # Signals marshal updates from worker threads onto the GUI thread.
    _state_sig = QtCore.Signal(str)
    _transcript_sig = QtCore.Signal(str)
    _partial_sig = QtCore.Signal(str)
    _warmup_sig = QtCore.Signal(bool, bool)

    def __init__(self, event_bus: EventBus) -> None:
        super().__init__()
        self._event_bus = event_bus

        # Window setup
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Layout
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)

        self._state_label = QtWidgets.QLabel("")
        self._state_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._state_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")

        self._transcript_label = QtWidgets.QLabel("")
        self._transcript_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._transcript_label.setWordWrap(True)
        self._transcript_label.setStyleSheet("color: rgba(255, 255, 255, 180); font-size: 12px;")
        # Hide transcript label initially
        self._transcript_label.hide()

        layout.addWidget(self._state_label)
        layout.addWidget(self._transcript_label)
        self.setLayout(layout)

        # Background styling (semi-transparent dark)
        self.setStyleSheet(
            "StatusOverlay { background-color: rgba(0, 0, 0, 180); border-radius: 8px; }"
        )

        # Position in top-right corner
        self._reposition()

        # Connect thread-marshalling signals to GUI-thread slots.
        self._state_sig.connect(self._apply_state)
        self._transcript_sig.connect(self._apply_transcript)
        self._partial_sig.connect(self._apply_partial)
        self._warmup_sig.connect(self._apply_warmup)

        # Subscribe to events (handlers may run on a worker thread).
        self._event_bus.subscribe(StateChangedEvent, self._on_state_changed)
        self._event_bus.subscribe(TranscriptEvent, self._on_transcript)
        self._event_bus.subscribe(PartialTranscriptEvent, self._on_partial_transcript)
        self._event_bus.subscribe(WarmupCompleteEvent, self._on_warmup_complete)

    def _reposition(self) -> None:
        """Place the overlay in the top-right corner of the screen."""
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        overlay_width = min(320, geometry.width() // 3)
        x = geometry.right() - overlay_width - 20
        y = geometry.top() + 20
        self.setGeometry(x, y, overlay_width, 80)

    def _on_state_changed(self, event: object) -> None:
        """Emit the state change onto the GUI thread."""
        self._state_sig.emit(getattr(event, "current", "idle"))

    def _on_transcript(self, event: object) -> None:
        """Emit the transcript text onto the GUI thread."""
        self._transcript_sig.emit(getattr(event, "text", "") or "")

    def _on_partial_transcript(self, event: object) -> None:
        """Emit a partial transcript onto the GUI thread."""
        self._partial_sig.emit(getattr(event, "text", "") or "")

    def _on_warmup_complete(self, event: object) -> None:
        """Emit warm-up completion onto the GUI thread."""
        self._warmup_sig.emit(
            bool(getattr(event, "asr_ready", False)),
            bool(getattr(event, "cleanup_ready", False)),
        )

    def _apply_state(self, current: str) -> None:
        """Update the state label when the app state changes (GUI thread)."""
        label = _STATE_LABELS.get(current, "")
        self._state_label.setText(label)

        # Apply state-specific styling
        colors = {
            "recording": "#dc3545",
            "transcribing": "#ffc107",
            "cleaning": "#ffc107",
            "inserting": "#28a745",
            "error": "#dc3545",
        }
        color = colors.get(current, "#ffffff")
        self._state_label.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")

        # Show/hide the overlay window itself based on state
        if current == "idle":
            self._transcript_label.hide()
            self.hide()
        else:
            self.show()
            self._transcript_label.show()

    def _apply_transcript(self, text: str) -> None:
        """Update the transcript display (GUI thread)."""
        if text:
            self._transcript_label.setText(text)
            self._transcript_label.show()

    def _apply_partial(self, text: str) -> None:
        """Update the transcript display with a live partial (GUI thread).

        Partial transcripts are styled as provisional (italic, dimmer) to
        distinguish them from the final transcript that will be inserted.
        """
        if text:
            self._transcript_label.setText(text)
            self._transcript_label.setStyleSheet(
                "color: rgba(255, 255, 255, 140); font-size: 12px; font-style: italic;"
            )
            self._transcript_label.show()

    def _apply_warmup(self, asr_ready: bool, cleanup_ready: bool) -> None:
        """Update the overlay when warm-up finishes (GUI thread).

        The overlay briefly shows a ready indicator and auto-hides after
        a short delay.
        """
        if asr_ready and cleanup_ready:
            self._state_label.setText("✓ Ready")
            self._state_label.setStyleSheet("color: #28a745; font-size: 12px; font-weight: bold;")
        elif not asr_ready:
            self._state_label.setText("⚠ ASR warm-up failed")
            self._state_label.setStyleSheet("color: #ffc107; font-size: 12px;")
        else:
            self._state_label.setText("✓ ASR ready")
            self._state_label.setStyleSheet("color: #28a745; font-size: 12px; font-weight: bold;")

        self.show()
        # Auto-hide after 2 seconds via Qt timer
        QtCore.QTimer.singleShot(2000, self.hide)

    def stop(self) -> None:
        """Clean up subscriptions."""
        self._event_bus.unsubscribe(StateChangedEvent, self._on_state_changed)
        self._event_bus.unsubscribe(TranscriptEvent, self._on_transcript)
        self._event_bus.unsubscribe(PartialTranscriptEvent, self._on_partial_transcript)
        self._event_bus.unsubscribe(WarmupCompleteEvent, self._on_warmup_complete)
        self.close()


# ── v0.4.0: ObserverIndicator ───────────────────────────────────────
# A separate, deliberately non-dismissable, click-through badge that
# is visible for the entire Observer session. Ending the session is
# the only way to dismiss it. Reuses the same window flags as
# ``StatusOverlay`` but is positioned to the left so it does not
# fight the dictation overlay for screen real estate.


def _fmt_elapsed(ms: int) -> str:
    """Format ``ms`` as ``H:MM:SS`` (zero-padded)."""
    if ms < 0:
        ms = 0
    total = ms // 1000
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


class ObserverIndicator(QtWidgets.QWidget):
    """Always-on-top, click-through badge for an active Observer session.

    The whole point of this widget is the consent surface. It is
    visible for the entire session, has no close button, and is
    click-through so it never gets in the user's way. A future
    contributor who feels tempted to add a close button is asked to
    read this docstring and reconsider: the indicator is the
    user's only at-a-glance reminder that Observer is running.

    Args:
        event_bus: Shared event bus for subscribing to session
            started / ended / paused events.
    """

    # Signals marshal updates from worker threads onto the GUI thread.
    _state_sig = QtCore.Signal(bool)  # paused (True) / recording (False)
    _tick_sig = QtCore.Signal(int)  # elapsed ms

    def __init__(self, event_bus: EventBus) -> None:
        super().__init__()
        self._event_bus = event_bus
        self._session_started_monotonic: float = 0.0

        # Window setup: frameless, always-on-top, no taskbar entry, no
        # focus stealing. ``WindowTransparentForInput`` makes the widget
        # click-through so the user can still click anything beneath it.
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        self._dot = QtWidgets.QLabel("\u25cf")
        self._dot.setStyleSheet("color: #dc3545; font-size: 12px;")
        layout.addWidget(self._dot)
        self._label = QtWidgets.QLabel("")
        self._label.setStyleSheet("color: white; font-size: 12px; font-weight: bold;")
        layout.addWidget(self._label)
        self.setLayout(layout)
        self.setStyleSheet(
            "ObserverIndicator { background-color: rgba(0, 0, 0, 180); border-radius: 6px; }"
        )

        self._reposition()

        self._state_sig.connect(self._apply_state)
        self._tick_sig.connect(self._apply_tick)
        self._event_bus.subscribe(ObserverSessionStartedEvent, self._on_started)
        self._event_bus.subscribe(ObserverSessionEndedEvent, self._on_ended)
        self._event_bus.subscribe(ObserverPausedEvent, self._on_paused)

        # 1 s elapsed timer \u2014 the badge is the at-a-glance reminder,
        # so 1 s granularity is fine. The tray tooltip uses a 10 s
        # timer to keep the menu lightweight.
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    def _reposition(self) -> None:
        """Place the badge in the top-left of the screen.

        The dictation overlay (``StatusOverlay``) lives in the
        top-right. Offsetting the Observer indicator to the left
        prevents the two widgets from fighting for the same pixels.
        """
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        self.setGeometry(geometry.left() + 20, geometry.top() + 20, 180, 28)

    def _on_started(self, event: object) -> None:
        self._session_started_monotonic = time.monotonic()
        self._state_sig.emit(False)  # recording
        if not self._timer.isActive():
            self._timer.start()
        self._tick_sig.emit(0)

    def _on_ended(self, event: object) -> None:
        self._state_sig.emit(False)  # not paused
        if self._timer.isActive():
            self._timer.stop()
        self._session_started_monotonic = 0.0
        # The badge is only visible while a session is active; hide
        # ourselves on session end. This is the **only** way the badge
        # gets hidden \u2014 do not add a close button.
        self.hide()

    def _on_paused(self, event: object) -> None:
        self._state_sig.emit(bool(getattr(event, "paused", False)))

    def _apply_state(self, paused: bool) -> None:
        if paused:
            self._dot.setStyleSheet("color: #ffc107; font-size: 12px;")
            self._label.setText("PAUSED")
        else:
            self._dot.setStyleSheet("color: #dc3545; font-size: 12px;")
            self._apply_tick(self._elapsed_ms())
        self.show()

    def _apply_tick(self, ms: int) -> None:
        self._label.setText(f"REC {_fmt_elapsed(ms)}")
        if not self.isVisible():
            self.show()

    def _tick(self) -> None:
        self._tick_sig.emit(self._elapsed_ms())

    def _elapsed_ms(self) -> int:
        if not self._session_started_monotonic:
            return 0
        return int((time.monotonic() - self._session_started_monotonic) * 1000)

    def stop(self) -> None:
        """Clean up subscriptions."""
        self._event_bus.unsubscribe(ObserverSessionStartedEvent, self._on_started)
        self._event_bus.unsubscribe(ObserverSessionEndedEvent, self._on_ended)
        self._event_bus.unsubscribe(ObserverPausedEvent, self._on_paused)
        if self._timer.isActive():
            self._timer.stop()
        self.close()
