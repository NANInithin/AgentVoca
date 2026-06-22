"""Screenshot capture using OS-native snip tools (v3).

The capturer invokes the platform's native region-snip UI and collects the
resulting PNG bytes:

    - macOS:   ``screencapture -i`` writes the selection to a temp file.
    - Windows: ``ms-screenclip:`` (Snip & Sketch) writes to the clipboard;
               the image is read back with Pillow.
    - Linux:   best-effort via ``gnome-screenshot`` / ``spectacle`` / ``maim``
               (mainly for development; not a primary target).

Captures run on a short-lived background thread so the global hotkey handler
never blocks while the user drags out a selection. Completed captures are
held in an ordered, thread-safe list that the orchestrator drains when the
dictation pipeline runs.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import struct
import subprocess
import tempfile
import threading
import time
from typing import Optional

from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import ScreenshotCapturedEvent

logger = logging.getLogger(__name__)


def _png_dimensions(data: bytes) -> tuple[Optional[int], Optional[int]]:
    """Return (width, height) for PNG bytes, or (None, None) if not parseable."""
    # PNG signature (8 bytes) + IHDR chunk: length(4) + "IHDR"(4) + width(4) + height(4)
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        return width, height
    return None, None


class ScreenshotCapturer:
    """Captures screenshots via OS-native snip tools and queues them.

    Args:
        event_bus: Shared event bus for publishing ``ScreenshotCapturedEvent``.
        capture_timeout_s: Max time to wait for the user to finish snipping.
    """

    def __init__(self, event_bus: EventBus, capture_timeout_s: int = 30) -> None:
        self._event_bus = event_bus
        self._timeout_s = capture_timeout_s
        self._platform = platform.system()

        self._screenshots: list[bytes] = []
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        self._in_flight = 0

    # ── Availability ───────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Return True if a native snip tool exists on this platform."""
        if self._platform == "Darwin":
            return shutil.which("screencapture") is not None
        if self._platform == "Windows":
            return True  # ms-screenclip: ships with Windows 10/11
        if self._platform == "Linux":
            return self._linux_tool() is not None
        return False

    # ── Capture control ────────────────────────────────────────────────

    def capture(self) -> None:
        """Trigger an asynchronous screenshot capture.

        Returns immediately; the snip runs on a daemon thread. Safe to call
        from the hotkey listener thread, and to call multiple times per
        dictation (each press queues another capture).
        """
        with self._lock:
            self._in_flight += 1
        thread = threading.Thread(target=self._run_capture, daemon=True)
        thread.start()

    def _run_capture(self) -> None:
        """Worker body: perform the snip, store bytes, publish an event."""
        try:
            data = self._capture_bytes()
        except Exception:
            logger.debug("Screenshot capture failed", exc_info=True)
            data = None

        index: Optional[int] = None
        width = height = None
        with self._lock:
            if data:
                index = len(self._screenshots)
                self._screenshots.append(data)
                width, height = _png_dimensions(data)
            self._in_flight -= 1
            if self._in_flight <= 0:
                self._idle.notify_all()

        if index is not None:
            logger.info("Screenshot captured (index=%d, %d bytes)", index, len(data or b""))
            self._event_bus.publish(
                ScreenshotCapturedEvent(index=index, width=width, height=height)
            )
        else:
            logger.info("Screenshot capture cancelled or produced no image")

    # ── Draining / synchronisation ─────────────────────────────────────

    def wait_idle(self, timeout: float) -> bool:
        """Block until no captures are in flight, or until ``timeout`` elapses.

        Returns True if idle, False on timeout. Call from a worker thread
        (e.g. via ``asyncio.to_thread``) — never from the event loop.
        """
        deadline = time.monotonic() + timeout
        with self._idle:
            while self._in_flight > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return self._in_flight == 0
                self._idle.wait(remaining)
            return True

    def drain(self) -> list[bytes]:
        """Return all captured screenshots in order and clear the queue."""
        with self._lock:
            shots = self._screenshots
            self._screenshots = []
        return shots

    def has_pending(self) -> bool:
        """Return True if any captures are queued or in flight."""
        with self._lock:
            return bool(self._screenshots) or self._in_flight > 0

    def clear(self) -> None:
        """Discard any queued screenshots (e.g. at the start of a recording)."""
        with self._lock:
            self._screenshots = []

    # ── Platform snip implementations ──────────────────────────────────

    def _capture_bytes(self) -> Optional[bytes]:
        """Run the platform snip and return PNG bytes, or None if cancelled."""
        if self._platform == "Darwin":
            return self._capture_macos()
        if self._platform == "Windows":
            return self._capture_windows()
        if self._platform == "Linux":
            return self._capture_linux()
        logger.warning("Screenshot capture is not supported on %s", self._platform)
        return None

    def _capture_macos(self) -> Optional[bytes]:
        fd, path = tempfile.mkstemp(suffix=".png", prefix="agentvoca_shot_")
        os.close(fd)
        try:
            # -i interactive selection, -t png. Returns 0 even if cancelled, but
            # no file is written on cancel.
            subprocess.run(
                ["screencapture", "-i", "-t", "png", path],
                timeout=self._timeout_s,
                check=False,
            )
            if os.path.getsize(path) > 0:
                with open(path, "rb") as f:
                    return f.read()
            return None
        except subprocess.TimeoutExpired:
            logger.warning("screencapture timed out after %ds", self._timeout_s)
            return None
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def _capture_windows(self) -> Optional[bytes]:
        try:
            from PIL import ImageGrab  # noqa: PLC0415
        except Exception:
            logger.warning("Pillow is required for screenshot capture on Windows")
            return None

        baseline = self._clipboard_signature(ImageGrab)
        # Launch the Snip & Sketch overlay (fire-and-forget; returns at once).
        try:
            os.startfile("ms-screenclip:")  # type: ignore[attr-defined]
        except Exception:
            subprocess.run(["explorer.exe", "ms-screenclip:"], check=False)

        deadline = time.monotonic() + self._timeout_s
        while time.monotonic() < deadline:
            time.sleep(0.4)
            try:
                grabbed = ImageGrab.grabclipboard()
            except Exception:
                grabbed = None
            if grabbed is None or isinstance(grabbed, list):
                continue
            if self._image_signature(grabbed) == baseline:
                continue  # unchanged — user still selecting
            import io  # noqa: PLC0415

            buf = io.BytesIO()
            grabbed.save(buf, format="PNG")
            return buf.getvalue()
        logger.warning("No screenshot detected on clipboard within %ds", self._timeout_s)
        return None

    @staticmethod
    def _clipboard_signature(image_grab) -> Optional[tuple]:
        try:
            img = image_grab.grabclipboard()
        except Exception:
            return None
        if img is None or isinstance(img, list):
            return None
        return ScreenshotCapturer._image_signature(img)

    @staticmethod
    def _image_signature(img) -> tuple:
        # Cheap identity: size + a small sample of pixel data.
        try:
            return (img.size, img.tobytes()[:64])
        except Exception:
            return (getattr(img, "size", None), None)

    def _capture_linux(self) -> Optional[bytes]:
        tool = self._linux_tool()
        if tool is None:
            logger.warning("No supported screenshot tool found on Linux")
            return None

        fd, path = tempfile.mkstemp(suffix=".png", prefix="agentvoca_shot_")
        os.close(fd)
        try:
            if tool == "gnome-screenshot":
                cmd = ["gnome-screenshot", "-a", "-f", path]
            elif tool == "spectacle":
                cmd = ["spectacle", "-r", "-b", "-n", "-o", path]
            else:  # maim
                cmd = ["maim", "-s", path]
            subprocess.run(cmd, timeout=self._timeout_s, check=False)
            if os.path.getsize(path) > 0:
                with open(path, "rb") as f:
                    return f.read()
            return None
        except subprocess.TimeoutExpired:
            logger.warning("%s timed out after %ds", tool, self._timeout_s)
            return None
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    @staticmethod
    def _linux_tool() -> Optional[str]:
        for tool in ("gnome-screenshot", "spectacle", "maim"):
            if shutil.which(tool):
                return tool
        return None
