"""Unit tests for OpenAI-compatible cleanup provider."""

import os

import pytest

import src.agentvoca.cleanup.openai_compatible as openai_module
from agentvoca.cleanup.openai_compatible import OpenAICompatibleCleanupProvider
from agentvoca.config.schema import CleanupConfig
from agentvoca.core.types import CleanupContext


class DummyResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class DummyClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, json: dict, headers: dict) -> DummyResponse:
        self.calls.append((url, json, headers))
        return DummyResponse(self.payload)


def _patch_client(monkeypatch, payload: dict, holder: list[DummyClient]) -> None:
    def _factory(*args, **kwargs):
        client = DummyClient(payload)
        holder.append(client)
        return client

    monkeypatch.setattr(openai_module.httpx, "AsyncClient", _factory)


def test_is_available_requires_api_key() -> None:
    config = CleanupConfig(
        provider="openai_compatible",
        endpoint="https://api.example.com/v1",
        api_key_env="MISSING_KEY",
    )
    provider = OpenAICompatibleCleanupProvider(config)
    assert provider.is_available() is False


def test_is_available_with_api_key() -> None:
    os.environ["_agentvoca_TEST_KEY"] = "test"
    try:
        config = CleanupConfig(
            provider="openai_compatible",
            endpoint="https://api.example.com/v1",
            api_key_env="_agentvoca_TEST_KEY",
        )
        provider = OpenAICompatibleCleanupProvider(config)
        assert provider.is_available() is True
    finally:
        del os.environ["_agentvoca_TEST_KEY"]


@pytest.mark.asyncio
async def test_rewrite_uses_response(monkeypatch):
    payload = {
        "choices": [
            {"message": {"content": "Cleaned text"}},
        ]
    }
    clients: list[DummyClient] = []
    _patch_client(monkeypatch, payload, clients)

    config = CleanupConfig(provider="openai_compatible", endpoint="https://api.example.com/v1")
    provider = OpenAICompatibleCleanupProvider(config)

    result = await provider.rewrite(
        "hello there",
        context=CleanupContext(style="technical", preserve_code=True),
    )

    assert result == "Cleaned text"
    assert len(clients) == 1
    url, body, headers = clients[0].calls[0]
    assert url == "https://api.example.com/v1/chat/completions"
    assert body["model"] == provider._model
    assert body["messages"][1]["content"] == "hello there"
    assert headers == {}


@pytest.mark.asyncio
async def test_rewrite_empty_response_falls_back(monkeypatch):
    payload = {
        "choices": [
            {"message": {"content": ""}},
        ]
    }
    clients: list[DummyClient] = []
    _patch_client(monkeypatch, payload, clients)

    config = CleanupConfig(provider="openai_compatible", endpoint="https://api.example.com/v1")
    provider = OpenAICompatibleCleanupProvider(config)

    result = await provider.rewrite("hello")
    assert result == "hello"
