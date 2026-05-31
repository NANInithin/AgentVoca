"""System tray icon and menu for voice dictation.

Uses PySide6 to create a system tray with a state-aware icon. Subscribes to
``StateChangedEvent`` to update the icon and tooltip when the app state changes.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import StateChangedEvent

logger = logging.getLogger(__name__)

# ── State-to-icon mapping ──────────────────────────────────────────

# In v1, we use simple coloured circles. In production, these would be
# proper SVG icons. See PyInstaller docs for bundling icon files.
_STATE_ICONS: dict[str, tuple[int, int, int]] = {
    "idle": (100, 100, 100),  # grey
    "recording": (220, 50, 50),  # red
    "transcribing": (220, 180, 50),  # amber
    "cleaning": (220, 180, 50),  # amber
    "inserting": (50, 180, 50),  # green
    "error": (220, 50, 50),  # red
}

_TOOLTIPS: dict[str, str] = {
    "idle": "agentvoca — Ready",
    "recording": "agentvoca — Recording…",
    "transcribing": "agentvoca — Transcribing…",
    "cleaning": "agentvoca — Cleaning…",
    "inserting": "agentvoca — Inserting…",
    "error": "agentvoca — Error",
}


def _make_icon(r: int, g: int, b: int, size: int = 16) -> QtGui.QIcon:
    """Create a solid-colour circle icon.

    Args:
        r, g, b: RGB colour values (0-255).
        size: Icon size in pixels.

    Returns:
        A ``QIcon`` with a filled circle on a transparent background.
    """
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setBrush(QtGui.QColor(r, g, b))
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.end()
    return QtGui.QIcon(pixmap)


class TrayApp:
    """System tray icon with state-aware visual feedback.

    Args:
        event_bus: Shared event bus to subscribe to state changes.
        parent: Optional parent QWidget.
    """

    def __init__(
        self,
        event_bus: EventBus,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        self._event_bus = event_bus
        self._parent = parent

        # Build the tray icon
        self._tray = QtWidgets.QSystemTrayIcon(parent)
        self._tray.setToolTip("agentvoca — Ready")
        self._set_state_icon("idle")

        # Build the context menu
        self._menu = QtWidgets.QMenu()
        self._status_action = self._menu.addAction("Ready")
        self._status_action.setEnabled(False)
        self._menu.addSeparator()
        self._open_settings_action = self._menu.addAction("Settings…")
        self._quit_action = self._menu.addAction("Quit")
        self._tray.setContextMenu(self._menu)

        # Subscribe to state changes
        self._event_bus.subscribe(StateChangedEvent, self._on_state_changed)

        # Show the tray icon
        self._tray.show()

    def _set_state_icon(self, state: str) -> None:
        """Update the tray icon to reflect the given state."""
        rgb = _STATE_ICONS.get(state, (100, 100, 100))
        icon = _make_icon(*rgb)
        self._tray.setIcon(icon)

    def _on_state_changed(self, event: object) -> None:
        """Handle a ``StateChangedEvent`` to update icon and tooltip."""
        # event has .previous and .current attributes
        current = getattr(event, "current", "idle")
        tip = _TOOLTIPS.get(current, "agentvoca")
        self._tray.setToolTip(tip)
        self._status_action.setText(tip)
        self._set_state_icon(current)

    @property
    def open_settings_action(self) -> QtGui.QAction:
        """Action that triggers the settings window."""
        return self._open_settings_action

    @property
    def quit_action(self) -> QtGui.QAction:
        """Action that quits the application."""
        return self._quit_action

    def show_message(self, title: str, message: str, icon: int = 0) -> None:
        """Show a balloon notification from the tray.

        Args:
            title: Notification title.
            message: Notification body text.
            icon: ``QSystemTrayIcon.MessageIcon`` value (0=Info, 1=Warning, 2=Critical).
        """
        self._tray.showMessage(
            title,
            message,
            QtWidgets.QSystemTrayIcon.MessageIcon(icon),
            3000,
        )

    def stop(self) -> None:
        """Clean up tray resources."""
        self._event_bus.unsubscribe(StateChangedEvent, self._on_state_changed)
        self._tray.hide()
