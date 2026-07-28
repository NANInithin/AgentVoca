"""Trigger gate and sources for Observer keyframe capture (v0.4.0, OBS-13).

The trigger gate is the single chokepoint for keyframe requests. The
four sources — window change, scroll settle, click/selection, speech
onset — all funnel through ``TriggerGate.request``. Without it, Observer
would be a firehose.

Rate limit (in order):
  1. session not active or paused  → drop
  2. foreground app/title excluded → drop
  3. ``min_interval_ms`` since the last accepted capture → drop
  4. token bucket (``max_keyframes_per_min``) → drop
  5. capture queue full → drop, count, record a gap

The gate is thread-safe; ``request()`` is called from the poll thread,
the pynput mouse listener thread, and the ambient speech-onset hook.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Optional

from agentvoca.config.schema import ObserverTriggersConfig
from agentvoca.context.active_app import ActiveAppDetector
from agentvoca.observer.models import TriggerReason
from agentvoca.observer.session import SessionManager

logger = logging.getLogger(__name__)


class TriggerGate:
    """Rate-limit keyframe requests. The only path to a screen capture.

    All four trigger sources call ``request()``. The gate enforces the
    configured rate limits. Cheap: a lock held for microseconds, a clock
    read, a few float comparisons.

    Args:
        min_interval_ms: Minimum wall-clock between two accepted
            captures. Default 4000.
        max_keyframes_per_min: Token-bucket capacity and refill target.
            Default 4.
        enqueue: Optional callable invoked with the ``TriggerReason``
            after acceptance. If it raises ``queue.Full`` the request
            is treated as dropped.
        is_session_active: Returns whether a session is open. Default true.
        is_paused: Returns whether capture is paused. Default false.
        is_excluded: Returns whether the current foreground is excluded.
            Default false.
        on_gap: Optional callback invoked with ``(reason, dropped_count)``
            when an accepted request is dropped at the enqueue boundary.
        clock: Monotonic clock function. Default ``time.monotonic``.
    """

    def __init__(
        self,
        *,
        min_interval_ms: int = 4000,
        max_keyframes_per_min: int = 4,
        enqueue: Optional[Callable[[TriggerReason], None]] = None,
        is_session_active: Optional[Callable[[], bool]] = None,
        is_paused: Optional[Callable[[], bool]] = None,
        is_excluded: Optional[Callable[[], bool]] = None,
        on_gap: Optional[Callable[[str, int], None]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._min_interval_ms = min_interval_ms
        self._capacity = max_keyframes_per_min
        self._refill_per_sec = max_keyframes_per_min / 60.0
        self._tokens = float(max_keyframes_per_min)
        # Start "infinitely in the past" so the first request always
        # passes the min-interval check AND the first call refills the
        # bucket to capacity in one go.
        self._last_accepted_t: float = -1e18
        # Time of the last refill (any call). The refill is incremental
        # from this point — a missing call does not silently accumulate
        # tokens. ``-1e18`` lets the first call add a full bucket.
        self._last_refill_t: float = -1e18
        self._lock = threading.Lock()
        self._clock = clock
        self._enqueue = enqueue
        self._is_session_active = is_session_active or (lambda: True)
        self._is_paused = is_paused or (lambda: False)
        self._is_excluded = is_excluded or (lambda: False)
        self._on_gap = on_gap
        self._dropped: int = 0
        self._accepted: int = 0

    def request(self, reason: TriggerReason) -> bool:
        """Return True if the request was accepted and enqueued."""
        if not self._is_session_active():
            return False
        if self._is_paused():
            return False
        if self._is_excluded():
            return False
        with self._lock:
            now = self._clock()
            # Refill the bucket from the LAST refill time, incrementally.
            # The first call (where last_refill_t is -inf) refills to
            # capacity. Subsequent calls add only the increment, so
            # the rate is exactly capacity/60 per second of wall clock
            # between calls.
            elapsed_refill = max(0.0, now - self._last_refill_t)
            self._tokens = min(
                self._capacity,
                self._tokens + elapsed_refill * self._refill_per_sec,
            )
            self._last_refill_t = now
            # Min-interval: too soon after the previous accepted capture.
            if (
                self._last_accepted_t > -1e17
                and (now - self._last_accepted_t) * 1000.0 < self._min_interval_ms
            ):
                return False
            # Token bucket.
            if self._tokens < 1.0:
                return False
            self._tokens -= 1.0
            self._last_accepted_t = now
            self._accepted += 1
        # Enqueue outside the lock — the enqueue callable may itself
        # acquire a queue lock briefly. We must not hold the gate lock
        # across that.
        if self._enqueue is not None:
            try:
                self._enqueue(reason)
            except queue.Full:
                self._dropped += 1
                if self._on_gap is not None:
                    try:
                        self._on_gap("capture_queue_full", 1)
                    except Exception:
                        logger.debug("on_gap callback raised", exc_info=True)
                return False
        return True

    @property
    def accepted(self) -> int:
        return self._accepted

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def tokens(self) -> float:
        """Current token count. Test affordance — not for production use."""
        with self._lock:
            return self._tokens


# ── Trigger sources / engine ───────────────────────────────────────


class TriggerEngine:
    """Owns the four trigger sources and a ``TriggerGate``.

    Threading
    ---------
    - ``observer-triggers`` (2 Hz poll): detects window/title change and
      scroll settle, fires the corresponding ``request()`` calls.
    - ``pynput.mouse.Listener`` thread: receives scroll + click events,
      stamps state, fires ``request()`` for click/selection.
    - ``observer-ambient`` thread (caller): fires ``request()`` on
      speech onset via ``on_speech_onset()``.

    The poll thread is cheap: a single ``ctypes`` call per iteration, no
    grabbing, no OCR. The pynput handlers return in microseconds.

    Args:
        config: ``ObserverTriggersConfig`` — which sources are enabled,
            the scroll-settle quiet period, etc.
        session: ``SessionManager`` — records ``focus_change`` events.
        active_app: Foreground detector reused from the context engine.
        gate: The rate-limiting ``TriggerGate``.
    """

    def __init__(
        self,
        config: ObserverTriggersConfig,
        session: SessionManager,
        active_app: ActiveAppDetector,
        gate: TriggerGate,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._session = session
        self._active_app = active_app
        self._gate = gate
        # pynput import is lazy so a non-mouse platform does not need it.
        self._mouse_listener: object | None = None
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_stop = threading.Event()
        # Shared state between pynput thread and poll thread.
        self._mouse_lock = threading.Lock()
        self._last_scroll_monotonic: float = -1e18
        self._last_app: tuple[Optional[str], Optional[str]] = (None, None)
        self._click_down_pos: Optional[tuple[int, int]] = None
        # Per-source enable flag is read by each source; flipped in the
        # spec by ``observer.triggers.*``. Default to True.
        self._window_change_enabled: bool = config.window_change
        self._scroll_settle_enabled: bool = config.scroll_settle
        self._click_selection_enabled: bool = config.click_selection
        self._speech_onset_enabled: bool = config.speech_onset
        # Injectable clock so tests can drive scroll-settle without
        # wall-clock sleeps. Defaults to ``time.monotonic``.
        self._clock = clock

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(self) -> None:
        """Start the poll thread and the mouse listener. Idempotent."""
        if self._poll_thread is not None and self._poll_thread.is_alive():
            return
        # Mouse listener — only construct if any click/scroll source is on.
        if self._scroll_settle_enabled or self._click_selection_enabled:
            try:
                from pynput import mouse  # noqa: PLC0415
            except Exception as exc:  # pragma: no cover - pynput always present
                logger.debug("pynput.mouse unavailable; triggers disabled: %s", exc)
            else:
                self._mouse_listener = mouse.Listener(
                    on_click=self._on_click, on_scroll=self._on_scroll
                )
                self._mouse_listener.start()
        self._poll_stop.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="observer-triggers", daemon=True
        )
        self._poll_thread.start()
        logger.debug("TriggerEngine started")

    def stop(self) -> None:
        """Stop the poll thread and the mouse listener. Idempotent."""
        self._poll_stop.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=2.0)
            self._poll_thread = None
        if self._mouse_listener is not None:
            try:
                self._mouse_listener.stop()
            except Exception:
                logger.debug("mouse listener stop raised", exc_info=True)
            self._mouse_listener = None
        logger.debug("TriggerEngine stopped")

    # ── Public source hooks ────────────────────────────────────────

    def on_speech_onset(self) -> None:
        """Called by the AmbientListener at every IDLE→SPEAKING transition."""
        if not self._speech_onset_enabled:
            return
        self._gate.request("speech_onset")

    def on_click_down_for_test(self, x: int, y: int) -> None:
        """Inject a click-down position from tests."""
        with self._mouse_lock:
            self._click_down_pos = (x, y)

    def on_click_up_for_test(self, x: int, y: int) -> None:
        """Inject a click-up position from tests."""
        with self._mouse_lock:
            down = self._click_down_pos
            self._click_down_pos = None
        if down is None:
            return
        if not self._click_selection_enabled:
            return
        self._handle_click_release(down[0], down[1], x, y)

    def on_scroll_for_test(self) -> None:
        """Inject a scroll event from tests."""
        self._on_scroll(0, 0, 0, 1)

    def poll_once_for_test(self) -> None:
        """One iteration of the poll loop. Used by tests."""
        self._poll_once()

    def last_app_for_test(self) -> tuple[Optional[str], Optional[str]]:
        return self._last_app

    def last_scroll_monotonic_for_test(self) -> float:
        with self._mouse_lock:
            return self._last_scroll_monotonic

    # ── Mouse handlers (pynput thread) ─────────────────────────────

    def _on_scroll(self, _x: int, _y: int, _dx: int, _dy: int) -> None:
        """pynput scroll handler. Microsecond budget — just stamp a ts."""
        if not self._scroll_settle_enabled:
            return
        with self._mouse_lock:
            self._last_scroll_monotonic = self._clock()

    def _on_click(self, x: int, y: int, _button: object, pressed: bool) -> None:
        """pynput click handler. Stamps the down position, classifies the up."""
        if not self._click_selection_enabled:
            return
        if pressed:
            with self._mouse_lock:
                self._click_down_pos = (x, y)
            return
        with self._mouse_lock:
            down = self._click_down_pos
            self._click_down_pos = None
        if down is None:
            return
        self._handle_click_release(down[0], down[1], x, y)

    def _handle_click_release(self, down_x: int, down_y: int, up_x: int, up_y: int) -> None:
        if max(abs(up_x - down_x), abs(up_y - down_y)) > 5:
            self._gate.request("selection")
        else:
            self._gate.request("click")

    # ── Poll loop (2 Hz) ───────────────────────────────────────────

    def _poll_loop(self) -> None:
        while not self._poll_stop.is_set():
            try:
                self._poll_once()
            except Exception:
                logger.debug("trigger poll iteration failed", exc_info=True)
            # 500 ms = 2 Hz. ``wait`` releases the GIL so other threads
            # can run.
            self._poll_stop.wait(0.5)

    def _poll_once(self) -> None:
        # 1) Window / title change.
        if self._window_change_enabled:
            try:
                app, title = self._active_app.detect()
            except Exception:
                logger.debug("active-app detect failed", exc_info=True)
                app, title = None, None
            if (app, title) != self._last_app:
                previous_app = self._last_app[0]
                self._last_app = (app, title)
                # Always record the focus_change event. The store's
                # per-session monotonicity check will timestamp it.
                self._session.record(
                    "focus_change",
                    app_name=app,
                    window_title=title,
                    meta={"previous_app": previous_app} if previous_app else {},
                )
                self._gate.request("window_change")
        # 2) Scroll settle.
        if self._scroll_settle_enabled:
            with self._mouse_lock:
                last = self._last_scroll_monotonic
            if last > -1e17:
                quiet_ms = (self._clock() - last) * 1000.0
                if quiet_ms >= self._config.scroll_settle_ms:
                    self._gate.request("scroll_settle")
                    with self._mouse_lock:
                        # Reset so we do not fire again until the next scroll.
                        self._last_scroll_monotonic = -1e18
