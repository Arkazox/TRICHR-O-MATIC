"""Top-of-sidebar panel: a single Mode selector (Solo / Classic Trichrome /
Color Trichrome), then either load the 3 channel images (either Trichrome
variant) or a single photo (Solo). Auto Align and Lock Layer Position moved
to the top of the "Trichrome Process" block (main_window.py's
independent_channels_group) - 2026-09-04.

Negative (invert) briefly lived here (2026-09-07) before moving back to
LightPanel's header the same day, once the user settled on a clearer
overall split: Negative reads as a Light-adjacent tonal concept to a user,
even though it's technically per-photo source state - see global_panel.py
for where it lives now.

Mode selector, unified 2026-09-07 from what used to be two separate
controls: a plain Normal/Trichrome toggle here, plus an independent
"Harris Shutter Effect" checkbox down in the Trichrome Process block. Both
described the same underlying thing - how this photo's files should be
interpreted - so they're now one 3-way choice, styled like the Crop tool's
own aspect-ratio selector (label + combo + a "?" info button - the combo's
own per-item icon folded the separate icon label the first pass had into
the combo itself later the same day, once Qt's own item-icon support made
that redundant):
**Solo** (BatchItem.mode == "normal" - a single already-composed photo),
**Classic Trichrome** (mode == "trichrome", ChannelLayer.harris_shutter ==
False - the classic case, 3 B&W photos through color filters), **Color
Trichrome** (mode == "trichrome", harris_shutter == True - 3 real color
photos, each keeping its own R/G/B channel). See CLAUDE.md's Harris
Shutter Effect section for the full processing-difference explanation."""
from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QDrag, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .. import i18n
from ..paths import icon_path
from .block_header_bar import finish_block_chrome, start_block_chrome
from .channel_panel import CHANNEL_COLORS, CHANNEL_KEY
from .controls import ElidingLabel
from .info_bubble import InfoButton
from .svg_icons import SvgToolButton, raw_svg_icon

# Drag-and-drop channel swap (2026-09-09): dragging a channel's own grip
# handle onto another channel's file block swaps which photo - and its own
# alignment/tone edits, see MainWindow._swap_channel_layers - is loaded into
# each of the two channels (e.g. swap the Red and Blue channel images).
# Mime payload is just the source channel index (0/1/2), utf-8 encoded -
# same shape as block_header_bar.BLOCK_REORDER_MIME's own single-value mime,
# a completely separate mechanism/mime type from that block-reorder drag.
_CHANNEL_SWAP_MIME = "application/x-trichrome-channel-index"


def _swap_source_index(mime: QMimeData) -> int | None:
    if not mime.hasFormat(_CHANNEL_SWAP_MIME):
        return None
    try:
        return int(bytes(mime.data(_CHANNEL_SWAP_MIME)).decode("utf-8"))
    except ValueError:
        return None


def _translucent_grab(widget: QWidget, opacity: float = 0.55) -> QPixmap:
    """A plain screen-grab of ``widget``, redrawn into a fresh pixmap at
    reduced opacity - used as the channel-swap drag pixmap so the dragged
    visual is exactly the filename+handle block being moved (Finder-style:
    you see what you're picking up), rather than a synthesized stand-in.
    No border (per the user's own ask, 2026-09-09) - a target channel's own
    blue drop-highlight sits directly under this while hovering, and needs
    to stay visible through it rather than being fully covered."""
    source = widget.grab()
    result = QPixmap(source.size())
    result.setDevicePixelRatio(source.devicePixelRatio())
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setOpacity(opacity)
    painter.drawPixmap(0, 0, source)
    painter.end()
    return result


