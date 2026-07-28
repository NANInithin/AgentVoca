"""Markdown exporter for Observer sessions (v0.4.0, Track 3, OBS-24).

Writes the compiled session's markdown to
``<out_dir>/<session-uuid>/session.md`` with atomic file replacement
so a crash mid-write cannot leave a truncated artifact.
"""

from __future__ import annotations

import logging
from pathlib import Path

from agentvoca.observer.export.base import atomic_write_text
from agentvoca.observer.models import CompiledSession, SessionBundle

logger = logging.getLogger(__name__)


class MarkdownExporter:
    """Write a compiled session's markdown to ``<out_dir>/<uuid>/session.md``."""

    name = "markdown"

    def __init__(self, bundle: SessionBundle, out_dir: Path) -> None:
        self._bundle = bundle
        self._out_dir = Path(out_dir)

    async def export(self, compiled: CompiledSession) -> str:
        """Write the compiled markdown and return its path.

        Args:
            compiled: The compiled session from a ``SessionCompiler``.

        Returns:
            The absolute path the markdown landed at.
        """
        target = self._path()
        atomic_write_text(target, compiled.markdown)
        logger.debug("MarkdownExporter wrote %s (%d bytes)", target, len(compiled.markdown))
        return str(target)

    def _path(self) -> Path:
        return self._out_dir / self._bundle.session.uuid / "session.md"


__all__ = ["MarkdownExporter"]
