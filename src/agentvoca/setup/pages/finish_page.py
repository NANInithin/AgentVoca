"""Finish page — review the diff before saving."""

from __future__ import annotations

from PySide6 import QtWidgets

from agentvoca.setup.pages.base import ConfigPage


class FinishPage(ConfigPage):
    title = "Review & save"
    subtitle = "Sanity-check the changes, then save."

    def _build(self) -> None:
        super()._build()
        layout = self._body_layout

        self._summary = QtWidgets.QPlainTextEdit()
        self._summary.setReadOnly(True)
        self._summary.setMinimumHeight(220)
        layout.addWidget(self._summary)

        note = QtWidgets.QLabel(
            "Click <b>Save</b> on the wizard's final page to write the config "
            "to <code>~/.agentvoca/config.yaml</code>. A timestamped backup is "
            "kept next to it. You can rerun this wizard any time from the tray."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addStretch()

    def load_from_controller(self) -> None:
        c = self.controller.draft
        lines = [
            "ASR provider:        " + c.asr.provider,
            "ASR model:           " + (c.asr.model or "(default)"),
            "Cleanup provider:    " + c.cleanup.provider,
            "Cleanup style:       " + c.cleanup.style,
            "Insertion:           " + c.insertion.strategy,
            "Recording mode:      " + c.app.mode,
            "Language:            " + c.app.language,
            "Input device:        " + (c.audio.input_device or "default"),
            "Hotkey (toggle):     " + (c.hotkeys.toggle_recording or "(disabled)"),
            "Vocab terms (inline):" + str(len(c.vocabulary.inline)),
            "Snippets file:       " + (c.snippets.path or "(none)"),
            "Context enabled:     " + str(c.context.enabled),
            "Commands enabled:    " + str(c.commands.enabled),
            "Adaptive enabled:    " + str(c.adaptive.enabled),
            "Vision enabled:      " + str(c.vision.enabled),
        ]
        self._summary.setPlainText("\n".join(lines))

    def is_complete(self) -> bool:
        ok, err = self.controller.validate()
        if not ok:
            QtWidgets.QMessageBox.warning(
                self,
                "Validation failed",
                f"The draft configuration is invalid:\n\n{err}",
            )
            return False
        return True
