"""Filmstrip sort button. Not checkable - clicking it pops up a menu (sort
field + reverse toggle), set externally via setMenu()."""
from __future__ import annotations

from PySide6.QtWidgets import QToolButton

from .svg_icons import SvgToolButton


class SortButton(SvgToolButton):
    def __init__(self, parent=None):
        super().__init__("Preview/sort.svg", parent=parent)
        self.setPopupMode(QToolButton.InstantPopup)