# Highlight styles for a channel's _ChannelFileBlock (filename + swap handle,
# grouped into one visual unit per the user's own "le bouton et le chemin
# d'accès ne forme qu'un bloc" ask, 2026-09-09 - an earlier pass framed only
# the filename label, and before that the whole row including the unrelated
# Load/Change Image button, both reverted) as a live preview of the pending
# swap while a drag is in progress - "source" (dashed, the block being
# picked up) on the dragged channel for the whole drag, "target" (solid
# accent-blue, the same accent used by the block drag-reorder insertion
# line) on whichever channel's block the cursor is currently over, so both
# halves of the prospective swap are visible before the drop actually
# commits to anything. All 3 share the same border width/radius so
# toggling the highlight never changes the block's own size.
_FILE_BLOCK_BASE_STYLE = "border: 1px solid transparent; border-radius: 4px; padding: 1px 2px;"
_FILE_BLOCK_SOURCE_STYLE = "border: 1px dashed rgba(255, 255, 255, 90); border-radius: 4px; padding: 1px 2px;"
_FILE_BLOCK_TARGET_STYLE = (
    "border: 1px solid #5b9bd5; border-radius: 4px; padding: 1px 2px; "
    "background: rgba(91, 155, 213, 40);"
)


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
        # A plain QWidget doesn't paint its own stylesheet border/background
        # by default (only specific widget types like QLabel/QPushButton do)
        # - without this, Qt's style-sheet cascade instead let the border
        # leak onto whichever child widget happens to render it (here,
        # filename_label, since it has no competing border of its own),
        # covering only that child's rect rather than the whole block, while
        # swap_handle's own explicit "border: none" (SvgToolButton's base
        # style) opted it out entirely - confirmed empirically (2026-09-09)
        # by grabbing the block and inspecting the rendered pixels.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(_FILE_BLOCK_BASE_STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.filename_label = ElidingLabel()
        # Explicit "border: none; background: transparent" so the label
        # doesn't independently pick up the block's own border/background
        # via the stylesheet cascade now that the block paints them itself
        # - without this, highlighting the block would draw two nested
        # frames again (the block's real one plus the label's inherited
        # one), the exact "des cadres dans des cadres" problem from before.
        self.filename_label.setStyleSheet(
            "color: #888; font-size: 11px; border: none; background: transparent;")
        layout.addWidget(self.filename_label, stretch=1)
        self.swap_handle = _ChannelSwapHandle(channel_index, self, panel)
        layout.addWidget(self.swap_handle)

    def dragEnterEvent(self, event) -> None:
        source_index = _swap_source_index(event.mimeData())
        if source_index is not None and source_index != self.channel_index:
            event.acceptProposedAction()
            self._panel._set_filename_drag_state(self.channel_index, "target")
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._panel._set_filename_drag_state(self.channel_index, "")

    def dropEvent(self, event) -> None:
        source_index = _swap_source_index(event.mimeData())
        self._panel._set_filename_drag_state(self.channel_index, "")
        if source_index is None or source_index == self.channel_index:
            event.ignore()
            return
        event.acceptProposedAction()
        self._panel.channel_swap_requested.emit(source_index, self.channel_index)


# Size the combo's own item icons are rendered at - matches the 18px
# default SvgIconLabel used before the Mode row folded its separate icon
# label into the combo itself (2026-09-07, "un menu déroulant mieux
# intégré... avec les icones qui s'affichent dans le menu déroulant").
_MODE_COMBO_ICON_SIZE = 18

