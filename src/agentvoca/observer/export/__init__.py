"""Observer session exporters (v0.4.0, Track 3, OBS-24).

Built-ins: ``MarkdownExporter`` and ``JsonExporter``. Constructed
with a ``SessionBundle`` and an output directory; the
``ObserverController`` calls ``await exporter.export(compiled)`` and
expects the file path back. The factory ``make_exporters`` builds
the list from the configured ``compile.formats``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from agentvoca.observer.export.base import Exporter, atomic_write_text  # re-exported
from agentvoca.observer.export.json_sidecar import JsonExporter
from agentvoca.observer.export.markdown import MarkdownExporter
from agentvoca.observer.models import SessionBundle

__all__ = [
    "Exporter",
    "JsonExporter",
    "MarkdownExporter",
    "atomic_write_text",
    "make_exporters",
]


def make_exporters(bundle: SessionBundle, formats: list[str], out_dir: Path) -> list[Exporter]:
    """Construct the exporter list for ``formats`` and ``out_dir``.

    Skips ``formats`` entries it does not know. Used by ``main.py``
    when wiring ``attach_surface``.
    """
    log = logging.getLogger(__name__)
    exporters: list[Exporter] = []
    for fmt in formats:
        if fmt == "markdown":
            exporters.append(MarkdownExporter(bundle, out_dir))
        elif fmt == "json":
            exporters.append(JsonExporter(bundle, out_dir))
        else:
            log.warning("Unknown export format %r; skipping", fmt)
    return exporters
