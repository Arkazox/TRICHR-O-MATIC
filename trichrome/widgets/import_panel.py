"""Top-of-sidebar panel: a single Mode selector (Solo / Classic Trichrome /
Color Trichrome), then either load the 3 channel images (either Trichrome
variant) or a single photo (Solo). Auto Align and Lock Layer Position moved to
the top of the "Trichrome Process" block (main_window.py's
independent_channels_group).

Negative (invert) briefly lived here before moving back to LightPanel's header:
Negative reads as a Light-adjacent tonal concept to a user, even though it's
technically per-photo source state - see global_panel.py for where it lives
now.

Mode selector, unified from what used to be two separate controls: a plain
Normal/Trichrome toggle here, plus an independent "Harris Shutter Effect"
checkbox down in the Trichrome Process block. Both described the same
underlying thing - how this photo's files should be interpreted - so they're
now one 3-way choice, styled like the Crop tool's own aspect-ratio selector
(label + combo + a "?" info button - the combo's own per-item icon folded the
separate icon label the first pass had into the combo itself later the same
day, once Qt's own item-icon support made that redundant):
**Solo** (BatchItem.mode == "normal" - a single already-composed photo),
**Classic Trichrome** (mode == "trichrome", ChannelLayer.harris_shutter ==
False - the classic case, 3 B&W photos through color filters), **Color
Trichrome** (mode == "trichrome", harris_shutter == True - 3 real color photos,
each keeping its own R/G/B channel; see ChannelLayer.harris_shutter for how
each channel is decoded)."""
from __future__ import annotations

import os

from PySide6.QtCore import QMimeData, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QGroupBox, QHBoxLayout, QLabel, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from .. import i18n, imaging, theme
from .block_header_bar import finish_block_chrome, start_block_chrome
from .channel_panel import CHANNEL_COLORS, CHANNEL_KEY
from .controls import ElidingLabel
from .info_bubble import InfoButton
from .svg_icons import (
    HEADER_COMPANION_BTN_SIZE, HEADER_COMPANION_ICON_SIZE, SvgToolButton, raw_svg_icon,
    recolored_svg_file,
)


# Drag-and-drop channel swap: dragging a channel's own grip handle onto another
# channel's file block swaps which photo - and its own alignment/tone edits,
# see MainWindow._swap_channel_layers - is loaded into each of the two channels
# (e.g. swap the Red and Blue channel images). Mime payload is just the source
# channel index (0/1/2), utf-8 encoded - same shape as
# block_header_bar.BLOCK_REORDER_MIME's own single-value mime, a completely
# separate mechanism/mime type from that block-reorder drag.
_CHANNEL_SWAP_MIME = "application/x-trichrome-channel-index"


def _swap_source_index(mime: QMimeData) -> int | None:
    if not mime.hasFormat(_CHANNEL_SWAP_MIME):
        return None
    try:
        return int(bytes(mime.data(_CHANNEL_SWAP_MIME)).decode("utf-8"))
    except ValueError:
        return None


def _dropped_image_path(mime: QMimeData) -> str | None:
    """The single importable image file in a Finder drop, or None."""
    if not mime.hasUrls():
        return None
    paths = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
    if len(paths) != 1 or os.path.splitext(paths[0])[1].lower() not in imaging.IMPORTABLE_EXTENSIONS:
        return None
    return paths[0]


def _translucent_grab(widget: QWidget, opacity: float = 0.55) -> QPixmap:
    """A plain screen-grab of ``widget``, redrawn into a fresh pixmap at
    reduced opacity - used as the channel-swap drag pixmap so the dragged
    visual is exactly the filename+handle block being moved (Finder-style: you
    see what you're picking up), rather than a synthesized stand-in. No border
    - a target channel's own blue drop-highlight sits directly under this while
    hovering, and needs to stay visible through it rather than being fully
    covered."""
    source = widget.grab()
    result = QPixmap(source.size())
    result.setDevicePixelRatio(source.devicePixelRatio())
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setOpacity(opacity)
    painter.drawPixmap(0, 0, source)
    painter.end()
    return result


