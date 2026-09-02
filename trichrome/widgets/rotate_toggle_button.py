"""Quarter-turn rotate buttons, using the rotate-cw/ccw-square SVG icons."""
from __future__ import annotations

from .svg_icons import SvgToolButton


class RotateRightButton(SvgToolButton):
    def __init__(self, parent=None):
        super().__init__("Preview/rotate-cw-square.svg", parent=parent)


class RotateLeftButton(SvgToolButton):
    def __init__(self, parent=None):
        super().__init__("Preview/rotate-ccw-square.svg", parent=parent)
