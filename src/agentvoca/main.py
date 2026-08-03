"""Entry point for the agentvoca dictation app.

Run with::

    python -m agentvoca --help
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from PySide6 import QtWidgets

from agentvoca.app.hotkeys import HotkeyManager
from agentvoca.app.overlay import StatusOverlay
from agentvoca.app.tray import TrayApp
from agentvoca.audio.capture import AudioCapture
from agentvoca.audio.chunker import AudioChunker
from agentvoca.audio.vad import VAD
from agentvoca.capture.screenshot import ScreenshotCapturer
from agentvoca.config.loader import load_config_lenient
from agentvoca.config.schema import ASRConfig, FullConfig
from agentvoca.core.async_loop import AsyncLoopThread
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import (
    ErrorEvent,
    HotkeyEvent,
    ObserverUtteranceEvent,
    ScreenshotCapturedEvent,
)
from agentvoca.core.orchestrator import Orchestrator
from agentvoca.core.registry import ProviderRegistry
from agentvoca.insertion._executor import shutdown_input_executor
from agentvoca.setup.controllers.config_controller import ConfigController
from agentvoca.setup.first_run import load_state
from agentvoca.setup.settings_window import SettingsWindow
from agentvoca.setup.wizard import SetupWizard
from agentvoca.utils.errors import AgentVocaError, AudioError, ConfigError
from agentvoca.utils.logging import setup_logging

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path.home() / ".agentvoca" / "config.yaml"


def _show_observer_recovery_dialog(
    observer_controller: object,
    sessions: list[object],
    tray: "TrayApp",
) -> None:
    """Show a non-modal dialog for each recovered Observer session.

    The dialog asks the user what to do with sessions left
    ``status='open'`` by a previous process. Three actions per
    session:

    * Compile it — mark the session ``closed`` and run compilation.
    * Keep for later — leave the session ``open``; ask again next launch.
    * Delete — ``purge_session``.

    Non-modal so the user can keep working while the dialog is up.
    """
    from PySide6 import QtCore, QtWidgets  # noqa: PLC0415

    from agentvoca.core.events import ObserverCompiledEvent  # noqa: PLC0415
    from agentvoca.observer.models import ObserverSession  # noqa: PLC0415

    for session in sessions:
        assert isinstance(session, ObserverSession)

        dialog = QtWidgets.QDialog()
        dialog.setWindowTitle("Unfinished Observer session")
        dialog.setModal(False)
        layout = QtWidgets.QVBoxLayout(dialog)

        started = session.started_at_ms or 0
        ended = session.ended_at_ms
        duration_ms = (ended - started) if ended and started else 0
        hours, rem = divmod(duration_ms // 60_000, 60)
        minutes = rem
        when = QtCore.QDateTime.fromMSecsSinceEpoch(started).toString("yyyy-MM-dd HH:mm")
        if duration_ms:
            duration_text = f"{hours} h {minutes} m" if hours else f"{minutes} m"
        else:
            duration_text = "?"
        msg = QtWidgets.QLabel(
            f"AgentVoca found 1 unfinished Observer session from {when} "
            f"({duration_text}).\n\nWhat would you like to do with it?"
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)

        button_row = QtWidgets.QHBoxLayout()
        compile_btn = QtWidgets.QPushButton("Compile it")
        keep_btn = QtWidgets.QPushButton("Keep for later")
        delete_btn = QtWidgets.QPushButton("Delete")
        button_row.addWidget(compile_btn)
        button_row.addWidget(keep_btn)
        button_row.addStretch()
        button_row.addWidget(delete_btn)
        layout.addLayout(button_row)

        store = getattr(observer_controller, "_store", None)
        compiler = getattr(observer_controller, "_compiler", None)
        loop = getattr(observer_controller, "_loop", None)

        def _on_compile() -> None:
            if store is None or compiler is None or loop is None:
                return
            try:
                store.close_session(
                    session.id, ended_at_ms=int(QtCore.QDateTime.currentMSecsSinceEpoch())
                )
            except Exception:
                logger.exception("Failed to mark session %d as closed", session.id)
            try:
                import asyncio  # noqa: PLC0415

                asyncio.run_coroutine_threadsafe(
                    getattr(observer_controller, "_run_compile")(session_id=session.id),
                    loop,
                )
            except Exception:
                logger.exception("Failed to schedule compile for session %d", session.id)
            try:
                tray.show_message(
                    "Observer session compiled",
                    f"Recompiling recovered session {when}",
                    icon=0,
                )
            except Exception:
                pass
            dialog.accept()

        def _on_keep() -> None:
            # Leave status='open'; the dialog asks again next launch.
            dialog.accept()

        def _on_delete() -> None:
            if store is None:
                dialog.accept()
                return
            try:
                store.purge_session(session.id)
            except Exception:
                logger.exception("Failed to purge session %d", session.id)
            dialog.accept()

        compile_btn.clicked.connect(_on_compile)
        keep_btn.clicked.connect(_on_keep)
        delete_btn.clicked.connect(_on_delete)
        # Avoid an unused-import warning; the type is referenced via isinstance.
        del ObserverCompiledEvent
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()


def _build_registry() -> ProviderRegistry:
    """Build the provider registry with all built-in providers.

    R14: built-in providers are registered as ``"module:Class"`` dotted
    paths inside ``ProviderRegistry.__init__``; this function just logs
    the names and returns the registry. The actual provider modules are
    imported only when ``get_*()`` is called for the configured provider.
    """
    registry = ProviderRegistry()

    for name in registry.list_asr():
        logger.debug("Registered ASR provider: %s", name)
    for name in registry.list_cleanup():
        logger.debug("Registered cleanup provider: %s", name)
    for name in registry.list_insertion():
        logger.debug("Registered insertion strategy: %s", name)
    for name in registry.list_vision():
        logger.debug("Registered vision provider: %s", name)
    for name in registry.list_ocr():
        logger.debug("Registered Observer OCR provider: %s", name)
    for name in registry.list_compiler():
        logger.debug("Registered Observer compiler: %s", name)

    logger.info(
        "Provider registry initialized: %d ASR, %d cleanup, %d insertion, %d vision, "
        "%d Observer OCR, %d Observer compiler",
        len(registry.list_asr()),
        len(registry.list_cleanup()),
        len(registry.list_insertion()),
        len(registry.list_vision()),
        len(registry.list_ocr()),
        len(registry.list_compiler()),
    )
    return registry


def _build_observer_capture(
    cfg: FullConfig,
    orchestrator: "Orchestrator | None",
    registry: ProviderRegistry,
    loop_thread: AsyncLoopThread,
    audio: AudioCapture,
    observer_controller: object,
    event_bus: EventBus,
    store: object,
) -> tuple:
    """Build and wire the capture-side Observer objects.

    Returns the (ambient, triggers, grabber, ocr, selection) tuple
    the controller expects, or a tuple of Nones on any construction
    failure — a broken Observer must never block dictation.

    Fault isolation matters as much as the wiring here. Each optional
    subsystem (ambient ASR, OCR, selection) is built inside its own
    try/except so a single failure costs only that subsystem. The
    outer try/except is the last resort for a failure in the parts
    Observer cannot run without (triggers, grabber): one exception
    there used to return the all-None tuple, which left the tray
    happily starting sessions that recorded nothing at all.
    """
    try:
        import functools  # noqa: PLC0415
        import itertools  # noqa: PLC0415
        import queue as _queue  # noqa: PLC0415
        import time as _time  # noqa: PLC0415

        from agentvoca.context.active_app import ActiveAppDetector  # noqa: PLC0415
        from agentvoca.core.events import ObserverKeyframeEvent  # noqa: PLC0415
        from agentvoca.observer.arbiter import ASRArbiter  # noqa: PLC0415
        from agentvoca.observer.audio import AmbientListener  # noqa: PLC0415
        from agentvoca.observer.models import Grab, ObserverEvent  # noqa: PLC0415
        from agentvoca.observer.privacy import ExclusionMatcher  # noqa: PLC0415
        from agentvoca.observer.screen import ScreenGrabber  # noqa: PLC0415
        from agentvoca.observer.triggers import TriggerEngine, TriggerGate  # noqa: PLC0415

        active_app = ActiveAppDetector()
        exclusions = ExclusionMatcher(cfg.observer.privacy)
        # The SessionManager, not the ObserverSession. ``sessions.record``
        # is the only write path that honours the pause carve-out.
        sessions = observer_controller.sessions

        # ── Ambient speech ──────────────────────────────────────────
        asr_arbiter: ASRArbiter | None = None
        if orchestrator is not None and getattr(orchestrator, "_asr_provider", None) is not None:

            def _on_ambient_text(text: str, ts_ms: int, duration_ms: int) -> None:
                """Store one ambient transcription. Runs on the loop thread."""
                if not text.strip():
                    return
                recorded = sessions.record(
                    "utterance_ambient",
                    text=text,
                    meta={"duration_ms": duration_ms},
                    ts_ms=ts_ms,
                )
                if recorded is None:
                    return  # no session open, or capture is paused
                event_bus.publish(
                    ObserverUtteranceEvent(text=text, source="ambient", duration_ms=duration_ms)
                )

            async def _start_arbiter() -> ASRArbiter:
                """Construct and start the arbiter ON the loop thread.

                ``ASRArbiter.start`` calls ``asyncio.get_running_loop()``
                and ``loop.create_task``. This function runs on the Qt
                thread, where there is no running loop, so calling
                ``start()`` directly raises RuntimeError.
                """
                arbiter = ASRArbiter(
                    provider=orchestrator._asr_provider,
                    queue_depth=cfg.observer.ocr.max_queue,
                )
                arbiter.start(on_text=_on_ambient_text)
                return arbiter

            try:
                asr_arbiter = loop_thread.submit(_start_arbiter()).result(timeout=10.0)
                orchestrator.attach_asr_arbiter(asr_arbiter)
            except Exception:
                logger.exception(
                    "Observer ambient ASR could not start; continuing without ambient "
                    "speech (screen capture is unaffected)"
                )
                asr_arbiter = None

        # ── OCR + selection (both optional) ─────────────────────────
        try:
            ocr_provider = registry.get_ocr(cfg.observer.ocr)
        except Exception:
            logger.exception(
                "Observer OCR provider '%s' is unavailable; keyframes will be stored without text",
                cfg.observer.ocr.provider,
            )
            ocr_provider = None

        selection_reader: object | None = None
        if cfg.observer.selection.enabled:
            try:
                if cfg.observer.selection.method == "uia" and sys.platform == "win32":
                    from agentvoca.observer.selection.windows_uia import (  # noqa: PLC0415
                        WindowsUIASelectionReader,
                    )

                    selection_reader = WindowsUIASelectionReader(
                        max_chars=cfg.observer.selection.max_chars,
                        active_app=active_app,
                    )
                else:
                    from agentvoca.observer.selection.noop import (  # noqa: PLC0415
                        NoopSelectionReader,
                    )

                    selection_reader = NoopSelectionReader()
            except Exception:
                logger.exception("Observer selection reader unavailable; continuing without it")
                selection_reader = None

        # ── Keyframe pipeline: gate → grabber → store → OCR ─────────
        grabber = ScreenGrabber(
            config=cfg.observer.screen,
            active_app=active_app,
        )
        # Running blob total per session uuid, so the per-session cap
        # costs a dict lookup instead of a directory walk per keyframe.
        blob_bytes: dict[str, int] = {}
        capped_sessions: set[str] = set()
        blob_seq = itertools.count()
        # Which exclusion pattern currently holds capture down, if any.
        # Used to emit exactly one pause_start / pause_end pair.
        exclusion_state = {"pattern": ""}

        def _record_gap(reason: str, dropped: int) -> None:
            """Timeline row for data we intentionally dropped."""
            sessions.record("gap", meta={"reason": reason, "dropped": dropped})

        def _is_excluded() -> bool:
            """Gate hook: is the foreground app/title privacy-excluded?

            Also emits the ``pause_start`` / ``pause_end`` pair so the
            timeline shows the gap. Neither row carries the app name or
            title — recording those would leak exactly what the
            exclusion list exists to keep out of the archive.
            """
            try:
                app_name, window_title = active_app.detect()
            except Exception:
                logger.debug("active-app detect failed in exclusion check", exc_info=True)
                return False
            excluded, pattern = exclusions.is_excluded(app_name, window_title)
            if excluded:
                if not exclusion_state["pattern"]:
                    exclusion_state["pattern"] = pattern or "excluded"
                    sessions.record(
                        "pause_start",
                        meta={"reason": "excluded_app", "pattern": pattern or ""},
                    )
            elif exclusion_state["pattern"]:
                exclusion_state["pattern"] = ""
                sessions.record("pause_end", meta={"reason": "excluded_app"})
            return excluded

        def _write_blob(session_uuid: str, jpeg: bytes) -> str | None:
            """Write a keyframe JPEG; return its path relative to storage.

            Relative so the whole archive can be moved (contracts §3).
            Returns None when the per-session cap is hit or the write
            fails — the caller then skips the row entirely rather than
            storing an event that points at nothing.
            """
            cap = cfg.observer.storage.max_session_mb * 1024 * 1024
            written = blob_bytes.get(session_uuid, 0)
            if cap and written + len(jpeg) > cap:
                if session_uuid not in capped_sessions:
                    capped_sessions.add(session_uuid)
                    _record_gap("disk_cap", 1)
                    logger.warning(
                        "Observer: session blob cap (%d MB) reached; keyframes are no "
                        "longer stored for this session",
                        cfg.observer.storage.max_session_mb,
                    )
                return None
            name = f"{int(_time.time() * 1000)}-{next(blob_seq)}.jpg"
            try:
                directory = store.blobs_dir / session_uuid
                directory.mkdir(parents=True, exist_ok=True)
                (directory / name).write_bytes(jpeg)
            except OSError:
                logger.warning("Observer: could not write keyframe blob", exc_info=True)
                return None
            blob_bytes[session_uuid] = written + len(jpeg)
            return f"blobs/{session_uuid}/{name}"

        async def _run_ocr(event_id: int, jpeg: bytes) -> None:
            """Extract text for one keyframe and patch its row.

            Runs on the loop thread. A failed extraction is recorded as
            ``ocr_status='failed'`` rather than dropped: the keyframe
            itself is still real, and the compiler needs to know the
            text is missing rather than empty.
            """
            started = _time.time()
            try:
                result = await ocr_provider.extract(jpeg)
            except Exception:
                logger.debug("Observer OCR failed for event %d", event_id, exc_info=True)
                store.set_event_text(event_id, "", {"ocr_status": "failed"})
                return
            meta_update = {
                "ocr_status": "ok",
                "ocr_ms": result.latency_ms or int((_time.time() - started) * 1000),
                "ocr_engine": result.engine,
            }
            if result.confidence is not None:
                meta_update["ocr_confidence"] = result.confidence
            store.set_event_text(event_id, result.text, meta_update)

        def _record_selection() -> None:
            """Read the highlighted text after a drag-select."""
            if selection_reader is None:
                return
            try:
                selection = selection_reader.read_selection()
            except Exception:
                logger.debug("Observer: selection read failed", exc_info=True)
                return
            if selection is None or not selection.text.strip():
                return
            sessions.record(
                "selection",
                app_name=selection.app_name,
                window_title=selection.window_title,
                text=selection.text,
                meta={
                    "method": selection.method,
                    "truncated": selection.truncated,
                    "chars": len(selection.text),
                },
            )

        def _on_keyframe_grab(reason: str, grab: "Grab | None") -> None:
            """Store one keyframe. Runs on the ``observer-capture`` thread."""
            if reason == "selection":
                _record_selection()
            if grab is None:
                return  # degenerate rect, or a dedup hit — both already counted
            session = sessions.current
            if session is None or observer_controller.is_paused:
                return  # the session closed or paused between gate and grab
            blob_path = _write_blob(session.uuid, grab.jpeg)
            if blob_path is None:
                return
            try:
                event_id = store.append_returning_id(
                    ObserverEvent(
                        id=0,
                        session_id=session.id,
                        ts_ms=int(_time.time() * 1000),
                        kind="keyframe",
                        app_name=grab.app_name,
                        window_title=grab.window_title,
                        text=None,
                        blob_path=blob_path,
                        meta={
                            "trigger": reason,
                            "dhash": grab.dhash,
                            "width": grab.width,
                            "height": grab.height,
                        },
                    )
                )
            except Exception:
                logger.warning("Observer: keyframe row insert failed", exc_info=True)
                return
            event_bus.publish(
                ObserverKeyframeEvent(
                    event_id=event_id,
                    trigger=reason,
                    app_name=grab.app_name,
                )
            )
            if ocr_provider is not None:
                loop_thread.submit(_run_ocr(event_id, grab.jpeg))

        def _enqueue_keyframe(reason: str) -> None:
            """Gate → capture worker.

            Called from the pynput listener thread among others, so it
            must return in microseconds: a bounded ``put_nowait`` and
            nothing else. ``queue.Full`` is the gate's signal to count
            the drop and record a gap.
            """
            if not grabber.submit(reason, functools.partial(_on_keyframe_grab, reason)):
                raise _queue.Full

        gate = TriggerGate(
            min_interval_ms=cfg.observer.triggers.min_interval_ms,
            max_keyframes_per_min=cfg.observer.triggers.max_keyframes_per_min,
            enqueue=_enqueue_keyframe,
            is_session_active=lambda: observer_controller.is_active,
            is_paused=lambda: observer_controller.is_paused,
            is_excluded=_is_excluded,
            on_gap=_record_gap,
        )
        trigger_engine = TriggerEngine(
            config=cfg.observer.triggers,
            session=sessions,
            active_app=active_app,
            gate=gate,
        )

        def _submit_ambient(audio: bytes, ts_ms: int, duration_ms: int) -> None:
            if asr_arbiter is None:
                return
            asr_arbiter.submit_ambient(
                audio,
                ts_ms=ts_ms,
                duration_ms=duration_ms,
                sample_rate=cfg.audio.sample_rate,
            )

        ambient_listener = AmbientListener(
            event_bus=event_bus,
            loop=loop_thread.loop,
            on_utterance=_submit_ambient,
            sample_rate=cfg.audio.sample_rate,
            on_speech_onset=trigger_engine.on_speech_onset,
        )

        audio.set_ambient_sink(ambient_listener)

        logger.info(
            "Observer capture wired: ambient_asr=%s ocr=%s selection=%s",
            asr_arbiter is not None,
            cfg.observer.ocr.provider if ocr_provider is not None else "none",
            selection_reader is not None,
        )
        return (ambient_listener, trigger_engine, grabber, ocr_provider, selection_reader)
    except Exception:
        logger.exception("Observer capture construction failed; observer will run in disabled mode")
        return (None, None, None, None, None)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, load config, and start the application.

    Startup order (v0.3.5):

    1. Parse CLI args and set up logging.
    2. Load the YAML config via the *lenient* loader. A previously-saved
       config that references an unset API-key env var does not crash the
       app; we surface a warning dialog and continue. Remember whether this
       is a genuine first run (no config file yet).
    3. Build the Qt app, event bus, async loop, registry, tray + overlay,
       and wire up the wizard/settings/hotkey callbacks — but *not* the
       config-dependent pipeline yet.
    4. First-run gate: if there is no config file, open the wizard modally
       and wait. This is the key ordering guarantee — the heavy pipeline
       (ASR provider, audio device, model warm-up) is built only *after*
       the user has chosen a provider, so picking a cloud provider never
       triggers a local Whisper model download/load. On subsequent launches
       we skip straight to building the pipeline (and only surface a
       lenient-load warning if the existing config was not fully valid).
    5. Build + start the pipeline from the effective config: providers,
       audio device, orchestrator warm-up, hotkeys.
    6. On non-first-run launches, auto-open the wizard non-blocking (unless
       the user opted out), then enter the Qt main loop.
    """
    parser = argparse.ArgumentParser(
        prog="agentvoca",
        description="A developer-first, model-agnostic voice dictation desktop app.",
        epilog=(
            "Configure via ~/.agentvoca/config.yaml. "
            "See docs/config-reference.md for available options."
        ),
    )
    parser.add_argument("-c", "--config", type=str, default=None)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--version", action="store_true")

    args = parser.parse_args(argv)

    if args.version:
        # Prefer the in-package constant: it's always bundled into the frozen
        # PyInstaller exe, whereas package metadata (.dist-info) is not, which
        # is why frozen builds otherwise fell back to a stale hardcoded string.
        from agentvoca import __version__ as ver

        print(f"agentvoca {ver}")
        return 0

    # ── Logging ──────────────────────────────────────────────────────
    setup_logging(debug=args.debug)

    # ── Config ───────────────────────────────────────────────────────
    config_path = Path(args.config).expanduser().resolve() if args.config else _DEFAULT_CONFIG_PATH
    # Captured before anything can create the file. On a genuine first run we
    # defer building/starting the pipeline until the user has completed the
    # wizard, so we never load a local ASR model they are about to replace
    # with a cloud provider (see the first-run gate near the bottom).
    is_first_run = not config_path.is_file()
    startup_config_warning: str | None = None
    if config_path.is_file():
        try:
            config, startup_config_warning = load_config_lenient(config_path)
            logger.info("Loaded config from %s", config_path)
        except ConfigError as exc:
            logger.error("Config error: %s", exc)
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 1
    else:
        logger.warning(
            "Config file not found at %s. Using defaults (faster_whisper base model).",
            config_path,
        )
        # Default to the 'base' model so faster-whisper has a model to load
        config = FullConfig(asr=ASRConfig(provider="faster_whisper", model="base"))

    if startup_config_warning:
        logger.warning("Config loaded with warnings: %s", startup_config_warning)

    # ── Config controller (v0.3.5 setup wizard / settings) ───────────
    # The wizard and tabbed settings window both go through a single
    # ConfigController that owns an in-memory draft + save semantics.
    # Seed it with the config we already loaded *leniently* above rather
    # than re-reading the file strictly — a config with a missing API-key
    # env var (e.g. an OPENROUTER_API_KEY unset since the last session)
    # must reach the wizard so the user can fix it, not crash startup.
    controller = ConfigController(config_path=config_path, initial=config)

    # ── Qt Application ───────────────────────────────────────────────
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # ── Core objects ─────────────────────────────────────────────────
    event_bus = EventBus()

    # Persistent asyncio loop on a background thread. The Qt main loop owns
    # this thread; all pipeline coroutines and their spawned tasks (warm-up,
    # streaming, voice-command inserts, error timer) run here so they are not
    # cancelled by a throwaway asyncio.run().
    loop_thread = AsyncLoopThread()
    loop_thread.start()
    event_bus.set_loop(loop_thread.loop)

    registry = _build_registry()

    # ── Config-dependent handles (built after the first-run gate) ─────
    # These are populated by ``_build_and_start_pipeline`` once the effective
    # config is known. On a first run that means *after* the wizard, so a
    # user who picks a cloud provider never triggers a local model load.
    screenshot_capturer: ScreenshotCapturer | None = None
    orchestrator: Orchestrator | None = None
    audio: AudioCapture | None = None
    chunker: AudioChunker | None = None
    hotkeys: HotkeyManager | None = None
    # v0.4.0: Observer mode controller. Stays None when observer.enabled
    # is False; on_hotkey closes over it like the other handles. The
    # class is imported lazily inside _build_and_start_pipeline to keep
    # the cold-start import path lean.
    observer_controller: object | None = None

    # ── UI scaffolding (tray, overlay) ───────────────────────────────
    # Built up front so the user has a UI surface immediately, even before
    # the heavy pipeline exists.
    overlay = StatusOverlay(event_bus)

    tray = TrayApp(event_bus)
    settings_window: SettingsWindow | None = None
    wizard: SetupWizard | None = None

    def _register_hotkeys(manager: HotkeyManager, cfg: FullConfig) -> None:
        """Bind every configured hotkey on ``manager``."""
        manager.register(cfg.hotkeys.toggle_recording, "toggle_recording")
        manager.register(cfg.hotkeys.cancel, "cancel")
        manager.register(cfg.hotkeys.open_settings, "open_settings")
        if cfg.hotkeys.insert_last_transcript:
            manager.register(cfg.hotkeys.insert_last_transcript, "insert_last")
        if cfg.hotkeys.undo:
            manager.register(cfg.hotkeys.undo, "undo")
        if cfg.vision.enabled and cfg.hotkeys.capture_screenshot:
            manager.register(cfg.hotkeys.capture_screenshot, "capture_screenshot")
        # v0.4.0: Observer hotkeys. Always gated by observer.enabled; the
        # hotkey string is validated by HotkeysConfig at config load.
        if cfg.observer.enabled and cfg.hotkeys.toggle_observer:
            manager.register(cfg.hotkeys.toggle_observer, "toggle_observer")
        if cfg.observer.enabled and cfg.hotkeys.pause_observer:
            manager.register(cfg.hotkeys.pause_observer, "pause_observer")

    def _reload_hot_components(new_config: FullConfig) -> None:
        """Hot-apply everything we can from a freshly-saved config.

        Called after the user saves from the wizard or settings window. Hot
        fields are pushed into the orchestrator; hotkeys are unregistered and
        re-registered. When the pipeline has not been built yet (a first-run
        wizard saving before ``_build_and_start_pipeline`` runs) this is a
        no-op — the pipeline is then built fresh from the saved config.

        The orchestrator call is routed through the asyncio loop thread
        (R8): the method touches async-owned state (cleanup/vocab swap,
        HTTP-client close) and must run there, not on the Qt thread that
        received the Qt save signal.
        """
        if orchestrator is not None:
            try:
                loop_thread.call_soon(orchestrator.apply_config_update, new_config)
            except Exception:
                logger.exception("Hot-apply failed; some changes may need a restart")

        if hotkeys is not None:
            try:
                hotkeys.unregister_all()
                _register_hotkeys(hotkeys, new_config)
                logger.info("Hotkeys re-registered")
            except Exception:
                logger.exception("Failed to re-register hotkeys")

    def open_settings() -> None:
        nonlocal settings_window
        settings_window = SettingsWindow(controller)
        settings_window.config_saved.connect(_reload_hot_components)
        settings_window.show()
        settings_window.raise_()
        settings_window.activateWindow()

    def open_wizard() -> None:
        nonlocal wizard
        wizard = SetupWizard(controller)
        wizard.config_saved.connect(_reload_hot_components)
        wizard.show()
        wizard.raise_()
        wizard.activateWindow()

    tray.open_settings_action.triggered.connect(open_settings)
    tray.open_wizard_action.triggered.connect(open_wizard)
    tray.quit_action.triggered.connect(app.quit)

    def on_error(event: object) -> None:
        message = getattr(event, "message", "Unknown error")
        stage = getattr(event, "stage", "unknown")
        recoverable = getattr(event, "recoverable", False)
        logger.error("Pipeline error [%s]: %s (recoverable=%s)", stage, message, recoverable)
        if not recoverable:
            tray.show_message("agentvoca Error", f"Error in {stage}: {message}", icon=2)

    event_bus.subscribe(ErrorEvent, on_error)

    def _notify_observer_unavailable() -> None:
        """Tell the user why an Observer action did nothing.

        Reached when the tray/hotkey fires but no ``ObserverController``
        was built — i.e. ``observer.enabled`` is false (the default, and
        the case for any config written before v0.4.0), or construction
        failed. Without this the click is swallowed silently, which reads
        as a broken feature.
        """
        logger.info("Observer action ignored: observer is not enabled in config")
        tray.show_message(
            "Observer is off",
            "Enable Observer in Settings → Observer, then restart AgentVoca.",
            icon=1,
        )

    def on_hotkey(event: object) -> None:
        from agentvoca.core.events import StateChangedEvent  # noqa: PLC0415

        # Hotkeys are only started after the pipeline is built, so audio and
        # orchestrator are non-None whenever this fires.
        if audio is None or orchestrator is None:
            return
        action = getattr(event, "action", None)
        if action == "toggle_recording":
            if audio.is_recording:
                logger.debug("Stopping recording")
                audio.stop_recording()
            else:
                logger.debug("Starting recording")
                # Reset any leftover streaming state before the new dictation.
                loop_thread.call_soon(orchestrator.prepare_for_recording)
                audio.start_recording()
                # Notify the overlay immediately so it appears during recording,
                # not only after the pipeline starts (which happens post-stop).
                event_bus.publish(StateChangedEvent(previous="idle", current="recording"))
        elif action == "cancel":
            logger.debug("Cancelling recording")
            audio.cancel_recording()
            # R6: route the orchestrator cancel through the loop thread so it
            # can interrupt the in-flight pipeline task at its next await
            # (sync method, mirrors ``prepare_for_recording``).
            loop_thread.call_soon(orchestrator.cancel)
            event_bus.publish(StateChangedEvent(previous="recording", current="idle"))
        elif action == "open_settings":
            open_settings()
        elif action == "undo":
            loop_thread.submit(orchestrator.undo_last_insertion())
        elif action == "capture_screenshot":
            if screenshot_capturer is not None and audio.is_recording:
                logger.debug("Capturing screenshot for current dictation")
                screenshot_capturer.capture()
            else:
                logger.debug("Screenshot hotkey ignored (not recording)")
        # v0.4.0: Observer hotkeys. The controller is None when observer
        # is disabled, so the hotkey may be registered but the action
        # becomes a no-op.
        elif action == "toggle_observer":
            if observer_controller is not None:
                observer_controller.toggle_session()
            else:
                _notify_observer_unavailable()
        elif action == "pause_observer":
            if observer_controller is not None:
                if observer_controller.is_paused:
                    observer_controller.resume()
                else:
                    observer_controller.pause()
            else:
                _notify_observer_unavailable()

    event_bus.subscribe(HotkeyEvent, on_hotkey)

    def _build_and_start_pipeline(cfg: FullConfig) -> bool:
        """Build the config-dependent pipeline and start it.

        This is where the heavy work happens: constructing the ASR/cleanup
        providers, opening the audio device, and kicking off model warm-up.
        It runs only after the effective config is known (after the first-run
        wizard, if any), so a cloud provider never triggers a local model
        load. Returns True on success, False if audio or the orchestrator
        failed to start.
        """
        nonlocal screenshot_capturer, orchestrator, audio, chunker, hotkeys, observer_controller

        # v3: screenshot capture (only when vision is enabled)
        if cfg.vision.enabled:
            screenshot_capturer = ScreenshotCapturer(
                event_bus=event_bus,
                capture_timeout_s=cfg.vision.capture_timeout_s,
            )
            if not screenshot_capturer.is_available():
                logger.warning(
                    "Vision enabled but no native screenshot tool was found on this platform"
                )

            def on_screenshot(event: object) -> None:
                index = getattr(event, "index", 0)
                logger.info("Screenshot %d captured for the current dictation", index + 1)
                tray.show_message(
                    "agentvoca",
                    f"Screenshot {index + 1} captured — keep dictating.",
                    icon=1,
                )

            event_bus.subscribe(ScreenshotCapturedEvent, on_screenshot)

        orchestrator = Orchestrator(
            config=cfg,
            registry=registry,
            event_bus=event_bus,
            screenshot_capturer=screenshot_capturer,
        )

        # Audio capture (light: just opens a sounddevice stream).
        if cfg.asr.streaming:
            chunker = AudioChunker(
                event_bus=event_bus,
                chunk_ms=cfg.asr.streaming_chunk_ms,
                window_s=cfg.asr.streaming_window_s,
                sample_rate=cfg.audio.sample_rate,
            )
            logger.info(
                "Streaming enabled (chunk_ms=%d, window_s=%d)",
                cfg.asr.streaming_chunk_ms,
                cfg.asr.streaming_window_s,
            )

        # OBS-0: construct a VAD when the user opted in. Fail-open: any failure
        # logs a warning and leaves vad=None, which is exactly today's behavior
        # (no auto-stop; recording ends only on max_recording_duration_s).
        vad: VAD | None = None
        if cfg.audio.vad_enabled:
            try:
                vad = VAD(
                    event_bus=event_bus,
                    sample_rate=cfg.audio.sample_rate,
                )
                # Constructing a VAD does not load silero — ``start()``
                # does, and ``is_available`` stays False until it has run.
                # Without this the check below always failed, so auto-stop
                # was silently off on every machine, however healthy the
                # install. Loaded on the loop thread: it is ~1 s of torch
                # work and the Qt thread must not stall on it.
                loop_thread.submit(vad.start()).result(timeout=60.0)
                if not vad.is_available:
                    logger.warning("VAD requested but silero is unavailable — auto-stop disabled")
                    vad = None
            except Exception:
                logger.exception("VAD initialization failed — continuing without auto-stop")
                vad = None

        audio = AudioCapture(
            event_bus=event_bus,
            sample_rate=cfg.audio.sample_rate,
            channels=cfg.audio.channels,
            device_name=cfg.audio.input_device,
            vad=vad,
            silence_timeout_ms=cfg.audio.silence_timeout_ms,
            max_duration_s=cfg.audio.max_recording_duration_s,
            chunker=chunker,
            loop=loop_thread.loop,
        )
        try:
            audio.start()
            logger.info("Audio input opened")
        except AudioError as exc:
            logger.error("Failed to open audio input: %s", exc)
            return False

        # Orchestrator startup (kicks off model warm-up).
        try:
            loop_thread.submit(orchestrator.start()).result()
            logger.info("Orchestrator ready")
        except AgentVocaError as exc:
            logger.critical("Failed to start orchestrator: %s", exc)
            audio.stop()
            return False

        # Hotkeys.
        hotkeys = HotkeyManager(event_bus)
        _register_hotkeys(hotkeys, cfg)
        hotkeys.start()
        logger.info("Hotkeys active — press %s to record", cfg.hotkeys.toggle_recording)

        # ── v0.4.0: Observer mode ───────────────────────────────────
        # Track 1 lands the full wiring block (controller construction,
        # store start, retention purge, both attach_* stub lines). Tracks
        # 2 and 3 each replace exactly their own marked line; nothing
        # else in this block changes.
        if cfg.observer.enabled:
            from pathlib import Path as _Path

            from agentvoca.observer.controller import ObserverController  # noqa: PLC0415
            from agentvoca.observer.store import ObserverStore  # noqa: PLC0415

            observer_store = ObserverStore(root=_Path(cfg.observer.storage.dir).expanduser())
            observer_store.start()
            observer_store.purge_expired(cfg.observer.storage.retention_days)

            observer_controller = ObserverController(
                config=cfg,
                event_bus=event_bus,
                store=observer_store,
                loop=loop_thread.loop,
            )
            # TRACK 2 REPLACES THIS LINE:
            observer_controller.attach_capture(
                *_build_observer_capture(
                    cfg=cfg,
                    orchestrator=orchestrator,
                    registry=registry,
                    loop_thread=loop_thread,
                    audio=audio,
                    observer_controller=observer_controller,
                    event_bus=event_bus,
                    store=observer_store,
                )
            )
            # TRACK 3 REPLACES THIS LINE:
            # Construct the compiler (registry-resolved), the exporter
            # coordinator (which finds the session bundle at compile
            # time), and the on-screen ``ObserverIndicator``. A broken
            # compiler (e.g. an unregistered provider name) must not
            # stop the app or stop *recording* \u2014 we degrade to
            # attach_surface(None, None, None) so the session can
            # still be opened and a later recompile can recover.
            try:
                from agentvoca.app.overlay import ObserverIndicator  # noqa: PLC0415
                from agentvoca.observer.compile.base import SessionCompiler  # noqa: PLC0415
                from agentvoca.observer.export.coordinator import (  # noqa: PLC0415
                    ExporterCoordinator,
                )

                try:
                    compiler: SessionCompiler | None = registry.get_compiler(cfg.observer.compile)
                except Exception:
                    logger.exception(
                        "Observer compiler '%s' could not be constructed; "
                        "sessions will not be compiled automatically",
                        cfg.observer.compile.provider,
                    )
                    compiler = None

                coordinator = ExporterCoordinator(
                    store=observer_store,
                    formats=list(cfg.observer.compile.formats),
                    out_dir=Path(cfg.observer.compile.output_dir).expanduser(),
                )
                indicator = ObserverIndicator(event_bus)
                observer_controller.attach_surface(compiler, [coordinator], indicator)
            except Exception:
                logger.exception("Failed to attach Observer surface; degrading to no-compile")
                observer_controller.attach_surface(None, None, None)

        # Only now does the tray know whether Observer can actually run.
        # Leaving the submenu live when the controller is None made every
        # click a silent no-op.
        tray.set_observer_available(
            observer_controller is not None,
            reason="enable in Settings",
        )
        return True

    # ── First-run gate ────────────────────────────────────────────────
    # On a genuine first run, open the wizard *modally* before building the
    # pipeline. This guarantees we do not load a local ASR model the user is
    # about to replace with a cloud provider. On subsequent launches the
    # config already reflects the user's choice, so we build immediately and
    # only surface a lenient-load warning / auto-open the wizard afterwards.
    state = load_state()
    if is_first_run:
        logger.info("First run detected — opening setup wizard before starting the pipeline")
        first_run_wizard = SetupWizard(controller)
        first_run_wizard.config_saved.connect(_reload_hot_components)
        first_run_wizard.exec()
        # Use whatever the user ended with — the saved config if they clicked
        # Save, or the untouched default if they cancelled setup.
        config = controller.draft
    elif startup_config_warning:
        # Existing but not-fully-valid config (e.g. a remote provider whose
        # API-key env var is unset). Open the wizard *modally* with an in-wizard
        # banner explaining the problem, before building the pipeline — so the
        # user can fix or replace the config first, and we never warm up a model
        # under a config they are about to change. This replaces the old
        # standalone "Config needs attention" message box.
        logger.info("Config loaded with warnings — opening setup wizard to fix it")
        fix_wizard = SetupWizard(controller, startup_warning=startup_config_warning)
        fix_wizard.config_saved.connect(_reload_hot_components)
        fix_wizard.exec()
        # Build from whatever the user ended with: the corrected config if they
        # saved, or the untouched lenient config if they cancelled.
        config = controller.draft

    if not _build_and_start_pipeline(config):
        loop_thread.stop()
        return 1

    # v0.4.0: Observer crash recovery. Sessions left ``status='open'``
    # by a previous process are recovered here, after the pipeline is
    # up, so the dialog never blocks startup. Non-modal, follows the
    # wizard's show/raise/activate pattern.
    if observer_controller is not None:
        recoverable = observer_controller.recover_sessions()
        if recoverable:
            _show_observer_recovery_dialog(observer_controller, recoverable, tray)

    # On normal non-first-run launches, auto-open the wizard non-blocking (if
    # the user has not opted out). Skipped when we already showed a modal wizard
    # above (first run, or the broken-config fix flow) so it never opens twice.
    if not is_first_run and not startup_config_warning and state.wizard_auto_open:
        wizard = SetupWizard(controller)
        wizard.config_saved.connect(_reload_hot_components)
        # Non-blocking so the tray + hotkey are still usable while the
        # user reviews settings.
        wizard.show()
        logger.info("Setup wizard shown on startup (auto-open enabled)")

    # ── Main loop ─────────────────────────────────────────────────────
    try:
        exit_code = app.exec()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        exit_code = 0
    finally:
        logger.info("Shutting down…")
        if wizard is not None:
            wizard.close()
        if settings_window is not None:
            settings_window.close()
        if hotkeys is not None:
            hotkeys.stop()
        if audio is not None:
            audio.stop()
        if orchestrator is not None:
            try:
                loop_thread.submit(orchestrator.stop()).result(timeout=3.0)
            except Exception:
                logger.debug("Orchestrator stop did not complete cleanly", exc_info=True)
        # v0.4.0: Observer shutdown — must happen BEFORE overlay.stop()
        # so the overlay is still up while we close any open session and
        # write the final events. A failure here is logged at DEBUG and
        # swallowed (the app is shutting down anyway).
        if observer_controller is not None:
            try:
                observer_controller.shutdown()
            except Exception:
                logger.debug("Observer shutdown did not complete cleanly", exc_info=True)
        overlay.stop()
        shutdown_input_executor()
        loop_thread.stop()
        logger.info("Shutdown complete")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