# A channel's _ChannelFileBlock frame, painted by the block itself (a QSS
# border with a radius and a translucent color draws its sides and corners as
# overlapping pieces, which looked dotted on a Retina screen). Dashed while the
# channel is empty, solid once a photo is loaded. During a channel-swap drag,
# "source" (stronger dashed) marks the block being picked up and "target"
# (accent blue, light fill) the block under the cursor. Same width in every
# state, so a highlight never changes the block's size.
_FILE_BLOCK_RADIUS = 5.0
# Shared by the Mode combo and the channel rows, so the two line up.
_ROW_HEIGHT = 30
_ROW_SPACING = 6


class _ChannelDot(QWidget):
    """The channel's color as a plain filled circle, left of its file block."""

    _DIAMETER = 10
    WIDTH = _DIAMETER + 4

    def __init__(self, color: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(self.WIDTH, self.WIDTH)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(2, 2, self._DIAMETER, self._DIAMETER)


class _ChannelSwapHandle(SvgToolButton):
    """Small drag grip, part of a channel's _ChannelFileBlock - starts the
    channel-swap drag. Reuses the same grip-vertical glyph as a block's own
    drag handle (block_header_bar.BlockDragHandle) so the two "drag this to
    reorder/reassign" affordances read as the same visual language, even
    though this one drags a channel index, not a block key, and drops onto
    another channel's file block rather than a BlockReorderZone.

    Not a drop target itself - see _ChannelFileBlock, which owns the whole
    block's drag-over/drop handling so the filename and this handle always
    highlight and drag together as one unit."""

    # A grip, not a button: no hover frame.
    _HOVER_FRAME = False

    def __init__(self, channel_index: int, block: "_ChannelFileBlock", panel: "ImportPanel",
                 parent: QWidget | None = None):
        super().__init__("Global/grip-vertical.svg", size=(16, 16), icon_size=12, parent=parent)
        self.channel_index = channel_index
        self._block = block
        self._panel = panel
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip(i18n.tr("channel_swap_handle_tooltip"))
        self._drag_start_pos: QPoint | None = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start_pos is not None and (event.buttons() & Qt.LeftButton):
            delta = event.position().toPoint() - self._drag_start_pos
            if delta.manhattanLength() >= QApplication.startDragDistance():
                # Hotspot in the block's own coordinates, computed from
                # where the grip sits within it, so the dragged block
                # tracks the cursor at the same relative point it was
                # grabbed from instead of jumping to its top-left (same
                # convention as BlockDragHandle._start_drag).
                hotspot = self.mapTo(self._block, event.position().toPoint())
                self._drag_start_pos = None
                # Grabbed before the "source" highlight is applied, so the
                # dragged visual shows the block's normal (not highlighted)
                # appearance - the highlight is left behind on the block's
                # original position instead, like a Finder drag.
                pixmap = _translucent_grab(self._block)
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData(_CHANNEL_SWAP_MIME, str(self.channel_index).encode("utf-8"))
                drag.setMimeData(mime)
                drag.setPixmap(pixmap)
                drag.setHotSpot(hotspot)
                self._panel._set_filename_drag_state(self.channel_index, "source")
                drag.exec(Qt.MoveAction)
                self._panel._clear_filename_drag_states()
                # QDrag.exec() consumes the mouse release - without this the
                # button is left visually stuck "down" (same gotcha as
                # BlockDragHandle._start_drag).
                self.setDown(False)
                return
        super().mouseMoveEvent(event)


class _ChannelFileBlock(QWidget):
    """A channel's filename label and its swap handle, grouped into a
    single visual/interactive block: the whole block (not just the label)
    highlights on drag-hover, and the whole block (not a synthesized text
    tag) is what's grabbed for the drag pixmap - see _ChannelSwapHandle and
    ImportPanel._set_filename_drag_state.

    Owns all drag-over/drop handling for the block (dropping on either the
    filename or the handle behaves identically, since only this container
    accepts drops - Qt bubbles an unaccepted drag event up to the nearest
    ancestor that does)."""

    def __init__(self, channel_index: int, panel: "ImportPanel", parent: QWidget | None = None):
        super().__init__(parent)
        self.channel_index = channel_index
        self._panel = panel
        self.setAcceptDrops(True)
        self.loaded = False
        self.drag_state = ""
        # Same height empty or loaded, and the same as the Mode combo above.
        self.setFixedHeight(_ROW_HEIGHT)
        layout = QHBoxLayout(self)
        # 1px frame + inner padding. Right, top and bottom match, so the ×'s
        # hover box sits with the same gap to all three edges of the frame.
        layout.setContentsMargins(3, 4, 4, 4)
        layout.setSpacing(4)
        self.swap_handle = _ChannelSwapHandle(channel_index, self, panel)
        layout.addWidget(self.swap_handle)
        self.filename_label = ElidingLabel()
        layout.addWidget(self.filename_label, stretch=1)
        self.size_label = QLabel()
        self.size_label.setStyleSheet(
            "color: #888; font-size: 11px; border: none; background: transparent; padding: 0;")
        layout.addWidget(self.size_label)
        self.clear_button = SvgToolButton("Global/close.svg", size=(22, 22), icon_size=12)
        self.clear_button.clicked.connect(
            lambda _checked=False: panel.clear_requested.emit(self.channel_index))
        layout.addWidget(self.clear_button, alignment=Qt.AlignVCenter)
        self.set_loaded(False)

    def set_loaded(self, loaded: bool) -> None:
        """Solid frame, full-strength name, resolution and × once a photo is
        loaded; dashed frame and the muted "choose or drop" prompt while the
        channel is empty (clicking it opens the file picker)."""
        self.loaded = loaded
        color = theme.text_color().name() if loaded else "#888"
        self.filename_label.setStyleSheet(
            f"color: {color}; font-size: 12px; border: none; background: transparent; padding: 0;")
        self.size_label.setVisible(loaded and bool(self.size_label.text()))
        self.clear_button.setVisible(loaded)
        self.setCursor(Qt.ArrowCursor if loaded else Qt.PointingHandCursor)
        self.update()

    def set_drag_state(self, state: str) -> None:
        self.drag_state = state
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.drag_state == "target":
            pen = QPen(QColor("#5b9bd5"), 1.0)
            painter.setBrush(QColor(91, 155, 213, 40))
        else:
            if self.drag_state == "source":
                pen = QPen(theme.overlay_color(110), 1.0, Qt.DashLine)
            else:
                pen = QPen(theme.overlay_color(45), 1.0, Qt.SolidLine if self.loaded else Qt.DashLine)
            painter.setBrush(Qt.NoBrush)
        if pen.style() == Qt.DashLine:
            pen.setDashPattern([3, 3])
        painter.setPen(pen)
        painter.drawRoundedRect(rect, _FILE_BLOCK_RADIUS, _FILE_BLOCK_RADIUS)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and not self.loaded and self.rect().contains(
                event.position().toPoint()):
            self._panel.load_requested.emit(self.channel_index)
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event) -> None:
        source_index = _swap_source_index(event.mimeData())
        if source_index is None and not self.loaded and _dropped_image_path(event.mimeData()):
            # A Finder file onto an empty channel loads it there.
            event.acceptProposedAction()
            self._panel._set_filename_drag_state(self.channel_index, "target")
        elif source_index is not None and source_index != self.channel_index:
            event.acceptProposedAction()
            self._panel._set_filename_drag_state(self.channel_index, "target")
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._panel._set_filename_drag_state(self.channel_index, "")

    def dropEvent(self, event) -> None:
        source_index = _swap_source_index(event.mimeData())
        self._panel._set_filename_drag_state(self.channel_index, "")
        file_path = _dropped_image_path(event.mimeData()) if source_index is None else None
        if file_path and not self.loaded:
            event.acceptProposedAction()
            self._panel.file_dropped.emit(self.channel_index, file_path)
            return
        if source_index is None or source_index == self.channel_index:
            event.ignore()
            return
        event.acceptProposedAction()
        self._panel.channel_swap_requested.emit(source_index, self.channel_index)


