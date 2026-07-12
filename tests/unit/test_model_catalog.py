"""Unit tests for the model catalog controller.

The catalog is a thin wrapper around ``GET {endpoint}/models`` that returns
a sorted list of ``ModelEntry`` rows. Tests use ``monkeypatch`` to stub out
``httpx.get`` so no real network call is made.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from agentvoca.setup.controllers.model_catalog import (
    ModelCatalog,
    ModelCatalogError,
    ModelEntry,
)


class _FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=MagicMock(), response=self)


def _openai_shape() -> dict:
    """Mimic the standard OpenAI / OpenRouter ``/v1/models`` response."""
    return {
        "data": [
            {"id": "openai/gpt-4o-mini", "pricing": {"prompt": "0.15", "completion": "0.6"}},
            {
                "id": "meta-llama/llama-3.1-8b-instruct:free",
                "pricing": {"prompt": "0", "completion": "0"},
            },
            {"id": "anthropic/claude-3.5-sonnet", "pricing": {"prompt": "3", "completion": "15"}},
            {"id": "google/gemini-flash-1.5:free", "pricing": {"prompt": 0, "completion": 0}},
        ]
    }


def test_fetch_parses_openai_shape_and_sorts_free_first():
    catalog = ModelCatalog()
    with patch.object(httpx, "get", return_value=_FakeResponse(_openai_shape())) as mock_get:
        entries = catalog.fetch("https://openrouter.ai/api/v1", "sk-test")
    assert mock_get.call_args is not None
    url = mock_get.call_args.args[0]
    assert url == "https://openrouter.ai/api/v1/models"
    # Free models first, then alphabetical.
    ids = [e.id for e in entries]
    assert ids == [
        "google/gemini-flash-1.5:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o-mini",
    ]
    # Free rows are marked.
    assert entries[0].is_free is True
    assert entries[1].is_free is True
    assert entries[2].is_free is False
    # Labels include the "(free)" tag.
    assert "(free)" in entries[0].label
    assert "(free)" not in entries[2].label


def test_fetch_sends_transcription_filter_only_for_openrouter():
    """The STT picker asks OpenRouter for transcription models via a query param.

    Other OpenAI-compatible hosts must not receive the param (some reject
    unknown query params, and their model lists are short anyway).
    """
    catalog = ModelCatalog()

    # OpenRouter: the output_modalities filter is forwarded as a query param.
    with patch.object(httpx, "get", return_value=_FakeResponse(_openai_shape())) as mock_get:
        catalog.fetch("https://openrouter.ai/api/v1", "k", output_modality="transcription")
    assert mock_get.call_args.kwargs["params"] == {"output_modalities": "transcription"}

    # Non-OpenRouter host: same request, but no query param.
    catalog.clear_cache()
    with patch.object(httpx, "get", return_value=_FakeResponse(_openai_shape())) as mock_get:
        catalog.fetch("https://api.openai.com/v1", "k", output_modality="transcription")
    assert mock_get.call_args.kwargs["params"] is None


def test_fetch_caches_separately_per_output_modality():
    catalog = ModelCatalog()
    with patch.object(httpx, "get", return_value=_FakeResponse(_openai_shape())) as mock_get:
        catalog.fetch("https://openrouter.ai/api/v1", "k")
        catalog.fetch("https://openrouter.ai/api/v1", "k", output_modality="transcription")
    # Different modality -> different cache key -> a second network call.
    assert mock_get.call_count == 2


def test_fetch_sends_bearer_header():
    catalog = ModelCatalog()
    with patch.object(httpx, "get", return_value=_FakeResponse(_openai_shape())) as mock_get:
        catalog.fetch("https://example.com/v1", "my-key")
    headers = mock_get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer my-key"
    assert headers["Accept"] == "application/json"


def test_fetch_omits_auth_header_when_no_key():
    catalog = ModelCatalog()
    with patch.object(httpx, "get", return_value=_FakeResponse(_openai_shape())) as mock_get:
        catalog.fetch("https://localhost:11434/v1", None)
    headers = mock_get.call_args.kwargs["headers"]
    assert "Authorization" not in headers


def test_fetch_strips_trailing_slash_from_endpoint():
    catalog = ModelCatalog()
    with patch.object(httpx, "get", return_value=_FakeResponse(_openai_shape())) as mock_get:
        catalog.fetch("https://example.com/v1/", "k")
    assert mock_get.call_args.args[0] == "https://example.com/v1/models"


def test_fetch_tolerates_bare_list_payload():
    """Some self-hosted servers (Ollama) return a bare JSON list."""
    payload = [
        {"id": "llama3.1:8b"},
        {"id": "qwen2.5:7b"},
    ]
    catalog = ModelCatalog()
    with patch.object(httpx, "get", return_value=_FakeResponse(payload)):
        entries = catalog.fetch("http://localhost:11434/v1", None)
    assert [e.id for e in entries] == ["llama3.1:8b", "qwen2.5:7b"]


def test_fetch_skips_rows_with_no_id():
    payload = {
        "data": [
            {"id": "good/model"},
            {"name": "missing-id"},  # skipped
            {"id": ""},  # skipped
            {"id": None},  # skipped
        ]
    }
    catalog = ModelCatalog()
    with patch.object(httpx, "get", return_value=_FakeResponse(payload)):
        entries = catalog.fetch("https://example.com/v1", "k")
    assert [e.id for e in entries] == ["good/model"]


def test_fetch_raises_on_http_error():
    catalog = ModelCatalog()
    with patch.object(httpx, "get", return_value=_FakeResponse({}, status_code=404)):
        with pytest.raises(ModelCatalogError) as exc:
            catalog.fetch("https://example.com/v1", "k")
    assert "404" in str(exc.value)


def test_fetch_raises_on_unexpected_shape():
    catalog = ModelCatalog()
    with patch.object(httpx, "get", return_value=_FakeResponse({"unexpected": "shape"})):
        with pytest.raises(ModelCatalogError):
            catalog.fetch("https://example.com/v1", "k")


def test_fetch_raises_on_empty_endpoint():
    catalog = ModelCatalog()
    with pytest.raises(ModelCatalogError):
        catalog.fetch("", "k")


def test_fetch_caches_result_per_endpoint_and_key():
    catalog = ModelCatalog()
    with patch.object(httpx, "get", return_value=_FakeResponse(_openai_shape())) as mock_get:
        catalog.fetch("https://example.com/v1", "k1")
        catalog.fetch("https://example.com/v1", "k1")
        catalog.fetch("https://example.com/v1", "k2")
    assert mock_get.call_count == 2


def test_clear_cache_drops_results():
    catalog = ModelCatalog()
    with patch.object(httpx, "get", return_value=_FakeResponse(_openai_shape())) as mock_get:
        catalog.fetch("https://example.com/v1", "k")
        catalog.clear_cache()
        catalog.fetch("https://example.com/v1", "k")
    assert mock_get.call_count == 2


def test_fetch_async_calls_callback_on_worker_thread(monkeypatch):
    catalog = ModelCatalog()
    captured: dict = {}

    def fake_fetch(endpoint, api_key, *, output_modality=None):
        captured["endpoint"] = endpoint
        captured["key"] = api_key
        captured["output_modality"] = output_modality
        return [ModelEntry(id="x", label="x", is_free=False)]

    monkeypatch.setattr(catalog, "fetch", fake_fetch)

    seen: dict = {}
    done = []

    def on_done(entries, error):
        seen["entries"] = entries
        seen["error"] = error
        done.append(True)

    catalog.fetch_async("https://example.com/v1", "k", on_done)

    # Wait briefly for the worker thread. This is a smoke test, not a perf
    # benchmark — 200 ms is more than enough for a stubbed fetch.
    import time

    for _ in range(20):
        if done:
            break
        time.sleep(0.01)

    assert done, "callback was never invoked"
    assert seen["error"] is None
    assert seen["entries"] and seen["entries"][0].id == "x"
    assert captured["endpoint"] == "https://example.com/v1"
