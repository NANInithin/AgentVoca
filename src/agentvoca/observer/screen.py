"""Screen capture + perceptual-hash dedup (v0.4.0, OBS-14).

Grabs the active window rect, downscales to a configurable max width,
JPEG-encodes, and computes a 64-bit difference hash for dedup. The
dHash is checked against the last eight hashes; a match (Hamming
distance ≤ ``dedup_phash_distance``) is dropped *before* OCR — the
single biggest CPU saving in the design.

Threading
---------
A single ``observer-capture`` daemon thread drains a bounded
``queue.Queue``. The capture worker is the only thread that opens
PIL images. ``grab()`` runs on the worker thread; the trigger
engine enqueues a request and continues.
"""

from __future__ import annotations

import io
import logging
import queue
import threading
import time
from collections import deque
from typing import Callable, Optional

from PIL import Image

from agentvoca.config.schema import ObserverScreenConfig
from agentvoca.context.active_app import ActiveAppDetector
from agentvoca.observer.models import Grab

logger = logging.getLogger(__name__)


# ── dHash ──────────────────────────────────────────────────────────


def dhash(image: Image.Image, hash_size: int = 8) -> int:
    """64-bit difference hash of a PIL image.

    Grayscale, resize to (hash_size + 1, hash_size), compare horizontally
    adjacent pixels, pack the bits. In-repo, no new dependency.
    """
    import numpy as np

    small = image.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
    pixels = np.asarray(small, dtype=np.int16)
    bits = pixels[:, 1:] > pixels[:, :-1]
    packed = np.packbits(bits.flatten())
    return int.from_bytes(packed.tobytes(), byteorder="big")


def hamming(a: int, b: int) -> int:
    """Hamming distance between two 64-bit hashes."""
    return bin(a ^ b).count("1")


# ── Active-window rect (Windows) ──────────────────────────────────


def _active_window_rect_windows() -> Optional[tuple[int, int, int, int]]:
    """Return ``(left, top, right, bottom)`` for the foreground window, or None.

    Prefers ``DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)`` when
    available — plain ``GetWindowRect`` includes the Win10/11 invisible
    drop-shadow border. Falls back to ``GetWindowRect``.
    """
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:  # pragma: no cover - non-Windows
        return None
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        # Try DWM extended frame bounds first.
        try:
            dwmapi = ctypes.windll.dwmapi
            DWMWA_EXTENDED_FRAME_BOUNDS = 9
            rect = wintypes.RECT()
            hr = dwmapi.DwmGetWindowAttribute(
                hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)
            )
            if hr == 0:  # S_OK
                return (rect.left, rect.top, rect.right, rect.bottom)
        except Exception:
            pass
        # Fallback: GetWindowRect.
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception as exc:
        logger.debug("Active-window rect failed: %s", exc)
    return None


# ── ScreenGrabber ──────────────────────────────────────────────────


