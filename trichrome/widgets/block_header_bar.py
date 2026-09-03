"""The side-panel "block" system: every tool block (Files, Trichrome,
Light, Color, Histogram, Crop, Scan) can be dragged to reorder within a
panel, dragged across to the *other* panel, collapsed (header only), or
closed (fully hidden, restorable from the Tools menu).

start_block_chrome()/finish_block_chrome() build the standard header (drag
handle, optional title, then whatever buttons the caller adds, then a
collapse toggle and a close button) and a body container - callers add
their real content to the returned body_layout instead of the block's own
top-level layout, so collapsing can hide just that.

Dragging starts only from a small dedicated BlockDragHandle icon (a grip
glyph), not from the whole header row - so the header's own title/buttons
never fight the drag gesture for mouse events. The drag pixmap is a scaled-
down (_GHOST_SCALE), outlined, semi-transparent grab of the whole block
widget, so the block visibly appears to move with the cursor rather than
just showing a generic drag icon - kept small on purpose so it doesn't
blanket the highlighted drop target underneath it while hovering.

Deliberately a single static QDrag.setPixmap() call, set once before
exec() and never touched again - a 2026-09-04 attempt at a live red/white
border swap (first via targetChanged + live setPixmap(), then via a
custom always-on-top overlay window polling the cursor) both got reverted:
the first was silently ignored (QDrag.setPixmap() isn't reliably honored
once a native drag session has started, notably on macOS), and the second
broke drag-and-drop entirely - a real top-level window kept positioned
exactly under the cursor turned out to intercept the OS's own native
drop-target hit-testing, which operates at the window-manager level and
isn't affected by Qt-side attributes like WA_TransparentForMouseEvents
(those only govern ordinary in-app mouse-event routing). Every drop
resolved to "nothing accepted it," i.e. deletion, regardless of where it
actually landed. Given two different techniques for this one cosmetic
detail both caused real problems and neither could be verified without a
real interactive session, this reverts to the simple version that's known
to work correctly, rather than attempting a third live-drag-visual trick.

BlockReorderZone is one side panel's drop target - both panels accept a
drop of any block (cross-panel moves are allowed), computing an insertion
index from the drop's Y position among the zone's own currently-visible
blocks (excluding the dragged one, which stays put/visible during the drag
itself). While hovering a valid drag, a thin dashed blue line is drawn at
the gap the block would land in - not a highlight over one whole block
(the first version did that, and it read as "this replaces that block"
rather than "it slots in above/below it").

A drop outside both BlockReorderZones (including an Escape-cancelled
drag) is simply a no-op - the block snaps back to where it was. A block
is only ever removed via its own close button or the Tools menu. An
earlier pass (2026-09-04) also removed a block on drop-outside; the user
asked to drop that behavior as redundant with the close button/Tools menu.
"""
from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import i18n
from .svg_icons import SvgToolButton

BLOCK_REORDER_MIME = "application/x-trichrome-block-key"

# The ghost pixmap is scaled down to this fraction of the real block's size -
# at full size it visually blankets whatever's underneath (including the
# highlighted drop target itself), which is what made the first version's
# drop preview hard to read.
_GHOST_SCALE = 0.42


def start_block_chrome(block: QWidget, block_key: str, title_i18n_key: str | None):
    """Sets up block's own top-level QVBoxLayout (tight top+bottom margins)
    and starts its header row with the drag handle, then an optional title.
    Returns (outer_layout, header_row, title_label_or_None) - the caller
    adds anything that belongs right next to the title next (e.g. a "?"
    scope-info button), **then its own `header_row.addStretch(1)`**, then
    any trailing buttons that should sit at the row's right edge (Reset,
    Copy, etc.), then calls finish_block_chrome() to close it out. The
    stretch is deliberately the caller's own responsibility, not added
    here - an earlier version added it unconditionally right after the
    title, which silently pushed every "?" button some panels added
    afterward all the way to the right edge instead of next to the title
    (2026-09-04 bug, caught by the user: "colle les indicateurs '?' à la
    droite des titres")."""
    outer = QVBoxLayout(block)
    left, _top, right, _bottom = outer.getContentsMargins()
    # Both margins tight, not just top - when a block is collapsed (body
    # hidden), the bottom margin sits directly under the header row, so
    # leaving it at the style default made a collapsed block look
    # asymmetric (tight top, loose bottom) even after the first pass
    # (2026-09-04 feedback: "même espace entre le haut et le bas du texte").
    outer.setContentsMargins(left, 4, right, 4)

    header_row = QHBoxLayout()
    header_row.addWidget(BlockDragHandle(block_key, block))
    title_label = None
    if title_i18n_key:
        title_label = QLabel()
        title_label.setStyleSheet("font-weight: bold;")
        header_row.addWidget(title_label)
    return outer, header_row, title_label


