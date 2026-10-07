"""Fullscreen show/hide toggle, swapping between the fullscreen/fullscreen_exit
SVG icons depending on state."""
from __future__ import annotations

from .svg_icons import SvgTwoStateToggleButton


class FullscreenToggleButton(SvgTwoStateToggleButton):
    def __init__(self, parent=None):
        super().__init__("Filmstrip/fullscreen_exit.svg", "Filmstrip/fullscreen.svg", initial_checked=False, parent=parent)
