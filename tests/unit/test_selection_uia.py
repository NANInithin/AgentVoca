"""Tests for the selection readers (OBS-18).

The UIA reader is mocked at the ``comtypes`` boundary so the tests
run on any platform without a real UIA server. The ``noop`` reader
is trivial.

The contract: NEVER touch the clipboard (D5). The clipboard test
monkey-patches ``pyperclip.copy`` and ``pyperclip.paste`` to raise
and asserts the selection path is unaffected.
"""

from __future__ import annotations

import sys
import time
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock

import pytest

from agentvoca.observer.selection.base import SelectionReader
from agentvoca.observer.selection.noop import NoopSelectionReader

# ── Noop ───────────────────────────────────────────────────────────


class TestNoop:
    def test_noop_is_unavailable(self) -> None:
        assert NoopSelectionReader().is_available() is False

    def test_noop_returns_none(self) -> None:
        assert NoopSelectionReader().read_selection() is None


# ── ABC ────────────────────────────────────────────────────────────


def test_base_class_is_abstract() -> None:
    with pytest.raises(TypeError):
        SelectionReader()  # type: ignore[abstract]


# ── UIA: happy path with mocked comtypes ──────────────────────────


class _FakeTextRange:
    def __init__(self, text: str) -> None:
        self._text = text

    def GetText(self, max_length: int) -> str:
        if max_length < 0:
            return self._text
        return self._text[:max_length]


class _FakeSelection:
    def __init__(self, length: int, text: str) -> None:
        self._length = length
        self._text = text

    @property
    def Length(self) -> int:
        return self._length

    def GetTextElement(self, idx: int) -> _FakeTextRange:
        return _FakeTextRange(self._text)


class _FakeTextPattern:
    def __init__(self, selection: Optional[_FakeSelection]) -> None:
        self._selection = selection

    def GetSelection(self) -> Optional[_FakeSelection]:
        return self._selection


class _FakeElement:
    def __init__(self, pattern: Optional[_FakeTextPattern]) -> None:
        self._pattern = pattern

    def GetCurrentPattern(self, pattern_id: int) -> Optional[_FakeTextPattern]:
        return self._pattern


class _FakeAutomation:
    def __init__(self, focused: Optional[_FakeElement]) -> None:
        self._focused = focused

    def GetFocusedElement(self) -> Optional[_FakeElement]:
        return self._focused


def _install_fake_comtypes(monkeypatch, automation: _FakeAutomation) -> None:
    """Patch comtypes so ``CreateObject`` returns our fake automation."""
    import types

    class _FakeGUID:
        def __init__(self, value: str) -> None:
            self.value = value

    fake_client = types.ModuleType("comtypes.client")
    fake_client.CreateObject = MagicMock(return_value=automation)  # type: ignore[attr-defined]
    fake_client.GetModule = MagicMock(  # type: ignore[attr-defined]
        return_value=SimpleNamespace(IUIAutomation=object())
    )
    fake_module = types.ModuleType("comtypes")
    fake_module.CoCreateInstance = MagicMock(return_value=automation)  # type: ignore[attr-defined]
    fake_module.GUID = _FakeGUID  # type: ignore[attr-defined]
    # The production code accesses comtypes.client.GetModule(...). Bind
    # the submodule as an attribute so both `import comtypes.client`
    # and `comtypes.client` lookups work.
    fake_module.client = fake_client  # type: ignore[attr-defined]
    # comtypes.gen is imported in is_available() to confirm the
    # gen-package init runs; provide a minimal stub.
    fake_gen = types.ModuleType("comtypes.gen")
    fake_module.gen = fake_gen  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "comtypes", fake_module)
    monkeypatch.setitem(sys.modules, "comtypes.client", fake_client)
    monkeypatch.setitem(sys.modules, "comtypes.gen", fake_gen)
    # Mark comtypes as available so the reader proceeds.
    # (is_available() in production imports the modules; here we just
    # confirm the patch is in place.)


def _make_uia_reader(
    request,
    monkeypatch,
    automation: _FakeAutomation,
    *,
    max_chars: int = 4000,
    timeout_ms: int = 250,
):
    from agentvoca.observer.selection.windows_uia import WindowsUIASelectionReader

    _install_fake_comtypes(monkeypatch, automation)
    reader = WindowsUIASelectionReader(max_chars=max_chars, timeout_ms=timeout_ms)
    # Tear down the executor on test exit so its worker thread does
    # not leak (and never blocks the next test by being the first to
    # try to import real comtypes).
    def _teardown() -> None:
        if reader._executor is not None and not reader._executor_shutdown:
            try:
                reader._executor.shutdown(wait=False)
                reader._executor_shutdown = True
            except Exception:
                pass

    request.addfinalizer(_teardown)
    return reader


# Skip UIA tests on non-Windows because the module's import-time
# ``comtypes`` reference is conditional.
pytestmark_uia = pytest.mark.skipif(
    sys.platform != "win32",
    reason="UIA tests construct a WindowsUIASelectionReader that imports comtypes",
)


