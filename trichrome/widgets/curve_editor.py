"""Interactive tone-curve editor: drag round control-point handles on a
diagonal reference plot to remap the image's tone directly, classic
Photoshop/Lightroom-Curves style. Purely a UI widget - the actual smooth
spline math (monotone cubic Hermite) and per-pixel LUT application live in
imaging.evaluate_curve_lut/apply_curve, reused here only to draw the same
curve the pipeline will actually apply.

The two endpoints always exist and can't be removed, but (2026-09-04) can
move on both axes now, same as any interior point - dragging one inward
sets a black/white point (the curve clips flat beyond it, per
imaging.evaluate_curve_lut). Interior points can be added (click empty
space), dragged (x clamped between neighbors, y clamped to [0,1]), or
removed (double-click). Handles are drawn with the exact same recipe as
_ResettableSlider's own handle (controls.py) - hollow ring at rest, filled
while held - so the curve tool reads as visually part of the same slider
family rather than a different control style.

set_channel() (added 2026-09-04) recolors both the curve line and the
optional background histogram (set_histogram()) to match whichever of
Y/R/G/B is being edited - CurvesPanel is what actually owns the 4 curves
and switches which one is loaded here; this widget only ever draws one at
a time. The histogram is drawn as a translucent fill only, no outline,
directly behind the curve/grid - CurvesPanel is also responsible for
making sure the counts handed to set_histogram() are the pipeline's
*input* to the curve (unaffected by the curve itself), not its output.

The widget keeps itself square (resizeEvent pins height to width) - the
user's own explicit request, since a curve plot reads better at a 1:1
aspect than stretched to fill an arbitrary panel width."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import imaging
from .channel_panel import CHANNEL_COLORS

_IDENTITY_POINTS = [(0.0, 0.0), (1.0, 1.0)]

# Same colors HistogramPanel's own Y/R/G/B channel buttons use - Y has no
# real "channel" color of its own, just a light neutral gray.
CURVE_CHANNEL_COLORS = {
    "Y": QColor(220, 220, 220),
    "R": QColor(CHANNEL_COLORS["R"]),
    "G": QColor(CHANNEL_COLORS["G"]),
    "B": QColor(CHANNEL_COLORS["B"]),
}

_MARGIN = 10.0
_HANDLE_RADIUS = 5.5  # matches _ResettableSlider.HANDLE_RADIUS exactly
_HANDLE_BORDER = 2.0  # matches _ResettableSlider.HANDLE_BORDER exactly
_HIT_RADIUS = 11.0  # generous click-target, larger than the drawn handle itself
_MIN_X_GAP = 0.015  # minimum normalized x-separation kept between adjacent points


class CurveEditor(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._points: list[tuple[float, float]] = list(_IDENTITY_POINTS)
        self._drag_index: int | None = None
        self._channel = "Y"
        self._histogram: np.ndarray | None = None
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Keep the plot square - pin height to whatever width the layout
        # just gave this widget. Guarded so it's a no-op once already
        # square, since setFixedHeight() itself triggers another resize.
        if self.height() != self.width():
            self.setFixedHeight(self.width())

    # -- reading/writing state -------------------------------------------
    def points(self) -> list[tuple[float, float]]:
        """Always a fresh list of fresh tuples - callers (MainWindow) store
        this directly onto the model, and undo/redo snapshots the model via
        a shallow copy, so nothing here may alias the widget's own mutable
        internal list."""
        return [tuple(p) for p in self._points]

    def set_points(self, points) -> None:
        self._points = [tuple(p) for p in points] if points else list(_IDENTITY_POINTS)
        self._points.sort(key=lambda p: p[0])
        self._drag_index = None
        self.update()

    def reset(self) -> None:
        self.set_points(_IDENTITY_POINTS)

    def set_channel(self, channel: str) -> None:
        """Recolors the curve line and histogram fill to match Y/R/G/B -
        CurvesPanel calls this whenever the channel selector changes."""
        self._channel = channel
        self.update()

    def set_histogram(self, counts) -> None:
        """256-bin counts (any numeric array, or None to hide) drawn as a
        translucent fill behind the curve - the *input* histogram for
        whichever channel is currently active, per CurvesPanel."""
        self._histogram = np.asarray(counts, dtype=np.float64) if counts is not None else None
        self.update()

    # -- coordinate mapping ------------------------------------------------
    def _plot_rect(self) -> QRectF:
        m = _MARGIN
        return QRectF(m, m, max(1.0, self.width() - 2 * m), max(1.0, self.height() - 2 * m))

    def _to_widget(self, x: float, y: float) -> QPointF:
        rect = self._plot_rect()
        return QPointF(rect.left() + x * rect.width(), rect.bottom() - y * rect.height())

    def _from_widget(self, pos: QPointF) -> tuple[float, float]:
        rect = self._plot_rect()
        x = (pos.x() - rect.left()) / rect.width() if rect.width() else 0.0
        y = (rect.bottom() - pos.y()) / rect.height() if rect.height() else 0.0
        return max(0.0, min(1.0, x)), max(0.0, min(1.0, y))

    def _nearest_point_index(self, pos: QPointF) -> int | None:
        best_index, best_dist = None, _HIT_RADIUS
        for i, (x, y) in enumerate(self._points):
            d = (self._to_widget(x, y) - pos).manhattanLength()
            if d < best_dist:
                best_index, best_dist = i, d
        return best_index

    # -- mouse interaction --------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        pos = event.position() if hasattr(event, "position") else event.pos()
        pos = QPointF(pos)
        idx = self._nearest_point_index(pos)
        if idx is None:
            x, y = self._from_widget(pos)
            x = self._clamp_x_for_new_point(x)
            self._points.append((x, y))
            self._points.sort(key=lambda p: p[0])
            idx = next(i for i, p in enumerate(self._points) if p[0] == x and p[1] == y)
        self._drag_index = idx
        self.update()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_index is None:
            return
        pos = event.position() if hasattr(event, "position") else event.pos()
        x, y = self._from_widget(QPointF(pos))
        self._move_drag_point(x, y)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._drag_index is not None:
            self._drag_index = None
            self.update()
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        pos = QPointF(event.position() if hasattr(event, "position") else event.pos())
        idx = self._nearest_point_index(pos)
        if idx is not None and 0 < idx < len(self._points) - 1:
            del self._points[idx]
            self._drag_index = None
            self.update()
            self.changed.emit()
        event.accept()

    def _clamp_x_for_new_point(self, x: float) -> float:
        lo, hi = 0.0 + _MIN_X_GAP, 1.0 - _MIN_X_GAP
        for px, _py in self._points:
            if px - _MIN_X_GAP < x < px + _MIN_X_GAP:
                x = px + _MIN_X_GAP if x >= px else px - _MIN_X_GAP
        return max(lo, min(hi, x))

    def _move_drag_point(self, x: float, y: float) -> None:
        """Every point, endpoints included, clamps the same way: between
        its neighbors (or the plot's own 0.0/1.0 edge where there's no
        neighbor on that side). Endpoints can move in x now (2026-09-04,
        "j'aimerai avoir cette possibilité") - dragging one inward sets a
        black/white point, clipping the curve flat beyond it rather than
        just shifting that one edge's output vertically - see
        imaging.evaluate_curve_lut's flat-outside-the-range behavior."""
        idx = self._drag_index
        n = len(self._points)
        lo = self._points[idx - 1][0] + _MIN_X_GAP if idx > 0 else 0.0
        hi = self._points[idx + 1][0] - _MIN_X_GAP if idx < n - 1 else 1.0
        x = max(lo, min(hi, x)) if lo <= hi else self._points[idx][0]
        self._points[idx] = (x, max(0.0, min(1.0, y)))
        self.update()
        self.changed.emit()

    # -- painting ------------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self._plot_rect()

        painter.setPen(QPen(QColor(90, 90, 96), 1.0))
        painter.setBrush(QColor(38, 38, 42))
        painter.drawRect(rect)

        # Faint quarter grid, same quiet always-on tonal reference spirit as
        # the histogram's own shadow/midtone/highlight divider lines.
        grid_pen = QPen(QColor(255, 255, 255, 22), 1.0)
        painter.setPen(grid_pen)
        for frac in (0.25, 0.5, 0.75):
            gx = rect.left() + frac * rect.width()
            gy = rect.top() + frac * rect.height()
            painter.drawLine(QPointF(gx, rect.top()), QPointF(gx, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), gy), QPointF(rect.right(), gy))

        # Diagonal identity reference (input == output).
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1.0, Qt.DashLine))
        painter.drawLine(self._to_widget(0.0, 0.0), self._to_widget(1.0, 1.0))

        channel_color = CURVE_CHANNEL_COLORS.get(self._channel, CURVE_CHANNEL_COLORS["Y"])

        # The *input* histogram (the pipeline's state right before the
        # curve applies - see CurveEditor's own module docstring and
        # CurvesPanel.set_reference_histogram) - a translucent fill only,
        # no outline stroke, sitting behind the curve itself. Linear scale
        # (2026-09-04, matching the main Histogram tool's own chart - see
        # its comment for the log1p -> sqrt -> linear history).
        if self._histogram is not None and self._histogram.size:
            scaled_hist = self._histogram
            max_val = float(scaled_hist.max()) or 1.0
            n = len(scaled_hist)
            fill = QPainterPath()
            fill.moveTo(self._to_widget(0.0, 0.0))
            for i, v in enumerate(scaled_hist):
                x = i / (n - 1)
                fill.lineTo(self._to_widget(x, min(1.0, float(v) / max_val)))
            fill.lineTo(self._to_widget(1.0, 0.0))
            fill.closeSubpath()
            painter.setPen(Qt.NoPen)
            hist_color = QColor(channel_color)
            hist_color.setAlpha(70)
            painter.setBrush(hist_color)
            painter.drawPath(fill)

        # The actual smooth curve - the same evaluate_curve_lut() the
        # pipeline itself will sample from, so what's drawn always matches
        # what gets applied. Colored to match the active Y/R/G/B channel.
        lut = imaging.evaluate_curve_lut(self._points, size=128)
        path = QPainterPath()
        for i, y in enumerate(lut):
            x = i / (len(lut) - 1)
            pt = self._to_widget(x, float(y))
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        painter.setPen(QPen(channel_color, 1.8))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # Handles last, same recipe as _ResettableSlider's own handle -
        # hollow ring at rest, filled solid while the point is held.
        enabled = self.isEnabled()
        handle_color = QColor(232, 232, 232) if enabled else QColor(140, 140, 144)
        bg = self.palette().color(self.backgroundRole())
        for i, (x, y) in enumerate(self._points):
            center = self._to_widget(x, y)
            if i == self._drag_index:
                painter.setPen(Qt.NoPen)
                painter.setBrush(handle_color)
                painter.drawEllipse(center, _HANDLE_RADIUS, _HANDLE_RADIUS)
            else:
                painter.setPen(QPen(handle_color, _HANDLE_BORDER))
                painter.setBrush(bg)
                painter.drawEllipse(center, _HANDLE_RADIUS - _HANDLE_BORDER / 2, _HANDLE_RADIUS - _HANDLE_BORDER / 2)
        painter.end()
