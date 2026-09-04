"""Curves tool panel: a classic tone-curve editor block, added 2026-09-04,
split into 4 independent per-channel curves the same day ("je veux pouvoir
modifier séparément les courbes YRGB").

Header follows the same shape as every other block (title, then action
buttons, Reset last before collapse/close) - Reset here resets all 4
channel curves at once, matching every other block's own "reset everything
this block controls" convention. CurveEditor (curve_editor.py) only ever
edits one curve at a time; this class is what makes it feel like 4 curves
by swapping which one is loaded into it whenever the channel row's
selection changes, and owns the other 3 channels' data while they're not
being shown.

The Y/R/G/B channel row below the curve is a deliberate, exact visual
match for HistogramPanel's own channel-letter row (same SvgLetterToggleButton
widget, same size/colors, same "Y" first) - the user's own explicit request
("exactement les mêmes boutons... que ceux présents en dessous de
l'histogramme"). The *behavior* differs on purpose though: the histogram's
buttons isolate which channels are *shown* (any subset, several at once,
via isolate_channel/show_all_channels) with its own Reset button restoring
"all 4"; here exactly one channel is ever being *edited* at a time (there's
no "show all curves overlaid for editing" concept), so this is a true
exclusive selector with no Reset button of its own - "une seule peut etre
active à la fois, par défaut Y" was explicit."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QWidget

from .. import i18n, imaging
from .block_header_bar import finish_block_chrome, start_block_chrome
from .curve_editor import CURVE_CHANNEL_COLORS, CurveEditor
from .svg_icons import HEADER_COMPANION_BTN_SIZE, HEADER_COMPANION_ICON_SIZE, SvgLetterToggleButton, SvgToolButton

_CHANNELS = ("Y", "R", "G", "B")
_IDENTITY_POINTS = [(0.0, 0.0), (1.0, 1.0)]


class CurvesPanel(QGroupBox):
    changed = Signal()
    reset_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._active_channel = "Y"
        self._curves: dict[str, list[tuple[float, float]]] = {ch: list(_IDENTITY_POINTS) for ch in _CHANNELS}
        # The *input* histogram (pipeline state right before the curve
        # applies) for all 4 channels at once - see set_reference_histogram.
        # None until the first recompute_preview() feeds one in.
        self._reference_histograms: dict[str, object] | None = None

        outer, header_row, self.title_label = start_block_chrome(self, "curves", "curves_group_title")
        header_row.addStretch(1)
        self.reset_button = SvgToolButton(
            "General/Reset.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.reset_button.clicked.connect(self.reset_requested.emit)
        header_row.addWidget(self.reset_button)
        self.body, layout, self.collapse_button, self.close_button = finish_block_chrome(outer, header_row)

        self.curve_editor = CurveEditor()
        self.curve_editor.changed.connect(self._on_editor_changed)
        layout.addWidget(self.curve_editor)

        channel_row = QHBoxLayout()
        self._channel_buttons: dict[str, SvgLetterToggleButton] = {}
        for ch in _CHANNELS:
            btn = SvgLetterToggleButton(ch, CURVE_CHANNEL_COLORS[ch], size=(32, 28), icon_size=22)
            btn.setCheckable(False)
            btn.set_active(ch == self._active_channel)
            btn.clicked.connect(lambda _checked=False, c=ch: self._select_channel(c))
            channel_row.addWidget(btn)
            self._channel_buttons[ch] = btn
        channel_row.addStretch(1)
        layout.addLayout(channel_row)

        self.curve_editor.set_channel(self._active_channel)
        self.curve_editor.set_points(self._curves[self._active_channel])
        self.retranslate_ui()

    def _select_channel(self, channel: str) -> None:
        if channel == self._active_channel:
            return
        self._active_channel = channel
        for ch, btn in self._channel_buttons.items():
            btn.set_active(ch == channel)
        self.curve_editor.set_channel(channel)
        self.curve_editor.set_points(self._curves[channel])
        self.curve_editor.set_histogram(
            self._reference_histograms.get(channel) if self._reference_histograms else None)

    def _on_editor_changed(self) -> None:
        self._curves[self._active_channel] = self.curve_editor.points()
        self.changed.emit()

    def curves(self) -> dict[str, list[tuple[float, float]]]:
        """A fresh {"Y"/"R"/"G"/"B": points} dict - the currently-edited
        channel's latest points come straight from the live CurveEditor
        (which _on_editor_changed already mirrors into self._curves on
        every change, but reading it fresh here costs nothing and avoids
        ever trusting a stale copy)."""
        self._curves[self._active_channel] = self.curve_editor.points()
        return {ch: list(pts) for ch, pts in self._curves.items()}

    def set_curves(self, curves: dict) -> None:
        self._curves = {
            ch: [tuple(p) for p in curves.get(ch) or _IDENTITY_POINTS] for ch in _CHANNELS
        }
        self.curve_editor.set_points(self._curves[self._active_channel])

    def active_channel(self) -> str:
        """Which of Y/R/G/B is currently loaded into the editor - lets
        MainWindow key its undo-coalescing per channel, not just per photo,
        so dragging Y then immediately dragging R doesn't merge into one
        undo step covering both."""
        return self._active_channel

    def set_reference_histogram(self, rgb_uint8, valid_mask=None) -> None:
        """Computes all 4 channels' *input* histograms at once from an
        already-composited image - MainWindow.recompute_preview() calls
        this with the pipeline's state right before the curve applies
        (never its output), and only when update_curve_reference is True
        (i.e. not on every tick of a live curve drag) - see
        recompute_preview's own docstring for why that split exists. Only
        the currently-active channel's counts are actually pushed into the
        editor; the other 3 stay cached for whenever the user switches to
        them."""
        self._reference_histograms = imaging.compute_channel_histograms(rgb_uint8, valid_mask)
        self.curve_editor.set_histogram(self._reference_histograms[self._active_channel])

    def retranslate_ui(self) -> None:
        self.title_label.setText(i18n.tr("curves_group_title"))
        self.reset_button.setToolTip(i18n.tr("curves_reset_tooltip"))
