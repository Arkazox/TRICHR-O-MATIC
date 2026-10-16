"""The icons shown in dialogs and the missing-files banner, painted here so
every surface draws the same two:

- ``warning_pixmap``: a filled amber triangle with rounded corners and a dark
  "!", for errors and warnings (alerts, the missing-files banner).
- ``question_pixmap``: the app icon with that triangle as a small badge at its
  bottom-right, like a native macOS alert, for questions and confirmations
  (Mode Change, Unsaved Changes, confirm dialogs).

Both use fixed colors: amber reads on the Dark and Light appearances alike."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

from ..paths import resource_path

_AMBER_TOP = QColor("#ffd84a")
_AMBER_BOTTOM = QColor("#e8a800")
_MARK_COLOR = QColor("#2b2208")


def _blank(size: int, dpr: float) -> QPixmap:
    pixmap = QPixmap(round(size * dpr), round(size * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.transparent)
    return pixmap


def _rounded_triangle(size: float, inset: float) -> QPainterPath:
    """An upward triangle filling a ``size`` square, its corners rounded with a
    radius proportional to the size."""
    corners = [QPointF(size / 2, inset), QPointF(size - inset, size - inset - size * 0.05),
               QPointF(inset, size - inset - size * 0.05)]
    radius = size * 0.15
    path = QPainterPath()
    for i, corner in enumerate(corners):
        prev_corner, next_corner = corners[i - 1], corners[(i + 1) % len(corners)]

        def toward(target: QPointF) -> QPointF:
            v = target - corner
            return corner + v * (radius / math.hypot(v.x(), v.y()))

        start, end = toward(prev_corner), toward(next_corner)
        if i == 0:
            path.moveTo(start)
        else:
            path.lineTo(start)
        path.quadTo(corner, end)
    path.closeSubpath()
    return path


def _paint_warning(painter: QPainter, size: float, outline: bool) -> None:
    gradient = QLinearGradient(0, 0, 0, size)
    gradient.setColorAt(0, _AMBER_TOP)
    gradient.setColorAt(1, _AMBER_BOTTOM)
    painter.setPen(QPen(QColor(0, 0, 0, 90), 1.0) if outline else Qt.NoPen)
    painter.setBrush(gradient)
    painter.drawPath(_rounded_triangle(size, size * 0.05))
    # The "!": a rounded bar and a dot, centered a little below the middle,
    # where the triangle is wide enough to hold it.
    painter.setPen(Qt.NoPen)
    painter.setBrush(_MARK_COLOR)
    width = size * 0.085
    center_y = size * 0.6
    painter.drawRoundedRect(QRectF(size / 2 - width / 2, center_y - size * 0.2, width, size * 0.24),
                            width / 2, width / 2)
    painter.drawEllipse(QPointF(size / 2, center_y + size * 0.13), width * 0.62, width * 0.62)


def warning_pixmap(size: int, dpr: float) -> QPixmap:
    pixmap = _blank(size, dpr)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    _paint_warning(painter, size, outline=False)
    painter.end()
    return pixmap


def question_pixmap(size: int, dpr: float) -> QPixmap:
    pixmap = _blank(size, dpr)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    logo = QPixmap(resource_path("resources", "app_logo.png"))
    logo_size = size * 0.88
    painter.drawPixmap(QRectF(0, 0, logo_size, logo_size), logo, QRectF(logo.rect()))
    badge = size * 0.42
    painter.translate(size - badge, size - badge)
    # A faint outline keeps the badge distinct from the icon behind it.
    _paint_warning(painter, badge, outline=True)
    painter.end()
    return pixmap
