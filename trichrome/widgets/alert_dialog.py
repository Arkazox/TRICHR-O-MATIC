"""Generic warning/error alert dialog matching the app's own look (a plain
QDialog with a tinted SVG icon and plain QPushButtons - see
unsaved_changes_dialog.py) instead of the native QMessageBox chrome. Use
show_alert() as a drop-in replacement for QMessageBox.warning/critical for
any message shown to the user from now on."""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import i18n
from .svg_icons import tinted_svg_pixmap

_ICON_SIZE = 36
_ICON_COLOR = QColor("#f2c40c")
# Caps the table's own height so a long list of rows scrolls internally
# instead of growing the dialog itself - the text above always stays put.
_TABLE_MAX_HEIGHT = 160
# Same idea for the body text itself: a long message (e.g. a raw gphoto2
# error dump) scrolls within this height instead of stretching the dialog
# past the screen - short messages just render at their own natural height,
# well under this cap.
_DETAIL_MAX_HEIGHT = 260


class AlertDialog(QDialog):
    """A single "Close" button informational/warning dialog. ``text`` is a
    fixed explanatory paragraph - pass ``table_rows`` (and matching
    ``table_headers``) instead of folding a variable-length list into
    ``text`` itself, so that list scrolls in its own bounded table rather
    than growing the dialog without limit.

    ``table_tooltips`` (one string per row, shown on hovering any cell of
    that row) and ``row_action_label``/``row_action``/``row_targets`` (a
    button, enabled once a row is selected, that calls
    ``row_action(row_targets[selected_row])`` - a per-row opaque payload,
    not necessarily the display strings themselves) are all optional and
    only meaningful together with ``table_rows``. ``row_action`` returning
    True removes that row from the table (treated as resolved); returning
    False leaves it in place so the user can try again.
    """

    def __init__(
        self, title: str, text: str, parent: QWidget | None = None,
        table_headers: tuple[str, ...] | None = None,
        table_rows: list[tuple[str, ...]] | None = None,
        table_tooltips: list[str] | None = None,
        row_action_label: str | None = None,
        row_action: Callable[[Any], bool] | None = None,
        row_targets: list[Any] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._row_action = row_action
        self._row_targets = list(row_targets) if row_targets else []

        root = QVBoxLayout(self)
        root.setSpacing(16)

        body_row = QHBoxLayout()
        body_row.setSpacing(14)

        icon_label = QLabel()
        icon_label.setPixmap(tinted_svg_pixmap(
            "General/warning.svg", _ICON_SIZE, _ICON_COLOR, self.devicePixelRatioF() or 1.0))
        icon_label.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        body_row.addWidget(icon_label, alignment=Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        text_col.addWidget(title_label)
        detail_label = QLabel(text)
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet("color: #999;")
        # Selectable/copyable (a QLabel isn't by default) - important for a
        # long/technical error message the user may need to paste elsewhere
        # (a bug report, a search, back to us) rather than retype by hand.
        detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        detail_label.setCursor(Qt.IBeamCursor)
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setFrameShape(QFrame.NoFrame)
        detail_scroll.setMaximumHeight(_DETAIL_MAX_HEIGHT)
        detail_scroll.setWidget(detail_label)
        text_col.addWidget(detail_scroll)
        body_row.addLayout(text_col, stretch=1)

        root.addLayout(body_row)

        self.table: QTableWidget | None = None
        self.row_action_button: QPushButton | None = None
        if table_rows:
            column_count = len(table_headers) if table_headers else (len(table_rows[0]) if table_rows else 0)
            table = QTableWidget(len(table_rows), column_count)
            self.table = table
            if table_headers:
                table.setHorizontalHeaderLabels(list(table_headers))
            table.verticalHeader().hide()
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setAlternatingRowColors(True)
            header = table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            for c in range(1, column_count):
                header.setSectionResizeMode(c, QHeaderView.ResizeToContents)
            for r, row in enumerate(table_rows):
                tooltip = table_tooltips[r] if table_tooltips and r < len(table_tooltips) else None
                for c, value in enumerate(row):
                    item = QTableWidgetItem(str(value))
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if tooltip:
                        item.setToolTip(tooltip)
                    table.setItem(r, c, item)
            table.setMaximumHeight(_TABLE_MAX_HEIGHT)
            root.addWidget(table)

            if row_action is not None:
                table.setSelectionBehavior(QAbstractItemView.SelectRows)
                table.setSelectionMode(QAbstractItemView.SingleSelection)
                table.itemSelectionChanged.connect(self._update_row_action_enabled)
                table.itemDoubleClicked.connect(lambda _item: self._trigger_row_action())

                action_row = QHBoxLayout()
                action_row.addStretch(1)
                self.row_action_button = QPushButton(row_action_label or "")
                self.row_action_button.setEnabled(False)
                self.row_action_button.clicked.connect(self._trigger_row_action)
                action_row.addWidget(self.row_action_button)
                root.addLayout(action_row)
            else:
                table.setSelectionMode(QAbstractItemView.NoSelection)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.close_button = QPushButton(i18n.tr("close_button"))
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)
        btn_row.addWidget(self.close_button)
        root.addLayout(btn_row)

        self.setFixedWidth(440)

    def _update_row_action_enabled(self) -> None:
        if self.row_action_button is not None and self.table is not None:
            self.row_action_button.setEnabled(self.table.currentRow() >= 0)

    def _trigger_row_action(self) -> None:
        if self.table is None or self._row_action is None:
            return
        row = self.table.currentRow()
        if not (0 <= row < len(self._row_targets)):
            return
        if self._row_action(self._row_targets[row]):
            self.table.removeRow(row)
            del self._row_targets[row]
        # Don't hardcode the button back to disabled here: removeRow()
        # auto-selects the next row (and fires itemSelectionChanged) when
        # rows remain, so re-derive the enabled state from the table's
        # actual current selection instead of assuming none is left -
        # forcing False here was disabling "Relink..." even with more
        # rows still in the table and one newly selected.
        self._update_row_action_enabled()


def show_alert(
    parent: QWidget | None, title: str, text: str,
    table_headers: tuple[str, ...] | None = None,
    table_rows: list[tuple[str, ...]] | None = None,
    table_tooltips: list[str] | None = None,
    row_action_label: str | None = None,
    row_action: Callable[[Any], bool] | None = None,
    row_targets: list[Any] | None = None,
) -> None:
    """Builds and exec()s an AlertDialog - same call shape as
    QMessageBox.warning/critical(parent, title, text), plus the optional
    scrollable table and per-row action (see AlertDialog)."""
    AlertDialog(
        title, text, parent, table_headers=table_headers, table_rows=table_rows,
        table_tooltips=table_tooltips, row_action_label=row_action_label,
        row_action=row_action, row_targets=row_targets,
    ).exec()