# Smaller and more discreet than the panel's own action buttons
# (Reset/Copy/etc. use HEADER_COMPANION_BTN_SIZE) - these two are
# secondary, always-present chrome on every block, not a primary action -
# and this size also happens to be what keeps the most-crowded header
# (Trichromie: grip+title+2 reset buttons+these 2) under the left panel's
# own minimum width (2026-09-04 fix, see the horizontal-scrollbar note in
# main_window.py).
_UTILITY_BTN_SIZE = (22, 22)
_COLLAPSE_ICON_SIZE = 13
# Lucide's "x" glyph spans ~50% of its viewBox height (corner to corner)
# vs. chevron-down's ~25% (a shallow centered dip) - at equal icon_size the
# X reads as visibly taller/heavier. Sized down so the two look like a
# matched pair rather than the X dominating (2026-09-04 feedback: "la
# croix doit visuellement être de la même hauteur que le bouton collapse").
_CLOSE_ICON_SIZE = 9


def finish_block_chrome(outer: QVBoxLayout, header_row: QHBoxLayout):
    """Appends the collapse toggle + close button at the end of header_row
    (after any custom buttons the caller already added), adds header_row to
    outer, then builds a body QWidget/QVBoxLayout for the block's real
    content. Returns (body, body_layout, collapse_button, close_button) -
    the caller keeps `body` (needed by set_block_collapsed) and adds its
    real content to `body_layout`; MainWindow wires collapse_button/
    close_button's clicks, since it owns the cross-block visible/collapsed
    state."""
    collapse_button = SvgToolButton(
        "General/chevron-down.svg", size=_UTILITY_BTN_SIZE, icon_size=_COLLAPSE_ICON_SIZE)
    collapse_button.setToolTip(i18n.tr("block_collapse_tooltip"))
    header_row.addWidget(collapse_button)
    close_button = SvgToolButton(
        "General/close.svg", size=_UTILITY_BTN_SIZE, icon_size=_CLOSE_ICON_SIZE)
    close_button.setToolTip(i18n.tr("block_close_tooltip"))
    header_row.addWidget(close_button)
    outer.addLayout(header_row)

    body = QWidget()
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(body)
    return body, body_layout, collapse_button, close_button


def set_block_collapsed(body: QWidget, collapse_button: SvgToolButton, collapsed: bool) -> None:
    """Hides/shows a block's body, and rotates its collapse chevron to
    point right (collapsed) instead of down (expanded) - a real 2-state
    indicator, not just an action icon with a fixed meaning. -90°, not
    +90°: with Qt's screen-space (y-down) rotation, +90 on a down-pointing
    chevron actually swings it to point left, not right - verified by
    tracing the rotated path's coordinates by hand after the first version
    (2026-09-04) rotated the wrong way. Matches the native QToolButton
    RightArrow/DownArrow convention CollapsibleSection already used
    elsewhere in the app (controls.py)."""
    body.setVisible(not collapsed)
    collapse_button.set_rotation(-90.0 if collapsed else 0.0)


