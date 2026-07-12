"""Model catalog — fetch the list of models available at an OpenAI-compatible
``/v1/models`` endpoint.

The wizard and settings window need a model picker so the user does not have
to memorise or hand-type model ids (a frequent source of 404s on OpenRouter
where model names drift over time). ``ModelCatalog`` wraps the
``GET {endpoint}/models`` call with the user's API key and returns a list of
``ModelEntry`` rows ready for a ``QComboBox``.

The probe is intentionally read-only and never mutates the controller. It is
called from a worker thread (via ``threading.Thread``) so the UI stays
responsive while the network round-trip is in flight; results are delivered
back to the Qt main loop via a callback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelEntry:
    """One row in the model dropdown.

    Attributes:
        id: The model id exactly as the provider returned it. This is what
            gets written into ``cleanup.model`` / ``asr.model`` / etc.
        label: A human-friendly label, including a "(free)" tag for OpenRouter
            free models so they are easy to spot.
        is_free: True when the provider marks the model as free. Used only
            for the label; the id is still authoritative.
    """

    id: str
    label: str
    is_free: bool


class ModelCatalogError(RuntimeError):
    """Raised when the catalog cannot be fetched.

    The wizard shows the message in a banner so the user knows the picker
    is empty and they can either retry or fall back to typing the id.
    """


class ModelCatalog:
    """Fetches and caches the list of models available at an endpoint.

    Usage (synchronous)::

        catalog = ModelCatalog()
        try:
            entries = catalog.fetch("https://openrouter.ai/api/v1", "sk-…")
        except ModelCatalogError as exc:
            ...

    The wizard uses :meth:`fetch_async` which runs the call on a worker
    thread and invokes ``on_done`` on the GUI thread with the result.
    """

    # Defensive timeout for a single network call. OpenRouter normally
    # responds in well under a second, but we do not want the UI to hang
    # forever if the endpoint is unreachable.
    _TIMEOUT_S: float = 8.0

    def __init__(self) -> None:
        # One cache slot keyed by (endpoint, api_key). The key includes the
        # api_key so re-pointing to a different provider does not return
        # stale data.
        self._cache: dict[tuple[str, str], list[ModelEntry]] = {}

    # ── Public API ─────────────────────────────────────────────────

    def fetch(
        self,
        endpoint: str,
        api_key: str | None,
        *,
        output_modality: str | None = None,
    ) -> list[ModelEntry]:
        """Synchronously fetch and cache the model list.

        Args:
            endpoint: Base URL with no trailing slash, e.g.
                ``"https://openrouter.ai/api/v1"``.
            api_key: Bearer token to send in the ``Authorization`` header.
                May be empty/None for providers that do not require auth
                (e.g. a local Ollama).
            output_modality: When set (e.g. ``"transcription"`` for the ASR
                model picker), filters the list to models that produce that
                output. Only OpenRouter supports this via the
                ``?output_modalities=`` query param; for other hosts it is
                ignored and the full list is returned. This is what trims
                OpenRouter's ~300 chat models down to the handful of
                speech-to-text models when choosing an ASR model.

        Returns:
            A list of ``ModelEntry`` rows. Sorted so free models come first
            (alphabetical within each group) to put the cheap options on top.

        Raises:
            ModelCatalogError: If the request fails or the response shape is
                unrecognisable.
        """
        endpoint = (endpoint or "").rstrip("/")
        if not endpoint:
            raise ModelCatalogError("Endpoint is required to fetch models.")
        key = (endpoint, api_key or "", output_modality or "")
        if key in self._cache:
            return self._cache[key]

        url = f"{endpoint}/models"
        headers: dict[str, str] = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # OpenRouter documents ``?output_modalities=transcription`` to list only
        # STT models. Other OpenAI-compatible hosts have short model lists and
        # some strict servers reject unknown query params, so we only send it to
        # OpenRouter, where it is both supported and genuinely needed.
        params: dict[str, str] | None = None
        if output_modality and "openrouter.ai" in endpoint:
            params = {"output_modalities": output_modality}

        try:
            response = httpx.get(url, headers=headers, params=params, timeout=self._TIMEOUT_S)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ModelCatalogError(
                f"Model list request failed: HTTP {exc.response.status_code} from {url}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ModelCatalogError(f"Model list request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ModelCatalogError(f"Model list response was not valid JSON: {exc}") from exc

        entries = self._parse(payload, endpoint)
        self._cache[key] = entries
        return entries

    def fetch_async(
        self,
        endpoint: str,
        api_key: str | None,
        on_done: Callable[[list[ModelEntry] | None, str | None], None],
        *,
        output_modality: str | None = None,
    ) -> None:
        """Fetch on a background thread; deliver result via ``on_done``.

        ``on_done`` receives ``(entries, error)`` — exactly one of them is
        non-None. The callback is invoked from the worker thread; the
        caller is responsible for marshalling back to the Qt main loop if
        it needs to touch widgets. ``output_modality`` is forwarded to
        :meth:`fetch` (see there).
        """
        import threading  # local import to keep the module import-cheap

        def _runner() -> None:
            try:
                entries = self.fetch(endpoint, api_key, output_modality=output_modality)
            except ModelCatalogError as exc:
                on_done(None, str(exc))
            except Exception as exc:  # last-resort safety net
                logger.exception("Unexpected error fetching model catalog")
                on_done(None, f"Unexpected error: {exc}")
            else:
                on_done(entries, None)

        threading.Thread(target=_runner, daemon=True, name="model-catalog-fetch").start()

    def clear_cache(self) -> None:
        """Drop the cached model list. Used when the user changes the endpoint."""
        self._cache.clear()

    # ── Parsing ────────────────────────────────────────────────────

    @staticmethod
    def _parse(payload: object, endpoint: str) -> list[ModelEntry]:
        """Turn a ``/v1/models`` payload into ``ModelEntry`` rows.

        Handles the OpenAI/OpenRouter shape::

            {"data": [{"id": "...", ...}, ...]}

        and tolerates the bare list shape some self-hosted servers use::

            [{"id": "..."}]

        Unknown fields are ignored; missing ``id`` is skipped with a debug
        log so a partially-misbehaving server does not blow up the wizard.
        """
        rows: list[dict] = []
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            rows = [r for r in payload["data"] if isinstance(r, dict)]
        elif isinstance(payload, list):
            rows = [r for r in payload if isinstance(r, dict)]
        else:
            raise ModelCatalogError(f"Model list response had an unexpected shape from {endpoint}.")

        entries: list[ModelEntry] = []
        for row in rows:
            model_id = row.get("id")
            if not isinstance(model_id, str) or not model_id:
                logger.debug("Skipping model entry without an id: %r", row)
                continue
            is_free = ModelCatalog._is_free(row, model_id)
            label = f"{model_id}  (free)" if is_free else model_id
            entries.append(ModelEntry(id=model_id, label=label, is_free=is_free))

        # Free models first, then alphabetical — this is the order most users
        # want when picking from a long list.
        entries.sort(key=lambda e: (not e.is_free, e.id.lower()))
        return entries

    @staticmethod
    def _is_free(row: dict, model_id: str) -> bool:
        """Best-effort free-tier detection for OpenRouter-style payloads."""
        # OpenRouter exposes ``pricing.prompt`` as a string like "0" for free
        # models and a non-zero decimal for paid ones. Some legacy entries
        # use the ``:free`` suffix in the id.
        if model_id.endswith(":free"):
            return True
        pricing = row.get("pricing")
        if isinstance(pricing, dict):
            prompt = pricing.get("prompt")
            completion = pricing.get("completion")
            # A free model has both prompt and completion priced at "0".
            if prompt in (0, "0", 0.0, "0.0") and completion in (0, "0", 0.0, "0.0"):
                return True
        return False


# ── Module-level convenience ─────────────────────────────────────────


def make_default_catalog() -> ModelCatalog:
    """Build a fresh ``ModelCatalog`` (factory used by tests)."""
    return ModelCatalog()
