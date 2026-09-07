"""Global (whole-image) color correction, split into two peer blocks: Light
(exposure/brightness/contrast/highlights/shadows/white/black/gamma) and
Color (temperature/tint/saturation, plus white balance pick). Split from
one combined GlobalPanel into LightPanel/ColorPanel on 2026-09-04, per the
user's request - each is now a standalone block in the side-panel block
system (see block_header_bar.py), not sub-sections of one larger panel.

Negative (invert) used to live in this panel's header (moved here when
Light/Color were split out) but moved again, 2026-09-07, to the top of the
Files block (import_panel.py) - it's per-photo source state, not a Light
correction, so it belongs alongside Harris Shutter Effect there instead."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QToolButton, QWidget

from .. import i18n
from .block_header_bar import (
    finish_block_chrome, make_disabled_message_label, set_block_disabled, start_block_chrome)
from .controls import SliderSpin
from .info_bubble import show_info_bubble
from .svg_icons import HEADER_COMPANION_BTN_SIZE, HEADER_COMPANION_ICON_SIZE, SvgCheckableToolButton, SvgToolButton


class LightPanel(QGroupBox):
    changed = Signal()
    reset_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        outer, header_row, self.title_label = start_block_chrome(self, "light", "global_light_subheader")
        self.scope_info_button = QToolButton()
        self.scope_info_button.setText("?")
        self.scope_info_button.setFixedSize(18, 18)
        self.scope_info_button.setStyleSheet("QToolButton { border-radius: 9px; }")
        self.scope_info_button.clicked.connect(
            lambda: show_info_bubble(i18n.tr("global_scope_info"), self.scope_info_button))
        header_row.addWidget(self.scope_info_button)
        header_row.addStretch(1)
        self.reset_button = SvgToolButton(
            "General/Reset.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.reset_button.clicked.connect(self.reset_requested.emit)
        header_row.addWidget(self.reset_button)
        self.body, self.body_layout, self.collapse_button, self.close_button = finish_block_chrome(outer, header_row)

        self.exposure = SliderSpin(i18n.tr("exposure_label"), -5.0, 5.0, 0.0, decimals=2, percent_mode=False)
        self.brightness = SliderSpin(i18n.tr("brightness_label"), -0.5, 0.5, 0.0, decimals=3, percent_mode=True)
        self.contrast = SliderSpin(i18n.tr("contrast_label"), 0.0, 3.0, 1.0, decimals=2, percent_mode=True)
        self.highlights = SliderSpin(i18n.tr("highlights_label"), -1.0, 1.0, 0.0, decimals=2, percent_mode=True)
        self.shadows = SliderSpin(i18n.tr("shadows_label"), -1.0, 1.0, 0.0, decimals=2, percent_mode=True)
        self.white_point = SliderSpin(i18n.tr("white_point"), -0.5, 0.5, 0.0, decimals=3, percent_mode=True)
        self.black_point = SliderSpin(i18n.tr("black_point"), -0.5, 0.5, 0.0, decimals=3, percent_mode=True)
        self.gamma = SliderSpin(i18n.tr("gamma_label"), 0.1, 4.0, 1.0, decimals=2, percent_mode=True)
        self._sliders = (
            self.exposure, self.brightness, self.contrast, self.highlights, self.shadows,
            self.white_point, self.black_point, self.gamma,
        )
        for w in self._sliders:
            w.value_changed.connect(lambda _v: self.changed.emit())
            self.body_layout.addWidget(w)

        self.retranslate_ui()

    def block_signals_all(self, block: bool) -> None:
        for w in self._sliders:
            w.blockSignals(block)

    def set_sliders_enabled(self, enabled: bool) -> None:
        for w in self._sliders:
            w.setEnabled(enabled)

    def retranslate_ui(self) -> None:
        self.title_label.setText(i18n.tr("global_light_subheader"))
        self.black_point.set_label_text(i18n.tr("black_point"))
        self.white_point.set_label_text(i18n.tr("white_point"))
        self.highlights.set_label_text(i18n.tr("highlights_label"))
        self.shadows.set_label_text(i18n.tr("shadows_label"))
        self.gamma.set_label_text(i18n.tr("gamma_label"))
        self.exposure.set_label_text(i18n.tr("exposure_label"))
        self.brightness.set_label_text(i18n.tr("brightness_label"))
        self.contrast.set_label_text(i18n.tr("contrast_label"))
        self.reset_button.setToolTip(i18n.tr("reset_light_tooltip"))
        for w in self._sliders:
            w.retranslate_ui()


class ColorPanel(QGroupBox):
    changed = Signal()
    reset_requested = Signal()
    pick_white_balance_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        outer, header_row, self.title_label = start_block_chrome(self, "color", "global_color_subheader")
        self.scope_info_button = QToolButton()
        self.scope_info_button.setText("?")
        self.scope_info_button.setFixedSize(18, 18)
        self.scope_info_button.setStyleSheet("QToolButton { border-radius: 9px; }")
        self.scope_info_button.clicked.connect(
            lambda: show_info_bubble(i18n.tr("global_scope_info"), self.scope_info_button))
        header_row.addWidget(self.scope_info_button)
        header_row.addStretch(1)
        self.pick_white_balance_btn = SvgCheckableToolButton(
            "Color Correction/eyedropper.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.pick_white_balance_btn.toggled.connect(self.pick_white_balance_toggled.emit)
        header_row.addWidget(self.pick_white_balance_btn)
        self.reset_button = SvgToolButton(
            "General/Reset.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.reset_button.clicked.connect(self.reset_requested.emit)
        header_row.addWidget(self.reset_button)
        self.body, self.body_layout, self.collapse_button, self.close_button = finish_block_chrome(outer, header_row)

        # Shown instead-of/alongside the (disabled) sliders while a Solo
        # photo has the B&W film type selected (see
        # MainWindow._sync_channels_panel_availability/set_disabled_message
        # below) - same convention as Trichrome Process's own
        # channels_disabled_label for Normal mode.
        self.color_disabled_label = make_disabled_message_label()
        self.body_layout.addWidget(self.color_disabled_label)

        self.temperature = SliderSpin(i18n.tr("temperature_label"), -100, 100, 0.0, decimals=0, percent_mode=True)
        self.tint = SliderSpin(i18n.tr("tint_label"), -100, 100, 0.0, decimals=0, percent_mode=True)
        self.saturation = SliderSpin(i18n.tr("saturation_label"), 0.0, 3.0, 1.0, decimals=2, percent_mode=True)
        self._sliders = (self.temperature, self.tint, self.saturation)
        for w in self._sliders:
            w.value_changed.connect(lambda _v: self.changed.emit())
            self.body_layout.addWidget(w)

        self.retranslate_ui()

    def block_signals_all(self, block: bool) -> None:
        for w in self._sliders:
            w.blockSignals(block)

    def set_sliders_enabled(self, enabled: bool) -> None:
        for w in self._sliders:
            w.setEnabled(enabled)

    def set_disabled_message(self, message: str | None) -> None:
        """Grays out and disables the whole block (sliders, the white
        balance eyedropper, the "?" scope-info button, and the header
        Reset button - everything except collapse/close) and shows
        ``message`` in their place - pass None to clear it and re-enable
        everything. See MainWindow._sync_channels_panel_availability's
        "Solo N&B" case, the only current caller."""
        set_block_disabled(
            self.body, self.color_disabled_label, message,
            extra_widgets=(
                self.title_label, self.scope_info_button, self.pick_white_balance_btn, self.reset_button))

    def set_pick_white_balance_active(self, active: bool) -> None:
        self.pick_white_balance_btn.blockSignals(True)
        self.pick_white_balance_btn.setChecked(active)
        self.pick_white_balance_btn.blockSignals(False)

    def retranslate_ui(self) -> None:
        self.title_label.setText(i18n.tr("global_color_subheader"))
        self.saturation.set_label_text(i18n.tr("saturation_label"))
        self.temperature.set_label_text(i18n.tr("temperature_label"))
        self.tint.set_label_text(i18n.tr("tint_label"))
        self.pick_white_balance_btn.setToolTip(i18n.tr("pick_white_balance_tooltip"))
        self.reset_button.setToolTip(i18n.tr("reset_white_balance_tooltip"))
        for w in self._sliders:
            w.retranslate_ui()
