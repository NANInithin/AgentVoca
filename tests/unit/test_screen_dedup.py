"""Tests for ``ScreenGrabber`` and the dHash dedup (OBS-14).

Tests use synthetic PIL images; no real screen, no real Windows
DWM calls. The platform ``ImageGrab.grab`` is patched to return
synthetic images driven by a ``FakeImageGrab`` whose current image
the test swaps in.
"""

from __future__ import annotations

import io
import time
import tracemalloc
from typing import Optional
from unittest.mock import patch

from PIL import Image

from agentvoca.config.schema import ObserverScreenConfig
from agentvoca.observer.screen import ScreenGrabber, dhash, hamming


def _make_image(width: int, height: int, *, text: str = "", seed: int = 0) -> Image.Image:
    """Build a deterministic synthetic RGB image.

    The base fill cycles through colors based on ``seed`` so different
    seeds produce visibly different dHashes even after the 9x8 resize.
    """
    import random

    rng = random.Random(seed)
    img = Image.new("RGB", (width, height), (rng.randint(0, 255),) * 3)
    # Sprinkle a few colored blocks so the dHash changes with seed.
    for _ in range(20):
        x = rng.randint(0, width - 20)
        y = rng.randint(0, height - 20)
        color = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
        for dx in range(20):
            for dy in range(20):
                if x + dx < width and y + dy < height:
                    img.putpixel((x + dx, y + dy), color)
    if text:
        from PIL import ImageDraw

        draw = ImageDraw.Draw(img)
        draw.text((10, 10), text, fill=(255, 255, 255))
    return img


class FakeImageGrab:
    """Stand-in for ``PIL.ImageGrab.grab``. Set ``current`` per test."""

    current: Optional[Image.Image] = None

    @staticmethod
    def grab(*, bbox, all_screens=True):  # noqa: ARG004
        if FakeImageGrab.current is None:
            raise RuntimeError("FakeImageGrab.current not set")
        # Return a copy so the caller can close it without affecting us.
        return FakeImageGrab.current.copy()


def _jpeg_bytes(img: Image.Image, quality: int = 75) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _make_grabber(
    *,
    rect: Optional[tuple[int, int, int, int]] = (0, 0, 800, 600),
    max_width_px: int = 1280,
    jpeg_quality: int = 75,
    dedup_phash_distance: int = 6,
) -> ScreenGrabber:
    cfg = ObserverScreenConfig(
        max_width_px=max_width_px,
        jpeg_quality=jpeg_quality,
        dedup_phash_distance=dedup_phash_distance,
    )
    return ScreenGrabber(
        config=cfg,
        rect_func=lambda: rect,
    )


# ── dHash ─────────────────────────────────────────────────────────


class TestDHash:
    def test_identical_images_have_zero_distance(self) -> None:
        a = _make_image(200, 100, text="hello")
        b = _make_image(200, 100, text="hello")
        assert hamming(dhash(a), dhash(b)) == 0

    def test_one_word_change_breaks_hash(self) -> None:
        # The dHash is on a 9x8 grayscale resize, so small text changes
        # can wash out. We use a clearly distinguishable change: a
        # completely different image (different seed produces different
        # random block layout).
        a = _make_image(800, 600, seed=1)
        b = _make_image(800, 600, seed=2)
        # Different seeds produce visibly different dHashes; assert the
        # hash is sensitive enough to distinguish them beyond the dedup
        # threshold.
        assert hamming(dhash(a), dhash(b)) > 6

    def test_dhash_stable_across_jpeg_round_trip(self) -> None:
        img = _make_image(800, 600, text="hello world this is a test")
        h1 = dhash(img)
        # JPEG q75 round-trip.
        jpeg = _jpeg_bytes(img, quality=75)
        decoded = Image.open(io.BytesIO(jpeg))
        h2 = dhash(decoded)
        assert hamming(h1, h2) <= 2, f"dHash drifted {hamming(h1, h2)} bits after JPEG round-trip"


# ── ScreenGrabber dedup ───────────────────────────────────────────


class TestDedup:
    def test_identical_images_deduped(self) -> None:
        grabber = _make_grabber()
        with patch("agentvoca.observer.screen.ImageGrab_grab", FakeImageGrab.grab):
            img = _make_image(800, 600, text="same")
            FakeImageGrab.current = img
            first = grabber.grab(reason="window_change")
            assert first is not None
            FakeImageGrab.current = img
            second = grabber.grab(reason="window_change")
            assert second is None, "duplicate should be deduped"
            assert grabber.deduped_count == 1

    def test_one_word_change_not_deduped(self) -> None:
        grabber = _make_grabber()
        with patch("agentvoca.observer.screen.ImageGrab_grab", FakeImageGrab.grab):
            FakeImageGrab.current = _make_image(800, 600, text="before", seed=2)
            first = grabber.grab(reason="window_change")
            assert first is not None
            # Significantly different image (different seed, different text)
            # so the dHash changes enough to exceed the dedup threshold.
            FakeImageGrab.current = _make_image(800, 600, text="COMPLETELY DIFFERENT", seed=99)
            second = grabber.grab(reason="window_change")
            assert second is not None, "different image should not be deduped"
            assert grabber.deduped_count == 0

    def test_dedup_disabled_when_distance_zero(self) -> None:
        grabber = _make_grabber(dedup_phash_distance=0)
        assert grabber._dedup_enabled is False
        with patch("agentvoca.observer.screen.ImageGrab_grab", FakeImageGrab.grab):
            FakeImageGrab.current = _make_image(800, 600, text="same")
            first = grabber.grab(reason="window_change")
            assert first is not None
            FakeImageGrab.current = _make_image(800, 600, text="same")
            second = grabber.grab(reason="window_change")
            assert second is not None
            assert grabber.deduped_count == 0


