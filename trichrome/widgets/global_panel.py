"""Global (whole-image) color correction panel."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from .. import i18n
from .controls import SliderSpin
from .info_bubble import show_info_bubble
from .svg_icons import (
    HEADER_COMPANION_BTN_SIZE, HEADER_COMPANION_ICON_SIZE,
    HEADER_RESET_BTN_SIZE, HEADER_RESET_ICON_SIZE,
    SvgCheckableToolButton, SvgToolButton,
)

_RESET_BTN_SIZE = HEADER_RESET_BTN_SIZE
_RESET_ICON_SIZE = HEADER_RESET_ICON_SIZE
# The white balance pick/reset buttons share the same "companion" size as
# the header's smaller secondary actions - both are secondary actions next
# to the panel's main sliders, not a header-row Reset.
_WB_BTN_SIZE = HEADER_COMPANION_BTN_SIZE
_WB_ICON_SIZE = HEADER_COMPANION_ICON_SIZE


def _make_subheader() -> QLabel:
    """A small bold sub-section label ("Light"/"Color") - a lighter-weight
    division than the panel's own title, styled a touch muted/smaller so it
    doesn't compete with it."""
    label = QLabel()
    label.setStyleSheet("font-weight: 600; color: #a8a8ae; padding-top: 4px;")
    return label


