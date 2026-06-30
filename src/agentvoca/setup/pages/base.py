"""Base class for wizard and settings-window pages.

Every page is a ``QWidget`` that:

- Holds a reference to a shared ``ConfigController`` (set after construction).
- Loads its UI state from the controller via ``load_from_controller``.
- Saves its UI state back into the controller via ``save_to_controller``.

The base class also tracks a ``title`` for the page header and an optional
``subtitle`` for context. Pages never touch ``FullConfig`` directly — they
delegate to ``controller.update_section(...)`` so validation runs through one
path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtWidgets

if TYPE_CHECKING:
    from agentvoca.setup.controllers.config_controller import ConfigController


class ConfigPage(QtWidgets.QWidget):
    """Base class for every page in the wizard and settings window.

    Subclasses override ``load_from_controller`` and ``save_to_controller``.
    The base constructor sets up the standard title + subtitle header.
    """

    title: str = ""
    subtitle: str = ""

    def __init__(self, controller: "ConfigController | None" = None) -> None:
        super().__init__()
        self._controller = controller
        self._build()

    # ── Controller binding ─────────────────────────────────────────────

    def set_controller(self, controller: "ConfigController") -> None:
        """Attach or re-attach a controller and refresh the UI."""
        self._controller = controller
        if controller is not None:
            self.load_from_controller()

    @property
    def controller(self) -> "ConfigController":
        """The controller bound to this page (never None inside a wizard/window)."""
        if self._controller is None:
            raise RuntimeError("ConfigPage has no controller bound")
        return self._controller

    # ── Subclass hooks ─────────────────────────────────────────────────

    def _build(self) -> None:
        """Build the page's UI. Subclasses should populate ``self._body``.

        The default implementation creates a vertical layout with the standard
        title + subtitle header and an empty body placeholder. Subclasses are
        free to ignore the helper and provide their own layout.
        """
        outer = QtWidgets.QVBoxLayout()
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(8)

        if self.title:
            title_label = QtWidgets.QLabel(self.title)
            title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
            outer.addWidget(title_label)

        if self.subtitle:
            subtitle_label = QtWidgets.QLabel(self.subtitle)
            subtitle_label.setStyleSheet("color: #666;")
            subtitle_label.setWordWrap(True)
            outer.addWidget(subtitle_label)

        self._body = QtWidgets.QWidget()
        self._body_layout = QtWidgets.QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 8, 0, 0)
        outer.addWidget(self._body)

        self.setLayout(outer)

    def load_from_controller(self) -> None:
        """Sync the UI from the controller's draft. Override in subclasses."""

    def save_to_controller(self) -> None:
        """Sync the UI back into the controller's draft. Override in subclasses."""
        # Default is a no-op so read-only pages do not have to implement it.

    # ── Convenience ────────────────────────────────────────────────────

    def is_complete(self) -> bool:
        """Return True if the page can be advanced past. Default True.

        Override to add per-page validation that should block wizard
        navigation. The wizard will not let the user proceed otherwise.
        """
        return True
