"""Shared helpers for the toolbar's SVG icon buttons (resources/icons/).

Every icon there is a plain single-color glyph on a transparent background,
so recoloring it for hover/disabled/normal states doesn't depend on its own
fill/stroke color: render it, then recolor every opaque pixel in one pass
with CompositionMode_SourceIn.
"""
from __future__ import annotations

import os
import re
import tempfile

from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap, QTransform
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel, QToolButton

from .. import theme
from ..paths import icon_path

# Shared size for every block header's action buttons (Reset, Copy, Invert/
# Negative, eyedropper, the two "reset all" buttons, etc.) - every block uses
# this one size (the one the histogram block's own pick/reset buttons use), so
# header rows render pixel-identical across blocks and stay as narrow as
# possible.
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


def raw_svg_pixmap(svg_name: str, size: int, dpr: float) -> QPixmap:
    """Renders an SVG using its own embedded colors verbatim, with no
    uniform re-tint pass - for the rare icon that deliberately encodes
    meaning through multiple colors at once (e.g. the Mode selector's
    layers icon, one distinct color per layer) rather than the single-
    color-glyph convention every other icon in resources/icons/ follows."""
    renderer = QSvgRenderer(_themed_svg_bytes(svg_name))
    pixmap = QPixmap(max(1, round(size * dpr)), max(1, round(size * dpr)))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


_HEX_COLOR = re.compile(r"#([0-9a-fA-F]{6})\b")


def _themed_svg_bytes(svg_name: str) -> QByteArray:
    """The SVG as-is in the dark theme. In the light theme, its light grays
    (drawn for a dark surface: the mode icons' white/gray layers) become dark
    grays, keeping their order; colors and darker grays are left alone."""
    with open(icon_path(svg_name), encoding="utf-8") as f:
        text = f.read()
    if not theme.is_dark():
        def swap(match):
            value = match.group(1)
            r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
            if r == g == b and r >= 0x80:
                v = theme.light_gray_for_icon(r)
                return f"#{v:02x}{v:02x}{v:02x}"
            return match.group(0)
        text = _HEX_COLOR.sub(swap, text)
    return QByteArray(text.encode("utf-8"))


def recolored_svg_file(svg_name: str, color: QColor) -> str:
    """A copy of a single-color SVG with its stroke/fill set to ``color``,
    written once to the temp folder - for QSS ``image: url(...)``, which
    can't tint an icon. Returns its path (forward slashes, as QSS wants)."""
    hex_color = color.name()
    folder = os.path.join(tempfile.gettempdir(), "trichr-o-matic-icons")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{svg_name.replace('/', '_')[:-4]}-{hex_color[1:]}.svg")
    if not os.path.exists(path):
        with open(icon_path(svg_name), encoding="utf-8") as f:
            text = f.read()
        text = re.sub(r'(stroke|fill)="#[0-9a-fA-F]{3,6}"', rf'\1="{hex_color}"', text)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return path.replace("\\", "/")


def raw_svg_icon(svg_name: str, size: int, dpr: float) -> QIcon:
    """QIcon wrapper over raw_svg_pixmap - for a QComboBox/QAction/etc. item
    that needs a multi-color icon shown by Qt's own item-view chrome
    (a combo's closed box and its dropdown list both paint from a QIcon,
    not a raw pixmap) rather than one this app paints itself. The same
    pixmap serves the Selected mode, so a highlighted list item keeps the
    icon's own colors instead of Qt's tinted version."""
    pixmap = raw_svg_pixmap(svg_name, size, dpr)
    icon = QIcon(pixmap)
    icon.addPixmap(pixmap, QIcon.Selected)
    return icon


def gradient_tinted_svg_pixmap(svg_name: str, size: int, gradient: QLinearGradient, dpr: float) -> QPixmap:
    """Same idea as tinted_svg_pixmap, but recolors the glyph with a linear-
    gradient brush instead of one flat color - for a glyph that needs to read
    as multiple colors at once without hand-splitting it into several
    separately-colored paths (e.g. the Scan tool's RGB Light icon, which is the
    plain light-bulb glyph every other light mode uses, banded red/green/blue
    top-to-bottom, so it reads as "RGB" while still being recognizably the same
    bulb shape as its sibling buttons)."""
    renderer = QSvgRenderer(icon_path(svg_name))
    pixmap = QPixmap(max(1, round(size * dpr)), max(1, round(size * dpr)))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(QRectF(0, 0, size, size), gradient)
    painter.end()
    return pixmap