class ScreenGrabber:
    """Grabs the active window rect, downscales, encodes JPEG, hashes.

    A single ``observer-capture`` daemon thread drains a bounded queue
    of ``(reason, result_callback)`` items. ``grab()`` runs on the
    worker thread and calls ``result_callback(grab)`` on completion.
    Bounded queue, drop-on-full — a dropped keyframe is fine.
    """

    def __init__(
        self,
        config: ObserverScreenConfig,
        active_app: Optional[ActiveAppDetector] = None,
        *,
        queue_depth: int = 8,
        clock: Callable[[], float] = time.monotonic,
        rect_func: Optional[Callable[[], Optional[tuple[int, int, int, int]]]] = None,
    ) -> None:
        self._config = config
        self._active_app = active_app
        self._queue: queue.Queue = queue.Queue(maxsize=queue_depth)
        self._thread: Optional[threading.Thread] = None
        self._dedup_threshold = config.dedup_phash_distance
        self._dedup_enabled = config.dedup_phash_distance > 0
        self._recent: deque[int] = deque(maxlen=8)
        self._deduped_count: int = 0
        self._dropped_count: int = 0
        self._clock = clock
        # ``rect_func`` is injectable so tests can stub the platform rect.
        # Default: Windows DWM extended bounds; macOS/Linux return None.
        self._rect_func = rect_func or _active_window_rect_windows
        self._unavailable_warned = False

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._worker, name="observer-capture", daemon=True)
        self._thread.start()
        logger.debug("ScreenGrabber started")

    def stop(self, timeout: float = 2.0) -> None:
        if self._thread is None:
            return
        try:
            self._queue.put_nowait(None)  # shutdown sentinel
        except queue.Full:
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            self._queue.put(None)
        self._thread.join(timeout=timeout)
        self._thread = None
        logger.debug("ScreenGrabber stopped")

    def submit(
        self,
        reason: str,
        on_grab: Callable[[Optional[Grab]], None],
    ) -> bool:
        """Enqueue a capture request. Returns False if the queue is full."""
        item = (reason, on_grab)
        try:
            self._queue.put_nowait(item)
            return True
        except queue.Full:
            self._dropped_count += 1
            return False

    @property
    def deduped_count(self) -> int:
        return self._deduped_count

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    # ── Worker ─────────────────────────────────────────────────────

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            reason, on_grab = item
            try:
                grab = self.grab(reason=reason)
            except Exception:
                logger.debug("capture worker iteration failed", exc_info=True)
                grab = None
            try:
                on_grab(grab)
            except Exception:
                logger.debug("on_grab callback raised", exc_info=True)

    def grab(self, *, reason: str) -> Optional[Grab]:
        """One capture iteration. Returns ``None`` on degenerate rect.

        Steps (order matters for OCR quality):
        1. Compute the active-window rect.
        2. Reject zero/negative area, off-screen, or tiny rects.
        3. Grab at native resolution via PIL.
        4. Compute dHash from the native image.
        5. Dedup check against the last eight hashes.
        6. Downscale to ``max_width_px`` (only if wider), LANCZOS.
        7. Encode JPEG at ``jpeg_quality``.
        """
        rect = self._rect_func()
        if rect is None:
            if not self._unavailable_warned:
                logger.debug("ScreenGrabber: no active-window rect; skipping capture")
                self._unavailable_warned = True
            return None
        left, top, right, bottom = rect
        width = right - left
        height = bottom - top
        if width < 100 or height < 100:
            return None
        # Minimized windows report (-32000, -32000).
        if left <= -32000 or top <= -32000:
            return None
        # Reject rects that are entirely off-screen.
        if right < 0 or bottom < 0:
            return None
        try:
            image = ImageGrab_grab(bbox=(left, top, right, bottom))
        except Exception as exc:
            logger.debug("PIL.ImageGrab failed: %s", exc)
            return None
        try:
            # dHash on the native image, BEFORE downscale.
            h = dhash(image) if self._dedup_enabled else 0
            if self._dedup_enabled and self._is_duplicate(h):
                self._deduped_count += 1
                return None
            # Downscale only if wider than max_width_px. Preserve aspect.
            if image.width > self._config.max_width_px:
                new_w = self._config.max_width_px
                new_h = int(image.height * (new_w / image.width))
                image = image.resize((new_w, new_h), Image.LANCZOS)
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=self._config.jpeg_quality)
            jpeg = buf.getvalue()
            # Register the hash AFTER the dedup check so a duplicate
            # does not count itself in the ring buffer.
            if self._dedup_enabled:
                self._recent.append(h)
        finally:
            image.close()
        # Foreground app name/title at grab time, if a detector is wired.
        app_name: Optional[str] = None
        window_title: Optional[str] = None
        if self._active_app is not None:
            try:
                app_name, window_title = self._active_app.detect()
            except Exception:
                logger.debug("active-app detect failed during grab", exc_info=True)
        return Grab(
            jpeg=jpeg,
            width=image.width,
            height=image.height,
            dhash=h,
            app_name=app_name,
            window_title=window_title,
        )

    def _is_duplicate(self, h: int) -> bool:
        for prev in self._recent:
            if hamming(prev, h) <= self._dedup_threshold:
                return True
        return False


def ImageGrab_grab(*, bbox: tuple[int, int, int, int]) -> Image.Image:
    """Wrapper around ``PIL.ImageGrab.grab`` so the platform side is
    swappable in tests.
    """
    from PIL import ImageGrab

    return ImageGrab.grab(bbox=bbox, all_screens=True)
