"""Small helpers shared between page widgets.

Kept in a private module so the pages don't have to import each other
just to share trivial utilities.
"""

from __future__ import annotations

from PySide6 import QtWidgets


def resolve_editable_combo_id(combo: QtWidgets.QComboBox) -> str:
    """Pick the authoritative id from an editable QComboBox.

    The combobox is populated by the model catalog with ``addItem(label,
    id)`` — the *displayed* text is the (possibly decorated, e.g. "…
    (free)") label, while the real id lives in userData. ``currentText()``
    always returns the displayed text, so when the user picks an entry from
    the dropdown we must map that label back to its userData id rather than
    using the text verbatim. When the user instead types a custom id that
    does not match any item's label, no item's text matches and we fall
    back to the typed text itself.

    Returns:
        The id string the user wants. Empty if the combobox is empty.
    """
    current_text = (combo.currentText() or "").strip()
    if not current_text:
        return ""
    for i in range(combo.count()):
        if combo.itemText(i) == current_text:
            data = combo.itemData(i)
            return str(data) if data is not None else current_text
    return current_text
