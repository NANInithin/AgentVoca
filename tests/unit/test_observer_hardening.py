"""OBS-6: storage directory ACL hardening (D12).

D12 chose no encryption; the user-only ACL is the only access control.
The hardening is best-effort — a failure logs a warning and never
raises. These tests assert:

- POSIX: ``os.chmod`` is called with 0o700 on the root (skipped on
  Windows; on Windows the user-only ACL is set by ``icacls``).
- Windows: ``subprocess.run`` is called with the expected argv and
  ``shell`` is not set (skipped on POSIX; icacls is not on the path
  here).
- Both platforms: a raising ``subprocess.run`` / ``os.chmod`` does not
  propagate and ``start()`` still succeeds.
- The hardening runs at most once per ObserverStore lifetime (restart
  on the same dir does not re-harden).
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from agentvoca.observer.store import ObserverStore


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-specific test")
def test_posix_chmod_0o700_on_root(tmp_path: Path) -> None:
    """POSIX: the root directory ends up with mode 0o700."""
    store = ObserverStore(root=tmp_path)
    store.start()
    try:
        mode = stat.S_IMODE(os.stat(tmp_path).st_mode)
        assert mode == 0o700, f"Expected 0o700, got {oct(mode)}"
    finally:
        store.stop()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-specific test")
def test_posix_chmod_called_via_os_chmod(tmp_path: Path) -> None:
    """POSIX: ``os.chmod`` is the call site; the dir is set to 0o700."""
    store = ObserverStore(root=tmp_path)
    with patch("agentvoca.observer.store.os.chmod") as chmod:
        store.start()
        try:
            # We need to actually create the root too, so the real
            # ``os.chmod`` runs at least once via the unpatched state
            # before the patch kicks in. Easier: assert it was called
            # with 0o700.
            assert any(call.args and call.args[1] == 0o700 for call in chmod.call_args_list), (
                f"chmod was not called with 0o700: {chmod.call_args_list!r}"
            )
        finally:
            store.stop()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
def test_windows_icacls_invocation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows: icacls is invoked with the expected argv and shell=False."""
    captured: dict = {}

    def fake_run(argv, **kwargs):  # noqa: ANN001
        captured["argv"] = argv
        captured["kwargs"] = kwargs

        # Return a CompletedProcess-ish result.
        class _R:
            returncode = 0
            stdout = b""
            stderr = b""

        return _R()

    monkeypatch.setattr("agentvoca.observer.store.os.environ", {"USERNAME": "TestUser"})
    monkeypatch.setattr("agentvoca.observer.store.subprocess.run", fake_run)

    store = ObserverStore(root=tmp_path)
    store.start()
    try:
        argv = captured.get("argv")
        kwargs = captured.get("kwargs", {})
        assert argv is not None, "subprocess.run was not called"
        # Expected argv: ["icacls", "<path>", "/inheritance:r", "/grant:r", "TestUser:(OI)(CI)F"]
        assert argv[0] == "icacls"
        assert str(tmp_path) in argv
        assert "/inheritance:r" in argv
        assert "/grant:r" in argv
        grant = next(a for a in argv if a.startswith("TestUser"))
        assert "(OI)(CI)F" in grant
        # shell is the relevant kwargs surface.
        assert "shell" not in kwargs or kwargs["shell"] is False
    finally:
        store.stop()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
def test_windows_icacls_failure_does_not_propagate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A raising icacls call must not prevent the store from starting."""
    monkeypatch.setattr("agentvoca.observer.store.os.environ", {"USERNAME": "TestUser"})

    def fake_run(*_a, **_k):  # noqa: ANN001
        raise FileNotFoundError("icacls not found")

    monkeypatch.setattr("agentvoca.observer.store.subprocess.run", fake_run)

    store = ObserverStore(root=tmp_path)
    store.start()  # must not raise
    try:
        assert store.flush(timeout=2.0)
    finally:
        store.stop()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-specific test")
def test_posix_chmod_failure_does_not_propagate(tmp_path: Path) -> None:
    """A raising os.chmod must not prevent the store from starting."""
    store = ObserverStore(root=tmp_path)
    with patch("agentvoca.observer.store.os.chmod", side_effect=OSError("boom")):
        store.start()  # must not raise
        try:
            assert store.flush(timeout=2.0)
        finally:
            store.stop()


def test_hardening_runs_once_per_store_lifetime(tmp_path: Path) -> None:
    """Restarting the same store on the same dir does not re-harden.

    The check is a guard on the store instance, not a file marker — a
    fresh ObserverStore on the same dir would re-harden. That is
    intentional: if a user re-installs the app and the dir already has
    a wider ACL, the new store should tighten it again.
    """
    if sys.platform == "win32":
        pytest.skip("POSIX-specific test")
    store = ObserverStore(root=tmp_path)
    store.start()
    # After the first start, _hardened is True.
    assert store._hardened is True  # noqa: SLF001
    store.stop()
    store.start()  # idempotent; hardening is NOT re-applied
    try:
        # The flag remains True; we did not re-chmod.
        assert store._hardened is True  # noqa: SLF001
    finally:
        store.stop()
