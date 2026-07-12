"""Tests for resolve_editable_combo_id.

Regression: the combobox is populated with ``addItem(label, id)`` where the
label can differ from the id (free-tier models get a " (free)" suffix).
``currentText()`` always reflects the *label*, so resolving the id has to
map label -> userData, not compare userData against the label directly.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6", reason="PySide6 (Qt) not available")

from PySide6 import QtWidgets  # noqa: E402

from agentvoca.setup.pages._combobox_utils import resolve_editable_combo_id  # noqa: E402


def _combo() -> QtWidgets.QComboBox:
    combo = QtWidgets.QComboBox()
    combo.setEditable(True)
    combo.addItem("openai/gpt-4o-mini  (free)", "openai/gpt-4o-mini")
    combo.addItem("gpt-4o", "gpt-4o")
    return combo


def test_selected_free_entry_resolves_to_the_bare_id(qapp):
    combo = _combo()
    combo.setCurrentIndex(0)
    assert resolve_editable_combo_id(combo) == "openai/gpt-4o-mini"


def test_selected_non_free_entry_resolves_to_its_id(qapp):
    combo = _combo()
    combo.setCurrentIndex(1)
    assert resolve_editable_combo_id(combo) == "gpt-4o"


def test_hand_typed_custom_id_is_preserved(qapp):
    combo = _combo()
    combo.setEditText("some/custom-model")
    assert resolve_editable_combo_id(combo) == "some/custom-model"


def test_empty_combo_returns_empty_string(qapp):
    combo = QtWidgets.QComboBox()
    combo.setEditable(True)
    assert resolve_editable_combo_id(combo) == ""
