"""Small RGB(+Y) histogram showing the tonal distribution of the final composed image."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .. import i18n, imaging
from .channel_panel import CHANNEL_COLORS
from .svg_icons import SvgCheckableToolButton, SvgLetterToggleButton, SvgToolButton

_CHANNELS = ("Y", "R", "G", "B")
_CHANNEL_COLORS = {
    "Y": QColor(220, 220, 220),
    "R": QColor(CHANNEL_COLORS["R"]),
    "G": QColor(CHANNEL_COLORS["G"]),
    "B": QColor(CHANNEL_COLORS["B"]),
}


class HistogramWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(110)
        self.setMaximumHeight(110)
        self._curves: dict[str, np.ndarray] | None = None
        self._clip_shadow: dict[str, float] = {}
        self._clip_highlight: dict[str, float] = {}
        self._visible = set(_CHANNELS)
        self._marker: dict[str, int] | None = None

    def set_image(self, rgb_uint8: np.ndarray, valid_mask: np.ndarray | None = None) -> None:
        """``valid_mask`` (same H×W, True/truthy where a pixel is real
        photographed content) excludes anything False from both the curves
        and the clipping fractions - used to leave out the thin black/white
        border a misaligned channel or a Straighten rotation pads the
        composite with (see imaging.compose_coverage_mask/warp_coverage_mask),
        which would otherwise read as real over/underexposure. ``None``
        means every pixel counts, unchanged from before this existed."""
        # Shared with the Curves tool's own reference-histogram overlay
        # (imaging.compute_channel_histograms) so both compute channel data
        # identically.
        self._curves = imaging.compute_channel_histograms(rgb_uint8, valid_mask)
        total = float(self._curves["Y"].sum()) if self._curves else 0.0
        if total == 0:
            self._clip_shadow = {ch: 0.0 for ch in _CHANNELS}
            self._clip_highlight = {ch: 0.0 for ch in _CHANNELS}
        else:
            self._clip_shadow = {ch: float(c[0]) / total for ch, c in self._curves.items()}
            self._clip_highlight = {ch: float(c[-1]) / total for ch, c in self._curves.items()}
        self.update()

    def clear(self) -> None:
        self._curves = None
        self._marker = None
        self.update()

    def set_marker(self, r: int, g: int, b: int) -> None:
        """Marks the tone of a single sampled pixel (the histogram pixel
        pick tool, hovering the preview) on the chart - one vertical line
        per channel, at that channel's own value. Y is derived with the
        same luma weights set_image uses, so it lines up with the Y curve."""
        y = int(round(0.299 * r + 0.587 * g + 0.114 * b))
        self._marker = {"Y": y, "R": int(r), "G": int(g), "B": int(b)}
        self.update()

    def clear_marker(self) -> None:
        self._marker = None
        self.update()

    def show_only_channel(self, channel: str) -> None:
        self._visible = {channel}
        self.update()

    def show_all_channels(self) -> None:
        self._visible = set(_CHANNELS)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        painter.fillRect(rect, QColor(24, 24, 24))
        painter.setPen(QPen(QColor(70, 70, 70)))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        if not self._curves:
            painter.end()
            return

        w = rect.width()
        h = rect.height()
        pad = 4

        # Zone guides: two fine, low-contrast vertical dividers at the
        # shadows/midtones and midtones/highlights thirds - a quiet
        # always-on reference for "where am I on the tone range", drawn
        # behind the curves themselves so they read as a background cue
        # rather than a foreground line.
        painter.setPen(QPen(QColor(255, 255, 255, 26), 1))
        for frac in (1 / 3, 2 / 3):
            x = round(w * frac)
            painter.drawLine(x, 1, x, h - 2)

        shown = [ch for ch in _CHANNELS if ch in self._visible]
        if not shown:
            painter.end()
            return
        # Linear scale (2026-09-04) - tried log1p, then sqrt, both replaced
        # after the user compared all 3 (via the temporary
        # histogram_compression_lab.py script) and preferred plain linear
        # bin counts, each channel normalized to its own tallest bin same
        # as before. A dominant clipped-bin spike does dwarf everything
        # else under this scale - accepted, since the clip indicator bars
        # below already exist specifically to surface that case regardless
        # of how tall the main curve reads.
        scaled_curves = {ch: self._curves[ch] for ch in shown}
        max_val = max(float(curve.max()) for curve in scaled_curves.values()) or 1.0

        # Lightroom-style rendering: a soft, additively-blended translucent
        # fill under each curve (so overlapping channels wash into lighter
        # composite colors instead of just occluding each other) plus a
        # fully solid outline traced along the curve itself, drawn in a
        # second pass with normal blending so it stays crisp/legible on top
        # of the wash instead of also brightening when curves overlap.
        curve_paths: dict[str, QPainterPath] = {}
        fill_paths: dict[str, QPainterPath] = {}
        for ch in shown:
            curve = scaled_curves[ch]
            n = len(curve)
            outline = QPainterPath()
            for i, v in enumerate(curve):
                x = i / (n - 1) * w
                y = h - (v / max_val) * (h - pad)
                if i == 0:
                    outline.moveTo(x, y)
                else:
                    outline.lineTo(x, y)
            curve_paths[ch] = outline
            fill = QPainterPath(outline)
            fill.lineTo(w, h)
            fill.lineTo(0, h)
            fill.closeSubpath()
            fill_paths[ch] = fill

        painter.setCompositionMode(QPainter.CompositionMode_Plus)
        painter.setPen(Qt.NoPen)
        for ch in shown:
            fill_color = QColor(_CHANNEL_COLORS[ch])
            fill_color.setAlpha(60)
            painter.setBrush(fill_color)
            painter.drawPath(fill_paths[ch])

        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setBrush(Qt.NoBrush)
        for ch in shown:
            line_color = QColor(_CHANNEL_COLORS[ch])
            line_color.setAlpha(235)
            painter.setPen(QPen(line_color, 1.3))
            painter.drawPath(curve_paths[ch])

        # Clipping indicators: a thin bar at each edge per channel that has a
        # non-negligible fraction of pixels pinned at 0 or 255 — the scaled
        # curve alone can still under-represent how much detail is lost there.
        # Height *and* opacity both scale with the clipped fraction instead of
        # jumping straight to a fixed size at the threshold - a fraction just
        # over the threshold (a sliver of real clipping, or a thin residual
        # misalignment/rotation border valid_mask didn't fully catch) reads as
        # a faint hint, while a large blown-out region still reads as a solid,
        # obvious bar. Reference point: 5% clipped reaches full height/opacity.
        bar_w = 3
        threshold = 0.001
        full_scale_at = 0.05
        for ch in shown:
            color = _CHANNEL_COLORS[ch]
            shadow_frac = self._clip_shadow[ch]
            if shadow_frac > threshold:
                severity = min(1.0, shadow_frac / full_scale_at)
                bar_h = max(2.0, severity * h)
                bar_color = QColor(color)
                bar_color.setAlpha(round(110 + severity * 125))
                painter.setBrush(bar_color)
                painter.drawRect(0, int(h - bar_h), bar_w, int(bar_h))
            highlight_frac = self._clip_highlight[ch]
            if highlight_frac > threshold:
                severity = min(1.0, highlight_frac / full_scale_at)
                bar_h = max(2.0, severity * h)
                bar_color = QColor(color)
                bar_color.setAlpha(round(110 + severity * 125))
                painter.setBrush(bar_color)
                painter.drawRect(w - bar_w, int(h - bar_h), bar_w, int(bar_h))

        # Pixel-pick marker: one dashed vertical line per shown channel, at
        # that channel's own value for whatever pixel is currently hovered
        # in the preview - drawn last so it always reads on top of the
        # curves/fills/clip bars underneath it.
        if self._marker is not None:
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setBrush(Qt.NoBrush)
            for ch in shown:
                value = self._marker[ch]
                x = value / 255 * w
                pen = QPen(_CHANNEL_COLORS[ch], 1.5, Qt.DashLine)
                painter.setPen(pen)
                painter.drawLine(int(x), 0, int(x), h)

        painter.end()


class HistogramPanel(QWidget):
    """The histogram chart plus its Y/R/G/B channel buttons (clicking one
    isolates that channel's curve) and a reset button that brings back all
    four at once - all four are active (solid icon) by default, since all
    four are shown by default.

    These buttons aren't a Qt-checkable exclusive group: "active" here means
    "currently shown", and all four are active simultaneously in the default
    state, which an exclusive QButtonGroup can't represent (it always keeps
    exactly one checked). Each button's solid/dotted icon is driven directly
    via SvgLetterToggleButton.set_active() instead.

    ``isolate_channel``/``show_all_channels`` are the public entry points a
    caller outside this widget (MainWindow, linking a channel's Solo B&W
    preview to its scope here) should use instead of reaching into
    ``.chart`` directly. ``reset_requested`` fires only when the Reset
    *button* itself is clicked - not when ``show_all_channels()`` is called
    programmatically - so MainWindow can tell "the user asked to see
    everything again" apart from its own show_all_channels() calls (e.g.
    when Solo is turned off directly) without looping back on itself.

    ``pick_button`` arms a live pixel-value readout: while checked, the
    caller (MainWindow, listening to the canvas's own hover signals) feeds
    ``set_marker(r, g, b)`` for whatever pixel is under the cursor in the
    preview, drawn as a dashed vertical line per channel on the chart;
    ``clear_marker()`` (also called automatically when the button is
    unchecked) removes it. ``pick_toggled`` re-emits the button's own
    ``toggled`` for that wiring, mirroring ColorPanel's
    ``pick_white_balance_btn``/``pick_white_balance_toggled``."""

    reset_requested = Signal()
    pick_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.chart = HistogramWidget()
        layout.addWidget(self.chart)

        toggle_row = QHBoxLayout()
        self._channel_buttons: dict[str, SvgLetterToggleButton] = {}
        for ch in _CHANNELS:
            btn = SvgLetterToggleButton(ch, _CHANNEL_COLORS[ch], size=(32, 28), icon_size=22)
            btn.setCheckable(False)
            btn.set_active(True)
            btn.clicked.connect(lambda _checked=False, c=ch: self.isolate_channel(c))
            toggle_row.addWidget(btn)
            self._channel_buttons[ch] = btn
        toggle_row.addStretch(1)
        self.pick_button = SvgCheckableToolButton(
            "Global/eyedropper.svg", size=(34, 30), icon_size=20)
        self.pick_button.toggled.connect(self._on_pick_toggled)
        self.pick_button.toggled.connect(self.pick_toggled.emit)
        toggle_row.addWidget(self.pick_button)
        self.reset_button = SvgToolButton("Global/Reset.svg", size=(34, 30), icon_size=20)
        self.reset_button.clicked.connect(self._on_reset_clicked)
        toggle_row.addWidget(self.reset_button)
        layout.addLayout(toggle_row)

        self.retranslate_ui()

    def isolate_channel(self, channel: str) -> None:
        self.chart.show_only_channel(channel)
        for ch, btn in self._channel_buttons.items():
            btn.set_active(ch == channel)

    def show_all_channels(self) -> None:
        self.chart.show_all_channels()
        for btn in self._channel_buttons.values():
            btn.set_active(True)

    def _on_reset_clicked(self) -> None:
        self.show_all_channels()
        self.reset_requested.emit()

    def _on_pick_toggled(self, checked: bool) -> None:
        if not checked:
            self.chart.clear_marker()

    def set_image(self, rgb_uint8: np.ndarray, valid_mask: np.ndarray | None = None) -> None:
        self.chart.set_image(rgb_uint8, valid_mask=valid_mask)

    def clear(self) -> None:
        self.chart.clear()

    def set_marker(self, r: int, g: int, b: int) -> None:
        self.chart.set_marker(r, g, b)

    def clear_marker(self) -> None:
        self.chart.clear_marker()

    def retranslate_ui(self) -> None:
        self.pick_button.setToolTip(i18n.tr("histogram_pick_tooltip"))
