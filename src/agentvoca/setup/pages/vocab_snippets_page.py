"""Vocabulary & snippets page — inline tables + file paths."""

from __future__ import annotations

from PySide6 import QtWidgets

from agentvoca.setup.pages.base import ConfigPage


def _to_table(items: list[str]) -> list[list[str]]:
    return [[item] for item in items]


def _from_table(table: list[list[str]]) -> list[str]:
    return [row[0].strip() for row in table if row and row[0].strip()]


class VocabSnippetsPage(ConfigPage):
    title = "Vocabulary & snippets"
    subtitle = (
        "Vocabulary: terms the ASR should preserve verbatim. "
        "Snippets: short triggers that expand to longer phrases."
    )

    def _build(self) -> None:
        super()._build()
        layout = self._body_layout

        # Vocabulary
        vocab_group = QtWidgets.QGroupBox("Vocabulary")
        v_layout = QtWidgets.QVBoxLayout(vocab_group)
        self._vocab_file = QtWidgets.QLineEdit()
        self._vocab_file.setPlaceholderText("(optional) ~/.agentvoca/vocab.txt")
        file_row = QtWidgets.QHBoxLayout()
        file_row.addWidget(QtWidgets.QLabel("File:"))
        file_row.addWidget(self._vocab_file)
        browse_v = QtWidgets.QPushButton("Browse…")
        browse_v.clicked.connect(self._on_browse_vocab)
        file_row.addWidget(browse_v)
        v_layout.addLayout(file_row)

        v_layout.addWidget(QtWidgets.QLabel("Inline terms (one per row):"))
        self._vocab_table = QtWidgets.QTableWidget(0, 1)
        self._vocab_table.setHorizontalHeaderLabels(["Term"])
        self._vocab_table.horizontalHeader().setStretchLastSection(True)
        self._vocab_table.verticalHeader().setVisible(False)
        v_layout.addWidget(self._vocab_table)

        add_row_v = QtWidgets.QHBoxLayout()
        add_v = QtWidgets.QPushButton("+ Add term")
        add_v.clicked.connect(lambda: self._add_row(self._vocab_table))
        del_v = QtWidgets.QPushButton("− Remove selected")
        del_v.clicked.connect(lambda: self._delete_selected(self._vocab_table))
        add_row_v.addWidget(add_v)
        add_row_v.addWidget(del_v)
        add_row_v.addStretch()
        v_layout.addLayout(add_row_v)
        layout.addWidget(vocab_group)

        # Snippets
        snip_group = QtWidgets.QGroupBox("Snippets (trigger → expansion)")
        s_layout = QtWidgets.QVBoxLayout(snip_group)
        self._snip_file = QtWidgets.QLineEdit()
        self._snip_file.setPlaceholderText("(optional) ~/.agentvoca/snippets.yaml")
        file_row2 = QtWidgets.QHBoxLayout()
        file_row2.addWidget(QtWidgets.QLabel("File:"))
        file_row2.addWidget(self._snip_file)
        browse_s = QtWidgets.QPushButton("Browse…")
        browse_s.clicked.connect(self._on_browse_snippets)
        file_row2.addWidget(browse_s)
        s_layout.addLayout(file_row2)

        s_layout.addWidget(QtWidgets.QLabel("Inline snippets:"))
        self._snip_table = QtWidgets.QTableWidget(0, 2)
        self._snip_table.setHorizontalHeaderLabels(["Trigger", "Expansion"])
        self._snip_table.horizontalHeader().setStretchLastSection(True)
        self._snip_table.verticalHeader().setVisible(False)
        s_layout.addWidget(self._snip_table)

        add_row_s = QtWidgets.QHBoxLayout()
        add_s = QtWidgets.QPushButton("+ Add snippet")
        add_s.clicked.connect(lambda: self._add_row(self._snip_table, cols=2))
        del_s = QtWidgets.QPushButton("− Remove selected")
        del_s.clicked.connect(lambda: self._delete_selected(self._snip_table))
        add_row_s.addWidget(add_s)
        add_row_s.addWidget(del_s)
        add_row_s.addStretch()
        s_layout.addLayout(add_row_s)
        layout.addWidget(snip_group)

        layout.addStretch()

    # ── File pickers ───────────────────────────────────────────────────

    def _on_browse_vocab(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Pick a vocab file", str(self._vocab_file.text() or "")
        )
        if path:
            self._vocab_file.setText(path)

    def _on_browse_snippets(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Pick a snippets file", str(self._snip_file.text() or "")
        )
        if path:
            self._snip_file.setText(path)

    # ── Table helpers ──────────────────────────────────────────────────

    @staticmethod
    def _add_row(table: QtWidgets.QTableWidget, cols: int = 1) -> None:
        table.setRowCount(table.rowCount() + 1)

    @staticmethod
    def _delete_selected(table: QtWidgets.QTableWidget) -> None:
        rows = sorted({i.row() for i in table.selectedIndexes()}, reverse=True)
        for row in rows:
            table.removeRow(row)

    @staticmethod
    def _read_table(table: QtWidgets.QTableWidget) -> list[list[str]]:
        result: list[list[str]] = []
        for row in range(table.rowCount()):
            cells: list[str] = []
            for col in range(table.columnCount()):
                item = table.item(row, col)
                cells.append(item.text() if item else "")
            if any(cell.strip() for cell in cells):
                result.append(cells)
        return result

    # ── Load / save ────────────────────────────────────────────────────

    def load_from_controller(self) -> None:
        c = self.controller.draft
        self._vocab_file.setText(c.vocabulary.path or "")
        self._fill_table(self._vocab_table, [[t] for t in c.vocabulary.inline])
        self._snip_file.setText(c.snippets.path or "")
        # snippets.path points to YAML — we don't try to read it; the user
        # manages that file separately. Inline snippets from the config are
        # shown as a hint.
        inline_snippets: list[list[str]] = []
        # No inline snippets field on the schema, but the SnippetExpander
        # constructor accepts a dict. We surface path-only inline editing
        # by leaving the table empty if no inline data is present.
        self._fill_table(self._snip_table, inline_snippets)

    def save_to_controller(self) -> None:
        vocab_inline = [row[0].strip() for row in self._read_table(self._vocab_table)]
        self.controller.update_section(
            vocabulary={
                "path": self._vocab_file.text().strip() or None,
                "inline": [v for v in vocab_inline if v],
            },
            snippets={
                "path": self._snip_file.text().strip() or None,
            },
        )

    @staticmethod
    def _fill_table(table: QtWidgets.QTableWidget, rows: list[list[str]]) -> None:
        table.setRowCount(len(rows))
        for row_idx, cells in enumerate(rows):
            for col_idx, value in enumerate(cells):
                table.setItem(row_idx, col_idx, QtWidgets.QTableWidgetItem(value))
