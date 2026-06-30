"""Tests for the DeviceProbe module."""

from __future__ import annotations

from agentvoca.setup.controllers.device_probe import DeviceProbe


def test_probe_caches_results(monkeypatch):
    probe = DeviceProbe()
    # First call: cache is populated.
    entries1 = probe.entries()
    # Second call: same list (cached).
    entries2 = probe.entries()
    assert entries1 is entries2


def test_probe_refresh_returns_at_least_default_entry(monkeypatch):
    """Even with no sounddevice devices, 'default' should be offered."""
    probe = DeviceProbe()
    # Force the safe_call to return [] (simulating PortAudio missing).
    import agentvoca.setup.controllers.device_probe as dp

    def fake_safe_call(fn, *a, **kw):
        return [] if fn.__name__ == "list_input_devices" else None

    monkeypatch.setattr(dp, "_safe_call", fake_safe_call)
    entries = probe.refresh()
    # The probe always inserts a "default" entry.
    assert any(e.name == "default" for e in entries)
    assert any(e.is_default for e in entries)


def test_probe_resolve_name_handles_missing_portaudio(monkeypatch):
    """When PortAudio is unavailable, ``resolve_name`` returns None."""
    import agentvoca.setup.controllers.device_probe as dp

    monkeypatch.setattr(dp, "_devices_module", lambda: None)
    assert DeviceProbe.resolve_name("anything") is None
    assert DeviceProbe.resolve_name(None) is None
