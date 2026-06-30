"""Controllers sub-package — logic shared between the wizard and settings window."""

from agentvoca.setup.controllers.device_probe import DeviceEntry, DeviceProbe
from agentvoca.setup.controllers.env_helper import (
    EnvStatus,
    all_snippets,
    bash_snippet,
    fish_snippet,
    powershell_snippet,
    set_for_session,
    snippet_for_current_platform,
    unset_for_session,
)
from agentvoca.setup.controllers.hotkey_presets import (
    ALL_ACTIONS,
    CUSTOM,
    DISABLED,
    PRESETS,
    HotkeyAction,
    HotkeyPreset,
    action_by_field,
    find_preset,
    labels_for_dropdown,
    value_for_label,
    warning_for,
)
from agentvoca.setup.controllers.restart_policy import (
    all_known_paths,
    is_hot_field,
    is_restart_field,
    partition,
)

__all__ = [
    "ALL_ACTIONS",
    "CUSTOM",
    "DISABLED",
    "DeviceEntry",
    "DeviceProbe",
    "EnvStatus",
    "HotkeyAction",
    "HotkeyPreset",
    "PRESETS",
    "action_by_field",
    "all_known_paths",
    "all_snippets",
    "bash_snippet",
    "find_preset",
    "fish_snippet",
    "is_hot_field",
    "is_restart_field",
    "labels_for_dropdown",
    "partition",
    "powershell_snippet",
    "set_for_session",
    "snippet_for_current_platform",
    "unset_for_session",
    "value_for_label",
    "warning_for",
]
