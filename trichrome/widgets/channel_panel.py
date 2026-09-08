"""Per-channel (R, G or B) control panel: load image, alignment, tone correction."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QPushButton,
    QVBoxLayout, QWidget,
)

from .. import i18n
from .controls import CollapsibleSection, SliderSpin
from .info_bubble import InfoButton

CHANNEL_COLORS = {"R": "#e05555", "G": "#3fae4a", "B": "#4a7fe0"}
CHANNEL_KEY = {"R": "channel_r", "G": "channel_g", "B": "channel_b"}

# The already-established "muted gray" elsewhere in this app (e.g. the
# Mode selector's Solo icon) - used to gray out a panel's own colored
# border/title when the whole Trichrome Process block is disabled (Solo
# mode), since an explicit QSS color doesn't automatically dim the way a
# plain unstyled border would when the widget/its ancestor is disabled.
_DISABLED_BORDER_COLOR = "#5c5c5c"


class ChannelPanel(QGroupBox):
    align_changed = Signal()
    tone_changed = Signal()
    reset_align_requested = Signal()
    reset_tone_requested = Signal()
    solo_toggled = Signal(bool)
    active_toggled = Signal(bool)

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.label = label
        self._color = CHANNEL_COLORS.get(label, "#888")
        color = self._color
        self._apply_group_box_style(color)

        root = QVBoxLayout(self)

        # --- selection toggles ---
        toggle_row = QHBoxLayout()
        self.solo_checkbox = QCheckBox()
        self.solo_checkbox.toggled.connect(self.solo_toggled.emit)
        toggle_row.addWidget(self.solo_checkbox)
        root.addLayout(toggle_row)

        self.active_checkbox = QCheckBox()
        self.active_checkbox.toggled.connect(self.active_toggled.emit)
        self.active_info_button = InfoButton("active_layer_info")

        # --- alignment section (collapsible via disclosure arrow, collapsed by default) ---
        self.align_box = CollapsibleSection()
        self.align_box.setStyleSheet(f"CollapsibleSection {{ border: 1px solid {color}; border-radius: 6px; }}")
        align_layout = self.align_box.content_layout
        active_row = QHBoxLayout()
        active_row.addWidget(self.active_checkbox)
        active_row.addWidget(self.active_info_button)
        active_row.addStretch(1)
        align_layout.addLayout(active_row)
        self.dx = SliderSpin(i18n.tr("offset_x"), -500, 500, 0.0, decimals=1)
        self.dy = SliderSpin(i18n.tr("offset_y"), -500, 500, 0.0, decimals=1)
        self.scale = SliderSpin(i18n.tr("scale_label"), 0.5, 2.0, 1.0, decimals=4)
        self.rotation = SliderSpin(i18n.tr("rotation_label"), -45, 45, 0.0, decimals=2)
        for w in (self.dx, self.dy, self.scale, self.rotation):
            w.value_changed.connect(lambda _v: self.align_changed.emit())
            align_layout.addWidget(w)

        align_btn_row = QHBoxLayout()
        self.reset_align_button = QPushButton()
        self.reset_align_button.clicked.connect(self.reset_align_requested.emit)
        align_btn_row.addStretch(1)
        align_btn_row.addWidget(self.reset_align_button)
        align_layout.addLayout(align_btn_row)
        root.addWidget(self.align_box)

        # --- color correction section (collapsible via disclosure arrow, collapsed by default) ---
        self.tone_box = CollapsibleSection()
        self.tone_box.setStyleSheet(f"CollapsibleSection {{ border: 1px solid {color}; border-radius: 6px; }}")
        tone_layout = self.tone_box.content_layout
        # Real unit (stops/EV), not percent_mode - like alignment's dx/dy/
        # scale/rotation, its unit already means something on its own; see
        # CLAUDE.md on why this differs from Brightness (a plain additive
        # offset, percent_mode) despite both looking like "make it lighter".
        self.exposure = SliderSpin(i18n.tr("exposure_label"), -5.0, 5.0, 0.0, decimals=2, percent_mode=False)
        self.brightness = SliderSpin(i18n.tr("brightness_label"), -0.5, 0.5, 0.0, decimals=3, percent_mode=True)
        self.contrast = SliderSpin(i18n.tr("contrast_label"), 0.0, 3.0, 1.0, decimals=2, percent_mode=True)
        self.highlights = SliderSpin(i18n.tr("highlights_label"), -1.0, 1.0, 0.0, decimals=2, percent_mode=True)
        self.shadows = SliderSpin(i18n.tr("shadows_label"), -1.0, 1.0, 0.0, decimals=2, percent_mode=True)
        self.white_point = SliderSpin(i18n.tr("white_point"), -0.5, 0.5, 0.0, decimals=3, percent_mode=True)
        self.black_point = SliderSpin(i18n.tr("black_point"), -0.5, 0.5, 0.0, decimals=3, percent_mode=True)
        self.gamma = SliderSpin(i18n.tr("gamma_label"), 0.1, 4.0, 1.0, decimals=2, percent_mode=True)
        for w in (self.exposure, self.brightness, self.contrast, self.highlights, self.shadows,
                  self.white_point, self.black_point, self.gamma):
            w.value_changed.connect(lambda _v: self.tone_changed.emit())
            tone_layout.addWidget(w)

        tone_btn_row = QHBoxLayout()
        self.reset_tone_button = QPushButton()
        self.reset_tone_button.clicked.connect(self.reset_tone_requested.emit)
        tone_btn_row.addStretch(1)
        tone_btn_row.addWidget(self.reset_tone_button)
        tone_layout.addLayout(tone_btn_row)
        root.addWidget(self.tone_box)

        self.retranslate_ui()

    # -- helpers -------------------------------------------------------
    def _apply_group_box_style(self, color: str) -> None:
        self.setStyleSheet(f"QGroupBox {{ border: 2px solid {color}; border-radius: 6px; "
                            f"margin-top: 8px; font-weight: bold; }} "
                            f"QGroupBox::title {{ color: {color}; subcontrol-origin: margin; left: 8px; }}")

    def set_frame_disabled(self, disabled: bool) -> None:
        """Grays this panel's own colored border/title, and its 2 nested
        CollapsibleSection borders, to _DISABLED_BORDER_COLOR - restores
        the real channel color when re-enabled. Needed alongside
        setEnabled(False) (which MainWindow._sync_channels_panel_availability
        already applies to the whole Trichrome Process block, cascading
        down to this panel) because an explicit QSS color, unlike a plain
        unstyled border, doesn't automatically dim just because the widget
        (or an ancestor) is disabled - confirmed empirically the same way
        block_header_bar.set_block_disabled's own yellow message label
        needed its own explicit color to survive a disabled ancestor."""
        color = _DISABLED_BORDER_COLOR if disabled else self._color
        self._apply_group_box_style(color)
        self.align_box.setStyleSheet(f"CollapsibleSection {{ border: 1px solid {color}; border-radius: 6px; }}")
        self.tone_box.setStyleSheet(f"CollapsibleSection {{ border: 1px solid {color}; border-radius: 6px; }}")

    def block_align_signals(self, block: bool) -> None:
        for w in (self.dx, self.dy, self.scale, self.rotation):
            w.blockSignals(block)

    def block_tone_signals(self, block: bool) -> None:
        for w in (self.black_point, self.white_point, self.gamma, self.exposure, self.brightness,
                  self.contrast, self.highlights, self.shadows):
            w.blockSignals(block)

    def set_sliders_enabled(self, enabled: bool) -> None:
        for w in (self.dx, self.dy, self.scale, self.rotation,
                  self.black_point, self.white_point, self.gamma, self.exposure, self.brightness,
                  self.contrast, self.highlights, self.shadows):
            w.setEnabled(enabled)

    def retranslate_ui(self) -> None:
        self.setTitle(i18n.tr("panel_title", channel=i18n.tr(CHANNEL_KEY[self.label])))
        self.active_checkbox.setText(i18n.tr("active_checkbox"))
        self.solo_checkbox.setText(i18n.tr("solo_checkbox"))

        self.align_box.setTitle(i18n.tr("alignment_group"))
        self.dx.set_label_text(i18n.tr("offset_x"))
        self.dy.set_label_text(i18n.tr("offset_y"))
        self.scale.set_label_text(i18n.tr("scale_label"))
        self.rotation.set_label_text(i18n.tr("rotation_label"))
        self.reset_align_button.setText(i18n.tr("reset_button"))

        self.tone_box.setTitle(i18n.tr("tone_group"))
        self.black_point.set_label_text(i18n.tr("black_point"))
        self.white_point.set_label_text(i18n.tr("white_point"))
        self.highlights.set_label_text(i18n.tr("highlights_label"))
        self.shadows.set_label_text(i18n.tr("shadows_label"))
        self.gamma.set_label_text(i18n.tr("gamma_label"))
        self.exposure.set_label_text(i18n.tr("exposure_label"))
        self.brightness.set_label_text(i18n.tr("brightness_label"))
        self.contrast.set_label_text(i18n.tr("contrast_label"))
        self.reset_tone_button.setText(i18n.tr("reset_button"))

        for w in (self.dx, self.dy, self.scale, self.rotation,
                  self.black_point, self.white_point, self.gamma, self.exposure, self.brightness,
                  self.contrast, self.highlights, self.shadows):
            w.retranslate_ui()