# Size the combo's own item icons are rendered at - matches the 18px default
# SvgIconLabel used before the Mode row folded its separate icon label into the
# combo itself, with the icons shown in the dropdown list.
_MODE_COMBO_ICON_SIZE = 18

# Flat/borderless-at-rest styling so the combo reads as part of the block's own
# surface rather than a separate native control sitting on top of it. Applying
# any stylesheet at all switches Qt from native platform chrome to its own
# QStyleSheetStyle rendering for this one widget - deliberately scoped to just
# this combo, not a blanket app-wide QComboBox rule, since no other combo in
# the app (crop_panel.py's aspect-ratio/grid pickers) needs this treatment. The
# dropdown arrow reuses the same Global/chevron-down.svg glyph every block's
# own collapse chevron already uses, recolored to the theme's foreground
# (QSS can't tint an ``image: url()``, so a recolored copy is written to the
# temp folder). selection-background-color reuses #5b9bd5, the one accent blue
# already established elsewhere in the app (the block drag-reorder insertion
# line).
def _mode_combo_style() -> str:
    """Built for the current theme: the box is a subtle overlay on the panel,
    the arrow and text follow the theme's foreground."""
    fg = theme.text_color()
    arrow = recolored_svg_file("Global/chevron-down.svg", fg)
    return f"""
QComboBox {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 3px 4px 3px 6px;
    color: {fg.name()};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: url({arrow});
    width: 12px;
    height: 12px;
}}
QComboBox QAbstractItemView {{
    background-color: {theme.pick("#2b2b2b", theme.LIGHT_POPUP)};
    color: {fg.name()};
    border: 1px solid {theme.overlay(40)};
    outline: none;
    selection-background-color: rgba(91, 155, 213, 90);
    selection-color: {fg.name()};
    padding: 4px;
}}
QComboBox QAbstractItemView::item {{
    padding: 3px 6px;
    border-radius: 4px;
}}
QComboBox QAbstractItemView::item:selected,
QComboBox QAbstractItemView::item:hover {{
    background: #5b9bd5;
    color: #ffffff;
}}
"""


