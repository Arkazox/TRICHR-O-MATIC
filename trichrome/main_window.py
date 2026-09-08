"""Main application window wiring the model, imaging pipeline and widgets together."""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys

import numpy as np
from PySide6.QtCore import QEvent, QSettings, Qt, QThread, QTimer
from PySide6.QtGui import QAction, QActionGroup, QImage, QKeySequence, QPalette, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QButtonGroup, QDialog, QFileDialog, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMenu, QPushButton, QSizePolicy, QSplitter, QStackedWidget, QStatusBar,
    QTextBrowser, QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from . import alignment, i18n, imaging
from .batch_window import BatchWindow
from .import_worker import BatchImportWorker
from .model import (
    CHANNEL_NAMES, BatchItem, ChannelLayer, CropSettings, GlobalCorrection, ensure_batch_item_uid_above,
    new_project_layers,
)
from .widgets.block_header_bar import (
    BlockReorderZone, finish_block_chrome, make_disabled_message_label, set_block_collapsed,
    set_block_disabled, start_block_chrome,
)
from .widgets.canvas_widget import CanvasWidget
from .widgets.carousel_widget import CarouselWidget
from .widgets.channel_panel import CHANNEL_COLORS, CHANNEL_KEY, ChannelPanel
from .widgets.compare_button import CompareButton
from .widgets.crop_panel import CropPanel
from .widgets.controls import ArrowKeyScrollArea
from .widgets.curves_panel import CurvesPanel
from .widgets.export_dialog import ExportDialog
from .widgets.filmstrip_toggle_button import FilmstripToggleButton
from .widgets.fullscreen_toggle_button import FullscreenToggleButton
from .widgets.global_panel import ColorPanel, LightPanel
from .widgets.histogram_widget import HistogramPanel
from .widgets.alert_dialog import show_alert
from .widgets.import_panel import ImportPanel
from .widgets.info_bubble import InfoButton
from .widgets.missing_files_banner import MissingFilesBanner
from .widgets.mode_switch_dialog import ModeSwitchDialog
from .widgets.rotate_toggle_button import RotateLeftButton, RotateRightButton
from .widgets.scan_panel import ScanPanel
from .widgets.sort_button import SortButton
from .widgets.svg_icons import (
    HEADER_COMPANION_BTN_SIZE, HEADER_COMPANION_ICON_SIZE,
    SvgCheckableToolButton, SvgLetterToggleButton, SvgToolButton, SvgTwoStateToggleButton,
)
from .widgets.unsaved_changes_dialog import UnsavedChangesDialog

