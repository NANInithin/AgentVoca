"""Integration tests for the inline API-key widget."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6", reason="PySide6 (Qt) not available")

import keyring  # noqa: E402
from PySide6 import QtWidgets  # noqa: E402

from agentvoca import keystore  # noqa: E402
from agentvoca.setup.pages.api_key_field import ApiKeyField  # noqa: E402
from tests.unit.test_keystore import MemoryKeyring  # noqa: E402


@pytest.fixture
def memory_keyring(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("FIELD_TEST_KEY", raising=False)
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)
    keystore._injected.discard("FIELD_TEST_KEY")
    keystore._session_only.discard("FIELD_TEST_KEY")
    os.environ.pop("FIELD_TEST_KEY", None)


def test_save_and_delete_key(qapp, memory_keyring, monkeypatch):
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes,
    )
    field = ApiKeyField(lambda: "FIELD_TEST_KEY")
    assert not field._delete_btn.isEnabled()

    field._value.setText("sk-test-9876")
    field._on_save()
    assert memory_keyring.store[("agentvoca", "FIELD_TEST_KEY")] == "sk-test-9876"
    assert field._value.text() == ""
    assert "saved securely" in field._status.text()
    assert "9876" in field._status.text()
    assert field._delete_btn.isEnabled()

    field._on_delete()
    assert memory_keyring.store == {}
    assert "FIELD_TEST_KEY" not in os.environ
    assert "No API key" in field._status.text()
    field.deleteLater()


def test_commit_pending_saves_with_chosen_retention(qapp, memory_keyring):
    field = ApiKeyField(lambda: "FIELD_TEST_KEY")
    field._retention.setCurrentIndex(field._retention.findData("30d"))
    field._value.setText("sk-pending")
    field.commit_pending()
    status = keystore.key_status("FIELD_TEST_KEY")
    assert status.source == "saved"
    assert status.retention == "30d"
    assert "deleted automatically on" in field._status.text()
    field.deleteLater()


def test_local_endpoint_needs_no_key(qapp, memory_keyring):
    field = ApiKeyField(lambda: None)
    assert "does not need an API key" in field._status.text()
    field.deleteLater()