# Order matches the combo's own item order. Icons are rendered "raw" (their
# own embedded colors, not the usual single-tint convention - see
# svg_icons.raw_svg_pixmap) since the whole point is 3 visually distinct
# glyphs. bw_trichrome/color_trichrome are General/layers-mode-{bw,color}.svg
# - the app's own filled "stack" glyph (resources/icons/General/stack.svg, a
# solid front diamond + 2 chevron slivers, as opposed to the plain- outline
# layers-outline.svg these 2 files used to derive from) with its 2 <path>
# elements split into 3 (the original has the top+bottom shapes sharing one
# path, same structure layers-outline.svg had) so each layer can carry its own
# explicit fill: Classic Trichrome grades from white at the front down to
# darker light-grays at the back (#ffffff/#e5e5e5/#cccccc - "white", "90%
# gray", "80% gray"); Color Trichrome colors each layer in its real R/G/B
# channel color (matching channel_panel.CHANNEL_COLORS exactly). solo is
# Global/stack-middle.svg - a new asset built to match
# stack-front.svg/stack-back.svg's own family (front/back's card fully outlined
# AND filled; a card occluded by the one in front of it is outline-only with
# just a filled chevron sliver peeking through) with the *middle* card filled
# instead - the old outline-based General/layers-mode-solo.svg is left on disk,
# unreferenced, same leave-it-there convention as every other superseded icon
# in this project.
MODE_KEYS = ("solo", "bw_trichrome", "color_trichrome")
MODE_ICONS = {
    "solo": "Global/stack-middle.svg",
    "bw_trichrome": "Global/layers-mode-bw.svg",
    "color_trichrome": "Global/layers-mode-color.svg",
}
MODE_LABEL_KEYS = {
    "solo": "mode_solo_option",
    "bw_trichrome": "mode_bw_trichrome_option",
    "color_trichrome": "mode_color_trichrome_option",
}


class _ModeComboBox(QComboBox):
    """The Mode combo, with its box painted here rather than by QSS (a
    translucent QSS border with a radius looks dotted on a Retina screen,
    same as _ChannelFileBlock's frame): a subtle fill and hairline, both a
    little stronger on hover."""

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        hovered = self.isEnabled() and self.underMouse()
        painter.setPen(QPen(theme.overlay_color(60 if hovered else 45), 1.0))
        painter.setBrush(theme.overlay_color(24 if hovered else 14))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                                _FILE_BLOCK_RADIUS, _FILE_BLOCK_RADIUS)
        painter.end()
        super().paintEvent(event)

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)


