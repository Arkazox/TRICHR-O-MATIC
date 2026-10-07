"""Shared visual style for the app's plain text QPushButtons (not an icon-only
SvgToolButton, and not a checkable/exclusive toggle like the Film/Scan Light
radios or the Mode combo, both of which already have their own distinct bespoke
looks) - generalizes Quick Tour's own Back/Next button look (quick_tour.py's
TourCallout) across every dialog/panel footer button in the app that still had
the plain native OS look. Two variants, matching that reference:

- style_primary_button(): the one preferred/default action of a dialog or
  panel (Next/Finish, Export, Import, Save, Capture, Auto Align, a lone
  OK/Close, ...) - a filled accent-blue button. Reserved for whichever
  button already carried (or deserves) setDefault(True) - that was already
  this codebase's own signal for "the preferred action" before this file
  existed, so it doubles as a reliable per-dialog classifier here too.
- style_secondary_button(): every other action (Cancel, Back, Browse,
  Rescan, Clear, a Close that sits beside a real primary, ...) - a plain
  outlined button that blends into the background until hovered.

Both derive their colors from the widget's own live QPalette (Window/
WindowText), exactly like quick_tour.py's own _blend-based recipe, so dark/
light mode is picked up automatically instead of a hardcoded color."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QPushButton

# This app's one accent blue - see widgets/info_bubble.py's InfoButton and
# quick_tour.py's own ACCENT.
ACCENT = QColor("#5b9bd5")


def _blend(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t))


def style_primary_button(button: QPushButton) -> None:
    button.setStyleSheet(
        f"QPushButton {{ border: 1px solid {ACCENT.name()}; border-radius: 6px;"
        f" padding: 5px 14px; background: {ACCENT.name()}; color: white; font-weight: 600; }}"
        f" QPushButton:hover {{ background: {ACCENT.lighter(112).name()}; }}"
        f" QPushButton:pressed {{ background: {ACCENT.darker(108).name()}; }}"
        f" QPushButton:disabled {{ background: {_blend(ACCENT, QColor('#808080'), 0.5).name()};"
        " border-color: transparent; color: #e4e4e4; }"
    )


def style_secondary_button(button: QPushButton) -> None:
    pal = button.palette()
    window, text = pal.color(QPalette.Window), pal.color(QPalette.WindowText)
    border = _blend(window, text, 0.22)
    button.setStyleSheet(
        f"QPushButton {{ border: 1px solid {border.name()}; border-radius: 6px;"
        " padding: 5px 14px; background: transparent; }"
        f" QPushButton:hover {{ background: {_blend(window, text, 0.08).name()}; }}"
        f" QPushButton:pressed {{ background: {_blend(window, text, 0.14).name()}; }}"
        f" QPushButton:disabled {{ color: {_blend(window, text, 0.35).name()};"
        f" border-color: {_blend(window, text, 0.12).name()}; }}"
    )
