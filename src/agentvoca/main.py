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
from agentvoca.core.events import ErrorEvent, HotkeyEvent, ScreenshotCapturedEvent
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
        elif action == "pause_observer":
            if observer_controller is not None:
                if observer_controller.is_paused:
                    observer_controller.resume()
                else:
                    observer_controller.pause()

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
            observer_controller.attach_capture(None, None, None, None, None)
            # TRACK 3 REPLACES THIS LINE:
            observer_controller.attach_surface(None, None, None)
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