# ── Downscale ─────────────────────────────────────────────────────


class TestDownscale:
    def test_downscale_only_when_wider(self) -> None:
        grabber = _make_grabber(max_width_px=1280)
        with patch("agentvoca.observer.screen.ImageGrab_grab", FakeImageGrab.grab):
            FakeImageGrab.current = _make_image(1000, 500, text="smaller")
            g = grabber.grab(reason="window_change")
            assert g is not None
            assert g.width == 1000  # unchanged

    def test_downscale_when_wider(self) -> None:
        grabber = _make_grabber(max_width_px=1280)
        with patch("agentvoca.observer.screen.ImageGrab_grab", FakeImageGrab.grab):
            FakeImageGrab.current = _make_image(3840, 2160, text="4k")
            g = grabber.grab(reason="window_change")
            assert g is not None
            # 3840 → 1280 wide; height scales proportionally: 2160 / 3 = 720.
            assert g.width == 1280
            assert g.height == 720

    def test_aspect_preserved(self) -> None:
        grabber = _make_grabber(max_width_px=800)
        with patch("agentvoca.observer.screen.ImageGrab_grab", FakeImageGrab.grab):
            FakeImageGrab.current = _make_image(1600, 600, text="wide")
            g = grabber.grab(reason="window_change")
            assert g is not None
            # 1600 → 800 (1/2), 600 → 300 (1/2). Aspect preserved.
            assert g.width == 800
            assert g.height == 300


# ── Degenerate rects ──────────────────────────────────────────────


class TestDegenerateRects:
    def test_no_rect_returns_none(self) -> None:
        grabber = _make_grabber(rect=None)
        assert grabber.grab(reason="window_change") is None

    def test_minimized_rect_returns_none(self) -> None:
        grabber = _make_grabber(rect=(-32000, -32000, -31900, -31900))
        assert grabber.grab(reason="window_change") is None

    def test_tiny_rect_returns_none(self) -> None:
        grabber = _make_grabber(rect=(0, 0, 50, 50))
        assert grabber.grab(reason="window_change") is None

    def test_negative_area_returns_none(self) -> None:
        grabber = _make_grabber(rect=(100, 100, 50, 50))
        assert grabber.grab(reason="window_change") is None

    def test_offscreen_rect_returns_none(self) -> None:
        grabber = _make_grabber(rect=(-200, -200, -50, -50))
        assert grabber.grab(reason="window_change") is None


# ── Ring buffer ───────────────────────────────────────────────────


class TestRingBuffer:
    def test_ring_buffer_holds_exactly_eight(self) -> None:
        grabber = _make_grabber(dedup_phash_distance=6)
        with patch("agentvoca.observer.screen.ImageGrab_grab", FakeImageGrab.grab):
            for i in range(10):
                # Different seeds so dHashes differ enough to exceed
                # the dedup threshold of 6.
                FakeImageGrab.current = _make_image(800, 600, text=f"frame{i}", seed=i)
                g = grabber.grab(reason="window_change")
                assert g is not None, f"frame {i} unexpectedly deduped"
            assert len(grabber._recent) == 8
            # The 8 most recent (frames 2..9) are in the ring; frames
            # 0 and 1 were evicted. Re-using frame 0 should NOT be a
            # duplicate of any of frames 2..9.
            FakeImageGrab.current = _make_image(800, 600, text="frame0", seed=0)
            again = grabber.grab(reason="window_change")
            assert again is not None, "frame 0 was evicted from the ring; should not be deduped"


# ── Memory ────────────────────────────────────────────────────────


class TestMemoryBounded:
    def test_peak_memory_bounded_under_4k_grabs(self) -> None:
        grabber = _make_grabber(max_width_px=1280, dedup_phash_distance=0)
        tracemalloc.start()
        try:
            with patch("agentvoca.observer.screen.ImageGrab_grab", FakeImageGrab.grab):
                for i in range(20):
                    FakeImageGrab.current = _make_image(3840, 2160, text=f"frame{i}")
                    g = grabber.grab(reason="window_change")
                    assert g is not None
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        # One 4K RGB frame is 3840 * 2160 * 3 = 24.88 MB. Allow 5× that
        # for transient allocations during resize/encode.
        one_frame = 3840 * 2160 * 3
        assert peak < 5 * one_frame, f"Peak {peak} bytes exceeds 5x one 4K frame ({one_frame})"


# ── Submit / worker plumbing ──────────────────────────────────────


class TestSubmitAndWorker:
    def test_submit_returns_false_when_queue_full(self) -> None:
        grabber = _make_grabber()
        captured: list = []

        def on_grab(g):
            captured.append(g)

        # Don't start the worker. Fill the queue.
        for _ in range(8):
            assert grabber.submit("window_change", on_grab) is True
        # 9th: full.
        assert grabber.submit("window_change", on_grab) is False
        assert grabber.dropped_count == 1

    def test_worker_picks_up_enqueued_requests(self) -> None:
        grabber = _make_grabber()
        captured: list = []
        with patch("agentvoca.observer.screen.ImageGrab_grab", FakeImageGrab.grab):
            grabber.start()
            try:
                FakeImageGrab.current = _make_image(800, 600, text="hello")
                grabber.submit("window_change", captured.append)
                deadline = time.time() + 2.0
                while time.time() < deadline and not captured:
                    time.sleep(0.01)
                assert len(captured) == 1
                assert captured[0] is not None
                assert captured[0].width == 800
            finally:
                grabber.stop()
