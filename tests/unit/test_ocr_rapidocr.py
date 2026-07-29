"""Tests for the RapidOCR provider (OBS-16).

The provider wraps the ``rapidocr_onnxruntime`` package, which is
heavy (ONNX runtime + ~15 MB of models). We never load it for real in
CI — the engine is monkey-patched in every test. The contract is
small: read-order sort, empty result, raising engine, lazy import,
and ``intra_op_num_threads=1`` is actually passed to the engine.
"""

from __future__ import annotations

import asyncio
import sys
import types
from typing import Optional

import pytest

from agentvoca.config.schema import ObserverOCRConfig
from agentvoca.observer.ocr.rapidocr import RapidOCRProvider


class _FakeEngine:
    """Stand-in for the real ``RapidOCR`` engine. ``next_result`` controls return."""

    last_constructor_kwargs: dict = {}

    def __init__(self, *args, **kwargs) -> None:
        _FakeEngine.last_constructor_kwargs = kwargs
        # Do NOT reset next_result or raise_on_call — the test sets
        # them after constructing the engine, but the _RapidOCR wrapper
        # re-invokes __init__ when the engine is first built.
        if not hasattr(self, "calls"):
            self.calls: list[bytes] = []
        if not hasattr(self, "next_result"):
            self.next_result = None
        if not hasattr(self, "raise_on_call"):
            self.raise_on_call = None

    def __call__(self, image: bytes) -> Optional[tuple]:
        self.calls.append(image)
        if self.raise_on_call is not None:
            raise self.raise_on_call
        return self.next_result


def _install_fake_rapidocr(monkeypatch, engine: _FakeEngine) -> None:
    """Patch the lazy import so ``RapidOCR`` returns our fake engine."""
    fake_module = types.ModuleType("rapidocr_onnxruntime")

    class _RapidOCR:
        def __init__(self, *args, **kwargs):
            engine.__init__(*args, **kwargs)
            # ``RapidOCR`` is constructed and *its* instance is what the
            # provider caches. Forward __call__ to the engine so the
            # provider's ``engine(image_jpeg)`` works.
            self._engine = engine

        def __call__(self, image: bytes):
            return self._engine(image)

    fake_module.RapidOCR = _RapidOCR  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", fake_module)


# ── Contract conformance ───────────────────────────────────────────


