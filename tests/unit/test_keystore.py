"""Tests for saved API keys (keystore)."""

from __future__ import annotations

import json

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from agentvoca import keystore


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self.store:
            raise PasswordDeleteError(username)
        del self.store[(service, username)]


@pytest.fixture
def memory_keyring(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("TEST_KEY", raising=False)
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    keystore._injected.clear()
    keystore._session_only.clear()
    yield backend
    keyring.set_keyring(previous)
    keystore._injected.clear()
    keystore._session_only.clear()


def test_saved_key_survives_restart(memory_keyring, monkeypatch, tmp_path):
    assert keystore.save_key("TEST_KEY", "sk-secret-1234") is True
    assert memory_keyring.store[("agentvoca", "TEST_KEY")] == "sk-secret-1234"
    index = (tmp_path / ".agentvoca" / "keys.json").read_text(encoding="utf-8")
    assert "sk-secret" not in index
    assert json.loads(index)["keys"][0]["name"] == "TEST_KEY"

    # Simulate a new process: env var gone, saved key reloaded.
    monkeypatch.delenv("TEST_KEY")
    keystore._injected.clear()
    assert keystore.load_saved_keys() == ["TEST_KEY"]
    import os

    assert os.environ["TEST_KEY"] == "sk-secret-1234"
    assert keystore.key_status("TEST_KEY").source == "saved"


def test_environment_variable_takes_precedence(memory_keyring, monkeypatch):
    keystore.save_key("TEST_KEY", "saved-value")
    monkeypatch.setenv("TEST_KEY", "from-shell")
    keystore._injected.clear()
    assert keystore.load_saved_keys() == []
    import os

    assert os.environ["TEST_KEY"] == "from-shell"


def test_delete_removes_store_index_and_env(memory_keyring):
    import os

    keystore.save_key("TEST_KEY", "sk-1234")
    keystore.delete_key("TEST_KEY")
    assert memory_keyring.store == {}
    assert "TEST_KEY" not in os.environ
    assert keystore.key_status("TEST_KEY").source is None


def test_delete_keeps_users_own_env_var(memory_keyring, monkeypatch):
    import os

    monkeypatch.setenv("TEST_KEY", "from-shell")
    keystore.delete_key("TEST_KEY")
    assert os.environ["TEST_KEY"] == "from-shell"
    assert keystore.key_status("TEST_KEY").source == "environment"


def test_session_only_key_is_not_persisted(memory_keyring):
    import os

    assert keystore.save_key("TEST_KEY", "sk-1234", keystore.KEEP_SESSION) is False
    assert memory_keyring.store == {}
    assert keystore.key_status("TEST_KEY").source == "session"
    keystore.forget_session_keys()
    assert "TEST_KEY" not in os.environ


def test_expired_key_is_purged(memory_keyring, monkeypatch):
    keystore.save_key("TEST_KEY", "sk-1234", "7d")
    status = keystore.key_status("TEST_KEY")
    assert status.expires_at is not None
    assert keystore.purge_expired(now=status.expires_at - 1) == []
    assert keystore.purge_expired(now=status.expires_at + 1) == ["TEST_KEY"]
    assert memory_keyring.store == {}


def test_no_credential_store_falls_back_to_session(memory_keyring, monkeypatch):
    monkeypatch.setattr(keystore, "_keyring", lambda: None)
    assert keystore.save_key("TEST_KEY", "sk-1234") is False
    assert keystore.key_status("TEST_KEY").source == "session"


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        (None, "OPENAI_API_KEY"),
        ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
        ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
        ("http://localhost:11434/v1", None),
        ("https://llm.example.com/v1", "AGENTVOCA_CLEANUP_API_KEY"),
    ],
)
def test_default_key_env(endpoint, expected):
    assert keystore.default_key_env(endpoint, "cleanup") == expected
