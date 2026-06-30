"""Backward-compat shim — the read-only settings window moved to ``setup``.

The v0.3.5 release moves the editable, tabbed settings window into
``agentvoca.setup.settings_window``. This module re-exports ``SettingsWindow``
so any third-party code that imported from ``agentvoca.app.settings`` keeps
working.

New code should import from ``agentvoca.setup.settings_window``.
"""

from agentvoca.setup.settings_window import SettingsWindow

__all__ = ["SettingsWindow"]