class TestContract:
    def test_reading_order_sort(self, monkeypatch) -> None:
        engine = _FakeEngine()
        _install_fake_rapidocr(monkeypatch, engine)
        provider = RapidOCRProvider(config=ObserverOCRConfig())

        # Sort by (y, x) — top-of-image first, then left-to-right.
        # "top" at y=5 is at the top of the image, so it should be first.
        # "left" and "right" share y=10; left (x=10) comes before
        # right (x=100) in left-to-right reading order.
        engine.next_result = (
            [
                [[10, 10], [20, 10], [20, 20], [10, 20]],  # y=10 x=10: "left"
                [[100, 10], [110, 10], [110, 20], [100, 20]],  # y=10 x=100: "right"
                [[10, 5], [20, 5], [20, 15], [10, 15]],  # y=5 x=10: "top"
            ],
            ["left", "right", "top"],
            [0.9, 0.8, 0.7],
        )
        result = asyncio.run(provider.extract(b"\xff\xd8fake"))
        assert result.text == "top\nleft\nright"
        assert result.confidence is not None
        assert abs(result.confidence - 0.8) < 0.01
        assert result.engine == "rapidocr"
        assert result.latency_ms >= 0

    def test_newline_joining(self, monkeypatch) -> None:
        engine = _FakeEngine()
        _install_fake_rapidocr(monkeypatch, engine)
        provider = RapidOCRProvider(config=ObserverOCRConfig())
        engine.next_result = (
            [[[0, 0], [10, 0], [10, 10], [0, 10]]],
            ["line one", "line two"],
            [0.5, 0.6],
        )
        result = asyncio.run(provider.extract(b"\xff\xd8fake"))
        assert "\n" in result.text
        assert "line one" in result.text
        assert "line two" in result.text

    def test_empty_result_returns_empty_text(self, monkeypatch) -> None:
        engine = _FakeEngine()
        _install_fake_rapidocr(monkeypatch, engine)
        provider = RapidOCRProvider(config=ObserverOCRConfig())

        # Engine returns None (blank image).
        engine.next_result = None
        result = asyncio.run(provider.extract(b"\xff\xd8fake"))
        assert result.text == ""
        assert result.confidence is None
        assert result.engine == "rapidocr"

        # Engine returns empty lists.
        engine.next_result = ([], [], [])
        result = asyncio.run(provider.extract(b"\xff\xd8fake"))
        assert result.text == ""

    def test_raising_engine_propagates(self, monkeypatch) -> None:
        engine = _FakeEngine()
        _install_fake_rapidocr(monkeypatch, engine)
        provider = RapidOCRProvider(config=ObserverOCRConfig())
        engine.raise_on_call = RuntimeError("engine failed")
        with pytest.raises(RuntimeError, match="engine failed"):
            asyncio.run(provider.extract(b"\xff\xd8fake"))

    def test_confidence_normalized_when_above_one(self, monkeypatch) -> None:
        engine = _FakeEngine()
        _install_fake_rapidocr(monkeypatch, engine)
        provider = RapidOCRProvider(config=ObserverOCRConfig())
        # Engine returns scores in 0-100.
        engine.next_result = (
            [[[0, 0], [10, 0], [10, 10], [0, 10]]],
            ["text"],
            [80.0],  # 80% in 0-100 scale
        )
        result = asyncio.run(provider.extract(b"\xff\xd8fake"))
        assert result.confidence is not None
        assert 0.79 < result.confidence < 0.81


# ── Lazy import ────────────────────────────────────────────────────


class TestLazyImport:
    def test_rapidocr_not_imported_at_construction(self, monkeypatch) -> None:
        # Just constructing the provider must not construct the engine.
        # We use the absence of a side-effect: the fake engine's
        # constructor is the only thing that would record a build.
        engine = _FakeEngine()
        _install_fake_rapidocr(monkeypatch, engine)
        RapidOCRProvider(config=ObserverOCRConfig())
        # The engine's __init__ was never called — the provider is lazy.
        # _FakeEngine.last_constructor_kwargs stays empty.
        assert _FakeEngine.last_constructor_kwargs == {}

    def test_rapidocr_imported_on_first_extract(self, monkeypatch) -> None:
        engine = _FakeEngine()
        _install_fake_rapidocr(monkeypatch, engine)
        provider = RapidOCRProvider(config=ObserverOCRConfig())
        # Pre-condition: the engine has not been built yet.
        assert _FakeEngine.last_constructor_kwargs == {}
        engine.next_result = None
        asyncio.run(provider.extract(b"\xff\xd8fake"))
        # Post-condition: the engine was built (its constructor ran).
        assert "intra_op_num_threads" in _FakeEngine.last_constructor_kwargs


# ── Configuration ──────────────────────────────────────────────────


class TestConfiguration:
    def test_intra_op_num_threads_passed(self, monkeypatch) -> None:
        engine = _FakeEngine()
        _install_fake_rapidocr(monkeypatch, engine)
        provider = RapidOCRProvider(config=ObserverOCRConfig())
        engine.next_result = None
        asyncio.run(provider.extract(b"\xff\xd8fake"))
        # The provider must pass intra_op_num_threads=1 to bound the
        # ONNX thread pool to one thread.
        assert _FakeEngine.last_constructor_kwargs.get("intra_op_num_threads") == 1

    def test_warm_up_does_not_raise_on_engine_failure(self, monkeypatch) -> None:
        engine = _FakeEngine()
        _install_fake_rapidocr(monkeypatch, engine)
        provider = RapidOCRProvider(config=ObserverOCRConfig())
        engine.raise_on_call = RuntimeError("warm-up failed")
        # warm_up() must swallow the error.
        asyncio.run(provider.warm_up())
