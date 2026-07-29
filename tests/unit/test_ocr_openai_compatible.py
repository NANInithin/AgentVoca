"""Tests for the OpenAI-compatible OCR provider (OBS-17).

Modeled on ``test_vision_openai_compatible.py`` and
``test_vision_persistent_client.py``. The HTTP client is replaced
with a counting fake; the JSON transport is patched via
``httpx.MockTransport``-style monkey-patching.
"""

from __future__ import annotations

from typing import Optional

import httpx
import pytest

import src.agentvoca.observer.ocr.openai_compatible as ocr_module
from agentvoca.config.schema import ObserverOCRConfig
from agentvoca.observer.ocr.openai_compatible import OpenAICompatibleOCRProvider


class CountingClient:
    """``AsyncClient``-like fake: counts constructions, records posts."""

    construct_count: int = 0

    def __init__(self, *args, **kwargs) -> None:
        CountingClient.construct_count += 1
        self.posts: list[tuple] = []
        self.gets: list[tuple] = []
        self.is_closed: bool = False
        # The next response to return.
        self.next_payload: dict = {"choices": [{"message": {"content": "extracted text"}}]}
        self.raise_on_post: Optional[Exception] = None

    async def post(self, url: str, json=None, headers=None, timeout=None):
        self.posts.append((url, json, headers))
        if self.raise_on_post is not None:
            raise self.raise_on_post
        return httpx.Response(
            200,
            json=self.next_payload,
            request=httpx.Request("POST", url),
        )

    async def get(self, url, headers=None, timeout=None):
        self.gets.append((url, headers, timeout))
        return httpx.Response(200, json={"data": []}, request=httpx.Request("GET", url))

    async def aclose(self) -> None:
        self.is_closed = True


class _TestableProvider(OpenAICompatibleOCRProvider):
    """Subclass that uses CountingClient for its HTTP client."""

    def _make_client(self, *, timeout):
        return CountingClient()


def _provider(monkeypatch) -> OpenAICompatibleOCRProvider:
    """Build a provider backed by CountingClient."""
    CountingClient.construct_count = 0
    monkeypatch.setattr(ocr_module, "OpenAICompatibleOCRProvider", _TestableProvider)
    config = ObserverOCRConfig(
        provider="openai_compatible",
        endpoint="https://api.example.com/v1",
        api_key_env=None,
    )
    return _TestableProvider(config)


# ── Availability ───────────────────────────────────────────────────


class TestAvailability:
    def test_no_endpoint_uses_default_and_is_available(self) -> None:
        # No explicit endpoint → the default OpenAI endpoint is used
        # and the provider is available (no API key required for the
        # generic URL shape; callers set api_key_env when needed).
        config = ObserverOCRConfig(provider="openai_compatible", endpoint=None)
        provider = OpenAICompatibleOCRProvider(config)
        assert provider._endpoint == "https://api.openai.com/v1"
        assert provider.is_available() is True

    def test_missing_api_key_unavailable(self, monkeypatch) -> None:
        config = ObserverOCRConfig(
            provider="openai_compatible",
            endpoint="https://api.example.com/v1",
            api_key_env="MISSING_OCR_KEY",
        )
        provider = OpenAICompatibleOCRProvider(config)
        assert provider.is_available() is False

    def test_present_api_key_available(self, monkeypatch) -> None:
        monkeypatch.setenv("_agentvoca_OCR_KEY", "test")
        config = ObserverOCRConfig(
            provider="openai_compatible",
            endpoint="https://api.example.com/v1",
            api_key_env="_agentvoca_OCR_KEY",
        )
        provider = OpenAICompatibleOCRProvider(config)
        assert provider.is_available() is True


# ── Request shape ──────────────────────────────────────────────────


class TestRequestShape:
    def test_extract_builds_image_payload(self, monkeypatch) -> None:
        provider = _provider(monkeypatch)
        client = provider._client
        client.next_payload = {"choices": [{"message": {"content": "the quick brown fox"}}]}
        import asyncio

        result = asyncio.run(provider.extract(b"\xff\xd8\xff\xe0fake_jpeg"))
        assert result.text == "the quick brown fox"
        assert result.engine == "openai_compatible"
        assert client.posts, "the OCR provider must POST to the endpoint"
        url, body, headers = client.posts[0]
        assert url == "https://api.example.com/v1/chat/completions"
        # System prompt + user message.
        assert body["messages"][0]["role"] == "system"
        user_content = body["messages"][1]["content"]
        image_blocks = [b for b in user_content if b["type"] == "image_url"]
        assert len(image_blocks) == 1
        assert image_blocks[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")

    def test_extract_empty_image_returns_empty(self, monkeypatch) -> None:
        provider = _provider(monkeypatch)
        import asyncio

        result = asyncio.run(provider.extract(b""))
        assert result.text == ""
        # No HTTP call.
        assert not provider._client.posts


# ── Error handling ─────────────────────────────────────────────────


class TestErrorHandling:
    def test_http_error_raises(self, monkeypatch) -> None:
        provider = _provider(monkeypatch)
        provider._client.raise_on_post = httpx.HTTPError("connection failed")
        import asyncio

        with pytest.raises(httpx.HTTPError):
            asyncio.run(provider.extract(b"\xff\xd8fake"))

    def test_malformed_response_raises(self, monkeypatch) -> None:
        provider = _provider(monkeypatch)
        provider._client.next_payload = {"unexpected": True}
        import asyncio

        with pytest.raises(KeyError):
            asyncio.run(provider.extract(b"\xff\xd8fake"))


# ── Persistent client (R8) ─────────────────────────────────────────


class TestPersistentClient:
    async def test_extract_reuses_one_client(self, monkeypatch) -> None:
        provider = _provider(monkeypatch)
        client = provider._client
        assert CountingClient.construct_count == 1

        for _ in range(3):
            client.next_payload = {"choices": [{"message": {"content": "text"}}]}
            await provider.extract(b"\xff\xd8fake")

        assert CountingClient.construct_count == 1, (
            "extract() should reuse self._client, not rebuild it"
        )

    async def test_warm_up_uses_same_client(self, monkeypatch) -> None:
        provider = _provider(monkeypatch)
        client = provider._client
        assert CountingClient.construct_count == 1
        await provider.warm_up()
        assert CountingClient.construct_count == 1
        assert client.gets, "the warm-up call must land on self._client"

    async def test_shutdown_closes_client_and_is_idempotent(self, monkeypatch) -> None:
        provider = _provider(monkeypatch)
        client = provider._client
        assert not client.is_closed

        await provider.shutdown()
        assert client.is_closed

        # Second call must not raise.
        await provider.shutdown()
