"""Filmstrip of imported batch photos, at the bottom of the preview - and,
in "grid mode", the exact same widget/cards/selection/reorder/context-menu
logic shown as a full responsive grid standing in for the preview canvas
(see set_grid_mode(), toggled by MainWindow as the filmstrip's own
"fullscreen" mode). Only the cards' container/layout and size change
between the two modes - every card is the same _CarouselCard instance
either way, so nothing about selection, drag-reorder or the context menu
needs to be reimplemented for the grid.

Plain click / arrow-key navigation picks the "current" photo (the one shown
and edited in the main window) and, by default, makes it the sole selection.
Cmd+click toggles a photo in/out of the selection without changing which one
is current; Cmd+A selects all (or deselects all, if everything is already
selected) - that selection is what "export selected" uses.

Cards can also be dragged to reorder - a drop anywhere (including past the
last card, or in any empty grid cell) is resolved to an insertion point and
reported upward via ``reordered`` as a permutation of the old indices.

The strip/grid is also a drop target for image files dragged in from Finder
- those are reported upward via ``files_dropped`` (a plain list of local
paths) rather than handled here, since deciding what to do with them
(new Normal-mode photos, appended at the end) is MainWindow's job.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QMimeData, QPointF, Qt, Signal
from PySide6.QtGui import QDrag, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget

from .. import i18n
from .controls import ArrowKeyScrollArea

THUMB_W, THUMB_H = 96, 64
CURRENT_COLOR = "#f2c40c"
SELECTED_COLOR = "#8a7a3a"
DEFAULT_COLOR = "#444"

# Grid mode (fullscreen) sizing - cards fill the available width, Zoom
# In/Out (see MainWindow.on_zoom_in_clicked/on_zoom_out_clicked) only
# change the column count; the cell size is derived to always fill the row.
MIN_GRID_COLUMNS = 1
MAX_GRID_COLUMNS = 24
MIN_GRID_CELL_SIZE = 40
_GRID_SPACING = 8
_GRID_MARGIN = 8
_GRID_CELL_CHROME = 14  # matches _CarouselCard's own thumb_w + 14 chrome convention
_INITIAL_GRID_CELL_TARGET = THUMB_W  # ~96px, used only to pick the starting column count

_REORDER_MIME = "application/x-trichrome-carousel-index"
# Same set load_image's own file-picker filter accepts.
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


def _local_image_paths(mime_data: QMimeData) -> list[str]:
    if not mime_data.hasUrls():
        return []
    return [
        url.toLocalFile() for url in mime_data.urls()
        if url.isLocalFile() and os.path.splitext(url.toLocalFile())[1].lower() in _IMAGE_EXTENSIONS
    ]


class _CarouselCard(QFrame):
    clicked = Signal(int)
    ctrl_clicked = Signal(int)
    context_menu_requested = Signal(int, object, bool)  # index, global pos, cmd held

    def __init__(self, index: int, base: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.index = index
        self._is_current = False
        self._is_selected = False
        self._drag_start_pos = None
        self._base = base
        self._pixmap: QPixmap | None = None
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 2)
        layout.setSpacing(2)

        self.thumb_label = QLabel()
        self.thumb_label.setStyleSheet("background:#222; border:1px solid #444;")
        self.thumb_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.thumb_label)

        self.name_label = QLabel()
        self.name_label.setStyleSheet("color:#aaa; font-size:10px;")
        self.name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.name_label)

        self.set_cell_size(THUMB_W)
        self._update_style()

    def set_cell_size(self, thumb_w: int) -> None:
        """Resizes the card to a given thumbnail width - THUMB_W (the
        filmstrip's own fixed size) in strip mode, or whatever the grid's
        current per-cell size is in grid mode (see CarouselWidget._reflow_grid)."""
        thumb_h = max(1, round(thumb_w * THUMB_H / THUMB_W))
        self.setFixedSize(thumb_w + 14, thumb_h + 30)
        self.thumb_label.setFixedSize(thumb_w, thumb_h)
        self._rescale_thumbnail()
        fm = self.name_label.fontMetrics()
        self.name_label.setText(fm.elidedText(self._base, Qt.ElideMiddle, thumb_w + 6))

    def _update_style(self) -> None:
        if self._is_current:
            color, width = CURRENT_COLOR, 3
        elif self._is_selected:
            color, width = SELECTED_COLOR, 2
        else:
            color, width = DEFAULT_COLOR, 1
        self.setStyleSheet(f"_CarouselCard {{ border: {width}px solid {color}; border-radius: 6px; }}")

    def set_current(self, current: bool) -> None:
        self._is_current = current
        self._update_style()

    def set_selected(self, selected: bool) -> None:
        self._is_selected = selected
        self._update_style()

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self._rescale_thumbnail()

    def _rescale_thumbnail(self) -> None:
        if self._pixmap is None:
            return
        scaled = self._pixmap.scaled(
            self.thumb_label.width(), self.thumb_label.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.thumb_label.setPixmap(scaled)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            if event.modifiers() & Qt.ControlModifier:
                self.ctrl_clicked.emit(self.index)
            else:
                self.clicked.emit(self.index)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (event.buttons() & Qt.LeftButton) and self._drag_start_pos is not None:
            moved = event.pos() - self._drag_start_pos
            if moved.manhattanLength() >= QApplication.startDragDistance():
                self._start_drag()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _start_drag(self) -> None:
        self._drag_start_pos = None
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_REORDER_MIME, str(self.index).encode())
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(self.rect().center())
        drag.exec(Qt.MoveAction)

    def contextMenuEvent(self, event) -> None:
        cmd_held = bool(event.modifiers() & Qt.ControlModifier)
        self.context_menu_requested.emit(self.index, event.globalPos(), cmd_held)


class _CarouselStrip(QWidget):
    """The cards' container - the row in strip mode, or the grid_strip in
    grid mode (see CarouselWidget). Also the drop target for reordering,
    spanning the trailing empty space too so dropping past the last card
    appends it - and, separately, for image files dragged in from Finder
    (see files_dropped)."""
    card_dropped = Signal(int, QPointF)  # from_index, drop position (local coords)
    files_dropped = Signal(list)  # local file paths

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(_REORDER_MIME) or _local_image_paths(event.mimeData()):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(_REORDER_MIME) or _local_image_paths(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if event.mimeData().hasFormat(_REORDER_MIME):
            from_index = int(bytes(event.mimeData().data(_REORDER_MIME)).decode())
            pos = event.position() if hasattr(event, "position") else event.pos()
            self.card_dropped.emit(from_index, QPointF(pos))
            event.acceptProposedAction()
            return
        paths = _local_image_paths(event.mimeData())
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()


class CarouselWidget(QWidget):
    current_changed = Signal(int)
    selection_changed = Signal()
    copy_requested = Signal(int)
    paste_requested = Signal(list)
    paste_crop_requested = Signal(list)
    delete_requested = Signal(list)
    reset_requested = Signal(list)
    duplicate_requested = Signal(int)
    reordered = Signal(list)  # order[new_position] = old_index
    files_dropped = Signal(list)  # local file paths dragged in from Finder

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._cards: list[_CarouselCard] = []
        self._current_index = -1
        self._selected: set[int] = set()
        self._selection_anchor = -1
        # Only true once something's been copied that carries crop settings -
        # gates whether "Paste Crop" shows in the context menu at all.
        self._paste_crop_available = False
        self._grid_mode = False
        self._grid_columns = 0  # 0 = not yet initialized; picked on first grid layout
        self._grid_cell_size = THUMB_W

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color:#777; font-style: italic;")
        outer.addWidget(self.empty_label)

        # Strip mode - the filmstrip, a single horizontally-scrolling row.
        self.scroll = ArrowKeyScrollArea()
        self.scroll.setFixedHeight(THUMB_H + 50)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.strip = _CarouselStrip()
        self.strip.card_dropped.connect(self._on_card_dropped)
        self.strip.files_dropped.connect(self.files_dropped.emit)
        self.strip_layout = QHBoxLayout(self.strip)
        self.strip_layout.setContentsMargins(6, 4, 6, 4)
        self.strip_layout.setSpacing(6)
        self.strip_layout.addStretch(1)
        self.scroll.setWidget(self.strip)
        outer.addWidget(self.scroll)

        # Grid mode - the same cards, wrapped into a responsive multi-column
        # grid instead of one scrolling row, centered in the available width
        # so the margins either side stay equal regardless of how wide the
        # container is (see set_grid_mode(), toggled by MainWindow as this
        # widget's own "fullscreen" mode).
        self.grid_scroll = ArrowKeyScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.grid_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.grid_scroll.setFrameShape(QFrame.NoFrame)
        self.grid_strip = _CarouselStrip()
        self.grid_strip.card_dropped.connect(self._on_card_dropped)
        self.grid_strip.files_dropped.connect(self.files_dropped.emit)
        self.grid_layout = QGridLayout(self.grid_strip)
        self.grid_layout.setContentsMargins(_GRID_MARGIN, _GRID_MARGIN, _GRID_MARGIN, _GRID_MARGIN)
        self.grid_layout.setSpacing(_GRID_SPACING)
        self.grid_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.grid_scroll.setWidget(self.grid_strip)
        self.grid_scroll.setVisible(False)
        outer.addWidget(self.grid_scroll)

        self.retranslate_ui()
        self._update_empty_state()

    def retranslate_ui(self) -> None:
        self.empty_label.setText(i18n.tr("carousel_empty_hint"))

    def _update_empty_state(self) -> None:
        has_items = bool(self._cards)
        self.empty_label.setVisible(not has_items)
        self.scroll.setVisible(has_items and not self._grid_mode)
        self.grid_scroll.setVisible(has_items and self._grid_mode)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._grid_mode:
            self._reflow_grid()

    # ------------------------------------------------------------------
    # Grid mode (fullscreen)
    # ------------------------------------------------------------------
    def set_grid_mode(self, enabled: bool) -> None:
        if enabled == self._grid_mode:
            return
        self._grid_mode = enabled
        if enabled:
            for card in self._cards:
                self.strip_layout.removeWidget(card)
            # Force a resize pass even if the recomputed size happens to
            # match the last-known grid cell size, since the cards were
            # just reset to the strip's fixed THUMB_W by the disable
            # branch below the last time grid mode was left.
            self._grid_cell_size = 0
            self._reflow_grid(force=True)
        else:
            for card in self._cards:
                self.grid_layout.removeWidget(card)
                card.set_cell_size(THUMB_W)
            for i, card in enumerate(self._cards):
                self.strip_layout.insertWidget(i, card)
        self._update_empty_state()
        self._ensure_current_visible()

    def zoom_in(self) -> None:
        self._set_grid_columns(self._grid_columns - 1)

    def zoom_out(self) -> None:
        self._set_grid_columns(self._grid_columns + 1)

    def _set_grid_columns(self, columns: int) -> None:
        columns = max(MIN_GRID_COLUMNS, min(MAX_GRID_COLUMNS, columns))
        if columns == self._grid_columns:
            return
        self._grid_columns = columns
        self._reflow_grid(force=True)

    def _initial_grid_columns(self) -> int:
        available = self.grid_scroll.viewport().width() - 2 * _GRID_MARGIN
        if available <= 0:
            return max(MIN_GRID_COLUMNS, min(MAX_GRID_COLUMNS, 6))
        step = _INITIAL_GRID_CELL_TARGET + _GRID_CELL_CHROME + _GRID_SPACING
        columns = (available + _GRID_SPACING) // step
        return max(MIN_GRID_COLUMNS, min(MAX_GRID_COLUMNS, int(columns)))

    def _reflow_grid(self, force: bool = False) -> None:
        if not self._grid_mode or not self._cards:
            return
        columns_changed = force
        if self._grid_columns <= 0:
            self._grid_columns = self._initial_grid_columns()
            columns_changed = True
        available = self.grid_scroll.viewport().width() - 2 * _GRID_MARGIN
        total_spacing = _GRID_SPACING * (self._grid_columns - 1)
        cell_size = max(
            MIN_GRID_CELL_SIZE,
            (max(self._grid_columns, available) - total_spacing) // self._grid_columns - _GRID_CELL_CHROME,
        )
        if cell_size != self._grid_cell_size:
            self._grid_cell_size = cell_size
            for card in self._cards:
                card.set_cell_size(self._grid_cell_size)
        if columns_changed:
            while self.grid_layout.count():
                self.grid_layout.takeAt(0)
            for i, card in enumerate(self._cards):
                row, col = divmod(i, self._grid_columns)
                self.grid_layout.addWidget(card, row, col)

    def _insert_index_for_point(self, pos: QPointF) -> int:
        if not self._cards or self._grid_columns <= 0:
            return len(self._cards)
        card0 = self._cards[0]
        cell_w = card0.width() + _GRID_SPACING
        cell_h = card0.height() + _GRID_SPACING
        if cell_w <= 0 or cell_h <= 0:
            return len(self._cards)
        col = int((pos.x() - _GRID_MARGIN) // cell_w)
        row = int((pos.y() - _GRID_MARGIN) // cell_h)
        col = max(0, min(col, self._grid_columns - 1))
        row = max(0, row)
        index = row * self._grid_columns + col
        return max(0, min(index, len(self._cards)))

    def _ensure_current_visible(self) -> None:
        if not (0 <= self._current_index < len(self._cards)):
            return
        scroll = self.grid_scroll if self._grid_mode else self.scroll
        scroll.ensureWidgetVisible(self._cards[self._current_index])

    # ------------------------------------------------------------------
    # Items / selection / activation
    # ------------------------------------------------------------------
    def set_items(self, bases: list[str]) -> None:
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = []
        self._selected = set()

        for i, base in enumerate(bases):
            card = _CarouselCard(i, base)
            card.clicked.connect(self._on_card_clicked)
            card.ctrl_clicked.connect(self._on_card_ctrl_clicked)
            card.context_menu_requested.connect(self._on_card_context_menu)
            self._cards.append(card)

        if self._grid_mode:
            for card in self._cards:
                card.set_cell_size(self._grid_cell_size or THUMB_W)
            self._reflow_grid(force=True)
        else:
            for card in self._cards:
                self.strip_layout.insertWidget(self.strip_layout.count() - 1, card)

        self._current_index = -1
        self._selection_anchor = -1
        self._update_empty_state()

    def _on_card_clicked(self, index: int) -> None:
        self.set_current(index)
        self.select_only(index)
        self._selection_anchor = index
        self.current_changed.emit(index)

    def _on_card_ctrl_clicked(self, index: int) -> None:
        if index in self._selected:
            self._selected.discard(index)
        else:
            self._selected.add(index)
        self._cards[index].set_selected(index in self._selected)
        self.selection_changed.emit()

    def _on_card_context_menu(self, index: int, global_pos, cmd_held: bool) -> None:
        # Right-clicking moves the "current" (yellow) highlight to the
        # clicked card first, same as a left click - so the menu always
        # opens on what's now visibly current.
        if self._current_index != index:
            self.set_current(index)
            self.current_changed.emit(index)
        # Right-clicking a lone selected (or unselected) photo replaces the
        # selection, same as a plain click would, so the menu acts on only
        # this card. But right-clicking *into* an existing multi-selection
        # (2+ photos) keeps it intact - that's what lets "Reset All" etc.
        # act on a whole group - the same as holding Cmd would.
        keep_selection = cmd_held or (len(self._selected) > 1 and index in self._selected)
        if not keep_selection:
            self.select_only(index)
        targets = sorted(self._selected) if index in self._selected else [index]
        menu = QMenu(self)
        copy_action = menu.addAction(i18n.tr("menu_edit_copy"))
        paste_action = menu.addAction(i18n.tr("menu_edit_paste"))
        # Only appears once something carrying crop settings has been
        # copied - the regular Paste above never restores crop.
        paste_crop_action = menu.addAction(i18n.tr("menu_paste_crop")) if self._paste_crop_available else None
        menu.addSeparator()
        reset_action = menu.addAction(i18n.tr("menu_reset_all"))
        duplicate_action = menu.addAction(i18n.tr("menu_duplicate"))
        menu.addSeparator()
        delete_action = menu.addAction(i18n.tr("menu_edit_delete"))
        chosen = menu.exec(global_pos)
        if chosen is copy_action:
            self.copy_requested.emit(index)
        elif chosen is paste_action:
            self.paste_requested.emit(targets)
        elif paste_crop_action is not None and chosen is paste_crop_action:
            self.paste_crop_requested.emit(targets)
        elif chosen is reset_action:
            self.reset_requested.emit(targets)
        elif chosen is duplicate_action:
            # Duplicate always acts on the single active photo, never the
            # whole multi-selection - unlike Copy/Paste/Reset/Delete above.
            self.duplicate_requested.emit(index)
        elif chosen is delete_action:
            self.delete_requested.emit(targets)

    def _insert_index_for_x(self, x: float) -> int:
        for i, card in enumerate(self._cards):
            if x < card.x() + card.width() / 2.0:
                return i
        return len(self._cards)

    def _on_card_dropped(self, from_index: int, pos: QPointF) -> None:
        if not (0 <= from_index < len(self._cards)):
            return
        insert_before = self._insert_index_for_point(pos) if self._grid_mode else self._insert_index_for_x(pos.x())
        target = insert_before - 1 if insert_before > from_index else insert_before
        target = max(0, min(target, len(self._cards) - 1))
        if target == from_index:
            return
        self._reorder(from_index, target)

    def _reorder(self, from_index: int, target: int) -> None:
        order = list(range(len(self._cards)))
        order.insert(target, order.pop(from_index))

        current_card = self._cards[self._current_index] if 0 <= self._current_index < len(self._cards) else None
        selected_cards = {self._cards[i] for i in self._selected}

        card = self._cards.pop(from_index)
        self._cards.insert(target, card)
        if self._grid_mode:
            self._reflow_grid(force=True)
        else:
            self.strip_layout.removeWidget(card)
            self.strip_layout.insertWidget(target, card)
        for i, c in enumerate(self._cards):
            c.index = i

        self._current_index = self._cards.index(current_card) if current_card is not None else -1
        self._selected = {i for i, c in enumerate(self._cards) if c in selected_cards}

        self.reordered.emit(order)

    def set_current(self, index: int) -> None:
        if self._current_index == index:
            return
        if 0 <= self._current_index < len(self._cards):
            self._cards[self._current_index].set_current(False)
        self._current_index = index
        if 0 <= index < len(self._cards):
            self._cards[index].set_current(True)
            self._ensure_current_visible()

    def set_selected(self, index: int, selected: bool) -> None:
        """Directly set one card's selection state without emitting
        selection_changed - for syncing the carousel from already-known data
        (e.g. after rebuilding cards from a fresh item list)."""
        if not (0 <= index < len(self._cards)):
            return
        if selected:
            self._selected.add(index)
        else:
            self._selected.discard(index)
        self._cards[index].set_selected(selected)

    def select_only(self, index: int) -> None:
        self._selected = {index} if 0 <= index < len(self._cards) else set()
        for i, card in enumerate(self._cards):
            card.set_selected(i in self._selected)
        self.selection_changed.emit()

    def toggle_select_all(self) -> None:
        if not self._cards:
            return
        if len(self._selected) == len(self._cards):
            self._selected = set()
        else:
            self._selected = set(range(len(self._cards)))
        for i, card in enumerate(self._cards):
            card.set_selected(i in self._selected)
        self.selection_changed.emit()

    def set_thumbnail(self, index: int, pixmap: QPixmap) -> None:
        if 0 <= index < len(self._cards):
            self._cards[index].set_thumbnail(pixmap)

    def set_paste_crop_available(self, available: bool) -> None:
        self._paste_crop_available = available

    def selected_indices(self) -> list[int]:
        return sorted(self._selected)

    def count(self) -> int:
        return len(self._cards)

    def current_index(self) -> int:
        return self._current_index

    def go_next(self, extend_selection: bool = False) -> None:
        if not self._cards:
            return
        nxt = min(self._current_index + 1, len(self._cards) - 1) if self._current_index >= 0 else 0
        if extend_selection:
            self._extend_selection_to(nxt)
        else:
            self._on_card_clicked(nxt)

    def go_prev(self, extend_selection: bool = False) -> None:
        if not self._cards:
            return
        prv = max(self._current_index - 1, 0) if self._current_index >= 0 else 0
        if extend_selection:
            self._extend_selection_to(prv)
        else:
            self._on_card_clicked(prv)

    def _extend_selection_to(self, index: int) -> None:
        """Finder-style Shift+arrow range selection: grows/shrinks the
        selection between the anchor (set by the last plain click/move) and
        ``index``, and moves "current" along with it."""
        if not (0 <= index < len(self._cards)):
            return
        if self._selection_anchor < 0:
            self._selection_anchor = self._current_index if self._current_index >= 0 else index
        lo, hi = sorted((self._selection_anchor, index))
        new_selected = set(range(lo, hi + 1))
        for i, card in enumerate(self._cards):
            sel = i in new_selected
            if sel != (i in self._selected):
                card.set_selected(sel)
        self._selected = new_selected
        self.set_current(index)
        self.selection_changed.emit()
        self.current_changed.emit(index)
