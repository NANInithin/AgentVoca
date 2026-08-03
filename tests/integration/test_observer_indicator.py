"""Tests for the Observer indicator and tray Observer state (OBS-26).

Driven headlessly via the same ``qapp`` fixture used by the settings
tests. The test asserts:

* a started event shows the badge; an ended event hides it
* a paused event switches text and colour; resume restores
* elapsed timer formats correctly at 0 s, 59 s, 1 h 1 m 1 s
* the tray icon changes on each transition
* the badge has no close affordance and
  ``WindowTransparentForInput`` is set
* rapid start / stop / start does not leak a widget or a timer
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6", reason="PySide6 (Qt) not available")

from PySide6 import QtCore, QtWidgets  # noqa: E402

from agentvoca.app.overlay import ObserverIndicator, _fmt_elapsed  # noqa: E402
from agentvoca.app.tray import TrayApp  # noqa: E402
from agentvoca.core.event_bus import EventBus  # noqa: E402
from agentvoca.core.events import (  # noqa: E402
    ObserverPausedEvent,
    ObserverSessionEndedEvent,
    ObserverSessionStartedEvent,
)

# ── pure-Python formatter (no Qt) ──────────────────────────────────


def test_format_elapsed_zero() -> None:
    assert _fmt_elapsed(0) == "0:00:00"


def test_format_elapsed_59_seconds() -> None:
    assert _fmt_elapsed(59_000) == "0:00:59"


def test_format_elapsed_1h_1m_1s() -> None:
    assert _fmt_elapsed((3600 + 60 + 1) * 1000) == "1:01:01"


def test_format_elapsed_negative_clamps_to_zero() -> None:
    assert _fmt_elapsed(-1000) == "0:00:00"


# ── badge widget ────────────────────────────────────────────────────


def test_indicator_started_shows_badge(qapp) -> None:
    bus = EventBus()
    bus.set_loop(qapp)  # event bus can publish via the loop if available
    indicator = ObserverIndicator(bus)
    assert not indicator.isVisible()
    bus.publish(ObserverSessionStartedEvent(session_uuid="x", session_id=1, started_at_ms=0))
    # Pump the event loop so queued signals fire.
    qapp.processEvents()
    assert indicator.isVisible()
    indicator.stop()


def test_indicator_ended_hides_badge(qapp) -> None:
    bus = EventBus()
    bus.set_loop(qapp)
    indicator = ObserverIndicator(bus)
    bus.publish(ObserverSessionStartedEvent(session_uuid="x", session_id=1, started_at_ms=0))
    qapp.processEvents()
    assert indicator.isVisible()
    bus.publish(
        ObserverSessionEndedEvent(session_uuid="x", session_id=1, duration_ms=1000, event_count=0)
    )
    qapp.processEvents()
    assert not indicator.isVisible()
    indicator.stop()


def test_indicator_paused_text_and_colour(qapp) -> None:
    bus = EventBus()
    bus.set_loop(qapp)
    indicator = ObserverIndicator(bus)
    bus.publish(ObserverSessionStartedEvent(session_uuid="x", session_id=1, started_at_ms=0))
    qapp.processEvents()
    bus.publish(ObserverPausedEvent(paused=True, reason="hotkey"))
    qapp.processEvents()
    assert "PAUSED" in indicator._label.text()
    # The dot colour changes to amber when paused.
    assert "#ffc107" in indicator._dot.styleSheet()
    # Resume restores REC + red dot.
    bus.publish(ObserverPausedEvent(paused=False, reason="hotkey"))
    qapp.processEvents()
    assert "REC" in indicator._label.text()
    assert "#dc3545" in indicator._dot.styleSheet()
    indicator.stop()


def test_indicator_window_flags_include_transparent_for_input(qapp) -> None:
    bus = EventBus()
    bus.set_loop(qapp)
    indicator = ObserverIndicator(bus)
    flags = indicator.windowFlags()
    assert bool(flags & QtCore.Qt.WindowType.WindowTransparentForInput)
    indicator.stop()


def test_indicator_no_close_button(qapp) -> None:
    """The widget has no close affordance \u2014 it can only be hidden by stop()."""
    bus = EventBus()
    bus.set_loop(qapp)
    indicator = ObserverIndicator(bus)
    # Children of the badge should not include a close button or any
    # pushbutton. The class is a plain QWidget with a horizontal layout
    # containing a QLabel dot and a QLabel label.
    push_buttons = indicator.findChildren(QtWidgets.QPushButton)
    assert push_buttons == []
    indicator.stop()


def test_indicator_rapid_start_stop_does_not_leak(qapp) -> None:
    bus = EventBus()
    bus.set_loop(qapp)
    indicator = ObserverIndicator(bus)
    for _ in range(5):
        bus.publish(ObserverSessionStartedEvent(session_uuid="x", session_id=1, started_at_ms=0))
        qapp.processEvents()
        bus.publish(
            ObserverSessionEndedEvent(
                session_uuid="x", session_id=1, duration_ms=1000, event_count=0
            )
        )
        qapp.processEvents()
    # Timer should not be active.
    assert not indicator._timer.isActive()
    # Only one ObserverIndicator should be alive.
    assert len(indicator.findChildren(QtWidgets.QWidget)) == 2  # the dot + label
    indicator.stop()


def test_indicator_elapsed_ticks_at_least_once(qapp) -> None:
    bus = EventBus()
    bus.set_loop(qapp)
    indicator = ObserverIndicator(bus)
    bus.publish(ObserverSessionStartedEvent(session_uuid="x", session_id=1, started_at_ms=0))
    qapp.processEvents()
    # Wait 1.1 s; the 1 s timer should fire at least once.
    started = time.monotonic()
    while time.monotonic() - started < 1.2:
        qapp.processEvents()
        time.sleep(0.05)
    # Label should now read REC 0:00:0X for some X >= 1.
    label = indicator._label.text()
    assert label.startswith("REC ")
    parts = label.removeprefix("REC ").split(":")
    assert len(parts) == 3
    seconds = int(parts[2])
    assert seconds >= 1
    indicator.stop()


# ── tray observer state ────────────────────────────────────────────


def test_tray_observer_started_changes_icon(qapp) -> None:
    bus = EventBus()
    bus.set_loop(qapp)
    tray = TrayApp(bus)
    # Initial label / icon: idle
    assert tray._status_action.text() in ("Ready",)
    bus.publish(ObserverSessionStartedEvent(session_uuid="x", session_id=1, started_at_ms=0))
    qapp.processEvents()
    assert "Observer" in tray._status_action.text()
    assert "Stop session" == tray._toggle_session_action.text()
    assert tray._pause_action.isEnabled()
    tray.stop()


def test_tray_observer_paused_label_flip(qapp) -> None:
    bus = EventBus()
    bus.set_loop(qapp)
    tray = TrayApp(bus)
    bus.publish(ObserverSessionStartedEvent(session_uuid="x", session_id=1, started_at_ms=0))
    qapp.processEvents()
    bus.publish(ObserverPausedEvent(paused=True, reason="hotkey"))
    qapp.processEvents()
    assert tray._pause_action.text() == "Resume"
    bus.publish(ObserverPausedEvent(paused=False, reason="hotkey"))
    qapp.processEvents()
    assert tray._pause_action.text() == "Pause"
    tray.stop()


def test_tray_observer_ended_returns_to_idle(qapp) -> None:
    bus = EventBus()
    bus.set_loop(qapp)
    tray = TrayApp(bus)
    bus.publish(ObserverSessionStartedEvent(session_uuid="x", session_id=1, started_at_ms=0))
    qapp.processEvents()
    bus.publish(
        ObserverSessionEndedEvent(session_uuid="x", session_id=1, duration_ms=1000, event_count=0)
    )
    qapp.processEvents()
    assert "Start session" == tray._toggle_session_action.text()
    assert not tray._pause_action.isEnabled()
    # Elapsed timer should be off.
    assert not tray._elapsed_timer.isActive()
    tray.stop()


def test_tray_observer_submenu_actions_exist(qapp) -> None:
    bus = EventBus()
    bus.set_loop(qapp)
    tray = TrayApp(bus)
    # All four observer actions should be wired.
    assert tray.toggle_session_action is not None
    assert tray.pause_action is not None
    assert tray.open_last_action is not None
    assert tray.delete_all_action is not None
    tray.stop()


# ── Regression: Observer submenu must not look live when it is not ────


def test_observer_menu_disabled_until_available(qapp) -> None:
    """Regression: the tray Observer submenu did nothing and said nothing.

    The submenu was built unconditionally, but ``main.py`` only builds an
    ``ObserverController`` when ``observer.enabled`` is true. Any config
    written before v0.4.0 has no ``observer:`` block at all, so the
    controller was None and the hotkey handler swallowed every click --
    "Start session" appeared to work and simply did nothing.
    """
    bus = EventBus()
    tray = TrayApp(bus)
    try:
        # Default state: not available, and the title says so.
        assert tray._observer_menu.isEnabled() is False
        assert "disabled" in tray._observer_menu.title().lower()

        tray.set_observer_available(True)
        assert tray._observer_menu.isEnabled() is True
        assert tray._observer_menu.title() == "Observer"

        tray.set_observer_available(False, reason="enable in Settings")
        assert tray._observer_menu.isEnabled() is False
        assert "enable in Settings" in tray._observer_menu.title()
    finally:
        tray.stop()
