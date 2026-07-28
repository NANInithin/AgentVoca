"""Privacy exclusion matching for Observer mode (v0.4.0, Track 3, OBS-25).

Decides whether the current foreground context must not be captured.
When the foreground app or window title matches a configured pattern,
Observer pauses and records a ``pause_start`` / ``pause_end`` pair \u2014
no keyframe, no OCR, no selection. Ambient audio is also suspended
(parent doc \xa77.3).

Patterns are case-insensitive globs matched via ``fnmatch``, the
same approach ``context.profiles.ProfileResolver`` uses for app
names. ``None`` app or title never matches: an unknown app is not
automatically private.
"""

from __future__ import annotations

import fnmatch
import logging
import re
from typing import Iterable, Optional, Pattern

from agentvoca.config.schema import ObserverPrivacyConfig

logger = logging.getLogger(__name__)


class ExclusionMatcher:
    """Decides whether the current foreground context must not be captured.

    Args:
        config: The Observer privacy configuration block.

    Case-insensitive glob matching via ``fnmatch`` so a pattern like
    ``"1Password.exe"`` also matches ``"1PASSWORD.EXE"`` on Windows
    (exe names are case-insensitive in the OS).

    The class is constructed once and queried at the foreground-poll
    rate (2 Hz). Both pattern lists are precompiled in ``__init__``
    to keep the hot path cheap; see ``is_excluded``.
    """

    def __init__(self, config: ObserverPrivacyConfig) -> None:
        self._app_patterns = self._precompile(config.exclude_apps)
        self._title_patterns = self._precompile(config.exclude_title_patterns)

    @staticmethod
    def _precompile(patterns: Iterable[str]) -> list[tuple[str, Pattern[str]]]:
        """Compile a list of glob patterns into a list of (literal, regex) pairs.

        ``fnmatch.translate`` returns a string regex; we compile it
        once per pattern. The haystack is lowercased at match time
        so a pattern written in any case still matches.
        """
        out: list[tuple[str, Pattern[str]]] = []
        for raw in patterns:
            if not raw or not raw.strip():
                continue
            out.append((raw, re.compile(fnmatch.translate(raw.lower()))))
        return out

    @property
    def app_patterns(self) -> list[str]:
        """The original ``exclude_apps`` patterns (post-filter of blanks)."""
        return [p for p, _ in self._app_patterns]

    @property
    def title_patterns(self) -> list[str]:
        """The original ``exclude_title_patterns`` (post-filter of blanks)."""
        return [p for p, _ in self._title_patterns]

    def is_excluded(
        self, app_name: Optional[str], window_title: Optional[str]
    ) -> tuple[bool, Optional[str]]:
        """Return ``(excluded, matched_pattern)``.

        A match in either list excludes. The first match wins so
        ``pause_start`` can record the pattern that fired. App matches
        are tested first, then titles \u2014 order does not affect the
        boolean result, only the reported pattern.

        Args:
            app_name: Foreground executable name, or None.
            window_title: Foreground window title, or None.

        Returns:
            ``(True, "1Password.exe")`` if excluded, else
            ``(False, None)``. A ``None`` app or title never matches.
        """
        if app_name:
            lowered = app_name.lower()
            for pattern, regex in self._app_patterns:
                if regex.match(lowered):
                    return True, pattern
        if window_title:
            lowered = window_title.lower()
            for pattern, regex in self._title_patterns:
                if regex.match(lowered):
                    return True, pattern
        return False, None


__all__ = ["ExclusionMatcher"]
