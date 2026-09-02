"""Inline banner shown above the canvas when the active photo's source
file(s) can't be found on disk (moved or deleted since import or since the
session was saved). Lists the missing channel(s) with their last-known
path, and offers a Locate button to relink them to a new folder - see
MainWindow.on_locate_missing_files."""
from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from .. import i18n
from .svg_icons import tinted_svg_pixmap

_ICON_SIZE = 20
_ICON_COLOR = QColor("#f2c40c")


class MissingFilesBanner(QFrame):
    locate_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "MissingFilesBanner { background: rgba(242, 196, 12, 28); "
            "border-bottom: 1px solid rgba(242, 196, 12, 90); }"
        )
        self._entries: list[tuple[str, str]] = []

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(tinted_svg_pixmap(
            "General/warning.svg", _ICON_SIZE, _ICON_COLOR, self.devicePixelRatioF() or 1.0))
        self.icon_label.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        row.addWidget(self.icon_label)

        self.text_label = QLabel()
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet("color: #e8e8ea;")
        row.addWidget(self.text_label, stretch=1)

        self.locate_button = QPushButton()
        self.locate_button.clicked.connect(self.locate_clicked.emit)
        row.addWidget(self.locate_button)

        self.retranslate_ui()
        self.setVisible(False)

    def set_missing(self, entries: list[tuple[str, str]]) -> None:
        """``entries``: list of (channel_label, last_known_path) for the
        currently active photo's missing channels; empty hides the banner."""
        self._entries = list(entries)
        self.setVisible(bool(self._entries))
        if self._entries:
            self._refresh_text()

    def _refresh_text(self) -> None:
        lines = [f"{label}: {path}" for label, path in self._entries]
        self.text_label.setText(i18n.tr("missing_files_banner_text") + "\n" + "\n".join(lines))

    def retranslate_ui(self) -> None:
        self.locate_button.setText(i18n.tr("missing_files_locate_button"))
        self.locate_button.setToolTip(i18n.tr("missing_files_locate_tooltip"))
        if self._entries:
            self._refresh_text()
