"""A native QComboBox whose macOS arrow box uses the app's accent instead of
the system accent colour.

macOS draws a pop-up button's arrow box (the rounded square with the up/down
chevrons) in the system accent colour, and Qt exposes no way to change it.
Styling the combo with QSS would replace the whole native control, so this
keeps the native painting and repaints only that box: the same light-to-
ACCENT gradient as the checkbox/radio indicators (checkbox.py), with white
chevrons.

The box is found rather than hard-coded: the native combo is rendered once
per size/state into an image and the saturated (accent-coloured) pixels give
its rect. Where there is none (Graphite accent, a macOS version that draws
pop-ups differently, Windows), nothing is repainted and the combo stays
fully native."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QStyle, QStyleOptionComboBox

from .checkbox import ACCENT, ACCENT_LIGHT

# Minimum channel spread (max - min, 0-255) for a pixel to count as part of
# the accent box. The bezel and its label are grey (spread near 0).
_SATURATION_THRESHOLD = 80


class ComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._box_cache: dict[tuple, QRectF | None] = {}

    def _native_box_rect(self, opt: QStyleOptionComboBox) -> QRectF | None:
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr, bool(opt.state & QStyle.State_Enabled),
               bool(opt.state & QStyle.State_Sunken), self.palette().cacheKey())
        if key in self._box_cache:
            return self._box_cache[key]
        image = QImage(round(self.width() * dpr), round(self.height() * dpr), QImage.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(dpr)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        self.style().drawComplexControl(QStyle.CC_ComboBox, opt, painter, self)
        painter.end()
        pixels = np.frombuffer(image.constBits(), np.uint8).reshape(
            image.height(), image.bytesPerLine() // 4, 4)[:, :image.width()].astype(np.int16)
        rgb = pixels[..., :3]
        mask = ((rgb.max(axis=2) - rgb.min(axis=2)) > _SATURATION_THRESHOLD) & (pixels[..., 3] > 128)
        # Only the right half: the box is always at the trailing edge, and
        # this keeps a coloured label icon from ever counting.
        mask[:, : mask.shape[1] // 2] = False
        ys, xs = np.nonzero(mask)
        rect = None
        if len(xs) >= 20:
            rect = QRectF(xs.min() / dpr, ys.min() / dpr,
                          (xs.max() + 1 - xs.min()) / dpr, (ys.max() + 1 - ys.min()) / dpr)
        self._box_cache[key] = rect
        if len(self._box_cache) > 16:
            self._box_cache.pop(next(iter(self._box_cache)))
        return rect

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        rect = self._native_box_rect(opt)
        if rect is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        # Half a point larger on each side, to cover the native box's
        # antialiased edge.
        box = rect.adjusted(-0.5, -0.5, 0.5, 0.5)
        gradient = QLinearGradient(box.topLeft(), box.bottomLeft())
        gradient.setColorAt(0, QColor(ACCENT_LIGHT))
        gradient.setColorAt(1, QColor(ACCENT))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        # Same corner radius as the native bezel around it (about a quarter
        # of its height; the bezel is the box plus ~2pt on each side).
        radius = (rect.height() + 4.5) * 0.25
        painter.drawRoundedRect(box, radius, radius)

        pen = QPen(QColor("#ffffff"), 1.5)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        cx, cy = box.center().x(), box.center().y()
        half_w, gap, tip = box.width() * 0.17, box.height() * 0.09, box.height() * 0.27
        painter.drawPolyline([QPointF(cx - half_w, cy - gap), QPointF(cx, cy - tip), QPointF(cx + half_w, cy - gap)])
        painter.drawPolyline([QPointF(cx - half_w, cy + gap), QPointF(cx, cy + tip), QPointF(cx + half_w, cy + gap)])
        painter.end()
