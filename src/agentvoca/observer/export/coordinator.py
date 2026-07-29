"""Bundle-aware exporter coordinator (Track 3, OBS-28).

The concrete exporters (markdown / json sidecar) are constructed with
the ``SessionBundle`` they are about to write, because they need the
session uuid for the output path and the events to rebuild the JSON
``blocks[]``. The coordinator builds them per-session and runs them.

``ObserverController._run_compile`` passes the bundle it already
loaded via the required ``bundle`` keyword. It is deliberately
required rather than optional: an earlier revision let the
coordinator fall back to ``store.list_sessions(limit=1)`` when the
bundle was absent, which silently exported the wrong session whenever
a newer session had been opened between close and compile. Guessing
is not an acceptable fallback here — a wrong export looks correct.

A single coordinator is passed to ``attach_surface``; the controller
sees it as a list of one opaque object, the same way it sees plain
exporters, and dispatches on the ``accepts_bundle`` flag below.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from agentvoca.observer.models import CompiledSession, SessionBundle
    from agentvoca.observer.store import ObserverStore

logger = logging.getLogger(__name__)


class ExporterCoordinator:
    """Wraps the per-format exporter factory and runs it per-session.

    The controller calls ``await coordinator.export(compiled,
    bundle=bundle)`` with the bundle it already loaded for the
    compile. The coordinator constructs the real exporters for
    exactly that bundle — it never looks a session up itself.

    Args:
        store: The ``ObserverStore``. Retained for future use (e.g.
            re-compiling an archived session); the export path no
            longer reads from it.
        formats: The configured output formats, e.g. ``["markdown", "json"]``.
        out_dir: Where the exporters should write their artifacts.
    """

    #: Tells ``ObserverController._run_compile`` to pass ``bundle=``.
    #: Plain exporters (constructed with their bundle) leave this False.
    accepts_bundle = True

    def __init__(
        self,
        store: "ObserverStore",
        formats: list[str],
        out_dir: Path,
    ) -> None:
        self._store = store
        self._formats = list(formats)
        self._out_dir = Path(out_dir)

    async def export(self, compiled: "CompiledSession", *, bundle: "SessionBundle") -> dict:
        """Build exporters for ``bundle`` and run them.

        Args:
            compiled: The compiled session from a ``SessionCompiler``.
            bundle: The session being exported. Required — see the
                module docstring for why there is no fallback.

        Returns:
            ``{"markdown_path": ..., "json_path": ...}`` for the
            controller to publish as ``ObserverCompiledEvent``.
            Missing paths are ``""`` and ``None`` respectively.
        """
        from agentvoca.observer.export import make_exporters

        exporters = make_exporters(bundle, self._formats, self._out_dir)
        markdown_path = ""
        json_path: str | None = None
        for exporter in exporters:
            try:
                result = await exporter.export(compiled)
            except Exception:
                logger.exception("Exporter %s raised; continuing", getattr(exporter, "name", "?"))
                continue
            if result is None:
                continue
            if isinstance(result, str):
                name = getattr(exporter, "name", "")
                if name == "markdown" and not markdown_path:
                    markdown_path = result
                elif name == "json":
                    json_path = result
                elif not markdown_path:
                    # Unknown exporter: take the first string we get
                    # as the markdown path so the controller still
                    # has something to publish.
                    markdown_path = result
            elif isinstance(result, dict):
                if not markdown_path:
                    markdown_path = result.get("markdown_path", "")
                json_path = json_path or result.get("json_path")
        return {"markdown_path": markdown_path, "json_path": json_path}


__all__ = ["ExporterCoordinator"]
