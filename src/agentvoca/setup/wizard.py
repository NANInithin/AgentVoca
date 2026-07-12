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
        startup_warning: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller

        self.setWindowTitle(f"agentvoca setup — v{__version__}")
        self.setWizardStyle(QtWidgets.QWizard.WizardStyle.ModernStyle)
        self.setOption(QtWidgets.QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setOption(QtWidgets.QWizard.WizardOption.NoCancelButton, False)
        self.resize(720, 600)

        welcome = WelcomePage(controller)
        if startup_warning:
            welcome.show_startup_warning(startup_warning)
        self._pages = [
            welcome,
            AppBasicsPage(controller),
            AudioPage(controller),
            AsrPage(controller),
            CleanupPage(controller),
            HotkeysPage(controller),
            VocabSnippetsPage(controller),
            AdvancedPage(controller),
            FinishPage(controller),
        ]
        # Parallel list of QWizardPage wrappers so we can map wizard-id back
        # to the underlying ConfigPage index when handling navigation.
        self._wizard_pages: list[QtWidgets.QWizardPage] = []
        for page in self._pages:
            wrapper = _as_wizard_page(page)
            self._wizard_pages.append(wrapper)
            self.addPage(wrapper)

        self.setButtonText(QtWidgets.QWizard.WizardButton.NextButton, "Next →")
        self.setButtonText(QtWidgets.QWizard.WizardButton.BackButton, "← Back")
        self.setButtonText(QtWidgets.QWizard.WizardButton.FinishButton, "Save")
        self.setButtonText(QtWidgets.QWizard.WizardButton.CancelButton, "Cancel")

        # Track the page the user is leaving so we can capture its UI state
        # into the controller before rebinding. Without this, every "Next"
        # would rebind every page from the controller's draft, clobbering
        # values the user just typed but has not yet saved.
        # ``_current_id`` starts at -1 (no page shown yet) and is updated
        # in lock-step with QWizard's own currentId so we always know which
        # page is being left on every navigation.
        self._current_id: int = -1
        self.currentIdChanged.connect(self._on_current_changed)

    # ── Qt overrides ───────────────────────────────────────────────────

    def done(self, result: int) -> None:
        """Save when the user clicks Finish; cancel cleanly otherwise."""
        if result == QtWidgets.QWizard.DialogCode.Accepted:
            # 1. Push every page's UI into the controller draft *first*.
            # Without this, the wizard would persist whatever was loaded
            # from disk and silently drop everything the user just typed.
            for page in self._pages:
                page.save_to_controller()

            # 2. Validate + persist via the shared controller path.
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

    def _on_current_changed(self, new_id: int) -> None:
        # Skip the rebind while the wizard is closing. ``result()`` is
        # non-zero once the user has accepted/rejected, and QWizard fires
        # currentIdChanged during teardown — we must not overwrite the
        # just-saved draft (or any unsaved user input) at that point.
        if self.result() != 0:
            return

        # 1. Capture the page we're leaving: push its UI into the controller
        #    so its values survive the navigation. This is what fixes the
        #    "Next clobbers my typed values" bug. ``self._current_id`` was
        #    the last page id we saw, set either by us (initial -1) or by
        #    a prior invocation of this slot.
        if self._current_id != -1 and self._current_id != new_id:
            leaving_index = self._page_index_for_id(self._current_id)
            if leaving_index is not None and 0 <= leaving_index < len(self._pages):
                try:
                    self._pages[leaving_index].save_to_controller()
                except Exception:
                    logger.exception(
                        "Failed to capture state from page %d on navigation",
                        leaving_index,
                    )

        # 2. Rebind the page we're arriving at from the controller. We only
        #    rebind the *new* page, not every page, so typed-but-unsaved
        #    values on other pages are preserved. The full rebind still
        #    happens in ``_refresh_all`` if/when something external (e.g.
        #    the settings window) demands a global resync.
        if new_id != -1 and new_id != self._current_id:
            new_index = self._page_index_for_id(new_id)
            if new_index is not None and 0 <= new_index < len(self._pages):
                try:
                    self._pages[new_index].load_from_controller()
                except Exception:
                    logger.exception("Failed to rebind page %d on navigation", new_index)

        self._current_id = new_id

    def _page_index_for_id(self, wizard_id: int) -> int | None:
        """Map a ``QWizard`` page id to the index in ``self._pages``."""
        for idx, wrapper in enumerate(self._wizard_pages):
            if wrapper is self.page(wizard_id):
                return idx
        return None

    def _refresh_all(self) -> None:
        """Force a full rebind of every page. Used after external controller mutations."""
        for page_widget in self._pages:
            try:
                page_widget.load_from_controller()
            except Exception:
                logger.exception("Failed to rebind page during full refresh")