class GlobalPanel(QGroupBox):
    changed = Signal()
    reset_requested = Signal()
    invert_toggled = Signal(bool)
    pick_white_balance_toggled = Signal(bool)
    reset_white_balance_requested = Signal()
    reset_light_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        header_row = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: bold;")
        header_row.addWidget(self.title_label)
        self.scope_info_button = QToolButton()
        self.scope_info_button.setText("?")
        self.scope_info_button.setFixedSize(18, 18)
        self.scope_info_button.setStyleSheet("QToolButton { border-radius: 9px; }")
        self.scope_info_button.clicked.connect(
            lambda: show_info_bubble(i18n.tr("global_scope_info"), self.scope_info_button))
        header_row.addWidget(self.scope_info_button)
        header_row.addStretch(1)
        # Icon-only toggle (dims while off, full color while on - same
        # SvgCheckableToolButton pattern as the top toolbar's tool switcher)
        # for Negative/invert - important enough in trichromy to sit right
        # in the header, at the same size as Reset rather than tucked below
        # as a text checkbox.
        self.invert_button = SvgCheckableToolButton(
            "Color Correction/invert_colors.svg", size=_RESET_BTN_SIZE, icon_size=_RESET_ICON_SIZE)
        self.invert_button.toggled.connect(self.invert_toggled.emit)
        header_row.addWidget(self.invert_button)
        self.reset_button = SvgToolButton(
            "General/Reset.svg", size=_RESET_BTN_SIZE, icon_size=_RESET_ICON_SIZE)
        self.reset_button.clicked.connect(self.reset_requested.emit)
        header_row.addWidget(self.reset_button)
        layout.addLayout(header_row)

        # Real unit (stops/EV), not percent_mode - see the matching note in
        # ChannelPanel/CLAUDE.md on why Exposure differs from Brightness.
        self.exposure = SliderSpin(i18n.tr("exposure_label"), -5.0, 5.0, 0.0, decimals=2, percent_mode=False)
        self.brightness = SliderSpin(i18n.tr("brightness_label"), -0.5, 0.5, 0.0, decimals=3, percent_mode=True)
        self.contrast = SliderSpin(i18n.tr("contrast_label"), 0.0, 3.0, 1.0, decimals=2, percent_mode=True)
        self.highlights = SliderSpin(i18n.tr("highlights_label"), -1.0, 1.0, 0.0, decimals=2, percent_mode=True)
        self.shadows = SliderSpin(i18n.tr("shadows_label"), -1.0, 1.0, 0.0, decimals=2, percent_mode=True)
        self.white_point = SliderSpin(i18n.tr("white_point"), -0.5, 0.5, 0.0, decimals=3, percent_mode=True)
        self.black_point = SliderSpin(i18n.tr("black_point"), -0.5, 0.5, 0.0, decimals=3, percent_mode=True)
        self.gamma = SliderSpin(i18n.tr("gamma_label"), 0.1, 4.0, 1.0, decimals=2, percent_mode=True)
        self._light_sliders = (
            self.exposure, self.brightness, self.contrast, self.highlights, self.shadows,
            self.white_point, self.black_point, self.gamma,
        )

        # Order requested for this group specifically: Temperature, Tint, Saturation.
        self.temperature = SliderSpin(i18n.tr("temperature_label"), -100, 100, 0.0, decimals=0, percent_mode=True)
        self.tint = SliderSpin(i18n.tr("tint_label"), -100, 100, 0.0, decimals=0, percent_mode=True)
        self.saturation = SliderSpin(i18n.tr("saturation_label"), 0.0, 3.0, 1.0, decimals=2, percent_mode=True)
        self._color_sliders = (self.temperature, self.tint, self.saturation)

        self._sliders = self._light_sliders + self._color_sliders
        for w in self._sliders:
            w.value_changed.connect(lambda _v: self.changed.emit())

        self.light_subheader = _make_subheader()
        light_header_row = QHBoxLayout()
        light_header_row.addWidget(self.light_subheader)
        light_header_row.addStretch(1)
        self.reset_light_btn = SvgToolButton(
            "Color Correction/reset_brightness.svg", size=_WB_BTN_SIZE, icon_size=_WB_ICON_SIZE)
        self.reset_light_btn.clicked.connect(self.reset_light_requested.emit)
        light_header_row.addWidget(self.reset_light_btn)
        layout.addLayout(light_header_row)
        for w in self._light_sliders:
            layout.addWidget(w)

        self.color_subheader = _make_subheader()
        color_header_row = QHBoxLayout()
        color_header_row.addWidget(self.color_subheader)
        color_header_row.addStretch(1)
        self.pick_white_balance_btn = SvgCheckableToolButton(
            "Color Correction/eyedropper.svg", size=_WB_BTN_SIZE, icon_size=_WB_ICON_SIZE)
        self.pick_white_balance_btn.toggled.connect(self.pick_white_balance_toggled.emit)
        color_header_row.addWidget(self.pick_white_balance_btn)
        self.reset_white_balance_btn = SvgToolButton(
            "Color Correction/reset_white_balance.svg", size=_WB_BTN_SIZE, icon_size=_WB_ICON_SIZE)
        self.reset_white_balance_btn.clicked.connect(self.reset_white_balance_requested.emit)
        color_header_row.addWidget(self.reset_white_balance_btn)
        layout.addLayout(color_header_row)

        for w in self._color_sliders:
            layout.addWidget(w)

        self.retranslate_ui()

    def block_signals_all(self, block: bool) -> None:
        for w in self._sliders:
            w.blockSignals(block)

    def set_sliders_enabled(self, enabled: bool) -> None:
        for w in self._sliders:
            w.setEnabled(enabled)

    def set_pick_white_balance_active(self, active: bool) -> None:
        self.pick_white_balance_btn.blockSignals(True)
        self.pick_white_balance_btn.setChecked(active)
        self.pick_white_balance_btn.blockSignals(False)

    def set_invert(self, checked: bool) -> None:
        self.invert_button.blockSignals(True)
        self.invert_button.setChecked(checked)
        self.invert_button.blockSignals(False)

    def retranslate_ui(self) -> None:
        self.title_label.setText(i18n.tr("global_group_title"))
        self.invert_button.setToolTip(i18n.tr("invert_checkbox_tooltip"))
        self.light_subheader.setText(i18n.tr("global_light_subheader"))
        self.color_subheader.setText(i18n.tr("global_color_subheader"))
        self.black_point.set_label_text(i18n.tr("black_point"))
        self.white_point.set_label_text(i18n.tr("white_point"))
        self.highlights.set_label_text(i18n.tr("highlights_label"))
        self.shadows.set_label_text(i18n.tr("shadows_label"))
        self.gamma.set_label_text(i18n.tr("gamma_label"))
        self.exposure.set_label_text(i18n.tr("exposure_label"))
        self.brightness.set_label_text(i18n.tr("brightness_label"))
        self.contrast.set_label_text(i18n.tr("contrast_label"))
        self.saturation.set_label_text(i18n.tr("saturation_label"))
        self.temperature.set_label_text(i18n.tr("temperature_label"))
        self.tint.set_label_text(i18n.tr("tint_label"))
        self.reset_button.setToolTip(i18n.tr("global_reset_tooltip"))
        self.pick_white_balance_btn.setToolTip(i18n.tr("pick_white_balance_tooltip"))
        self.reset_white_balance_btn.setToolTip(i18n.tr("reset_white_balance_tooltip"))
        self.reset_light_btn.setToolTip(i18n.tr("reset_light_tooltip"))
        for w in self._sliders:
            w.retranslate_ui()
