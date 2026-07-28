"""Tests for the OCR provider base class and the ``none`` provider.

The contract is small: ``extract(image_jpeg)`` returns an
``OCRResult`` and never raises on a blank image. The ``none`` provider
returns empty text in zero ms.
"""

from __future__ import annotations

import pytest

from agentvoca.config.schema import ObserverOCRConfig
from agentvoca.observer.models import OCRResult
from agentvoca.observer.ocr.base import OCRProvider
from agentvoca.observer.ocr.none import NoneOCRProvider


def test_ocr_provider_is_abstract() -> None:
    """The base class cannot be instantiated directly."""
    with pytest.raises(TypeError):
        OCRProvider(config=ObserverOCRConfig())  # type: ignore[abstract]


def test_none_ocr_returns_empty_text() -> None:
    provider = NoneOCRProvider(config=ObserverOCRConfig())
    import asyncio

    result = asyncio.run(provider.extract(b"\xff\xd8\xff\xe0fake"))
    assert isinstance(result, OCRResult)
    assert result.text == ""
    assert result.confidence is None
    assert result.engine == "none"


def test_none_ocr_never_raises() -> None:
    """The contract: a blank image is a success, not an error."""
    provider = NoneOCRProvider(config=ObserverOCRConfig())
    import asyncio

    # Even with empty bytes, no raise.
    for payload in (b"", b"\x00" * 100, b"not a real jpeg"):
        result = asyncio.run(provider.extract(payload))
        assert result.text == ""


def test_none_ocr_accepts_hint_but_ignores_it() -> None:
    provider = NoneOCRProvider(config=ObserverOCRConfig())
    import asyncio

    result = asyncio.run(provider.extract(b"x", hint="some context"))
    assert result.text == ""


def test_none_ocr_warm_up_and_shutdown_are_noop() -> None:
    provider = NoneOCRProvider(config=ObserverOCRConfig())
    import asyncio

    # Both should complete without raising.
    asyncio.run(provider.warm_up())
    asyncio.run(provider.shutdown())
