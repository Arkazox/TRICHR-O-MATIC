"""The Quick Tour's welcome window - app logo, name, version and a short
description, an "Open at startup" checkbox, and Close / Start the Tour.
Shown at launch while that checkbox is checked (see
MainWindow.show_quick_tour_at_startup) and on demand from Help ▸ Quick Tour
or the toolbar's "?" menu. Styled like the app's other own dialogs
(ConfirmDialog, ModeSwitchDialog), not native QMessageBox chrome."""
from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLayout, QPushButton, QVBoxLayout,
)

from .. import i18n
from ..paths import resource_path
from ..version import __version__
from .button_style import style_primary_button, style_secondary_button

# QSettings key (main app domain) - True by default, re-armed by every
# build_mac.sh run so a fresh build always shows the welcome window again.
SHOW_AT_STARTUP_KEY = "quick_tour_show_at_startup"

_LOGO_SIZE = 96
_TEXT_WIDTH = 380


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

        text = QLabel(i18n.tr("quick_tour_welcome_text"))
        text.setWordWrap(True)
        # Fixed (not maximum) width - see ConfirmDialog's detail_label for
        # why a word-wrapped QLabel needs this to report its real height.
        text.setFixedWidth(_TEXT_WIDTH)
        text.setStyleSheet("line-height: 140%;")
        root.addWidget(text, alignment=Qt.AlignHCenter)
        root.addSpacing(20)

        row = QHBoxLayout()
        row.setSpacing(6)  # same gap as the tour callout's own Back/Next pair
        self.startup_checkbox = QCheckBox(i18n.tr("quick_tour_open_at_startup"))
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
