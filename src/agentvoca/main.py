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
from agentvoca.asr import BUILTIN_ASR_PROVIDERS
from agentvoca.audio.capture import AudioCapture
from agentvoca.audio.chunker import AudioChunker
from agentvoca.capture.screenshot import ScreenshotCapturer
from agentvoca.cleanup import BUILTIN_CLEANUP_PROVIDERS
from agentvoca.config.loader import load_config
from agentvoca.config.schema import ASRConfig, FullConfig
from agentvoca.core.async_loop import AsyncLoopThread
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import ErrorEvent, HotkeyEvent, ScreenshotCapturedEvent
from agentvoca.core.orchestrator import Orchestrator
from agentvoca.core.registry import ProviderRegistry
from agentvoca.insertion import BUILTIN_INSERTION_STRATEGIES
from agentvoca.setup.controllers.config_controller import load_controller
from agentvoca.setup.first_run import load_state
from agentvoca.setup.settings_window import SettingsWindow
from agentvoca.setup.wizard import SetupWizard
from agentvoca.utils.errors import AgentVocaError, AudioError, ConfigError
from agentvoca.utils.logging import setup_logging
from agentvoca.vision import BUILTIN_VISION_PROVIDERS

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path.home() / ".agentvoca" / "config.yaml"


def _build_registry() -> ProviderRegistry:
    """Build the provider registry with all built-in providers."""
    registry = ProviderRegistry()

    for name, cls in BUILTIN_ASR_PROVIDERS.items():
        registry.register_asr(name, cls)
        logger.debug("Registered ASR provider: %s", name)

    for name, cls in BUILTIN_CLEANUP_PROVIDERS.items():
        registry.register_cleanup(name, cls)
        logger.debug("Registered cleanup provider: %s", name)

    for name, cls in BUILTIN_INSERTION_STRATEGIES.items():
        registry.register_insertion(name, cls)
        logger.debug("Registered insertion strategy: %s", name)

    for name, cls in BUILTIN_VISION_PROVIDERS.items():
        registry.register_vision(name, cls)
        logger.debug("Registered vision provider: %s", name)

    logger.info(
        "Provider registry initialized: %d ASR, %d cleanup, %d insertion, %d vision",
        len(registry.list_asr()),
        len(registry.list_cleanup()),
        len(registry.list_insertion()),
        len(registry.list_vision()),
    )
    return registry


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, load config, and start the application."""
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

    try:
        if config_path.is_file():
            config = load_config(config_path)
            logger.info("Loaded config from %s", config_path)
        else:
            logger.warning(
                "Config file not found at %s. Using defaults (faster_whisper base model).",
                config_path,
            )
            # Default to the 'base' model so faster-whisper has a model to load
            config = FullConfig(asr=ASRConfig(provider="faster_whisper", model="base"))
    except ConfigError as exc:
        logger.error("Config error: %s", exc)
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    # ── Config controller (v0.3.5 setup wizard / settings) ───────────
    # The wizard and tabbed settings window both go through a single
    # ConfigController that owns an in-memory draft + save semantics.
    controller = load_controller(config_path)
    if not config_path.is_file():
        controller.replace_draft(config)

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

    # ── v3: screenshot capture (only when vision is enabled) ──────────
    screenshot_capturer: ScreenshotCapturer | None = None
    if config.vision.enabled:
        screenshot_capturer = ScreenshotCapturer(
            event_bus=event_bus,
            capture_timeout_s=config.vision.capture_timeout_s,
        )
        if not screenshot_capturer.is_available():
            logger.warning(
                "Vision enabled but no native screenshot tool was found on this platform"
            )

    orchestrator = Orchestrator(
        config=config,
        registry=registry,
        event_bus=event_bus,
        screenshot_capturer=screenshot_capturer,
    )

    # ── UI ────────────────────────────────────────────────────────────
    settings_window: SettingsWindow | None = None
    wizard: SetupWizard | None = None

    def _reload_hot_components(new_config: FullConfig) -> None:
        """Hot-apply everything we can from a freshly-saved config.

        Called after the user saves from the wizard or settings window. Hot
        fields are pushed into the orchestrator; hotkeys are unregistered and
        re-registered; restart-only fields are surfaced via a notification
        so the user knows to relaunch.
        """
        # Hot-apply providers / vocab / snippets / etc.
        try:
            orchestrator.apply_config_update(new_config)
        except Exception:
            logger.exception("Hot-apply failed; some changes may need a restart")

        # Re-register hotkeys (they may have changed).
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
        wizard.show()
        wizard.raise_()
        wizard.activateWindow()

    overlay = StatusOverlay(event_bus)

    tray = TrayApp(event_bus)
    tray.open_settings_action.triggered.connect(open_settings)
    tray.open_wizard_action.triggered.connect(open_wizard)
    tray.quit_action.triggered.connect(app.quit)

    # ── Error notifications ───────────────────────────────────────────
    def on_error(event: object) -> None:
        message = getattr(event, "message", "Unknown error")
        stage = getattr(event, "stage", "unknown")
        recoverable = getattr(event, "recoverable", False)
        logger.error("Pipeline error [%s]: %s (recoverable=%s)", stage, message, recoverable)
        if not recoverable:
            tray.show_message("agentvoca Error", f"Error in {stage}: {message}", icon=2)

    event_bus.subscribe(ErrorEvent, on_error)

    # ── v3: screenshot capture feedback ───────────────────────────────
    if screenshot_capturer is not None:

        def on_screenshot(event: object) -> None:
            index = getattr(event, "index", 0)
            logger.info("Screenshot %d captured for the current dictation", index + 1)
            tray.show_message(
                "agentvoca",
                f"Screenshot {index + 1} captured — keep dictating.",
                icon=1,
            )

        event_bus.subscribe(ScreenshotCapturedEvent, on_screenshot)

    # ── Audio capture ─────────────────────────────────────────────────
    # Build the streaming chunker only when streaming is enabled; otherwise
    # the v1 batch path is used unchanged.
    chunker: AudioChunker | None = None
    if config.asr.streaming:
        chunker = AudioChunker(
            event_bus=event_bus,
            chunk_ms=config.asr.streaming_chunk_ms,
            window_s=config.asr.streaming_window_s,
            sample_rate=config.audio.sample_rate,
        )
        logger.info(
            "Streaming enabled (chunk_ms=%d, window_s=%d)",
            config.asr.streaming_chunk_ms,
            config.asr.streaming_window_s,
        )

    audio = AudioCapture(
        event_bus=event_bus,
        sample_rate=config.audio.sample_rate,
        channels=config.audio.channels,
        device_name=config.audio.input_device,
        silence_timeout_ms=config.audio.silence_timeout_ms,
        max_duration_s=config.audio.max_recording_duration_s,
        chunker=chunker,
        loop=loop_thread.loop,
    )
    try:
        audio.start()
        logger.info("Audio input opened")
    except AudioError as exc:
        logger.error("Failed to open audio input: %s", exc)
        return 1

    # ── Orchestrator startup ──────────────────────────────────────────
    # Run start() on the persistent loop and block until it returns. The
    # background warm-up task it spawns keeps running on that loop afterwards.
    try:
        loop_thread.submit(orchestrator.start()).result()
        logger.info("Orchestrator ready")
    except AgentVocaError as exc:
        logger.critical("Failed to start orchestrator: %s", exc)
        audio.stop()
        loop_thread.stop()
        return 1

    # ── Hotkeys ───────────────────────────────────────────────────────
    hotkeys = HotkeyManager(event_bus)

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

    _register_hotkeys(hotkeys, config)

    def on_hotkey(event: object) -> None:
        from agentvoca.core.events import StateChangedEvent  # noqa: PLC0415

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

    event_bus.subscribe(HotkeyEvent, on_hotkey)
    hotkeys.start()
    logger.info("Hotkeys active — press %s to record", config.hotkeys.toggle_recording)

    # ── v0.3.5: auto-open setup wizard on every launch ─────────────────
    state = load_state()
    if state.wizard_auto_open:
        wizard = SetupWizard(controller)
        wizard.config_saved.connect(_reload_hot_components)
        # Make the wizard non-blocking so the tray + hotkey are still
        # usable while the user reviews settings.
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
        hotkeys.stop()
        audio.stop()
        try:
            loop_thread.submit(orchestrator.stop()).result(timeout=3.0)
        except Exception:
            logger.debug("Orchestrator stop did not complete cleanly", exc_info=True)
        overlay.stop()
        loop_thread.stop()
        logger.info("Shutdown complete")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
