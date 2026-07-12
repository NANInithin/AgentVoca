"""Tests for R8: persistent HTTP client in OpenAICompatibleVisionProvider.

Verifies that the vision provider reuses a single httpx.AsyncClient
across ``extract()`` and ``warm_up()`` (and that ``shutdown()`` is
idempotent and actually closes it).
"""

import pytest

import src.agentvoca.vision.openai_compatible as vision_module
from agentvoca.config.schema import VisionConfig
from agentvoca.vision.openai_compatible import OpenAICompatibleVisionProvider


class CountingClient:
    """AsyncClient-like stand-in: counts constructions, records posts."""

    construct_count = 0

    def __init__(self, *args, **kwargs):
        CountingClient.construct_count += 1
        self.posts: list[tuple] = []
        self.gets: list[tuple] = []
        self.is_closed = False

    async def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append((url, json, headers))
        return _ok_response(url)

    async def get(self, url, headers=None, timeout=None):
        self.gets.append((url, headers, timeout))
        return _ok_response(url)

    async def aclose(self):
        self.is_closed = True


def _ok_response(url):
    import httpx

    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": "vision text"}}]},
        request=httpx.Request("POST", url),
    )


class _TestableVisionProvider(OpenAICompatibleVisionProvider):
    """Subclass that uses CountingClient for its shared HTTP client."""

    def _make_client(self, *, timeout):
        return CountingClient()


def _provider(monkeypatch) -> OpenAICompatibleVisionProvider:
    """Build a vision provider backed by a counting client."""
    CountingClient.construct_count = 0
    monkeypatch.setattr(vision_module, "OpenAICompatibleVisionProvider", _TestableVisionProvider)
    config = VisionConfig(
        provider="openai_compatible",
        endpoint="https://api.example.com/v1",
        api_key_env=None,
    )
    return _TestableVisionProvider(config)


@pytest.mark.asyncio
async def test_extract_reuses_one_client(monkeypatch):
    """Three ``extract()`` calls must construct the client exactly once."""
    provider = _provider(monkeypatch)
    assert CountingClient.construct_count == 1  # built in __init__

    for _ in range(3):
        result = await provider.extract(b"\x89PNG", "describe this")
        assert result == "vision text"

    assert CountingClient.construct_count == 1, (
        f"expected 1 client construction, got {CountingClient.construct_count} "
        "(extract() should reuse self._client, not rebuild it)"
    )


@pytest.mark.asyncio
async def test_warm_up_uses_same_client(monkeypatch):
    """``warm_up()`` uses the same persistent client — no new construction."""
    provider = _provider(monkeypatch)
    assert CountingClient.construct_count == 1

    await provider.warm_up()
    assert CountingClient.construct_count == 1
    assert provider._client.gets  # the warm-up call landed on self._client


@pytest.mark.asyncio
async def test_shutdown_closes_client_and_is_idempotent(monkeypatch):
    """``shutdown()`` calls aclose() and a second call does not raise."""
    provider = _provider(monkeypatch)
    client = provider._client
    assert not client.is_closed

    await provider.shutdown()
    assert client.is_closed

    # Second call must not raise — aclose() on a closed client is a no-op.
    await provider.shutdown()
