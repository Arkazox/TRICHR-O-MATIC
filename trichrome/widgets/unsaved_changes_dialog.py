"""Confirmation dialog shown before discarding unsaved session changes
(New Session, Open Session, quitting) - a custom QDialog instead of the
native QMessageBox so it matches the rest of the app's plain, SVG-icon look
instead of the OS's generic exclamation-mark chrome."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .. import i18n
from .svg_icons import tinted_svg_pixmap

_ICON_SIZE = 36
_ICON_COLOR = QColor("#f2c40c")


class UnsavedChangesDialog(QDialog):
    """`choice` is set to "save", "discard", or "cancel" once the dialog
    closes (defaults to "cancel", e.g. if the user hits Escape/closes it)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.choice = "cancel"
        self.setWindowTitle(i18n.tr("dialog_quit_unsaved_title"))
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(16)

        body_row = QHBoxLayout()
        body_row.setSpacing(14)

        icon_label = QLabel()
        icon_label.setPixmap(tinted_svg_pixmap(
            "General/warning.svg", _ICON_SIZE, _ICON_COLOR, self.devicePixelRatioF() or 1.0))
        icon_label.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        body_row.addWidget(icon_label, alignment=Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        title_label = QLabel(i18n.tr("dialog_quit_unsaved_title"))
        title_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        text_col.addWidget(title_label)
        detail_label = QLabel(i18n.tr("dialog_quit_unsaved_text"))
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet("color: #999;")
        text_col.addWidget(detail_label)
        body_row.addLayout(text_col, stretch=1)

        root.addLayout(body_row)

        btn_row = QHBoxLayout()
        self.cancel_button = QPushButton(i18n.tr("dialog_quit_cancel_button"))
        self.cancel_button.clicked.connect(lambda: self._resolve("cancel"))
        btn_row.addWidget(self.cancel_button)
        btn_row.addStretch(1)
        self.discard_button = QPushButton(i18n.tr("dialog_quit_discard_button"))
        self.discard_button.clicked.connect(lambda: self._resolve("discard"))
        btn_row.addWidget(self.discard_button)
        self.save_button = QPushButton(i18n.tr("dialog_quit_save_button"))
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(lambda: self._resolve("save"))
        btn_row.addWidget(self.save_button)
        root.addLayout(btn_row)

        self.setFixedWidth(380)

    def _resolve(self, choice: str) -> None:
        self.choice = choice
        self.accept()