class BlockDragHandle(SvgToolButton):
    """A small grip icon that starts a block-reorder drag when moved past
    the OS drag threshold. drag_source is the whole block widget - grabbed
    for the drag pixmap so the block appears to move with the cursor,
    rather than dragging the tiny icon alone.

    A drop outside both BlockReorderZones (or an Escape-cancelled drag) is
    simply a no-op - the block stays exactly where it was. Removing a
    block is only ever done via its own close button or the Tools menu
    (2026-09-04: an earlier pass also removed a block on drop-outside, but
    the user asked to drop that - "cette option de supprimer l'outil en
    drag and drop n'est pas necessaire", already covered by the close
    button/Tools menu)."""

    def __init__(self, block_key: str, drag_source: QWidget,
                 size: tuple[int, int] = (16, 16), icon_size: int = 12, parent: QWidget | None = None):
        super().__init__("General/grip-vertical.svg", size=size, icon_size=icon_size, parent=parent)
        self.block_key = block_key
        self.drag_source = drag_source
        self.setCursor(Qt.OpenHandCursor)
        self._drag_start_pos: QPoint | None = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start_pos is not None and event.buttons() & Qt.LeftButton:
            moved = event.pos() - self._drag_start_pos
            if moved.manhattanLength() >= QApplication.startDragDistance():
                # Hotspot in the *scaled* ghost's own coordinates, computed
                # from where the grip sits within the full-size block, so
                # the ghost tracks the cursor at the same relative point it
                # was grabbed from instead of jumping to its top-left.
                full_hotspot = self.mapTo(self.drag_source, event.pos())
                hotspot = QPoint(round(full_hotspot.x() * _GHOST_SCALE), round(full_hotspot.y() * _GHOST_SCALE))
                self._drag_start_pos = None
                self._start_drag(hotspot)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _start_drag(self, hotspot: QPoint) -> None:
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(BLOCK_REORDER_MIME, self.block_key.encode("utf-8"))
        drag.setMimeData(mime)
        drag.setPixmap(self._ghost_pixmap())
        drag.setHotSpot(hotspot)
        drag.exec(Qt.MoveAction)
        # QDrag's own internal event loop consumes the mouse release that
        # ends the drag, so this button never gets a normal
        # mouseReleaseEvent for it - without this, QAbstractButton's
        # internal "down" state can stay stuck true after a drag.
        self.setDown(False)

    def _ghost_pixmap(self) -> QPixmap:
        """A scaled-down, semi-transparent, outlined preview of the whole
        block being moved - full-size would blanket whatever's underneath,
        including the drop-target highlight itself."""
        source = self.drag_source.grab()
        scaled = source.scaled(
            max(1, round(source.width() * _GHOST_SCALE)), max(1, round(source.height() * _GHOST_SCALE)),
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        ghost = QPixmap(scaled.size())
        ghost.setDevicePixelRatio(scaled.devicePixelRatio())
        ghost.fill(Qt.transparent)
        painter = QPainter(ghost)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setOpacity(0.9)
        painter.drawPixmap(0, 0, scaled)
        painter.setOpacity(1.0)
        painter.setPen(QPen(Qt.white, 1.5))
        painter.setBrush(Qt.NoBrush)
        inset = 0.75
        painter.drawRect(
            inset, inset,
            scaled.width() / scaled.devicePixelRatio() - 2 * inset,
            scaled.height() / scaled.devicePixelRatio() - 2 * inset)
        painter.end()
        return ghost


_INDICATOR_INSET = 6.0  # left/right margin the insertion line is drawn with
_INDICATOR_GAP = 4.0  # how far above/below the first/last block it sits


class BlockReorderZone(QWidget):
    """One side panel's drop target. Call set_block_widgets() once with a
    {block_key: widget} mapping of every block that *can* live here (shown
    or not - only currently-visible ones count for drop-position math).
    Emits block_dropped(dragged_block_key, insert_index) on a valid drop -
    insert_index is a position among this zone's own visible blocks
    (excluding the dragged one), 0..len(visible). Accepts drops for a block
    not currently in its own mapping too, since a block can be dragged in
    from the *other* panel - MainWindow's drop handler is what actually
    moves a block between sides.

    While hovering a valid drag, draws a thin dashed insertion line at the
    gap the block would land in - not a highlight over one whole block,
    which used to read as "this replaces that block" rather than "it slots
    in above/below it" (2026-09-04 feedback)."""

    block_dropped = Signal(str, int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._block_widgets: dict[str, QWidget] = {}
        self._indicator_y: float | None = None

    def set_block_widgets(self, mapping: dict[str, QWidget]) -> None:
        self._block_widgets = mapping

    def _visible_widgets(self, exclude_key: str | None) -> list[QWidget]:
        exclude = self._block_widgets.get(exclude_key) if exclude_key else None
        layout = self.layout()
        out = []
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w is not None and w is not exclude and w.isVisible():
                out.append(w)
        return out

    def _insert_position(self, y: float, exclude_key: str | None) -> tuple[int, float]:
        """Returns (insert_index, indicator_y) - the index among visible
        blocks (excluding the dragged one) the drop would land at, and the
        on-screen Y (this widget's own coordinates) of the gap it'd land
        in, so the drop logic and the drawn indicator always agree."""
        visible = self._visible_widgets(exclude_key)
        if not visible:
            return 0, _INDICATOR_GAP
        for i, w in enumerate(visible):
            mid = w.y() + w.height() / 2
            if y < mid:
                gap_y = (w.y() - _INDICATOR_GAP) if i == 0 else (
                    (visible[i - 1].y() + visible[i - 1].height() + w.y()) / 2)
                return i, gap_y
        last = visible[-1]
        return len(visible), last.y() + last.height() + _INDICATOR_GAP

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(BLOCK_REORDER_MIME):
            event.acceptProposedAction()
            self._update_drag_indicator(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(BLOCK_REORDER_MIME):
            event.acceptProposedAction()
            self._update_drag_indicator(event)

    def _update_drag_indicator(self, event) -> None:
        key = bytes(event.mimeData().data(BLOCK_REORDER_MIME)).decode("utf-8")
        _index, indicator_y = self._insert_position(event.position().y(), exclude_key=key)
        if self._indicator_y != indicator_y:
            self._indicator_y = indicator_y
            self.update()

    def dragLeaveEvent(self, event) -> None:
        self._clear_indicator()

    def dropEvent(self, event) -> None:
        mime = event.mimeData()
        if not mime.hasFormat(BLOCK_REORDER_MIME):
            return
        key = bytes(mime.data(BLOCK_REORDER_MIME)).decode("utf-8")
        index, _indicator_y = self._insert_position(event.position().y(), exclude_key=key)
        event.acceptProposedAction()
        self._clear_indicator()
        self.block_dropped.emit(key, index)

    def _clear_indicator(self) -> None:
        if self._indicator_y is not None:
            self._indicator_y = None
            self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._indicator_y is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor("#5b9bd5"), 2.5, Qt.DashLine)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        y = self._indicator_y
        painter.drawLine(QPointF(_INDICATOR_INSET, y), QPointF(self.width() - _INDICATOR_INSET, y))
        painter.setPen(QPen(Qt.NoPen))
        painter.setBrush(QColor("#5b9bd5"))
        for x in (_INDICATOR_INSET, self.width() - _INDICATOR_INSET):
            painter.drawEllipse(QPointF(x, y), 3.0, 3.0)
        painter.end()
