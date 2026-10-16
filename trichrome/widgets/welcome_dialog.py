"""The Quick Tour's welcome window - app logo, name, version and a short
description, an "Open at startup" checkbox, and Close / Start the Tour.
Shown at launch while that checkbox is checked (see
MainWindow.show_quick_tour_at_startup) and on demand from Help ▸ Quick Tour
or the toolbar's "?" menu. Styled like the app's other own dialogs
(ConfirmDialog, ModeSwitchDialog), not native QMessageBox chrome."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QSettings, Qt
from PySide6.QtGui import QPainter, QPalette, QPixmap, QTextLayout
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLayout, QPushButton, QVBoxLayout, QWidget,
)

from .. import i18n
from ..paths import resource_path
from ..version import __version__
from .button_style import style_primary_button, style_secondary_button
from .checkbox import CheckBox

# QSettings key (main app domain) - True by default, re-armed by every
# build_mac.sh run so a fresh build always shows the welcome window again.
SHOW_AT_STARTUP_KEY = "quick_tour_show_at_startup"

_LOGO_SIZE = 96
_TEXT_WIDTH = 380


class _JustifiedText(QWidget):
    """Fixed-width text, paragraphs split on newlines: every line of a
    paragraph is stretched to the full width, its last line centered.
    Painted by hand: Qt's own justify (rich text or QTextOption) never
    stretches a paragraph's last line nor a line ending in a forced break,
    so it can't justify all lines but the last one."""

    _LINE_HEIGHT = 1.4

    def __init__(self, text: str, width: int, parent=None):
        super().__init__(parent)
        self._text = text
        self._lines = []  # (words, is_last_line) per line; [] for a blank paragraph
        self.setFixedWidth(width)
        self._relayout()

    def _relayout(self) -> None:
        width = self.width()
        self._lines = []
        for paragraph in self._text.split("\n"):
            if not paragraph.strip():
                self._lines.append(([], True))
                continue
            layout = QTextLayout(paragraph, self.font())
            layout.beginLayout()
            spans = []
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(width)
                spans.append(paragraph[line.textStart():line.textStart() + line.textLength()])
            layout.endLayout()
            for i, span in enumerate(spans):
                self._lines.append((span.split(), i == len(spans) - 1))
        self.setFixedHeight(len(self._lines) * self._line_pitch())
        self.update()

    def _line_pitch(self) -> int:
        return round(self.fontMetrics().height() * self._LINE_HEIGHT)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.FontChange:
            self._relayout()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.WindowText))
        metrics = self.fontMetrics()
        pitch = self._line_pitch()
        # The extra line spacing is split above and below each line.
        baseline = (pitch - metrics.height()) / 2 + metrics.ascent()
        space = metrics.horizontalAdvance(" ")
        for row, (words, last) in enumerate(self._lines):
            if not words:
                continue
            y = row * pitch + baseline
            widths = [metrics.horizontalAdvance(w) for w in words]
            if last or len(words) == 1:
                x = (self.width() - sum(widths) - space * (len(words) - 1)) / 2
                gap = space
            else:
                x = 0
                gap = (self.width() - sum(widths)) / (len(words) - 1)
            for word, w in zip(words, widths):
                painter.drawText(QPointF(x, y), word)
                x += w + gap


def show_at_startup_enabled(org_name: str, app_name: str) -> bool:
    return QSettings(org_name, app_name).value(SHOW_AT_STARTUP_KEY, True, type=bool)


class WelcomeDialog(QDialog):
    """``result`` is "start" (Start the Tour, the default button) or
    "close" (Close/Escape). The checkbox writes its QSettings value as soon
    as it's toggled, regardless of which button closes the dialog."""

    def __init__(self, parent, org_name: str, app_name: str):
        super().__init__(parent)
        self.result = "close"
        self._org_name = org_name
        self._app_name = app_name
        self.setWindowTitle(i18n.tr("quick_tour_welcome_window_title"))
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 18)
        root.setSpacing(0)

        logo = QLabel()
        dpr = self.devicePixelRatioF() or 1.0
        pixmap = QPixmap(resource_path("resources", "app_logo.png"))
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                int(_LOGO_SIZE * dpr), int(_LOGO_SIZE * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pixmap.setDevicePixelRatio(dpr)
            logo.setPixmap(pixmap)
        logo.setFixedSize(_LOGO_SIZE, _LOGO_SIZE)
        root.addWidget(logo, alignment=Qt.AlignHCenter)
        root.addSpacing(10)

        title = QLabel(i18n.tr("quick_tour_welcome_title"))
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        root.addWidget(title, alignment=Qt.AlignHCenter)
        root.addSpacing(3)

        version = QLabel(i18n.tr("quick_tour_version", version=__version__))
        version.setStyleSheet("color: #999; font-size: 11px;")
        root.addWidget(version, alignment=Qt.AlignHCenter)
        root.addSpacing(14)

        text = _JustifiedText(i18n.tr("quick_tour_welcome_text"), _TEXT_WIDTH)
        root.addWidget(text, alignment=Qt.AlignHCenter)
        root.addSpacing(20)

        row = QHBoxLayout()
        row.setSpacing(6)  # same gap as the tour callout's own Back/Next pair
        self.startup_checkbox = CheckBox(i18n.tr("quick_tour_open_at_startup"))
        self.startup_checkbox.setChecked(show_at_startup_enabled(org_name, app_name))
        self.startup_checkbox.toggled.connect(self._on_startup_toggled)
        row.addWidget(self.startup_checkbox)
        row.addStretch(1)
        close_button = QPushButton(i18n.tr("quick_tour_close"))
        style_secondary_button(close_button)
        close_button.clicked.connect(self.reject)
        row.addWidget(close_button)
        start_button = QPushButton(i18n.tr("quick_tour_start"))
        style_primary_button(start_button)
        start_button.setDefault(True)
        start_button.clicked.connect(self._on_start)
        row.addWidget(start_button)
        root.addLayout(row)

        root.setSizeConstraint(QLayout.SetFixedSize)
        start_button.setFocus()

    def _on_startup_toggled(self, checked: bool) -> None:
        QSettings(self._org_name, self._app_name).setValue(SHOW_AT_STARTUP_KEY, checked)

    def _on_start(self) -> None:
        self.result = "start"
        self.accept()