class ImportPanel(QGroupBox):
    load_requested = Signal(int)
    # A channel row's × button (clear that channel), and a Finder image file
    # dropped onto an empty channel row (index, path).
    clear_requested = Signal(int)
    file_dropped = Signal(int, str)
    # Emitted whenever the Mode selector's target implies a different
    # BatchItem.mode ("normal" for Solo, "trichrome" for either Trichrome
    # variant) - MainWindow decides whether to apply it directly or
    # intercept with a confirmation (switching away from a multi-channel
    # trichrome photo); this panel has no visibility into that, so it never
    # applies the switch itself. harris_shutter_toggled (below) fires
    # alongside it whenever the target is a Trichrome variant - see
    # _on_mode_combo_changed. Call set_mode_selection() to reflect the
    # actual outcome afterward (including a reverted/cancelled switch).
    mode_change_requested = Signal(str)
    harris_shutter_toggled = Signal(bool)
    # Emitted (from_index, to_index) when a channel's drag handle is dropped
    # onto another channel's file block - see _ChannelSwapHandle/_ChannelFileBlock.
    channel_swap_requested = Signal(int, int)
    # Light mode only (see set_light_mode_active) - the Reset button next
    # to the Mode combo, clearing all 3 channels' loaded images/alignment/
    # tone back to blank. MainWindow implements the actual reset since it
    # owns self.layers.
    light_mode_reset_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # Only histogram_box stays title-less. Block key is "files" (matching
        # main_window.py's _ALL_BLOCK_KEYS and every
        # block_side/block_visible/block_widgets entry) - was "import" before,
        # a real bug: the drag handle's MIME data carried a key that matched
        # nothing in MainWindow's block state, so dragging this block silently
        # failed every time, same-panel included.
        outer, header_row, self.title_label = start_block_chrome(self, "files", "import_panel_title")
        header_row.addStretch(1)
        self.body, root, self.collapse_button, self.close_button = finish_block_chrome(outer, header_row)

        # --- Mode row: the Solo/Classic Trichrome/Color Trichrome combo, its
        # "?" info button, and the 3 quick per-photo toggles (B&W Film, Color
        # Film, Negative) all on one line. The standalone "Mode" label is gone
        # entirely - the combo's own icon (see below) already identifies what
        # the control is without needing a text label next to it, same
        # reasoning any icon-only toolbar button in this app already relies on.
        # AdjustToContents sizes the combo to its *widest* item, not just
        # whichever one happens to be selected - which is what leaves room for
        # the 3 toggle buttons on the same line without the combo eating all
        # the available width the way its previous stretch=1 did.
        # retranslate_ui() also enforces an explicit minimum width computed
        # from font metrics - see the comment there for why AdjustToContents
        # alone isn't enough.
        mode_row = QHBoxLayout()
        mode_row.setSpacing(_ROW_SPACING)
        # Indented past the channel dots, so the combo's left edge lines up
        # with the channel frames below.
        mode_row.addSpacing(_ChannelDot.WIDTH + _ROW_SPACING)
        self.mode_combo = _ModeComboBox()
        self.mode_combo.setFixedHeight(_ROW_HEIGHT)
        # The default macOS combo delegate ignores the QSS ::item rules, so
        # the popup had no hover highlight.
        self.mode_combo.setItemDelegate(QStyledItemDelegate(self.mode_combo))
        self.mode_combo.setStyleSheet(_mode_combo_style())
        theme.on_change(self._apply_theme)
        self.mode_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.mode_combo.setIconSize(QSize(_MODE_COMBO_ICON_SIZE, _MODE_COMBO_ICON_SIZE))
        self.mode_combo.currentIndexChanged.connect(lambda _i: self._on_mode_combo_changed())
        mode_row.addWidget(self.mode_combo)
        self.mode_info_button = InfoButton("mode_select_info")
        mode_row.addWidget(self.mode_info_button)
        # Light mode only - clears all 3 channels' loaded images/alignment/tone
        # back to blank, so the user can restart the single photo without ever
        # needing Batch Import (unavailable in Light mode) or a New Session (no
        # session concept there either). Hidden by default; see
        # set_light_mode_active.
        self.light_mode_reset_button = SvgToolButton(
            "Global/Reset.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.light_mode_reset_button.clicked.connect(
            lambda _checked=False: self.light_mode_reset_requested.emit())
        self.light_mode_reset_button.setVisible(False)
        mode_row.addWidget(self.light_mode_reset_button)
        # The quicker "B&W Film"/"Color Film" shortcut buttons that used to sit
        # here (duplicating the combo's own B&W/Color Trichrome entries, and
        # driving the old Solo-N&B cosmetic mechanism) were removed - fully
        # redundant once Trichrome's B&W/ Color choice is only ever made via
        # this combo, and Solo's own cosmetic B&W toggle lives in ColorPanel
        # instead (see global_panel.py's black_white_button and that module's
        # docstring for the full reasoning).
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        # --- Trichrome mode: the 3 channel rows + auto-align + lock ---
        self.trichrome_container = QWidget()
        trichrome_layout = QVBoxLayout(self.trichrome_container)
        trichrome_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.trichrome_container)

        self.channel_labels: list[_ChannelDot] = []
        self.filename_labels: list[ElidingLabel] = []
        self.channel_file_blocks: list[_ChannelFileBlock] = []

        for label in ("R", "G", "B"):
            idx = len(self.channel_labels)
            row = QHBoxLayout()
            row.setSpacing(_ROW_SPACING)
            color = CHANNEL_COLORS.get(label, "#888")
            # The channel's color as a dot; its name is the tooltip.
            channel_label = _ChannelDot(color)
            row.addWidget(channel_label)

            file_block = _ChannelFileBlock(idx, self)
            row.addWidget(file_block, stretch=1)

            trichrome_layout.addLayout(row)
            self.channel_labels.append(channel_label)
            self.filename_labels.append(file_block.filename_label)
            self.channel_file_blocks.append(file_block)

        # --- Normal mode: a single photo, no alignment/recompose ---
        self.normal_container = QWidget()
        normal_layout = QVBoxLayout(self.normal_container)
        normal_layout.setContentsMargins(0, 0, 0, 0)
        normal_row = QHBoxLayout()
        self.normal_path_label = QLabel()
        # Same font-size as normal_filename_label (only the weight differs) -
        # otherwise the two labels' differing line-heights get centered around
        # the row's own cross-axis independently, landing their text baselines
        # a couple pixels apart instead of visually "on the same line" (more
        # visible with real macOS font metrics than in headless testing). The
        # explicit AlignVCenter further pins both to the row's exact vertical
        # center regardless of platform font quirks.
        self.normal_path_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        normal_row.addWidget(self.normal_path_label, alignment=Qt.AlignVCenter)
        self.normal_filename_label = ElidingLabel()
        self.normal_filename_label.setStyleSheet("color: #888; font-size: 11px;")
        normal_row.addWidget(self.normal_filename_label, stretch=1, alignment=Qt.AlignVCenter)
        normal_layout.addLayout(normal_row)
        root.addWidget(self.normal_container)
        self.normal_container.hide()

        self._has_image = [False, False, False]
        self._has_normal_image = False
        self._light_mode_active = False
        self.retranslate_ui()
        # Default selection - matches BatchItem's own default mode
        # ("trichrome", harris_shutter False). MainWindow immediately
        # overrides this via set_mode_selection() once a real active photo
        # exists, so this only matters before that first sync.
        self.set_mode_selection("trichrome", False)

    def _set_filename_drag_state(self, index: int, state: str) -> None:
        """Highlights channel_file_blocks[index] - the filename+swap-handle
        block as a whole, see _ChannelFileBlock - as a live preview of a
        pending channel swap: "source" for the channel currently being
        dragged, "target" for whichever channel's block the cursor is over,
        "" to clear. Called from _ChannelSwapHandle (drag start/end) and
        _ChannelFileBlock (drag enter/leave/drop) - see those for when each
        state applies."""
        self.channel_file_blocks[index].set_drag_state(state)

    def _clear_filename_drag_states(self) -> None:
        """Resets every channel's file-block highlight - called once a drag
        ends (dropped or cancelled) so a target highlight left over from a
        drop that didn't fire a proper dragLeaveEvent (e.g. the drag was
        cancelled outside any widget) can't get stuck showing."""
        for file_block in self.channel_file_blocks:
            file_block.set_drag_state("")

    def set_filename(self, index: int, text: str, size: tuple[int, int] | None = None) -> None:
        """Channel ``index``'s row: ``text`` is the file name ("" for an empty
        channel), ``size`` its (width, height) in pixels when known."""
        self._has_image[index] = bool(text)
        block = self.channel_file_blocks[index]
        block.size_label.setText(f"{size[0]}×{size[1]}" if size else "")
        block.set_loaded(bool(text))
        self.filename_labels[index].setText(text or self._empty_slot_text(index))

    @staticmethod
    def _empty_slot_text(index: int) -> str:
        return i18n.tr("channel_empty_slot", channel=i18n.channel_name(index))

    def set_normal_filename(self, text: str) -> None:
        self._has_normal_image = bool(text)
        self.normal_filename_label.setText(text or i18n.tr("no_image_loaded"))

    def _visible_mode_keys(self) -> tuple[str, ...]:
        """Which MODE_KEYS entries the combo actually lists right now - Light
        mode drops Solo entirely (not just disables it) since it never has a
        use for it: Light mode always starts from a fresh blank BatchItem (see
        MainWindow's _enter_light_mode) and Light -> Advanced only ever carries
        over a Classic/Color Trichrome photo, so there's never a pre-existing
        Solo selection to preserve either. Every combo-index-based lookup below
        goes through this (not the raw MODE_KEYS/MODE_KEYS.index) so they stay
        correct regardless of which set is actually populated."""
        if self._light_mode_active:
            return tuple(k for k in MODE_KEYS if k != "solo")
        return MODE_KEYS

    def _current_mode_key(self) -> str | None:
        idx = self.mode_combo.currentIndex()
        keys = self._visible_mode_keys()
        return keys[idx] if 0 <= idx < len(keys) else None

    def is_harris_shutter_active(self) -> bool:
        """Whether the combo's current selection is Color Trichrome - the
        replacement for what used to be a standalone checkbox's
        isChecked(), read by MainWindow at load time (single manual load,
        batch import) to decide luminance vs. real-channel extraction."""
        return self._current_mode_key() == "color_trichrome"

    def _on_mode_combo_changed(self) -> None:
        key = self._current_mode_key()
        if key is None:
            return
        if key == "solo":
            self.mode_change_requested.emit("normal")
        else:
            # Reachable both from Solo (a real mode switch) and from the
            # other Trichrome variant (item.mode already "trichrome" -
            # on_import_mode_change_requested's own item.mode == mode
            # guard makes this a no-op there, only harris_shutter_toggled
            # actually does anything in that case).
            self.mode_change_requested.emit("trichrome")
            self.harris_shutter_toggled.emit(key == "color_trichrome")

    def set_mode_selection(self, mode: str, harris_shutter: bool) -> None:
        """Programmatic sync of the Mode combo (activating a different
        photo, session restore, undo/redo, a reverted/cancelled mode
        switch) - blocks signals so this never re-emits
        mode_change_requested/harris_shutter_toggled.

        ``harris_shutter`` is the *mode-appropriate* value - MainWindow
        passes self.normal_layer.harris_shutter while in Solo mode or
        self.layers[0].harris_shutter otherwise (B&W/Color Trichrome) -
        only the latter actually affects which combo entry is shown
        (Solo has no B&W/Color Trichrome distinction of its own).
        ``key`` falling back to index 0 when it isn't in
        _visible_mode_keys() (Solo requested while in Light mode) is a
        pure defensive fallback - shouldn't be reachable given the above,
        but a silent wrong-but-safe selection beats a ValueError crash."""
        is_normal = mode == "normal"
        key = "solo" if is_normal else ("color_trichrome" if harris_shutter else "bw_trichrome")
        visible = self._visible_mode_keys()
        idx = visible.index(key) if key in visible else 0
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(idx)
        self.mode_combo.blockSignals(False)
        self.trichrome_container.setVisible(not is_normal)
        self.normal_container.setVisible(is_normal)

    def set_light_mode_active(self, active: bool) -> None:
        """Light mode only offers Classic/Color Trichrome - Solo is
        dropped from the combo entirely (see _visible_mode_keys) - and
        shows the Reset button."""
        current_key = self._current_mode_key()
        self._light_mode_active = active
        self.light_mode_reset_button.setVisible(active)
        self._rebuild_mode_combo_items()
        if current_key is not None and current_key in self._visible_mode_keys():
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentIndex(self._visible_mode_keys().index(current_key))
            self.mode_combo.blockSignals(False)

    def _apply_theme(self) -> None:
        # The stylesheet and the items' multi-color icons both depend on it.
        self.mode_combo.setStyleSheet(_mode_combo_style())
        for file_block in self.channel_file_blocks:
            file_block.set_loaded(file_block.loaded)
        index = self.mode_combo.currentIndex()
        self._rebuild_mode_combo_items()
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(index)
        self.mode_combo.blockSignals(False)

    def _rebuild_mode_combo_items(self) -> None:
        dpr = self.mode_combo.devicePixelRatioF() or 1.0
        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        for key in self._visible_mode_keys():
            icon = raw_svg_icon(MODE_ICONS[key], _MODE_COMBO_ICON_SIZE, dpr)
            self.mode_combo.addItem(icon, i18n.tr(MODE_LABEL_KEYS[key]))
        self.mode_combo.blockSignals(False)

    def retranslate_ui(self) -> None:
        self.title_label.setText(i18n.tr("import_panel_title"))
        # retranslate_ui() rebuilds the combo's items from scratch on every
        # call (language switch included) - re-derive the current key from
        # the *old* list (still populated at this point) so the selection
        # survives the rebuild even though Light mode's filtered list has
        # different indices than the full MODE_KEYS (a language switch
        # while in Light mode must not silently reintroduce Solo or land
        # on the wrong entry).
        current_key = self._current_mode_key()
        self._rebuild_mode_combo_items()
        visible = self._visible_mode_keys()
        idx = visible.index(current_key) if current_key in visible else 0
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(idx)
        self.mode_combo.blockSignals(False)
        self.light_mode_reset_button.setToolTip(i18n.tr("light_mode_reset_channels_tooltip"))
        # AdjustToContents alone isn't reliable here once a stylesheet is
        # applied (Qt's QStyleSheetStyle doesn't always fold the QSS's own
        # padding/arrow-box width back into the size-hint computation it feeds
        # AdjustToContents) - confirmed empirically once "Classic
        # Trichrome"/"Trichromie Classique" became the widest item and started
        # getting clipped. Computing the needed width directly from font
        # metrics + the QSS's own known padding/icon/arrow dimensions and
        # enforcing it as a minimum sidesteps that entirely, regardless of what
        # AdjustToContents itself comes up with.
        metrics = self.mode_combo.fontMetrics()
        widest_text = max(metrics.horizontalAdvance(i18n.tr(MODE_LABEL_KEYS[key])) for key in MODE_KEYS)
        # icon + icon-text gap + QSS "padding: 3px 4px 3px 6px" (left+right)
        # + the QSS drop-down arrow's own 20px width + a small safety margin.
        chrome_width = _MODE_COMBO_ICON_SIZE + 4 + 10 + 20 + 10
        self.mode_combo.setMinimumWidth(widest_text + chrome_width)
        # The popup list: icon + gap + text, plus its own padding (view and
        # item, both sides), the frame and a safety margin.
        self.mode_combo.view().setMinimumWidth(widest_text + _MODE_COMBO_ICON_SIZE + 60)
        for i, label in enumerate(("R", "G", "B")):
            self.channel_labels[i].setToolTip(i18n.tr(CHANNEL_KEY[label]))
            self.channel_file_blocks[i].clear_button.setToolTip(i18n.tr("channel_clear_tooltip"))
            if not self._has_image[i]:
                self.filename_labels[i].setText(self._empty_slot_text(i))
        self.normal_path_label.setText(i18n.tr("normal_file_path_label"))
        if not self._has_normal_image:
            self.normal_filename_label.setText(i18n.tr("no_image_loaded"))
