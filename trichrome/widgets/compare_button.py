"""Compare toggle - dims while inactive, shows full color while active,
the same `SvgCheckableToolButton` convention every other mutually-exclusive
tool toggle in this app uses (e.g. grid_view_toggle_btn).

Previously the reverse (fading only while *active*, mirroring
FilmstripToggleButton's own fade-while-inactive state) - changed because a
dim-by-default icon reads more naturally as "available but not currently on"
than a full-brightness one did."""
from __future__ import annotations

from .svg_icons import SvgCheckableToolButton


class CompareButton(SvgCheckableToolButton):
    def __init__(self, parent=None):
        super().__init__("Filmstrip/a-b.svg", parent=parent)
