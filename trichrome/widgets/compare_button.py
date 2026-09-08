"""Compare toggle - placeholder button, behavior to be defined later.

Fades while active (same reduced intensity as FilmstripToggleButton's faded
state), the mirror of that button's fade-while-inactive."""
from __future__ import annotations

from PySide6.QtGui import QColor

from .svg_icons import SvgToolButton


class CompareButton(SvgToolButton):
    def __init__(self, parent=None):
        super().__init__("Filmstrip/a-b.svg", parent=parent)
        self.setCheckable(True)

    def _glyph_color(self) -> QColor:
        color = super()._glyph_color()
        if self.isEnabled() and not self.underMouse() and self.isChecked():
            color.setAlpha(90)
        return color
