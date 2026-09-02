"""Top-of-sidebar panel: load the 3 channel images."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup, QGroupBox, QHBoxLayout, QLabel, QPushButton, QToolButton,
    QVBoxLayout, QWidget,
)

from .. import i18n
from .channel_panel import CHANNEL_COLORS, CHANNEL_KEY
from .controls import ElidingLabel
from .info_bubble import show_info_bubble
from .svg_icons import SvgLetterToggleButton


class ImportPanel(QGroupBox):
    load_requested = Signal(int)
    auto_align_requested = Signal()
    lock_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        root = QVBoxLayout(self)

        self.channel_labels: list[QLabel] = []
        self.filename_labels: list[ElidingLabel] = []
        self.load_buttons: list[QPushButton] = []

        for label in ("R", "G", "B"):
            row = QHBoxLayout()
            color = CHANNEL_COLORS.get(label, "#888")
            channel_label = QLabel()
            channel_label.setStyleSheet(f"color: {color}; font-weight: bold;")
            channel_label.setFixedWidth(50)
            row.addWidget(channel_label)

            filename_label = ElidingLabel()
            filename_label.setStyleSheet("color: #888; font-size: 11px;")
            row.addWidget(filename_label, stretch=1)

            load_button = QPushButton()
            load_button.clicked.connect(lambda _checked=False, i=len(self.channel_labels): self.load_requested.emit(i))
            row.addWidget(load_button)

            root.addLayout(row)
            self.channel_labels.append(channel_label)
            self.filename_labels.append(filename_label)
            self.load_buttons.append(load_button)

        self.auto_align_button = QPushButton()
        self.auto_align_button.clicked.connect(self.auto_align_requested.emit)
        root.addWidget(self.auto_align_button)

        lock_row = QHBoxLayout()
        self.lock_label = QLabel()
        lock_row.addWidget(self.lock_label)
        self.lock_buttons: list[SvgLetterToggleButton] = []
        self.lock_group = QButtonGroup(self)
        self.lock_group.setExclusive(True)
        for i, label in enumerate(("R", "G", "B")):
            color = CHANNEL_COLORS.get(label, "#888")
            btn = SvgLetterToggleButton(label, color, size=(32, 28), icon_size=22)
            btn.toggled.connect(lambda checked, idx=i: self.lock_requested.emit(idx) if checked else None)
            self.lock_group.addButton(btn)
            lock_row.addWidget(btn)
            self.lock_buttons.append(btn)
        lock_row.addStretch(1)
        self.lock_info_button = QToolButton()
        self.lock_info_button.setText("?")
        self.lock_info_button.setFixedSize(18, 18)
        self.lock_info_button.setStyleSheet("QToolButton { border-radius: 9px; }")
        self.lock_info_button.clicked.connect(
            lambda: show_info_bubble(i18n.tr("lock_layer_position_info"), self.lock_info_button))
        lock_row.addWidget(self.lock_info_button)
        root.addLayout(lock_row)

        self._has_image = [False, False, False]
        self.retranslate_ui()

    def set_filename(self, index: int, text: str) -> None:
        self._has_image[index] = True
        self.filename_labels[index].setText(text)

    def set_locked_channel(self, index: int) -> None:
        for i, btn in enumerate(self.lock_buttons):
            btn.blockSignals(True)
            btn.setChecked(i == index)
            btn.blockSignals(False)

    def retranslate_ui(self) -> None:
        for i, label in enumerate(("R", "G", "B")):
            self.channel_labels[i].setText(i18n.tr(CHANNEL_KEY[label]) + ":")
            self.load_buttons[i].setText(i18n.tr("load_image_button"))
            if not self._has_image[i]:
                self.filename_labels[i].setText(i18n.tr("no_image_loaded"))
        self.auto_align_button.setText(i18n.tr("auto_align_button"))
        self.lock_label.setText(i18n.tr("lock_layer_position_label"))
        for i, label in enumerate(("R", "G", "B")):
            self.lock_buttons[i].setToolTip(i18n.tr(CHANNEL_KEY[label]))
