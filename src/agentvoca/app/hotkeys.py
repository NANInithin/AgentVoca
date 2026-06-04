"""Global hotkey binding for voice dictation.

Uses pynput.keyboard.HotKey (with listener.canonical for key normalisation)
to register global hotkeys and emit HotkeyEvent on the shared event bus.

Using HotKey + canonical is the correct pynput pattern for multi-key
combinations.  The hand-rolled set-matching approach has a Windows quirk
where Shift+letter keys arrive with char=None (only a virtual-key code),
so a stored KeyCode('z') never matched the fired KeyCode(vk=90, char=None).
"""

from __future__ import annotations

import logging
from typing import Optional

from pynput import keyboard

from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import HotkeyEvent

logger = logging.getLogger(__name__)

# ── Format conversion ────────────────────────────────────────────────

# Maps our config key names to pynput HotKey.parse() format.
_PYNPUT_MAP: dict[str, str] = {
    "ctrl": "<ctrl>",
    "alt": "<alt>",
    "shift": "<shift>",
    "cmd": "<cmd>",
    "win": "<cmd>",
    "escape": "<esc>",
    "space": "<space>",
    "comma": ",",
    "period": ".",
    "slash": "/",
    "backslash": "\\",
    "tab": "<tab>",
    "enter": "<enter>",
    "backspace": "<backspace>",
    "delete": "<delete>",
    "home": "<home>",
    "end": "<end>",
    "page_up": "<page_up>",
    "page_down": "<page_down>",
    "left": "<left>",
    "right": "<right>",
    "up": "<up>",
    "down": "<down>",
    "f1": "<f1>",
    "f2": "<f2>",
    "f3": "<f3>",
    "f4": "<f4>",
    "f5": "<f5>",
    "f6": "<f6>",
    "f7": "<f7>",
    "f8": "<f8>",
    "f9": "<f9>",
    "f10": "<f10>",
    "f11": "<f11>",
    "f12": "<f12>",
}


def _to_pynput_str(hotkey_str: str) -> str:
    """Convert our config format to pynput HotKey.parse() format.

    Examples::
        "ctrl+space"      -> "<ctrl>+<space>"
        "ctrl+shift+z"    -> "<ctrl>+<shift>+z"
        "ctrl+alt+comma"  -> "<ctrl>+<alt>+,"
        "escape"          -> "<esc>"
    """
    parts = hotkey_str.lower().split("+")
    result: list[str] = []
    for part in parts:
        if part in _PYNPUT_MAP:
            result.append(_PYNPUT_MAP[part])
        elif len(part) == 1:
            result.append(part)
        else:
            raise ValueError(f"Unknown hotkey part: {part!r} in {hotkey_str!r}")
    return "+".join(result)


# ── HotkeyManager ────────────────────────────────────────────────────


class HotkeyManager:
    """Manages global hotkey registration and dispatch.

    Args:
        event_bus: Shared event bus to publish HotkeyEvent on.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._listener: Optional[keyboard.Listener] = None
        self._hotkeys: list[keyboard.HotKey] = []

    def register(self, hotkey_str: str, action: str) -> None:
        """Register a hotkey to emit a specific action.

        Args:
            hotkey_str: Hotkey combination string (e.g. ``"ctrl+shift+z"``).
            action: The HotkeyEvent.action value to emit.
        """
        try:
            pynput_str = _to_pynput_str(hotkey_str)
        except ValueError as exc:
            logger.warning("Cannot register hotkey %r: %s", hotkey_str, exc)
            return

        # Capture action in the closure via a default-arg so each callback
        # holds its own copy.
        def on_activate(_action: str = action) -> None:
            logger.info("Hotkey triggered: %s", _action)
            self._event_bus.publish(HotkeyEvent(action=_action))  # type: ignore[arg-type]

        try:
            hk = keyboard.HotKey(keyboard.HotKey.parse(pynput_str), on_activate)
            self._hotkeys.append(hk)
            logger.debug("Registered hotkey: %s -> %s (pynput: %s)", hotkey_str, action, pynput_str)
        except Exception as exc:
            logger.warning("Failed to register hotkey %r: %s", hotkey_str, exc)

    def start(self) -> None:
        """Start the global hotkey listener."""
        if self._listener is not None:
            logger.warning("Hotkey listener already started")
            return

        # listener.canonical(key) is the correct pynput way to normalise keys
        # before passing them to HotKey.press / HotKey.release.  It handles:
        #   - Left/right modifier variants (ctrl_l -> ctrl)
        #   - Shift+letter on Windows (char=None, vk=90 -> canonical char 'z')
        #   - Dead-key combinations

        def on_press(key: keyboard.Key | keyboard.KeyCode | None) -> None:
            if key is None or self._listener is None:
                return
            canonical = self._listener.canonical(key)
            for hk in self._hotkeys:
                hk.press(canonical)

        def on_release(key: keyboard.Key | keyboard.KeyCode | None) -> None:
            if key is None or self._listener is None:
                return
            canonical = self._listener.canonical(key)
            for hk in self._hotkeys:
                hk.release(canonical)

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()
        logger.info("Hotkey listener started")

    def stop(self) -> None:
        """Stop the global hotkey listener."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
            logger.info("Hotkey listener stopped")
