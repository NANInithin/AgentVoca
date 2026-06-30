"""Advanced page — context, commands, adaptive, vision, insertion."""

from __future__ import annotations

from PySide6 import QtWidgets

from agentvoca.setup.pages.base import ConfigPage
from agentvoca.setup.pages.env_helper_dialog import EnvHelperDialog


class AdvancedPage(ConfigPage):
    title = "Advanced"
    subtitle = "Power-user features. Defaults work for most users."

    def _build(self) -> None:
        super()._build()
        layout = self._body_layout

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        inner_layout = QtWidgets.QVBoxLayout(inner)

        inner_layout.addWidget(self._build_context_group())
        inner_layout.addWidget(self._build_commands_group())
        inner_layout.addWidget(self._build_adaptive_group())
        inner_layout.addWidget(self._build_insertion_group())
        inner_layout.addWidget(self._build_vision_group())
        inner_layout.addStretch()

        scroll.setWidget(inner)
        layout.addWidget(scroll)

    # ── Per-feature groups ─────────────────────────────────────────────

    def _build_context_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Context (v2) — per-app cleanup style")
        layout = QtWidgets.QFormLayout(group)

        self._context_enabled = QtWidgets.QCheckBox("Enable context engine")
        layout.addRow("", self._context_enabled)

        self._context_read_screen = QtWidgets.QCheckBox("Allow reading screen for context")
        layout.addRow("", self._context_read_screen)
        self._context_read_clipboard = QtWidgets.QCheckBox("Allow reading clipboard for context")
        layout.addRow("", self._context_read_clipboard)

        layout.addRow(QtWidgets.QLabel("App-name glob → style:"))
        self._context_table = QtWidgets.QTableWidget(0, 2)
        self._context_table.setHorizontalHeaderLabels(["App glob", "Style"])
        self._context_table.horizontalHeader().setStretchLastSection(True)
        self._context_table.verticalHeader().setVisible(False)
        layout.addRow(self._context_table)

        row = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton("+ Add")
        add.clicked.connect(lambda: self._context_table.insertRow(self._context_table.rowCount()))
        rm = QtWidgets.QPushButton("− Remove")
        rm.clicked.connect(self._remove_context_rows)
        row.addWidget(add)
        row.addWidget(rm)
        row.addStretch()
        layout.addRow(row)

        return group

    def _build_commands_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Voice commands (v2) — 'new line', 'scratch that'…")
        layout = QtWidgets.QFormLayout(group)
        self._commands_enabled = QtWidgets.QCheckBox("Enable voice commands")
        layout.addRow("", self._commands_enabled)

        layout.addRow(QtWidgets.QLabel("Phrase overrides (one per row, format: phrase → action):"))
        self._commands_edit = QtWidgets.QPlainTextEdit()
        self._commands_edit.setPlaceholderText("scratch that → undo\nnew line → newline")
        self._commands_edit.setMaximumHeight(90)
        layout.addRow(self._commands_edit)
        return group

    def _build_adaptive_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Adaptive vocab (v2) — learn your corrections")
        layout = QtWidgets.QFormLayout(group)
        self._adaptive_enabled = QtWidgets.QCheckBox("Enable adaptive vocabulary learning")
        layout.addRow("", self._adaptive_enabled)
        self._adaptive_threshold = QtWidgets.QSpinBox()
        self._adaptive_threshold.setRange(2, 10)
        layout.addRow("Promote after N corrections:", self._adaptive_threshold)
        self._adaptive_path = QtWidgets.QLineEdit()
        self._adaptive_path.setPlaceholderText("(default) ~/.agentvoca/learned_vocab.txt")
        path_row = QtWidgets.QHBoxLayout()
        path_row.addWidget(self._adaptive_path)
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self._on_browse_adaptive)
        path_row.addWidget(browse)
        layout.addRow("Learned vocab path:", path_row)
        return group

    def _build_insertion_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Insertion")
        layout = QtWidgets.QFormLayout(group)
        self._insertion_strategy = QtWidgets.QComboBox()
        self._insertion_strategy.addItem("Keyboard (pyautogui)", "keyboard")
        self._insertion_strategy.addItem("Clipboard paste", "clipboard")
        layout.addRow("Strategy:", self._insertion_strategy)
        self._insertion_clipboard_fallback = QtWidgets.QCheckBox(
            "Fall back to clipboard if keyboard insertion fails"
        )
        layout.addRow("", self._insertion_clipboard_fallback)
        self._insertion_char_delay = QtWidgets.QSpinBox()
        self._insertion_char_delay.setRange(0, 100)
        self._insertion_char_delay.setSuffix(" ms")
        layout.addRow("Per-character delay:", self._insertion_char_delay)
        return group

    def _build_vision_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Vision (v3) — screenshot-to-text")
        layout = QtWidgets.QFormLayout(group)
        self._vision_enabled = QtWidgets.QCheckBox("Enable screenshot-to-text (vision)")
        layout.addRow("", self._vision_enabled)
        self._vision_endpoint = QtWidgets.QLineEdit()
        self._vision_endpoint.setPlaceholderText("https://openrouter.ai/api/v1")
        layout.addRow("Endpoint:", self._vision_endpoint)
        self._vision_model = QtWidgets.QLineEdit()
        self._vision_model.setPlaceholderText("openai/gpt-4o-mini")
        layout.addRow("Model:", self._vision_model)

        env_row = QtWidgets.QHBoxLayout()
        self._vision_api_key_env = QtWidgets.QLineEdit()
        self._vision_api_key_env.setPlaceholderText("OPENROUTER_API_KEY")
        env_row.addWidget(self._vision_api_key_env)
        helper = QtWidgets.QPushButton("Set API key…")
        helper.clicked.connect(self._on_vision_env_helper)
        env_row.addWidget(helper)
        layout.addRow("Env var name:", env_row)

        self._vision_timeout = QtWidgets.QSpinBox()
        self._vision_timeout.setRange(1, 300)
        self._vision_timeout.setSuffix(" s")
        layout.addRow("Capture timeout:", self._vision_timeout)

        self._vision_output_format = QtWidgets.QComboBox()
        self._vision_output_format.addItem("Auto (let the model choose)", "auto")
        self._vision_output_format.addItem("Markdown", "markdown")
        self._vision_output_format.addItem("Plain text", "plain")
        layout.addRow("Output format:", self._vision_output_format)

        layout.addRow(QtWidgets.QLabel("Anchor phrases (one per row):"))
        self._vision_anchors = QtWidgets.QPlainTextEdit()
        self._vision_anchors.setPlaceholderText("the attached screenshot\nas shown\n…")
        self._vision_anchors.setMaximumHeight(80)
        layout.addRow(self._vision_anchors)
        return group

    # ── Slots ──────────────────────────────────────────────────────────

    def _remove_context_rows(self) -> None:
        rows = sorted({i.row() for i in self._context_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._context_table.removeRow(r)

    def _on_browse_adaptive(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Pick a learned-vocab file", str(self._adaptive_path.text() or "")
        )
        if path:
            self._adaptive_path.setText(path)

    def _on_vision_env_helper(self) -> None:
        EnvHelperDialog(
            self._vision_api_key_env.text().strip() or "OPENROUTER_API_KEY", self
        ).exec()

    # ── Load / save ────────────────────────────────────────────────────

    def load_from_controller(self) -> None:
        c = self.controller.draft
        self._context_enabled.setChecked(c.context.enabled)
        self._context_read_screen.setChecked(c.context.read_screen)
        self._context_read_clipboard.setChecked(c.context.read_clipboard)
        self._context_table.setRowCount(0)
        for glob, style in c.context.profiles.items():
            row = self._context_table.rowCount()
            self._context_table.insertRow(row)
            self._context_table.setItem(row, 0, QtWidgets.QTableWidgetItem(glob))
            self._context_table.setItem(row, 1, QtWidgets.QTableWidgetItem(style))

        self._commands_enabled.setChecked(c.commands.enabled)
        self._commands_edit.setPlainText(
            "\n".join(f"{p} → {a}" for p, a in c.commands.phrases.items())
        )

        self._adaptive_enabled.setChecked(c.adaptive.enabled)
        self._adaptive_threshold.setValue(c.adaptive.promote_threshold)
        self._adaptive_path.setText(c.adaptive.learned_vocab_path or "")

        idx = self._insertion_strategy.findData(c.insertion.strategy)
        if idx >= 0:
            self._insertion_strategy.setCurrentIndex(idx)
        self._insertion_clipboard_fallback.setChecked(c.insertion.clipboard_fallback)
        self._insertion_char_delay.setValue(c.insertion.delay_between_chars_ms)

        v = c.vision
        self._vision_enabled.setChecked(v.enabled)
        self._vision_endpoint.setText(v.endpoint or "")
        self._vision_model.setText(v.model or "")
        self._vision_api_key_env.setText(v.api_key_env or "")
        self._vision_timeout.setValue(v.capture_timeout_s)
        idx = self._vision_output_format.findData(v.output_format)
        if idx >= 0:
            self._vision_output_format.setCurrentIndex(idx)
        self._vision_anchors.setPlainText("\n".join(v.anchor_phrases))

    def save_to_controller(self) -> None:
        # Context
        profiles: dict[str, str] = {}
        for row in range(self._context_table.rowCount()):
            glob_item = self._context_table.item(row, 0)
            style_item = self._context_table.item(row, 1)
            if glob_item and style_item and glob_item.text().strip():
                profiles[glob_item.text().strip()] = style_item.text().strip()
        context = {
            "enabled": self._context_enabled.isChecked(),
            "read_screen": self._context_read_screen.isChecked(),
            "read_clipboard": self._context_read_clipboard.isChecked(),
            "profiles": profiles,
        }

        # Commands
        phrases: dict[str, str] = {}
        for line in self._commands_edit.toPlainText().splitlines():
            line = line.strip()
            if "→" in line:
                phrase, _, action = line.partition("→")
                phrase = phrase.strip()
                action = action.strip()
                if phrase and action:
                    phrases[phrase] = action
        commands = {"enabled": self._commands_enabled.isChecked(), "phrases": phrases}

        # Adaptive
        adaptive = {
            "enabled": self._adaptive_enabled.isChecked(),
            "promote_threshold": self._adaptive_threshold.value(),
            "learned_vocab_path": self._adaptive_path.text().strip() or None,
        }

        # Insertion
        insertion = {
            "strategy": self._insertion_strategy.currentData() or "keyboard",
            "clipboard_fallback": self._insertion_clipboard_fallback.isChecked(),
            "delay_between_chars_ms": self._insertion_char_delay.value(),
        }

        # Vision
        anchors = [
            line.strip() for line in self._vision_anchors.toPlainText().splitlines() if line.strip()
        ]
        vision = {
            "enabled": self._vision_enabled.isChecked(),
            "endpoint": self._vision_endpoint.text().strip() or None,
            "model": self._vision_model.text().strip() or None,
            "api_key_env": self._vision_api_key_env.text().strip() or None,
            "capture_timeout_s": self._vision_timeout.value(),
            "output_format": self._vision_output_format.currentData() or "auto",
            "anchor_phrases": anchors,
        }

        self.controller.update_section(
            context=context,
            commands=commands,
            adaptive=adaptive,
            insertion=insertion,
            vision=vision,
        )