def gradient_tinted_svg_icon(svg_name: str, size: int, gradient: QLinearGradient, dpr: float) -> QIcon:
    return QIcon(gradient_tinted_svg_pixmap(svg_name, size, gradient, dpr))


def tinted_svg_icon(svg_name: str, size: int, color: QColor, dpr: float) -> QIcon:
    """QIcon wrapper over tinted_svg_pixmap - same use case as raw_svg_icon (a
    QComboBox/QRadioButton/etc. item painted by Qt's own item-view chrome), but
    for the common single-color-glyph case that still needs a fixed, per-item
    tint baked in (e.g. the Scan tool's per-Film-type camera-roll icon) rather
    than the glyph's own embedded colors verbatim."""
    return QIcon(tinted_svg_pixmap(svg_name, size, color, dpr))


def rotated_tinted_svg_pixmap(svg_name: str, size: int, color: QColor, dpr: float, rotation: float = 0.0) -> QPixmap:
    """Same as tinted_svg_pixmap, optionally rotated in place around its own
    center - shared by SvgIconLabel and CollapsibleSection's disclosure
    chevron (controls.py), so both use the same rotation math."""
    pixmap = tinted_svg_pixmap(svg_name, size, color, dpr)
    if rotation:
        pixmap = pixmap.transformed(QTransform().rotate(rotation), Qt.SmoothTransformation)
        pixmap.setDevicePixelRatio(dpr)
    return pixmap


class SvgToolButton(QToolButton):
    """A borderless icon button drawing one SVG glyph, tinted per state to
    match the app's existing icon-button look: palette text color normally,
    white on hover, faded when disabled.

    Hovering an enabled button draws a subtle rounded gray frame behind the
    glyph (``_HOVER_FRAME``). A subclass that sets ``_ACTIVE_FRAME`` draws an
    accent-blue frame while checked, with a white glyph."""

    _HOVER_FRAME = True
    _ACTIVE_FRAME = False
    _FRAME_RADIUS = 5.0

    def __init__(self, svg_name: str, size: tuple[int, int] = (30, 26), icon_size: int = 18,
                 parent=None):
        super().__init__(parent)
        self._svg_name = svg_name
        self._icon_size = icon_size
        self._rotation = 0.0
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(*size)
        self.setStyleSheet("QToolButton { border: none; background: transparent; }")

    def sizeHint(self) -> QSize:
        return self.size()

    def _current_svg_name(self) -> str:
        return self._svg_name

    def set_rotation(self, degrees: float) -> None:
        """Rotates the drawn icon in place around its own center - e.g. a
        disclosure chevron flipping 90° between expanded/collapsed."""
        if self._rotation != degrees:
            self._rotation = degrees
            self.update()

    def _active_frame_shown(self) -> bool:
        return self._ACTIVE_FRAME and self.isEnabled() and self.isChecked()

    def _paint_frame(self, painter: QPainter) -> None:
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self._active_frame_shown():
            painter.setPen(QPen(theme.qcolor("#5b9bd5", "#3f6d96"), 1.0))
            painter.setBrush(theme.qcolor("#3f6d96", "#5b9bd5"))
        elif self._HOVER_FRAME and self.isEnabled() and self.underMouse():
            painter.setPen(Qt.NoPen)
            painter.setBrush(theme.overlay_color(22 if theme.is_dark() else 20))
        else:
            return
        painter.drawRoundedRect(rect, self._FRAME_RADIUS, self._FRAME_RADIUS)

    def _glyph_color(self) -> QColor:
        if not self.isEnabled():
            color = QColor(self.palette().buttonText().color())
            color.setAlpha(70)
            return color
        if self._active_frame_shown():
            return QColor("#ffffff")
        if self.underMouse():
            return theme.text_color()
        return QColor(self.palette().buttonText().color())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        dpr = self.devicePixelRatioF() or 1.0
        self._paint_frame(painter)
        pixmap = tinted_svg_pixmap(self._current_svg_name(), self._icon_size, self._glyph_color(), dpr)
        if self._rotation:
            painter.translate(self.width() / 2.0, self.height() / 2.0)
            painter.rotate(self._rotation)
            painter.translate(-self.width() / 2.0, -self.height() / 2.0)
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
    """A checkable SvgToolButton (single, fixed icon) for a tool switch that
    must stay clickable in its unchecked state, unlike setEnabled(False).
    Checked shows the accent frame; unchecked is the plain icon at full
    strength. An instance with ``_ACTIVE_FRAME`` off (the toolbar workspace
    slots) has no frame, so it dims while unchecked instead."""

    _ACTIVE_FRAME = True

    def __init__(self, svg_name: str, size: tuple[int, int] = (30, 26), icon_size: int = 18, parent=None):
        super().__init__(svg_name, size=size, icon_size=icon_size, parent=parent)
        self.setCheckable(True)
        self.toggled.connect(lambda _checked: self.update())

    def _glyph_color(self) -> QColor:
        if (not self._ACTIVE_FRAME and self.isEnabled() and not self.isChecked()
                and not self.underMouse()):
            color = QColor(self.palette().buttonText().color())
            color.setAlpha(70)
            return color
        return super()._glyph_color()