# Flat/borderless-at-rest styling so the combo reads as part of the
# block's own surface rather than a separate native control sitting on
# top of it (2026-09-07, user's own ask: "un dropdown menu plus sobre et
# intégré à l'interface... qui se fond plus dans le bloc"). Applying any
# stylesheet at all switches Qt from native platform chrome to its own
# QStyleSheetStyle rendering for this one widget - deliberately scoped to
# just this combo, not a blanket app-wide QComboBox rule, since no other
# combo in the app (crop_panel.py's aspect-ratio/grid pickers) was asked
# for this treatment. The dropdown arrow reuses the same
# Global/chevron-down.svg glyph every block's own collapse chevron
# already uses (already a plain white stroke, so no re-tinting needed -
# confirmed by rendering it as a QComboBox::down-arrow image, which Qt's
# QSS engine renders as a real vector cheveron, not a broken image).
# selection-background-color reuses #5b9bd5, the one accent blue already
# established elsewhere in the app (the block drag-reorder insertion line).
_MODE_COMBO_STYLE = f"""
QComboBox {{
    background: rgba(255, 255, 255, 14);
    border: 1px solid rgba(255, 255, 255, 35);
    border-radius: 4px;
    padding: 3px 4px 3px 6px;
    color: #f0f0f0;
}}
QComboBox:hover {{
    background: rgba(255, 255, 255, 24);
    border: 1px solid rgba(255, 255, 255, 60);
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: url({icon_path("Global/chevron-down.svg")});
    width: 12px;
    height: 12px;
}}
QComboBox QAbstractItemView {{
    background-color: #2b2b2b;
    color: #f0f0f0;
    border: 1px solid rgba(255, 255, 255, 40);
    outline: none;
    selection-background-color: rgba(91, 155, 213, 90);
    selection-color: #ffffff;
}}
"""


# Order matches the combo's own item order. Icons are rendered "raw" (their
# own embedded colors, not the usual single-tint convention - see
# svg_icons.raw_svg_pixmap) since the whole point is 3 visually distinct
# glyphs. bw_trichrome/color_trichrome are General/layers-mode-{bw,color}.svg
# - the app's own filled "stack" glyph (resources/icons/General/stack.svg,
# a solid front diamond + 2 chevron slivers, as opposed to the plain-
# outline layers-outline.svg these 2 files used to derive from until
# 2026-09-07) with its 2 <path> elements split into 3 (the original has
# the top+bottom shapes sharing one path, same structure layers-outline.svg
# had) so each layer can carry its own explicit fill: Classic Trichrome grades
# from white at the front down to darker light-grays at the back
# (#ffffff/#e5e5e5/#cccccc - "white", "90% gray", "80% gray"); Color
# Trichrome colors each layer in its real R/G/B channel color (matching
# channel_panel.CHANNEL_COLORS exactly). solo is Global/stack-middle.svg -
# a new asset built to match stack-front.svg/stack-back.svg's own family
# (front/back's card fully outlined AND filled; a card occluded by the one
# in front of it is outline-only with just a filled chevron sliver peeking
# through) with the *middle* card filled instead - the old outline-based
# General/layers-mode-solo.svg is left on disk, unreferenced, same
# leave-it-there convention as every other superseded icon in this project.
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


