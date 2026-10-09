"""Preserve all clipboard MIME formats around a temporary text paste.

Qt owns the desktop clipboard on its GUI thread. The dictation loop runs on
another thread, so requests cross a queued signal rather than touching Qt's
clipboard from the input executor.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from typing import Any

from PySide6 import QtCore, QtWidgets
from shiboken6 import isValid


class _ClipboardBridge(QtCore.QObject):
    requested = QtCore.Signal(str, object, object)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.active = False
        self.requested.connect(self._execute, QtCore.Qt.ConnectionType.QueuedConnection)

    @QtCore.Slot()
    def activate(self) -> None:
        self.active = True

    @QtCore.Slot(str, object, object)
    def _execute(self, operation: str, payload: Any, future: Future) -> None:
        try:
            clipboard = QtWidgets.QApplication.clipboard()
            if operation == "snapshot":
                mime = clipboard.mimeData()
                result = {fmt: bytes(mime.data(fmt)) for fmt in mime.formats()}
            else:
                expected_text, formats = payload
                result = False
                # Leave a later user copy intact.
                if clipboard.text() == expected_text:
                    mime = QtCore.QMimeData()
                    for fmt, value in formats.items():
                        mime.setData(fmt, QtCore.QByteArray(value))
                    clipboard.setMimeData(mime)
                    result = True
            future.set_result(result)
        except Exception as exc:
            future.set_exception(exc)


_bridge: _ClipboardBridge | None = None


def init_clipboard_bridge() -> None:
    """Initialize on the GUI thread after QApplication construction."""
    global _bridge
    app = QtWidgets.QApplication.instance()
    if (_bridge is None or not isValid(_bridge)) and app is not None:
        _bridge = _ClipboardBridge(app)
        QtCore.QTimer.singleShot(0, _bridge.activate)
        bridge = _bridge
        app.aboutToQuit.connect(lambda: setattr(bridge, "active", False))


async def _request(operation: str, payload: Any = None) -> Any:
    bridge = _bridge
    if bridge is None or not isValid(bridge) or not bridge.active:
        raise RuntimeError("GUI clipboard bridge is not initialized")
    future: Future = Future()
    bridge.requested.emit(operation, payload, future)
    return await asyncio.wait_for(asyncio.wrap_future(future), timeout=2.0)


async def snapshot() -> dict[str, bytes]:
    """Take a complete MIME snapshot before replacing clipboard content."""
    return await _request("snapshot")


async def restore_if_ours(text: str, formats: dict[str, bytes]) -> bool:
    """Restore a snapshot only if the clipboard still contains our paste."""
    return await _request("restore", (text, formats))
