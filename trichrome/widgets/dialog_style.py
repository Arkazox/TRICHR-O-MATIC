"""Shared look for the plain form-style windows (Preferences, Export).

Matches Batch Import's own section style, which is the reference: a plain
section title sitting above a light framed panel. Batch Import keeps its own
QGroupBox styling and does not use this module.
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

PANEL_PADDING = 14

# Same tone as Batch Import's _RULE_SECTION_FRAME_STYLE, applied by object
# name so nested frames aren't painted too.
PANEL_STYLE = """
QFrame#dialogPanel {
    background: rgba(127, 127, 127, 20);
    border: 1px solid rgba(127, 127, 127, 70);
    border-radius: 6px;
}
"""


def make_panel(layout: QVBoxLayout) -> QVBoxLayout:
    """Adds a framed panel to ``layout`` and returns the panel's own content
    layout, already padded the same way every panel in these windows is."""
    frame = QFrame()
    frame.setObjectName("dialogPanel")
    frame.setStyleSheet(PANEL_STYLE)
    content = QVBoxLayout(frame)
    content.setContentsMargins(PANEL_PADDING, 12, PANEL_PADDING, 14)
    content.setSpacing(0)
    layout.addWidget(frame)
    return content


def make_section_title(layout: QVBoxLayout) -> QLabel:
    """Adds a plain section title above the next panel. The caller sets its
    text (usually from i18n) and keeps the returned label."""
    title = QLabel()
    layout.addWidget(title)
    layout.addSpacing(4)
    return title
