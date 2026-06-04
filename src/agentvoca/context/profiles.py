"""App → style profile resolution.

Maps detected application names to cleanup style profiles using a
configurable mapping (``context.profiles``). Supports wildcard matching
with a standalone ``"*"`` pattern as the fallback.

Examples:
    ``{"Code.exe": "technical", "Terminal": "technical", "*": "standard"}``
"""

from __future__ import annotations

import fnmatch
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Valid style names that a profile can resolve to
_VALID_STYLES = {"raw", "light", "standard", "technical", "professional", "custom"}


class ProfileResolver:
    """Resolves an app name to a cleanup style profile.

    Args:
        profiles: A dict mapping app name patterns → style names.
            Patterns support ``fnmatch`` globbing (e.g. ``"Code*"``).
            The key ``"*"`` serves as the default/fallback when no
            other pattern matches.
    """

    def __init__(self, profiles: dict[str, str] | None = None) -> None:
        self._profiles = profiles or {}
        self._fallback: Optional[str] = None

        # Separate the fallback from the matchable patterns
        self._patterns: dict[str, str] = {}
        for pattern, style in self._profiles.items():
            if pattern == "*":
                self._fallback = style
            elif style in _VALID_STYLES:
                self._patterns[pattern] = style
            else:
                logger.warning("Ignoring profile '%s': unknown style '%s'", pattern, style)

    @property
    def mapping(self) -> dict[str, str]:
        """Return a copy of the raw mapping (profile name → style)."""
        return dict(self._profiles)

    def resolve(self, app_name: Optional[str]) -> Optional[str]:
        """Resolve an app name to a style profile.

        Args:
            app_name: The detected application name, or None.

        Returns:
            The resolved style name, or None to keep the global configured style.
        """
        if not app_name:
            return self._fallback

        # Try exact match first
        if app_name in self._patterns:
            return self._patterns[app_name]

        # Try fnmatch patterns (e.g. "Code*" matches "Code.exe")
        for pattern, style in self._patterns.items():
            if fnmatch.fnmatch(app_name, pattern):
                return style

        # Fallback to the wildcard default
        return self._fallback
