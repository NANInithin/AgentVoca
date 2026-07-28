"""Bundle-aware exporter coordinator (Track 3, OBS-28).

The ``ObserverController._run_compile`` coroutine calls each item in
its ``_exporters`` list with the compiled session only. The
concrete exporters (markdown / json sidecar) need the session bundle
too, to read the session uuid and rebuild the JSON ``blocks[]``.

The coordinator wraps the per-format factory and, on every
``export()`` call from the controller, finds the most recently
closed session and constructs the real exporters for that bundle.

A single coordinator is passed to ``attach_surface``; the controller
sees it as a list of one opaque object, the same way it sees
plain exporters.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from agentvoca.observer.models import CompiledSession
    from agentvoca.observer.store import ObserverStore

logger = logging.getLogger(__name__)


class ExporterCoordinator:
    """Wraps the per-format exporter factory and runs it per-session.

    The controller calls ``await coordinator.export(compiled)`` with
    just the ``CompiledSession`` (the contract shape). The
    coordinator uses the store to find the most recently closed
    session and constructs the real exporters for that session's
    bundle.

    Args:
        store: The ``ObserverStore`` (used to find the most recent
            session and load its bundle).
        formats: The configured output formats, e.g. ``["markdown", "json"]``.
        out_dir: Where the exporters should write their artifacts.
    """

    def __init__(
        self,
        store: "ObserverStore",
        formats: list[str],
        out_dir: Path,
    ) -> None:
        self._store = store
        self._formats = list(formats)
        self._out_dir = Path(out_dir)

    async def export(self, compiled: "CompiledSession") -> dict:
        """Build exporters for the most recent session and run them.

        Returns:
            ``{"markdown_path": ..., "json_path": ...}`` for the
            controller to publish as ``ObserverCompiledEvent``.
            Missing paths are ``""`` and ``None`` respectively.
        """
        from agentvoca.observer.export import make_exporters

        sessions = self._store.list_sessions(limit=1)
        if not sessions:
            logger.warning("ExporterCoordinator: no sessions found in store")
            return {"markdown_path": "", "json_path": None}
        session = sessions[0]
        bundle = self._store.load_bundle(session_id=session.id)
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
