"""Top-of-sidebar panel: mode toggle (Normal/Trichrome), then either load
the 3 channel images (Trichrome) or a single photo (Normal). Auto Align and
Lock Layer Position moved to the top of the "Trichrome Process" block
(main_window.py's independent_channels_group) - 2026-09-04."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import i18n
from .block_header_bar import finish_block_chrome, start_block_chrome
from .channel_panel import CHANNEL_COLORS, CHANNEL_KEY
from .controls import ElidingLabel
from .svg_icons import HEADER_COMPANION_BTN_SIZE, HEADER_COMPANION_ICON_SIZE, SvgToolButton

_COMPACT_MODE_BUTTON_STYLE = "QPushButton { padding: 4px 8px; }"


class ImportPanel(QGroupBox):
    load_requested = Signal(int)
    # Emitted whenever the user clicks the Normal/Trichrome toggle -
    # MainWindow decides whether to apply it directly or intercept with a
    # confirmation (switching away from a multi-channel trichrome photo) -
    # this panel has no visibility into that, so it never applies the switch
    # itself; call set_mode() to reflect the actual outcome afterward.
    mode_change_requested = Signal(str)
    load_normal_requested = Signal()
    add_photo_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # Title restored 2026-09-04 (removed 2026-09-03, then the user
        # asked for it back - "c'était mieux") - only histogram_box stays
        # title-less.
        # Block key is "files" (matching main_window.py's _ALL_BLOCK_KEYS
        # and every block_side/block_visible/block_widgets entry) - was
        # "import" until 2026-09-04, a real bug: the drag handle's MIME
        # data carried a key that matched nothing in MainWindow's block
        # state, so dragging this block silently failed every time,
        # same-panel included.
        outer, header_row, self.title_label = start_block_chrome(self, "files", "import_panel_title")
        header_row.addStretch(1)
        # "Add Photo" - appends a new photo to the carousel, same header-
        # action-button convention as every other block's Reset (companion
        # size, trailing edge) - see MainWindow.on_add_photo_clicked for
        # what it actually does per mode.
        self.add_photo_button = SvgToolButton(
            "Toolbar/image-plus.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.add_photo_button.clicked.connect(self.add_photo_requested.emit)
        header_row.addWidget(self.add_photo_button)
        self.body, root, self.collapse_button, self.close_button = finish_block_chrome(outer, header_row)

        # --- Normal / Trichrome mode toggle ---
        mode_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.normal_mode_button = QPushButton()
        self.normal_mode_button.setCheckable(True)
        self.normal_mode_button.setStyleSheet(_COMPACT_MODE_BUTTON_STYLE)
        self.trichrome_mode_button = QPushButton()
        self.trichrome_mode_button.setCheckable(True)
        self.trichrome_mode_button.setChecked(True)
        self.trichrome_mode_button.setStyleSheet(_COMPACT_MODE_BUTTON_STYLE)
        self.mode_group.addButton(self.normal_mode_button)
        self.mode_group.addButton(self.trichrome_mode_button)
        self.normal_mode_button.clicked.connect(lambda: self.mode_change_requested.emit("normal"))
        self.trichrome_mode_button.clicked.connect(lambda: self.mode_change_requested.emit("trichrome"))
        mode_row.addWidget(self.normal_mode_button)
        mode_row.addWidget(self.trichrome_mode_button)
        root.addLayout(mode_row)

        # --- Trichrome mode: the 3 channel rows + auto-align + lock ---
        self.trichrome_container = QWidget()
        trichrome_layout = QVBoxLayout(self.trichrome_container)
        trichrome_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.trichrome_container)

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

            trichrome_layout.addLayout(row)
            self.channel_labels.append(channel_label)
            self.filename_labels.append(filename_label)
            self.load_buttons.append(load_button)

        # --- Normal mode: a single photo, no alignment/recompose ---
        self.normal_container = QWidget()
        normal_layout = QVBoxLayout(self.normal_container)
        normal_layout.setContentsMargins(0, 0, 0, 0)
        normal_row = QHBoxLayout()
        self.normal_filename_label = ElidingLabel()
        self.normal_filename_label.setStyleSheet("color: #888; font-size: 11px;")
        normal_row.addWidget(self.normal_filename_label, stretch=1)
        self.load_normal_button = QPushButton()
        self.load_normal_button.clicked.connect(self.load_normal_requested.emit)
        normal_row.addWidget(self.load_normal_button)
        normal_layout.addLayout(normal_row)
        root.addWidget(self.normal_container)
        self.normal_container.hide()

        self._has_image = [False, False, False]
        self._has_normal_image = False
        self.retranslate_ui()

    def set_filename(self, index: int, text: str) -> None:
        self._has_image[index] = bool(text)
        self.filename_labels[index].setText(text or i18n.tr("no_image_loaded"))
        self.load_buttons[index].setText(
            i18n.tr("change_image_button") if text else i18n.tr("load_image_button"))

    def set_normal_filename(self, text: str) -> None:
        self._has_normal_image = bool(text)
        self.normal_filename_label.setText(text or i18n.tr("no_image_loaded"))
        self.load_normal_button.setText(
            i18n.tr("change_image_button") if text else i18n.tr("load_image_button"))

    def set_mode(self, mode: str) -> None:
        """Programmatic mode sync (activating a different photo, session
        restore) - blocks signals so this never re-emits mode_change_requested."""
        is_normal = mode == "normal"
        self.normal_mode_button.blockSignals(True)
        self.trichrome_mode_button.blockSignals(True)
        self.normal_mode_button.setChecked(is_normal)
        self.trichrome_mode_button.setChecked(not is_normal)
        self.normal_mode_button.blockSignals(False)
        self.trichrome_mode_button.blockSignals(False)
        self.trichrome_container.setVisible(not is_normal)
        self.normal_container.setVisible(is_normal)

    def retranslate_ui(self) -> None:
        self.title_label.setText(i18n.tr("import_panel_title"))
        self.normal_mode_button.setText(i18n.tr("import_mode_normal_button"))
        self.trichrome_mode_button.setText(i18n.tr("import_mode_trichrome_button"))
        for i, label in enumerate(("R", "G", "B")):
            self.channel_labels[i].setText(i18n.tr(CHANNEL_KEY[label]) + ":")
            self.load_buttons[i].setText(
                i18n.tr("change_image_button") if self._has_image[i] else i18n.tr("load_image_button"))
            if not self._has_image[i]:
                self.filename_labels[i].setText(i18n.tr("no_image_loaded"))
        self.load_normal_button.setText(
            i18n.tr("change_image_button") if self._has_normal_image else i18n.tr("load_image_button"))
        if not self._has_normal_image:
            self.normal_filename_label.setText(i18n.tr("no_image_loaded"))
        self.add_photo_button.setToolTip(i18n.tr("add_photo_tooltip"))
