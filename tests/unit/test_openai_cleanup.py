"""Unit tests for the OpenAI-compatible cleanup provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agentvoca.cleanup.openai_compatible import OpenAICompatibleCleanupProvider
from agentvoca.config.schema import CleanupConfig
from agentvoca.utils.errors import CleanupError


@pytest.fixture
def config():
    return CleanupConfig(
        provider="openai_compatible",
        endpoint="https://api.openai.com/v1",
        model="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
    )


@pytest.fixture
def provider(config, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return OpenAICompatibleCleanupProvider(config)


@pytest.mark.asyncio
async def test_openai_cleanup_success(provider):
    """Test successful cleanup via OpenAI API."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Cleaned transcript."}}]}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await provider.rewrite("Raw transcript.")

        assert result == "Cleaned transcript."
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["messages"][1]["content"] == "Raw transcript."


@pytest.mark.asyncio
async def test_openai_cleanup_failure(provider):
    """Test API error handling."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.HTTPError("Network error")

        with pytest.raises(CleanupError) as exc:
            await provider.rewrite("Raw transcript.")
        assert "LLM cleanup request failed" in str(exc.value)


@pytest.mark.asyncio
async def test_openai_cleanup_empty_response(provider):
    """Test that it returns raw transcript if LLM returns empty."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": ""}}]}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await provider.rewrite("Original transcript.")
        assert result == "Original transcript."
