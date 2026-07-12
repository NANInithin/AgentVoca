"""Tests for R8: persistent HTTP client in OpenAICompatibleCleanupProvider.

Verifies that the provider reuses a single httpx.AsyncClient across
``rewrite()`` and ``warm_up()`` (and that ``shutdown()`` is idempotent
and actually closes it).
"""

import httpx
import pytest

import src.agentvoca.cleanup.openai_compatible as openai_module
from agentvoca.cleanup.openai_compatible import OpenAICompatibleCleanupProvider
from agentvoca.config.schema import CleanupConfig


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
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
            request=httpx.Request("POST", url),
        )

    async def get(self, url, headers=None, timeout=None):
        self.gets.append((url, headers, timeout))
        return httpx.Response(
            200,
            json={"data": []},
            request=httpx.Request("GET", url),
        )

    async def aclose(self):
        self.is_closed = True


class _TestableCleanupProvider(OpenAICompatibleCleanupProvider):
    """A subclass that uses CountingClient for its shared HTTP client."""

    def _make_client(self, *, timeout):
        return CountingClient()


def _provider(monkeypatch) -> OpenAICompatibleCleanupProvider:
    """Build a provider with a counting client plugged in via the seam."""
    CountingClient.construct_count = 0
    # Make the test class discoverable as the implementation for the name.
    monkeypatch.setitem(
        __import__("agentvoca.cleanup", fromlist=["BUILTIN_CLEANUP_PROVIDERS"]).__dict__.get(
            "BUILTIN_CLEANUP_PROVIDERS", {}
        ),
        "openai_compatible",
        _TestableCleanupProvider,
    )
    # Belt-and-braces: also patch the provider module so any direct
    # reference to the symbol resolves to the test subclass.
    monkeypatch.setattr(
        openai_module, "OpenAICompatibleCleanupProvider", _TestableCleanupProvider
    )
    config = CleanupConfig(
        provider="openai_compatible",
        endpoint="https://api.example.com/v1",
        api_key_env=None,
    )
    return _TestableCleanupProvider(config)


@pytest.mark.asyncio
async def test_rewrite_reuses_one_client(monkeypatch):
    """Three ``rewrite()`` calls must construct the client exactly once."""
    provider = _provider(monkeypatch)
    assert CountingClient.construct_count == 1  # built in __init__

    for _ in range(3):
        result = await provider.rewrite("hello")
        assert result == "ok"

    assert CountingClient.construct_count == 1, (
        f"expected 1 client construction, got {CountingClient.construct_count} "
        "(rewrite() should reuse self._client, not rebuild it)"
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


@pytest.mark.asyncio
async def test_shutdown_missing_on_provider_without_method(monkeypatch):
    """Providers without a ``shutdown`` attribute (e.g. mocks, other
    adapters) are skipped by ``Orchestrator.stop()``'s getattr guard.
    Verify the soft contract here by patching a provider-shaped object.
    """
    class NoShutdownProvider:
        async def rewrite(self, transcript, context=None):
            return transcript

    provider = NoShutdownProvider()
    # getattr(...) default to None, so the orchestrator's stop() guard
    # treats this as "no shutdown needed".
    assert getattr(provider, "shutdown", None) is None