class SvgColorCheckableToolButton(SvgCheckableToolButton):
    """Like SvgCheckableToolButton, but tinted to a fixed custom color
    instead of the palette's button-text color - full strength while
    checked, faded (alpha 70 - reads as a muted/"grayed" version of the
    same hue against this app's dark background, the same alpha value
    SvgCheckableToolButton's own dimmed state already uses) while
    unchecked. For a toggle whose "on" state should always read as one
    specific color rather than plain white (e.g. Files' Color Film
    button, meant to always read as orange)."""

    # The glyph's own color already shows the state.
    _ACTIVE_FRAME = False

    def __init__(self, svg_name: str, color, size: tuple[int, int] = (30, 26), icon_size: int = 18, parent=None):
        super().__init__(svg_name, size=size, icon_size=icon_size, parent=parent)
        self._color = QColor(color)

    def _glyph_color(self) -> QColor:
        color = QColor(self._color)
        color.setAlpha(255 if (self.isEnabled() and self.isChecked()) else 70)
        return color


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
        checked_svg = f"Global/circle-letter-{letter.lower()}.svg"
        unchecked_svg = f"Global/circle-dotted-letter-{letter.lower()}.svg"
        super().__init__(checked_svg, unchecked_svg, initial_checked=initial_checked,
                          size=size, icon_size=icon_size, parent=parent)
        # A callable is read at paint time (a color that follows the theme).
        self._color = color if callable(color) else QColor(color)
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
        color = QColor(self._color() if callable(self._color) else self._color)
        if not self.isEnabled():
            color.setAlpha(70)
        return color


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
        self._render_args = None
        self.set_icon(svg_name, color)
        theme.on_change(self._rerender)

    def set_icon(self, svg_name: str, color: QColor | None = None, rotation: float = 0.0) -> None:
        self._render_args = ("tint", svg_name, color, rotation)
        if color is None:
            color = QColor(self.palette().buttonText().color())
        dpr = self.devicePixelRatioF() or 1.0
        self.setPixmap(rotated_tinted_svg_pixmap(svg_name, self._icon_size, color, dpr, rotation))

    def set_icon_raw(self, svg_name: str) -> None:
        """Like set_icon(), but renders the SVG's own embedded colors
        verbatim instead of re-tinting the whole glyph to one color - see
        raw_svg_pixmap()."""
        self._render_args = ("raw", svg_name)
        dpr = self.devicePixelRatioF() or 1.0
        self.setPixmap(raw_svg_pixmap(svg_name, self._icon_size, dpr))

    def _rerender(self) -> None:
        """A palette-tinted or raw icon follows the theme; an explicit color
        is kept as it was."""
        args = self._render_args
        if args is None:
            return
        if args[0] == "raw":
            self.set_icon_raw(args[1])
        elif args[2] is None:
            self.set_icon(args[1], None, args[3])
