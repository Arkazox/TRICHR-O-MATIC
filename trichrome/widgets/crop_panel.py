"""Crop tool panel: aspect ratio, straighten, mirror and grid controls.

The actual crop rectangle is dragged directly on the canvas (CanvasWidget's
crop overlay) and applied on Enter - this panel only holds the settings that
apply immediately (straighten/mirror/grid) plus the aspect-ratio constraint
used while dragging the rect.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QGroupBox, QHBoxLayout, QLabel,
    QVBoxLayout, QWidget,
)

from .. import i18n
from .controls import SliderSpin
from .svg_icons import (
    HEADER_COMPANION_BTN_SIZE, HEADER_COMPANION_ICON_SIZE,
    HEADER_RESET_BTN_SIZE, HEADER_RESET_ICON_SIZE,
    SvgCheckableToolButton, SvgIconLabel, SvgToolButton,
)

# Ordered most-square to widest (original/free/custom aren't numeric so they
# sit outside that ordering, at their existing spots).
RATIO_KEYS = ("original", "free", "1:1", "5:4", "4:3", "7:5", "3:2", "16:9", "custom")
_RATIO_ICONS = {
    "original": "Crop/aspect-ratio.svg",
    "free": "Crop/crop_free.svg",
    "1:1": "Crop/crop_1_1.svg",
    "5:4": "Crop/crop_5_4.svg",
    "4:3": "Crop/crop_4_3.svg",
    "7:5": "Crop/crop_7_5.svg",
    "3:2": "Crop/crop_3_2.svg",
    "16:9": "Crop/crop_16_9.svg",
    "custom": "Crop/aspect-ratio.svg",
}
_GRID_MODES = ("off", "3x3", "2x2", "golden", "grid")
_GRID_ICONS = {
    # No dedicated "off"/no-grid glyph - falls back to the generic one.
    "off": "Crop/grid.svg",
    "3x3": "Crop/grid_3x3.svg",
    "2x2": "Crop/grid-2x2.svg",
    "golden": "Crop/grid-golden-ratio.svg",
    "grid": "Crop/grid.svg",
}
_MIRROR_BTN_SIZE = (34, 30)
_MIRROR_ICON_SIZE = 20
# Reset matches Global Color Correction's Reset exactly (same shared
# constants); Copy and Invert Orientation are the smaller "companion" size,
# mirroring how that panel's warning glyph stays smaller next to its Reset -
# together this keeps both panels' header rows the same width/shape so
# nothing shifts when switching tools.
_HEADER_BTN_SIZE = HEADER_COMPANION_BTN_SIZE
_HEADER_ICON_SIZE = HEADER_COMPANION_ICON_SIZE


class CropPanel(QGroupBox):
    settings_changed = Signal()  # straighten/mirror/grid/aspect ratio - applies immediately
    orientation_invert_requested = Signal()
    reset_requested = Signal()
    copy_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self._portrait = False  # last-known crop.aspect_portrait, for the ratio icon's rotation

        header_row = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: bold;")
        header_row.addWidget(self.title_label)
        header_row.addStretch(1)
        self.reset_button = SvgToolButton(
            "General/Reset.svg", size=HEADER_RESET_BTN_SIZE, icon_size=HEADER_RESET_ICON_SIZE)
        self.reset_button.clicked.connect(self.reset_requested.emit)
        header_row.addWidget(self.reset_button)
        self.copy_button = SvgToolButton(
            "General/copy.svg", size=_HEADER_BTN_SIZE, icon_size=_HEADER_ICON_SIZE)
        self.copy_button.clicked.connect(self.copy_requested.emit)
        header_row.addWidget(self.copy_button)
        layout.addLayout(header_row)

        ratio_row = QHBoxLayout()
        self.aspect_ratio_icon = SvgIconLabel(_RATIO_ICONS["original"])
        ratio_row.addWidget(self.aspect_ratio_icon)
        self.aspect_ratio_label = QLabel()
        ratio_row.addWidget(self.aspect_ratio_label)
        self.aspect_ratio_combo = QComboBox()
        self.aspect_ratio_combo.currentIndexChanged.connect(lambda _i: self._on_ratio_changed())
        ratio_row.addWidget(self.aspect_ratio_combo, stretch=1)
        self.invert_orientation_button = SvgToolButton(
            "Crop/crop_rotate.svg", size=_HEADER_BTN_SIZE, icon_size=_HEADER_ICON_SIZE)
        self.invert_orientation_button.clicked.connect(self.orientation_invert_requested.emit)
        ratio_row.addWidget(self.invert_orientation_button)
        layout.addLayout(ratio_row)

        self.custom_ratio_row = QHBoxLayout()
        self.custom_ratio_w = QDoubleSpinBox()
        self.custom_ratio_w.setRange(0.1, 100.0)
        self.custom_ratio_w.setValue(1.0)
        self.custom_ratio_w.setDecimals(1)
        self.custom_ratio_row.addWidget(self.custom_ratio_w)
        self.custom_ratio_sep_label = QLabel(":")
        self.custom_ratio_row.addWidget(self.custom_ratio_sep_label)
        self.custom_ratio_h = QDoubleSpinBox()
        self.custom_ratio_h.setRange(0.1, 100.0)
        self.custom_ratio_h.setValue(1.0)
        self.custom_ratio_h.setDecimals(1)
        self.custom_ratio_row.addWidget(self.custom_ratio_h)
        self.custom_ratio_w.valueChanged.connect(self._on_custom_ratio_changed)
        self.custom_ratio_h.valueChanged.connect(self._on_custom_ratio_changed)
        self.custom_ratio_row.addStretch(1)
        layout.addLayout(self.custom_ratio_row)

        self.straighten = SliderSpin(i18n.tr("crop_straighten_label"), -45.0, 45.0, 0.0, decimals=2)
        self.straighten.value_changed.connect(lambda _v: self.settings_changed.emit())
        layout.addWidget(self.straighten)

        mirror_row = QHBoxLayout()
        self.mirror_h_button = SvgCheckableToolButton(
            "Crop/mirror_line.svg", size=_MIRROR_BTN_SIZE, icon_size=_MIRROR_ICON_SIZE)
        self.mirror_h_button.toggled.connect(lambda _c: self.settings_changed.emit())
        mirror_row.addWidget(self.mirror_h_button)
        self.mirror_v_button = SvgCheckableToolButton(
            "Crop/mirror_line_vertical.svg", size=_MIRROR_BTN_SIZE, icon_size=_MIRROR_ICON_SIZE)
        self.mirror_v_button.toggled.connect(lambda _c: self.settings_changed.emit())
        mirror_row.addWidget(self.mirror_v_button)
        mirror_row.addStretch(1)
        layout.addLayout(mirror_row)

        grid_row = QHBoxLayout()
        self.grid_label = SvgIconLabel(_GRID_ICONS["off"])
        grid_row.addWidget(self.grid_label)
        self.grid_combo = QComboBox()
        self.grid_combo.currentIndexChanged.connect(lambda _i: self._on_grid_changed())
        grid_row.addWidget(self.grid_combo, stretch=1)
        layout.addLayout(grid_row)

        self.apply_hint_label = QLabel()
        self.apply_hint_label.setStyleSheet("color: #888; padding-top: 6px;")
        layout.addWidget(self.apply_hint_label)

        self.retranslate_ui()
        self.grid_combo.setCurrentIndex(1)  # "3 x 3" is the default grid
        self._sync_custom_ratio_visibility()
        self._sync_invert_enabled()

    # -- reading current settings ---------------------------------------
    def aspect_ratio(self) -> str:
        return RATIO_KEYS[self.aspect_ratio_combo.currentIndex()]

    def custom_ratio(self) -> tuple[float, float]:
        return self.custom_ratio_w.value(), self.custom_ratio_h.value()

    def straighten_value(self) -> float:
        return self.straighten.value()

    def is_mirrored_h(self) -> bool:
        return self.mirror_h_button.isChecked()

    def is_mirrored_v(self) -> bool:
        return self.mirror_v_button.isChecked()

    def grid_mode(self) -> str:
        return _GRID_MODES[self.grid_combo.currentIndex()]

    # -- writing settings (e.g. from a freshly-activated photo) ---------
    def set_from_crop(self, crop) -> None:
        self.aspect_ratio_combo.blockSignals(True)
        self.aspect_ratio_combo.setCurrentIndex(RATIO_KEYS.index(crop.aspect_ratio))
        self.aspect_ratio_combo.blockSignals(False)
        self.custom_ratio_w.blockSignals(True)
        self.custom_ratio_w.setValue(crop.custom_ratio_w)
        self.custom_ratio_w.blockSignals(False)
        self.custom_ratio_h.blockSignals(True)
        self.custom_ratio_h.setValue(crop.custom_ratio_h)
        self.custom_ratio_h.blockSignals(False)
        self.straighten.set_value(crop.rotation)
        self.mirror_h_button.blockSignals(True)
        self.mirror_h_button.setChecked(crop.mirror_h)
        self.mirror_h_button.blockSignals(False)
        self.mirror_v_button.blockSignals(True)
        self.mirror_v_button.setChecked(crop.mirror_v)
        self.mirror_v_button.blockSignals(False)
        self._portrait = crop.aspect_portrait
        self._sync_custom_ratio_visibility()
        self._sync_ratio_icon()
        self._sync_invert_enabled()

    def _on_ratio_changed(self) -> None:
        self._sync_custom_ratio_visibility()
        self._sync_ratio_icon()
        self._sync_invert_enabled()
        self.settings_changed.emit()

    def _on_custom_ratio_changed(self, _v: float) -> None:
        self._sync_invert_enabled()
        self.settings_changed.emit()

    def _on_grid_changed(self) -> None:
        self.grid_label.set_icon(_GRID_ICONS[self.grid_mode()])
        self.settings_changed.emit()

    def _sync_ratio_icon(self) -> None:
        self.aspect_ratio_icon.set_icon(
            _RATIO_ICONS[self.aspect_ratio()], rotation=90.0 if self._portrait else 0.0)

    def _ratio_invert_meaningful(self) -> bool:
        """Whether "invert orientation" would actually change anything for
        the current ratio - not for "free" (unconstrained) or "1:1"
        (swapping W:H is a no-op), nor a custom ratio someone set to W==H."""
        key = self.aspect_ratio()
        if key in ("free", "1:1"):
            return False
        if key == "custom":
            w, h = self.custom_ratio()
            return w != h
        return True

    def _sync_invert_enabled(self) -> None:
        self.invert_orientation_button.setEnabled(self._ratio_invert_meaningful())

    def _sync_custom_ratio_visibility(self) -> None:
        is_custom = self.aspect_ratio() == "custom"
        self.custom_ratio_w.setVisible(is_custom)
        self.custom_ratio_sep_label.setVisible(is_custom)
        self.custom_ratio_h.setVisible(is_custom)

    def retranslate_ui(self) -> None:
        self.title_label.setText(i18n.tr("crop_group_title"))
        self.reset_button.setToolTip(i18n.tr("crop_reset_tooltip"))
        self.copy_button.setToolTip(i18n.tr("crop_copy_tooltip"))
        self.aspect_ratio_label.setText(i18n.tr("crop_aspect_ratio_label"))
        current = self.aspect_ratio_combo.currentIndex()
        self.aspect_ratio_combo.blockSignals(True)
        self.aspect_ratio_combo.clear()
        for key in RATIO_KEYS:
            if key == "original":
                self.aspect_ratio_combo.addItem(i18n.tr("crop_ratio_original"))
            elif key == "free":
                self.aspect_ratio_combo.addItem(i18n.tr("crop_ratio_free"))
            elif key == "custom":
                self.aspect_ratio_combo.addItem(i18n.tr("crop_ratio_custom"))
            else:
                self.aspect_ratio_combo.addItem(key)
        self.aspect_ratio_combo.setCurrentIndex(max(0, current))
        self.aspect_ratio_combo.blockSignals(False)
        self.invert_orientation_button.setToolTip(i18n.tr("crop_invert_orientation_button"))
        self.mirror_h_button.setToolTip(i18n.tr("crop_mirror_h_button"))
        self.mirror_v_button.setToolTip(i18n.tr("crop_mirror_v_button"))
        self.grid_label.setToolTip(i18n.tr("crop_grid_label"))
        current_grid = self.grid_combo.currentIndex()
        self.grid_combo.blockSignals(True)
        self.grid_combo.clear()
        self.grid_combo.addItem(i18n.tr("crop_grid_off"))
        self.grid_combo.addItem(i18n.tr("crop_grid_3x3"))
        self.grid_combo.addItem(i18n.tr("crop_grid_2x2"))
        self.grid_combo.addItem(i18n.tr("crop_grid_golden"))
        self.grid_combo.addItem(i18n.tr("crop_grid_squares"))
        self.grid_combo.setCurrentIndex(max(0, current_grid))
        self.grid_combo.blockSignals(False)
        self.apply_hint_label.setText(i18n.tr("crop_apply_hint"))
        self.straighten.retranslate_ui()
