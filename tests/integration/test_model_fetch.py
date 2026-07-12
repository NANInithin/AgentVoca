"""Integration tests for the "Fetch models…" flow on the ASR / Cleanup pages.

Two regressions covered here:

1. The worker-thread callback used to bounce back to the GUI thread via a
   bare ``QtCore.QTimer.singleShot(0, ...)`` called *from the worker
   thread itself*. That only fires if the calling thread has a running Qt
   event loop, which a plain ``threading.Thread`` never does — so the
   callback silently never ran and the "Fetch models…" button got stuck on
   "Fetching…" forever. Fixed by emitting a Qt signal instead, which Qt
   automatically queues onto the receiver's thread.
2. ``resolve_editable_combo_id`` used to compare an item's userData (the
   model id) against the combobox's currentText (the item's *label*, which
   includes a " (free)" suffix for free OpenRouter models) — the two never
   matched, so selecting a free model saved the decorated label instead of
   the bare id.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

pytest.importorskip("PySide6", reason="PySide6 (Qt) not available")

from PySide6 import QtCore  # noqa: E402

from agentvoca.setup.controllers.config_controller import load_controller  # noqa: E402
from agentvoca.setup.pages.asr_page import AsrPage  # noqa: E402


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        pass


def _run_until(app, predicate, timeout_ms: int = 3000) -> None:
    """Pump the Qt event loop until ``predicate()`` is true or we time out."""
    result = {"done": False}

    def _check() -> None:
        if predicate():
            result["done"] = True
            app.quit()

    poll = QtCore.QTimer()
    poll.timeout.connect(_check)
    poll.start(10)
    QtCore.QTimer.singleShot(timeout_ms, app.quit)
    app.exec()
    poll.stop()
    assert result["done"], "condition was never satisfied before the timeout"


def test_fetch_models_result_reaches_the_gui_thread(qapp, tmp_path: Path):
    """Regression: the fetch callback must actually populate the combobox."""
    controller = load_controller(tmp_path / "config.yaml")
    page = AsrPage(controller)
    page._cloud_btn.setChecked(True)
    page._endpoint.setText("https://openrouter.ai/api/v1")

    payload = {
        "data": [
            {"id": "openai/gpt-4o-mini", "pricing": {"prompt": "0.15", "completion": "0.6"}},
        ]
    }
    with patch.object(httpx, "get", return_value=_FakeResponse(payload)):
        page._on_fetch_models()

    _run_until(
        qapp,
        lambda: page._api_model.count() > 0 and not page._fetch_in_flight,
    )

    assert page._api_model.count() == 1
    assert page._api_model.itemData(0) == "openai/gpt-4o-mini"
    assert page._fetch_models_btn.isEnabled()  # re-enabled after fetch completes

    page.deleteLater()


def test_asr_page_warns_when_endpoint_cannot_do_speech_to_text(qapp, tmp_path: Path):
    """A chat-only host (Anthropic) must surface a visible no-STT warning."""
    controller = load_controller(tmp_path / "config.yaml")
    page = AsrPage(controller)
    page._cloud_btn.setChecked(True)

    # ``isHidden()`` reflects the explicit visibility flag regardless of
    # whether the (never-shown) page is on screen, which ``isVisible()`` would
    # require.
    # A real speech-to-text endpoint: no warning.
    page._endpoint.setText("https://api.openai.com/v1")
    assert page._endpoint_warning.isHidden()

    # Anthropic has no /audio/transcriptions route: warn.
    page._endpoint.setText("https://api.anthropic.com/v1")
    assert not page._endpoint_warning.isHidden()
    assert "speech-to-text" in page._endpoint_warning.text().lower()

    # Switching back to a valid host clears the warning again.
    page._endpoint.setText("https://api.groq.com/openai/v1")
    assert page._endpoint_warning.isHidden()

    page.deleteLater()


def test_asr_page_does_not_warn_for_openrouter(qapp, tmp_path: Path):
    """Regression: OpenRouter now has an STT endpoint, so it must NOT warn."""
    controller = load_controller(tmp_path / "config.yaml")
    page = AsrPage(controller)
    page._cloud_btn.setChecked(True)

    page._endpoint.setText("https://openrouter.ai/api/v1")
    assert page._endpoint_warning.isHidden()

    page.deleteLater()


def test_selecting_a_free_model_saves_the_bare_id_not_the_label(qapp, tmp_path: Path):
    """Regression: picking a "(free)"-tagged entry must not save the label."""
    controller = load_controller(tmp_path / "config.yaml")
    page = AsrPage(controller)
    page._cloud_btn.setChecked(True)
    page._endpoint.setText("https://openrouter.ai/api/v1")
    page._api_key_env.setText("")

    payload = {
        "data": [
            {
                "id": "meta-llama/llama-3.1-8b-instruct:free",
                "pricing": {"prompt": "0", "completion": "0"},
            },
        ]
    }
    with patch.object(httpx, "get", return_value=_FakeResponse(payload)):
        page._on_fetch_models()

    _run_until(qapp, lambda: page._api_model.count() > 0 and not page._fetch_in_flight)

    # The label carries the "(free)" suffix...
    assert "(free)" in page._api_model.itemText(0)
    page._api_model.setCurrentIndex(0)

    # ...but saving must persist the bare id, not the decorated label.
    page.save_to_controller()
    assert controller.draft.asr.model == "meta-llama/llama-3.1-8b-instruct:free"

    page.deleteLater()
