"""Unit tests for the OpenAI-compatible vision provider (v3)."""

import os

import pytest

import src.agentvoca.vision.openai_compatible as vision_module
from agentvoca.config.schema import VisionConfig
from agentvoca.core.types import VisionContext
from agentvoca.utils.errors import VisionError
from agentvoca.vision.openai_compatible import OpenAICompatibleVisionProvider


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

    monkeypatch.setattr(vision_module.httpx, "AsyncClient", _factory)


def test_is_available_requires_api_key() -> None:
    config = VisionConfig(
        enabled=True,
        endpoint="https://api.example.com/v1",
        api_key_env="MISSING_VISION_KEY",
    )
    provider = OpenAICompatibleVisionProvider(config)
    assert provider.is_available() is False


def test_is_available_with_api_key() -> None:
    os.environ["_agentvoca_VISION_KEY"] = "test"
    try:
        config = VisionConfig(
            enabled=True,
            endpoint="https://api.example.com/v1",
            api_key_env="_agentvoca_VISION_KEY",
        )
        provider = OpenAICompatibleVisionProvider(config)
        assert provider.is_available() is True
    finally:
        del os.environ["_agentvoca_VISION_KEY"]


@pytest.mark.asyncio
async def test_extract_builds_image_payload(monkeypatch):
    payload = {"choices": [{"message": {"content": "| A | B |"}}]}
    clients: list[DummyClient] = []
    _patch_client(monkeypatch, payload, clients)

    config = VisionConfig(enabled=True, endpoint="https://api.example.com/v1")
    provider = OpenAICompatibleVisionProvider(config)

    result = await provider.extract(
        b"\x89PNG\r\n\x1a\nfakeimage",
        instruction="make a table of the expenses",
        context=VisionContext(instruction="make a table of the expenses"),
    )

    assert result == "| A | B |"
    assert len(clients) == 1
    url, body, headers = clients[0].calls[0]
    assert url == "https://api.example.com/v1/chat/completions"
    # System prompt + a user message whose content carries an image block.
    assert body["messages"][0]["role"] == "system"
    user_content = body["messages"][1]["content"]
    image_blocks = [b for b in user_content if b["type"] == "image_url"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["image_url"]["url"].startswith("data:image/png;base64,")
    # The instruction text is included as a text block.
    text_blocks = [b for b in user_content if b["type"] == "text"]
    assert text_blocks and "expenses" in text_blocks[0]["text"]


@pytest.mark.asyncio
async def test_extract_empty_image_raises() -> None:
    config = VisionConfig(enabled=True, endpoint="https://api.example.com/v1")
    provider = OpenAICompatibleVisionProvider(config)
    with pytest.raises(VisionError):
        await provider.extract(b"", instruction="x")


@pytest.mark.asyncio
async def test_extract_malformed_response_raises(monkeypatch):
    clients: list[DummyClient] = []
    _patch_client(monkeypatch, {"unexpected": True}, clients)
    config = VisionConfig(enabled=True, endpoint="https://api.example.com/v1")
    provider = OpenAICompatibleVisionProvider(config)
    with pytest.raises(VisionError):
        await provider.extract(b"image-bytes", instruction="x")