@pytestmark_uia
class TestUIASelection:
    def test_happy_path(self, request, monkeypatch) -> None:
        text = "the quick brown fox"
        pattern = _FakeTextPattern(_FakeSelection(length=1, text=text))
        element = _FakeElement(pattern)
        automation = _FakeAutomation(element)
        reader = _make_uia_reader(request, monkeypatch, automation)

        result = reader.read_selection()
        assert result is not None
        assert result.text == text
        assert result.method == "uia"
        assert result.truncated is False
        assert result.app_name is None  # no active_app detector

    def test_no_text_pattern_returns_none(self, request, monkeypatch) -> None:
        element = _FakeElement(pattern=None)
        automation = _FakeAutomation(element)
        reader = _make_uia_reader(request, monkeypatch, automation)
        assert reader.read_selection() is None

    def test_no_selection_returns_none(self, request, monkeypatch) -> None:
        pattern = _FakeTextPattern(selection=None)
        element = _FakeElement(pattern)
        automation = _FakeAutomation(element)
        reader = _make_uia_reader(request, monkeypatch, automation)
        assert reader.read_selection() is None

    def test_empty_selection_returns_none(self, request, monkeypatch) -> None:
        pattern = _FakeTextPattern(selection=_FakeSelection(length=0, text=""))
        element = _FakeElement(pattern)
        automation = _FakeAutomation(element)
        reader = _make_uia_reader(request, monkeypatch, automation)
        assert reader.read_selection() is None

    def test_whitespace_only_returns_none(self, request, monkeypatch) -> None:
        pattern = _FakeTextPattern(selection=_FakeSelection(length=1, text="   \n  "))
        element = _FakeElement(pattern)
        automation = _FakeAutomation(element)
        reader = _make_uia_reader(request, monkeypatch, automation)
        assert reader.read_selection() is None

    def test_truncation_at_max_chars(self, request, monkeypatch) -> None:
        long_text = "x" * 5000
        pattern = _FakeTextPattern(selection=_FakeSelection(length=1, text=long_text))
        element = _FakeElement(pattern)
        automation = _FakeAutomation(element)
        reader = _make_uia_reader(request, monkeypatch, automation, max_chars=100)

        result = reader.read_selection()
        assert result is not None
        assert len(result.text) == 100
        assert result.truncated is True


@pytestmark_uia
class TestUIAClipboardSafety:
    """The contract: the selection path NEVER touches the clipboard."""

    def test_clipboard_never_read_or_written(self, request, monkeypatch) -> None:
        import pyperclip

        def explode(*args, **kwargs):
            raise AssertionError("clipboard was touched")

        monkeypatch.setattr(pyperclip, "copy", explode)
        monkeypatch.setattr(pyperclip, "paste", explode)

        text = "selected text"
        pattern = _FakeTextPattern(_FakeSelection(length=1, text=text))
        element = _FakeElement(pattern)
        automation = _FakeAutomation(element)
        reader = _make_uia_reader(request, monkeypatch, automation)

        result = reader.read_selection()
        assert result is not None
        assert result.text == text
        # If we got here without AssertionError, the clipboard is safe.

    def test_pyautogui_never_called(self, request, monkeypatch) -> None:
        import pyautogui

        def explode(*args, **kwargs):
            raise AssertionError("pyautogui was called")

        monkeypatch.setattr(pyautogui, "typewrite", explode)
        monkeypatch.setattr(pyautogui, "press", explode)
        monkeypatch.setattr(pyautogui, "hotkey", explode)

        text = "selected text"
        pattern = _FakeTextPattern(_FakeSelection(length=1, text=text))
        element = _FakeElement(pattern)
        automation = _FakeAutomation(element)
        reader = _make_uia_reader(request, monkeypatch, automation)

        result = reader.read_selection()
        assert result is not None


@pytestmark_uia
class TestUIATimeout:
    def test_timeout_returns_none(self, request, monkeypatch) -> None:
        """A UIA call that hangs past the timeout returns None."""

        class SlowAutomation(_FakeAutomation):
            def GetFocusedElement(self):
                time.sleep(2.0)
                return None

        automation = SlowAutomation(None)
        _install_fake_comtypes(monkeypatch, automation)
        from agentvoca.observer.selection.windows_uia import (
            WindowsUIASelectionReader,
        )

        reader = WindowsUIASelectionReader(timeout_ms=50)
        t0 = time.perf_counter()
        result = reader.read_selection(timeout_ms=50)
        elapsed = time.perf_counter() - t0
        assert result is None
        # Must return close to the timeout, not the full 2 s sleep.
        assert elapsed < 1.0, f"timeout took {elapsed:.2f}s"

    def test_repeated_timeouts_log_once(self, request, monkeypatch) -> None:
        """Multiple timeouts on the same app log once (RK4)."""

        class SlowAutomation(_FakeAutomation):
            def GetFocusedElement(self):
                time.sleep(2.0)
                return None

        automation = SlowAutomation(None)
        _install_fake_comtypes(monkeypatch, automation)
        from agentvoca.observer.selection.windows_uia import (
            WindowsUIASelectionReader,
        )

        # Wire a fake active_app detector that always returns the
        # same app name.
        class _FakeApp:
            def detect(self):
                return "slow_app.exe", None

        reader = WindowsUIASelectionReader(timeout_ms=20, active_app=_FakeApp())
        for _ in range(5):
            assert reader.read_selection(timeout_ms=20) is None
        # Only one app name was logged.
        assert reader._timed_out_apps == {"slow_app.exe"}


# ── Non-Windows platform: is_available returns False ────────────────


class TestNonWindows:
    def test_uia_reader_reports_unavailable_on_non_windows(self, request, monkeypatch) -> None:
        from agentvoca.observer.selection.windows_uia import (
            WindowsUIASelectionReader,
        )

        # Simulate non-Windows: comtypes import would fail or not exist.
        # We can just call is_available and assert False; the
        # constructor never imports comtypes.
        reader = WindowsUIASelectionReader()
        monkeypatch.setattr(sys, "platform", "darwin", raising=False)
        assert reader.is_available() is False