class ImportPanel(QGroupBox):
    load_requested = Signal(int)
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

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # Title restored 2026-09-04 (removed 2026-09-03, then the user
        # asked for it back - "c'était mieux") - only histogram_box stays
        # title-less.
        # Block key is "files" (matching main_window.py's _ALL_BLOCK_KEYS
        # and every block_side/block_visible/block_widgets entry) - was
        # "import" until 2026-09-04, a real bug: the drag handle's MIME
        # data carried a key that matched nothing in MainWindow's block
        # state, so dragging this block silently failed every time,
        # same-panel included.
        outer, header_row, self.title_label = start_block_chrome(self, "files", "import_panel_title")
        header_row.addStretch(1)
        self.body, root, self.collapse_button, self.close_button = finish_block_chrome(outer, header_row)

        # --- Mode row: the Solo/Classic Trichrome/Color Trichrome combo, its
        # "?" info button, and the 3 quick per-photo toggles (B&W Film,
        # Color Film, Negative) all on one line (2026-09-07, user's own
        # ask: "retire le mot 'Mode'... mets les boutons... sur la même
        # ligne"). The standalone "Mode" label is gone entirely - the
        # combo's own icon (see below) already identifies what the control
        # is without needing a text label next to it, same reasoning any
        # icon-only toolbar button in this app already relies on.
        # AdjustToContents sizes the combo to its *widest* item, not just
        # whichever one happens to be selected - which is what leaves room
        # for the 3 toggle buttons on the same line without the combo
        # eating all the available width the way its previous stretch=1
        # did. retranslate_ui() also enforces an explicit minimum width
        # computed from font metrics - see the comment there for why
        # AdjustToContents alone isn't enough.
        mode_row = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.setStyleSheet(_MODE_COMBO_STYLE)
        self.mode_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.mode_combo.setIconSize(QSize(_MODE_COMBO_ICON_SIZE, _MODE_COMBO_ICON_SIZE))
        self.mode_combo.currentIndexChanged.connect(lambda _i: self._on_mode_combo_changed())
        mode_row.addWidget(self.mode_combo)
        self.mode_info_button = InfoButton("mode_select_info")
        mode_row.addWidget(self.mode_info_button)
        # The quicker "B&W Film"/"Color Film" shortcut buttons that used
        # to sit here (duplicating the combo's own B&W/Color Trichrome
        # entries, and driving the old Solo-N&B cosmetic mechanism) were
        # removed 2026-09-07 - now fully redundant once Trichrome's B&W/
        # Color choice is only ever made via this combo, and Solo's own
        # cosmetic B&W toggle lives in ColorPanel instead (see
        # global_panel.py's black_white_button). See CLAUDE.md's "Mode
        # selector" section for the full reasoning.
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        # --- Trichrome mode: the 3 channel rows + auto-align + lock ---
        self.trichrome_container = QWidget()
        trichrome_layout = QVBoxLayout(self.trichrome_container)
        trichrome_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.trichrome_container)

        self.channel_labels: list[QLabel] = []
        self.filename_labels: list[ElidingLabel] = []
        self.load_buttons: list[QPushButton] = []
        self.channel_file_blocks: list[_ChannelFileBlock] = []

        for label in ("R", "G", "B"):
            idx = len(self.channel_labels)
            row = QHBoxLayout()
            color = CHANNEL_COLORS.get(label, "#888")
            channel_label = QLabel()
            channel_label.setStyleSheet(f"color: {color}; font-weight: bold;")
            channel_label.setFixedWidth(50)
            row.addWidget(channel_label)

            file_block = _ChannelFileBlock(idx, self)
            row.addWidget(file_block, stretch=1)

            load_button = QPushButton()
            load_button.clicked.connect(lambda _checked=False, i=idx: self.load_requested.emit(i))
            row.addWidget(load_button)

            trichrome_layout.addLayout(row)
            self.channel_labels.append(channel_label)
            self.filename_labels.append(file_block.filename_label)
            self.load_buttons.append(load_button)
            self.channel_file_blocks.append(file_block)

        # --- Normal mode: a single photo, no alignment/recompose ---
        self.normal_container = QWidget()
        normal_layout = QVBoxLayout(self.normal_container)
        normal_layout.setContentsMargins(0, 0, 0, 0)
        normal_row = QHBoxLayout()
        self.normal_path_label = QLabel()
        # Same font-size as normal_filename_label (only the weight differs) -
        # otherwise the two labels' differing line-heights get centered
        # around the row's own cross-axis independently, landing their text
        # baselines a couple pixels apart instead of visually "on the same
        # line" (reported 2026-09-10, more visible with real macOS font
        # metrics than in headless testing - see the font-metrics gotcha in
        # CLAUDE.md). The explicit AlignVCenter further pins both to the
        # row's exact vertical center regardless of platform font quirks.
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
        style = {
            "source": _FILE_BLOCK_SOURCE_STYLE,
            "target": _FILE_BLOCK_TARGET_STYLE,
        }.get(state, _FILE_BLOCK_BASE_STYLE)
        self.channel_file_blocks[index].setStyleSheet(style)

    def _clear_filename_drag_states(self) -> None:
        """Resets every channel's file-block highlight - called once a drag
        ends (dropped or cancelled) so a target highlight left over from a
        drop that didn't fire a proper dragLeaveEvent (e.g. the drag was
        cancelled outside any widget) can't get stuck showing."""
        for file_block in self.channel_file_blocks:
            file_block.setStyleSheet(_FILE_BLOCK_BASE_STYLE)

    def set_filename(self, index: int, text: str) -> None:
        self._has_image[index] = bool(text)
        self.filename_labels[index].setText(text or i18n.tr("no_image_loaded"))
        self.load_buttons[index].setText(
            i18n.tr("change_image_button") if text else i18n.tr("load_image_button"))

    def set_normal_filename(self, text: str) -> None:
        self._has_normal_image = bool(text)
        self.normal_filename_label.setText(text or i18n.tr("no_image_loaded"))

    def is_harris_shutter_active(self) -> bool:
        """Whether the combo's current selection is Color Trichrome - the
        replacement for what used to be a standalone checkbox's
        isChecked(), read by MainWindow at load time (single manual load,
        batch import) to decide luminance vs. real-channel extraction."""
        idx = self.mode_combo.currentIndex()
        return 0 <= idx < len(MODE_KEYS) and MODE_KEYS[idx] == "color_trichrome"

    def _on_mode_combo_changed(self) -> None:
        idx = self.mode_combo.currentIndex()
        if idx < 0:
            return
        key = MODE_KEYS[idx]
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
        (Solo has no B&W/Color Trichrome distinction of its own)."""
        is_normal = mode == "normal"
        key = "solo" if is_normal else ("color_trichrome" if harris_shutter else "bw_trichrome")
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(MODE_KEYS.index(key))
        self.mode_combo.blockSignals(False)
        self.trichrome_container.setVisible(not is_normal)
        self.normal_container.setVisible(is_normal)

    def retranslate_ui(self) -> None:
        self.title_label.setText(i18n.tr("import_panel_title"))
        current = self.mode_combo.currentIndex()
        dpr = self.mode_combo.devicePixelRatioF() or 1.0
        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        for key in MODE_KEYS:
            icon = raw_svg_icon(MODE_ICONS[key], _MODE_COMBO_ICON_SIZE, dpr)
            self.mode_combo.addItem(icon, i18n.tr(MODE_LABEL_KEYS[key]))
        self.mode_combo.setCurrentIndex(max(0, current))
        self.mode_combo.blockSignals(False)
        # AdjustToContents alone isn't reliable here once a stylesheet is
        # applied (Qt's QStyleSheetStyle doesn't always fold the QSS's own
        # padding/arrow-box width back into the size-hint computation it
        # feeds AdjustToContents) - confirmed empirically (2026-09-09) once
        # "Classic Trichrome"/"Trichromie Classique" became the widest item
        # and started getting clipped. Computing the needed width directly
        # from font metrics + the QSS's own known padding/icon/arrow
        # dimensions and enforcing it as a minimum sidesteps that entirely,
        # regardless of what AdjustToContents itself comes up with.
        metrics = self.mode_combo.fontMetrics()
        widest_text = max(metrics.horizontalAdvance(i18n.tr(MODE_LABEL_KEYS[key])) for key in MODE_KEYS)
        # icon + icon-text gap + QSS "padding: 3px 4px 3px 6px" (left+right)
        # + the QSS drop-down arrow's own 20px width + a small safety margin.
        chrome_width = _MODE_COMBO_ICON_SIZE + 4 + 10 + 20 + 10
        self.mode_combo.setMinimumWidth(widest_text + chrome_width)
        for i, label in enumerate(("R", "G", "B")):
            self.channel_labels[i].setText(i18n.tr(CHANNEL_KEY[label]) + ":")
            self.load_buttons[i].setText(
                i18n.tr("change_image_button") if self._has_image[i] else i18n.tr("load_image_button"))
            if not self._has_image[i]:
                self.filename_labels[i].setText(i18n.tr("no_image_loaded"))
        self.normal_path_label.setText(i18n.tr("normal_file_path_label"))
        if not self._has_normal_image:
            self.normal_filename_label.setText(i18n.tr("no_image_loaded"))
