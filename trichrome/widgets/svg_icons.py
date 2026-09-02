"""Shared helpers for the toolbar's SVG icon buttons (resources/icons/).

Every icon there is a plain single-color glyph on a transparent background,
so recoloring it for hover/disabled/normal states doesn't depend on its own
fill/stroke color: render it, then recolor every opaque pixel in one pass
with CompositionMode_SourceIn.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap, QTransform
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel, QToolButton

from ..paths import icon_path

# Shared sizes for a panel's header row (title + action icon buttons) - the
# Crop and Global Color Correction panels both use these so their Reset
# buttons (and the smaller trailing companion icon next to it - a warning
# glyph on one, Copy/Invert Orientation on the other) render pixel-identical
# between panels, keeping the header row's layout from visibly shifting when
# switching tools.
HEADER_RESET_BTN_SIZE = (41, 36)
HEADER_RESET_ICON_SIZE = 24
HEADER_COMPANION_BTN_SIZE = (34, 30)
HEADER_COMPANION_ICON_SIZE = 20


def tinted_svg_pixmap(svg_name: str, size: int, color: QColor, dpr: float) -> QPixmap:
    renderer = QSvgRenderer(icon_path(svg_name))
    pixmap = QPixmap(max(1, round(size * dpr)), max(1, round(size * dpr)))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(QRectF(0, 0, size, size), color)
    painter.end()
    return pixmap


class SvgToolButton(QToolButton):
    """A borderless icon button drawing one SVG glyph, tinted per state to
    match the app's existing icon-button look: palette text color normally,
    white on hover, faded when disabled."""

    def __init__(self, svg_name: str, size: tuple[int, int] = (30, 26), icon_size: int = 18,
                 parent=None):
        super().__init__(parent)
        self._svg_name = svg_name
        self._icon_size = icon_size
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(*size)
        self.setStyleSheet("QToolButton { border: none; background: transparent; }")

    def sizeHint(self) -> QSize:
        return self.size()

    def _current_svg_name(self) -> str:
        return self._svg_name

    def _glyph_color(self) -> QColor:
        if not self.isEnabled():
            color = QColor(self.palette().buttonText().color())
            color.setAlpha(70)
            return color
        if self.underMouse():
            return QColor(Qt.white)
        return QColor(self.palette().buttonText().color())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        dpr = self.devicePixelRatioF() or 1.0
        pixmap = tinted_svg_pixmap(self._current_svg_name(), self._icon_size, self._glyph_color(), dpr)
        x = (self.width() - self._icon_size) / 2.0
        y = (self.height() - self._icon_size) / 2.0
        painter.drawPixmap(QPointF(x, y), pixmap)
        painter.end()

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)


class SvgTwoStateToggleButton(SvgToolButton):
    """A checkable SvgToolButton that swaps between two icons by state.
    Convention: the icon always depicts the action a click will perform
    (e.g. a "close panel" glyph while the panel is open), not the current
    state itself - matches FullscreenToggleButton's existing behavior."""

    def __init__(self, checked_svg: str, unchecked_svg: str, initial_checked: bool = True,
                 size: tuple[int, int] = (30, 26), icon_size: int = 18, parent=None):
        super().__init__(checked_svg, size=size, icon_size=icon_size, parent=parent)
        self._checked_svg = checked_svg
        self._unchecked_svg = unchecked_svg
        self.setCheckable(True)
        self.setChecked(initial_checked)

    def _current_svg_name(self) -> str:
        return self._checked_svg if self.isChecked() else self._unchecked_svg


class SvgCheckableToolButton(SvgToolButton):
    """A checkable SvgToolButton (single, fixed icon) that dims like a
    disabled button while unchecked and shows full color while checked - for
    a mutually-exclusive tool switch (e.g. via QButtonGroup) that must stay
    clickable even in its unchecked state, unlike setEnabled(False)."""

    def __init__(self, svg_name: str, size: tuple[int, int] = (30, 26), icon_size: int = 18, parent=None):
        super().__init__(svg_name, size=size, icon_size=icon_size, parent=parent)
        self.setCheckable(True)

    def _glyph_color(self) -> QColor:
        if self.isEnabled() and not self.isChecked() and not self.underMouse():
            color = QColor(self.palette().buttonText().color())
            color.setAlpha(70)
            return color
        return super()._glyph_color()


class SvgLetterToggleButton(SvgTwoStateToggleButton):
    """A checkable single-letter channel button (R/G/B/Y) drawn from the
    "Letters" icon set: the solid circle-letter glyph while active, the
    dotted one while inactive - both tinted in the channel's own fixed
    color (not the palette-based hover/disabled tinting other icon buttons
    use), so it reads as "this channel" regardless of state.

    Which icon shows is driven by ``isChecked()`` by default (e.g. Lock
    Layer Position's exclusive R/G/B group), but can be overridden
    independently via ``set_active()`` for cases where "active" isn't the
    same thing as Qt's checked state - e.g. the histogram's Y/R/G/B, where
    several can be active at once (all by default) which an exclusive
    QButtonGroup can't represent."""

    def __init__(self, letter: str, color, initial_checked: bool = False,
                 size: tuple[int, int] = (30, 26), icon_size: int = 18, parent=None):
        checked_svg = f"Letters/circle-letter-{letter.lower()}.svg"
        unchecked_svg = f"Letters/circle-dotted-letter-{letter.lower()}.svg"
        super().__init__(checked_svg, unchecked_svg, initial_checked=initial_checked,
                          size=size, icon_size=icon_size, parent=parent)
        self._color = QColor(color)
        self._active_override: bool | None = None

    def set_active(self, active: bool | None) -> None:
        """Pass True/False to force the solid/dotted icon regardless of
        isChecked(); pass None to fall back to isChecked() again."""
        if active != self._active_override:
            self._active_override = active
            self.update()

    def _current_svg_name(self) -> str:
        active = self.isChecked() if self._active_override is None else self._active_override
        return self._checked_svg if active else self._unchecked_svg

    def _glyph_color(self) -> QColor:
        if not self.isEnabled():
            color = QColor(self._color)
            color.setAlpha(70)
            return color
        return QColor(self._color)


class SvgIconLabel(QLabel):
    """A plain (non-interactive) label showing one tinted SVG icon - for a
    static decoration/status icon, as opposed to a clickable SvgToolButton.
    ``set_icon()`` lets the glyph change at runtime (e.g. to reflect which
    option is currently selected elsewhere in the same panel)."""

    def __init__(self, svg_name: str, size: int = 18, color: QColor | None = None,
                 parent=None):
        super().__init__(parent)
        self._icon_size = size
        self.setFixedSize(size, size)
        self.set_icon(svg_name, color)

    def set_icon(self, svg_name: str, color: QColor | None = None, rotation: float = 0.0) -> None:
        if color is None:
            color = QColor(self.palette().buttonText().color())
        dpr = self.devicePixelRatioF() or 1.0
        pixmap = tinted_svg_pixmap(svg_name, self._icon_size, color, dpr)
        if rotation:
            pixmap = pixmap.transformed(QTransform().rotate(rotation), Qt.SmoothTransformation)
            pixmap.setDevicePixelRatio(dpr)
        self.setPixmap(pixmap)
