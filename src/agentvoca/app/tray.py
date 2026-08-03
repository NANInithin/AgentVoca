"""System tray icon and menu for voice dictation.

Uses PySide6 to create a system tray with a state-aware icon. Subscribes to
``StateChangedEvent`` to update the icon and tooltip when the app state changes.

v0.4.0 adds Observer-mode states (recording / paused / idle / compiling) on
top of the dictation states. The existing dictation states are unchanged;
the new Observer submenu is appended to the same context menu.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import (
    ObserverCompiledEvent,
    ObserverPausedEvent,
    ObserverSessionEndedEvent,
    ObserverSessionStartedEvent,
    StateChangedEvent,
)

logger = logging.getLogger(__name__)

# ── State-to-icon mapping ──────────────────────────────────────────

# In v1, we use simple coloured circles. In production, these would be
# proper SVG icons. See PyInstaller docs for bundling icon files.
_DICTATION_STATE_ICONS: dict[str, tuple[int, int, int]] = {
    "idle": (100, 100, 100),  # grey
    "recording": (220, 50, 50),  # red
    "transcribing": (220, 180, 50),  # amber
    "cleaning": (220, 180, 50),  # amber
    "inserting": (50, 180, 50),  # green
    "error": (220, 50, 50),  # red
}

_DICTATION_TOOLTIPS: dict[str, str] = {
    "idle": "agentvoca \u2014 Ready",
    "recording": "agentvoca \u2014 Recording\u2026",
    "transcribing": "agentvoca \u2014 Transcribing\u2026",
    "cleaning": "agentvoca \u2014 Cleaning\u2026",
    "inserting": "agentvoca \u2014 Inserting\u2026",
    "error": "agentvoca \u2014 Error",
}

# Observer states, layered on top of the dictation states. When a session
# is active, the icon takes the observer colour; otherwise the dictation
# colour wins.
_OBSERVER_STATE_ICONS: dict[str, tuple[int, int, int]] = {
    "recording": (200, 30, 30),  # red \u2014 session in progress
    "paused": (220, 180, 50),  # amber \u2014 paused
    "idle": (100, 100, 100),  # grey \u2014 no session
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


def _fmt_elapsed(ms: int) -> str:
    """Format an elapsed-ms value as ``H:MM:SS`` (zero-padded)."""
    if ms < 0:
        ms = 0
    total = ms // 1000
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


class TrayApp(QtCore.QObject):
    """System tray icon with state-aware visual feedback.

    Subclasses ``QObject`` so it can use signals to marshal updates from
    worker threads (the persistent asyncio loop, the audio callback) onto the
    GUI thread \u2014 Qt widgets must only be touched there.

    Args:
        event_bus: Shared event bus to subscribe to state changes.
        parent: Optional parent QWidget.
    """

    # Signals marshal updates onto the GUI thread.
    _state_sig = QtCore.Signal(str)
    _message_sig = QtCore.Signal(str, str, int)
    _observer_state_sig = QtCore.Signal(str)  # "recording" | "paused" | "idle"
    _observer_elapsed_sig = QtCore.Signal(str)  # formatted elapsed
    _observer_menu_sig = QtCore.Signal(str, str)  # message title, body (compile notification)

    def __init__(
        self,
        event_bus: EventBus,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__()
        self._event_bus = event_bus
        self._parent = parent

        # Build the tray icon
        self._tray = QtWidgets.QSystemTrayIcon(parent)
        self._tray.setToolTip("agentvoca \u2014 Ready")
        self._set_state_icon("idle")

        # Build the context menu
        self._menu = QtWidgets.QMenu()
        self._status_action = self._menu.addAction("Ready")
        self._status_action.setEnabled(False)
        self._menu.addSeparator()
        self._open_settings_action = self._menu.addAction("Settings\u2026")
        self._open_wizard_action = self._menu.addAction("Setup Wizard\u2026")
        # v0.4.0: Observer submenu. Actions are wired to signals the
        # controller subscribes to (or the actions are no-ops if the
        # controller is not attached).
        # Disabled until ``set_observer_available(True)`` is called. The
        # host only enables Observer when ``observer.enabled`` is set AND
        # the controller was built, so a greyed-out menu is the honest
        # state rather than a live-looking item that silently does nothing.
        self._observer_menu = self._menu.addMenu("Observer (disabled)")
        self._observer_menu.setEnabled(False)
        self._observer_available = False
        self._toggle_session_action = self._observer_menu.addAction("Start session")
        self._toggle_session_action.triggered.connect(
            lambda: self._emit_observer_action("toggle_session")
        )
        self._pause_action = self._observer_menu.addAction("Pause")
        self._pause_action.setEnabled(False)
        self._pause_action.triggered.connect(lambda: self._emit_observer_action("toggle_pause"))
        self._open_last_action = self._observer_menu.addAction("Open last session\u2026")
        self._open_last_action.triggered.connect(lambda: self._emit_observer_action("open_last"))
        self._delete_all_action = self._observer_menu.addAction("Delete all sessions\u2026")
        self._delete_all_action.triggered.connect(lambda: self._emit_observer_action("delete_all"))
        self._quit_action = self._menu.addAction("Quit")
        self._tray.setContextMenu(self._menu)

        # Connect thread-marshalling signals to GUI-thread slots.
        self._state_sig.connect(self._apply_state)
        self._message_sig.connect(self._apply_message)
        self._observer_state_sig.connect(self._apply_observer_state)
        self._observer_elapsed_sig.connect(self._apply_observer_elapsed)
        self._observer_menu_sig.connect(self._apply_observer_menu_notification)

        # Subscribe to state changes (handler may run on a worker thread)
        self._event_bus.subscribe(StateChangedEvent, self._on_state_changed)

        # v0.4.0: subscribe to observer events. The handlers route the
        # updates through signals so the GUI thread does the actual work.
        self._event_bus.subscribe(ObserverSessionStartedEvent, self._on_observer_started)
        self._event_bus.subscribe(ObserverSessionEndedEvent, self._on_observer_ended)
        self._event_bus.subscribe(ObserverPausedEvent, self._on_observer_paused)
        self._event_bus.subscribe(ObserverCompiledEvent, self._on_observer_compiled)

        # Elapsed-time timer: 10 s. Updating the tooltip every 1 s for
        # an hours-long session wastes CPU; the user only needs ~10 s
        # granularity to confirm "yes, it's still running".
        self._elapsed_timer = QtCore.QTimer(self)
        self._elapsed_timer.setInterval(10_000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._observer_state: str = "idle"
        self._session_started_monotonic: float = 0.0

        # Show the tray icon
        self._tray.show()

    def _set_state_icon(self, state: str) -> None:
        """Update the tray icon to reflect the given dictation state."""
        rgb = _DICTATION_STATE_ICONS.get(state, (100, 100, 100))
        icon = _make_icon(*rgb)
        self._tray.setIcon(icon)

    def _on_state_changed(self, event: object) -> None:
        """Emit the state change onto the GUI thread."""
        self._state_sig.emit(getattr(event, "current", "idle"))

    def _apply_state(self, current: str) -> None:
        """Update icon and tooltip for the given state (GUI thread)."""
        tip = _DICTATION_TOOLTIPS.get(current, "agentvoca")
        self._tray.setToolTip(tip)
        self._status_action.setText(tip)
        self._set_state_icon(current)

    @property
    def open_settings_action(self) -> QtGui.QAction:
        """Action that triggers the settings window."""
        return self._open_settings_action

    @property
    def open_wizard_action(self) -> QtGui.QAction:
        """Action that triggers the setup wizard."""
        return self._open_wizard_action

    @property
    def quit_action(self) -> QtGui.QAction:
        """Action that quits the application."""
        return self._quit_action

    @property
    def toggle_session_action(self) -> QtGui.QAction:
        """Action that toggles an Observer session (start if none, stop otherwise)."""
        return self._toggle_session_action

    @property
    def pause_action(self) -> QtGui.QAction:
        """Action that toggles the pause state of the active Observer session."""
        return self._pause_action

    @property
    def open_last_action(self) -> QtGui.QAction:
        """Action that opens the most recent Observer session's output folder."""
        return self._open_last_action

    @property
    def delete_all_action(self) -> QtGui.QAction:
        """Action that triggers the "delete all sessions" purge."""
        return self._delete_all_action

    def show_message(self, title: str, message: str, icon: int = 0) -> None:
        """Show a balloon notification from the tray.

        Safe to call from any thread; the balloon is shown on the GUI thread.

        Args:
            title: Notification title.
            message: Notification body text.
            icon: ``QSystemTrayIcon.MessageIcon`` value (0=Info, 1=Warning, 2=Critical).
        """
        self._message_sig.emit(title, message, icon)

    def _apply_message(self, title: str, message: str, icon: int) -> None:
        """Show a balloon notification (GUI thread)."""
        self._tray.showMessage(
            title,
            message,
            QtWidgets.QSystemTrayIcon.MessageIcon(icon),
            3000,
        )

    def stop(self) -> None:
        """Clean up tray resources."""
        self._event_bus.unsubscribe(StateChangedEvent, self._on_state_changed)
        self._event_bus.unsubscribe(ObserverSessionStartedEvent, self._on_observer_started)
        self._event_bus.unsubscribe(ObserverSessionEndedEvent, self._on_observer_ended)
        self._event_bus.unsubscribe(ObserverPausedEvent, self._on_observer_paused)
        self._event_bus.unsubscribe(ObserverCompiledEvent, self._on_observer_compiled)
        if self._elapsed_timer.isActive():
            self._elapsed_timer.stop()
        self._tray.hide()

    # ── v0.4.0 Observer ───────────────────────────────────────────

    def set_observer_available(self, available: bool, reason: str = "") -> None:
        """Enable or disable the Observer submenu.

        Called by ``main.py`` once it knows whether an ``ObserverController``
        exists. When Observer is off in config, or its construction failed,
        the submenu is greyed out and its title says so — previously the
        menu looked live but every click was swallowed by a ``None`` check
        in the hotkey handler, so nothing happened and nothing was logged
        above DEBUG.

        Args:
            available: True when a controller is wired and usable.
            reason: Short text appended to the menu title when unavailable,
                e.g. "enable in Settings".
        """
        self._observer_available = available
        self._observer_menu.setEnabled(available)
        if available:
            self._observer_menu.setTitle("Observer")
        else:
            suffix = reason or "disabled"
            self._observer_menu.setTitle(f"Observer ({suffix})")

    def _emit_observer_action(self, action: str) -> None:
        """Forward a tray Observer submenu action to subscribed listeners.

        The host (``main.py``) wires the action names to the
        ``ObserverController`` after construction. Until then the
        actions are visible but their handler is a no-op.
        """
        # Log only; ``controller`` is owned by main.py and reaches us
        # through the event bus, not a direct reference. The action
        # names mirror the public methods on ``ObserverController``
        # (``toggle_session``, ``pause`` / ``resume``).
        logger.debug("Tray Observer menu action: %s", action)
        # Best-effort: dispatch via a generic event so the host can
        # route it without coupling the tray to the controller.
        from agentvoca.core.events import HotkeyEvent  # noqa: PLC0415

        if action == "toggle_session":
            self._event_bus.publish(HotkeyEvent(action="toggle_observer"))
        elif action == "toggle_pause":
            self._event_bus.publish(HotkeyEvent(action="pause_observer"))
        # open_last / delete_all have no hotkey equivalent; main.py
        # listens for them by other means (e.g. directly via
        # ``TrayApp.toggle_session_action`` etc.). The signal here is
        # informational so a future wiring step does not need a
        # separate event.

    def _on_observer_started(self, event: object) -> None:
        self._observer_state_sig.emit("recording")
        self._observer_elapsed_sig.emit(_fmt_elapsed(0))
        self._session_started_monotonic = time.monotonic()
        self._elapsed_timer.start()

    def _on_observer_ended(self, event: object) -> None:
        self._observer_state_sig.emit("idle")
        if self._elapsed_timer.isActive():
            self._elapsed_timer.stop()

    def _on_observer_paused(self, event: object) -> None:
        paused = bool(getattr(event, "paused", False))
        self._observer_state_sig.emit("paused" if paused else "recording")

    def _on_observer_compiled(self, event: object) -> None:
        title = "Observer session compiled"
        md_path = getattr(event, "markdown_path", "") or ""
        degraded = bool(getattr(event, "degraded", False))
        if degraded:
            body = "Some blocks used rules rendering. Output: " + (md_path or "(no output)")
        else:
            body = "Output: " + (md_path or "(no output)")
        self._observer_menu_sig.emit(title, body)
        # Also a balloon so the user notices even when the menu is closed.
        self._message_sig.emit(title, body, 0)

    def _apply_observer_state(self, state: str) -> None:
        """Switch the tray icon colour and label for the new state.

        Recording sessions use red, paused uses amber, idle is grey.
        The action labels flip so the menu reflects the current state
        (``Start`` when no session, ``Stop`` when one is active;
        ``Pause`` / ``Resume`` likewise).
        """
        self._observer_state = state
        rgb = _OBSERVER_STATE_ICONS.get(state, _OBSERVER_STATE_ICONS["idle"])
        self._tray.setIcon(_make_icon(*rgb))
        if state == "recording":
            self._toggle_session_action.setText("Stop session")
            self._pause_action.setText("Pause")
            self._pause_action.setEnabled(True)
            self._status_action.setText("Observer \u2014 recording")
            self._tray.setToolTip("agentvoca \u2014 Observer recording")
        elif state == "paused":
            self._toggle_session_action.setText("Stop session")
            self._pause_action.setText("Resume")
            self._pause_action.setEnabled(True)
            self._status_action.setText("Observer \u2014 paused")
            self._tray.setToolTip("agentvoca \u2014 Observer paused")
        else:  # idle
            self._toggle_session_action.setText("Start session")
            self._pause_action.setText("Pause")
            self._pause_action.setEnabled(False)
            self._status_action.setText("Ready")
            self._tray.setToolTip("agentvoca \u2014 Ready")

    def _apply_observer_elapsed(self, text: str) -> None:
        """Update the tooltip with the formatted elapsed time."""
        if self._observer_state == "recording":
            self._tray.setToolTip(f"agentvoca \u2014 Observer recording ({text})")
        elif self._observer_state == "paused":
            self._tray.setToolTip(f"agentvoca \u2014 Observer paused ({text})")

    def _tick_elapsed(self) -> None:
        """Recompute and display the elapsed time on the 10 s timer."""
        if not self._session_started_monotonic:
            return
        elapsed_ms = int((time.monotonic() - self._session_started_monotonic) * 1000)
        self._observer_elapsed_sig.emit(_fmt_elapsed(elapsed_ms))

    def _apply_observer_menu_notification(self, title: str, body: str) -> None:
        """Update the menu status line when a session is compiled."""
        self._status_action.setText(title)
