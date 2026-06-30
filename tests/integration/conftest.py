"""Shared fixtures for integration tests in this directory."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _force_offscreen_qt():
    """Force the offscreen Qt platform so the wizard renders in CI."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    yield


@pytest.fixture
def qapp():
    """Return a single QApplication for the duration of the test."""
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
