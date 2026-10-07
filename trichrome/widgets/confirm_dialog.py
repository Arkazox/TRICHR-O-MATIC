"""A Cancel/Confirm (optionally + a third "alternate" choice) confirmation
dialog, styled like the rest of the app instead of native QMessageBox chrome
- the same visual shape as UnsavedChangesDialog (icon + title + text +
buttons) but for a confirmation where nothing is being saved/discarded in
the Save/Don't Save sense (e.g. Light mode's Light -> Advanced switch: no
data is ever lost there, but the user picks *what happens next* - carry the
current photo into a new session, or reopen the last session instead - so
UnsavedChangesDialog's Save/Don't Save/Cancel framing would be the wrong
prompt)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLayout, QPushButton, QVBoxLayout

from .button_style import style_primary_button, style_secondary_button
from .svg_icons import tinted_svg_pixmap

_ICON_SIZE = 36
_ICON_COLOR = QColor("#f2c40c")


class ConfirmDialog(QDialog):
    """``result`` is one of "cancel" (Escape/close/Cancel button - the
    default), "confirm" (the primary, right-most/bold button), or
    "alternate" (only reachable when ``alternate_label`` is given - a
    secondary choice between Cancel and Confirm, same position
    UnsavedChangesDialog's own "Discard" occupies)."""

    def __init__(
        self, parent, title: str, text: str, confirm_label: str, cancel_label: str,
        alternate_label: str | None = None,
    ):
        super().__init__(parent)
        self.result = "cancel"
        self.setWindowTitle(title)
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
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        title_label.setWordWrap(True)
        text_col.addWidget(title_label)
        detail_label = QLabel(text)
        detail_label.setWordWrap(True)
        # A genuinely *fixed* (not maximum) wrap width, same fix/reasoning
        # as ModeSwitchDialog's own detail_label: a word-wrapped QLabel's
        # sizeHint() reports its *unwrapped*, single-line width until
        # something has actually constrained it - a plain setFixedWidth()
        # on the dialog itself (the previous approach here) doesn't feed
        # into that at all, so the dialog's own size can come out too
        # narrow, clipping/truncating the wrapped text. 300px leaves room
        # for the icon/spacing/margins within the dialog's own ~370-380px
        # total width.
        detail_label.setFixedWidth(300)
        detail_label.setStyleSheet("color: #999;")
        text_col.addWidget(detail_label)
        body_row.addLayout(text_col, stretch=1)
        root.addLayout(body_row)

        btn_row = QHBoxLayout()
        cancel_button = QPushButton(cancel_label)
        style_secondary_button(cancel_button)
        cancel_button.clicked.connect(self.reject)
        btn_row.addWidget(cancel_button)
        btn_row.addStretch(1)
        if alternate_label:
            alternate_button = QPushButton(alternate_label)
            style_secondary_button(alternate_button)
            alternate_button.clicked.connect(lambda: self._resolve("alternate"))
            btn_row.addWidget(alternate_button)
        confirm_button = QPushButton(confirm_label)
        style_primary_button(confirm_button)
        confirm_button.setDefault(True)
        confirm_button.clicked.connect(lambda: self._resolve("confirm"))
        btn_row.addWidget(confirm_button)
        root.addLayout(btn_row)

        # Pins the dialog's actual size to the root layout's own sizeHint
        # (which now correctly folds in detail_label's real wrapped
        # height, thanks to the fixed width above) on every relayout,
        # instead of a plain setFixedWidth() that doesn't account for the
        # label's own wrapping - see ModeSwitchDialog for the same fix.
        root.setSizeConstraint(QLayout.SetFixedSize)

    def _resolve(self, result: str) -> None:
        self.result = result
        self.accept()
