"""Global hotkey binding for voice dictation.

Uses pynput to register global hotkeys and emits ``HotkeyEvent`` on the
shared event bus when a hotkey is pressed.
"""

from __future__ import annotations

import logging
from typing import Optional

from pynput import keyboard

from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import HotkeyEvent

logger = logging.getLogger(__name__)


def _parse_hotkey(hotkey_str: str) -> set[keyboard.Key | keyboard.KeyCode]:
    """Parse a hotkey string into a set of pynput key objects.

    Supports modifiers (ctrl, alt, shift, cmd, win) and a final key.
    Examples::
        "ctrl+space"     -> {Key.ctrl, Key.space}
        "ctrl+alt+comma" -> {Key.ctrl, Key.alt, KeyCode.from_char(',')}
        "escape"         -> {Key.esc}
    """
    parts = hotkey_str.lower().split("+")
    keys: set[keyboard.Key | keyboard.KeyCode] = set()

    # Modifier mapping
    modifier_map = {
        "ctrl": keyboard.Key.ctrl,
        "alt": keyboard.Key.alt,
        "shift": keyboard.Key.shift,
        "cmd": keyboard.Key.cmd,
        "win": keyboard.Key.cmd,
    }

    # Final key mapping (common special keys)
    special_map = {
        "escape": keyboard.Key.esc,
        "space": keyboard.Key.space,
        "comma": keyboard.KeyCode.from_char(","),
        "period": keyboard.KeyCode.from_char("."),
        "slash": keyboard.KeyCode.from_char("/"),
        "backslash": keyboard.KeyCode.from_char("\\"),
        "tab": keyboard.Key.tab,
        "enter": keyboard.Key.enter,
        "backspace": keyboard.Key.backspace,
        "delete": keyboard.Key.delete,
        "home": keyboard.Key.home,
        "end": keyboard.Key.end,
        "left": keyboard.Key.left,
        "right": keyboard.Key.right,
        "up": keyboard.Key.up,
        "down": keyboard.Key.down,
    }

    for i, part in enumerate(parts):
        if part in modifier_map:
            keys.add(modifier_map[part])
        elif part in special_map:
            keys.add(special_map[part])
        elif part.startswith("f") and part[1:].isdigit():
            # F1-F24
            fid = int(part[1:])
            if 1 <= fid <= 24:
                keys.add(getattr(keyboard.Key, f"f{fid}"))
        elif len(part) == 1:
            keys.add(keyboard.KeyCode.from_char(part))
        else:
            logger.warning("Unknown hotkey part: %s", part)

    return keys


class HotkeyManager:
    """Manages global hotkey registration and dispatch.

    Args:
        event_bus: Shared event bus to publish ``HotkeyEvent`` on.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._listener: Optional[keyboard.Listener] = None
        self._hotkey_handlers: dict[frozenset, str] = {}

    def register(
        self,
        hotkey_str: str,
        action: str,
    ) -> None:
        """Register a hotkey to emit a specific action.

        Args:
            hotkey_str: Hotkey combination string (e.g., ``"ctrl+space"``).
            action: The ``HotkeyEvent.action`` value to emit.

        The action must be one of: ``"toggle_recording"``, ``"cancel"``,
        ``"open_settings"``, ``"insert_last"``.
        """
        keys = _parse_hotkey(hotkey_str)
        self._hotkey_handlers[frozenset(keys)] = action
        logger.debug("Registered hotkey: %s -> %s (keys=%s)", hotkey_str, action, keys)

    def start(self) -> None:
        """Start the global hotkey listener."""
        if self._listener is not None:
            logger.warning("Hotkey listener already started")
            return

        # pynput fires Key.ctrl_l / Key.ctrl_r on actual key presses, but
        # _parse_hotkey stores the generic Key.ctrl / Key.alt / Key.shift.
        # Normalize left/right variants so the subset check works correctly.
        _MODIFIER_NORMALIZE: dict[keyboard.Key, keyboard.Key] = {
            keyboard.Key.ctrl_l: keyboard.Key.ctrl,
            keyboard.Key.ctrl_r: keyboard.Key.ctrl,
            keyboard.Key.alt_l: keyboard.Key.alt,
            keyboard.Key.alt_r: keyboard.Key.alt,
            keyboard.Key.shift_l: keyboard.Key.shift,
            keyboard.Key.shift_r: keyboard.Key.shift,
            keyboard.Key.cmd_l: keyboard.Key.cmd,
            keyboard.Key.cmd_r: keyboard.Key.cmd,
        }

        def _normalize(key: keyboard.Key | keyboard.KeyCode) -> keyboard.Key | keyboard.KeyCode:
            return _MODIFIER_NORMALIZE.get(key, key)  # type: ignore[arg-type]

        current_pressed: set[keyboard.Key | keyboard.KeyCode] = set()

        def on_press(key: keyboard.Key | keyboard.KeyCode | None) -> None:
            if key is None:
                return
            current_pressed.add(_normalize(key))

            # Check if current pressed keys match any registered hotkey
            for hotkey_set, action in self._hotkey_handlers.items():
                if hotkey_set.issubset(current_pressed):
                    logger.info("Hotkey triggered: %s", action)
                    # Clear before publishing — the publish may block the pynput
                    # thread for seconds (ASR pipeline), so key-release events
                    # would never fire and stale keys would remain in the set,
                    # causing any subsequent keypress to re-trigger the hotkey.
                    current_pressed.clear()
                    self._event_bus.publish(HotkeyEvent(action=action))  # type: ignore[arg-type]
                    break

        def on_release(key: keyboard.Key | keyboard.KeyCode | None) -> None:
            if key is None:
                return
            current_pressed.discard(_normalize(key))

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()
        logger.info("Hotkey listener started")

    def stop(self) -> None:
        """Stop the global hotkey listener."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
            logger.info("Hotkey listener stopped")
