"""Internal helpers for Observer exporters (v0.4.0, Track 3, OBS-24).

Atomic file writes, the exporter ``Protocol``, and the
``make_exporters`` factory. The concrete exporters live in
``markdown.py`` and ``json_sidecar.py``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol

from agentvoca.observer.models import CompiledSession, SessionBundle

logger = logging.getLogger(__name__)


class Exporter(Protocol):
    """Protocol for an Observer session exporter.

    An exporter is constructed with a bundle and output directory,
    then invoked with the compiled session when the user stops a
    recording. The return value is the path the artifact landed at,
    or a ``dict`` whose keys are paths.

    Attributes:
        name: ``"markdown"`` or ``"json"`` \u2014 used by the controller to
            pick which exporters to run from ``compile.formats``.
    """

    name: str

    def __init__(self, bundle: SessionBundle, out_dir: Path) -> None: ...

    async def export(self, compiled: CompiledSession) -> str | dict:
        """Write the artifact and return its path.

        The controller (``observer.controller.ObserverController``)
        calls this with just the ``CompiledSession``; the bundle and
        output directory were captured at construction time.
        """


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` atomically.

    A crash mid-write (process kill, power loss) cannot leave a
    truncated artifact at the public path because the write goes to
    ``path.with_suffix(path.suffix + ".tmp")`` first and is then
    renamed into place with ``os.replace`` (atomic on POSIX and
    Windows).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding=encoding, newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


__all__ = ["Exporter", "atomic_write_text"]
