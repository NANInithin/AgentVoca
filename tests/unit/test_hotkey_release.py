"""Push-to-talk: a hotkey registered with ``emit_on_release`` fires on release too."""

from __future__ import annotations

from pynput import keyboard

from agentvoca.app.hotkeys import HotkeyManager
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import HotkeyEvent


def _press_release(manager: HotkeyManager, keys: list) -> None:
    for key in keys:
        manager._pressed.add(key)
        for hk in manager._hotkeys:
            hk.press(key)
    for key in keys:
        for hk in manager._hotkeys:
            hk.release(key)
        manager._dispatch_release(key)


def _collect(bus: EventBus) -> list[str]:
    actions: list[str] = []
    bus.subscribe(HotkeyEvent, lambda e: actions.append(e.action))
    return actions


CTRL_SPACE = keyboard.HotKey.parse("<ctrl>+<space>")
SPACE = CTRL_SPACE[1]


def test_push_to_talk_emits_on_press_and_release() -> None:
    bus = EventBus()
    actions = _collect(bus)
    manager = HotkeyManager(bus)
    manager.register("ctrl+space", "toggle_recording", emit_on_release=True)

    _press_release(manager, CTRL_SPACE)

    assert actions == ["toggle_recording", "toggle_recording"]


def test_toggle_hotkey_emits_only_on_press() -> None:
    bus = EventBus()
    actions = _collect(bus)
    manager = HotkeyManager(bus)
    manager.register("ctrl+space", "toggle_recording")

    _press_release(manager, CTRL_SPACE)

    assert actions == ["toggle_recording"]


def test_release_without_activation_is_ignored() -> None:
    bus = EventBus()
    actions = _collect(bus)
    manager = HotkeyManager(bus)
    manager.register("ctrl+space", "toggle_recording", emit_on_release=True)

    for hk in manager._hotkeys:
        hk.press(SPACE)
        hk.release(SPACE)
    manager._dispatch_release(SPACE)

    assert actions == []


def test_unregister_all_clears_release_bindings() -> None:
    bus = EventBus()
    actions = _collect(bus)
    manager = HotkeyManager(bus)
    manager.register("ctrl+space", "toggle_recording", emit_on_release=True)
    manager.unregister_all()

    manager._dispatch_release(SPACE)

    assert actions == []


def test_deferred_hotkey_waits_until_all_keys_are_up() -> None:
    bus = EventBus()
    actions = _collect(bus)
    manager = HotkeyManager(bus)
    manager.register("ctrl+alt+i", "insert_last", defer_until_released=True)
    keys = keyboard.HotKey.parse("<ctrl>+<alt>+i")

    for key in keys:
        manager._pressed.add(key)
        for hk in manager._hotkeys:
            hk.press(key)
    assert actions == []

    manager._dispatch_release(keys[2])
    manager._dispatch_release(keys[0])
    assert actions == []
    manager._dispatch_release(keys[1])
    assert actions == ["insert_last"]
