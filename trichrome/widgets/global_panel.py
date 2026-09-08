"""Global (whole-image) color correction, split into two peer blocks: Light
(exposure/brightness/contrast/highlights/shadows/white/black/gamma, plus
Negative) and Color (temperature/tint/saturation, plus white balance pick
and a Black & White toggle). Split from one combined GlobalPanel into
LightPanel/ColorPanel on 2026-09-04, per the user's request - each is now
a standalone block in the side-panel block system (see block_header_bar.py),
not sub-sections of one larger panel.

Negative (invert) moved briefly to the Files block (2026-09-07) alongside
Harris Shutter Effect, on the reasoning that both are per-photo source
state - then moved back here the same day, once the user settled on a
different split: Negative reads as a Light-adjacent tonal concept to a
user (it's "the first thing you'd fix about a scan," ahead of any tone
work), even though it's technically source state rather than a
correction - worth more than it's worth optimizing for internal-data-
model purity over what a user would actually go looking for.

Black & White toggle (`ColorPanel.black_white_button`), added the same
day: deliberately NOT the same thing as Trichrome's own B&W/Color choice
(the Files-block Mode combo's "B&W Trichrome"/"Color Trichrome" entries -
`import_panel.py`'s `bw_film_button`/`color_film_button` used to offer a
quicker shortcut to the same choice, removed 2026-09-07 once this toggle
made them fully redundant), which still controls Harris Shutter/decode
strategy - a structural, import-time decision about how 3 Trichrome
source files get read from disk. This one is purely cosmetic and mode-
agnostic: it never touches decode, only performs a real luminance-
weighted grayscale conversion (`imaging.apply_black_white`) as the very
last step on the already-composited/corrected image - see its own
docstring in this file and CLAUDE.md's "Mode selector" section for the
full reasoning behind keeping these two concepts genuinely independent
instead of reusing one control for both.

Originally (same day, 2026-09-07) implemented as forcing
`GlobalCorrection.saturation` to 0.0 - replaced a few hours later once
the user asked what the actual difference is between "saturation = 0"
and "a real B&W conversion": setting saturation to 0 in this app's HSV-
based saturation slider only grays a pixel to HSV's V channel
(max(R,G,B)), not a perceptually-weighted luminance, so e.g. a saturated
pure red and a saturated pure blue at the same V read as identical grays
even though the human eye (and a real film/luminance conversion) would
see the blue as clearly darker. The toggle now leaves `saturation`
completely alone and instead applies a real grayscale conversion after
every other correction - see `GlobalCorrection.black_white_active`'s own
comment in model.py."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QWidget

from .. import i18n
from .block_header_bar import finish_block_chrome, start_block_chrome
from .controls import SliderSpin
from .info_bubble import InfoButton
from .svg_icons import HEADER_COMPANION_BTN_SIZE, HEADER_COMPANION_ICON_SIZE, SvgCheckableToolButton, SvgToolButton


class LightPanel(QGroupBox):
    changed = Signal()
    reset_requested = Signal()
    invert_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        outer, header_row, self.title_label = start_block_chrome(self, "light", "global_light_subheader")
        self.scope_info_button = InfoButton("global_scope_info")
        header_row.addWidget(self.scope_info_button)
        header_row.addStretch(1)
        # Icon-only toggle (dims while off, full color while on) for
        # Negative/invert - back in this block's header (2026-09-07,
        # restored to its original home - see the module docstring above).
        self.invert_button = SvgCheckableToolButton(
            "Preview/invert.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.invert_button.toggled.connect(self.invert_toggled.emit)
        header_row.addWidget(self.invert_button)
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

    def set_invert(self, checked: bool) -> None:
        self.invert_button.blockSignals(True)
        self.invert_button.setChecked(checked)
        self.invert_button.blockSignals(False)

    def retranslate_ui(self) -> None:
        self.title_label.setText(i18n.tr("global_light_subheader"))
        self.invert_button.setToolTip(i18n.tr("invert_checkbox_tooltip"))
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
    # Purely cosmetic B&W toggle (2026-09-07) - see the module docstring
    # above for why this is deliberately independent from Trichrome's own
    # Harris-Shutter-driven B&W/Color choice. Emitted whenever the
    # button is clicked; MainWindow.on_black_white_toggled decides what
    # "black and white" actually means (a real grayscale conversion,
    # disable the rest of this panel) - this panel has no opinion on that,
    # same "widget emits, MainWindow decides" split every other toggle here
    # already follows.
    black_white_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        outer, header_row, self.title_label = start_block_chrome(self, "color", "global_color_subheader")
        self.scope_info_button = InfoButton("global_scope_info")
        header_row.addWidget(self.scope_info_button)
        header_row.addStretch(1)
        # Black & White - a single state toggle (same "dims off/full color
        # on" recipe as every other SvgCheckableToolButton here, including
        # Light's own Negative button) sitting right before the white
        # balance eyedropper, per the user's own placement spec ("en haut
        # du bouton couleur, à côté du bouton WB"). Icon moved by the user
        # from General/ to its own Color Correction/b&w.svg (2026-09-07,
        # same day as the saturation->real-grayscale rework above).
        self.black_white_button = SvgCheckableToolButton(
            "Color Correction/b&w.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.black_white_button.toggled.connect(self.black_white_toggled.emit)
        header_row.addWidget(self.black_white_button)
        self.pick_white_balance_btn = SvgCheckableToolButton(
            "Color Correction/eyedropper.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.pick_white_balance_btn.toggled.connect(self.pick_white_balance_toggled.emit)
        header_row.addWidget(self.pick_white_balance_btn)
        self.reset_button = SvgToolButton(
            "General/Reset.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.reset_button.clicked.connect(self.reset_requested.emit)
        header_row.addWidget(self.reset_button)
        self.body, self.body_layout, self.collapse_button, self.close_button = finish_block_chrome(outer, header_row)

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

    def set_black_white_active(self, active: bool) -> None:
        """Syncs the B&W toggle's own checked state and disables the
        sliders/WB eyedropper/Reset while active - the toggle itself,
        title, "?", collapse and close all stay clickable. No message
        label - the control causing this is right here, visibly checked,
        so there's nothing to explain that isn't already obvious."""
        self.black_white_button.blockSignals(True)
        self.black_white_button.setChecked(active)
        self.black_white_button.blockSignals(False)
        self.set_sliders_enabled(not active)
        self.pick_white_balance_btn.setEnabled(not active)
        self.reset_button.setEnabled(not active)

    def set_pick_white_balance_active(self, active: bool) -> None:
        self.pick_white_balance_btn.blockSignals(True)
        self.pick_white_balance_btn.setChecked(active)
        self.pick_white_balance_btn.blockSignals(False)

    def retranslate_ui(self) -> None:
        self.title_label.setText(i18n.tr("global_color_subheader"))
        self.saturation.set_label_text(i18n.tr("saturation_label"))
        self.temperature.set_label_text(i18n.tr("temperature_label"))
        self.tint.set_label_text(i18n.tr("tint_label"))
        self.black_white_button.setToolTip(i18n.tr("black_white_button_tooltip"))
        self.pick_white_balance_btn.setToolTip(i18n.tr("pick_white_balance_tooltip"))
        self.reset_button.setToolTip(i18n.tr("reset_white_balance_tooltip"))
        for w in self._sliders:
            w.retranslate_ui()
