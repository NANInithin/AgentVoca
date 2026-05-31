"""Unit tests for the passthrough cleanup provider."""

import pytest

from agentvoca.cleanup.none import NoneCleanupProvider


@pytest.mark.asyncio
async def test_none_cleanup_passthrough():
    provider = NoneCleanupProvider()
    assert await provider.rewrite("Hello world") == "Hello world"
    assert await provider.rewrite("  ") == "  "


def test_none_cleanup_available():
    provider = NoneCleanupProvider()
    assert provider.is_available() is True
    assert provider.get_name() == "none"