# Neutral tone/global-correction values used by "Compare" mode to preview
# the original: black, white, gamma, exposure, brightness, contrast,
# shadows, highlights (matches ChannelLayer.reset_tone()'s defaults).
# Alignment and invert are deliberately NOT part of this - compare only
# bypasses color.
_NEUTRAL_TONE = (0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_IDENTITY_CURVE = ((0.0, 0.0), (1.0, 1.0))
_CURVE_CHANNELS = ("Y", "R", "G", "B")
_IDENTITY_CURVES = {ch: _IDENTITY_CURVE for ch in _CURVE_CHANNELS}
_NEUTRAL_GLOBAL = (0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, _IDENTITY_CURVES, False)

# Carousel/grid thumbnail source resolution - see _update_carousel_thumbnail.
_THUMBNAIL_MAX_DIM = 480


def _decode_curves(raw: str) -> dict[str, list[tuple[float, float]]]:
    """Parses the Curves tool's QSettings-string encoding (a JSON
    {"Y"/"R"/"G"/"B": [[x, y], ...]} object, the same json.dumps/loads-a-
    string convention already used for layout_preset_data_*) back into a
    {channel: [(x, y), ...]} dict - all-identity for a missing/empty/
    corrupt value (a session saved before the Curves tool existed, before
    it went per-channel, or anything unparseable), and any channel key
    missing from an otherwise-valid value defaults to identity too."""
    if not raw:
        return {ch: [tuple(p) for p in _IDENTITY_CURVE] for ch in _CURVE_CHANNELS}
    try:
        data = json.loads(raw)
        return {
            ch: [(float(x), float(y)) for x, y in data[ch]] if ch in data else [tuple(p) for p in _IDENTITY_CURVE]
            for ch in _CURVE_CHANNELS
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return {ch: [tuple(p) for p in _IDENTITY_CURVE] for ch in _CURVE_CHANNELS}


def _decode_film_base(raw: str) -> dict | None:
    """Parses a ChannelLayer.film_base value's QSettings-string encoding
    (the same json.dumps/loads-a-string convention _decode_curves uses) -
    None for a missing/empty/corrupt value (no correction), unlike
    _decode_curves' all-identity default, since "no film base sampled" is
    film_base's own natural default rather than a per-key fallback."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    result = {k: float(v) for k, v in data.items() if k in ("R", "G", "B") and isinstance(v, (int, float))}
    return result or None

# Matches the "(N)" version suffix Duplicate Selection appends, so
# duplicating an already-duplicated photo increments N instead of stacking
# another suffix (e.g. "IMG_1234 (2)" -> "IMG_1234 (3)", not "... (2) (2)").
_DUPLICATE_SUFFIX_RE = re.compile(r"^(.*) \((\d+)\)$")

# Dragging a curve point emits `changed` on every raw mouse-move (unlike a
# QSlider, which is quantized to its own step range) - triggering a full
# recompute_preview() (warp + composite + histogram + canvas repaint) on
# every single one of those can't keep up with a fast drag, and unlike a
# 1D slider's value catching up a frame late, a laggy 2D curve point read
# as visibly janky against the cursor (2026-09-04, "la modification de la
# courbe n'est pas très fluide"). CurveEditor's own on-screen redraw stays
# instant/unthrottled (see on_curve_changed) - only the expensive full
# image recompute is throttled, to at most one per this many ms. 16ms
# matches a 60Hz display (~62.5fps) - most screens' refresh rate, and the
# user's own explicit choice (2026-09-04) over the initial, more
# conservative 40ms guess. Below this, recompute_preview()'s own real
# cost (not this timer) becomes the limiting factor regardless.
_CURVE_RECOMPUTE_THROTTLE_MS = 16

# The block system (2026-09-04): every side-panel block (Files/Channels on
# the left; Histogram/Light/Color/Crop on the right; Scan can live on
# either) has its own side, position, visibility and collapsed state -
# freely reassignable at runtime by dragging a block's grip handle (within
# or across panels), collapsing it, or closing it (restorable from the
# Tools menu). These are the defaults the app starts with and that
# Window > Reset Layout restores - matches what the old exclusive
# tool-switcher used to show by default (Files+Channels left;
# Histogram+Light+Color right; Crop/Scan hidden until enabled).
# Order here is what the Tools menu lists top-to-bottom (built by
# iterating this tuple directly, see _build_ui) - "curves" sits between
# "light" and "color" specifically for that menu (2026-09-04, the user's
# own explicit placement); it does NOT affect the actual default panel
# position, which is _DEFAULT_RIGHT_BLOCK_ORDER's own separate list
# (curves stays last there, after crop).
_ALL_BLOCK_KEYS = ("files", "channels", "histogram", "light", "curves", "color", "crop", "scan")
_DEFAULT_BLOCK_SIDE = {
    "files": "left", "channels": "left", "scan": "left",
    "histogram": "right", "light": "right", "color": "right", "crop": "right", "curves": "right",
}
_DEFAULT_BLOCK_VISIBLE = {
    "files": True, "channels": True, "scan": False,
    "histogram": True, "light": True, "color": True, "crop": False, "curves": False,
}
_DEFAULT_LEFT_BLOCK_ORDER = ["files", "channels", "scan"]
_DEFAULT_RIGHT_BLOCK_ORDER = ["histogram", "light", "color", "crop", "curves"]

# Both side panels share one width range (2026-09-04 fix) - they used to
# differ (left 360-420, right 300-360), which is exactly backwards now
# that any block can be dragged to either side: a block sized to fit the
# left panel could overflow the right one. Reusing the wider of the two
# previous ranges for both, since every block already fits it with margin
# (verified headlessly) and it's the one already used by whichever side a
# given block happens to be visiting.
_SIDE_PANEL_MIN_WIDTH = 360
_SIDE_PANEL_MAX_WIDTH = 420
# i18n key for each block's Tools-menu label - also used by retranslate_ui.
_BLOCK_MENU_LABEL_KEYS = {
    "files": "import_panel_title",
    "channels": "independent_channels_group_title",
    "histogram": "menu_tools_histogram",
    "light": "global_light_subheader",
    "color": "global_color_subheader",
    "crop": "menu_tools_crop",
    "scan": "menu_tools_scan",
    "curves": "curves_group_title",
}

# The 4 built-in default-layout menu entries (2026-09-04), each backing one
# of the top toolbar's Trichrome/Color Correction/Crop/Scan buttons -
# ordered (display name - the fixed identifier used throughout the code,
# its Window-menu i18n label key, bare-letter shortcut hint, source preset
# name) matching the toolbar's own left-to-right order. The display name
# itself is a reserved slot, not a real saved preset - on_save_layout_preset
# refuses to save a custom preset under one of these 4 names, and
# _rebuild_layout_preset_menu skips them so they never show a stray
# Load/Update/Delete submenu of their own. What each one actually loads is
# its `source` preset - an ordinary, fully editable/updatable/deletable
# custom preset the user manages like any other through the Layout Preset
# submenu (2026-09-04: user recreated these as "NewTrichrome"/
# "NewColorCorrection"/"NewCrop"/"NewScan" after finding the layouts saved
# under the display names themselves didn't match what they'd set up -
# decoupling display name from source preset name is what lets the menu
# item keep a fixed, translated label while the underlying layout it
# applies stays a normal, user-editable preset).
_BUILT_IN_LAYOUT_PRESETS = (
    ("Trichrome", "menu_window_layout_trichrome", "T", "NewTrichrome"),
    ("Color Correction", "menu_window_layout_color_correction", "E", "NewColorCorrection"),
    ("Crop", "menu_window_layout_crop", "C", "NewCrop"),
    ("Scan", "menu_window_layout_scan", "S", "NewScan"),
)
_BUILT_IN_LAYOUT_PRESET_NAMES = tuple(name for name, _key, _shortcut, _source in _BUILT_IN_LAYOUT_PRESETS)
_BUILT_IN_LAYOUT_SOURCE = {name: source for name, _key, _shortcut, source in _BUILT_IN_LAYOUT_PRESETS}

# Session files: a portable project file (every imported photo's path,
# alignment, tone, and global correction) - distinct from the QSettings-based
# autosave-on-close session, which is implicit and OS-scoped.
SESSION_FILE_EXTENSION = "trirgb"
SESSION_FILE_FILTER = "Trichr-o-matic Session (*.trirgb)"
SESSION_FORMAT_VERSION = 1

ORG_NAME = "TrichromeMaker"
APP_NAME = "TrichromeMaker"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._load_language_setting()

        self.setWindowTitle("Trichr-o-matic")
        self.resize(1500, 950)

        self.layers = new_project_layers()
        self.global_corr = GlobalCorrection()
        self.crop = CropSettings()
        # Normal mode's single-photo holder (see BatchItem.normal_layer in
        # model.py) - aliased the same way self.layers/global_corr/crop
        # already are, kept in sync with the active item by
        # activate_batch_item/_restore_state/_apply_restored_items.
        self.normal_layer = ChannelLayer(color_index=0, label="Normal")
        self.active_index: int | None = None
        self._is_focus_mode = False
        self._compare_active = False
        # Whether the interactive Crop overlay (draggable rect on the
        # canvas, Enter-to-apply, full-vs-cropped preview) is armed -
        # decoupled from the Crop block's own visibility (2026-09-04),
        # since the block can now be shown in any custom layout. See
        # _set_crop_active().
        self._crop_active = False
        # Throttles recompute_preview() during a live curve drag - see
        # _CURVE_RECOMPUTE_THROTTLE_MS and on_curve_changed(). Always calls
        # with update_curve_reference=False (via the lambda, since
        # QTimer.timeout carries no args and would otherwise fall back to
        # recompute_preview's own True default) - a curve-only recompute
        # must never refresh the Curves tool's "input" reference histogram.
        self._curve_recompute_timer = QTimer(self)
        self._curve_recompute_timer.setSingleShot(True)
        self._curve_recompute_timer.timeout.connect(lambda: self.recompute_preview(update_curve_reference=False))
        # The exact array last handed to canvas.set_image_rgb/set_image_gray
        # and histogram.set_image - the histogram pixel-pick tool samples
        # from this on hover instead of recomposing anything itself.
        self._last_preview_rgb_u8: np.ndarray | None = None
        self._session_file_path: str | None = None
        # A change counter mirroring position in the undo/redo timeline
        # (push_undo: +1, undo: -1, redo: +1) - comparing it against the
        # value recorded at the last session-file save tells us whether
        # there are unsaved changes, including correctly recognizing "undid
        # back to exactly the saved state" as not dirty.
        self._edit_counter = 0
        self._saved_edit_counter = 0
        self.batch_window: BatchWindow | None = None

        # The session always has at least one "photo" (this classic single
        # item) - the carousel/batch machinery is unified with Simple mode,
        # it just stays hidden while there's only one item to show.
        initial_item = BatchItem(base="", paths={}, layers=self.layers,
                                  global_corr=self.global_corr, crop=self.crop,
                                  normal_layer=self.normal_layer, selected=True)
        self.batch_items: list = [initial_item]
        self.batch_current_index: int = 0
        self.sort_mode: str = "import_order"
        self.sort_reversed: bool = False
        self._import_thread: QThread | None = None
        self._import_worker: BatchImportWorker | None = None
        self._import_pending: list = []
        self._import_replace: bool = True

        # Block system state (2026-09-04) - see _ALL_BLOCK_KEYS above and
        # _apply_block_layout(). block_side says which panel a block is
        # in; left_block_order/right_block_order is that panel's own full
        # order (hidden blocks keep their slot so re-showing one restores
        # its old position, per the user's explicit request); block_visible/
        # block_collapsed are independent per-block toggles.
        self.block_side: dict[str, str] = dict(_DEFAULT_BLOCK_SIDE)
        self.block_visible: dict[str, bool] = dict(_DEFAULT_BLOCK_VISIBLE)
        self.block_collapsed: dict[str, bool] = {k: False for k in _ALL_BLOCK_KEYS}
        self.left_block_order: list[str] = list(_DEFAULT_LEFT_BLOCK_ORDER)
        self.right_block_order: list[str] = list(_DEFAULT_RIGHT_BLOCK_ORDER)

        # Named layout snapshots (Window > Layout Preset) - loaded eagerly
        # here since _build_ui() needs the list to populate the menu.
        self._layout_preset_names: list[str] = list(
            QSettings(ORG_NAME, APP_NAME).value("layout_preset_names", [], type=list))

        self._clipboard_settings: dict | None = None
        self._undo_stack: list = []
        self._redo_stack: list = []
        self._undo_suppressed = False
        self._undo_coalesce_keys: set = set()
        self._undo_coalesce_timers: dict = {}

        self._build_ui()
        self._connect_signals()
        # App-wide, so a click on any other window (a dialog, the batch
        # window) disarms the histogram pick tool too, not just clicks
        # inside this window - see eventFilter().
        QApplication.instance().installEventFilter(self)
        self._refresh_reference_ui()
        self._undo_suppressed = True
        try:
            self._restore_session()
        finally:
            self._undo_suppressed = False
        self._sync_sort_menu_state()
        self.recompute_preview()
        # Deferred: the viewport isn't laid out to its final size yet at this
        # point (the window hasn't been shown), so fit-to-window would use a
        # wrong size if computed synchronously here.
        QTimer.singleShot(0, self.canvas.zoom_fit)

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------
    def _load_language_setting(self) -> None:
        settings = QSettings(ORG_NAME, APP_NAME)
        lang = settings.value("language", i18n.DEFAULT_LANGUAGE)
        i18n.set_language(lang)

    def change_language(self, lang: str) -> None:
        if lang == i18n.current_language():
            return
        i18n.set_language(lang)
        QSettings(ORG_NAME, APP_NAME).setValue("language", lang)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.file_menu.setTitle(i18n.tr("menu_file"))
        for i, action in enumerate(self.load_actions):
            action.setText(i18n.tr("menu_load_channel", channel=i18n.channel_name(i)))
        self.new_session_action.setText(i18n.tr("menu_new_session"))
        self.open_session_action.setText(i18n.tr("menu_open_session"))
        self.save_session_action.setText(i18n.tr("menu_save_session"))
        self.save_session_as_action.setText(i18n.tr("menu_save_session_as"))
        self.export_action.setText(i18n.tr("export_button"))
        self.batch_action.setText(i18n.tr("menu_batch"))
        self.quit_action.setText(i18n.tr("menu_quit"))
        self.edit_menu.setTitle(i18n.tr("menu_edit"))
        self.undo_action.setText(i18n.tr("menu_undo"))
        self.redo_action.setText(i18n.tr("menu_redo"))
        self.copy_action.setText(i18n.tr("menu_edit_copy"))
        self.paste_action.setText(i18n.tr("menu_edit_paste"))
        self.rotate_right_action.setText(i18n.tr("menu_edit_rotate_right"))
        self.rotate_left_action.setText(i18n.tr("menu_edit_rotate_left"))
        self.delete_selection_action.setText(i18n.tr("menu_edit_delete") + "\t⌘⌫")
        self.language_menu.setTitle(i18n.tr("menu_language"))
        self.tools_menu.setTitle(i18n.tr("menu_tools"))
        for key, action in self.block_menu_actions.items():
            action.setText(i18n.tr(_BLOCK_MENU_LABEL_KEYS[key]))
        self.window_menu.setTitle(i18n.tr("menu_window"))
        self.window_close_action.setText(i18n.tr("menu_window_close") + "\t⌘W")
        self.window_left_panel_action.setText(i18n.tr("menu_window_left_panel") + "\tI")
        self.window_right_panel_action.setText(i18n.tr("menu_window_right_panel") + "\tO")
        self.window_thumbnails_action.setText(i18n.tr("menu_window_thumbnails") + "\tP")
        for name, label_key, shortcut, _source in _BUILT_IN_LAYOUT_PRESETS:
            self.builtin_layout_menus[name].setTitle(i18n.tr("menu_window_layout_prefix") + i18n.tr(label_key))
            self.builtin_layout_load_actions[name].setText(i18n.tr("layout_preset_load") + f"\t{shortcut}")
            self.builtin_layout_update_actions[name].setText(i18n.tr("layout_preset_update"))
        self.layout_preset_menu.setTitle(i18n.tr("menu_window_layout_preset"))
        self.save_layout_preset_action.setText(i18n.tr("menu_window_save_layout_preset"))
        self._rebuild_layout_preset_menu()
        self.reset_layout_action.setText(i18n.tr("menu_window_reset_layout"))
        self.help_menu.setTitle(i18n.tr("menu_help"))
        self.quickstart_action.setText(i18n.tr("menu_quickstart_action"))
        self.shortcuts_action.setText(i18n.tr("menu_shortcuts_action"))

        self.import_panel.retranslate_ui()
        self.independent_channels_title_label.setText(i18n.tr("independent_channels_group_title"))
        if not self.channels_disabled_label.isHidden():
            self.channels_disabled_label.setText(i18n.tr("channels_disabled_normal_mode"))
        self.auto_align_button.setText(i18n.tr("auto_align_button"))
        self.lock_label.setText(i18n.tr("lock_layer_position_label"))
        for i, label in enumerate(("R", "G", "B")):
            self.lock_buttons[i].setToolTip(i18n.tr(CHANNEL_KEY[label]))
        self.reset_all_alignment_button.setToolTip(i18n.tr("reset_all_alignment_tooltip"))
        self.reset_all_color_button.setToolTip(i18n.tr("reset_all_color_tooltip"))
        for panel in self.channel_panels:
            panel.retranslate_ui()
        self.light_panel.retranslate_ui()
        self.color_panel.retranslate_ui()
        self.crop_panel.retranslate_ui()
        self.curves_panel.retranslate_ui()
        self.histogram_title_label.setText(i18n.tr("menu_tools_histogram"))
        self.histogram.retranslate_ui()
        self.scan_panel.retranslate_ui()
        self.canvas.retranslate_ui()
        self.carousel.retranslate_ui()
        self.missing_files_banner.retranslate_ui()

        self.zoom_out_btn.setToolTip(i18n.tr("zoom_out"))
        self.zoom_in_btn.setToolTip(i18n.tr("zoom_in"))
        self.zoom_fit_btn.setToolTip(i18n.tr("zoom_fit_tooltip"))
        self.zoom_100_btn.setToolTip(i18n.tr("zoom_100"))
        self.rotate_left_btn.setToolTip(i18n.tr("rotate_left_tooltip"))
        self.rotate_right_btn.setToolTip(i18n.tr("rotate_right_tooltip"))
        self.compare_btn.setToolTip(i18n.tr("compare_tooltip"))
        self.compare_indicator.setText(i18n.tr("compare_indicator_label"))
        self.fullscreen_btn.setToolTip(
            i18n.tr("exit_fullscreen_button") if self._is_focus_mode else i18n.tr("fullscreen_button")
        )
        self.sort_btn.setToolTip(i18n.tr("sort_button_tooltip"))
        self.sort_action_filename.setText(i18n.tr("sort_by_filename"))
        self.sort_action_capture_date.setText(i18n.tr("sort_by_capture_date"))
        self.sort_action_import_order.setText(i18n.tr("sort_by_import_order"))
        self.sort_action_custom.setText(i18n.tr("sort_by_custom"))
        self.sort_action_reversed.setText(i18n.tr("sort_reverse_order"))
        self.grid_view_toggle_btn.setToolTip(i18n.tr("grid_view_toggle_tooltip"))
        self.carousel_toggle_btn.setToolTip(i18n.tr("carousel_toggle_tooltip"))

        self.new_session_toolbar_btn.setToolTip(i18n.tr("menu_new_session"))
        self.open_session_toolbar_btn.setToolTip(i18n.tr("menu_open_session"))
        self.import_toolbar_btn.setToolTip(i18n.tr("import_toolbar_tooltip"))
        self.left_panel_toggle_btn.setToolTip(i18n.tr("left_panel_toggle_tooltip"))
        self.save_session_toolbar_btn.setToolTip(i18n.tr("save_session_toolbar_tooltip"))
        self.export_toolbar_btn.setToolTip(i18n.tr("export_toolbar_tooltip"))
        self.trichrome_toolbar_btn.setToolTip(i18n.tr("trichrome_toolbar_tooltip"))
        self.settings_toolbar_btn.setToolTip(i18n.tr("settings_toolbar_tooltip"))
        self.crop_toolbar_btn.setToolTip(i18n.tr("crop_toolbar_tooltip"))
        self.scan_toolbar_btn.setToolTip(i18n.tr("scan_toolbar_tooltip"))
        self.right_panel_toggle_btn.setToolTip(i18n.tr("right_panel_toggle_tooltip"))
        self.help_toolbar_btn.setToolTip(i18n.tr("help_toolbar_tooltip"))
        self.quickstart_toolbar_action.setText(i18n.tr("menu_quickstart_action"))
        self.shortcuts_toolbar_action.setText(i18n.tr("menu_shortcuts_action"))
        self._update_session_name_label()

        if self.batch_window is not None:
            self.batch_window.retranslate_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.file_menu = self.menuBar().addMenu(i18n.tr("menu_file"))
        self.load_actions: list[QAction] = []
        for i in range(3):
            act = QAction(i18n.tr("menu_load_channel", channel=i18n.channel_name(i)), self)
            act.triggered.connect(lambda _checked=False, idx=i: self.load_image(idx))
            self.file_menu.addAction(act)
            self.load_actions.append(act)
        self.file_menu.addSeparator()
        self.new_session_action = QAction(i18n.tr("menu_new_session"), self)
        self.new_session_action.setShortcut(QKeySequence("Ctrl+N"))
        self.new_session_action.triggered.connect(self.action_new_session)
        self.file_menu.addAction(self.new_session_action)
        self.open_session_action = QAction(i18n.tr("menu_open_session"), self)
        self.open_session_action.setShortcut(QKeySequence("Ctrl+O"))
        self.open_session_action.triggered.connect(self.action_open_session)
        self.file_menu.addAction(self.open_session_action)
        self.save_session_action = QAction(i18n.tr("menu_save_session"), self)
        self.save_session_action.setShortcut(QKeySequence("Ctrl+S"))
        self.save_session_action.triggered.connect(self.action_save_session)
        self.file_menu.addAction(self.save_session_action)
        self.save_session_as_action = QAction(i18n.tr("menu_save_session_as"), self)
        self.save_session_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.save_session_as_action.triggered.connect(self.action_save_session_as)
        self.file_menu.addAction(self.save_session_as_action)
        self.file_menu.addSeparator()
        self.export_action = QAction(i18n.tr("export_button"), self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_action.triggered.connect(self.export_image)
        self.file_menu.addAction(self.export_action)
        self.file_menu.addSeparator()
        self.batch_action = QAction(i18n.tr("menu_batch"), self)
        self.batch_action.setShortcut(QKeySequence("Ctrl+I"))
        self.batch_action.triggered.connect(self.open_batch_window)
        self.file_menu.addAction(self.batch_action)
        self.file_menu.addSeparator()
        self.quit_action = QAction(i18n.tr("menu_quit"), self)
        self.quit_action.setShortcut(QKeySequence.Quit)
        self.quit_action.setMenuRole(QAction.QuitRole)
        self.quit_action.triggered.connect(self.close)
        self.file_menu.addAction(self.quit_action)

        self.edit_menu = self.menuBar().addMenu(i18n.tr("menu_edit"))
        self.undo_action = QAction(i18n.tr("menu_undo"), self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.triggered.connect(self.undo)
        self.undo_action.setEnabled(False)
        self.edit_menu.addAction(self.undo_action)
        self.redo_action = QAction(i18n.tr("menu_redo"), self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.redo_action.triggered.connect(self.redo)
        self.redo_action.setEnabled(False)
        self.edit_menu.addAction(self.redo_action)
        self.edit_menu.addSeparator()
        self.copy_action = QAction(i18n.tr("menu_edit_copy"), self)
        self.copy_action.setShortcut(QKeySequence.Copy)
        self.copy_action.triggered.connect(lambda: self.copy_settings_from(self.batch_current_index))
        self.edit_menu.addAction(self.copy_action)
        self.paste_action = QAction(i18n.tr("menu_edit_paste"), self)
        self.paste_action.setShortcut(QKeySequence.Paste)
        self.paste_action.triggered.connect(self.paste_settings_to_selected)
        self.paste_action.setEnabled(False)
        self.edit_menu.addAction(self.paste_action)
        self.edit_menu.addSeparator()
        self.rotate_right_action = QAction(i18n.tr("menu_edit_rotate_right"), self)
        self.rotate_right_action.setShortcut(QKeySequence("Ctrl+R"))
        self.rotate_right_action.triggered.connect(self.on_rotate_right)
        self.edit_menu.addAction(self.rotate_right_action)
        self.rotate_left_action = QAction(i18n.tr("menu_edit_rotate_left"), self)
        self.rotate_left_action.setShortcut(QKeySequence("Ctrl+L"))
        self.rotate_left_action.triggered.connect(self.on_rotate_left)
        self.edit_menu.addAction(self.rotate_left_action)
        self.edit_menu.addSeparator()
        self.delete_selection_action = QAction(self)
        # No QAction-level shortcut: unlike Copy/Paste/Undo/Redo, Qt's
        # QLineEdit doesn't claim Ctrl+Backspace (or any modified
        # Backspace/Delete combo) as its own via ShortcutOverride, so a real
        # global shortcut here would fire even while a text field is
        # focused and delete photos out from under the user's typing.
        # Handled in keyPressEvent instead, with the same focus guard as
        # Cmd+A; the shortcut text below is display-only.
        self.delete_selection_action.triggered.connect(
            lambda: self.delete_batch_items(self.carousel.selected_indices()))
        self.edit_menu.addAction(self.delete_selection_action)

        self.tools_menu = self.menuBar().addMenu(i18n.tr("menu_tools"))
        # 2026-09-04: lists every block individually (Files/Channels/
        # Histogram/Light/Color/Crop/Scan), not the old 4 tool-switcher
        # pairs - each a plain independent checkable toggle controlling
        # that one block's visibility (self.block_visible), synced with
        # its own header's close button via set_block_visible(). No
        # QActionGroup: unlike the old exclusive-pair tools, any number of
        # blocks can be shown at once now. Actual checked-state + the
        # toggled connection are wired in _connect_signals(), once
        # self.block_menu_actions exists (built at the end of _build_ui).
        self.block_menu_actions: dict[str, QAction] = {}
        for key in _ALL_BLOCK_KEYS:
            action = QAction(self, checkable=True)
            self.tools_menu.addAction(action)
            self.block_menu_actions[key] = action

        self.window_menu = self.menuBar().addMenu(i18n.tr("menu_window"))
        self.window_close_action = QAction(self)
        # No QAction-level shortcut: Cmd+W is already handled per-window by
        # a local QShortcut(QKeySequence.Close, ...) on each secondary
        # window (export_dialog.py/batch_window.py/the help QDialog below)
        # - deliberately not the main window itself. A second, menu-bar-
        # level binding of the same key sequence risks Qt shortcut
        # ambiguity between the two; the text below is display-only, same
        # convention as delete_selection_action above. This action's own
        # handler covers a mouse click on the menu item itself.
        self.window_close_action.triggered.connect(self._close_active_window)
        self.window_menu.addAction(self.window_close_action)
        self.window_menu.addSeparator()
        # Checkable, mirroring left_panel_toggle_btn/right_panel_toggle_btn/
        # carousel_toggle_btn - those don't exist yet at this point in
        # _build_ui (built later, in _build_top_toolbar/further down here),
        # so the actual cross-wiring (initial checked state + bidirectional
        # sync with the toolbar buttons) happens in _connect_signals()
        # instead, same reason settings_toolbar_btn/crop_toolbar_btn's
        # panel-visibility wiring is deferred there too.
        self.window_left_panel_action = QAction(self, checkable=True)
        self.window_menu.addAction(self.window_left_panel_action)
        self.window_right_panel_action = QAction(self, checkable=True)
        self.window_menu.addAction(self.window_right_panel_action)
        self.window_thumbnails_action = QAction(self, checkable=True)
        self.window_menu.addAction(self.window_thumbnails_action)
        self.window_menu.addSeparator()

        # The 4 built-in default-layout presets, listed directly in the
        # Window menu (not nested in the Layout Preset submenu below) -
        # each one is its own small submenu (Load + Update, no Delete -
        # 2026-09-04, the user asked for Update to be added here too,
        # matching a custom preset's own submenu shape minus the ability
        # to remove a reserved slot entirely). Load mirrors one of the top
        # toolbar's Trichrome/Color Correction/Crop/Scan buttons -
        # triggering either goes through the same _activate_default_layout(),
        # so the toolbar's exclusive checked state stays in sync regardless
        # of which one was used. Update re-saves the *current* layout into
        # that slot's underlying source preset (_BUILT_IN_LAYOUT_SOURCE,
        # e.g. "Trichrome" -> "NewTrichrome") - the same effect as finding
        # that preset under Layout Preset and clicking its own Update, just
        # reachable directly from the slot the user actually thinks of it
        # by ("update the Trichrome layout").
        self.builtin_layout_menus: dict[str, QMenu] = {}
        self.builtin_layout_load_actions: dict[str, QAction] = {}
        self.builtin_layout_update_actions: dict[str, QAction] = {}
        for name, _label_key, _shortcut, source in _BUILT_IN_LAYOUT_PRESETS:
            submenu = QMenu(self.window_menu)
            load_action = QAction(submenu)
            load_action.triggered.connect(lambda _checked=False, n=name: self._activate_default_layout(n))
            submenu.addAction(load_action)
            update_action = QAction(submenu)
            update_action.triggered.connect(lambda _checked=False, src=source: self._save_layout_preset(src))
            submenu.addAction(update_action)
            self.window_menu.addMenu(submenu)
            self.builtin_layout_menus[name] = submenu
            self.builtin_layout_load_actions[name] = load_action
            self.builtin_layout_update_actions[name] = update_action
        self.window_menu.addSeparator()

        # Layout Preset: save/restore a full named layout snapshot (panel
        # visibility, which side each tool lives on, which tool is active
        # per side, and the left/right block order) - see
        # _capture_layout_state/_apply_layout_state and
        # _save_layout_preset/_load_layout_preset/_delete_layout_preset.
        # Persisted via QSettings only (not part of .trirgb) since presets
        # are a personal, cross-session arrangement library, not project
        # file content. self._layout_preset_names is loaded in __init__.
        self.layout_preset_menu = self.window_menu.addMenu(i18n.tr("menu_window_layout_preset"))
        self.save_layout_preset_action = QAction(self)
        self.save_layout_preset_action.triggered.connect(self.on_save_layout_preset)
        self.layout_preset_menu.addAction(self.save_layout_preset_action)
        self._layout_preset_separator = self.layout_preset_menu.addSeparator()
        self._rebuild_layout_preset_menu()

        # Reset Layout sits directly below Layout Preset, no separator
        # between them (2026-09-04, per the user's explicit request) - the
        # separator above (before the 4 built-in layout submenus) still
        # marks the start of the whole "layout" section of the menu; tool
        # panels can now be reordered directly by dragging a block's
        # header (BlockHeaderBar/BlockReorderZone) instead of via a menu
        # action, so the old per-tool "move to left/right panel" actions
        # were removed (2026-09-03) and Reset Layout is the one remaining
        # fixed-arrangement action left in this section.
        self.reset_layout_action = QAction(self)
        self.reset_layout_action.triggered.connect(self.reset_layout)
        self.window_menu.addAction(self.reset_layout_action)

        self.help_menu = self.menuBar().addMenu(i18n.tr("menu_help"))
        self.quickstart_action = QAction(i18n.tr("menu_quickstart_action"), self)
        self.quickstart_action.triggered.connect(self.show_quickstart_dialog)
        self.help_menu.addAction(self.quickstart_action)
        self.shortcuts_action = QAction(i18n.tr("menu_shortcuts_action"), self)
        self.shortcuts_action.triggered.connect(self.show_shortcuts_dialog)
        self.help_menu.addAction(self.shortcuts_action)
        self.help_menu.addSeparator()

        # Language selection, in the Help menu (2026-09-04) - moved here
        # after relocating it into the native macOS Application menu (via
        # menuAction().setMenuRole(QAction.ApplicationSpecificRole), see
        # git history) turned out not to actually work in the real built
        # .app, confirmed by the user - Qt's Cocoa menu-role merging only
        # reliably relocates flat leaf QActions (About/Preferences/Quit-
        # style singletons), not a whole submenu with children. Rather
        # than gamble on a second unverifiable native-menu trick, this
        # uses the same ordinary QMenu nesting every other menu in the app
        # already relies on (Tools, Window, ...), which is known to work.
        self.language_menu = self.help_menu.addMenu(i18n.tr("menu_language"))
        lang_group = QActionGroup(self)
        lang_group.setExclusive(True)
        act_en = QAction("English", self, checkable=True)
        act_fr = QAction("Français", self, checkable=True)
        act_en.setChecked(i18n.current_language() == "en")
        act_fr.setChecked(i18n.current_language() == "fr")
        act_en.triggered.connect(lambda: self.change_language("en"))
        act_fr.triggered.connect(lambda: self.change_language("fr"))
        for act in (act_en, act_fr):
            lang_group.addAction(act)
            self.language_menu.addAction(act)

        fullscreen_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        fullscreen_shortcut.activated.connect(self.toggle_focus_mode)
        help_shortcut = QShortcut(QKeySequence("F1"), self)
        help_shortcut.activated.connect(self.show_quickstart_dialog)

        self._build_top_toolbar()

        self.import_panel = ImportPanel()
        self.import_panel.load_requested.connect(self.load_image)
        self.import_panel.mode_change_requested.connect(self.on_import_mode_change_requested)
        self.import_panel.load_normal_requested.connect(self.load_normal_image)
        self.import_panel.harris_shutter_toggled.connect(self.on_harris_shutter_toggled)

        self.channel_panels = [ChannelPanel(layer.label) for layer in self.layers]
        self.independent_channels_group = QGroupBox()
        independent_channels_outer, independent_channels_header, self.independent_channels_title_label = (
            start_block_chrome(self.independent_channels_group, "channels", "independent_channels_group_title"))
        # Same "?" scope-info convention as Light/Color's own
        # scope_info_button (2026-09-04, added here per the user's
        # explicit request - "ajoute le même bouton pour l'outil RGB
        # Channels").
        self.channels_scope_info_button = InfoButton("channels_scope_info")
        independent_channels_header.addWidget(self.channels_scope_info_button)
        independent_channels_header.addStretch(1)
        self.reset_all_alignment_button = SvgToolButton(
            "Tools/Trichrome Process/reset_alignment.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.reset_all_alignment_button.clicked.connect(self.on_reset_all_alignment)
        independent_channels_header.addWidget(self.reset_all_alignment_button)
        self.reset_all_color_button = SvgToolButton(
            "Tools/Trichrome Process/reset_settings.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.reset_all_color_button.clicked.connect(self.on_reset_all_color)
        independent_channels_header.addWidget(self.reset_all_color_button)
        (self.independent_channels_body, independent_channels_layout,
         self.channels_collapse_button, self.channels_close_button) = finish_block_chrome(
            independent_channels_outer, independent_channels_header)
        # Every block widget exposes .body (set_block_collapsed's contract)
        # - the class-based panels (ImportPanel/LightPanel/etc.) set this on
        # themselves; these 3 inline-built blocks need it set explicitly.
        self.independent_channels_group.body = self.independent_channels_body

        # Shown at the very top of the block, in place of everything below
        # it, while the active photo is in Normal mode - see
        # _sync_channels_panel_availability/set_block_disabled.
        self.channels_disabled_label = make_disabled_message_label()
        independent_channels_layout.addWidget(self.channels_disabled_label)

        # Lock Layer Position + Auto Align (moved here from the Files block,
        # 2026-09-04, per the user's explicit request - they only ever
        # applied to the 3 trichrome channels this block itself controls,
        # not to Files' own load-image concerns). Auto Align sits below
        # Lock (2026-09-04 follow-up) since which channel is locked is what
        # Auto Align aligns the other two against - picking a lock target
        # naturally reads as the step before running it.
        lock_row = QHBoxLayout()
        self.lock_label = QLabel()
        lock_row.addWidget(self.lock_label)
        self.lock_buttons: list[SvgLetterToggleButton] = []
        self.lock_group = QButtonGroup(self)
        self.lock_group.setExclusive(True)
        for i, label in enumerate(("R", "G", "B")):
            color = CHANNEL_COLORS.get(label, "#888")
            btn = SvgLetterToggleButton(label, color, size=(32, 28), icon_size=22)
            btn.toggled.connect(lambda checked, idx=i: self.on_reference_toggled(idx, True) if checked else None)
            self.lock_group.addButton(btn)
            lock_row.addWidget(btn)
            self.lock_buttons.append(btn)
        lock_row.addStretch(1)
        self.lock_info_button = InfoButton("lock_layer_position_info")
        lock_row.addWidget(self.lock_info_button)
        independent_channels_layout.addLayout(lock_row)

        self.auto_align_button = QPushButton()
        self.auto_align_button.clicked.connect(self.on_auto_align_all)
        independent_channels_layout.addWidget(self.auto_align_button)

        for panel in self.channel_panels:
            independent_channels_layout.addWidget(panel)

        # Scan is a first-class block like every other one (grip/collapse/
        # close/title) - 2026-09-04, the placeholder body that used to sit
        # here replaced with the real ScanPanel, ported over from the
        # standalone trichrome.scan_tool package (kept alive there too, for
        # separate beta testing per the user's explicit request).
        self.scan_panel = ScanPanel()

        # left_container/right_container (below) are BlockReorderZone
        # instances holding every block assigned to that side directly -
        # see the block-system state (self.block_side/_visible/_collapsed,
        # self.left_block_order/right_block_order) and _apply_block_layout.
        self.left_container = BlockReorderZone()
        self.left_layout = QVBoxLayout(self.left_container)
        self.left_layout.addStretch(1)
        self.left_container.block_dropped.connect(lambda key, idx: self._on_block_dropped("left", key, idx))
        self.left_scroll = ArrowKeyScrollArea()
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setWidget(self.left_container)
        self.left_scroll.setMinimumWidth(_SIDE_PANEL_MIN_WIDTH)
        self.left_scroll.setMaximumWidth(_SIDE_PANEL_MAX_WIDTH)
        # Only ever scrolls vertically - block content must fit the
        # column's width, not spill sideways (2026-09-04 fix - this one
        # was missed when right_scroll got the same policy earlier; blocks
        # must adapt to the panel's width, never the other way around).
        self.left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.canvas = CanvasWidget()

        self.zoom_out_btn = SvgToolButton("Filmstrip/zoom_out.svg")
        self.zoom_in_btn = SvgToolButton("Filmstrip/zoom_in.svg")
        self.zoom_fit_btn = SvgToolButton("Filmstrip/fit_screen.svg")
        self.zoom_100_btn = SvgToolButton("Filmstrip/view_real_size.svg")
        self.zoom_out_btn.clicked.connect(self.on_zoom_out_clicked)
        self.zoom_in_btn.clicked.connect(self.on_zoom_in_clicked)
        self.zoom_fit_btn.clicked.connect(self.canvas.zoom_fit)
        self.zoom_100_btn.clicked.connect(self.canvas.zoom_100)

        self.rotate_left_btn = RotateLeftButton()
        self.rotate_left_btn.clicked.connect(self.on_rotate_left)

        self.rotate_right_btn = RotateRightButton()
        self.rotate_right_btn.clicked.connect(self.on_rotate_right)

        self.compare_btn = CompareButton()

        self.fullscreen_btn = FullscreenToggleButton()
        self.fullscreen_btn.clicked.connect(self.toggle_focus_mode)

        self.sort_btn = SortButton()
        self.sort_menu = QMenu(self.sort_btn)
        self.sort_field_group = QActionGroup(self.sort_menu)
        self.sort_field_group.setExclusive(True)
        self.sort_action_filename = QAction(checkable=True)
        self.sort_action_capture_date = QAction(checkable=True)
        self.sort_action_import_order = QAction(checkable=True)
        self.sort_action_custom = QAction(checkable=True)
        self._sort_field_actions = {
            "filename": self.sort_action_filename,
            "capture_date": self.sort_action_capture_date,
            "import_order": self.sort_action_import_order,
            "custom": self.sort_action_custom,
        }
        for mode, act in self._sort_field_actions.items():
            act.triggered.connect(lambda _checked=False, m=mode: self.set_sort_mode(m))
            self.sort_field_group.addAction(act)
            self.sort_menu.addAction(act)
        self.sort_menu.addSeparator()
        self.sort_action_reversed = QAction(checkable=True)
        self.sort_action_reversed.triggered.connect(self.set_sort_reversed)
        self.sort_menu.addAction(self.sort_action_reversed)
        self.sort_btn.setMenu(self.sort_menu)

        self.grid_view_toggle_btn = SvgCheckableToolButton("Filmstrip/grid-3x3.svg", icon_size=14)
        self.grid_view_toggle_btn.toggled.connect(self.on_grid_view_toggled)

        self.carousel_toggle_btn = FilmstripToggleButton()
        self.carousel_toggle_btn.toggled.connect(self._on_carousel_toggle_btn)

        # A hairline divider between the per-photo actions (rotate, compare)
        # and the display/view actions (fullscreen, sort, thumbnails).
        bar_separator = QWidget()
        bar_separator.setFixedSize(1, 16)
        bar_separator.setStyleSheet("background-color: rgba(128, 128, 128, 90);")

        self.compare_indicator = QLabel()
        self.compare_indicator.setStyleSheet("color: #f2c40c; font-weight: 600; font-size: 11px;")
        self.compare_indicator.setVisible(False)

        bottom_bar = QWidget()
        bottom_bar_layout = QHBoxLayout(bottom_bar)
        bottom_bar_layout.setContentsMargins(6, 4, 6, 4)
        for btn in (self.zoom_out_btn, self.zoom_in_btn, self.zoom_fit_btn, self.zoom_100_btn):
            bottom_bar_layout.addWidget(btn)
        bottom_bar_layout.addStretch(1)
        bottom_bar_layout.addWidget(self.compare_indicator)
        bottom_bar_layout.addStretch(1)
        bottom_bar_layout.addWidget(self.rotate_left_btn)
        bottom_bar_layout.addWidget(self.rotate_right_btn)
        bottom_bar_layout.addWidget(self.compare_btn)
        bottom_bar_layout.addSpacing(4)
        bottom_bar_layout.addWidget(bar_separator)
        bottom_bar_layout.addSpacing(4)
        bottom_bar_layout.addWidget(self.fullscreen_btn)
        bottom_bar_layout.addWidget(self.sort_btn)
        bottom_bar_layout.addWidget(self.grid_view_toggle_btn)
        bottom_bar_layout.addWidget(self.carousel_toggle_btn)

        self.carousel = CarouselWidget()
        self.carousel.setVisible(False)
        self.carousel.current_changed.connect(self.activate_batch_item)
        self.carousel.selection_changed.connect(self.on_carousel_selection_changed)
        self.carousel.copy_requested.connect(self.copy_settings_from)
        self.carousel.paste_requested.connect(self.paste_settings_to)
        self.carousel.paste_crop_requested.connect(self.paste_crop_to)
        self.carousel.delete_requested.connect(self.delete_batch_items)
        self.carousel.reset_requested.connect(self.reset_batch_items)
        self.carousel.duplicate_requested.connect(self.duplicate_batch_item)
        self.carousel.reordered.connect(self.on_carousel_reordered)
        self.carousel.files_dropped.connect(self.on_carousel_files_dropped)
        self.scan_panel.add_to_session_requested.connect(self.on_scan_add_to_session_requested)
        self.scan_panel.pick_film_base_from_photo_toggled.connect(self.on_pick_film_base_from_photo_toggled)
        self.scan_panel.apply_film_base_requested.connect(self.on_apply_film_base_requested)

        self.missing_files_banner = MissingFilesBanner()
        self.missing_files_banner.locate_clicked.connect(self.on_locate_missing_files)

        # Grid mode (the "Grid" toolbar button) reparents self.carousel
        # itself into preview_stack, in place of self.canvas, instead of
        # using a second widget - see on_grid_view_toggled(). Only
        # self.canvas lives here at construction time; self.carousel is
        # added/removed dynamically as its mode toggles.
        self.preview_stack = QStackedWidget()
        self.preview_stack.addWidget(self.canvas)

        canvas_container = QWidget()
        canvas_layout = QVBoxLayout(canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        canvas_layout.addWidget(self.missing_files_banner)
        canvas_layout.addWidget(self.preview_stack, stretch=1)
        # self.carousel sits ABOVE bottom_bar (not below it) so bottom_bar -
        # zoom/rotate/compare/fullscreen/sort/grid/thumbnails-toggle - stays
        # pinned to the true bottom edge of the preview window at all times,
        # regardless of whether the filmstrip strip is shown/hidden below
        # it. on_grid_view_toggled() must preserve this order when it
        # reparents self.carousel back out of preview_stack.
        canvas_layout.addWidget(self.carousel)
        canvas_layout.addWidget(bottom_bar)
        self.canvas_container = canvas_container
        self.canvas_layout = canvas_layout
        self.bottom_bar = bottom_bar

        # Title added 2026-09-04 (had been left off on purpose in earlier
        # passes - the user changed their mind and asked for it back).
        self.histogram = HistogramPanel()
        self.histogram_box = QGroupBox()
        histogram_outer, histogram_header, self.histogram_title_label = start_block_chrome(
            self.histogram_box, "histogram", "menu_tools_histogram")
        (self.histogram_body, histogram_body_layout,
         self.histogram_collapse_button, self.histogram_close_button) = finish_block_chrome(
            histogram_outer, histogram_header)
        self.histogram_box.body = self.histogram_body
        histogram_body_layout.addWidget(self.histogram)

        self.light_panel = LightPanel()
        self.color_panel = ColorPanel()
        self.crop_panel = CropPanel()
        self.curves_panel = CurvesPanel()

        self.right_container = BlockReorderZone()
        self.right_layout = QVBoxLayout(self.right_container)
        self.right_layout.addStretch(1)
        self.right_container.block_dropped.connect(lambda key, idx: self._on_block_dropped("right", key, idx))

        self.right_scroll = ArrowKeyScrollArea()
        self.right_scroll.setWidgetResizable(True)
        self.right_scroll.setWidget(self.right_container)
        self.right_scroll.setMinimumWidth(_SIDE_PANEL_MIN_WIDTH)
        self.right_scroll.setMaximumWidth(_SIDE_PANEL_MAX_WIDTH)
        # Only ever scrolls vertically - content must fit the column's width,
        # not spill sideways into a horizontal scrollbar.
        self.right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.left_scroll)
        self.splitter.addWidget(canvas_container)
        self.splitter.addWidget(self.right_scroll)
        self.splitter.setStretchFactor(1, 1)

        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 10, 0, 0)
        central_layout.addWidget(self.splitter)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())
        self.session_name_label = QLabel()
        # Right padding so the label doesn't sit flush against the window's
        # edge - most noticeable right after New Session/Open Session, when
        # its text changes and draws the eye.
        self.session_name_label.setStyleSheet("color: #888; padding-right: 10px;")
        self.statusBar().addPermanentWidget(self.session_name_label)

        # Registry mapping every block key to its widget/collapse-button/
        # close-button, built here (end of _build_ui) since every block now
        # exists - the one lookup table the whole block system is built on.
        self.block_widgets: dict[str, QWidget] = {
            "files": self.import_panel,
            "channels": self.independent_channels_group,
            "histogram": self.histogram_box,
            "light": self.light_panel,
            "color": self.color_panel,
            "crop": self.crop_panel,
            "scan": self.scan_panel,
            "curves": self.curves_panel,
        }
        self.block_collapse_buttons: dict[str, SvgToolButton] = {
            "files": self.import_panel.collapse_button,
            "channels": self.channels_collapse_button,
            "histogram": self.histogram_collapse_button,
            "light": self.light_panel.collapse_button,
            "color": self.color_panel.collapse_button,
            "crop": self.crop_panel.collapse_button,
            "scan": self.scan_panel.collapse_button,
            "curves": self.curves_panel.collapse_button,
        }
        self.block_close_buttons: dict[str, SvgToolButton] = {
            "files": self.import_panel.close_button,
            "channels": self.channels_close_button,
            "histogram": self.histogram_close_button,
            "light": self.light_panel.close_button,
            "color": self.color_panel.close_button,
            "crop": self.crop_panel.close_button,
            "scan": self.scan_panel.close_button,
            "curves": self.curves_panel.close_button,
        }
        for key, btn in self.block_collapse_buttons.items():
            btn.clicked.connect(lambda _checked=False, k=key: self._toggle_block_collapsed(k))
        for key, btn in self.block_close_buttons.items():
            btn.clicked.connect(lambda _checked=False, k=key: self.set_block_visible(k, False))

        self._apply_block_layout()
        self.retranslate_ui()
        self._update_carousel_visibility()

    # Button height == the toolbar's total height on purpose: QToolBar's
    # internal layout top-anchors children within any extra vertical space
    # it's given (setContentsMargins/setFixedHeight/layout alignment on the
    # QToolBar itself don't change that - confirmed empirically, independent
    # of the earlier unified-title-bar issue). Giving buttons the toolbar's
    # full height sidesteps that entirely: there's no leftover space for
    # QToolBar to mis-place, and each SvgToolButton centers its own icon
    # within its own box in paintEvent, which we do control.
    _TOP_TOOLBAR_HEIGHT = 30
    _TOP_TOOLBAR_BTN_SIZE = (32, _TOP_TOOLBAR_HEIGHT)
    _TOP_TOOLBAR_ICON_SIZE = 24

    def _build_top_toolbar(self) -> None:
        """A regular (non-unified) toolbar sitting below the native title
        bar, mirroring the bottom bar's borderless SVG icon-button style.
        Left cluster: toggle-left-panel + save session +
        import. Right cluster: export, toggle-right-panel, help (Quick
        Start / Shortcuts).

        Deliberately NOT merged into the title bar via
        setUnifiedTitleAndToolBarOnMac: once bridged to Cocoa's native
        unified toolbar, the real on-screen layout (vertical centering,
        symmetric side margins) is entirely decided by AppKit and ignores
        every Qt-side lever. Staying with a plain QToolBar trades the
        seamless blend with the traffic lights for actual pixel control
        over spacing.
        """
        self.top_toolbar = QToolBar()
        self.top_toolbar.setMovable(False)
        self.top_toolbar.setFloatable(False)
        self.top_toolbar.setStyleSheet(
            "QToolBar { border: none; "
            "border-top: 1px solid rgba(128, 128, 128, 90); "
            "spacing: 2px; padding: 0px; }"
        )
        # 0, not 10px side margins: QToolBar's layout doesn't apply
        # contentsMargins per-edge to its children - it only folds the total
        # into its own size hint and dumps the leftover space at the trailing
        # end, which is what caused the left/right asymmetry. Real fixed-
        # width spacer widgets (below) are used instead for guaranteed,
        # symmetric edge spacing.
        self.top_toolbar.setContentsMargins(0, 0, 0, 0)
        self.addToolBar(Qt.TopToolBarArea, self.top_toolbar)

        btn_kwargs = dict(size=self._TOP_TOOLBAR_BTN_SIZE, icon_size=self._TOP_TOOLBAR_ICON_SIZE)

        self.new_session_toolbar_btn = SvgToolButton("Toolbar/file-new.svg", **btn_kwargs)
        self.new_session_toolbar_btn.clicked.connect(self.action_new_session)

        self.open_session_toolbar_btn = SvgToolButton("Toolbar/file-open.svg", **btn_kwargs)
        self.open_session_toolbar_btn.clicked.connect(self.action_open_session)

        self.save_session_toolbar_btn = SvgToolButton("Toolbar/save.svg", **btn_kwargs)
        self.save_session_toolbar_btn.clicked.connect(self.action_save_session)

        self.import_toolbar_btn = SvgToolButton("Toolbar/image-plus.svg", **btn_kwargs)
        self.import_toolbar_btn.clicked.connect(self.open_batch_window)

        self.export_toolbar_btn = SvgToolButton("Toolbar/Export.svg", **btn_kwargs)
        self.export_toolbar_btn.clicked.connect(self.export_image)

        self.left_panel_toggle_btn = SvgTwoStateToggleButton(
            "Toolbar/panel-left-close.svg", "Toolbar/panel-left-open.svg", **btn_kwargs)
        self.left_panel_toggle_btn.toggled.connect(self.on_left_panel_toggled)

        self.right_panel_toggle_btn = SvgTwoStateToggleButton(
            "Toolbar/panel-right-close.svg", "Toolbar/panel-right-open.svg", **btn_kwargs)
        self.right_panel_toggle_btn.toggled.connect(self.on_right_panel_toggled)

        # "?" button: a menu rather than a single action, since it now
        # covers both the quick-start guide and the shortcuts reference.
        # A distinct attribute name from self.help_menu (the real menu-bar
        # Help menu, built earlier in _build_ui) - the two used to share
        # the name "help_menu", silently reassigning it here and leaving
        # retranslate_ui's self.help_menu.setTitle(...) call retitling
        # this popup instead of the real menu-bar entry (a harmless no-op,
        # since a popup QMenu has no visible title bar of its own, but the
        # real Help menu-bar label then never actually got retranslated on
        # a language switch) - fixed 2026-09-04 while touching this area
        # for the Language-menu relocation.
        self.help_toolbar_btn = SvgToolButton("Toolbar/help.svg", **btn_kwargs)
        self.help_toolbar_btn.setPopupMode(QToolButton.InstantPopup)
        self.help_toolbar_menu = QMenu(self.help_toolbar_btn)
        self.quickstart_toolbar_action = QAction(self)
        self.quickstart_toolbar_action.triggered.connect(self.show_quickstart_dialog)
        self.help_toolbar_menu.addAction(self.quickstart_toolbar_action)
        self.shortcuts_toolbar_action = QAction(self)
        self.shortcuts_toolbar_action.triggered.connect(self.show_shortcuts_dialog)
        self.help_toolbar_menu.addAction(self.shortcuts_toolbar_action)
        self.help_toolbar_btn.setMenu(self.help_toolbar_menu)

        # Default-layout quick-switch buttons (Trichrome/Color Correction/
        # Crop/Scan), re-purposed 2026-09-04 - now that layout is fully
        # customizable (the block system above), these 4 no longer toggle
        # a fixed tool panel's visibility; each instead loads whichever
        # custom preset _BUILT_IN_LAYOUT_SOURCE maps its display name to
        # (see _BUILT_IN_LAYOUT_PRESETS) via _activate_default_layout(). A
        # single exclusive QButtonGroup across all 4 (not two independent
        # pairs like the old tool-switcher) - only one default layout
        # reads as "active" (full color) at a time, the rest dimmed, per
        # the user's explicit ask.
        self.trichrome_toolbar_btn = SvgCheckableToolButton("Toolbar/trichrome.svg", **btn_kwargs)
        self.trichrome_toolbar_btn.setChecked(True)
        self.settings_toolbar_btn = SvgCheckableToolButton("Toolbar/horizontal_sliders.svg", **btn_kwargs)
        self.crop_toolbar_btn = SvgCheckableToolButton("Global/crop.svg", **btn_kwargs)
        self.scan_toolbar_btn = SvgCheckableToolButton("Toolbar/camera-plus.svg", **btn_kwargs)
        self.default_layout_group = QButtonGroup(self)
        self.default_layout_group.setExclusive(True)
        for btn in (
            self.trichrome_toolbar_btn, self.settings_toolbar_btn, self.crop_toolbar_btn, self.scan_toolbar_btn,
        ):
            self.default_layout_group.addButton(btn)
        # Maps each built-in preset name to its toolbar button, so
        # _activate_default_layout() can sync the exclusive checked state
        # regardless of which of the 3 entry points (toolbar click, bare
        # keyboard shortcut, Window menu item) triggered it.
        self._default_layout_buttons = {
            "Trichrome": self.trichrome_toolbar_btn,
            "Color Correction": self.settings_toolbar_btn,
            "Crop": self.crop_toolbar_btn,
            "Scan": self.scan_toolbar_btn,
        }
        for name, btn in self._default_layout_buttons.items():
            btn.clicked.connect(lambda _checked=False, n=name: self._activate_default_layout(n))

        # Split into two expanding halves with the status label between them,
        # so the label sits centered regardless of window width.
        toolbar_spacer_left = QWidget()
        toolbar_spacer_left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar_spacer_right = QWidget()
        toolbar_spacer_right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.save_status_label = QLabel()
        self.save_status_label.setStyleSheet("color: #f2c40c; font-weight: 600; font-size: 11px;")
        self.save_status_label.setVisible(False)

        # -2px: the toolbar's own 2px inter-item spacing (QSS "spacing")
        # still applies next to these, so the visible gap ends up exactly 10px.
        left_edge_spacer = QWidget()
        left_edge_spacer.setFixedWidth(8)
        right_edge_spacer = QWidget()
        right_edge_spacer.setFixedWidth(8)

        self.top_toolbar.addWidget(left_edge_spacer)
        self.top_toolbar.addWidget(self.new_session_toolbar_btn)
        self.top_toolbar.addWidget(self.open_session_toolbar_btn)
        self.top_toolbar.addWidget(self.save_session_toolbar_btn)
        self.top_toolbar.addWidget(self.import_toolbar_btn)
        self.top_toolbar.addWidget(toolbar_spacer_left)
        self.top_toolbar.addWidget(self.trichrome_toolbar_btn)
        self.top_toolbar.addWidget(self.settings_toolbar_btn)
        self.top_toolbar.addWidget(self.crop_toolbar_btn)
        self.top_toolbar.addWidget(self.scan_toolbar_btn)
        self.top_toolbar.addWidget(self.save_status_label)
        self.top_toolbar.addWidget(toolbar_spacer_right)
        self.top_toolbar.addWidget(self.export_toolbar_btn)
        self.top_toolbar.addWidget(self.left_panel_toggle_btn)
        self.top_toolbar.addWidget(self.right_panel_toggle_btn)
        self.top_toolbar.addWidget(self.help_toolbar_btn)
        self.top_toolbar.addWidget(right_edge_spacer)

    def on_left_panel_toggled(self, visible: bool) -> None:
        self.left_scroll.setVisible(visible)

    def on_right_panel_toggled(self, visible: bool) -> None:
        self.right_scroll.setVisible(visible)

    def _close_active_window(self) -> None:
        """The Window menu's "Close Window" - same effect as the existing
        per-window Cmd+W shortcuts (see window_close_action above),
        reachable by clicking the menu item too. Deliberately a no-op when
        the main window itself is active, matching that same policy."""
        active = QApplication.activeWindow()
        if active is not None and active is not self:
            active.close()

    # ------------------------------------------------------------------
    # Block system (2026-09-04) - which side panel each block lives in,
    # its position there, and its visible/collapsed state. Freely
    # reassignable at runtime via drag (BlockReorderZone/_on_block_dropped),
    # the collapse/close buttons on each block's own header, and the Tools
    # menu; see _DEFAULT_BLOCK_SIDE/_DEFAULT_BLOCK_VISIBLE/
    # _DEFAULT_LEFT_BLOCK_ORDER/_DEFAULT_RIGHT_BLOCK_ORDER for the fallback
    # shape restored by Window > Reset Layout.
    # ------------------------------------------------------------------
    def _apply_block_layout(self) -> None:
        """Rebuilds left_layout/right_layout from block_side/block_visible/
        left_block_order/right_block_order - the single place block-system
        state turns into actual on-screen layout. Called after every
        drag-drop, visibility toggle, reset, and layout restore."""
        for side, layout, order in (
            ("left", self.left_layout, self.left_block_order),
            ("right", self.right_layout, self.right_block_order),
        ):
            for key in order:
                widget = self.block_widgets.get(key)
                if widget is not None:
                    layout.removeWidget(widget)
            for i, key in enumerate(order):
                widget = self.block_widgets.get(key)
                if widget is None:
                    continue
                layout.insertWidget(i, widget)
                widget.setVisible(self.block_visible.get(key, True) and self.block_side.get(key) == side)

        self.left_container.set_block_widgets(
            {k: w for k, w in self.block_widgets.items() if self.block_side.get(k) == "left"})
        self.right_container.set_block_widgets(
            {k: w for k, w in self.block_widgets.items() if self.block_side.get(k) == "right"})

        for key, action in self.block_menu_actions.items():
            action.blockSignals(True)
            action.setChecked(self.block_visible.get(key, True))
            action.blockSignals(False)

        # Force both scroll areas to re-evaluate their contained widget's
        # width against the viewport - without this, a block moved by
        # drag (removeWidget/insertWidget, not a real user resize) could
        # leave a stale cached size behind, and the "no horizontal
        # scrollbar" fix would silently stop applying after a drag
        # (2026-09-04 feedback: "lorsque l'on déplace les blocs, cette
        # adaptation n'est plus prise en compte").
        for layout in (self.left_layout, self.right_layout):
            layout.invalidate()
            layout.activate()
        for container in (self.left_container, self.right_container):
            container.updateGeometry()

    def _on_block_dropped(self, target_side: str, dragged_key: str, insert_index: int) -> None:
        """A block was dropped in the target_side zone (left_container or
        right_container) at insert_index among that zone's own currently-
        visible blocks (excluding the dragged one). Works uniformly for a
        same-panel reorder and a cross-panel move - target_side may or may
        not be the block's current side."""
        if dragged_key not in self.block_widgets:
            return
        old_side = self.block_side.get(dragged_key)
        if old_side is None:
            return
        old_order = self.left_block_order if old_side == "left" else self.right_block_order
        if dragged_key in old_order:
            old_order.remove(dragged_key)

        target_order = self.left_block_order if target_side == "left" else self.right_block_order
        self.block_side[dragged_key] = target_side
        visible_in_target = [
            k for k in target_order
            if k != dragged_key and self.block_visible.get(k, True) and self.block_side.get(k) == target_side
        ]
        if 0 <= insert_index < len(visible_in_target):
            pos = target_order.index(visible_in_target[insert_index])
        else:
            pos = len(target_order)
        target_order.insert(pos, dragged_key)
        self._apply_block_layout()

    def _toggle_block_collapsed(self, key: str) -> None:
        self.block_collapsed[key] = not self.block_collapsed.get(key, False)
        widget = self.block_widgets.get(key)
        if widget is not None:
            set_block_collapsed(widget.body, self.block_collapse_buttons[key], self.block_collapsed[key])

    def set_block_visible(self, key: str, visible: bool) -> None:
        """Shows/hides one block - its own header's close button and the
        Tools menu's checkable action for it both funnel through here, so
        the two stay in sync regardless of which one the user used.
        Re-showing a block restores it at wherever it already sits in its
        side's order list (hidden blocks keep their slot, never removed
        from the order - only _on_block_dropped changes position)."""
        self.block_visible[key] = visible
        widget = self.block_widgets.get(key)
        if widget is not None:
            widget.setVisible(visible)
        if key == "crop" and not visible and self._crop_active:
            # Hiding the Crop block while active crop mode is armed would
            # leave a live canvas overlay with no panel to interact with -
            # fold active mode off too (same as Escape), just reached via
            # the close button/Tools menu instead of the keyboard. This
            # does NOT run the other way: showing the block never arms
            # active mode on its own (2026-09-04) - see _set_crop_active.
            self._set_crop_active(False)
        action = self.block_menu_actions.get(key)
        if action is not None:
            action.blockSignals(True)
            action.setChecked(visible)
            action.blockSignals(False)

    def reset_layout(self) -> None:
        """Window > Reset Layout - the one default configuration: Files +
        Independent Channels visible on the left, Histogram + Light + Color
        visible on the right, Crop and Scan hidden, nothing collapsed,
        thumbnail strip visible, zoomed to fit."""
        self.block_side = dict(_DEFAULT_BLOCK_SIDE)
        self.block_visible = dict(_DEFAULT_BLOCK_VISIBLE)
        self.block_collapsed = {k: False for k in _ALL_BLOCK_KEYS}
        self.left_block_order = list(_DEFAULT_LEFT_BLOCK_ORDER)
        self.right_block_order = list(_DEFAULT_RIGHT_BLOCK_ORDER)
        for key, widget in self.block_widgets.items():
            set_block_collapsed(widget.body, self.block_collapse_buttons[key], False)
        self.left_panel_toggle_btn.setChecked(True)
        self.right_panel_toggle_btn.setChecked(True)
        self.carousel_toggle_btn.setChecked(True)
        self.canvas.zoom_fit()
        self._apply_block_layout()
        # Reset Layout counts as "changing layout" - always deactivates
        # active crop mode, same as loading any other layout (see
        # _apply_restored_layout/_activate_default_layout).
        self._set_crop_active(False)

    def _capture_layout_state(self) -> dict:
        """Every field _apply_layout_state/_apply_restored_layout can
        restore, as a plain dict - used both by Layout Presets and (via
        _apply_layout_state) by the two session-persistence mechanisms'
        own layout fields, so there's one place this list is kept in
        sync."""
        return {
            "left_panel_visible": self.left_panel_toggle_btn.isChecked(),
            "right_panel_visible": self.right_panel_toggle_btn.isChecked(),
            "carousel_visible": self.carousel_toggle_btn.isChecked(),
            "block_side": dict(self.block_side),
            "block_visible": dict(self.block_visible),
            "block_collapsed": dict(self.block_collapsed),
            "left_block_order": list(self.left_block_order),
            "right_block_order": list(self.right_block_order),
        }

    def _apply_layout_state(self, data: dict) -> None:
        self._apply_restored_layout(
            data.get("left_panel_visible", True),
            data.get("right_panel_visible", True),
            data.get("carousel_visible", True),
            data.get("block_side"),
            data.get("block_visible"),
            data.get("block_collapsed"),
            data.get("left_block_order"),
            data.get("right_block_order"),
        )

    def on_save_layout_preset(self) -> None:
        name, ok = QInputDialog.getText(
            self, i18n.tr("layout_preset_save_dialog_title"), i18n.tr("layout_preset_name_prompt"))
        name = name.strip()
        if not ok or not name:
            return
        if name in _BUILT_IN_LAYOUT_PRESET_NAMES:
            show_alert(
                self, i18n.tr("layout_preset_builtin_name_title"),
                i18n.tr("layout_preset_builtin_name_text", name=name))
            return
        self._save_layout_preset(name)

    def _activate_default_layout(self, name: str) -> None:
        """Loads one of the 4 built-in default-layout menu entries (name is
        the fixed display identifier - "Trichrome"/"Color Correction"/
        "Crop"/"Scan", never the underlying preset name) and syncs the
        matching toolbar button's exclusive checked state - the single
        entry point for all 3 ways to trigger this (toolbar click, bare
        keyboard shortcut, Window menu item), so whichever was used, the
        toolbar always ends up showing the right one active. Always
        reloads the preset even if that button was already checked (e.g.
        re-pressing T after dragging blocks around resets back to the
        Trichrome layout), unlike a plain radio-button click which would
        be a no-op in that case. Resolves through _BUILT_IN_LAYOUT_SOURCE
        to the actual custom preset name it loads (e.g. "NewTrichrome") -
        the display name itself isn't a real saved preset. Activating the
        "Crop" slot specifically also arms active crop mode - every other
        slot (and the preset load itself, via _apply_restored_layout)
        deactivates it, since loading a layout otherwise always turns
        active crop mode off (2026-09-04)."""
        button = self._default_layout_buttons.get(name)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        source = _BUILT_IN_LAYOUT_SOURCE.get(name, name)
        self._load_layout_preset(source)
        self._set_crop_active(name == "Crop")

    def _save_layout_preset(self, name: str) -> None:
        """Also used as the "Update" action for an existing preset - saving
        under a name that already exists just overwrites its data, no
        separate update code path needed."""
        settings = QSettings(ORG_NAME, APP_NAME)
        settings.setValue(f"layout_preset_data_{name}", json.dumps(self._capture_layout_state()))
        if name not in self._layout_preset_names:
            self._layout_preset_names.append(name)
            settings.setValue("layout_preset_names", self._layout_preset_names)
        self._rebuild_layout_preset_menu()

    def _load_layout_preset(self, name: str) -> None:
        settings = QSettings(ORG_NAME, APP_NAME)
        raw = settings.value(f"layout_preset_data_{name}", "", type=str)
        if not raw:
            return
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return
        self._apply_layout_state(data)

    def _delete_layout_preset(self, name: str) -> None:
        # Defense in depth - the Layout Preset submenu no longer offers a
        # Delete action for a built-in name (see _rebuild_layout_preset_menu),
        # so this shouldn't be reachable for one, but guard here too.
        if name in _BUILT_IN_LAYOUT_PRESET_NAMES:
            return
        settings = QSettings(ORG_NAME, APP_NAME)
        settings.remove(f"layout_preset_data_{name}")
        if name in self._layout_preset_names:
            self._layout_preset_names.remove(name)
            settings.setValue("layout_preset_names", self._layout_preset_names)
        self._rebuild_layout_preset_menu()

    def _rebuild_layout_preset_menu(self) -> None:
        """Rebuilds every per-preset submenu below the Save action/
        separator - called after any preset is saved/updated/deleted, and
        from retranslate_ui() so a language switch also re-translates the
        per-preset Load/Update/Delete Preset labels (they're plain QActions
        built with i18n.tr() at construction time, not synced elsewhere).
        Skips any of the 4 reserved display names entirely (e.g. saving a
        custom preset literally called "Trichrome" is already refused by
        on_save_layout_preset, but this is a second guard) - they must
        never be Delete-able. Their *source* presets (e.g. "NewTrichrome")
        aren't reserved names, so they still appear here normally with
        their own full Load/Update/Delete, alongside the same slot's
        Load/Update submenu in the Window menu directly
        (builtin_layout_menus) - two convenient paths to the same preset,
        not a conflict."""
        for action in list(self.layout_preset_menu.actions()):
            if action in (self.save_layout_preset_action, self._layout_preset_separator):
                continue
            submenu = action.menu()
            self.layout_preset_menu.removeAction(action)
            if submenu is not None:
                submenu.deleteLater()
        for name in self._layout_preset_names:
            if name in _BUILT_IN_LAYOUT_PRESET_NAMES:
                continue
            submenu = QMenu(name, self.layout_preset_menu)
            load_action = QAction(i18n.tr("layout_preset_load"), submenu)
            load_action.triggered.connect(lambda _checked=False, n=name: self._load_layout_preset(n))
            submenu.addAction(load_action)
            update_action = QAction(i18n.tr("layout_preset_update"), submenu)
            update_action.triggered.connect(lambda _checked=False, n=name: self._save_layout_preset(n))
            submenu.addAction(update_action)
            delete_action = QAction(i18n.tr("layout_preset_delete"), submenu)
            delete_action.triggered.connect(lambda _checked=False, n=name: self._delete_layout_preset(n))
            submenu.addAction(delete_action)
            self.layout_preset_menu.addMenu(submenu)

    def _connect_signals(self) -> None:
        for i, panel in enumerate(self.channel_panels):
            panel.align_changed.connect(lambda idx=i: self.on_align_changed(idx))
            panel.tone_changed.connect(lambda idx=i: self.on_tone_changed(idx))
            panel.reset_align_requested.connect(lambda idx=i: self.on_reset_align(idx))
            panel.reset_tone_requested.connect(lambda idx=i: self.on_reset_tone(idx))
            panel.solo_toggled.connect(lambda checked, idx=i: self.on_solo_toggled(idx, checked))
            panel.active_toggled.connect(lambda checked, idx=i: self.on_active_toggled(idx, checked))

        self.histogram.reset_requested.connect(self.on_histogram_reset)

        # QAction.triggered must be connected via an explicit lambda, not a
        # bare bound setChecked reference - PySide6 doesn't reliably pass
        # the checked bool through to a raw C++ bound method here (confirmed
        # empirically: TypeError "takes exactly one argument (0 given)" on
        # both .trigger() and the real activate(Trigger) path a menu click
        # uses). The reverse direction (toggled -> action.setChecked) has no
        # such issue.
        self.window_left_panel_action.setChecked(self.left_panel_toggle_btn.isChecked())
        self.window_left_panel_action.triggered.connect(
            lambda checked: self.left_panel_toggle_btn.setChecked(checked))
        self.left_panel_toggle_btn.toggled.connect(self.window_left_panel_action.setChecked)
        self.window_right_panel_action.setChecked(self.right_panel_toggle_btn.isChecked())
        self.window_right_panel_action.triggered.connect(
            lambda checked: self.right_panel_toggle_btn.setChecked(checked))
        self.right_panel_toggle_btn.toggled.connect(self.window_right_panel_action.setChecked)
        self.window_thumbnails_action.setChecked(self.carousel_toggle_btn.isChecked())
        self.window_thumbnails_action.setEnabled(self.carousel_toggle_btn.isEnabled())
        self.window_thumbnails_action.triggered.connect(
            lambda checked: self.carousel_toggle_btn.setChecked(checked))
        self.carousel_toggle_btn.toggled.connect(self.window_thumbnails_action.setChecked)

        # Tools menu now lists every block individually (2026-09-04,
        # replacing the old 4 tool-switcher-mirroring actions) - each a
        # plain independent checkable toggle wired straight to
        # set_block_visible, which is also what each block's own close
        # button calls, so both stay in sync regardless of which one the
        # user used.
        for key, action in self.block_menu_actions.items():
            action.setChecked(self.block_visible.get(key, True))
            action.toggled.connect(lambda checked, k=key: self.set_block_visible(k, checked))

        self.light_panel.changed.connect(self.on_global_changed)
        self.light_panel.reset_requested.connect(self.on_reset_light)
        self.light_panel.invert_toggled.connect(self.on_invert_toggled)
        self.color_panel.changed.connect(self.on_global_changed)
        self.color_panel.reset_requested.connect(self.on_reset_white_balance)
        self.color_panel.pick_white_balance_toggled.connect(self.on_pick_white_balance_toggled)
        self.color_panel.black_white_toggled.connect(self.on_black_white_toggled)
        self.canvas.white_balance_pick_requested.connect(self.on_white_balance_picked)
        self.canvas.film_base_pick_requested.connect(self.on_film_base_pick_requested)
        self.histogram.pick_toggled.connect(self.canvas.set_histogram_pick_enabled)
        self.canvas.histogram_pixel_hovered.connect(self.on_histogram_pixel_hovered)
        self.canvas.histogram_pixel_left.connect(self.on_histogram_pixel_left)

        self.crop_panel.settings_changed.connect(self.on_crop_settings_changed)
        self.crop_panel.orientation_invert_requested.connect(self.on_crop_orientation_invert)
        self.crop_panel.reset_requested.connect(self.on_crop_reset)
        self.crop_panel.activate_toggled.connect(self._set_crop_active)

        self.curves_panel.changed.connect(self.on_curve_changed)
        self.curves_panel.reset_requested.connect(self.on_curve_reset)

        self.canvas.drag_delta.connect(self.on_canvas_drag)
        self.canvas.scale_delta.connect(self.on_canvas_scale)
        self.canvas.rotate_delta.connect(self.on_canvas_rotate)

        self.compare_btn.toggled.connect(self.on_compare_toggled)

    # ------------------------------------------------------------------
    # Fullscreen / focus mode
    # ------------------------------------------------------------------
    def toggle_focus_mode(self) -> None:
        self._is_focus_mode = not self._is_focus_mode
        self.fullscreen_btn.setChecked(self._is_focus_mode)
        if self._is_focus_mode:
            self.left_scroll.setVisible(False)
            self.right_scroll.setVisible(False)
            self.showFullScreen()
            self.fullscreen_btn.setToolTip(i18n.tr("exit_fullscreen_button"))
        else:
            self.showNormal()
            # Respect whatever the left/right panel toggle buttons were set
            # to before entering fullscreen, rather than forcing both back on.
            self.left_scroll.setVisible(self.left_panel_toggle_btn.isChecked())
            self.right_scroll.setVisible(self.right_panel_toggle_btn.isChecked())
            self.fullscreen_btn.setToolTip(i18n.tr("fullscreen_button"))

    # ------------------------------------------------------------------
    # Compare (preview the original, color adjustments bypassed)
    # ------------------------------------------------------------------
    def on_compare_toggled(self, active: bool) -> None:
        self._compare_active = active
        self.compare_indicator.setVisible(active)
        for panel in self.channel_panels:
            panel.set_sliders_enabled(not active)
        self.light_panel.set_sliders_enabled(not active)
        self.color_panel.set_sliders_enabled(not active)
        self.recompute_preview()

    def _on_carousel_toggle_btn(self, checked: bool) -> None:
        self._update_carousel_visibility()

    # ------------------------------------------------------------------
    # Grid view - the filmstrip's own "fullscreen" mode: the exact same
    # CarouselWidget instance, just reparented into preview_stack (in
    # place of the canvas) and switched into its grid layout
    # (CarouselWidget.set_grid_mode) instead of the bottom "bande" strip -
    # so every filmstrip feature (drag-to-reorder, right-click menu,
    # selection) keeps working unchanged, there's nothing separate to
    # keep in sync. There's no need for the bottom strip to also show
    # while this is up, so it's simply moved rather than duplicated.
    # ------------------------------------------------------------------
    def on_grid_view_toggled(self, checked: bool) -> None:
        if checked:
            self.canvas_layout.removeWidget(self.carousel)
            self.preview_stack.addWidget(self.carousel)
            self.preview_stack.setCurrentWidget(self.carousel)
            self.carousel.set_grid_mode(True)
        else:
            self.preview_stack.removeWidget(self.carousel)
            self.preview_stack.setCurrentWidget(self.canvas)
            self.carousel.set_grid_mode(False)
            # Insert back right before bottom_bar (not appended at the
            # layout's end), so bottom_bar stays the last/bottom-most item.
            self.canvas_layout.insertWidget(self.canvas_layout.indexOf(self.bottom_bar), self.carousel)
        self.zoom_fit_btn.setEnabled(not checked)
        self.zoom_100_btn.setEnabled(not checked)
        self._update_carousel_visibility()

    def on_zoom_in_clicked(self) -> None:
        if self.grid_view_toggle_btn.isChecked():
            self.carousel.zoom_in()
        else:
            self.canvas.zoom_in()

    def on_zoom_out_clicked(self) -> None:
        if self.grid_view_toggle_btn.isChecked():
            self.carousel.zoom_out()
        else:
            self.canvas.zoom_out()

    def _update_carousel_visibility(self, force_show: bool = False) -> None:
        multi = len(self.batch_items) >= 2
        grid_active = self.grid_view_toggle_btn.isChecked()
        self.carousel_toggle_btn.setEnabled(multi and not grid_active)
        self.window_thumbnails_action.setEnabled(multi and not grid_active)
        if force_show and multi and not grid_active:
            self.carousel_toggle_btn.setChecked(True)
        if grid_active:
            self.carousel.setVisible(True)
        else:
            self.carousel.setVisible(multi and self.carousel_toggle_btn.isChecked())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape and self._is_focus_mode:
            # Fullscreen takes priority: the first Escape only leaves it,
            # even while the Crop tool is active - a second Escape (now
            # windowed) is what backs out of Crop.
            self.toggle_focus_mode()
            event.accept()
            return

        if event.key() == Qt.Key_Escape and self._crop_active:
            # Discards any in-progress drag and exits active crop mode -
            # deliberately does NOT hide the Crop block/change layout
            # (2026-09-04), unlike a plain set_block_visible("crop", False).
            self._set_crop_active(False)
            event.accept()
            return

        if event.key() == Qt.Key_Escape and self.grid_view_toggle_btn.isChecked():
            self.grid_view_toggle_btn.setChecked(False)
            event.accept()
            return

        focus = QApplication.focusWidget()
        text_editing = isinstance(focus, (QAbstractSpinBox, QLineEdit))
        if (not text_editing and event.key() == Qt.Key_F
                and event.modifiers() == Qt.NoModifier):
            self.canvas.zoom_fit()
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_Z
                and event.modifiers() == Qt.NoModifier):
            self.canvas.zoom_100()
            event.accept()
            return

        if not text_editing and event.key() == Qt.Key_Colon:
            self.compare_btn.toggle()
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_W
                and event.modifiers() == Qt.NoModifier):
            self.color_panel.pick_white_balance_btn.toggle()
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_I
                and event.modifiers() == Qt.NoModifier):
            self.left_panel_toggle_btn.toggle()
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_O
                and event.modifiers() == Qt.NoModifier):
            self.right_panel_toggle_btn.toggle()
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_P
                and event.modifiers() == Qt.NoModifier
                and self.carousel_toggle_btn.isEnabled()):
            self.carousel_toggle_btn.toggle()
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_G
                and event.modifiers() == Qt.NoModifier):
            self.grid_view_toggle_btn.toggle()
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_T
                and event.modifiers() == Qt.NoModifier):
            self._activate_default_layout("Trichrome")
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_S
                and event.modifiers() == Qt.NoModifier):
            self._activate_default_layout("Scan")
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_E
                and event.modifiers() == Qt.NoModifier):
            self._activate_default_layout("Color Correction")
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_C
                and event.modifiers() == Qt.NoModifier):
            self._activate_default_layout("Crop")
            event.accept()
            return

        if (not text_editing and event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and self._crop_active):
            self.on_crop_apply()
            event.accept()
            return

        if self.carousel.count():
            if not text_editing and event.key() in (Qt.Key_Left, Qt.Key_Right):
                extend = bool(event.modifiers() & Qt.ShiftModifier)
                if event.key() == Qt.Key_Left:
                    self.carousel.go_prev(extend_selection=extend)
                else:
                    self.carousel.go_next(extend_selection=extend)
                event.accept()
                return
            if (not text_editing and event.key() == Qt.Key_A
                    and (event.modifiers() & Qt.ControlModifier)):
                self.carousel.toggle_select_all()
                event.accept()
                return
            if (not text_editing and event.key() in (Qt.Key_Backspace, Qt.Key_Delete)
                    and (event.modifiers() & Qt.ControlModifier)):
                self.delete_batch_items(self.carousel.selected_indices())
                event.accept()
                return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Help dialogs
    # ------------------------------------------------------------------
    def show_quickstart_dialog(self) -> None:
        self._show_help_dialog(i18n.tr("help_quickstart_title"), i18n.tr("help_quickstart_content"))

    def show_shortcuts_dialog(self) -> None:
        self._show_help_dialog(i18n.tr("help_shortcuts_title"), i18n.tr("help_shortcuts_content"))

    def _help_dialog_text_colors(self) -> tuple[str, str]:
        """(normal, muted) hex colors for help dialog text, derived from the
        live palette so bold headings/labels read clearly against de-
        emphasized body text in both light and dark mode - blending toward
        the text-edit background instead of a hardcoded gray."""
        fg = self.palette().color(QPalette.WindowText)
        bg = self.palette().color(QPalette.Base)
        t = 0.45
        muted = "#%02x%02x%02x" % (
            round(fg.red() + (bg.red() - fg.red()) * t),
            round(fg.green() + (bg.green() - fg.green()) * t),
            round(fg.blue() + (bg.blue() - fg.blue()) * t),
        )
        return fg.name(), muted

    def _show_help_dialog(self, title: str, html: str) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(560, 620)
        QShortcut(QKeySequence.Close, dialog, activated=dialog.close)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        normal, muted = self._help_dialog_text_colors()
        browser.document().setDefaultStyleSheet(
            f"body, p, li {{ color: {muted}; }} "
            f"b, h3 {{ color: {normal}; font-weight: 600; }}"
        )
        browser.setHtml(html)
        layout.addWidget(browser)
        close_btn = QPushButton("OK")
        close_btn.clicked.connect(dialog.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dialog.exec()

    # ------------------------------------------------------------------
    # Batch mode
    # ------------------------------------------------------------------
    def open_batch_window(self) -> None:
        # A fresh window each time: the previous one closes itself once an
        # import is confirmed, and its file-matching state doesn't need to
        # survive across separate batch imports.
        self.batch_window = BatchWindow(self)
        self.batch_window.show()
        self.batch_window.raise_()
        self.batch_window.activateWindow()

    # ------------------------------------------------------------------
    # Batch import (background load of many triplets into independent items)
    # ------------------------------------------------------------------
    def start_batch_import(
        self, triplets, ref_letter: str, auto_align: bool, replace: bool, harris_shutter: bool,
    ) -> None:
        """``harris_shutter`` is now an explicit parameter (2026-09-07) -
        the only caller, BatchWindow.start_import(), derives it from its
        own Processing Mode radios (B&W/Color Trichrome) rather than this
        reaching into self.import_panel.is_harris_shutter_active(), which
        used to silently read whatever the *main window's currently active
        photo* happened to have set, regardless of what's actually being
        batch-imported."""
        self._import_replace = replace
        self._import_pending = [None] * len(triplets)
        self.statusBar().showMessage(i18n.tr("batch_import_status_running", i=0, n=len(triplets)))

        self._import_thread = QThread(self)
        self._import_worker = BatchImportWorker(
            triplets=triplets,
            ref_letter=ref_letter,
            auto_align=auto_align,
            harris_shutter=harris_shutter,
        )
        self._import_worker.moveToThread(self._import_thread)
        self._import_thread.started.connect(self._import_worker.run)
        self._import_worker.progress.connect(self._on_batch_import_progress)
        self._import_worker.item_ready.connect(self._on_batch_import_item_ready)
        self._import_worker.finished.connect(self._on_batch_import_finished)
        self._import_worker.finished.connect(self._import_thread.quit)
        self._import_worker.finished.connect(self._import_worker.deleteLater)
        # Same QThread lifecycle rule as elsewhere: only drop refs once the
        # thread itself reports finished, not merely the worker's own signal.
        self._import_thread.finished.connect(self._import_thread.deleteLater)
        self._import_thread.finished.connect(self._clear_import_thread_refs)
        self._import_thread.start()

    def _on_batch_import_progress(self, done: int, total: int) -> None:
        self.statusBar().showMessage(i18n.tr("batch_import_status_running", i=done, n=total))

    def _on_batch_import_item_ready(self, index: int, item, warning: str) -> None:
        self._import_pending[index] = item

    def _on_batch_import_finished(self) -> None:
        items = [it for it in self._import_pending if it is not None]
        self._import_pending = []
        self._load_batch_items(items, replace=self._import_replace)
        self.statusBar().showMessage(i18n.tr("batch_import_status_done", n=len(items)), 8000)

    def _clear_import_thread_refs(self) -> None:
        self._import_thread = None
        self._import_worker = None

    def _load_batch_items(self, new_items: list, replace: bool) -> None:
        if not new_items:
            return
        # If the only existing item is still the untouched classic slot (no
        # photo ever loaded into it), there's nothing worth keeping - swap it
        # out instead of leaving a blank card in the filmstrip.
        if (not replace and len(self.batch_items) == 1
                and not any(l.has_image() for l in self.batch_items[0].layers)):
            replace = True
        self.push_undo()
        first_new = new_items[0]
        if replace:
            self.batch_items = new_items
        else:
            self.batch_items.extend(new_items)
        self._apply_current_sort()

        self.carousel.set_items([it.base for it in self.batch_items])

        start_index = next(i for i, it in enumerate(self.batch_items) if it is first_new)
        self.activate_batch_item(start_index)
        # By default only the newly-activated photo is selected for export;
        # cmd+click / cmd+A build a custom selection from there.
        self.carousel.select_only(start_index)
        self._update_carousel_visibility(force_show=True)
        self.canvas.zoom_fit()
        self._refresh_all_carousel_thumbnails()

    def _refresh_all_carousel_thumbnails(self) -> None:
        for i in range(len(self.batch_items)):
            self._refresh_carousel_thumbnail_for_item(i)

    # ------------------------------------------------------------------
    # Filmstrip sorting
    # ------------------------------------------------------------------
    def _sort_key(self, item: BatchItem):
        if self.sort_mode == "filename":
            return item.base.lower()
        if self.sort_mode == "capture_date":
            return item.effective_capture_date()
        if self.sort_mode == "custom":
            return item.effective_custom_order()
        return item.uid  # import_order, and the fallback for an unknown mode

    def _apply_current_sort(self) -> None:
        self.batch_items.sort(key=self._sort_key, reverse=self.sort_reversed)

    def set_sort_mode(self, mode: str) -> None:
        if mode not in self._sort_field_actions:
            return
        self.sort_mode = mode
        self._resort_and_refresh_carousel()
        self._sync_sort_menu_state()

    def set_sort_reversed(self, reversed_: bool) -> None:
        self.sort_reversed = reversed_
        self._resort_and_refresh_carousel()
        self._sync_sort_menu_state()

    def _sync_sort_menu_state(self) -> None:
        act = self._sort_field_actions.get(self.sort_mode)
        if act is not None:
            act.setChecked(True)
        self.sort_action_reversed.setChecked(self.sort_reversed)

    def _resort_and_refresh_carousel(self) -> None:
        if len(self.batch_items) < 2:
            return
        current_item = self.batch_items[self.batch_current_index] if self.batch_items else None
        self._apply_current_sort()
        self.carousel.set_items([it.base for it in self.batch_items])
        for i, it in enumerate(self.batch_items):
            self.carousel.set_selected(i, it.selected)
        if current_item is not None:
            self.batch_current_index = next(
                i for i, it in enumerate(self.batch_items) if it is current_item)
        self.carousel.set_current(self.batch_current_index)
        self._refresh_all_carousel_thumbnails()

    def on_carousel_reordered(self, order: list[int]) -> None:
        """The user dragged a filmstrip card to a new spot: ``order[new_pos]``
        is the old index now sitting at ``new_pos``. Reorder the model to
        match, and switch to (and renumber) custom order so the new
        arrangement "sticks" even after flipping to another sort field and
        back. ``batch_current_index`` is resynced from the carousel's own
        current index - its item identities don't change, only positions."""
        self.push_undo()
        self.batch_items = [self.batch_items[i] for i in order]
        # custom_order must be assigned so that re-applying the sort
        # (_apply_current_sort, which honors sort_reversed) reproduces
        # exactly this on-screen arrangement - if reversed is active, the
        # first card on screen needs the *highest* value, not the lowest,
        # since it'll come out first again only when sorted descending.
        n = len(self.batch_items)
        for i, it in enumerate(self.batch_items):
            it.custom_order = float(n - 1 - i) if self.sort_reversed else float(i)
        self.batch_current_index = self.carousel.current_index()
        if self.sort_mode != "custom":
            self.sort_mode = "custom"
        self._sync_sort_menu_state()

    def _refresh_carousel_thumbnail_for_item(self, index: int) -> None:
        item = self.batch_items[index]
        if item.mode == "normal":
            nl = item.normal_layer
            if not nl.has_image():
                return
            image = imaging.apply_invert(nl.image_preview, nl.invert)
            gc = item.global_corr
            global_params = (gc.black_point, gc.white_point, gc.gamma, gc.exposure, gc.brightness, gc.contrast,
                              gc.shadows, gc.highlights, gc.saturation, gc.temperature, gc.tint,
                              {ch: tuple(pts) for ch, pts in gc.curves.items()}, gc.black_white_active)
            rgb = imaging.compose_normal(image, global_params)
            self._update_carousel_thumbnail(index, imaging.to_uint8(rgb))
            return
        ref = next((l for l in item.layers if l.is_reference), item.layers[0])
        if not ref.has_image():
            return
        images = [l.image_preview for l in item.layers]
        geo_params = [(l.dx, l.dy, l.scale, l.rotation) for l in item.layers]
        tone_params = [(l.black_point, l.white_point, l.gamma, l.exposure, l.brightness, l.contrast,
                        l.shadows, l.highlights, l.invert) for l in item.layers]
        gc = item.global_corr
        global_params = (gc.black_point, gc.white_point, gc.gamma, gc.exposure, gc.brightness, gc.contrast,
                          gc.shadows, gc.highlights, gc.saturation, gc.temperature, gc.tint,
                          {ch: tuple(pts) for ch, pts in gc.curves.items()}, gc.black_white_active)
        rgb = imaging.compose_trichrome(images, geo_params, tone_params, ref.color_index, global_params)
        self._update_carousel_thumbnail(index, imaging.to_uint8(rgb))

    def _update_carousel_thumbnail(self, index: int, rgb_u8: np.ndarray) -> None:
        # max_dim is well above the filmstrip's own small on-screen size
        # (THUMB_W/THUMB_H, ~96px) on purpose - the same pixmap is reused,
        # scaled up, for grid-mode cells (see CarouselWidget._reflow_grid),
        # which can display much larger than the filmstrip - a 110px source
        # (the old value) read as visibly pixelated once enlarged there.
        small, _ = imaging.make_preview(rgb_u8, max_dim=_THUMBNAIL_MAX_DIM)
        small = np.ascontiguousarray(small)
        h, w = small.shape[:2]
        qimg = QImage(small.data, w, h, w * 3, QImage.Format_RGB888).copy()
        self.carousel.set_thumbnail(index, QPixmap.fromImage(qimg))

    # ------------------------------------------------------------------
    # Normal / Trichrome mode (added 2026-09-04) - see BatchItem.mode/
    # normal_layer in model.py. Trichrome is the app's original behavior (3
    # R/G/B shots recomposed); Normal is a single already-color photo,
    # loaded straight through without any warp/alignment/recompose step -
    # Light/Color/Crop/Curves still apply on top either way (see
    # recompute_preview's mode branch), only the RGB Channels tool (which
    # only makes sense for the 3-channel case) becomes unavailable.
    # ------------------------------------------------------------------
    def _sync_channels_panel_availability(self, mode: str) -> None:
        is_normal = mode == "normal"
        # Grays out and disables the whole block (channel_panels/lock row/
        # Auto Align all live inside independent_channels_body, so
        # disabling the body alone already covers them - only the header's
        # own title/"?"/Reset-all buttons need listing explicitly).
        set_block_disabled(
            self.independent_channels_body, self.channels_disabled_label,
            i18n.tr("channels_disabled_normal_mode") if is_normal else None,
            extra_widgets=(
                self.independent_channels_title_label, self.channels_scope_info_button,
                self.reset_all_alignment_button, self.reset_all_color_button))
        # setEnabled(False) alone doesn't dim each channel panel's own
        # explicitly-colored R/G/B border/title (or its 2 nested
        # CollapsibleSection borders) - QSS colors don't automatically
        # follow the disabled palette the way an unstyled border would -
        # so ChannelPanel.set_frame_disabled grays them explicitly.
        for panel in self.channel_panels:
            panel.set_frame_disabled(is_normal)

    def _sync_import_and_channels_ui(self) -> None:
        """Shared tail, called any time the active item's mode, its Harris
        Shutter state (Trichrome variant *or* Solo film type - two
        independent per-item flags, see on_harris_shutter_toggled), or its
        Normal-mode photo might have changed - activate_batch_item, undo/
        redo, session restore, paste/reset, the mode-switch handlers, and
        on_harris_shutter_toggled. Also what the Mode combo/film buttons'
        own set_mode_selection() call reads its harris_shutter argument
        from - self.layers/self.normal_layer are already the active item's
        own objects by every call site here (set right when
        batch_current_index changes), so reading them directly is always
        correct at this point. The mode-appropriate flag is picked here
        (self.normal_layer.harris_shutter in Solo, self.layers[0].harris_shutter
        otherwise) since ImportPanel has no visibility into which BatchItem
        field backs which mode."""
        if 0 <= self.batch_current_index < len(self.batch_items):
            mode = self.batch_items[self.batch_current_index].mode
        else:
            mode = "trichrome"
        active_harris_shutter = (
            self.normal_layer.harris_shutter if mode == "normal" else self.layers[0].harris_shutter)
        self.import_panel.set_mode_selection(mode, active_harris_shutter)
        self.import_panel.set_normal_filename(
            os.path.basename(self.normal_layer.path) if self.normal_layer.path else "")
        self._sync_channels_panel_availability(mode)

    def on_import_mode_change_requested(self, mode: str) -> None:
        if not (0 <= self.batch_current_index < len(self.batch_items)):
            return
        item = self.batch_items[self.batch_current_index]
        if item.mode == mode:
            return

        if mode == "trichrome":
            self._switch_to_trichrome_mode(item)
            return

        available = [l.has_image() for l in item.layers]
        loaded_count = sum(available)
        if loaded_count > 1:
            # Switching away from an already-multi-channel trichrome photo
            # would leave 1-2 loaded channels invisible/unused - ask which
            # one to keep editing, per the user's explicit spec, instead of
            # silently picking one.
            dialog = ModeSwitchDialog(available, self)
            dialog.exec()
            if dialog.chosen_index is None:
                self._sync_import_and_channels_ui()  # revert the combo, nothing changed
                return
            self._switch_to_normal_mode(item, item.layers[dialog.chosen_index])
        elif loaded_count == 1:
            self._switch_to_normal_mode(item, item.layers[available.index(True)])
        else:
            # Nothing loaded in any channel yet - a trivial mode flip, no
            # photo to carry over.
            self.push_undo()
            item.mode = "normal"
            self._sync_import_and_channels_ui()
            self.recompute_preview()

    def _switch_to_normal_mode(self, item, source_layer) -> None:
        """Reloads ``source_layer``'s own file (always one of item.layers,
        already has an image - never item.normal_layer itself) as a full-
        color image into item.normal_layer, and switches item.mode. The 3
        original channels stay completely untouched, so switching back to
        Trichrome mode later restores them exactly as they were."""
        try:
            full = imaging.load_color(source_layer.path)
        except Exception as exc:
            show_alert(self, i18n.tr("dialog_load_error_title"),
                                  i18n.tr("dialog_load_error_text", error=exc))
            self._sync_import_and_channels_ui()
            return
        if source_layer.quarter_turns:
            full = np.ascontiguousarray(np.rot90(full, source_layer.quarter_turns))

        self.push_undo()
        preview, preview_scale = imaging.make_preview(full)
        item.mode = "normal"
        item.normal_layer.path = source_layer.path
        item.normal_layer.image_full = full
        item.normal_layer.image_preview = preview
        item.normal_layer.preview_scale = preview_scale
        item.normal_layer.quarter_turns = source_layer.quarter_turns
        item.normal_layer.invert = source_layer.invert
        # A freshly-switched Solo photo always starts as "Solo Couleur" -
        # imaging.load_color() just loaded a real color image, so nothing
        # about it is B&W by default (unlike a Trichrome channel, whose
        # own correct default *is* harris_shutter=False/classic - Solo and
        # Trichrome have opposite natural defaults for this same field).
        item.normal_layer.harris_shutter = True
        self.normal_layer = item.normal_layer
        self._sync_import_and_channels_ui()
        self.recompute_preview()
        self.canvas.zoom_fit()

    def _switch_to_trichrome_mode(self, item) -> None:
        self.push_undo()
        item.mode = "trichrome"
        self._sync_import_and_channels_ui()
        self.recompute_preview()
        self.canvas.zoom_fit()

    def load_normal_image(self) -> None:
        name_filter = "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp);;" + i18n.tr("file_filter_all")
        settings = QSettings(ORG_NAME, APP_NAME)
        start_dir = settings.value("last_import_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.tr("load_normal_dialog_title"), start_dir, name_filter)
        if not path:
            return
        settings.setValue("last_import_dir", os.path.dirname(path))
        self._load_normal_image_from_path(path)

    def _load_normal_image_from_path(self, path: str, state: dict | None = None) -> bool:
        """Load ``path`` as the active item's Normal-mode photo. With
        ``state`` omitted (a fresh, manual load) quarter_turns resets to 0;
        with ``state`` given (restoring the same file from a previous
        session) it's restored from it instead - mirrors
        _load_image_from_path's own ``state`` convention."""
        try:
            full = imaging.load_color(path)
        except Exception as exc:
            show_alert(self, i18n.tr("dialog_load_error_title"),
                                  i18n.tr("dialog_load_error_text", error=exc))
            return False

        self.push_undo()
        film_base = state.get("film_base") if state is not None else None
        full = imaging.apply_film_base_correction(full, film_base)
        preview, preview_scale = imaging.make_preview(full)
        layer = self.normal_layer
        layer.path = path
        layer.image_full = full
        layer.image_preview = preview
        layer.preview_scale = preview_scale
        layer.quarter_turns = state.get("quarter_turns", 0) if state is not None else 0
        layer.film_base = film_base
        # A fresh manual load always starts as "Solo Couleur" (a real color
        # image was just loaded); restoring from a previous session's
        # ``state`` instead honors whichever film type was selected then -
        # defaulting True there too, for a state dict saved before this
        # field existed.
        layer.harris_shutter = state.get("harris_shutter", True) if state is not None else True
        if 0 <= self.batch_current_index < len(self.batch_items):
            item = self.batch_items[self.batch_current_index]
            item.base = os.path.splitext(os.path.basename(path))[0]
            # Defensive, not just relying on the Load button only being
            # reachable while normal_container is already shown - loading a
            # Normal photo always implies Normal mode is now active.
            if item.mode != "normal":
                item.mode = "normal"
                self._sync_channels_panel_availability("normal")

        self._sync_import_and_channels_ui()
        self.recompute_preview()
        self.canvas.zoom_fit()
        return True

    def on_carousel_files_dropped(self, paths: list[str]) -> None:
        """Photos dragged in from Finder directly onto the thumbnail strip -
        each becomes its own new Normal-mode photo, appended at the end
        (per the user's explicit spec: dropped files show up at the end of
        the filmstrip, treated as Normal mode by default). One unreadable
        file among several doesn't abort the rest."""
        new_items = []
        failed = []
        for path in paths:
            try:
                new_items.append(self._build_normal_batch_item(path))
            except Exception:
                failed.append(os.path.basename(path))
        if new_items:
            self.push_undo()
            self._append_new_batch_items(new_items)
        if failed:
            show_alert(self, i18n.tr("dialog_load_error_title"),
                       i18n.tr("dialog_drop_photos_failed_text", files=", ".join(failed)))

    def _build_normal_batch_item(self, path: str, film_base: dict | None = None) -> BatchItem:
        """Loads ``path`` as a fresh Normal-mode BatchItem, ready to append -
        shared by on_carousel_files_dropped (drag-and-drop from Finder) and
        on_scan_add_to_session_requested (Scan tool captures). Raises
        whatever imaging.load_color raises on a bad/unreadable file -
        callers decide how to surface that.

        ``film_base`` (optional {"R"/"G"/"B": float}) is stored on the
        layer *and* applied to the loaded pixel data - see
        ChannelLayer.film_base's own docstring in model.py for why this
        needs to be a real, persisted field (not baked in once) rather
        than a one-shot correction: every later reload of this same photo
        (a full-res export reload, a session restore, a relink) must keep
        reapplying it, or the correction would silently vanish there."""
        full = imaging.load_color(path)
        full = imaging.apply_film_base_correction(full, film_base)
        preview, preview_scale = imaging.make_preview(full)
        normal_layer = ChannelLayer(color_index=0, label="Normal")
        normal_layer.path = path
        normal_layer.image_full = full
        normal_layer.image_preview = preview
        normal_layer.preview_scale = preview_scale
        normal_layer.film_base = film_base
        # A freshly-created Solo item always starts as "Solo Couleur" - see
        # the same note in _switch_to_normal_mode.
        normal_layer.harris_shutter = True
        return BatchItem(
            base=os.path.splitext(os.path.basename(path))[0], paths={}, layers=new_project_layers(),
            global_corr=GlobalCorrection(), mode="normal", normal_layer=normal_layer, selected=True)

    def _build_trichrome_batch_item_from_paths(
        self, paths_by_channel: dict, invert: bool, film_base: dict | None = None,
    ) -> BatchItem:
        """Builds a Trichrome-mode BatchItem from 3 already-known R/G/B file
        paths (currently only the Scan tool's RGB Light triplet - see
        on_scan_add_to_session_requested) - same load/layer shape as
        BatchImportWorker._build_item (import_worker.py), minus auto-align:
        left at identity, since the Trichrome Process block's own Auto
        Align button is right there to run afterward rather than guessing
        whether the user wants it.
        ``invert`` is applied uniformly to all 3 layers, same invariant
        on_invert_toggled maintains elsewhere. Raises whatever
        imaging.load_grayscale raises on a bad/unreadable file - the caller
        decides how to surface that.

        ``film_base`` (optional {"R"/"G"/"B": float}, the Scan tool's
        "Sample Film Base" reference - a per-channel mean of the film's own
        clear/unexposed base) is stored on each layer *and* divided out of
        its own channel's raw density *before* invert (see
        ChannelLayer.film_base's docstring in model.py) - color negative's
        orange mask biases the raw RGB-Light-scanned channels unevenly
        (e.g. much less blue transmitted than red/green even at a neutral
        scene point), and that bias does NOT survive as a simple uniform
        tint through the 1-x invert (it becomes tone-dependent - see
        CLAUDE.md's writeup), which is exactly why a post-invert white-
        balance pick alone can't remove it. Normalizing so the sampled
        clear-film value maps to 1.0 in every channel *before* inverting is
        what lets the resulting positive be genuinely neutral in the
        shadows, not just at whichever one tone was picked."""
        layers = []
        for ci, letter in enumerate(CHANNEL_NAMES):
            full = imaging.load_grayscale(paths_by_channel[letter])
            full = imaging.apply_film_base_correction(full, film_base, channel=letter)
            preview, preview_scale = imaging.make_preview(full)
            layer = ChannelLayer(color_index=ci, label=letter)
            layer.path = paths_by_channel[letter]
            layer.image_full = full
            layer.image_preview = preview
            layer.preview_scale = preview_scale
            layer.is_reference = (letter == "G")
            layer.invert = invert
            layer.film_base = film_base
            # Explicit, not just relying on ChannelLayer's own default -
            # an RGB Light triplet is always recomposed as Standard (B&W)
            # Trichrome, never Color Trichrome, per the user's own
            # "RGB Light = Standard Trichrome" mapping (2026-09-08).
            layer.harris_shutter = False
            layers.append(layer)
        item_base = os.path.splitext(os.path.basename(paths_by_channel["G"]))[0]
        capture_date = imaging.extract_capture_date(paths_by_channel["G"])
        return BatchItem(
            base=item_base, paths=dict(paths_by_channel), layers=layers,
            global_corr=GlobalCorrection(), mode="trichrome", capture_date=capture_date, selected=True)

    def on_scan_add_to_session_requested(self, groups: list) -> None:
        """Handles ScanPanel.add_to_session_requested - one entry per
        capture group (a single External/White-light shot, or a complete
        RGB Light triplet), each already resolved to real file path(s) and
        the invert value the Scan tool's own Film mode implies. Mirrors
        on_carousel_files_dropped's "load what you can, report the rest"
        convention: one bad file among several doesn't block the others.

        ``black_white`` (2026-09-08) is the Film mode's own "force this
        composite to true neutral gray" flag (True only for B&W) - applied
        here, uniformly across both kinds, onto the freshly-built item's
        GlobalCorrection.black_white_active, per the user's "en fonction
        des films" auto-processing spec (see ScanPanel._auto_add_to_session's
        own docstring for the full mapping). The Light-mode half of that
        same spec ("External/White = Solo, RGB Light = Standard Trichrome")
        needs no extra code here - it's already exactly what ``kind``
        ("normal" vs "trichrome") and _build_trichrome_batch_item_from_paths's
        own explicit harris_shutter=False already produce."""
        new_items = []
        failed = []
        for g in groups:
            label = g["path"] if g["kind"] == "normal" else g["paths"].get("G", "")
            try:
                if g["kind"] == "normal":
                    item = self._build_normal_batch_item(g["path"])
                    item.normal_layer.invert = g["invert"]
                else:
                    item = self._build_trichrome_batch_item_from_paths(
                        g["paths"], g["invert"], g.get("film_base"))
                item.global_corr.black_white_active = g.get("black_white", False)
                new_items.append(item)
            except Exception:
                failed.append(os.path.basename(label) if label else "?")
        if new_items:
            self.push_undo()
            self._append_new_batch_items(new_items)
        if failed:
            show_alert(self, i18n.tr("dialog_load_error_title"),
                       i18n.tr("dialog_drop_photos_failed_text", files=", ".join(failed)))

    def _append_new_batch_items(self, items: list) -> None:
        """Shared tail for dropping files onto the carousel
        (on_carousel_files_dropped) and adding Scan tool captures
        (on_scan_add_to_session_requested) - appends ``items`` at the end
        of batch_items, makes them the sole selection, activates the last
        one, and refreshes the carousel/thumbnails. Mirrors
        duplicate_batch_item's own carousel-update sequence."""
        if not items:
            return
        self.batch_items.extend(items)
        new_index = len(self.batch_items) - 1
        added_ids = {id(it) for it in items}
        for it in self.batch_items:
            it.selected = id(it) in added_ids

        self.carousel.set_items([it.base for it in self.batch_items])
        for i, it in enumerate(self.batch_items):
            self.carousel.set_selected(i, it.selected)
        self.activate_batch_item(new_index)
        self._update_carousel_visibility(force_show=True)
        self._refresh_all_carousel_thumbnails()
        if len(items) == 1:
            self.statusBar().showMessage(i18n.tr("status_photo_added"), 4000)
        else:
            self.statusBar().showMessage(i18n.tr("status_photos_added", n=len(items)), 4000)

    def activate_batch_item(self, index: int) -> None:
        if not (0 <= index < len(self.batch_items)):
            return
        item = self.batch_items[index]
        self.batch_current_index = index
        self.layers = item.layers
        self.global_corr = item.global_corr
        self.crop = item.crop
        self.normal_layer = item.normal_layer
        self.active_index = None
        self.carousel.set_current(index)
        self.color_panel.set_pick_white_balance_active(False)
        self.canvas.set_wb_pick_enabled(False)
        self.scan_panel.set_pick_from_photo_active(False)
        self.canvas.set_film_base_pick_enabled(False)

        for i, panel in enumerate(self.channel_panels):
            panel.active_checkbox.blockSignals(True)
            panel.active_checkbox.setChecked(False)
            panel.active_checkbox.blockSignals(False)
            panel.solo_checkbox.blockSignals(True)
            panel.solo_checkbox.setChecked(self.layers[i].solo)
            panel.solo_checkbox.blockSignals(False)
        self.canvas.set_align_enabled(False)

        for i in range(3):
            layer = self.layers[i]
            self.import_panel.set_filename(i, os.path.basename(layer.path) if layer.path else "")
            self._sync_panel_from_layer(i)
        self.light_panel.set_invert(self._active_invert_state())
        self._refresh_reference_ui()
        self._sync_global_panel_from_model()
        self._sync_import_and_channels_ui()
        if self.block_visible.get("crop", False):
            self._sync_crop_panel_from_item()

        self.recompute_preview()

    def on_carousel_selection_changed(self) -> None:
        selected = set(self.carousel.selected_indices())
        for i, item in enumerate(self.batch_items):
            item.selected = i in selected

    # ------------------------------------------------------------------
    # Copy / paste settings, delete photos
    # ------------------------------------------------------------------
    def copy_settings_from(self, index: int) -> None:
        if not (0 <= index < len(self.batch_items)):
            return
        self._clipboard_settings = self._extract_settings(self.batch_items[index])
        self.paste_action.setEnabled(True)
        self.carousel.set_paste_crop_available(True)
        self.statusBar().showMessage(i18n.tr("status_settings_copied"), 4000)

    @staticmethod
    def _extract_settings(item) -> dict:
        # Color settings only - alignment (dx/dy/scale/rotation) is specific
        # to each photo's own geometry and must never be copied across items.
        layers_data = [{
            "black_point": l.black_point, "white_point": l.white_point, "gamma": l.gamma,
            "exposure": l.exposure, "brightness": l.brightness, "contrast": l.contrast,
            "shadows": l.shadows, "highlights": l.highlights, "invert": l.invert,
        } for l in item.layers]
        gc = item.global_corr
        global_data = {
            "black_point": gc.black_point, "white_point": gc.white_point, "gamma": gc.gamma,
            "exposure": gc.exposure, "brightness": gc.brightness, "contrast": gc.contrast,
            "shadows": gc.shadows,
            "highlights": gc.highlights, "saturation": gc.saturation,
            "temperature": gc.temperature, "tint": gc.tint,
            "curves": {ch: list(pts) for ch, pts in gc.curves.items()},
            "black_white_active": gc.black_white_active,
        }
        # Crop rides along in every copy (like color, unlike alignment), but
        # deliberately isn't restored by the regular Paste below - only the
        # dedicated "Paste Crop" (thumbnail menu / Crop panel button) applies it.
        cr = item.crop
        crop_data = {
            "x": cr.x, "y": cr.y, "width": cr.width, "height": cr.height,
            "rotation": cr.rotation, "mirror_h": cr.mirror_h, "mirror_v": cr.mirror_v,
            "aspect_ratio": cr.aspect_ratio, "aspect_portrait": cr.aspect_portrait,
            "custom_ratio_w": cr.custom_ratio_w, "custom_ratio_h": cr.custom_ratio_h,
        }
        return {"layers": layers_data, "global": global_data, "crop": crop_data}

    def paste_settings_to_selected(self) -> None:
        self.paste_settings_to(self.carousel.selected_indices())

    def paste_settings_to(self, indices: list[int]) -> None:
        if self._clipboard_settings is None or not indices:
            return
        self.push_undo()
        for idx in indices:
            if not (0 <= idx < len(self.batch_items)):
                continue
            item = self.batch_items[idx]
            for ci, layer in enumerate(item.layers):
                data = self._clipboard_settings["layers"][ci]
                layer.black_point, layer.white_point = data["black_point"], data["white_point"]
                layer.gamma, layer.exposure = data["gamma"], data["exposure"]
                layer.brightness, layer.contrast = data["brightness"], data["contrast"]
                layer.shadows, layer.highlights = data["shadows"], data["highlights"]
                layer.invert = data["invert"]
            # Mirrors the same invert value onto normal_layer too, so
            # pasting onto a Normal-mode item also takes effect there -
            # invert is always kept identical across all 3 trichrome
            # channels (see on_invert_toggled), so channel 0's copied
            # value is representative of the whole photo either way.
            item.normal_layer.invert = self._clipboard_settings["layers"][0]["invert"]
            gdata = self._clipboard_settings["global"]
            gc = item.global_corr
            gc.black_point, gc.white_point = gdata["black_point"], gdata["white_point"]
            gc.gamma, gc.exposure = gdata["gamma"], gdata["exposure"]
            gc.brightness, gc.contrast = gdata["brightness"], gdata["contrast"]
            gc.shadows, gc.highlights = gdata["shadows"], gdata["highlights"]
            gc.saturation = gdata["saturation"]
            gc.temperature, gc.tint = gdata["temperature"], gdata["tint"]
            gc.curves = {ch: list(pts) for ch, pts in gdata["curves"].items()}
            gc.black_white_active = gdata.get("black_white_active", False)

        if self.batch_current_index in indices:
            for i in range(3):
                self._sync_panel_from_layer(i)
            self.light_panel.set_invert(self._active_invert_state())
            self._sync_import_and_channels_ui()
            self._sync_global_panel_from_model()
            self.recompute_preview()
        for idx in indices:
            if idx != self.batch_current_index:
                self._refresh_carousel_thumbnail_for_item(idx)
        self.statusBar().showMessage(i18n.tr("status_settings_pasted", n=len(indices)), 4000)

    def paste_crop_to_selected(self) -> None:
        self.paste_crop_to(self.carousel.selected_indices())

    def paste_crop_to(self, indices: list[int]) -> None:
        """The only two ways to restore a copied crop: this (thumbnail menu
        "Paste Crop", or the Crop panel's own Paste button) - the regular
        Paste above deliberately skips it."""
        if self._clipboard_settings is None or "crop" not in self._clipboard_settings or not indices:
            return
        self.push_undo()
        cd = self._clipboard_settings["crop"]
        for idx in indices:
            if not (0 <= idx < len(self.batch_items)):
                continue
            cr = self.batch_items[idx].crop
            cr.x, cr.y, cr.width, cr.height = cd["x"], cd["y"], cd["width"], cd["height"]
            cr.rotation = cd["rotation"]
            cr.mirror_h, cr.mirror_v = cd["mirror_h"], cd["mirror_v"]
            cr.aspect_ratio = cd["aspect_ratio"]
            cr.aspect_portrait = cd["aspect_portrait"]
            cr.custom_ratio_w, cr.custom_ratio_h = cd["custom_ratio_w"], cd["custom_ratio_h"]

        if self.batch_current_index in indices:
            if self.block_visible.get("crop", False):
                self._sync_crop_panel_from_item()
            self.recompute_preview()
        for idx in indices:
            if idx != self.batch_current_index:
                self._refresh_carousel_thumbnail_for_item(idx)
        self.statusBar().showMessage(i18n.tr("status_crop_pasted", n=len(indices)), 4000)

    def delete_batch_items(self, indices: list[int]) -> None:
        if not indices:
            return
        self._play_delete_sound()
        self.push_undo()
        indices_set = set(indices)
        self.batch_items = [it for i, it in enumerate(self.batch_items) if i not in indices_set]

        if not self.batch_items:
            # Deleting the last photo(s) leaves an empty session - fall back
            # to one fresh blank item, same as a brand-new launch.
            self.batch_items = [BatchItem(base="", paths={}, layers=new_project_layers(),
                                           global_corr=GlobalCorrection(), selected=True)]

        self.carousel.set_items([it.base for it in self.batch_items])

        # Every item that was selected got deleted (that's what "indices"
        # was), so the only thing left worth selecting is the new current
        # item - same as a real click would leave it, and critically what
        # lets a repeated Cmd+Delete act on it immediately without first
        # having to click the photo again.
        new_index = min(self.batch_current_index, len(self.batch_items) - 1)
        self.activate_batch_item(new_index)
        self.carousel.select_only(new_index)
        self._update_carousel_visibility()
        self._refresh_all_carousel_thumbnails()
        self.statusBar().showMessage(i18n.tr("status_photos_deleted", n=len(indices)), 4000)

    def reset_batch_items(self, indices: list[int]) -> None:
        """Resets alignment, per-channel tone, global correction, invert and
        crop for each given photo - everything a fresh import would start
        with."""
        if not indices:
            return
        self.push_undo()
        for idx in indices:
            if not (0 <= idx < len(self.batch_items)):
                continue
            item = self.batch_items[idx]
            for layer in item.layers:
                layer.reset_alignment()
                layer.reset_tone()
                layer.invert = False
            item.normal_layer.invert = False
            item.global_corr.reset()
            item.crop.reset()

        if self.batch_current_index in indices:
            for i in range(3):
                self._sync_panel_from_layer(i)
            self.light_panel.set_invert(self._active_invert_state())
            self._sync_import_and_channels_ui()
            self._sync_global_panel_from_model()
            if self.block_visible.get("crop", False):
                self._sync_crop_panel_from_item()
            self.recompute_preview()
        for idx in indices:
            if idx != self.batch_current_index:
                self._refresh_carousel_thumbnail_for_item(idx)
        self.statusBar().showMessage(i18n.tr("status_photos_reset", n=len(indices)), 4000)

    def _duplicate_base_name(self, base: str) -> str:
        match = _DUPLICATE_SUFFIX_RE.match(base)
        root = match.group(1) if match else base
        used = set()
        for it in self.batch_items:
            m = _DUPLICATE_SUFFIX_RE.match(it.base)
            if m and m.group(1) == root:
                used.add(int(m.group(2)))
            elif it.base == root:
                used.add(1)
        n = 2
        while n in used:
            n += 1
        return f"{root} ({n})"

    def duplicate_batch_item(self, index: int) -> None:
        """Duplicates a single photo, inserted right after it and named with
        a "(N)" version suffix, so it can have several parallel edits - e.g.
        for comparing two alignments or color treatments side by side.
        Always acts on just this one photo, regardless of any multi-selection."""
        if not (0 <= index < len(self.batch_items)):
            return
        self.push_undo()
        src = self.batch_items[index]
        dup = BatchItem(
            base=self._duplicate_base_name(src.base),
            paths=dict(src.paths),
            layers=[copy.copy(l) for l in src.layers],
            global_corr=copy.copy(src.global_corr),
            mode=src.mode, normal_layer=copy.copy(src.normal_layer),
            selected=False,
            capture_date=src.capture_date,
        )
        self.batch_items.insert(index + 1, dup)

        self.carousel.set_items([it.base for it in self.batch_items])
        for i, it in enumerate(self.batch_items):
            it.selected = it is dup
            self.carousel.set_selected(i, it.selected)
        self.activate_batch_item(index + 1)
        self._update_carousel_visibility(force_show=True)
        self._refresh_all_carousel_thumbnails()
        self.statusBar().showMessage(i18n.tr("status_photo_duplicated"), 4000)

    # ------------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------------
    def _snapshot_state(self) -> dict:
        return {
            "batch_items": [
                BatchItem(
                    base=it.base, paths=dict(it.paths),
                    layers=[copy.copy(l) for l in it.layers],
                    global_corr=copy.copy(it.global_corr),
                    crop=copy.copy(it.crop),
                    mode=it.mode, normal_layer=copy.copy(it.normal_layer),
                    selected=it.selected, uid=it.uid,
                    capture_date=it.capture_date, custom_order=it.custom_order,
                ) for it in self.batch_items
            ],
            "batch_current_index": self.batch_current_index,
        }

    def _restore_state(self, snapshot: dict) -> None:
        self.batch_items = snapshot["batch_items"]
        index = max(0, min(snapshot["batch_current_index"], len(self.batch_items) - 1))
        self.batch_current_index = index
        self.layers = self.batch_items[index].layers
        self.global_corr = self.batch_items[index].global_corr
        self.crop = self.batch_items[index].crop
        self.normal_layer = self.batch_items[index].normal_layer
        self.active_index = None
        self.canvas.set_align_enabled(False)

        self.carousel.set_items([it.base for it in self.batch_items])
        for i, it in enumerate(self.batch_items):
            self.carousel.set_selected(i, it.selected)
        self.carousel.set_current(index)
        self._update_carousel_visibility()

        for i, panel in enumerate(self.channel_panels):
            panel.active_checkbox.blockSignals(True)
            panel.active_checkbox.setChecked(False)
            panel.active_checkbox.blockSignals(False)
            panel.solo_checkbox.blockSignals(True)
            panel.solo_checkbox.setChecked(self.layers[i].solo)
            panel.solo_checkbox.blockSignals(False)

        for i in range(3):
            layer = self.layers[i]
            self.import_panel.set_filename(i, os.path.basename(layer.path) if layer.path else "")
            self._sync_panel_from_layer(i)
        self.light_panel.set_invert(self._active_invert_state())
        self._refresh_reference_ui()
        self._sync_global_panel_from_model()
        self._sync_import_and_channels_ui()
        if self.block_visible.get("crop", False):
            self._sync_crop_panel_from_item()

        self.recompute_preview()
        self._refresh_all_carousel_thumbnails()

    def push_undo(self) -> None:
        if self._undo_suppressed:
            return
        self._undo_stack.append(self._snapshot_state())
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._edit_counter += 1
        self._update_undo_redo_actions()

    def _push_undo_coalesced(self, key: str) -> None:
        if self._undo_suppressed:
            return
        if key not in self._undo_coalesce_keys:
            self.push_undo()
            self._undo_coalesce_keys.add(key)
        timer = self._undo_coalesce_timers.get(key)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda k=key: self._undo_coalesce_keys.discard(k))
            self._undo_coalesce_timers[key] = timer
        timer.start(700)

    def undo(self) -> None:
        if not self._undo_stack:
            return
        current = self._snapshot_state()
        snapshot = self._undo_stack.pop()
        self._redo_stack.append(current)
        self._undo_suppressed = True
        try:
            self._restore_state(snapshot)
        finally:
            self._undo_suppressed = False
        self._edit_counter -= 1
        self._update_undo_redo_actions()

    def redo(self) -> None:
        if not self._redo_stack:
            return
        current = self._snapshot_state()
        snapshot = self._redo_stack.pop()
        self._undo_stack.append(current)
        self._undo_suppressed = True
        try:
            self._restore_state(snapshot)
        finally:
            self._undo_suppressed = False
        self._edit_counter += 1
        self._update_undo_redo_actions()

    def _update_undo_redo_actions(self) -> None:
        self.undo_action.setEnabled(bool(self._undo_stack))
        self.redo_action.setEnabled(bool(self._redo_stack))

    # ------------------------------------------------------------------
    # Loading images
    # ------------------------------------------------------------------
    def load_image(self, index: int) -> None:
        channel = i18n.channel_name(index)
        name_filter = "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp);;" + i18n.tr("file_filter_all")
        settings = QSettings(ORG_NAME, APP_NAME)
        start_dir = settings.value("last_import_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.tr("load_dialog_title", channel=channel), start_dir, name_filter)
        if not path:
            return
        settings.setValue("last_import_dir", os.path.dirname(path))
        self._load_image_from_path(index, path)

    def _load_image_from_path(self, index: int, path: str, state: dict | None = None) -> bool:
        """Load ``path`` into channel ``index``.

        With ``state`` omitted (a fresh, manual load), alignment and tone are
        reset to defaults. With ``state`` given (restoring the same file from
        a previous session), alignment and tone are restored from it instead.
        """
        layer = self.layers[index]
        loaded_before = sum(1 for l in self.layers if l.has_image())
        try:
            full = imaging.load_grayscale(
                path, channel=CHANNEL_NAMES[index] if self.import_panel.is_harris_shutter_active() else None)
        except Exception as exc:
            show_alert(self, i18n.tr("dialog_load_error_title"),
                                  i18n.tr("dialog_load_error_text", error=exc))
            return False

        self.push_undo()
        film_base = state.get("film_base") if state is not None else None
        full = imaging.apply_film_base_correction(full, film_base, channel=CHANNEL_NAMES[index])
        preview, preview_scale = imaging.make_preview(full)
        layer.path = path
        layer.image_full = full
        layer.image_preview = preview
        layer.preview_scale = preview_scale
        layer.harris_shutter = self.import_panel.is_harris_shutter_active()
        layer.film_base = film_base
        if layer.is_reference and 0 <= self.batch_current_index < len(self.batch_items):
            self.batch_items[self.batch_current_index].base = os.path.splitext(os.path.basename(path))[0]

        if state is not None:
            layer.dx = state["dx"]
            layer.dy = state["dy"]
            layer.scale = state["scale"]
            layer.rotation = state["rotation"]
            layer.black_point = state["black_point"]
            layer.white_point = state["white_point"]
            layer.gamma = state["gamma"]
            layer.exposure = state.get("exposure", 0.0)
            layer.brightness = state["brightness"]
            layer.contrast = state["contrast"]
            layer.shadows = state["shadows"]
            layer.highlights = state["highlights"]
            layer.quarter_turns = state.get("quarter_turns", 0)
        else:
            layer.reset_alignment()
            layer.reset_tone()
            layer.quarter_turns = 0
            ref = self._reference_layer()
            if ref is not layer and ref.has_image():
                ref_h, ref_w = ref.image_preview.shape[:2]
                h, w = preview.shape[:2]
                if w and h:
                    layer.scale = float(np.mean([ref_w / w, ref_h / h]))

        self.import_panel.set_filename(index, os.path.basename(path))
        self._sync_panel_from_layer(index)

        self.recompute_preview()
        self.canvas.zoom_fit()

        # The moment the 3rd photo completes the initial R+G+B set (a fresh
        # manual load, not a settings restore), auto-align the other two
        # channels against the reference so the composite looks right away.
        # Suppressed from pushing its own undo entries: they're part of the
        # same "load the 3rd photo" action already captured above.
        if state is None and loaded_before == 2 and all(l.has_image() for l in self.layers):
            was_suppressed = self._undo_suppressed
            self._undo_suppressed = True
            try:
                self._auto_align_after_import()
            finally:
                self._undo_suppressed = was_suppressed

        return True

    def _target_batch_indices(self) -> list[int]:
        """Selected photos in the carousel, or just the active one if
        nothing is selected - the standard "apply to multiple photos at
        once" fallback, shared by on_locate_missing_files/on_invert_toggled/
        on_harris_shutter_toggled."""
        selected = self.carousel.selected_indices()
        if selected:
            return [i for i in selected if 0 <= i < len(self.batch_items)]
        if 0 <= self.batch_current_index < len(self.batch_items):
            return [self.batch_current_index]
        return []

    def on_locate_missing_files(self) -> None:
        """Relinks missing channel(s) (see ChannelLayer.is_missing) across
        every selected photo in one action - falls back to just the active
        photo if the selection is empty. For each missing channel, looks for
        a file with the same basename as its last-known path, directly
        inside the picked folder or in a subfolder of it (_find_file_in_folder),
        then reloads it via _relink_channel, which always preserves the
        layer's existing alignment/tone - unlike a fresh manual "Load
        image", this is meant to restore existing photos, not start over on
        them. One push_undo() covers the whole batch, same convention as
        paste_settings_to/reset_batch_items/delete_batch_items."""
        selected = self._target_batch_indices()
        targets = [
            (i, ci) for i in selected if 0 <= i < len(self.batch_items)
            for ci, layer in enumerate(self.batch_items[i].layers) if layer.is_missing()
        ]
        if not targets:
            return

        settings = QSettings(ORG_NAME, APP_NAME)
        start_dir = settings.value("last_import_dir", "")
        folder = QFileDialog.getExistingDirectory(
            self, i18n.tr("missing_files_locate_dialog_title"), start_dir)
        if not folder:
            return
        settings.setValue("last_import_dir", folder)

        # Snapshotted before relinking anything - _relink_channel renames
        # item.base when its reference channel is relinked (same as a
        # manual reload), which would otherwise make an item's name drift
        # mid-loop if e.g. its reference channel succeeds right before one
        # of its other channels fails, confusingly relabeling the failure.
        original_base = {i: self.batch_items[i].base for i in {idx for idx, _ in targets}}

        self.push_undo()
        relinked = 0
        # (item_index, channel index, original item base, channel label,
        # last-known path) for anything still missing after this pass.
        unresolved = []
        for item_index, ci in targets:
            item = self.batch_items[item_index]
            layer = item.layers[ci]
            found = self._find_file_in_folder(folder, os.path.basename(layer.path))
            if found is not None and self._relink_channel(item, ci, found):
                relinked += 1
            else:
                unresolved.append((item_index, ci, original_base[item_index], layer.label, layer.path))

        if 0 <= self.batch_current_index < len(self.batch_items):
            for i in range(3):
                layer = self.layers[i]
                self.import_panel.set_filename(i, os.path.basename(layer.path) if layer.path else "")
                self._sync_panel_from_layer(i)
        self.recompute_preview()
        self.canvas.zoom_fit()
        self._refresh_all_carousel_thumbnails()

        if relinked:
            self.statusBar().showMessage(i18n.tr("missing_files_locate_success", count=relinked), 4000)
        if unresolved:
            # Same file-not-found basename match failed for these - most
            # likely they were renamed, not just moved, so basename matching
            # alone can't find them; explain both remaining options rather
            # than leaving the user to guess why Locate didn't fully work.
            # The list itself goes in a scrollable table (not folded into
            # the fixed text) so it stays legible even with many rows -
            # hovering a row shows its last-known path (table_tooltips), and
            # selecting a row + "Relink..." lets the user pick that exact
            # replacement file directly, without leaving this dialog for the
            # left panel.
            show_alert(
                self, i18n.tr("dialog_locate_failed_title"),
                i18n.tr("dialog_locate_failed_text"),
                table_headers=(i18n.tr("dialog_locate_failed_column_photo"),
                               i18n.tr("dialog_locate_failed_column_channel")),
                table_rows=[(base, label) for _, _, base, label, _ in unresolved],
                table_tooltips=[path for _, _, _, _, path in unresolved],
                row_action_label=i18n.tr("missing_files_relink_button"),
                row_action=lambda target: self._relink_one_channel_interactively(*target),
                row_targets=[(item_index, ci) for item_index, ci, _, _, _ in unresolved])

    def _relink_channel(self, item, ci: int, path: str) -> bool:
        """Reloads channel ``ci`` of ``item`` (which may not be the active
        item) from a new location, preserving its existing alignment/tone -
        the per-channel core of "Locate" (see on_locate_missing_files).
        Unlike _load_image_from_path, doesn't touch per-active-item UI or
        push its own undo entry - the caller handles both once for the
        whole batch of relinked channels."""
        layer = item.layers[ci]
        try:
            # Preserves this channel's own existing harris_shutter mode
            # (not the shared checkbox, which reflects whichever photo is
            # currently active and may differ from item) - relinking is
            # meant to restore the same photo, not reinterpret it.
            full = imaging.load_grayscale(
                path, channel=CHANNEL_NAMES[ci] if layer.harris_shutter else None)
        except Exception:
            return False
        # Preserves this channel's own existing film_base correction too,
        # same reasoning as harris_shutter just above - relinking restores
        # the same photo's own settings, not a fresh reinterpretation.
        full = imaging.apply_film_base_correction(full, layer.film_base, channel=CHANNEL_NAMES[ci])
        if layer.quarter_turns:
            full = np.ascontiguousarray(np.rot90(full, layer.quarter_turns))
        preview, preview_scale = imaging.make_preview(full)
        layer.path = path
        layer.image_full = full
        layer.image_preview = preview
        layer.preview_scale = preview_scale
        if layer.is_reference:
            item.base = os.path.splitext(os.path.basename(path))[0]
        return True

    def _relink_one_channel_interactively(self, item_index: int, ci: int) -> bool:
        """Opens a file picker for one specific missing channel and relinks
        it in place - the Locate-failure dialog's per-row "Relink..."
        action, for a photo whose file couldn't be found by basename match
        alone (e.g. renamed rather than moved). Lets the user pick that
        exact replacement file directly from the dialog, without needing to
        go find it via the left panel's per-channel Load. Same preserve-
        alignment/tone semantics as _relink_channel; returns True/False so
        the dialog knows whether to remove that row (see AlertDialog)."""
        if not (0 <= item_index < len(self.batch_items)):
            return False
        item = self.batch_items[item_index]
        if not (0 <= ci < len(item.layers)):
            return False
        layer = item.layers[ci]

        settings = QSettings(ORG_NAME, APP_NAME)
        start_dir = os.path.dirname(layer.path) if layer.path else settings.value("last_import_dir", "")
        name_filter = "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp);;" + i18n.tr("file_filter_all")
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.tr("missing_files_relink_dialog_title"), start_dir, name_filter)
        if not path:
            return False
        settings.setValue("last_import_dir", os.path.dirname(path))

        # Pre-flight load check so a bad file doesn't push a no-op undo
        # entry - same "load first, push_undo only once success is
        # confirmed" order as _load_image_from_path. _relink_channel below
        # repeats this load once confirmed; a second decode is an
        # acceptable cost for a one-off interactive pick, not a hot path.
        try:
            imaging.load_grayscale(
                path, channel=CHANNEL_NAMES[ci] if layer.harris_shutter else None)
        except Exception:
            return False

        self.push_undo()
        if not self._relink_channel(item, ci, path):
            return False

        if item_index == self.batch_current_index:
            self.import_panel.set_filename(ci, os.path.basename(self.layers[ci].path) if self.layers[ci].path else "")
            self._sync_panel_from_layer(ci)
            self.recompute_preview()
            self.canvas.zoom_fit()
        self._refresh_carousel_thumbnail_for_item(item_index)
        self.statusBar().showMessage(i18n.tr("missing_files_locate_success", count=1), 3000)
        return True

    @staticmethod
    def _find_file_in_folder(folder: str, basename: str) -> str | None:
        """A file named exactly ``basename`` directly inside ``folder``, or
        the first match found in one of its subfolders (the source photos
        may have been moved into a nested folder rather than dropped flat)."""
        direct = os.path.join(folder, basename)
        if os.path.isfile(direct):
            return direct
        for root, _dirs, files in os.walk(folder):
            if basename in files:
                return os.path.join(root, basename)
        return None

    def _auto_align_after_import(self) -> None:
        self.on_auto_align_all()

    def _restore_session(self) -> None:
        """On launch, just reopen whatever .trirgb was last open (full
        fidelity, same code path as File > Open Session) instead of
        reconstructing state field-by-field. Falls back to the legacy
        QSettings item-array restore below only when there's no remembered
        session file (fresh install, or a session that was never saved to a
        .trirgb) or reopening it failed."""
        last_path = QSettings(ORG_NAME, APP_NAME).value("last_session_file_path", "", type=str)
        if last_path and os.path.isfile(last_path):
            try:
                self.load_session_from_path(last_path, show_warnings=False)
                return
            except Exception:
                pass  # corrupted/empty/unreadable - fall through to the legacy restore

        self._legacy_restore_session()

    def _legacy_restore_session(self) -> None:
        """Rebuild every batch item (photos + their alignment/color settings)
        saved by ``_save_session_state`` on the previous close. Any channel
        whose file changed (or vanished) on disk since then is left unloaded,
        same policy as the old single-item restore. Superseded by the
        .trirgb-based restore in _restore_session, kept as a fallback."""
        settings = QSettings(ORG_NAME, APP_NAME)
        # Backward-compat default for a session saved before Harris Shutter
        # became per-channel (2026-09-02) - such a file only has this one
        # session-wide flag, not a per-channel value, so fall back to it
        # below when the newer per-channel key is missing.
        legacy_harris_shutter_default = settings.value("harris_shutter_enabled", False, type=bool)
        count = settings.beginReadArray("session_items")
        restored_items = []
        for i in range(count):
            settings.setArrayIndex(i)
            base = settings.value("base", "", type=str)
            selected = settings.value("selected", False, type=bool)
            raw_uid = settings.value("uid", -1, type=int)
            raw_capture_date = settings.value("capture_date", -1.0, type=float)
            raw_custom_order = settings.value("custom_order", -1.0, type=float)
            layers = []
            any_loaded = False
            for ci in range(3):
                prefix = f"ch{ci}_"
                layer = ChannelLayer(color_index=ci, label=CHANNEL_NAMES[ci])
                layer.is_reference = settings.value(prefix + "is_reference", ci == 1, type=bool)
                layer.invert = settings.value(prefix + "invert", False, type=bool)
                layer.harris_shutter = settings.value(
                    prefix + "harris_shutter", legacy_harris_shutter_default, type=bool)
                layer.dx = settings.value(prefix + "dx", 0.0, type=float)
                layer.dy = settings.value(prefix + "dy", 0.0, type=float)
                layer.scale = settings.value(prefix + "scale", 1.0, type=float)
                layer.rotation = settings.value(prefix + "rotation", 0.0, type=float)
                layer.black_point = settings.value(prefix + "black", 0.0, type=float)
                layer.white_point = settings.value(prefix + "white", 0.0, type=float)
                layer.gamma = settings.value(prefix + "gamma", 1.0, type=float)
                layer.exposure = settings.value(prefix + "exposure", 0.0, type=float)
                layer.brightness = settings.value(prefix + "brightness", 0.0, type=float)
                layer.contrast = settings.value(prefix + "contrast", 1.0, type=float)
                layer.shadows = settings.value(prefix + "shadows", 0.0, type=float)
                layer.highlights = settings.value(prefix + "highlights", 0.0, type=float)
                layer.quarter_turns = settings.value(prefix + "quarter_turns", 0, type=int)
                layer.film_base = _decode_film_base(settings.value(prefix + "film_base", "", type=str))

                path = settings.value(prefix + "path", "", type=str)
                stored_mtime = settings.value(prefix + "mtime", -1.0, type=float)
                if path:
                    # Retained even if the file below can't be loaded (moved/
                    # deleted since), so the missing path can still be shown
                    # and relinked via "Locate" - see ChannelLayer.is_missing.
                    layer.path = path
                if path and stored_mtime >= 0 and os.path.isfile(path):
                    try:
                        current_mtime = os.path.getmtime(path)
                    except OSError:
                        current_mtime = None
                    if current_mtime is not None and abs(current_mtime - stored_mtime) <= 1e-6:
                        try:
                            full = imaging.load_grayscale(
                                path, channel=CHANNEL_NAMES[ci] if layer.harris_shutter else None)
                        except Exception:
                            full = None
                        if full is not None:
                            full = imaging.apply_film_base_correction(
                                full, layer.film_base, channel=CHANNEL_NAMES[ci])
                            if layer.quarter_turns:
                                full = np.ascontiguousarray(np.rot90(full, layer.quarter_turns))
                            preview, preview_scale = imaging.make_preview(full)
                            layer.image_preview = preview
                            layer.preview_scale = preview_scale
                            any_loaded = True
                layers.append(layer)

            mode = settings.value("mode", "trichrome", type=str)
            if mode not in ("trichrome", "normal"):
                mode = "trichrome"
            normal_layer = ChannelLayer(color_index=0, label="Normal")
            normal_layer.quarter_turns = settings.value("normal_quarter_turns", 0, type=int)
            normal_layer.invert = settings.value("normal_invert", False, type=bool)
            # Default True ("Solo Couleur") for a session saved before this
            # field existed - a Solo photo has only ever behaved as color
            # until now, never as an implicit B&W.
            normal_layer.harris_shutter = settings.value("normal_harris_shutter", True, type=bool)
            normal_layer.film_base = _decode_film_base(settings.value("normal_film_base", "", type=str))
            normal_path = settings.value("normal_path", "", type=str)
            normal_mtime = settings.value("normal_mtime", -1.0, type=float)
            if normal_path:
                normal_layer.path = normal_path
            if normal_path and normal_mtime >= 0 and os.path.isfile(normal_path):
                try:
                    normal_current_mtime = os.path.getmtime(normal_path)
                except OSError:
                    normal_current_mtime = None
                if normal_current_mtime is not None and abs(normal_current_mtime - normal_mtime) <= 1e-6:
                    try:
                        normal_full = imaging.load_color(normal_path)
                    except Exception:
                        normal_full = None
                    if normal_full is not None:
                        normal_full = imaging.apply_film_base_correction(normal_full, normal_layer.film_base)
                        if normal_layer.quarter_turns:
                            normal_full = np.ascontiguousarray(np.rot90(normal_full, normal_layer.quarter_turns))
                        normal_preview, normal_preview_scale = imaging.make_preview(normal_full)
                        normal_layer.image_preview = normal_preview
                        normal_layer.preview_scale = normal_preview_scale

            if not any_loaded and not any(l.path for l in layers) and not normal_path:
                continue  # a genuinely empty item (never had any channel or normal photo) - drop it

            gc = GlobalCorrection()
            gc.black_point = settings.value("g_black", 0.0, type=float)
            gc.white_point = settings.value("g_white", 0.0, type=float)
            gc.gamma = settings.value("g_gamma", 1.0, type=float)
            gc.exposure = settings.value("g_exposure", 0.0, type=float)
            gc.brightness = settings.value("g_brightness", 0.0, type=float)
            gc.contrast = settings.value("g_contrast", 1.0, type=float)
            gc.shadows = settings.value("g_shadows", 0.0, type=float)
            gc.highlights = settings.value("g_highlights", 0.0, type=float)
            gc.saturation = settings.value("g_saturation", 1.0, type=float)
            gc.temperature = settings.value("g_temperature", 0.0, type=float)
            gc.tint = settings.value("g_tint", 0.0, type=float)
            gc.curves = _decode_curves(settings.value("g_curves", "", type=str))
            gc.black_white_active = settings.value("g_black_white_active", False, type=bool)

            cr = CropSettings()
            cr.x = settings.value("crop_x", 0.0, type=float)
            cr.y = settings.value("crop_y", 0.0, type=float)
            cr.width = settings.value("crop_width", 1.0, type=float)
            cr.height = settings.value("crop_height", 1.0, type=float)
            cr.rotation = settings.value("crop_rotation", 0.0, type=float)
            cr.mirror_h = settings.value("crop_mirror_h", False, type=bool)
            cr.mirror_v = settings.value("crop_mirror_v", False, type=bool)
            cr.aspect_ratio = settings.value("crop_aspect_ratio", "original", type=str)
            cr.aspect_portrait = settings.value("crop_aspect_portrait", False, type=bool)
            cr.custom_ratio_w = settings.value("crop_custom_ratio_w", 1.0, type=float)
            cr.custom_ratio_h = settings.value("crop_custom_ratio_h", 1.0, type=float)

            item_kwargs = {}
            if raw_uid >= 0:
                item_kwargs["uid"] = raw_uid
            if raw_capture_date >= 0:
                item_kwargs["capture_date"] = raw_capture_date
            if raw_custom_order >= 0:
                item_kwargs["custom_order"] = raw_custom_order
            restored_items.append(BatchItem(base=base, paths={}, layers=layers,
                                             global_corr=gc, crop=cr, mode=mode, normal_layer=normal_layer,
                                             selected=selected, **item_kwargs))
        settings.endArray()

        if not restored_items:
            return  # keep the fresh, empty item created in __init__

        saved_index = settings.value("session_current_index", 0, type=int)
        self._apply_restored_items(
            restored_items,
            settings.value("sort_mode", "import_order", type=str),
            settings.value("sort_reversed", False, type=bool),
            saved_index,
        )
        def _load_json(qkey: str):
            raw = settings.value(qkey, "", type=str)
            if not raw:
                return None
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return None

        self._apply_restored_layout(
            settings.value("left_panel_visible", True, type=bool),
            settings.value("right_panel_visible", True, type=bool),
            settings.value("carousel_visible", True, type=bool),
            _load_json("block_side"),
            _load_json("block_visible"),
            _load_json("block_collapsed"),
            _load_json("left_block_order"),
            _load_json("right_block_order"),
        )

    def _apply_restored_layout(
        self, left_visible: bool, right_visible: bool, carousel_visible: bool,
        block_side: dict | None = None, block_visible: dict | None = None,
        block_collapsed: dict | None = None,
        left_block_order: list | None = None, right_block_order: list | None = None,
    ) -> None:
        """Restores which panels were shown/hidden - shared by both the
        QSettings autosave and .trirgb restore paths. Separate from
        _apply_restored_items since it's window-level state, not tied to
        batch_items. (Harris Shutter's own combo state used to be synced
        here too, back when it was one session-wide flag - now that it's
        per-photo like invert, _apply_restored_items syncs it via
        _sync_import_and_channels_ui() alongside set_invert(), the same
        place/timing as every other per-photo widget.)

        block_side/block_visible/block_collapsed/left_block_order/
        right_block_order (the block system, 2026-09-04) are all optional/
        None-safe so an old saved session or .trirgb from before this
        feature existed just keeps whatever __init__'s own defaults
        (_DEFAULT_BLOCK_SIDE etc.) already set up, rather than needing
        every caller to know that default itself. Only known block keys
        are accepted, so a future block key removed from a newer version
        can't leave a stale/unreachable entry around."""
        self.left_panel_toggle_btn.setChecked(left_visible)
        self.right_panel_toggle_btn.setChecked(right_visible)
        self.carousel_toggle_btn.setChecked(carousel_visible)

        if block_side:
            self.block_side.update({k: v for k, v in block_side.items() if k in _ALL_BLOCK_KEYS})
        if block_visible:
            self.block_visible.update({k: bool(v) for k, v in block_visible.items() if k in _ALL_BLOCK_KEYS})
        if block_collapsed:
            self.block_collapsed.update({k: bool(v) for k, v in block_collapsed.items() if k in _ALL_BLOCK_KEYS})
        if left_block_order:
            self.left_block_order = [k for k in left_block_order if k in _ALL_BLOCK_KEYS]
            for k in _ALL_BLOCK_KEYS:
                if self.block_side.get(k) == "left" and k not in self.left_block_order:
                    self.left_block_order.append(k)
        if right_block_order:
            self.right_block_order = [k for k in right_block_order if k in _ALL_BLOCK_KEYS]
            for k in _ALL_BLOCK_KEYS:
                if self.block_side.get(k) == "right" and k not in self.right_block_order:
                    self.right_block_order.append(k)
        for key, widget in self.block_widgets.items():
            set_block_collapsed(widget.body, self.block_collapse_buttons[key], self.block_collapsed.get(key, False))
        self._apply_block_layout()
        # Loading any layout (a session restore, or a Layout Preset - built-
        # in or custom) always deactivates active crop mode, whether or not
        # the Crop block ends up visible - "changing layout" turns it off
        # unconditionally (2026-09-04). _activate_default_layout re-arms it
        # afterward specifically for the "Crop" slot; nothing else should.
        self._set_crop_active(False)

    def _apply_restored_items(
        self, restored_items: list, sort_mode: str, sort_reversed: bool, current_index: int,
    ) -> None:
        """Shared tail for _restore_session (QSettings autosave) and
        load_session_from_path (an explicit .trirgb file): install a
        reconstructed batch_items list as the working session and refresh
        every UI element that reflects it."""
        ensure_batch_item_uid_above(max(it.uid for it in restored_items))
        self.sort_mode = sort_mode if sort_mode in self._sort_field_actions else "import_order"
        self.sort_reversed = sort_reversed

        current_index = max(0, min(current_index, len(restored_items) - 1))
        current_item = restored_items[current_index]

        self.batch_items = restored_items
        self._apply_current_sort()
        self.batch_current_index = next(
            i for i, it in enumerate(self.batch_items) if it is current_item)
        self.layers = self.batch_items[self.batch_current_index].layers
        self.global_corr = self.batch_items[self.batch_current_index].global_corr
        self.crop = self.batch_items[self.batch_current_index].crop
        self.normal_layer = self.batch_items[self.batch_current_index].normal_layer

        self.carousel.set_items([it.base for it in self.batch_items])
        for i, it in enumerate(self.batch_items):
            self.carousel.set_selected(i, it.selected)
        self.carousel.set_current(self.batch_current_index)
        self._update_carousel_visibility()

        for i, panel in enumerate(self.channel_panels):
            panel.solo_checkbox.blockSignals(True)
            panel.solo_checkbox.setChecked(self.layers[i].solo)
            panel.solo_checkbox.blockSignals(False)
        for i in range(3):
            layer = self.layers[i]
            self.import_panel.set_filename(i, os.path.basename(layer.path) if layer.path else "")
            self._sync_panel_from_layer(i)
        self.light_panel.set_invert(self._active_invert_state())
        self._refresh_reference_ui()
        self._sync_global_panel_from_model()
        self._sync_import_and_channels_ui()
        if self.block_visible.get("crop", False):
            self._sync_crop_panel_from_item()
        self._refresh_all_carousel_thumbnails()

    # ------------------------------------------------------------------
    # Session files (.trirgb) - an explicit, portable project file, as
    # opposed to the QSettings-based autosave-on-close session above.
    # ------------------------------------------------------------------
    def _collect_session_data(self) -> dict:
        items_data = []
        for item in self.batch_items:
            channels_data = []
            for layer in item.layers:
                channels_data.append({
                    "path": layer.path or "",
                    "is_reference": layer.is_reference,
                    "invert": layer.invert,
                    "harris_shutter": layer.harris_shutter,
                    "dx": layer.dx, "dy": layer.dy, "scale": layer.scale, "rotation": layer.rotation,
                    "quarter_turns": layer.quarter_turns,
                    "film_base": layer.film_base,
                    "black": layer.black_point, "white": layer.white_point, "gamma": layer.gamma,
                    "exposure": layer.exposure,
                    "brightness": layer.brightness, "contrast": layer.contrast,
                    "shadows": layer.shadows, "highlights": layer.highlights,
                })
            gc = item.global_corr
            cr = item.crop
            nl = item.normal_layer
            items_data.append({
                "base": item.base,
                "selected": item.selected,
                "uid": item.uid,
                "capture_date": item.capture_date,
                "custom_order": item.custom_order,
                "channels": channels_data,
                "mode": item.mode,
                "normal": {
                    "path": nl.path or "", "quarter_turns": nl.quarter_turns, "invert": nl.invert,
                    "harris_shutter": nl.harris_shutter, "film_base": nl.film_base,
                },
                "global": {
                    "black": gc.black_point, "white": gc.white_point, "gamma": gc.gamma,
                    "exposure": gc.exposure,
                    "brightness": gc.brightness, "contrast": gc.contrast,
                    "shadows": gc.shadows, "highlights": gc.highlights,
                    "saturation": gc.saturation, "temperature": gc.temperature, "tint": gc.tint,
                    "curves": {ch: [[x, y] for x, y in pts] for ch, pts in gc.curves.items()},
                    "black_white_active": gc.black_white_active,
                },
                "crop": {
                    "x": cr.x, "y": cr.y, "width": cr.width, "height": cr.height,
                    "rotation": cr.rotation, "mirror_h": cr.mirror_h, "mirror_v": cr.mirror_v,
                    "aspect_ratio": cr.aspect_ratio, "aspect_portrait": cr.aspect_portrait,
                    "custom_ratio_w": cr.custom_ratio_w, "custom_ratio_h": cr.custom_ratio_h,
                },
            })

        settings = QSettings(ORG_NAME, APP_NAME)
        return {
            "format_version": SESSION_FORMAT_VERSION,
            "sort_mode": self.sort_mode,
            "sort_reversed": self.sort_reversed,
            "current_index": self.batch_current_index,
            **self._capture_layout_state(),
            "scan_settings": self.scan_panel.settings_snapshot(),
            "items": items_data,
            "preferences": {
                "last_import_dir": settings.value("last_import_dir", "", type=str),
                "export_output_dir": settings.value("export_output_dir", "", type=str),
                "export_same_as_source": settings.value("export_same_as_source", False, type=bool),
            },
        }

    def _build_restored_items_from_data(self, data: dict) -> tuple[list, str, bool, int]:
        """Inverse of _collect_session_data. Unlike _restore_session (the
        QSettings autosave), there's no mtime staleness check: opening a
        named .trirgb file is an explicit user action, so every channel
        whose path still exists on disk is reloaded regardless of when it
        last changed."""
        # Backward-compat default for a .trirgb saved before Harris Shutter
        # became per-channel (2026-09-02) - such a file only has this one
        # session-wide key, not a per-channel value.
        legacy_harris_shutter_default = data.get("harris_shutter_enabled", False)
        restored_items = []
        for item_data in data.get("items", []):
            layers = []
            any_loaded = False
            for ci, ch in enumerate(item_data.get("channels", [])):
                layer = ChannelLayer(color_index=ci, label=CHANNEL_NAMES[ci])
                layer.is_reference = ch.get("is_reference", ci == 1)
                layer.invert = ch.get("invert", False)
                layer.harris_shutter = ch.get("harris_shutter", legacy_harris_shutter_default)
                layer.dx = ch.get("dx", 0.0)
                layer.dy = ch.get("dy", 0.0)
                layer.scale = ch.get("scale", 1.0)
                layer.rotation = ch.get("rotation", 0.0)
                layer.black_point = ch.get("black", 0.0)
                layer.white_point = ch.get("white", 0.0)
                layer.gamma = ch.get("gamma", 1.0)
                layer.exposure = ch.get("exposure", 0.0)
                layer.brightness = ch.get("brightness", 0.0)
                layer.contrast = ch.get("contrast", 1.0)
                layer.shadows = ch.get("shadows", 0.0)
                layer.highlights = ch.get("highlights", 0.0)
                layer.quarter_turns = ch.get("quarter_turns", 0)
                layer.film_base = ch.get("film_base")

                path = ch.get("path", "")
                if path:
                    # Retained even if the file below can't be loaded (moved/
                    # deleted since), so the missing path can still be shown
                    # and relinked via "Locate" - see ChannelLayer.is_missing.
                    layer.path = path
                if path and os.path.isfile(path):
                    try:
                        full = imaging.load_grayscale(
                            path, channel=CHANNEL_NAMES[ci] if layer.harris_shutter else None)
                    except Exception:
                        full = None
                    if full is not None:
                        full = imaging.apply_film_base_correction(
                            full, layer.film_base, channel=CHANNEL_NAMES[ci])
                        if layer.quarter_turns:
                            full = np.ascontiguousarray(np.rot90(full, layer.quarter_turns))
                        preview, preview_scale = imaging.make_preview(full)
                        layer.image_preview = preview
                        layer.preview_scale = preview_scale
                        any_loaded = True
                layers.append(layer)

            normal_layer = ChannelLayer(color_index=0, label="Normal")
            n = item_data.get("normal", {})
            normal_path = n.get("path", "")
            normal_layer.quarter_turns = n.get("quarter_turns", 0)
            normal_layer.invert = n.get("invert", False)
            # Default True ("Solo Couleur") for a .trirgb saved before this
            # field existed - same reasoning as the QSettings restore path.
            normal_layer.harris_shutter = n.get("harris_shutter", True)
            normal_layer.film_base = n.get("film_base")
            if normal_path:
                # Same is_missing()-on-load-failure retention as the 3
                # trichrome channels above.
                normal_layer.path = normal_path
            if normal_path and os.path.isfile(normal_path):
                try:
                    normal_full = imaging.load_color(normal_path)
                except Exception:
                    normal_full = None
                if normal_full is not None:
                    normal_full = imaging.apply_film_base_correction(normal_full, normal_layer.film_base)
                    if normal_layer.quarter_turns:
                        normal_full = np.ascontiguousarray(np.rot90(normal_full, normal_layer.quarter_turns))
                    normal_preview, normal_preview_scale = imaging.make_preview(normal_full)
                    normal_layer.image_preview = normal_preview
                    normal_layer.preview_scale = normal_preview_scale

            if not any_loaded and not any(l.path for l in layers) and not normal_path:
                continue  # a genuinely empty item (never had any channel or normal photo) - drop it

            gc = GlobalCorrection()
            g = item_data.get("global", {})
            gc.black_point = g.get("black", 0.0)
            gc.white_point = g.get("white", 0.0)
            gc.gamma = g.get("gamma", 1.0)
            gc.exposure = g.get("exposure", 0.0)
            gc.brightness = g.get("brightness", 0.0)
            gc.contrast = g.get("contrast", 1.0)
            gc.shadows = g.get("shadows", 0.0)
            gc.highlights = g.get("highlights", 0.0)
            gc.saturation = g.get("saturation", 1.0)
            gc.temperature = g.get("temperature", 0.0)
            gc.tint = g.get("tint", 0.0)
            raw_curves = g.get("curves")
            gc.curves = {
                ch: [(float(x), float(y)) for x, y in raw_curves[ch]] if raw_curves and ch in raw_curves
                else [tuple(p) for p in _IDENTITY_CURVE]
                for ch in _CURVE_CHANNELS
            }
            gc.black_white_active = g.get("black_white_active", False)

            cr = CropSettings()
            c = item_data.get("crop", {})
            cr.x = c.get("x", 0.0)
            cr.y = c.get("y", 0.0)
            cr.width = c.get("width", 1.0)
            cr.height = c.get("height", 1.0)
            cr.rotation = c.get("rotation", 0.0)
            cr.mirror_h = c.get("mirror_h", False)
            cr.mirror_v = c.get("mirror_v", False)
            cr.aspect_ratio = c.get("aspect_ratio", "original")
            cr.aspect_portrait = c.get("aspect_portrait", False)
            cr.custom_ratio_w = c.get("custom_ratio_w", 1.0)
            cr.custom_ratio_h = c.get("custom_ratio_h", 1.0)

            item_kwargs = {}
            if item_data.get("uid") is not None:
                item_kwargs["uid"] = item_data["uid"]
            if item_data.get("capture_date") is not None:
                item_kwargs["capture_date"] = item_data["capture_date"]
            if item_data.get("custom_order") is not None:
                item_kwargs["custom_order"] = item_data["custom_order"]
            mode = item_data.get("mode", "trichrome")
            restored_items.append(BatchItem(
                base=item_data.get("base", ""), paths={}, layers=layers, global_corr=gc, crop=cr,
                mode=mode if mode in ("trichrome", "normal") else "trichrome",
                normal_layer=normal_layer,
                selected=item_data.get("selected", False), **item_kwargs))

        sort_mode = data.get("sort_mode", "import_order")
        sort_reversed = bool(data.get("sort_reversed", False))
        current_index = int(data.get("current_index", 0))
        return restored_items, sort_mode, sort_reversed, current_index

    def _set_session_file_path(self, path: str | None) -> None:
        """Sets the active session file and remembers it in QSettings as
        "the session to reopen on next launch" - see _restore_session."""
        self._session_file_path = path
        QSettings(ORG_NAME, APP_NAME).setValue("last_session_file_path", path or "")

    def save_session_to_path(self, path: str) -> None:
        self.statusBar().showMessage(i18n.tr("status_saving_session"), 1500)
        data = self._collect_session_data()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self._set_session_file_path(path)
        self._saved_edit_counter = self._edit_counter
        self._update_session_name_label()
        self._show_save_status()

    def _play_delete_sound(self) -> None:
        if sys.platform == "darwin":
            try:
                subprocess.Popen(
                    ["afplay", "/System/Library/Sounds/Pop.aiff"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    def _show_save_status(self) -> None:
        if sys.platform == "darwin":
            try:
                subprocess.Popen(
                    ["afplay", "/System/Library/Sounds/Glass.aiff"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
        self.save_status_label.setText(i18n.tr("session_saved_status"))
        self.save_status_label.setVisible(True)
        QTimer.singleShot(1000, lambda: self.save_status_label.setVisible(False))

    def _update_session_name_label(self) -> None:
        if self._session_file_path:
            name = os.path.splitext(os.path.basename(self._session_file_path))[0]
        else:
            name = i18n.tr("session_untitled_label")
        self.session_name_label.setText(i18n.tr("session_open_prefix") + name)

    def load_session_from_path(self, path: str, show_warnings: bool = True) -> None:
        """``show_warnings=False`` is used by the silent, automatic restore
        at launch (_restore_session): an empty/unreadable remembered session
        should just fall back to the legacy restore, not pop a dialog on
        every startup."""
        self.statusBar().showMessage(i18n.tr("status_loading_session"), 1500)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        restored_items, sort_mode, sort_reversed, current_index = self._build_restored_items_from_data(data)
        if not restored_items:
            if not show_warnings:
                raise ValueError(f"session file has no restorable items: {path!r}")
            show_alert(self, i18n.tr("dialog_session_load_error_title"),
                                 i18n.tr("dialog_session_load_empty"))
            return

        self.push_undo()
        prefs = data.get("preferences", {})
        settings = QSettings(ORG_NAME, APP_NAME)
        if prefs.get("last_import_dir"):
            settings.setValue("last_import_dir", prefs["last_import_dir"])
        if prefs.get("export_output_dir"):
            settings.setValue("export_output_dir", prefs["export_output_dir"])
        if "export_same_as_source" in prefs:
            settings.setValue("export_same_as_source", prefs["export_same_as_source"])

        self._apply_restored_items(restored_items, sort_mode, sort_reversed, current_index)
        self._apply_layout_state(data)
        self.scan_panel.apply_settings_snapshot(data.get("scan_settings", {}))
        self._sync_sort_menu_state()
        self.recompute_preview()
        self.canvas.zoom_fit()
        self._set_session_file_path(path)
        # A freshly-opened, unmodified session isn't "dirty" - push_undo()
        # above bumped the counter for the open action itself, so re-sync.
        self._saved_edit_counter = self._edit_counter
        self._update_session_name_label()

    def action_save_session(self) -> None:
        if self._session_file_path:
            self.save_session_to_path(self._session_file_path)
        else:
            self.action_save_session_as()

    def action_save_session_as(self) -> None:
        base_name = self._current_export_base_name() or "trichr-o-matic"
        start = self._session_file_path or base_name + "." + SESSION_FILE_EXTENSION
        path, _ = QFileDialog.getSaveFileName(
            self, i18n.tr("menu_save_session_as"), start, SESSION_FILE_FILTER)
        if not path:
            return
        if not path.lower().endswith("." + SESSION_FILE_EXTENSION):
            path += "." + SESSION_FILE_EXTENSION
        self.save_session_to_path(path)

    def action_open_session(self) -> None:
        if not self._confirm_discard_unsaved_changes():
            return
        settings = QSettings(ORG_NAME, APP_NAME)
        start_dir = settings.value("last_session_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.tr("menu_open_session"), start_dir, SESSION_FILE_FILTER)
        if not path:
            return
        settings.setValue("last_session_dir", os.path.dirname(path))
        try:
            self.load_session_from_path(path)
        except Exception as exc:
            show_alert(self, i18n.tr("dialog_session_load_error_title"),
                                  i18n.tr("dialog_session_load_error_text", error=exc))

    def _sync_global_panel_from_model(self) -> None:
        lp, cp = self.light_panel, self.color_panel
        gc = self.global_corr
        lp.block_signals_all(True)
        lp.black_point.set_value(gc.black_point)
        lp.white_point.set_value(gc.white_point)
        lp.gamma.set_value(gc.gamma)
        lp.exposure.set_value(gc.exposure)
        lp.brightness.set_value(gc.brightness)
        lp.contrast.set_value(gc.contrast)
        lp.highlights.set_value(gc.highlights)
        lp.shadows.set_value(gc.shadows)
        lp.block_signals_all(False)
        cp.block_signals_all(True)
        cp.saturation.set_value(gc.saturation)
        cp.temperature.set_value(gc.temperature)
        cp.tint.set_value(gc.tint)
        cp.block_signals_all(False)
        # CurveEditor.set_points() doesn't emit `changed` itself (only real
        # mouse interaction does), so no blockSignals dance needed here.
        self.curves_panel.set_curves(gc.curves)
        # set_black_white_active() has its own blockSignals for the toggle
        # itself and also drives the sliders/WB/Reset disabled state - not
        # folded into the block_signals_all()/set_value() dance above.
        cp.set_black_white_active(gc.black_white_active)

    def _save_session_state(self) -> None:
        """Persist every batch item (photos + their alignment/color settings)
        as a fallback for ``_legacy_restore_session`` - used on next launch
        only when there's no remembered .trirgb to reopen (see
        ``_restore_session``)."""
        settings = QSettings(ORG_NAME, APP_NAME)
        settings.remove("session_items")
        settings.beginWriteArray("session_items", len(self.batch_items))
        for i, item in enumerate(self.batch_items):
            settings.setArrayIndex(i)
            settings.setValue("base", item.base)
            settings.setValue("selected", item.selected)
            settings.setValue("uid", item.uid)
            settings.setValue("capture_date", item.capture_date if item.capture_date is not None else -1.0)
            settings.setValue("custom_order", item.custom_order if item.custom_order is not None else -1.0)
            for ci, layer in enumerate(item.layers):
                prefix = f"ch{ci}_"
                mtime = -1.0
                if layer.has_image() and layer.path:
                    try:
                        mtime = os.path.getmtime(layer.path)
                    except OSError:
                        mtime = -1.0
                settings.setValue(prefix + "path", layer.path or "")
                settings.setValue(prefix + "mtime", mtime)
                settings.setValue(prefix + "is_reference", layer.is_reference)
                settings.setValue(prefix + "invert", layer.invert)
                settings.setValue(prefix + "harris_shutter", layer.harris_shutter)
                settings.setValue(prefix + "dx", layer.dx)
                settings.setValue(prefix + "dy", layer.dy)
                settings.setValue(prefix + "scale", layer.scale)
                settings.setValue(prefix + "rotation", layer.rotation)
                settings.setValue(prefix + "black", layer.black_point)
                settings.setValue(prefix + "white", layer.white_point)
                settings.setValue(prefix + "gamma", layer.gamma)
                settings.setValue(prefix + "exposure", layer.exposure)
                settings.setValue(prefix + "brightness", layer.brightness)
                settings.setValue(prefix + "contrast", layer.contrast)
                settings.setValue(prefix + "shadows", layer.shadows)
                settings.setValue(prefix + "highlights", layer.highlights)
                settings.setValue(prefix + "quarter_turns", layer.quarter_turns)
                settings.setValue(prefix + "film_base", json.dumps(layer.film_base) if layer.film_base else "")

            nl = item.normal_layer
            normal_mtime = -1.0
            if nl.has_image() and nl.path:
                try:
                    normal_mtime = os.path.getmtime(nl.path)
                except OSError:
                    normal_mtime = -1.0
            settings.setValue("mode", item.mode)
            settings.setValue("normal_path", nl.path or "")
            settings.setValue("normal_mtime", normal_mtime)
            settings.setValue("normal_quarter_turns", nl.quarter_turns)
            settings.setValue("normal_invert", nl.invert)
            settings.setValue("normal_harris_shutter", nl.harris_shutter)
            settings.setValue("normal_film_base", json.dumps(nl.film_base) if nl.film_base else "")

            gc = item.global_corr
            settings.setValue("g_black", gc.black_point)
            settings.setValue("g_white", gc.white_point)
            settings.setValue("g_gamma", gc.gamma)
            settings.setValue("g_exposure", gc.exposure)
            settings.setValue("g_brightness", gc.brightness)
            settings.setValue("g_contrast", gc.contrast)
            settings.setValue("g_shadows", gc.shadows)
            settings.setValue("g_highlights", gc.highlights)
            settings.setValue("g_saturation", gc.saturation)
            settings.setValue("g_temperature", gc.temperature)
            settings.setValue("g_tint", gc.tint)
            settings.setValue("g_curves", json.dumps({ch: list(pts) for ch, pts in gc.curves.items()}))
            settings.setValue("g_black_white_active", gc.black_white_active)

            cr = item.crop
            settings.setValue("crop_x", cr.x)
            settings.setValue("crop_y", cr.y)
            settings.setValue("crop_width", cr.width)
            settings.setValue("crop_height", cr.height)
            settings.setValue("crop_rotation", cr.rotation)
            settings.setValue("crop_mirror_h", cr.mirror_h)
            settings.setValue("crop_mirror_v", cr.mirror_v)
            settings.setValue("crop_aspect_ratio", cr.aspect_ratio)
            settings.setValue("crop_aspect_portrait", cr.aspect_portrait)
            settings.setValue("crop_custom_ratio_w", cr.custom_ratio_w)
            settings.setValue("crop_custom_ratio_h", cr.custom_ratio_h)
        settings.endArray()
        settings.setValue("session_current_index", self.batch_current_index)
        settings.setValue("sort_mode", self.sort_mode)
        settings.setValue("sort_reversed", self.sort_reversed)
        settings.setValue("left_panel_visible", self.left_panel_toggle_btn.isChecked())
        settings.setValue("right_panel_visible", self.right_panel_toggle_btn.isChecked())
        settings.setValue("carousel_visible", self.carousel_toggle_btn.isChecked())
        settings.setValue("block_side", json.dumps(self.block_side))
        settings.setValue("block_visible", json.dumps(self.block_visible))
        settings.setValue("block_collapsed", json.dumps(self.block_collapsed))
        settings.setValue("left_block_order", json.dumps(self.left_block_order))
        settings.setValue("right_block_order", json.dumps(self.right_block_order))

    def _confirm_discard_unsaved_changes(self) -> bool:
        """Ask to save before an action that would discard the current
        session (New Session, Open Session, quitting). True: OK to proceed
        (nothing unsaved, or the user chose Save/Don't Save). False: the
        user cancelled - the caller should abort.

        Deliberately not gated on a session file already existing: the
        first time you do real work and haven't saved yet counts too, same
        as any other unsaved-changes prompt. The QSettings autosave doesn't
        change that - it's silent/implicit and not what this is asking about."""
        if self._edit_counter == self._saved_edit_counter:
            return True
        dialog = UnsavedChangesDialog(self)
        dialog.exec()
        choice = dialog.choice
        if choice == "cancel":
            return False
        if choice == "save":
            if self._session_file_path:
                self.save_session_to_path(self._session_file_path)
            else:
                self.action_save_session_as()
                if self._edit_counter != self._saved_edit_counter:
                    return False  # Save As was itself cancelled
        return True

    def action_new_session(self) -> None:
        if not self._confirm_discard_unsaved_changes():
            return
        self.push_undo()
        self._set_session_file_path(None)
        fresh_item = BatchItem(base="", paths={}, layers=new_project_layers(),
                                global_corr=GlobalCorrection(), selected=True)
        self._apply_restored_items([fresh_item], "import_order", False, 0)
        self._sync_sort_menu_state()
        self.recompute_preview()
        self.canvas.zoom_fit()
        self._update_session_name_label()
        # A fresh blank session has nothing worth losing relative to itself.
        self._saved_edit_counter = self._edit_counter

    def eventFilter(self, obj, event) -> bool:
        # Disarms the histogram pick tool on a click anywhere other than the
        # preview canvas itself (any other widget in this window, a dialog,
        # the batch window...) - it's meant to feel like a modal "point at
        # something" gesture, not a mode you have to remember to turn off.
        # Excludes the pick button's own click: without this, the filter's
        # forced setChecked(False) on the button's own press would fire
        # first, then the same click's release would toggle it straight
        # back on via QAbstractButton's normal checkable handling - the
        # button already disarms itself correctly when clicked directly.
        if (event.type() == QEvent.Type.MouseButtonPress
                and self.histogram.pick_button.isChecked()
                and obj is not self.histogram.pick_button
                and not (isinstance(obj, QWidget)
                         and (obj is self.canvas or self.canvas.isAncestorOf(obj)))):
            self.histogram.pick_button.setChecked(False)
        return super().eventFilter(obj, event)

    def closeEvent(self, event) -> None:
        if not self._confirm_discard_unsaved_changes():
            event.ignore()
            return
        QApplication.instance().removeEventFilter(self)
        self._save_session_state()
        if self.batch_window is not None:
            self.batch_window.close()
        # ScanPanel is an embedded block now, not its own top-level window,
        # so it never gets its own closeEvent() - stop its poll timer, close
        # the backlight window if open, and wait for any in-flight process
        # thread explicitly here instead.
        self.scan_panel.shutdown()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Reference / solo / active management
    # ------------------------------------------------------------------
    def _reference_layer(self):
        """The layer every "give me the composed image's own size/path"
        call site reads from - self.normal_layer while the active item is
        in Normal mode (a single already-color photo, no per-channel
        reference concept), else whichever trichrome channel is marked
        is_reference. This one change is what makes _current_crop_ratio_value/
        _composed_image_ratio/_current_export_base_name (and every other
        read-only caller of this method) correct for Normal mode too,
        without each needing its own mode check."""
        if (0 <= self.batch_current_index < len(self.batch_items)
                and self.batch_items[self.batch_current_index].mode == "normal"):
            return self.normal_layer
        for layer in self.layers:
            if layer.is_reference:
                return layer
        return self.layers[0]

    def _refresh_reference_ui(self) -> None:
        for i, layer in enumerate(self.layers):
            if layer.is_reference:
                for j, btn in enumerate(self.lock_buttons):
                    btn.blockSignals(True)
                    btn.setChecked(j == i)
                    btn.blockSignals(False)

    def on_reference_toggled(self, index: int, checked: bool) -> None:
        # Locking a channel only changes which one Auto Align treats as the
        # fixed target (see on_auto_align_all) - it must not touch anyone's
        # alignment, so manually-set positions always survive a lock change.
        if not checked:
            return
        self.push_undo()
        for i, layer in enumerate(self.layers):
            layer.is_reference = (i == index)
        self._refresh_reference_ui()
        self.recompute_preview()

    def on_solo_toggled(self, index: int, checked: bool) -> None:
        for i, layer in enumerate(self.layers):
            layer.solo = (i == index) and checked
            if i != index:
                panel = self.channel_panels[i]
                panel.solo_checkbox.blockSignals(True)
                panel.solo_checkbox.setChecked(False)
                panel.solo_checkbox.blockSignals(False)
        # Soloing a channel highlights its own scope in the histogram;
        # un-soloing (whether directly or via on_histogram_reset below)
        # brings back the full Y/R/G/B view.
        if checked:
            self.histogram.isolate_channel(CHANNEL_NAMES[index])
        else:
            self.histogram.show_all_channels()
        self.recompute_preview()

    def on_histogram_reset(self) -> None:
        """The histogram's own Reset button also turns Solo preview back
        off - Solo is what put the histogram into a single-channel scope
        in the first place (see on_solo_toggled), so "reset the histogram"
        should undo that, not just its own display."""
        for i, layer in enumerate(self.layers):
            if layer.solo:
                self.channel_panels[i].solo_checkbox.setChecked(False)
                break

    def on_invert_toggled(self, checked: bool) -> None:
        # A single Negative toggle covers all 3 channels of a photo - they're
        # normally all shot on the same stock, either all-negative or
        # all-positive - and applies to every currently-selected photo at
        # once, falling back to just the active one (_target_batch_indices,
        # same convention as on_locate_missing_files/on_harris_shutter_toggled).
        # Always sets the explicit new `checked` value on every layer, never
        # toggles each against its own prior state - so a selection with
        # mixed invert states converges on one state instead of each photo
        # flipping independently.
        targets = self._target_batch_indices()
        if not targets:
            return
        self.push_undo()
        for idx in targets:
            item = self.batch_items[idx]
            for layer in item.layers:
                layer.invert = checked
            # Always written on both, mirroring how BatchItem.layers/
            # normal_layer both always exist regardless of mode elsewhere
            # in this file - harmless on whichever one the item's own
            # mode doesn't currently read from.
            item.normal_layer.invert = checked
        if self.batch_current_index in targets:
            self.recompute_preview()
        for idx in targets:
            if idx != self.batch_current_index:
                self._refresh_carousel_thumbnail_for_item(idx)
        # Re-derive from the active photo's actual (possibly unchanged, if
        # it wasn't among targets) state, rather than trusting `checked`
        # blindly - keeps the button honest in that edge case.
        self.light_panel.set_invert(self._active_invert_state())

    def on_active_toggled(self, index: int, checked: bool) -> None:
        if checked:
            self.active_index = index
            for i, panel in enumerate(self.channel_panels):
                if i != index:
                    panel.active_checkbox.blockSignals(True)
                    panel.active_checkbox.setChecked(False)
                    panel.active_checkbox.blockSignals(False)
        elif self.active_index == index:
            self.active_index = None
        self.canvas.set_align_enabled(self.active_index is not None)

    def _active_invert_state(self) -> bool:
        """Which invert/Negative state the Light panel's button should
        show - the active item's normal_layer.invert in Normal mode
        (self.layers' own invert has no effect there, since
        _recompute_preview_normal never reads it), the trichrome layers'
        shared invert otherwise (see on_invert_toggled)."""
        if (0 <= self.batch_current_index < len(self.batch_items)
                and self.batch_items[self.batch_current_index].mode == "normal"):
            return self.normal_layer.invert
        return self.layers[0].invert

    def on_black_white_toggled(self, checked: bool) -> None:
        """ColorPanel's Black & White toggle - purely cosmetic, mode-
        agnostic (works the same on Solo or either Trichrome photo, since
        it only ever touches the final composited/corrected image, never
        how the source was decoded - see global_panel.py's module
        docstring). Applies to every currently-selected photo at once,
        falling back to the active one (_target_batch_indices, same
        convention as on_invert_toggled/on_harris_shutter_toggled) -
        always sets the explicit new `checked` state rather than toggling
        each photo against its own prior state, so a mixed-state
        selection converges on one result.

        Originally implemented (2026-09-07) by forcing
        GlobalCorrection.saturation to 0.0 - replaced the same day with a
        real grayscale conversion (imaging.apply_black_white, applied as
        the pipeline's very last step in recompute_preview/
        compose_trichrome/compose_normal) once the user asked what the
        actual difference was: this app's saturation slider works in HSV
        space, so saturation=0 only grays a pixel to HSV's V
        (max(R,G,B)), not a true perceptually-weighted luminance - a
        saturated red and a saturated blue at the same V would read as
        identical grays, which a real B&W conversion (and the human eye)
        wouldn't. `saturation` itself is now left completely untouched by
        this toggle; only `GlobalCorrection.black_white_active` changes.

        The old "Solo N&B" mechanism this once coexisted with (Files'
        bw_film_button/color_film_button forcing saturation via
        on_harris_shutter_toggled, and ColorPanel.set_disabled_message's
        full-block disable) was retired entirely 2026-09-07, once the
        user settled on this toggle as the *only* way to make a photo
        read as B&W, in any mode - see CLAUDE.md's "Mode selector"
        section for the full history. This method and its field
        (GlobalCorrection.black_white_active) are now the sole
        mechanism, with nothing left to coexist with."""
        targets = self._target_batch_indices()
        if not targets:
            return
        self.push_undo()
        for idx in targets:
            gc = self.batch_items[idx].global_corr
            if gc.black_white_active == checked:
                continue
            gc.black_white_active = checked
            if idx != self.batch_current_index:
                self._refresh_carousel_thumbnail_for_item(idx)
        if self.batch_current_index in targets:
            self._sync_global_panel_from_model()
            self.recompute_preview()
        else:
            # The active photo wasn't targeted - keep the button honest
            # against whatever it actually holds, rather than the clicked
            # state.
            self.color_panel.set_black_white_active(self.global_corr.black_white_active)

    # ------------------------------------------------------------------
    # Alignment / tone parameter changes from the panels
    # ------------------------------------------------------------------
    def _sync_panel_from_layer(self, index: int) -> None:
        layer = self.layers[index]
        panel = self.channel_panels[index]
        panel.block_align_signals(True)
        panel.dx.set_value(layer.dx)
        panel.dy.set_value(layer.dy)
        panel.scale.set_value(layer.scale)
        panel.rotation.set_value(layer.rotation)
        panel.block_align_signals(False)

        panel.block_tone_signals(True)
        panel.black_point.set_value(layer.black_point)
        panel.white_point.set_value(layer.white_point)
        panel.gamma.set_value(layer.gamma)
        panel.exposure.set_value(layer.exposure)
        panel.brightness.set_value(layer.brightness)
        panel.contrast.set_value(layer.contrast)
        panel.highlights.set_value(layer.highlights)
        panel.shadows.set_value(layer.shadows)
        panel.block_tone_signals(False)

    def on_align_changed(self, index: int) -> None:
        self._push_undo_coalesced(f"align_{self.batch_current_index}_{index}")
        layer = self.layers[index]
        panel = self.channel_panels[index]
        layer.dx = panel.dx.value()
        layer.dy = panel.dy.value()
        layer.scale = panel.scale.value()
        layer.rotation = panel.rotation.value()
        self.recompute_preview()

    def on_tone_changed(self, index: int) -> None:
        self._push_undo_coalesced(f"tone_{self.batch_current_index}_{index}")
        layer = self.layers[index]
        panel = self.channel_panels[index]
        layer.black_point = panel.black_point.value()
        layer.white_point = panel.white_point.value()
        layer.gamma = panel.gamma.value()
        layer.exposure = panel.exposure.value()
        layer.brightness = panel.brightness.value()
        layer.contrast = panel.contrast.value()
        layer.highlights = panel.highlights.value()
        layer.shadows = panel.shadows.value()
        self.recompute_preview()

    def on_reset_align(self, index: int) -> None:
        self.push_undo()
        self.layers[index].reset_alignment()
        self._sync_panel_from_layer(index)
        self.recompute_preview()

    def on_reset_tone(self, index: int) -> None:
        self.push_undo()
        self.layers[index].reset_tone()
        self._sync_panel_from_layer(index)
        self.recompute_preview()

    def on_reset_all_alignment(self) -> None:
        self.push_undo()
        for i, layer in enumerate(self.layers):
            layer.reset_alignment()
            self._sync_panel_from_layer(i)
        self.recompute_preview()

    def on_reset_all_color(self) -> None:
        self.push_undo()
        for i, layer in enumerate(self.layers):
            layer.reset_tone()
            self._sync_panel_from_layer(i)
        self.recompute_preview()

    def on_harris_shutter_toggled(self, checked: bool) -> None:
        """Harris Shutter/Trichrome decode strategy is per-item state
        (ChannelLayer.harris_shutter, kept identical across a photo's 3
        Trichrome channels - see the field's own docstring in model.py),
        not one session-wide flag - so this applies to every currently-
        selected photo at once, falling back to just the active one
        (_target_batch_indices, same convention as
        on_locate_missing_files/on_invert_toggled). Always sets the
        explicit new `checked` value, never toggles against prior state,
        so a selection with mixed harris_shutter states converges on one
        state instead of each photo flipping independently.

        **Trichrome-only, Solo items in the target selection are skipped
        entirely (2026-09-07).** This used to also drive a "Solo N&B"
        cosmetic mechanism (forcing GlobalCorrection.saturation to 0 via
        Files' now-removed bw_film_button/color_film_button) - retired per
        the user's own explicit direction: the Mode combo is now the only
        indicator of whether Trichrome photos should be processed as B&W
        or Color (Harris Shutter Effect); Solo's own cosmetic B&W concept
        lives entirely in ColorPanel.black_white_button/
        MainWindow.on_black_white_toggled now, fully independent of this
        method - see CLAUDE.md's "Mode selector" section for the full
        history. Reloads each channel that has a real loaded image from
        disk under the new interpretation (luminance vs. its own R/G/B
        channel - see imaging.load_grayscale). Future loads (single
        manual load or batch import) pick up the new Trichrome mode
        automatically since they all read
        ImportPanel.is_harris_shutter_active() at load time."""
        targets = self._target_batch_indices()
        if not targets:
            return
        self.push_undo()
        for idx in targets:
            item = self.batch_items[idx]
            if item.mode == "normal":
                continue
            item_reloaded = False
            for ci, layer in enumerate(item.layers):
                layer.harris_shutter = checked
                if not layer.path or not os.path.isfile(layer.path):
                    continue
                channel = CHANNEL_NAMES[ci] if checked else None
                try:
                    full = imaging.load_grayscale(layer.path, channel=channel)
                except Exception:
                    continue
                full = imaging.apply_film_base_correction(full, layer.film_base, channel=CHANNEL_NAMES[ci])
                if layer.quarter_turns:
                    full = np.ascontiguousarray(np.rot90(full, layer.quarter_turns))
                preview, preview_scale = imaging.make_preview(full)
                layer.image_preview = preview
                layer.preview_scale = preview_scale
                if layer.image_full is not None:
                    layer.image_full = full
                item_reloaded = True
            if item_reloaded and idx != self.batch_current_index:
                self._refresh_carousel_thumbnail_for_item(idx)
        if self.batch_current_index in targets:
            self._sync_global_panel_from_model()
            self.recompute_preview()
        # Re-derive from the active photo's actual (possibly unchanged, if
        # it wasn't among targets) state, rather than trusting `checked`
        # blindly - keeps the Mode combo honest in that edge case.
        self._sync_import_and_channels_ui()

    def on_rotate_right(self) -> None:
        self._rotate_all_channels(clockwise=True)

    def on_rotate_left(self) -> None:
        self._rotate_all_channels(clockwise=False)

    def _rotate_all_channels(self, clockwise: bool) -> None:
        is_normal_mode = (0 <= self.batch_current_index < len(self.batch_items)
                           and self.batch_items[self.batch_current_index].mode == "normal")
        if is_normal_mode:
            if not self.normal_layer.has_image():
                return
            self.push_undo()
            self.normal_layer.rotate_quarter(clockwise)
            self.recompute_preview()
            self.canvas.zoom_fit()
            self._refresh_carousel_thumbnail_for_item(self.batch_current_index)
            return
        if not any(l.has_image() for l in self.layers):
            return
        self.push_undo()
        for i, layer in enumerate(self.layers):
            layer.rotate_quarter(clockwise)
            self._sync_panel_from_layer(i)
        self.recompute_preview()
        self.canvas.zoom_fit()
        self._refresh_carousel_thumbnail_for_item(self.batch_current_index)

    def on_global_changed(self) -> None:
        self._push_undo_coalesced(f"global_{self.batch_current_index}")
        lp, cp = self.light_panel, self.color_panel
        gc = self.global_corr
        gc.black_point = lp.black_point.value()
        gc.white_point = lp.white_point.value()
        gc.gamma = lp.gamma.value()
        gc.exposure = lp.exposure.value()
        gc.brightness = lp.brightness.value()
        gc.contrast = lp.contrast.value()
        gc.highlights = lp.highlights.value()
        gc.shadows = lp.shadows.value()
        gc.saturation = cp.saturation.value()
        gc.temperature = cp.temperature.value()
        gc.tint = cp.tint.value()
        self.recompute_preview()

    def on_reset_white_balance(self) -> None:
        """Resets every "Color" slider (Temperature, Tint, Saturation) -
        broadened from just temperature/tint so this button's scope matches
        its position next to the whole "Color" subheader, not only the
        white-balance pair."""
        gc = self.global_corr
        if not gc.has_color_correction():
            return
        self.push_undo()
        gc.temperature = 0.0
        gc.tint = 0.0
        gc.saturation = 1.0
        self._sync_global_panel_from_model()
        self.recompute_preview()

    def on_reset_light(self) -> None:
        gc = self.global_corr
        if not gc.has_light_correction():
            return
        self.push_undo()
        gc.black_point = 0.0
        gc.white_point = 0.0
        gc.gamma = 1.0
        gc.exposure = 0.0
        gc.brightness = 0.0
        gc.contrast = 1.0
        gc.shadows = 0.0
        gc.highlights = 0.0
        self._sync_global_panel_from_model()
        self.recompute_preview()

    def on_pick_white_balance_toggled(self, checked: bool) -> None:
        self.canvas.set_wb_pick_enabled(checked)

    def on_white_balance_picked(self, u: float, v: float) -> None:
        """Solves and applies the (temperature, tint) that neutralizes the
        pixel clicked at normalized canvas position (u, v) - see
        imaging.solve_white_balance. Single-shot: the picker tool disarms
        itself after one click, Lightroom-style."""
        self.color_panel.set_pick_white_balance_active(False)
        self.canvas.set_wb_pick_enabled(False)

        ref = self._reference_layer()
        if ref is None or not ref.has_image():
            return
        gc = self.global_corr
        global_params = (gc.black_point, gc.white_point, gc.gamma, gc.exposure, gc.brightness, gc.contrast,
                          gc.shadows, gc.highlights, gc.saturation, gc.temperature, gc.tint,
                          {ch: tuple(pts) for ch, pts in gc.curves.items()}, gc.black_white_active)
        is_normal = (0 <= self.batch_current_index < len(self.batch_items)
                     and self.batch_items[self.batch_current_index].mode == "normal")
        if is_normal:
            # No warp/recompose step in Normal mode - ref (the single
            # already-color photo) already IS the pre-recompose image, so
            # this is just the tone-curve stage compose_pre_white_balance_rgb
            # would otherwise apply on top of the trichrome recompose.
            (gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights, *_rest) = global_params
            pre_wb = imaging.apply_tone_curve(
                imaging.apply_invert(ref.image_preview, ref.invert),
                gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights)
        else:
            images = [l.image_preview if l.has_image() else None for l in self.layers]
            geo_params = [(l.dx, l.dy, l.scale, l.rotation) for l in self.layers]
            tone_params = [(l.black_point, l.white_point, l.gamma, l.exposure, l.brightness, l.contrast,
                            l.shadows, l.highlights, l.invert) for l in self.layers]
            pre_wb = imaging.compose_pre_white_balance_rgb(
                images, geo_params, tone_params, ref.color_index, global_params)
        # (u, v) are normalized against what's actually on screen - the
        # straightened/mirrored/cropped frame, same as recompute_preview.
        pre_wb = imaging.apply_straighten_mirror(pre_wb, self.crop.rotation, self.crop.mirror_h, self.crop.mirror_v)
        if not self._crop_active:
            pre_wb = imaging.apply_crop_rect(pre_wb, self.crop.x, self.crop.y, self.crop.width, self.crop.height)

        h, w = pre_wb.shape[:2]
        if h == 0 or w == 0:
            return
        px = min(max(int(u * w), 0), w - 1)
        py = min(max(int(v * h), 0), h - 1)
        r, g, b = (float(x) for x in pre_wb[py, px])

        result = imaging.solve_white_balance(r, g, b)
        if result is None:
            self.statusBar().showMessage(i18n.tr("white_balance_pick_failed"), 3000)
            return

        self.push_undo()
        self.global_corr.temperature, self.global_corr.tint = result
        self._sync_global_panel_from_model()
        self.recompute_preview()
        self.statusBar().showMessage(i18n.tr("white_balance_picked"), 3000)

    def _active_item_valid_for_film_base_pick(self):
        """Returns the active BatchItem if it has real image data to pick a
        film-base reference from (either mode - widened 2026-09-04 from
        Trichrome-only), else None."""
        if not (0 <= self.batch_current_index < len(self.batch_items)):
            return None
        item = self.batch_items[self.batch_current_index]
        if item.mode == "trichrome" and all(l.has_image() for l in item.layers):
            return item
        if item.mode == "normal" and item.normal_layer.has_image():
            return item
        return None

    def on_pick_film_base_from_photo_toggled(self, checked: bool) -> None:
        """The Scan tool's eyedropper alternative to a dedicated 3-shot
        Sample Film Base capture - validated *here*, at arm time, rather
        than only on click, so an invalid active photo gives immediate
        feedback instead of arming a tool that can only fail later. Works
        on a Trichrome photo (all 3 channels loaded) or a Normal-mode one
        (its own composited image) - widened 2026-09-04, see the "film
        base on Normal mode" entry in CLAUDE.md."""
        if checked and self._active_item_valid_for_film_base_pick() is None:
            self.scan_panel.set_pick_from_photo_active(False)
            show_alert(self, i18n.tr("scan_error_title"), i18n.tr("scan_pick_film_base_requires_photo"))
            return
        self.canvas.set_film_base_pick_enabled(checked)

    def on_film_base_pick_requested(self, u: float, v: float) -> None:
        """Samples the Scan tool's film-base reference from a point on the
        *active* photo, instead of a dedicated calibration capture - see
        ScanPanel.set_film_base_from_pick and the "Sample Film Base"
        section in CLAUDE.md for why this reference (and not a post-invert
        white-balance pick) is what actually corrects color negative's
        orange mask. Single-shot, like the white balance/histogram
        eyedroppers - disarms itself immediately.

        Trichrome: each channel is warped to canvas space first
        (imaging.build_similarity_matrix/warp_to_canvas, the same per-
        channel math recompute_preview's own composite path uses) before
        sampling - required for correctness whenever the photo has real
        per-channel alignment (e.g. after running Auto Align), where the
        same (u, v) canvas position maps to a *different* raw pixel in
        each channel's own, differently-warped array. Normal mode: no warp
        needed (one image, not 3 separately-aligned channels) - just reads
        its own R/G/B pixel value directly, straighten/mirror/crop applied
        the same way on_white_balance_picked's Normal-mode branch already
        does. Either way, reads raw density directly (no invert/tone-curve
        applied) - the same kind of quantity a dedicated 3-shot sample
        already stores."""
        self.scan_panel.set_pick_from_photo_active(False)
        self.canvas.set_film_base_pick_enabled(False)

        item = self._active_item_valid_for_film_base_pick()
        if item is None:
            return

        if item.mode == "normal":
            img = imaging.apply_straighten_mirror(
                item.normal_layer.image_preview, self.crop.rotation, self.crop.mirror_h, self.crop.mirror_v)
            if not self._crop_active:
                img = imaging.apply_crop_rect(img, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
            hh, ww = img.shape[:2]
            if hh == 0 or ww == 0:
                return
            px = min(max(int(u * ww), 0), ww - 1)
            py = min(max(int(v * hh), 0), hh - 1)
            r, g, b = (float(x) for x in img[py, px])
            base = {"R": r, "G": g, "B": b}
        else:
            ref = self._reference_layer()
            canvas_h, canvas_w = ref.image_preview.shape[:2]
            canvas_size = (canvas_w, canvas_h)
            base = {}
            for letter, layer in zip(CHANNEL_NAMES, item.layers):
                h, w = layer.image_preview.shape[:2]
                matrix = imaging.build_similarity_matrix(
                    layer.dx, layer.dy, layer.scale, layer.rotation,
                    src_center=(w / 2, h / 2), dst_center=(canvas_w / 2, canvas_h / 2))
                warped = imaging.warp_to_canvas(layer.image_preview, matrix, canvas_size)
                warped = imaging.apply_straighten_mirror(
                    warped, self.crop.rotation, self.crop.mirror_h, self.crop.mirror_v)
                if not self._crop_active:
                    warped = imaging.apply_crop_rect(
                        warped, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
                hh, ww = warped.shape[:2]
                if hh == 0 or ww == 0:
                    return
                px = min(max(int(u * ww), 0), ww - 1)
                py = min(max(int(v * hh), 0), hh - 1)
                base[letter] = float(warped[py, px])

        self.scan_panel.set_film_base_from_pick(base)
        self.statusBar().showMessage(i18n.tr("status_film_base_picked"), 3000)

    def on_apply_film_base_requested(self) -> None:
        """The "a posteriori" case: applies the Scan tool's currently
        sampled/picked film-base reference to already-imported photo(s) -
        the selected carousel photos, falling back to just the active one
        (_target_batch_indices, same convention as on_invert_toggled/
        on_harris_shutter_toggled) - regardless of how they got into the
        session (Scan tool auto-add, manual Add Photo, drag-and-drop,
        batch import...). Reloads each target's own source file(s) from
        disk and re-applies imaging.apply_film_base_correction, same as a
        fresh Scan-tool import would - see ChannelLayer.film_base's
        docstring in model.py for why this needs a real reload rather than
        a live transform. One bad/missing file among several targets
        doesn't block the rest, same "load what you can, report the rest"
        convention as on_carousel_files_dropped."""
        film_base = self.scan_panel.film_base()
        if film_base is None:
            return
        targets = self._target_batch_indices()
        if not targets:
            return
        self.push_undo()
        applied = 0
        failed = []
        for idx in targets:
            item = self.batch_items[idx]
            if item.mode == "trichrome":
                ok = self._apply_film_base_to_trichrome_item(item, film_base)
            else:
                ok = self._apply_film_base_to_normal_item(item, film_base)
            if ok:
                applied += 1
            else:
                failed.append(item.base or "?")
            if idx != self.batch_current_index:
                self._refresh_carousel_thumbnail_for_item(idx)
        if self.batch_current_index in targets:
            self.recompute_preview()
        if applied:
            self.statusBar().showMessage(i18n.tr("status_film_base_applied", n=applied), 4000)
        if failed:
            show_alert(self, i18n.tr("dialog_load_error_title"),
                       i18n.tr("dialog_drop_photos_failed_text", files=", ".join(failed)))

    def _apply_film_base_to_trichrome_item(self, item, film_base: dict) -> bool:
        """Reloads all 3 channels of ``item`` from their own source files
        and re-applies ``film_base`` to each - requires every channel's
        file to still exist (a partial reload would leave the trichrome
        recompose using a stale, uncorrected channel alongside 2 corrected
        ones, a worse outcome than just reporting failure)."""
        if not all(l.path and os.path.isfile(l.path) for l in item.layers):
            return False
        for letter, layer in zip(CHANNEL_NAMES, item.layers):
            try:
                full = imaging.load_grayscale(
                    layer.path, channel=CHANNEL_NAMES[layer.color_index] if layer.harris_shutter else None)
            except Exception:
                return False
            layer.film_base = dict(film_base)
            full = imaging.apply_film_base_correction(full, layer.film_base, channel=letter)
            if layer.quarter_turns:
                full = np.ascontiguousarray(np.rot90(full, layer.quarter_turns))
            preview, preview_scale = imaging.make_preview(full)
            layer.image_full = full
            layer.image_preview = preview
            layer.preview_scale = preview_scale
        return True

    def _apply_film_base_to_normal_item(self, item, film_base: dict) -> bool:
        nl = item.normal_layer
        if not nl.path or not os.path.isfile(nl.path):
            return False
        try:
            full = imaging.load_color(nl.path)
        except Exception:
            return False
        nl.film_base = dict(film_base)
        full = imaging.apply_film_base_correction(full, nl.film_base)
        if nl.quarter_turns:
            full = np.ascontiguousarray(np.rot90(full, nl.quarter_turns))
        preview, preview_scale = imaging.make_preview(full)
        nl.image_full = full
        nl.image_preview = preview
        nl.preview_scale = preview_scale
        return True

    def on_histogram_pixel_hovered(self, u: float, v: float) -> None:
        """Live readout for the histogram's own pick tool - unlike the
        white-balance eyedropper this doesn't change anything, just samples
        whatever's already displayed (self._last_preview_rgb_u8, the exact
        array last handed to canvas/histogram) at the hovered normalized
        position and marks it on the chart. No-op before any image exists."""
        if self._last_preview_rgb_u8 is None:
            return
        h, w = self._last_preview_rgb_u8.shape[:2]
        if h == 0 or w == 0:
            return
        x = min(max(int(u * w), 0), w - 1)
        y = min(max(int(v * h), 0), h - 1)
        r, g, b = (int(c) for c in self._last_preview_rgb_u8[y, x, :3])
        self.histogram.set_marker(r, g, b)

    def on_histogram_pixel_left(self) -> None:
        self.histogram.clear_marker()

    # ------------------------------------------------------------------
    # Crop tool
    # ------------------------------------------------------------------
    def _set_crop_active(self, active: bool) -> None:
        """The single place "active crop mode" (the interactive draggable
        overlay on the canvas, Enter-to-apply, and the full-vs-cropped
        preview frame) is armed or disarmed - self._crop_active is the one
        source of truth. Decoupled from the Crop block's own visibility
        (2026-09-04): the block can now be shown in any custom layout
        alongside anything else, so tying active mode to block-visible
        alone made the crop overlay pop on/off unexpectedly as blocks were
        dragged around or layouts switched. Reachable from: the Crop
        block's own activate button (crop_panel.activate_toggled), Escape
        (off only - never touches layout/visibility), on_crop_apply (off,
        after committing), _activate_default_layout (on only when loading
        the "Crop" slot, off for every other layout), reset_layout, and
        _apply_restored_layout (both always turn it off - loading any
        layout counts as "changing layout"), and set_block_visible (off,
        if the Crop block itself gets hidden while active).

        Activating also force-shows the Crop block via set_block_visible
        (there's no point arming an invisible tool) - but deactivating
        never touches visibility, since that would be a layout change,
        which Escape/apply deliberately are not."""
        if active:
            self.set_block_visible("crop", True)
        self._crop_active = active
        self.crop_panel.set_active(active)
        self.canvas.set_crop_enabled(active)
        if active:
            # Crop dragging and the click-to-sample eyedroppers (white
            # balance, film base) are mutually exclusive canvas click
            # modes - disarm them if left armed.
            self.color_panel.set_pick_white_balance_active(False)
            self.canvas.set_wb_pick_enabled(False)
            self.scan_panel.set_pick_from_photo_active(False)
            self.canvas.set_film_base_pick_enabled(False)
            self._sync_crop_panel_from_item()
        # The full-vs-cropped frame shown in the preview depends on whether
        # crop mode is active (see recompute_preview) - refresh either way.
        self.recompute_preview()

    def _current_crop_ratio_value(self) -> float | None:
        """Like CropSettings.ratio_value(), but resolves "original" (the
        photo's own composed aspect ratio) using the actual image size,
        which the model alone can't know."""
        if self.crop.aspect_ratio == "original":
            ref = self._reference_layer()
            if not ref.has_image():
                return None
            h, w = ref.image_preview.shape[:2]
            ratio = (w / h) if h else None
            if ratio and self.crop.aspect_portrait:
                ratio = 1.0 / ratio
            return ratio
        return self.crop.ratio_value()

    def _composed_image_ratio(self) -> float | None:
        """The composed image's own real width/height - needed to convert a
        target *real* aspect ratio into the crop rect's normalized [0,1]
        width/height (which are fractions of the image's width and height
        respectively, not the same unit unless the image happens to be
        square)."""
        ref = self._reference_layer()
        if not ref.has_image():
            return None
        h, w = ref.image_preview.shape[:2]
        return (w / h) if h else None

    def _sync_crop_panel_from_item(self) -> None:
        """Seeds the crop panel's controls and the canvas overlay from the
        active photo's currently-applied crop - called whenever the Crop
        tool becomes active, or the active photo changes while it already is."""
        self.crop_panel.set_from_crop(self.crop)
        self.canvas.set_crop_ratio(self._current_crop_ratio_value())
        self.canvas.set_crop_grid(self.crop_panel.grid_mode())
        self.canvas.set_crop_rect(self.crop.x, self.crop.y, self.crop.width, self.crop.height)

    def on_crop_settings_changed(self) -> None:
        """Straighten/mirror/aspect-ratio/grid - these apply live, unlike
        the crop rect itself which only takes effect on Enter (see
        on_crop_apply)."""
        self._push_undo_coalesced(f"crop_{self.batch_current_index}")
        panel = self.crop_panel
        self.crop.rotation = panel.straighten_value()
        self.crop.mirror_h = panel.is_mirrored_h()
        self.crop.mirror_v = panel.is_mirrored_v()
        self.crop.aspect_ratio = panel.aspect_ratio()
        self.crop.custom_ratio_w, self.crop.custom_ratio_h = panel.custom_ratio()
        ratio = self._current_crop_ratio_value()
        self.canvas.set_crop_ratio(ratio)
        self.canvas.set_crop_grid(panel.grid_mode())
        if ratio:
            # Reshape the still-proposed (not yet applied) overlay rect to
            # the new ratio too, anchored at its current top-left corner.
            # ratio is a *real* pixel width/height; w/h here are normalized
            # fractions of the image's own width/height, which only match
            # real proportions once corrected by the image's own aspect
            # ratio (image_ratio) - see _composed_image_ratio().
            image_ratio = self._composed_image_ratio() or 1.0
            x, y, w, h = self.canvas.crop_rect()
            h = min(w * image_ratio / ratio, 1.0 - y)
            w = h * ratio / image_ratio
            self.canvas.set_crop_rect(x, y, w, h)
        self.recompute_preview()

    def on_crop_orientation_invert(self) -> None:
        self.push_undo()
        self.crop.aspect_portrait = not self.crop.aspect_portrait
        self.crop_panel.set_from_crop(self.crop)
        self.on_crop_settings_changed()

    def on_crop_apply(self) -> None:
        """Commits the interactively-dragged overlay rect as this photo's
        actual crop - bound to Enter while active crop mode is on - then
        turns active crop mode off, same as Escape, so the composited
        result isn't obscured by the drag overlay. Deliberately does NOT
        hide the Crop block/change layout (2026-09-04) - only Escape and
        Enter's shared _set_crop_active(False) call, never
        set_block_visible directly."""
        self.push_undo()
        self.crop.x, self.crop.y, self.crop.width, self.crop.height = self.canvas.crop_rect()
        self.statusBar().showMessage(i18n.tr("status_crop_applied"), 4000)
        self._set_crop_active(False)

    def on_crop_reset(self) -> None:
        self.push_undo()
        self.crop.reset()
        self._sync_crop_panel_from_item()
        self.recompute_preview()

    def on_curve_changed(self) -> None:
        """Fires continuously while a curve point is being dragged - same
        coalesced-undo convention as a slider drag, keyed per-photo *and*
        per-channel so dragging Y then immediately dragging R doesn't
        coalesce into a single undo step covering both. The model is
        updated immediately (cheap) on every call, but the expensive
        recompute_preview() itself is throttled (see
        _CURVE_RECOMPUTE_THROTTLE_MS) - CurveEditor's own on-screen curve
        already redrew itself instantly before this even ran, so the
        throttle only affects how quickly the *image* preview catches up,
        not how responsive the curve itself feels under the cursor."""
        self._push_undo_coalesced(f"curve_{self.batch_current_index}_{self.curves_panel.active_channel()}")
        self.global_corr.curves = self.curves_panel.curves()
        if not self._curve_recompute_timer.isActive():
            self._curve_recompute_timer.start(_CURVE_RECOMPUTE_THROTTLE_MS)

    def on_curve_reset(self) -> None:
        """Resets all 4 channel curves at once, matching every other
        block's own "reset everything this block controls" convention -
        not just whichever channel happens to be selected right now."""
        self.push_undo()
        self.global_corr.curves = {ch: [(0.0, 0.0), (1.0, 1.0)] for ch in _CURVE_CHANNELS}
        self.curves_panel.set_curves(self.global_corr.curves)
        self.recompute_preview()

    # ------------------------------------------------------------------
    # Canvas mouse/wheel interaction on the active layer
    # ------------------------------------------------------------------
    def on_canvas_drag(self, dx: float, dy: float) -> None:
        if self.active_index is None:
            return
        layer = self.layers[self.active_index]
        self._push_undo_coalesced(f"canvas_{self.batch_current_index}_{self.active_index}")
        layer.dx += dx
        layer.dy += dy
        self._sync_panel_from_layer(self.active_index)
        self.recompute_preview()

    def on_canvas_scale(self, factor: float) -> None:
        if self.active_index is None:
            return
        layer = self.layers[self.active_index]
        self._push_undo_coalesced(f"canvas_{self.batch_current_index}_{self.active_index}")
        layer.scale = max(0.1, min(5.0, layer.scale * factor))
        self._sync_panel_from_layer(self.active_index)
        self.recompute_preview()

    def on_canvas_rotate(self, degrees: float) -> None:
        if self.active_index is None:
            return
        layer = self.layers[self.active_index]
        self._push_undo_coalesced(f"canvas_{self.batch_current_index}_{self.active_index}")
        layer.rotation = max(-45.0, min(45.0, layer.rotation + degrees))
        self._sync_panel_from_layer(self.active_index)
        self.recompute_preview()

    # ------------------------------------------------------------------
    # Auto alignment
    # ------------------------------------------------------------------
    def on_auto_align_all(self) -> None:
        # Not reachable via the UI while the active item is in Normal mode
        # (the Auto Align button lives in ImportPanel's trichrome-only
        # container, hidden then) - guarded anyway since _reference_layer()
        # would otherwise return self.normal_layer here, which has no
        # is_reference-based "other 2 channels to align" concept at all.
        if (0 <= self.batch_current_index < len(self.batch_items)
                and self.batch_items[self.batch_current_index].mode == "normal"):
            return
        ref = self._reference_layer()
        targets = [i for i, layer in enumerate(self.layers) if not layer.is_reference]
        if not ref.has_image() or any(not self.layers[i].has_image() for i in targets):
            show_alert(self, i18n.tr("dialog_alignment_title"),
                                 i18n.tr("dialog_alignment_missing_images"))
            return

        self.statusBar().showMessage(i18n.tr("status_auto_align_running_all"))
        # auto_align() matches raw, untransformed pixels - it knows nothing of
        # the locked channel's own (possibly non-identity) manual alignment.
        # Compose its result with the locked channel's transform so the other
        # two land on where it actually ends up on the canvas, not on its raw
        # pixel grid.
        ref_h, ref_w = ref.image_preview.shape[:2]
        ref_center = (ref_w / 2, ref_h / 2)
        ref_matrix = imaging.build_similarity_matrix(
            ref.dx, ref.dy, ref.scale, ref.rotation, src_center=ref_center, dst_center=ref_center)

        results: dict[int, tuple[float, float, float, float]] = {}
        failed_channels = []
        for index in targets:
            layer = self.layers[index]
            try:
                matrix = alignment.auto_align(ref.image_preview, layer.image_preview)
            except alignment.AlignmentError:
                failed_channels.append(i18n.channel_name(index))
                continue
            h, w = layer.image_preview.shape[:2]
            final_matrix = imaging.compose_affine(ref_matrix, matrix)
            results[index] = imaging.decompose_similarity_matrix(
                final_matrix, src_center=(w / 2, h / 2), dst_center=ref_center,
            )

        if results:
            self.push_undo()
            for index, (dx, dy, scale, rotation) in results.items():
                layer = self.layers[index]
                layer.dx, layer.dy, layer.scale, layer.rotation = dx, dy, scale, rotation
                self._sync_panel_from_layer(index)
            self.recompute_preview()

        if failed_channels:
            show_alert(self, i18n.tr("dialog_auto_align_title"),
                                 i18n.tr("dialog_auto_align_failed_channels", channels=", ".join(failed_channels)))
            self.statusBar().showMessage(i18n.tr("status_auto_align_failed"), 5000)
        else:
            self.statusBar().showMessage(i18n.tr("status_auto_align_all_done"), 5000)

    # ------------------------------------------------------------------
    # Compositing pipeline (preview resolution)
    # ------------------------------------------------------------------
    def recompute_preview(self, update_curve_reference: bool = True) -> None:
        """``update_curve_reference`` gates whether the Curves tool's own
        "input" reference-histogram overlay (curves_panel.set_reference_histogram)
        gets refreshed this call - it must be True for every ordinary
        recompute (a photo switch, a slider drag, anything upstream of the
        curve changing) but False for the throttled recompute a live curve
        drag itself triggers (_curve_recompute_timer, see on_curve_changed):
        the whole point of that histogram is that it reflects the pipeline's
        state *before* the curve, so it must never move while the curve
        itself is being dragged - see the user's own requirement, quoted in
        CLAUDE.md's Curves tool section. Skipping it on a curve-only tick
        also avoids paying for a second straighten/crop/to_uint8 pass that
        would just get thrown away unused."""
        self.light_panel.reset_button.setEnabled(self.global_corr.has_light_correction())
        # Never re-enable Color's own Reset while the B&W toggle has it
        # partially disabled - has_color_correction() doesn't know about
        # that state, so left unguarded this would silently reactivate the
        # button the moment any *other* edit (e.g. a Light slider) called
        # recompute_preview, even though set_black_white_active already
        # turned it off.
        if not self.global_corr.black_white_active:
            self.color_panel.reset_button.setEnabled(self.global_corr.has_color_correction())
        self.crop_panel.reset_button.setEnabled(self.crop.has_crop())
        self.curves_panel.reset_button.setEnabled(self.global_corr.has_curve_correction())

        is_normal_mode = (0 <= self.batch_current_index < len(self.batch_items)
                           and self.batch_items[self.batch_current_index].mode == "normal")
        if is_normal_mode:
            # Alignment/per-channel-tone reset buttons have nothing to
            # reflect in Normal mode (no channels to align, RGB Channels is
            # disabled) - always greyed rather than reading stale state from
            # whatever self.layers happen to still hold.
            self.missing_files_banner.set_missing(
                [(i18n.tr("normal_photo_label"), self.normal_layer.path)]
                if self.normal_layer.is_missing() else [])
            self.reset_all_alignment_button.setEnabled(False)
            self.reset_all_color_button.setEnabled(False)
            for panel in self.channel_panels:
                panel.reset_align_button.setEnabled(False)
                panel.reset_tone_button.setEnabled(False)
            self._recompute_preview_normal(update_curve_reference)
            return

        self.missing_files_banner.set_missing(
            [(l.label, l.path) for l in self.layers if l.is_missing()])
        self.reset_all_alignment_button.setEnabled(
            any(l.has_alignment_correction() for l in self.layers))
        self.reset_all_color_button.setEnabled(
            any(l.has_tone_correction() for l in self.layers))
        for i, layer in enumerate(self.layers):
            panel = self.channel_panels[i]
            panel.reset_align_button.setEnabled(layer.has_alignment_correction())
            panel.reset_tone_button.setEnabled(layer.has_tone_correction())
        ref = self._reference_layer()
        if not ref.has_image():
            # No reference image yet: fall back to any loaded channel so the
            # user sees a (single-color-tinted) preview from the first import.
            ref = next((l for l in self.layers if l.has_image()), None)
        if ref is None:
            self.canvas.clear_image()
            self.histogram.clear()
            self._last_preview_rgb_u8 = None
            return

        canvas_h, canvas_w = ref.image_preview.shape[:2]
        canvas_size = (canvas_w, canvas_h)

        solo_layer = next((l for l in self.layers if l.solo), None)
        if solo_layer is not None:
            if not solo_layer.has_image():
                self.canvas.clear_image()
                self.histogram.clear()
                self._last_preview_rgb_u8 = None
                return
            warped, pre_curve_toned, gcurve = self._warp_and_tone(solo_layer, canvas_size, ref)
            mask = imaging.warp_coverage_mask(
                solo_layer.image_preview.shape[:2],
                (solo_layer.dx, solo_layer.dy, solo_layer.scale, solo_layer.rotation), canvas_size)
            toned = imaging.apply_curve(pre_curve_toned, gcurve)
            toned = imaging.apply_straighten_mirror(toned, self.crop.rotation, self.crop.mirror_h, self.crop.mirror_v)
            mask = imaging.apply_straighten_mirror(mask, self.crop.rotation, self.crop.mirror_h, self.crop.mirror_v)
            if not self._crop_active:
                # Only crop to the final rect outside active crop mode -
                # while it's active the full (straightened/mirrored) frame
                # must stay visible to crop against, not a shrinking
                # crop-of-a-crop of whatever was last applied.
                toned = imaging.apply_crop_rect(
                    toned, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
                mask = imaging.apply_crop_rect(
                    mask, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
            gray_u8 = imaging.to_uint8(toned)
            rgb_u8 = np.repeat(gray_u8[:, :, None], 3, axis=2)
            self.canvas.set_image_gray(gray_u8)
            self.histogram.set_image(rgb_u8, valid_mask=mask > 0.5)
            self._last_preview_rgb_u8 = rgb_u8
            if update_curve_reference:
                pre_curve_toned = imaging.apply_straighten_mirror(
                    pre_curve_toned, self.crop.rotation, self.crop.mirror_h, self.crop.mirror_v)
                if not self._crop_active:
                    pre_curve_toned = imaging.apply_crop_rect(
                        pre_curve_toned, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
                pre_curve_gray_u8 = imaging.to_uint8(pre_curve_toned)
                pre_curve_rgb_u8 = np.repeat(pre_curve_gray_u8[:, :, None], 3, axis=2)
                self.curves_panel.set_reference_histogram(pre_curve_rgb_u8, valid_mask=mask > 0.5)
            return

        images = [l.image_preview if l.has_image() else None for l in self.layers]
        geo_params = [(l.dx, l.dy, l.scale, l.rotation) for l in self.layers]
        if self._compare_active:
            tone_params = [(*_NEUTRAL_TONE, l.invert) for l in self.layers]
            global_params = _NEUTRAL_GLOBAL
        else:
            tone_params = [(l.black_point, l.white_point, l.gamma, l.exposure, l.brightness, l.contrast,
                            l.shadows, l.highlights, l.invert) for l in self.layers]
            gc = self.global_corr
            global_params = (gc.black_point, gc.white_point, gc.gamma, gc.exposure, gc.brightness, gc.contrast,
                              gc.shadows, gc.highlights, gc.saturation, gc.temperature, gc.tint,
                              {ch: tuple(pts) for ch, pts in gc.curves.items()}, gc.black_white_active)
        # Split what compose_trichrome would otherwise do as one call, so
        # the pre-curve intermediate is available for the Curves tool's own
        # reference histogram without warping the 3 channels a second time.
        rgb0 = imaging.compose_rgb_from_channels(images, geo_params, tone_params, ref.color_index)
        mask = imaging.compose_coverage_mask(images, geo_params, ref.color_index)
        (gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
         gsat, gtemp, gtint, gcurves, gbw) = global_params
        pre_curve_rgb = imaging.apply_global_correction_before_curves(
            rgb0, gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
            gsat, gtemp, gtint)
        rgb = imaging.apply_curves(pre_curve_rgb, gcurves)
        if gbw:
            rgb = imaging.apply_black_white(rgb)
        rgb = np.clip(rgb, 0.0, 1.0)

        rgb = imaging.apply_straighten_mirror(rgb, self.crop.rotation, self.crop.mirror_h, self.crop.mirror_v)
        mask = imaging.apply_straighten_mirror(mask, self.crop.rotation, self.crop.mirror_h, self.crop.mirror_v)
        if not self._crop_active:
            # See the matching comment in the Solo-mode branch above:
            # active crop mode always shows the full frame to crop against.
            rgb = imaging.apply_crop_rect(rgb, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
            mask = imaging.apply_crop_rect(mask, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
        rgb_u8 = imaging.to_uint8(rgb)
        self.canvas.set_image_rgb(rgb_u8)
        self.histogram.set_image(rgb_u8, valid_mask=mask > 0.5)
        self._last_preview_rgb_u8 = rgb_u8

        if update_curve_reference:
            pre_curve_rgb = imaging.apply_straighten_mirror(
                pre_curve_rgb, self.crop.rotation, self.crop.mirror_h, self.crop.mirror_v)
            if not self._crop_active:
                pre_curve_rgb = imaging.apply_crop_rect(
                    pre_curve_rgb, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
            self.curves_panel.set_reference_histogram(imaging.to_uint8(pre_curve_rgb), valid_mask=mask > 0.5)

        if 0 <= self.batch_current_index < len(self.batch_items):
            self._update_carousel_thumbnail(self.batch_current_index, rgb_u8)

    def _recompute_preview_normal(self, update_curve_reference: bool) -> None:
        """Normal-mode counterpart of the main recompute_preview body above -
        no warp/alignment/harris-shutter/trichrome-recompose step, since
        self.normal_layer's own already-color image IS the composite; only
        straighten/mirror/crop and the same Light/Color/Curves global
        correction apply, via imaging.compose_normal. No coverage mask
        either (that concept only exists to exclude a misaligned channel's
        warp-padding border, which Normal mode has none of)."""
        layer = self.normal_layer
        if not layer.has_image():
            self.canvas.clear_image()
            self.histogram.clear()
            self._last_preview_rgb_u8 = None
            return

        image = imaging.apply_invert(layer.image_preview, layer.invert)
        if self._compare_active:
            global_params = _NEUTRAL_GLOBAL
        else:
            gc = self.global_corr
            global_params = (gc.black_point, gc.white_point, gc.gamma, gc.exposure, gc.brightness, gc.contrast,
                              gc.shadows, gc.highlights, gc.saturation, gc.temperature, gc.tint,
                              {ch: tuple(pts) for ch, pts in gc.curves.items()}, gc.black_white_active)
        (gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
         gsat, gtemp, gtint, gcurves, gbw) = global_params
        pre_curve_rgb = imaging.apply_global_correction_before_curves(
            image, gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
            gsat, gtemp, gtint)
        rgb = imaging.apply_curves(pre_curve_rgb, gcurves)
        if gbw:
            rgb = imaging.apply_black_white(rgb)
        rgb = np.clip(rgb, 0.0, 1.0)

        rgb = imaging.apply_straighten_mirror(rgb, self.crop.rotation, self.crop.mirror_h, self.crop.mirror_v)
        if not self._crop_active:
            rgb = imaging.apply_crop_rect(rgb, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
        rgb_u8 = imaging.to_uint8(rgb)
        self.canvas.set_image_rgb(rgb_u8)
        self.histogram.set_image(rgb_u8)
        self._last_preview_rgb_u8 = rgb_u8

        if update_curve_reference:
            pre_curve_rgb = imaging.apply_straighten_mirror(
                pre_curve_rgb, self.crop.rotation, self.crop.mirror_h, self.crop.mirror_v)
            if not self._crop_active:
                pre_curve_rgb = imaging.apply_crop_rect(
                    pre_curve_rgb, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
            self.curves_panel.set_reference_histogram(imaging.to_uint8(pre_curve_rgb))

        if 0 <= self.batch_current_index < len(self.batch_items):
            self._update_carousel_thumbnail(self.batch_current_index, rgb_u8)

    def _warp_and_tone(self, layer, canvas_size, ref):
        h, w = layer.image_preview.shape[:2]
        canvas_w, canvas_h = canvas_size
        matrix = imaging.build_similarity_matrix(
            layer.dx, layer.dy, layer.scale, layer.rotation,
            src_center=(w / 2, h / 2), dst_center=(canvas_w / 2, canvas_h / 2),
        )
        warped = imaging.warp_to_canvas(layer.image_preview, matrix, canvas_size)
        warped = imaging.apply_invert(warped, layer.invert)
        if self._compare_active:
            black, white, gamma, exposure, brightness, contrast, shadows, highlights = _NEUTRAL_TONE
            gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights = _NEUTRAL_TONE
            gcurve = _IDENTITY_CURVE
        else:
            black, white, gamma, exposure, brightness, contrast, shadows, highlights = (
                layer.black_point, layer.white_point, layer.gamma, layer.exposure,
                layer.brightness, layer.contrast, layer.shadows, layer.highlights,
            )
            gc = self.global_corr
            gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights = (
                gc.black_point, gc.white_point, gc.gamma, gc.exposure,
                gc.brightness, gc.contrast, gc.shadows, gc.highlights,
            )
            gcurve = gc.curves.get("Y", _IDENTITY_CURVE)
        toned = imaging.apply_tone_curve(
            warped, black, white, gamma, exposure, brightness, contrast, shadows, highlights,
        )
        # Solo/B&W preview shows this one channel's own independent tone
        # *plus* the Global Correction panel's "Light" adjustments layered
        # on top - the same second tone-curve pass compose_trichrome applies
        # to the composed RGB via apply_global_correction, just without the
        # white-balance/saturation portion of that function, which is
        # color-only and meaningless on a single-channel grayscale image.
        # Solo used to skip Global entirely, silently ignoring it while
        # isolating a channel. The Curves tool's "Y" (master) curve is a
        # tone remap, not a color operation, so it applies here too
        # (2026-09-04) - same relative position (last) as in
        # apply_global_correction, but applied by the caller, not here (see
        # the comment on the return statement below). The per-channel R/G/B
        # curves are NOT applied here, same reasoning as saturation/
        # temperature/tint being excluded - there's no separate R/G/B data
        # in a single-channel Solo preview, only "Y" is meaningful on it.
        toned = imaging.apply_tone_curve(
            toned, gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
        )
        # Curve deliberately NOT applied here - the caller (recompute_preview)
        # needs both the pre-curve array (for the Curves tool's own "input"
        # reference histogram, which must never reflect the curve's own
        # output) and the curved one, so it applies gcurve itself.
        return warped, toned, gcurve

    # ------------------------------------------------------------------
    # Full resolution export
    # ------------------------------------------------------------------
    def _full_res_params(self, layer, ref) -> tuple[float, float, float, float]:
        if layer is ref:
            return 0.0, 0.0, 1.0, 0.0
        ratio = layer.preview_scale / ref.preview_scale
        dx_full = layer.dx / ref.preview_scale
        dy_full = layer.dy / ref.preview_scale
        scale_full = layer.scale * ratio
        return dx_full, dy_full, scale_full, layer.rotation

    def _full_res_image(self, layer) -> np.ndarray:
        """Full-resolution grayscale for ``layer``, reloading from disk if it
        wasn't kept in memory (batch-imported items only hold a preview)."""
        if layer.image_full is not None:
            return layer.image_full
        # layer's own field, not the shared checkbox - this reloads
        # whichever layer is passed in, which for a batch export is not
        # necessarily the active photo's own layers.
        channel = CHANNEL_NAMES[layer.color_index] if layer.harris_shutter else None
        full = imaging.load_grayscale(layer.path, channel=channel)
        full = imaging.apply_film_base_correction(full, layer.film_base, channel=CHANNEL_NAMES[layer.color_index])
        if layer.quarter_turns:
            full = np.ascontiguousarray(np.rot90(full, layer.quarter_turns))
        return full

    def _full_res_color_image(self, layer) -> np.ndarray:
        """Normal-mode counterpart of _full_res_image - never collapses to
        grayscale, since a Normal-mode photo's own real color is the point."""
        if layer.image_full is not None:
            return layer.image_full
        full = imaging.load_color(layer.path)
        full = imaging.apply_film_base_correction(full, layer.film_base)
        if layer.quarter_turns:
            full = np.ascontiguousarray(np.rot90(full, layer.quarter_turns))
        return full

    def _current_export_base_name(self) -> str:
        if 0 <= self.batch_current_index < len(self.batch_items):
            return self.batch_items[self.batch_current_index].base
        ref = self._reference_layer()
        if ref.path:
            return os.path.splitext(os.path.basename(ref.path))[0]
        return "trichrome"

    def export_image(self) -> None:
        dialog = ExportDialog(self, parent=self)
        dialog.exec()
