"""Thumbnails strip show/hide toggle. Only one icon exists for this glyph
(no distinct "hidden" version), so the hidden state is shown by fading the
same icon instead of swapping it."""
from __future__ import annotations

from PySide6.QtGui import QColor

from .svg_icons import SvgToolButton


class FilmstripToggleButton(SvgToolButton):
    def __init__(self, parent=None):
        super().__init__("Preview/gallery-thumbnails.svg", parent=parent)
        self.setCheckable(True)
        self.setChecked(True)

    def _glyph_color(self) -> QColor:
        color = super()._glyph_color()
        if self.isEnabled() and not self.underMouse() and not self.isChecked():
            color.setAlpha(90)
        return color
