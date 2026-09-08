"""Confirmation dialog shown when switching an active trichrome photo (with
more than one channel already loaded) to Normal mode - continuing to a
single Normal-mode photo needs picking which loaded channel to keep editing,
since the other 1-2 would otherwise just become invisible. Same custom-
QDialog look as UnsavedChangesDialog (tinted warning.svg, plain QPushButtons,
no native chrome) rather than a native QMessageBox."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .. import i18n
from .channel_panel import CHANNEL_COLORS, CHANNEL_KEY
from .svg_icons import tinted_svg_pixmap

_ICON_SIZE = 36
_ICON_COLOR = QColor("#f2c40c")


class ModeSwitchDialog(QDialog):
    """``chosen_index`` is set to 0/1/2 (R/G/B) once a channel button is
    clicked, or stays None if cancelled/closed - check it after exec().
    ``available`` is a 3-bool list (which of R/G/B actually has an image
    loaded) - a channel with nothing loaded has no button, since there'd be
    nothing to continue editing."""

    def __init__(self, available: list[bool], parent=None):
        super().__init__(parent)
        self.chosen_index: int | None = None
        self.setWindowTitle(i18n.tr("mode_switch_dialog_title"))
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(16)

        body_row = QHBoxLayout()
        body_row.setSpacing(14)
        icon_label = QLabel()
        icon_label.setPixmap(tinted_svg_pixmap(
            "Global/warning.svg", _ICON_SIZE, _ICON_COLOR, self.devicePixelRatioF() or 1.0))
        icon_label.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        body_row.addWidget(icon_label, alignment=Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        title_label = QLabel(i18n.tr("mode_switch_dialog_title"))
        title_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        text_col.addWidget(title_label)
        detail_label = QLabel(i18n.tr("mode_switch_dialog_text"))
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet("color: #999;")
        text_col.addWidget(detail_label)
        body_row.addLayout(text_col, stretch=1)
        root.addLayout(body_row)

        self.channel_buttons: list[QPushButton] = []
        for i, label in enumerate(("R", "G", "B")):
            if not available[i]:
                continue
            color = CHANNEL_COLORS.get(label, "#888")
            btn = QPushButton(i18n.tr("mode_switch_channel_button", channel=i18n.tr(CHANNEL_KEY[label])))
            btn.setStyleSheet(
                f"QPushButton {{ text-align: left; padding: 8px 12px; "
                f"border-left: 3px solid {color}; }}")
            btn.clicked.connect(lambda _checked=False, idx=i: self._resolve(idx))
            root.addWidget(btn)
            self.channel_buttons.append(btn)

        cancel_row = QHBoxLayout()
        cancel_row.addStretch(1)
        self.cancel_button = QPushButton(i18n.tr("mode_switch_cancel_button"))
        self.cancel_button.setDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        cancel_row.addWidget(self.cancel_button)
        root.addLayout(cancel_row)

        self.setFixedWidth(380)

    def _resolve(self, index: int) -> None:
        self.chosen_index = index
        self.accept()
