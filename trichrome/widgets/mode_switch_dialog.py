"""Confirmation dialog shown on either direction of a Solo <-> Trichrome
mode switch that needs picking a specific R/G/B channel: switching a
multi-channel Trichrome photo back to Solo (continuing to a single photo
needs picking which loaded channel to keep editing, since the other 1-2
would otherwise just become invisible - MainWindow._switch_to_normal_mode),
or switching a Solo photo to either Trichrome variant (which channel should
this image become - MainWindow._switch_to_trichrome_mode). Same custom-
QDialog look as UnsavedChangesDialog (tinted warning.svg, plain QPushButtons,
no native chrome) rather than a native QMessageBox; the body text is passed
in fully pre-translated since the two directions phrase it differently."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLayout, QPushButton, QVBoxLayout

from .. import i18n
from .channel_panel import CHANNEL_COLORS, CHANNEL_KEY
from .svg_icons import tinted_svg_icon, tinted_svg_pixmap

_ICON_SIZE = 36
_ICON_COLOR = QColor("#f2c40c")

# Icon size and rounded/translucent look matching ImportPanel's own Mode
# combo (import_panel.py's _MODE_COMBO_ICON_SIZE/_MODE_COMBO_STYLE) - the
# user's own ask was for these channel-choice buttons to read as the same
# "icon + text, rounded corners" family as that Mode selector, rather than
# the plain flat rectangle + colored left-border strip they used before.
_CHANNEL_BUTTON_ICON_SIZE = 18
_CHANNEL_BUTTON_STYLE = """
QPushButton {
    text-align: left;
    padding: 8px 12px;
    background: rgba(255, 255, 255, 14);
    border: 1px solid rgba(255, 255, 255, 35);
    border-radius: 4px;
    color: #f0f0f0;
}
QPushButton:hover {
    background: rgba(255, 255, 255, 24);
    border: 1px solid rgba(255, 255, 255, 60);
}
"""


class ModeSwitchDialog(QDialog):
    """``chosen_index`` is set to 0/1/2 (R/G/B) once a channel button is
    clicked, or stays None if cancelled/closed - check it after exec().
    ``available`` is a 3-bool list controlling which of the R/G/B buttons
    show - Trichrome-to-Solo only offers channels that actually have an
    image loaded (nothing to continue editing otherwise), while Solo-to-
    Trichrome always passes all-True (any of the 3 can receive the image).
    ``text`` is the already-translated body text - the two directions
    phrase it differently, see MainWindow._switch_to_normal_mode/
    _switch_to_trichrome_mode for the exact wording each uses."""

    def __init__(self, available: list[bool], text: str, parent=None):
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
        title_label.setWordWrap(True)
        text_col.addWidget(title_label)
        detail_label = QLabel(text)
        detail_label.setWordWrap(True)
        # A deliberate, truly *fixed* (not maximum) wrap width for the
        # paragraph itself - QLabel.sizeHint() for word-wrapped text
        # otherwise reports its *unwrapped*, single-line width whenever
        # nothing has constrained it yet (a maximumWidth alone doesn't
        # feed into sizeHint(), only into how far the layout lets it grow
        # afterward), which is what let the dialog's own SetFixedSize-
        # computed size come out too narrow for the actual wrapped
        # paragraph beneath it - a genuinely fixed width makes sizeHint()
        # report the real multi-line height for that width instead. 300px
        # leaves room for the icon/spacing/margins within the dialog's own
        # ~370-380px total width.
        detail_label.setFixedWidth(300)
        detail_label.setStyleSheet("color: #999;")
        text_col.addWidget(detail_label)
        body_row.addLayout(text_col, stretch=1)
        root.addLayout(body_row)

        self.channel_buttons: list[QPushButton] = []
        dpr = self.devicePixelRatioF() or 1.0
        for i, label in enumerate(("R", "G", "B")):
            if not available[i]:
                continue
            color = CHANNEL_COLORS.get(label, "#888")
            btn = QPushButton(i18n.tr("mode_switch_channel_button", channel=i18n.tr(CHANNEL_KEY[label])))
            # Same solid circle-letter glyph the Histogram/Curves channel
            # toggles and Lock Layer Position use (SvgLetterToggleButton),
            # here just as a static icon on an ordinary button rather than
            # a checkable widget of its own, since each row is a one-shot
            # choice, not a toggle.
            btn.setIcon(tinted_svg_icon(f"Global/circle-letter-{label.lower()}.svg",
                                         _CHANNEL_BUTTON_ICON_SIZE, QColor(color), dpr))
            btn.setIconSize(QSize(_CHANNEL_BUTTON_ICON_SIZE, _CHANNEL_BUTTON_ICON_SIZE))
            btn.setStyleSheet(_CHANNEL_BUTTON_STYLE)
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

        # SetFixedSize pins the dialog's actual size to the root layout's
        # own sizeHint on every relayout (which correctly folds in the
        # labels' heightForWidth now that detail_label has a real wrap
        # width via setMaximumWidth above) - so its size always matches
        # what the content actually needs, on construction and afterward,
        # rather than whatever size Qt/the parent window happens to hand
        # it. The user's own ask was for the text to always display in
        # full regardless of any external sizing influence, not just
        # "usually wide enough."
        root.setSizeConstraint(QLayout.SetFixedSize)

    def _resolve(self, index: int) -> None:
        self.chosen_index = index
        self.accept()
