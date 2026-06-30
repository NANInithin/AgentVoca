"""Hotkey preset catalogue.

Per the v0.3.5 UI decision, the hotkey fields expose a dropdown of curated
presets instead of a free-form capture field. ``(disabled)`` is included so
users can opt out of any hotkey (including the previously required ones).

The presets round-trip cleanly through ``HotkeyManager._to_pynput_str`` (see
``app/hotkeys.py``) and through the schema's hotkey regex.
"""

from __future__ import annotations

from dataclasses import dataclass

# Sentinel value used by the UI to indicate "no hotkey bound". Stored on disk
# as ``None`` in the YAML config, matching the existing schema.
DISABLED = None

# Sentinel value used by the UI to indicate a user-typed free-form hotkey.
# Stored as the literal string the user typed. Kept distinct from DISABLED so
# the wizard can offer "Advanced…" for power users without cluttering the
# default dropdown.
CUSTOM = "__custom__"


@dataclass(frozen=True)
class HotkeyPreset:
    """A single entry in the hotkey dropdown.

    Attributes:
        value: The string written into the YAML config (or ``None`` for
            DISABLED).
        label: Human-readable label shown in the dropdown.
        warning: Optional warning shown next to the dropdown when this preset
            is selected (e.g. "Ctrl+Space is widely used").
    """

    value: str | None
    label: str
    warning: str | None = None


# Order matters — these are the entries shown in the dropdown, top to bottom.
PRESETS: tuple[HotkeyPreset, ...] = (
    HotkeyPreset(DISABLED, "(disabled)"),
    HotkeyPreset("ctrl+space", "Ctrl+Space", "Widely used — may conflict with IME toggles"),
    HotkeyPreset("ctrl+shift+space", "Ctrl+Shift+Space"),
    HotkeyPreset("ctrl+alt+space", "Ctrl+Alt+Space"),
    HotkeyPreset("ctrl+enter", "Ctrl+Enter"),
    HotkeyPreset("ctrl+shift+enter", "Ctrl+Shift+Enter"),
    HotkeyPreset("ctrl+shift+z", "Ctrl+Shift+Z", "Recommended on Windows (NVIDIA capture)"),
    HotkeyPreset("ctrl+shift+y", "Ctrl+Shift+Y"),
    HotkeyPreset("ctrl+alt+z", "Ctrl+Alt+Z", "Captured by NVIDIA drivers on most systems"),
    HotkeyPreset("ctrl+alt+y", "Ctrl+Alt+Y"),
    HotkeyPreset("ctrl+grave", "Ctrl+`"),
    HotkeyPreset("ctrl+shift+s", "Ctrl+Shift+S", "May conflict with screen capture"),
    HotkeyPreset("ctrl+shift+k", "Ctrl+Shift+K"),
    HotkeyPreset("ctrl+1", "Ctrl+1"),
    HotkeyPreset("ctrl+2", "Ctrl+2"),
    HotkeyPreset("ctrl+3", "Ctrl+3"),
    HotkeyPreset("ctrl+4", "Ctrl+4"),
    HotkeyPreset("f8", "F8"),
    HotkeyPreset("f9", "F9"),
    HotkeyPreset("f10", "F10"),
    HotkeyPreset("f11", "F11"),
    HotkeyPreset("f12", "F12"),
    HotkeyPreset("capslock", "CapsLock"),
    HotkeyPreset("pause", "Pause"),
    HotkeyPreset("insert", "Insert"),
    HotkeyPreset("home", "Home"),
    HotkeyPreset("end", "End"),
    HotkeyPreset("escape", "Escape"),
    HotkeyPreset("ctrl+alt+comma", "Ctrl+Alt+, (default Settings)"),
)


def find_preset(value: str | None) -> HotkeyPreset | None:
    """Return the preset matching ``value``, or None if it is a custom hotkey.

    A custom hotkey is anything not in the catalogue (including the empty
    string). The wizard uses this to decide whether to show the "(custom)"
    option as selected.
    """
    for preset in PRESETS:
        if preset.value == value:
            return preset
    return None


def labels_for_dropdown() -> list[str]:
    """Return the dropdown labels in declaration order.

    The user-visible label is what the wizard binds to the combo box. The
    matching ``HotkeyPreset.value`` is stored back into the config.
    """
    return [p.label for p in PRESETS]


def value_for_label(label: str) -> str | None:
    """Return the config value for a dropdown label, or ``CUSTOM`` sentinel.

    Returns ``CUSTOM`` (``"__custom__"``) when ``label`` does not match any
    preset so the wizard can render a text field for free-form entry.
    """
    for preset in PRESETS:
        if preset.label == label:
            return preset.value
    return CUSTOM


def warning_for(value: str | None) -> str | None:
    """Return the warning string for ``value``, or None if it has none."""
    preset = find_preset(value)
    return preset.warning if preset else None


# ── Action metadata ───────────────────────────────────────────────────
# The wizard's Hotkeys page shows one row per action. ``ALL_ACTIONS`` lists
# the actions exposed in the dropdown, in the order they should appear.


@dataclass(frozen=True)
class HotkeyAction:
    """A hotkey action exposed in the UI.

    Attributes:
        config_field: Dotted path into ``FullConfig`` (e.g. ``hotkeys.toggle_recording``).
        label: Friendly label shown to the user.
        description: One-line description of what the hotkey does.
        required: True if the action is always active (e.g. toggle_recording
            must remain bound or the app is unusable). When required, the
            dropdown still offers ``(disabled)`` but the wizard warns the user.
    """

    config_field: str
    label: str
    description: str
    required: bool = False


ALL_ACTIONS: tuple[HotkeyAction, ...] = (
    HotkeyAction(
        config_field="hotkeys.toggle_recording",
        label="Toggle recording",
        description="Start and stop dictation.",
        required=True,
    ),
    HotkeyAction(
        config_field="hotkeys.open_settings",
        label="Open Settings",
        description="Open the tabbed Settings window.",
    ),
    HotkeyAction(
        config_field="hotkeys.cancel",
        label="Cancel recording",
        description="Discard the current dictation without inserting.",
    ),
    HotkeyAction(
        config_field="hotkeys.undo",
        label="Undo last insertion",
        description="Remove the most recently inserted text.",
    ),
    HotkeyAction(
        config_field="hotkeys.insert_last_transcript",
        label="Insert last transcript",
        description="Re-insert the transcript from the previous dictation.",
    ),
    HotkeyAction(
        config_field="hotkeys.capture_screenshot",
        label="Capture screenshot (vision)",
        description="Snip a region mid-dictation; the vision model extracts its text.",
    ),
)


def action_by_field(field_path: str) -> HotkeyAction | None:
    """Return the action whose ``config_field`` matches ``field_path``."""
    for action in ALL_ACTIONS:
        if action.config_field == field_path:
            return action
    return None
