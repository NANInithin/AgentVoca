"""Session compiler abstract base class and shared blocking algorithm (v0.4.0).

Track 3, OBS-20. Implements contracts \xa76 verbatim: the ``SessionCompiler`` ABC
and the ``split_blocks`` helper that BOTH compilers and the JSON exporter
call. The blocking function is shared so markdown and JSON can never disagree
about where blocks begin (contracts \xa75).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from agentvoca.config.schema import ObserverCompileConfig
from agentvoca.observer.models import CompiledSession, SessionBundle

if TYPE_CHECKING:  # pragma: no cover - type-only imports
    from agentvoca.observer.models import ObserverEvent

logger = logging.getLogger(__name__)

# A new block starts when more than this many milliseconds elapse between
# consecutive events within the same app (contracts \xa75).
_BLOCK_GAP_MS = 5 * 60 * 1000


class SessionCompiler(ABC):
    """Abstract base class for Observer session compilers.

    Args:
        config: The Observer compile configuration block.
    """

    def __init__(self, config: ObserverCompileConfig) -> None:
        self._config = config

    @abstractmethod
    async def compile(self, bundle: SessionBundle) -> CompiledSession:
        """Render a session into a ``CompiledSession``.

        MUST NOT raise. On any internal failure, the ABC contract says the
        compiler must degrade to the rules rendering for the affected block
        and set ``degraded=True``. A user who just recorded an hour of work
        must always get an artifact.

        Args:
            bundle: A whole session loaded by ``ObserverStore.load_bundle``.

        Returns:
            The compiled session.
        """

    async def shutdown(self) -> None:
        """Optional soft contract. Default no-op."""
        return None


def block_window(events: list["ObserverEvent"]) -> tuple[int, int]:
    """Return the ``(started_at_ms, ended_at_ms)`` window of a block.

    Empty block -> ``(0, 0)``. Otherwise the timestamps of the first and
    last events. Used by both compilers and the JSON exporter.
    """
    if not events:
        return (0, 0)
    return (events[0].ts_ms, events[-1].ts_ms)


def split_blocks(bundle: SessionBundle) -> list[list["ObserverEvent"]]:
    """Partition a session's events into blocks.

    A new block starts on a ``focus_change`` event, OR when more than
    ``_BLOCK_GAP_MS`` (5 minutes) elapse between consecutive events
    within the same app.

    ``pause_start`` / ``pause_end`` never open a block \u2014 they are recorded
    as gaps on the enclosing block, so a paused stretch does not
    fragment the narrative.

    Both compilers AND the JSON exporter call this one function, so
    markdown and JSON can never disagree about where blocks begin.

    Edge cases:
        * Empty session -> ``[]``.
        * First event not a ``focus_change`` -> one implicit block
          containing it (and any subsequent same-app events until a
          focus_change or a >5 min same-app gap).
        * Session of only ``pause_*`` events -> a single block.
    """
    events = bundle.events
    if not events:
        return []

    blocks: list[list["ObserverEvent"]] = []
    current: list["ObserverEvent"] = []

    for event in events:
        if not current:
            # Open an implicit block for the first event, whatever its
            # kind. ``focus_change`` is a normal event here \u2014 the rule
            # only applies AFTER the first event has been seen.
            current.append(event)
            continue

        prev = current[-1]
        opened_by_focus = event.kind == "focus_change"
        opened_by_gap = (
            event.app_name == prev.app_name and (event.ts_ms - prev.ts_ms) > _BLOCK_GAP_MS
        )
        if opened_by_focus or opened_by_gap:
            blocks.append(current)
            current = [event]
        else:
            current.append(event)

    if current:
        blocks.append(current)

    return blocks


__all__ = [
    "SessionCompiler",
    "block_window",
    "split_blocks",
]
