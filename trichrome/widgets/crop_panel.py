"""Crop tool panel: aspect ratio, straighten, mirror and grid controls.

The actual crop rectangle is dragged directly on the canvas (CanvasWidget's
crop overlay) and applied on Enter - this panel only holds the settings that
apply immediately (straighten/mirror/grid) plus the aspect-ratio constraint
used while dragging the rect.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QGroupBox, QHBoxLayout, QLabel, QWidget,
)

from .. import i18n
from .block_header_bar import finish_block_chrome, start_block_chrome
from .controls import CollapsibleSection, SliderSpin
from .svg_icons import (
    HEADER_COMPANION_BTN_SIZE, HEADER_COMPANION_ICON_SIZE,
    SvgCheckableToolButton, SvgIconLabel, SvgToolButton,
)

# Ordered most-square to widest (original/free/custom aren't numeric so they
# sit outside that ordering, at their existing spots).
RATIO_KEYS = ("original", "free", "1:1", "5:4", "4:3", "7:5", "3:2", "16:9", "custom")
_RATIO_ICONS = {
    "original": "Tools/Crop/aspect-ratio.svg",
    "free": "Tools/Crop/crop_free.svg",
    "1:1": "Tools/Crop/crop_1_1.svg",
    "5:4": "Tools/Crop/crop_5_4.svg",
    "4:3": "Tools/Crop/crop_4_3.svg",
    "7:5": "Tools/Crop/crop_7_5.svg",
    "3:2": "Tools/Crop/crop_3_2.svg",
    "16:9": "Tools/Crop/crop_16_9.svg",
    "custom": "Tools/Crop/aspect-ratio.svg",
}
_GRID_MODES = ("off", "3x3", "2x2", "golden", "grid")
_GRID_ICONS = {
    # No dedicated "off"/no-grid glyph - falls back to the generic one.
    "off": "Tools/Crop/grid.svg",
    "3x3": "Tools/Crop/grid_3x3.svg",
    "2x2": "Tools/Crop/grid-2x2.svg",
    "golden": "Tools/Crop/grid-golden-ratio.svg",
    "grid": "Tools/Crop/grid.svg",
}
_MIRROR_BTN_SIZE = (34, 30)
_SECTION_GAP = 8
_MIRROR_ICON_SIZE = 20
# Every block-header action button (Reset, Copy, Invert Orientation, and every
# other block's own Reset/eyedropper/Negative) shares this one size (the
# histogram block's button size) - keeps every block's header row visually
# consistent and, not incidentally, narrower.
_HEADER_BTN_SIZE = HEADER_COMPANION_BTN_SIZE
_HEADER_ICON_SIZE = HEADER_COMPANION_ICON_SIZE


class CropPanel(QGroupBox):
    settings_changed = Signal()  # straighten/mirror/grid/aspect ratio - applies immediately
    orientation_invert_requested = Signal()
    reset_requested = Signal()
    geometry_changed = Signal()  # the Geometry section's 4 lens-correction sliders
    reset_geometry_requested = Signal()
    perspective_toggled = Signal(bool)  # guided Perspective mode on/off
    activate_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._portrait = False  # last-known crop.aspect_portrait, for the ratio icon's rotation

        outer, header_row, self.title_label = start_block_chrome(self, "crop", "crop_group_title")
        header_row.addStretch(1)
        self.body, body_layout, self.collapse_button, self.close_button = finish_block_chrome(outer, header_row)

        # 2 sections: "Crop" (every pre-existing control, expanded by default)
        # and "Geometry" (the same 4 lens-correction sliders as Trichrome
        # Process's per-channel Distortion section, applied once to the whole
        # composed image - see CropSettings.distortion; collapsed by default).
        # Each section has its own Reset in its own header, same convention as
        # ChannelPanel's sections. Equal gaps above each section (block title
        # -> Crop, Crop -> Geometry) - body_layout's own spacing zeroed so
        # _SECTION_GAP is the only thing between them.
        body_layout.setSpacing(0)
        # outer already puts its own spacing between the header row and
        # body - only top up the difference.
        body_layout.addSpacing(max(0, _SECTION_GAP - outer.spacing()))
        self.crop_section = CollapsibleSection()
        self.crop_section.setChecked(True)
        # Activate + Reset live in the Crop section's own header (not the block
        # header), right-justified like Geometry's own Reset - and this Reset
        # now only resets the Crop section's fields (CropSettings.reset_crop),
        # not Geometry.
        self.crop_section.header_row.addStretch(1)
        # Activates/deactivates "active crop mode" (the interactive draggable
        # overlay on the canvas) - left of Reset so Reset stays the header's
        # right-most action, matching every other block's own header order
        # (title, [action buttons], Reset). Same icon as the top toolbar's
        # "Layout - Crop" button, since it represents the same concept
        # (entering crop mode), just reachable from inside the panel now that
        # Crop block visibility alone no longer implies active crop mode.
        self.activate_button = SvgCheckableToolButton(
            "Global/crop.svg", size=_HEADER_BTN_SIZE, icon_size=_HEADER_ICON_SIZE)
        self.activate_button.toggled.connect(self.activate_toggled.emit)
        self.crop_section.header_row.addWidget(self.activate_button)
        self.reset_button = SvgToolButton(
            "Global/Reset.svg", size=_HEADER_BTN_SIZE, icon_size=_HEADER_ICON_SIZE)
        self.reset_button.clicked.connect(self.reset_requested.emit)
        self.crop_section.header_row.addWidget(self.reset_button)
        body_layout.addWidget(self.crop_section)
        layout = self.crop_section.content_layout
        layout.addSpacing(4)

        ratio_row = QHBoxLayout()
        self.aspect_ratio_icon = SvgIconLabel(_RATIO_ICONS["original"])
        ratio_row.addWidget(self.aspect_ratio_icon)
        self.aspect_ratio_label = QLabel()
        ratio_row.addWidget(self.aspect_ratio_label)
        self.aspect_ratio_combo = QComboBox()
        self.aspect_ratio_combo.currentIndexChanged.connect(lambda _i: self._on_ratio_changed())
        ratio_row.addWidget(self.aspect_ratio_combo, stretch=1)
        self.invert_orientation_button = SvgToolButton(
            "Tools/Crop/crop_rotate.svg", size=_HEADER_BTN_SIZE, icon_size=_HEADER_ICON_SIZE)
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

        # Grid and Mirror share one row: the grid icon + dropdown on the left -
        # sized to its own content (AdjustToContents, no stretch) rather than
        # filling the row - then "Mirror" and its 2 toggles right-justified.
        grid_mirror_row = QHBoxLayout()
        self.grid_label = SvgIconLabel(_GRID_ICONS["off"])
        grid_mirror_row.addWidget(self.grid_label)
        self.grid_combo = QComboBox()
        self.grid_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.grid_combo.currentIndexChanged.connect(lambda _i: self._on_grid_changed())
        grid_mirror_row.addWidget(self.grid_combo)
        grid_mirror_row.addStretch(1)
        self.mirror_label = QLabel()
        grid_mirror_row.addWidget(self.mirror_label)
        self.mirror_h_button = SvgCheckableToolButton(
            "Tools/Crop/mirror_line.svg", size=_MIRROR_BTN_SIZE, icon_size=_MIRROR_ICON_SIZE)
        self.mirror_h_button.toggled.connect(lambda _c: self.settings_changed.emit())
        grid_mirror_row.addWidget(self.mirror_h_button)
        self.mirror_v_button = SvgCheckableToolButton(
            "Tools/Crop/mirror_line_vertical.svg", size=_MIRROR_BTN_SIZE, icon_size=_MIRROR_ICON_SIZE)
        self.mirror_v_button.toggled.connect(lambda _c: self.settings_changed.emit())
        grid_mirror_row.addWidget(self.mirror_v_button)
        layout.addLayout(grid_mirror_row)

        self.geometry_section = CollapsibleSection()
        self.reset_geometry_button = SvgToolButton(
            "Global/Reset.svg", size=_HEADER_BTN_SIZE, icon_size=_HEADER_ICON_SIZE)
        self.reset_geometry_button.clicked.connect(self.reset_geometry_requested.emit)
        self.geometry_section.header_row.addStretch(1)
        # Guided Perspective mode: draw 2 vertical or 2 horizontal guides on
        # the canvas, Enter solves Vertical/Horizontal + Straighten from them -
        # see MainWindow._set_perspective_active. Same
        # checkable-icon-left-of-Reset placement as the Crop section's own
        # Activate button.
        self.perspective_button = SvgCheckableToolButton(
            "Tools/Crop/perspective-view.svg", size=_HEADER_BTN_SIZE, icon_size=_HEADER_ICON_SIZE)
        self.perspective_button.toggled.connect(self.perspective_toggled.emit)
        self.geometry_section.header_row.addWidget(self.perspective_button)
        self.geometry_section.header_row.addWidget(self.reset_geometry_button)
        geometry_layout = self.geometry_section.content_layout
        geometry_layout.addSpacing(4)
        # Same ranges/percent_mode/i18n labels as ChannelPanel's own
        # Distortion sliders.
        self.distortion = SliderSpin(i18n.tr("distortion_label"), -1.0, 1.0, 0.0, decimals=3, percent_mode=True)
        self.perspective_v = SliderSpin(i18n.tr("perspective_v_label"), -1.0, 1.0, 0.0, decimals=3, percent_mode=True)
        self.perspective_h = SliderSpin(i18n.tr("perspective_h_label"), -1.0, 1.0, 0.0, decimals=3, percent_mode=True)
        self.anamorphic = SliderSpin(i18n.tr("anamorphic_label"), -1.0, 1.0, 0.0, decimals=3, percent_mode=True)
        for w in self._geometry_sliders():
            w.value_changed.connect(lambda _v: self.geometry_changed.emit())
            geometry_layout.addWidget(w)
        # A discreet hairline splitting Crop from Geometry, centered in the
        # same _SECTION_GAP total (so the gap still matches the one above
        # Crop) - same flat 1px look as batch_window.py's own
        # import_rules_separator, not QFrame.HLine's native groove.
        body_layout.addSpacing(_SECTION_GAP // 2)
        self.section_separator = QFrame()
        self.section_separator.setFixedHeight(1)
        self.section_separator.setStyleSheet("background: rgba(127, 127, 127, 70); border: none;")
        body_layout.addWidget(self.section_separator)
        body_layout.addSpacing(_SECTION_GAP - _SECTION_GAP // 2 - 1)
        body_layout.addWidget(self.geometry_section)

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

    def _geometry_sliders(self) -> tuple:
        return (self.distortion, self.perspective_v, self.perspective_h, self.anamorphic)

    def geometry_values(self) -> dict:
        """Same keys as CropSettings.geometry_kwargs()."""
        return {"distortion": self.distortion.value(), "perspective_v": self.perspective_v.value(),
                "perspective_h": self.perspective_h.value(), "anamorphic": self.anamorphic.value()}

    def set_perspective_active(self, active: bool) -> None:
        """Syncs perspective_button's checked state without re-emitting -
        same role as set_active() for the Crop section's Activate button."""
        self.perspective_button.blockSignals(True)
        self.perspective_button.setChecked(active)
        self.perspective_button.blockSignals(False)

    def set_geometry_reset_enabled(self, enabled: bool) -> None:
        self.reset_geometry_button.setEnabled(enabled)

    def grid_mode(self) -> str:
        return _GRID_MODES[self.grid_combo.currentIndex()]

    def set_active(self, active: bool) -> None:
        """Syncs the activate button's checked state without re-emitting
        activate_toggled - called from MainWindow._set_crop_active(),
        the single owner of whether active crop mode is actually on,
        whenever something other than a direct click on this button
        changed it (Escape, Enter-to-apply, a layout switch)."""
        self.activate_button.blockSignals(True)
        self.activate_button.setChecked(active)
        self.activate_button.blockSignals(False)

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
        for w, value in zip(self._geometry_sliders(), crop.geometry_kwargs().values()):
            w.set_value(value)  # set_value never emits value_changed
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
        self.activate_button.setToolTip(i18n.tr("crop_activate_tooltip"))
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
        self.mirror_label.setText(i18n.tr("crop_mirror_label"))
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
        self.straighten.retranslate_ui()
        self.crop_section.setTitle(i18n.tr("crop_section_title"))
        self.geometry_section.setTitle(i18n.tr("crop_geometry_section_title"))
        self.distortion.set_label_text(i18n.tr("distortion_label"))
        self.perspective_v.set_label_text(i18n.tr("perspective_v_label"))
        self.perspective_h.set_label_text(i18n.tr("perspective_h_label"))
        self.anamorphic.set_label_text(i18n.tr("anamorphic_label"))
        self.reset_geometry_button.setToolTip(i18n.tr("reset_crop_geometry_tooltip"))
        self.perspective_button.setToolTip(i18n.tr("crop_perspective_tooltip"))
