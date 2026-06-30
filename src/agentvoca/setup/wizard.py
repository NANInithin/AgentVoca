"""Setup wizard — ``QWizard`` composing the page widgets in order.

The wizard auto-opens on every launch (per the v0.3.5 decision). Users can
opt out via the checkbox on the Welcome page, which persists to
``state.json``.

Usage::

    wizard = SetupWizard(controller)
    wizard.show()          # non-modal; main loop continues
    # or:
    wizard.exec()          # modal block
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtWidgets

from agentvoca import __version__
from agentvoca.setup.first_run import mark_first_run_complete
from agentvoca.setup.pages import (
    AdvancedPage,
    AppBasicsPage,
    AsrPage,
    AudioPage,
    CleanupPage,
    FinishPage,
    HotkeysPage,
    VocabSnippetsPage,
    WelcomePage,
)
from agentvoca.setup.pages.base import ConfigPage

if TYPE_CHECKING:
    from agentvoca.setup.controllers.config_controller import ConfigController

logger = logging.getLogger(__name__)


def _as_wizard_page(widget: ConfigPage) -> QtWidgets.QWizardPage:
    """Wrap a ``ConfigPage`` so it can be added to a ``QWizard``.

    ``QWizard.addPage`` requires ``QWizardPage`` instances. The wizard
    delegates ``isComplete`` to the wrapped page so the validation on
    ``FinishPage`` still blocks navigation.
    """
    page = QtWidgets.QWizardPage()
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(widget)
    page.isComplete = widget.is_complete  # type: ignore[method-assign]
    return page


class SetupWizard(QtWidgets.QWizard):
    """The full first-run wizard with eight pages + welcome + review."""

    # Emitted on a successful save. The payload is the freshly-written
    # ``FullConfig`` so the host application can hot-apply supported fields.
    config_saved = QtCore.Signal(object)

    def __init__(
        self,
        controller: "ConfigController",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller

        self.setWindowTitle(f"agentvoca setup — v{__version__}")
        self.setWizardStyle(QtWidgets.QWizard.WizardStyle.ModernStyle)
        self.setOption(QtWidgets.QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setOption(QtWidgets.QWizard.WizardOption.NoCancelButton, False)
        self.resize(720, 600)

        self._pages = [
            WelcomePage(controller),
            AppBasicsPage(controller),
            AudioPage(controller),
            AsrPage(controller),
            CleanupPage(controller),
            HotkeysPage(controller),
            VocabSnippetsPage(controller),
            AdvancedPage(controller),
            FinishPage(controller),
        ]
        for page in self._pages:
            self.addPage(_as_wizard_page(page))

        self.setButtonText(QtWidgets.QWizard.WizardButton.NextButton, "Next →")
        self.setButtonText(QtWidgets.QWizard.WizardButton.BackButton, "← Back")
        self.setButtonText(QtWidgets.QWizard.WizardButton.FinishButton, "Save")
        self.setButtonText(QtWidgets.QWizard.WizardButton.CancelButton, "Cancel")

        # Reload every page's UI from the controller each time it becomes the
        # current page. This makes "Back" re-bind values even when the user
        # changed them in the Settings window mid-wizard.
        self.currentIdChanged.connect(self._on_current_changed)

    # ── Qt overrides ───────────────────────────────────────────────────

    def done(self, result: int) -> None:
        """Save when the user clicks Finish; cancel cleanly otherwise."""
        if result == QtWidgets.QWizard.DialogCode.Accepted:
            save_result = self._controller.save()
            if save_result.success:
                mark_first_run_complete(__version__)
                logger.info(
                    "Wizard saved config (hot=%d, restart=%d)",
                    len(save_result.hot_paths),
                    len(save_result.restart_paths),
                )
                try:
                    self.config_saved.emit(self._controller.draft)
                except Exception:
                    logger.exception("config_saved listener raised")
            else:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Save failed",
                    f"Could not write config:\n\n{save_result.error}",
                )
                # Stay in the wizard so the user can retry.
                return
        super().done(result)

    def accept(self) -> None:
        super().accept()

    # ── Internal ───────────────────────────────────────────────────────

    def _on_current_changed(self, _new_id: int) -> None:
        # Re-bind the controller on the underlying ConfigPage when navigating.
        for page_widget in self._pages:
            page_widget.load_from_controller()
