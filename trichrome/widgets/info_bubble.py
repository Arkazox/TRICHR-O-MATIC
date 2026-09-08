"""Small speech-bubble style popups for contextual help, anchored to a widget.

Unlike QMessageBox these are lightweight, non-modal Qt::Popup windows: they
appear next to the widget that triggered them and close as soon as the user
clicks away (or, for the hover-triggered cases below, moves the cursor off
both the anchor and the bubble itself).
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractItemView, QLabel, QListWidget, QToolButton, QVBoxLayout, QWidget

from .. import i18n

_BUBBLE_HOVER_DELAY_MS = 500


class _PopupBubble(QWidget):
    """Shared paint/position code for InfoBubble and ListBubble - the one
    small dark rounded-rect popup look used throughout this app for
    lightweight contextual info, factored out once ListBubble needed the
    same chrome with different content (2026-09-07)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QColor(40, 42, 48, 235))
        painter.setPen(QPen(QColor(100, 104, 112), 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)

    def show_near(self, anchor: QWidget) -> None:
        self.adjustSize()
        pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        pos.setX(pos.x() - 10)
        pos.setY(pos.y() + 6)
        self.move(pos)
        self.show()


class InfoBubble(_PopupBubble):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(320)
        label.setStyleSheet("color: #f0f0f0; font-size: 12px; background: transparent;")
        layout.addWidget(label)


class ListBubble(_PopupBubble):
    """Same bubble chrome as InfoBubble, but holding a real (read-only,
    non-selectable) list of rows instead of a paragraph of text - used by
    the Batch Import window's Automatic-mode unmatched-files hover
    (2026-09-07), per the user's own "dans une fenêtre similaire à celle
    des boutons infos" spec. Height is capped to a handful of visible
    rows (not a fixed pixel guess) so a short list doesn't leave dead
    space and a long one scrolls instead of growing unbounded."""

    _MAX_VISIBLE_ROWS = 8

    def __init__(self, items: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.list_widget = QListWidget()
        self.list_widget.setFocusPolicy(Qt.NoFocus)
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        self.list_widget.setFrameShape(QListWidget.NoFrame)
        self.list_widget.setStyleSheet(
            "QListWidget { background: transparent; color: #f0f0f0; font-size: 12px; border: none; }")
        self.list_widget.addItems(items)
        self.list_widget.setMinimumWidth(220)
        self.list_widget.setMaximumWidth(360)
        row_height = self.list_widget.sizeHintForRow(0) if items else 18
        visible_rows = max(1, min(len(items), self._MAX_VISIBLE_ROWS))
        self.list_widget.setFixedHeight(row_height * visible_rows + 6)
        layout.addWidget(self.list_widget)

    def leaveEvent(self, event) -> None:
        # Closes itself once the cursor has genuinely left the bubble -
        # the anchor label that opened it (batch_window.py's
        # _UnmatchedSummaryLabel) only closes it defensively/on a delay,
        # specifically to give the cursor time to land here first.
        self.close()
        super().leaveEvent(event)


def show_info_bubble(text: str, anchor: QWidget) -> InfoBubble:
    bubble = InfoBubble(text, anchor)
    bubble.show_near(anchor)
    return bubble


def show_list_bubble(items: list[str], anchor: QWidget) -> ListBubble:
    bubble = ListBubble(items, anchor)
    bubble.show_near(anchor)
    return bubble


class InfoButton(QToolButton):
    """The app's standard "?" info button - a small fixed rounded circle
    that shows its InfoBubble both on click and after the cursor hovers
    statically over the button for _BUBBLE_HOVER_DELAY_MS without leaving
    (added 2026-09-07). Replaces the ~8 near-identical hand-rolled
    QToolButton-plus-lambda call sites this app had accumulated across
    main_window.py/batch_window.py/channel_panel.py/global_panel.py/
    import_panel.py - one shared class instead.

    **The two trigger paths behave differently once the bubble is open**
    (refined 2026-09-08, after the user tried the first version): a
    **click**-opened bubble stays open until the user clicks elsewhere -
    unchanged, ordinary `Qt.Popup` behavior, nothing this class has to
    implement itself. A **hover**-opened bubble instead closes itself the
    moment the cursor leaves the button - it was never asked for and
    shouldn't outlive the hover that triggered it, unlike a click's
    bubble which the user deliberately asked to see and may want to keep
    reading. `self._bubble_from_hover` tracks which path opened the
    currently-open bubble (if any) so `leaveEvent` knows whether it's
    allowed to close it.

    `info_key` is looked up via i18n.tr() fresh every time the bubble is
    actually shown (click or hover-timeout), never cached at construction
    - so a language switch is picked up automatically, with no
    retranslate_ui hook needed for the bubble text itself (matching how
    the original per-site lambdas already worked)."""

    def __init__(self, info_key: str, parent: QWidget | None = None, color: str | None = None):
        super().__init__(parent)
        self.info_key = info_key
        self.setText("?")
        self.setFixedSize(18, 18)
        if color:
            # An accented variant (added 2026-09-08 for the Batch Import
            # window's "Import Rules" title, next to the Auto-Import-
            # specific bubble) - a colored ring/glyph instead of the
            # default plain style, to visually stand out as a more
            # important callout than an ordinary "?" hint.
            self.setStyleSheet(
                f"QToolButton {{ border-radius: 9px; border: 1.5px solid {color}; "
                f"color: {color}; font-weight: bold; }}"
            )
        else:
            self.setStyleSheet("QToolButton { border-radius: 9px; }")
        self._bubble: InfoBubble | None = None
        self._bubble_from_hover = False
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._on_hover_timeout)
        self.clicked.connect(self._on_clicked)

    def _show_bubble(self, from_hover: bool) -> None:
        if self._bubble is not None:
            self._bubble.close()
        self._bubble = show_info_bubble(i18n.tr(self.info_key), self)
        self._bubble_from_hover = from_hover

    def _on_clicked(self) -> None:
        # Stop any pending hover-triggered popup so clicking while still
        # hovering doesn't pop a second, redundant bubble a moment later.
        self._hover_timer.stop()
        self._show_bubble(from_hover=False)

    def _on_hover_timeout(self) -> None:
        self._show_bubble(from_hover=True)

    def enterEvent(self, event: QEvent) -> None:
        self._hover_timer.start(_BUBBLE_HOVER_DELAY_MS)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hover_timer.stop()
        if self._bubble is not None and self._bubble_from_hover:
            self._bubble.close()
            self._bubble = None
        super().leaveEvent(event)
