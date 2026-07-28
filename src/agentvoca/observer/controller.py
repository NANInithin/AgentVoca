"""ObserverController — the integration seam for Observer mode (v0.4.0).

Owns the Observer subsystem lifecycle. Constructed unconditionally in
``main.py``; does nothing at all unless ``config.observer.enabled`` and
the user starts a session.

Track 1 ships this class complete, with both ``attach_*`` methods
present and callable. Tracks 2 and 3 each construct their own objects
and hand them over. This is what keeps three tracks out of each
other's way in ``main.py``.

Lifecycle (Track 1 implements; T2/T3 fill the bodies they own):

- ``start_session()`` opens via ``SessionManager``, publishes
  ``ObserverSessionStartedEvent``, and calls ``start()`` on any
  attached capture objects (via ``getattr(obj, "start", None)`` — the
  soft-contract pattern R8 used for ``shutdown()``).
- ``stop_session()`` stops attached objects the same way, closes the
  session, publishes ``ObserverSessionEndedEvent``, and — if a
  compiler is attached — schedules compilation with
  ``asyncio.run_coroutine_threadsafe(...)`` on the loop. No compiler
  attached → log INFO and skip. That is Track 3's item.
- ``pause()`` / ``resume()`` publish ``ObserverPausedEvent``.
- ``recover_sessions()`` returns ``store.find_open_sessions()``.
- ``shutdown()`` closes any open session as ``closed`` (a clean exit
  is not a crash), stops attached objects, and calls ``store.stop()``.
  Must be safe to call twice and safe when no session was ever opened.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from agentvoca.config.schema import FullConfig
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import (
    ObserverCompiledEvent,
    ObserverPausedEvent,
    ObserverSessionEndedEvent,
    ObserverSessionStartedEvent,
)
from agentvoca.observer.models import ObserverSession
from agentvoca.observer.session import SessionManager
from agentvoca.observer.store import ObserverStore

if TYPE_CHECKING:  # pragma: no cover - type-only imports
    from agentvoca.observer.compile.base import SessionCompiler

logger = logging.getLogger(__name__)


class ObserverController:
    """Owns the Observer subsystem lifecycle.

    Constructed unconditionally in main.py; does nothing at all unless
    ``config.observer.enabled`` and the user starts a session.
    """

    def __init__(
        self,
        config: FullConfig,
        event_bus: EventBus,
        store: ObserverStore,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._config = config
        self._event_bus = event_bus
        self._store = store
        self._loop = loop
        self._sessions = SessionManager(store=store)
        # Track 2 hands its objects over via attach_capture. Storing
        # them here, not the other way around, is what keeps the
        # three tracks' lifecycles independent.
        self._ambient: object | None = None
        self._triggers: object | None = None
        self._grabber: object | None = None
        self._ocr: object | None = None
        self._selection: object | None = None
        # Track 3 hands its objects over via attach_surface.
        self._compiler: "SessionCompiler | None" = None
        self._exporters: list[object] | None = None
        self._indicator: object | None = None

    # ── Track 2 hands its objects over here ─────────────────────────
    def attach_capture(
        self,
        ambient: "object | None",
        triggers: "object | None",
        grabber: "object | None",
        ocr: "object | None",
        selection: "object | None",
    ) -> None:
        """Register the capture subsystem.

        Track 1 ships this as a no-op that stores the references; Track
        2 makes ``start_session()`` use them. Objects are looked up via
        ``getattr(obj, "start", None)`` so a partial Track 2 attach
        (e.g. ambient wired but triggers not) still works.
        """
        self._ambient = ambient
        self._triggers = triggers
        self._grabber = grabber
        self._ocr = ocr
        self._selection = selection
        logger.debug(
            "ObserverController.capture attached: ambient=%s triggers=%s grabber=%s "
            "ocr=%s selection=%s",
            bool(ambient),
            bool(triggers),
            bool(grabber),
            bool(ocr),
            bool(selection),
        )

    # ── Track 3 hands its objects over here ─────────────────────────
    def attach_surface(
        self,
        compiler: "SessionCompiler | None",
        exporters: "list[object] | None",
        indicator: "object | None",
    ) -> None:
        """Register the compile + UI subsystem. Same stub arrangement."""
        self._compiler = compiler
        self._exporters = list(exporters) if exporters else []
        self._indicator = indicator
        logger.debug(
            "ObserverController.surface attached: compiler=%s exporters=%d indicator=%s",
            bool(compiler),
            len(self._exporters),
            bool(indicator),
        )

    # ── Lifecycle ──────────────────────────────────────────────────
    def start_session(self) -> bool:
        """Open a session and start capture.

        Returns:
            True if a session was opened, False if Observer is disabled
            or a session is already open.
        """
        if not self._config.observer.enabled:
            logger.debug("start_session: observer is disabled in config")
            return False
        if self.is_active:
            logger.debug("start_session: a session is already open")
            return False
        # Determine the app_version: this is a real-world concern but
        # for the seam we fall back to the bundle default.
        try:
            from agentvoca import __version__ as app_version
        except ImportError:
            app_version = "0.4.0"
        session = self._sessions.open(app_version=app_version)
        # Fire the start hooks on whatever capture subsystem is attached.
        # ``getattr(obj, "start", None)`` is the R8 soft-contract pattern:
        # works before Track 2 lands and works for partial Track 2 attach.
        for label, obj in (
            ("ambient", self._ambient),
            ("triggers", self._triggers),
            ("grabber", self._grabber),
            ("ocr", self._ocr),
            ("selection", self._selection),
        ):
            start = getattr(obj, "start", None) if obj is not None else None
            if callable(start):
                try:
                    start()
                except Exception:
                    logger.exception("Observer capture %s.start() raised; continuing", label)
        self._event_bus.publish(
            ObserverSessionStartedEvent(
                session_uuid=session.uuid,
                session_id=session.id,
                started_at_ms=session.started_at_ms,
            )
        )
        return True

    def stop_session(self) -> None:
        """Close the session and schedule compilation on the loop thread."""
        if not self.is_active:
            return
        # Snapshot the session id before close() clears it.
        session_id = self._sessions.current.id  # type: ignore[union-attr]
        session_uuid = self._sessions.current.uuid  # type: ignore[union-attr]
        # Stop attached capture objects first so they stop producing new
        # events that race the close.
        for label, obj in (
            ("ambient", self._ambient),
            ("triggers", self._triggers),
            ("grabber", self._grabber),
            ("ocr", self._ocr),
            ("selection", self._selection),
        ):
            stop = getattr(obj, "stop", None) if obj is not None else None
            if callable(stop):
                try:
                    stop()
                except Exception:
                    logger.exception("Observer capture %s.stop() raised; continuing", label)
        closed = self._sessions.close()
        if closed is None:
            return
        duration_ms = (closed.ended_at_ms or 0) - closed.started_at_ms
        # ``event_count`` is informational — we don't have it here, the
        # store does. Leave it 0 in the event; the consumer that needs
        # the exact number can ``load_bundle(session_id)``.
        self._event_bus.publish(
            ObserverSessionEndedEvent(
                session_uuid=session_uuid,
                session_id=session_id,
                duration_ms=duration_ms,
                event_count=0,
            )
        )
        # If a compiler is attached, schedule compilation on the loop.
        if self._compiler is not None:
            self._schedule_compile(session_id=session_id)
        else:
            logger.info(
                "ObserverController: no compiler attached; skipping compilation "
                "for session %d (the session is closed and the data is on disk)",
                session_id,
            )

    def _schedule_compile(self, session_id: int) -> None:
        """Schedule the compile coroutine on the asyncio loop thread."""
        try:
            asyncio.run_coroutine_threadsafe(self._run_compile(session_id=session_id), self._loop)
        except RuntimeError:
            # Loop is closed. Log and move on; the session is closed
            # regardless, the user can recompile later.
            logger.warning(
                "ObserverController: could not schedule compile for session %d (loop closed)",
                session_id,
            )

    async def _run_compile(self, session_id: int) -> None:
        """Compile a closed session and write its outputs to disk.

        On any failure, the session is left at status='closed' (NOT
        'compiled') and an ``ObserverCompiledEvent`` with ``degraded=True``
        is published. The user can always re-run compilation later.
        """
        assert self._compiler is not None
        started = int(time.time() * 1000)
        bundle = self._store.load_bundle(session_id=session_id)
        try:
            compiled = await self._compiler.compile(bundle)
        except Exception:
            logger.exception(
                "ObserverController: compiler raised for session %d; leaving as closed",
                session_id,
            )
            self._event_bus.publish(
                ObserverCompiledEvent(
                    session_uuid=bundle.session.uuid,
                    markdown_path="",
                    json_path=None,
                    degraded=True,
                    latency_ms=int(time.time() * 1000) - started,
                )
            )
            return
        # Run exporters (Track 3 owns the writer; Track 1 just calls them).
        markdown_path = ""
        json_path: str | None = None
        for exporter in self._exporters or []:
            try:
                result = await exporter.export(compiled)  # type: ignore[attr-defined]
            except Exception:
                logger.exception("ObserverController: exporter raised; continuing")
                continue
            if result is None:
                continue
            # Exporters may return either a string (path) or a dict with
            # 'markdown_path' / 'json_path'. Accept both for flexibility.
            if isinstance(result, str):
                if not markdown_path:
                    markdown_path = result
            elif isinstance(result, dict):
                markdown_path = markdown_path or result.get("markdown_path", "")
                json_path = json_path or result.get("json_path")
        latency_ms = int(time.time() * 1000) - started
        # Only mark the session 'compiled' if at least one output was produced.
        if markdown_path or json_path:
            self._store.mark_compiled(session_id=session_id)
        self._event_bus.publish(
            ObserverCompiledEvent(
                session_uuid=bundle.session.uuid,
                markdown_path=markdown_path,
                json_path=json_path,
                degraded=bool(compiled.degraded),
                latency_ms=latency_ms,
            )
        )

    def toggle_session(self) -> None:
        """Hotkey/tray entry point."""
        if self.is_active:
            self.stop_session()
        else:
            self.start_session()

    def pause(self, reason: str = "hotkey") -> None:
        """Suspend capture."""
        if not self._sessions.pause(reason=reason):
            return
        self._event_bus.publish(ObserverPausedEvent(paused=True, reason=reason))

    def resume(self, reason: str = "hotkey") -> None:
        """Resume capture."""
        if not self._sessions.resume(reason=reason):
            return
        self._event_bus.publish(ObserverPausedEvent(paused=False, reason=reason))

    @property
    def is_active(self) -> bool:
        return self._sessions.current is not None

    @property
    def is_paused(self) -> bool:
        return self._sessions.is_paused

    def recover_sessions(self) -> list[ObserverSession]:
        """Return sessions left 'open' by a crashed process, for the prompt."""
        return self._store.find_open_sessions()

    def shutdown(self) -> None:
        """Called from main.py's finally block.

        Closes any open session as 'closed' (NOT 'abandoned' — a clean
        exit is not a crash), stops attached objects, and calls
        ``store.stop()``. Safe to call twice and safe when no session
        was ever opened.
        """
        if self.is_active:
            # Use the same path as stop_session but without scheduling
            # compile (the loop may already be closing).
            for label, obj in (
                ("ambient", self._ambient),
                ("triggers", self._triggers),
                ("grabber", self._grabber),
                ("ocr", self._ocr),
                ("selection", self._selection),
            ):
                stop = getattr(obj, "stop", None) if obj is not None else None
                if callable(stop):
                    try:
                        stop()
                    except Exception:
                        logger.exception(
                            "Observer capture %s.stop() raised during shutdown; continuing",
                            label,
                        )
            self._sessions.close()
        # Stop attached surface subsystems too (indicator, compiler
        # warm-up connection, etc). The soft-contract pattern means
        # these are no-ops before Track 3 lands.
        for label, obj in (
            ("compiler", self._compiler),
            ("indicator", self._indicator),
        ):
            shutdown = getattr(obj, "shutdown", None) if obj is not None else None
            if callable(shutdown):
                try:
                    result = shutdown()
                    if asyncio.iscoroutine(result):
                        # The loop may already be closed; just close it
                        # synchronously via run_until_complete on a
                        # throwaway loop is too invasive here. Log and
                        # continue.
                        logger.debug(
                            "Observer %s.shutdown() returned a coroutine; "
                            "deferring to garbage collection",
                            label,
                        )
                except Exception:
                    logger.exception("Observer surface %s.shutdown() raised; continuing", label)
        # Always flush + stop the store. stop() is idempotent.
        try:
            self._store.flush(timeout=2.0)
        except Exception:
            logger.debug("Observer store flush during shutdown failed", exc_info=True)
        self._store.stop()

    # Expose the session manager for tests; not part of the public seam.
    @property
    def sessions(self) -> SessionManager:
        return self._sessions
