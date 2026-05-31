"""Minimal transparent status overlay showing recording state and interim transcript.

Uses PySide6 to create a small, always-on-top, frameless window that displays
the current app state and the latest transcript text. Subscribes to
``StateChangedEvent`` and ``TranscriptEvent`` to update the display.
"""

from __future__ import annotations

import logging

from PySide6 import QtCore, QtWidgets

from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import StateChangedEvent, TranscriptEvent

logger = logging.getLogger(__name__)

_STATE_LABELS: dict[str, str] = {
    "idle": "",
    "recording": "🎤 Recording…",
    "transcribing": "⏳ Transcribing…",
    "cleaning": "✨ Cleaning…",
    "inserting": "📝 Inserting…",
    "error": "⚠️ Error",
}


class StatusOverlay(QtWidgets.QWidget):
    """Minimal, always-on-top overlay showing dictation status.

    Args:
        event_bus: Shared event bus for subscribing to state/transcript
            events.
    """

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

        # Subscribe to events
        self._event_bus.subscribe(StateChangedEvent, self._on_state_changed)
        self._event_bus.subscribe(TranscriptEvent, self._on_transcript)

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
        """Update the state label when the app state changes."""
        current = getattr(event, "current", "idle")
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

    def _on_transcript(self, event: object) -> None:
        """Update the transcript display."""
        text = getattr(event, "text", "")
        if text:
            self._transcript_label.setText(text)
            self._transcript_label.show()

    def stop(self) -> None:
        """Clean up subscriptions."""
        self._event_bus.unsubscribe(StateChangedEvent, self._on_state_changed)
        self._event_bus.unsubscribe(TranscriptEvent, self._on_transcript)
        self.close()
