"""Main application window wiring the model, imaging pipeline and widgets together."""
from __future__ import annotations

import copy
import dataclasses
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from html import escape as _html_escape
from html import unescape as _html_unescape

import numpy as np
from PySide6.QtCore import (
    QCoreApplication, QEvent, QEventLoop, QPoint, QSettings, Qt, QThread, QTimer, QTranslator,
)
from PySide6.QtGui import QAction, QActionGroup, QImage, QKeySequence, QPalette, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QButtonGroup, QDialog, QFileDialog, QFrame, QGroupBox,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QStatusBar,
    QToolButton, QVBoxLayout, QWidget,
)

from . import alignment, i18n, imaging
from .batch_window import BatchWindow
from .quick_tour import finish_quick_tour, open_quick_tour
from .hq_preview_worker import HQPreviewWorker
from .export_worker import BatchExportWorker
from . import preview_cache
from . import self_update
from .preview_upgrade_worker import PreviewUpgradeWorker, preview_decode_workers
from .import_worker import BatchImportWorker
from .update_checker import UpdateCheckWorker, parse_version
from .version import __version__
from .model import (
    CHANNEL_NAMES, BatchItem, ChannelLayer, CropSettings, GlobalCorrection, ensure_batch_item_uid_above,
    new_project_layers,
)
from .widgets.block_header_bar import (
    BlockReorderZone, finish_block_chrome, make_disabled_message_label, set_block_collapsed,
    set_block_disabled, start_block_chrome,
)
from .widgets.button_style import style_primary_button, style_secondary_button
from .widgets.dialog_style import PANEL_PADDING, PANEL_STYLE, make_panel, make_section_title
from .widgets.canvas_widget import CanvasWidget
from .widgets.carousel_widget import CarouselWidget
from .widgets.channel_panel import CHANNEL_COLORS, CHANNEL_KEY, ChannelPanel, ChannelTabFrame
from .widgets.compare_button import CompareButton
from .widgets.confirm_dialog import ConfirmDialog
from .widgets.crop_panel import CropPanel
from .widgets.controls import ArrowKeyScrollArea, CollapsibleSection
from .widgets.curves_panel import CurvesPanel
from .widgets.export_dialog import ExportDialog
from .widgets.settings_dialog import (
    CHECK_UPDATES_ON_STARTUP_KEY, PLAY_SOUNDS_KEY, REOPEN_LAST_SESSION_KEY, SCAN_TOOL_ENABLED_KEY,
    SESSION_PREVIEW_CACHE_KEY, SettingsDialog, setting_bool,
)
from .widgets.filmstrip_toggle_button import FilmstripToggleButton
from .widgets.fullscreen_toggle_button import FullscreenToggleButton
from .widgets.global_panel import ColorPanel, LightPanel
from .widgets.histogram_widget import HistogramPanel
from .widgets.alert_dialog import show_alert
from .widgets.import_panel import MODE_LABEL_KEYS, ImportPanel
from .widgets.info_bubble import InfoButton
from .widgets.missing_files_banner import MissingFilesBanner
from .widgets.mode_switch_dialog import ModeSwitchDialog
from .widgets.rotate_toggle_button import RotateLeftButton, RotateRightButton
from .widgets.scan_panel import ScanPanel
from .widgets.sort_button import SortButton
from .widgets.update_dialog import UpdateCheckDialog
from .widgets.svg_icons import (
    HEADER_COMPANION_BTN_SIZE, HEADER_COMPANION_ICON_SIZE,
    SvgCheckableToolButton, SvgLetterToggleButton, SvgToolButton, SvgTwoStateToggleButton,
    tinted_svg_icon,
)
from .widgets.unsaved_changes_dialog import UnsavedChangesDialog
from .widgets.checkbox import CheckBox

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

# Arrow-key micro-adjustment step (in ChannelLayer.dx/dy's own preview-space
# unit) for the active channel's alignment - see keyPressEvent. Shift held
# nudges by the larger step instead, mirroring the plain/Shift+arrow
# convention from other image editors.
_ALIGN_NUDGE_STEP = 0.5
_ALIGN_NUDGE_STEP_SHIFT = 5.0

# Fixed width of the table-of-contents pane _show_help_dialog adds next to
# the Quick Start/Shortcuts dialogs - added on top of each dialog's own
# ``width`` (the browser pane's intended width), not carved out of it.
_HELP_TOC_WIDTH = 190


def _help_search_key(text: str) -> str:
    """Normalizes text for the help search box: casefolded and stripped of
    accents, so "elements" finds "éléments" and "ombre" finds "Ombré"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


# The Guide's in-text search highlight: an opaque marker yellow with dark
# text, readable on both the light and the dark theme.
_HELP_HIGHLIGHT_STYLE = "background-color:#f5d76e; color:#1a1a1a;"


def _help_highlight_html(html: str, needle: str) -> tuple[str, int]:
    """Wraps every match of ``needle`` (already a _help_search_key) in the
    text between ``html``'s tags with a highlight span, matching the same
    accent- and case-insensitive way the search filters. Returns the new
    HTML and the number of matches. A match spanning a tag isn't found,
    the same as with _help_plain_text."""
    if not needle:
        return html, 0
    out = []
    count = 0
    for part in re.split(r"(<[^>]*>)", html):
        if not part or part.startswith("<"):
            out.append(part)
            continue
        text = _html_unescape(part)
        # Normalized key, plus which original character each key char came from.
        key_chars = []
        owners = []
        for i, c in enumerate(text):
            k = _help_search_key(c)
            key_chars.append(k)
            owners.extend([i] * len(k))
        key = "".join(key_chars)
        start = key.find(needle)
        if start == -1:
            out.append(part)
            continue
        marked = [False] * len(text)
        while start != -1:
            count += 1
            for j in range(start, start + len(needle)):
                marked[owners[j]] = True
            start = key.find(needle, start + len(needle))
        i = 0
        while i < len(text):
            j = i
            while j < len(text) and marked[j] == marked[i]:
                j += 1
            chunk = _html_escape(text[i:j], quote=False)
            out.append(f'<span style="{_HELP_HIGHLIGHT_STYLE}">{chunk}</span>' if marked[i] else chunk)
            i = j
    return "".join(out), count

# Marks where _general_shortcuts_html()'s dynamically-derived <li> items
# (read live from each QAction's own shortcut, so they can't drift from
# what the app actually does) get spliced into help_shortcuts_content's
# General section - see show_shortcuts_dialog.
_GENERAL_SHORTCUTS_PLACEHOLDER = "%%GENERAL_SHORTCUTS_ITEMS%%"


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


def _decode_stretch_pins(raw: str) -> list:
    """Parses a ChannelLayer.stretch_pins value's QSettings-string encoding
    (a JSON array of [anchor_u, anchor_v, delta_u, delta_v] arrays, same
    json.dumps/loads-a-string convention _decode_curves/_decode_film_base
    use) - [] for a missing/empty/corrupt value, same "no correction"
    natural default as _decode_film_base's None."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    try:
        return [tuple(float(x) for x in pin) for pin in data if len(pin) == 4]
    except (TypeError, ValueError):
        return []

# Matches the "(N)" version suffix Duplicate Selection appends, so
# duplicating an already-duplicated photo increments N instead of stacking
# another suffix (e.g. "IMG_1234 (2)" -> "IMG_1234 (3)", not "... (2) (2)").
_DUPLICATE_SUFFIX_RE = re.compile(r"^(.*) \((\d+)\)$")

# Dragging a curve point emits `changed` on every raw mouse-move (unlike a
# QSlider, which is quantized to its own step range) - triggering a full
# recompute_preview() (warp + composite + histogram + canvas repaint) on every
# single one of those can't keep up with a fast drag, and unlike a 1D slider's
# value catching up a frame late, a laggy 2D curve point read as visibly janky
# against the cursor. CurveEditor's own on-screen redraw stays
# instant/unthrottled (see on_curve_changed) - only the expensive full image
# recompute is throttled, to at most one per this many ms. 16ms matches a 60Hz
# display (~62.5fps) - most screens' refresh rate, chosen over the initial,
# more conservative 40ms guess. Below this, recompute_preview()'s own real cost
# (not this timer) becomes the limiting factor regardless.
_CURVE_RECOMPUTE_THROTTLE_MS = 16

# HQ Preview: the live preview always composites from the
# ~MAX_PREVIEW_DIM-capped (1400px, see imaging.py) imaging.make_preview()
# arrays - fast enough to stay live on every slider tick, but visibly soft once
# zoomed in or in fullscreen. Recomposing at the source's true native
# resolution on every tick would defeat that whole point (measured empirically
# at ~2.9s for a single pass on a realistic 24MP (6000x4000) trichrome triplet,
# all in compose_trichrome's own warp/tone/color math, not I/O), so HQ Preview
# mode instead waits for a short idle gap (_HQ_PREVIEW_IDLE_MS, (re)armed on
# every edit by _arm_hq_preview_if_enabled - QTimer.start() on an
# already-running single-shot timer restarts its countdown, so this is a
# settle-delay that fires N ms after the *last* edit, not a throttle like the
# Curves tool's own _CURVE_RECOMPUTE_THROTTLE_MS, which fires at most once per
# burst) before recomposing at native resolution. That recompute runs in a
# background QThread (HQPreviewWorker, see _start_hq_preview), not on the UI
# thread, so it doesn't block sliders/menus/etc. while it runs - see
# hq_preview_worker.py. Since a stale result (an edit arriving before/ during
# an in-flight compute) is simply discarded rather than shown (see
# _hq_result_stale), this delay can stay short: unlike the earlier
# UI-thread-blocking design, firing it too eagerly costs some wasted background
# CPU on a fast-moving edit, not a frozen UI.
#
# **Tried and reverted**: an intermediate capped stage (a fast ~3200px pass at
# 400ms idle, then upgrading to native at 4s idle, both still fast enough to
# run *synchronously*) was tried first and dropped once the recompute moved to
# a background thread - at that point a single native-resolution step, now able
# to fire much sooner (500ms) since it no longer risks freezing the UI, was
# simpler and sharper sooner.
_HQ_PREVIEW_IDLE_MS = 500

# The status bar's HQ-compute indicator's spin rate (see _on_status_spin_tick) -
# matches ScanPanel's own refresh-button spin exactly (same tick interval,
# same -360deg/second speed), just looped continuously instead of that
# one's fixed 1-second one-shot, since a HQ compute's duration isn't known
# up front.
_HQ_SPIN_TICK_MS = 16
_HQ_SPIN_DEGREES_PER_SEC = 360.0

# Minimum time a bottom-left status activity ("Saving session…", "Importing 2 /
# 3…") stays on screen, even when the work itself is near-instant - otherwise
# it just flickers past unread. See _set_status_activity.
_STATUS_ACTIVITY_MIN_MS = 1500


class _AppMenuTranslator(QTranslator):
    """Qt's Cocoa plugin forces the title of the PreferencesRole item it
    moves into the application menu to its own untranslated "Preferences..."
    string, ignoring the action's text; this supplies the app's own label
    ("Preferences…"/"Préférences…") in its current language instead.
    Answers nothing else, so every other string falls through untouched."""

    def translate(self, context, source_text, disambiguation=None, n=-1):
        if context == "MAC_APPLICATION_MENU" and source_text == "Preferences...":
            return i18n.tr("menu_settings")
        # None (a null QString), never "": an empty string counts as a real
        # translation, and Qt then blanks every string it translates
        # itself - it emptied the whole macOS menu bar.
        return None


class _DeferringStatusBar(QStatusBar):
    """A QStatusBar whose showMessage() can be put on hold - used while a
    just-finished activity is still being kept on screen for its
    _STATUS_ACTIVITY_MIN_MS minimum, so its "done" message ("Session
    Saved") appears right after it instead of hiding it immediately (a
    temporary message hides QStatusBar's normal widgets). Only the latest
    held message is kept. Every caller goes through Python, so overriding
    showMessage here covers them all."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._held = False
        self._queued: tuple[str, int] | None = None

    def set_held(self, held: bool) -> None:
        self._held = held
        if not held and self._queued is not None:
            text, timeout = self._queued
            self._queued = None
            super().showMessage(text, timeout)

    def showMessage(self, text: str, timeout: int = 0) -> None:
        if self._held:
            self._queued = (text, timeout)
            return
        super().showMessage(text, timeout)

# The block system: every side-panel block (Files/Channels on the left;
# Histogram/Light/Color/Crop on the right; Scan can live on either) has its own
# side, position, visibility and collapsed state - freely reassignable at
# runtime by dragging a block's grip handle (within or across panels),
# collapsing it, or closing it (restorable from the Tools menu). These are the
# defaults the app starts with and that Window > Reset Layout restores -
# matches what the old exclusive tool-switcher used to show by default
# (Files+Channels left; Histogram+Light+Color right; Crop/Scan hidden until
# enabled). Order here is what the Tools menu lists top-to-bottom (built by
# iterating this tuple directly, see _build_ui) - "curves" sits between "light"
# and "color" specifically for that menu; it does NOT affect the actual default
# panel position, which is _DEFAULT_RIGHT_BLOCK_ORDER's own separate list
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

# Light mode (single-photo, simplified UI): the fixed left-panel-only block set
# and order it forces, regardless of the user's Advanced-mode
# block_side/block_visible/order - those are deliberately left untouched while
# light_mode_active, so switching back to Advanced needs no restore step.
# Histogram sits first, even though it normally defaults to the *right* panel
# in Advanced mode. See _apply_light_mode_block_layout().
_LIGHT_MODE_BLOCK_KEYS = ("histogram", "files", "channels", "crop")

# Both side panels share one width range - they used to differ (left 360-420,
# right 300-360), which is exactly backwards now that any block can be dragged
# to either side: a block sized to fit the left panel could overflow the right
# one. Reusing the wider of the two previous ranges for both, since every block
# already fits it with margin (verified headlessly) and it's the one already
# used by whichever side a given block happens to be visiting.
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

# The 4 built-in default-layout menu entries, each backing one of the top
# toolbar's Trichrome/Color Correction/Crop/Scan buttons - ordered (display
# name - the fixed identifier used throughout the code, its Window-menu
# i18n label key, bare-letter shortcut hint) matching the toolbar's own
# left-to-right order. The display name itself is a reserved slot, not a
# real saved preset - on_save_layout_preset refuses to save a custom
# preset under one of these 4 names, and _rebuild_layout_preset_menu skips
# them so they never show a stray Load/Update/Delete submenu of their own.
#
# Each slot's actual layout is a fixed dict literal (_BUILT_IN_LAYOUT_STATES
# below), not a QSettings-backed custom preset. Previously each slot loaded an
# ordinary user-editable preset ("NewTrichrome"/
# "NewColorCorrection"/"NewCrop"/"NewScan") via an indirection table - that
# meant these 4 toolbar buttons silently broke if that underlying preset was
# ever deleted (which build_mac.sh's fresh-build QSettings reset now does
# deliberately - see build_mac.sh), and the "New*" presets themselves cluttered
# the Layout Preset submenu as ordinary-looking entries. Hardcoding the state
# here makes these 4 slots immune to any preset being cleared - there's no more
# "Update" action for them either (removed from the Window menu's per-slot
# submenu), since there's no live preset left to update; a genuinely different
# default would mean editing this dict directly. If a user later
# saves/recreates a custom preset literally named "NewTrichrome" (or any other
# string), it's just an ordinary preset now - no special handling, shows
# normally in the Layout Preset submenu.
_BUILT_IN_LAYOUT_PRESETS = (
    ("Trichrome", "menu_window_layout_trichrome", "T"),
    ("Color Correction", "menu_window_layout_color_correction", "E"),
    ("Crop", "menu_window_layout_crop", "C"),
    ("Scan", "menu_window_layout_scan", "S"),
)
_BUILT_IN_LAYOUT_PRESET_NAMES = tuple(name for name, _key, _shortcut in _BUILT_IN_LAYOUT_PRESETS)
_BUILT_IN_LAYOUT_STATES = {
    "Trichrome": {
        "left_panel_visible": True, "right_panel_visible": True, "carousel_visible": True,
        "block_side": {
            "files": "left", "channels": "left", "scan": "left",
            "histogram": "right", "light": "right", "color": "right", "crop": "right", "curves": "right",
        },
        "block_visible": {
            "files": True, "channels": True, "scan": False,
            "histogram": True, "light": True, "color": True, "crop": False, "curves": True,
        },
        "block_collapsed": {k: False for k in _ALL_BLOCK_KEYS},
        "left_block_order": ["files", "channels", "scan"],
        "right_block_order": ["histogram", "crop", "light", "curves", "color"],
    },
    "Color Correction": {
        "left_panel_visible": True, "right_panel_visible": True, "carousel_visible": True,
        "block_side": {
            "files": "left", "channels": "left", "scan": "left",
            "histogram": "right", "light": "right", "color": "left", "crop": "right", "curves": "left",
        },
        "block_visible": {
            "files": False, "channels": False, "scan": False,
            "histogram": True, "light": True, "color": True, "crop": False, "curves": True,
        },
        "block_collapsed": {k: False for k in _ALL_BLOCK_KEYS},
        "left_block_order": ["files", "channels", "scan", "curves", "color"],
        "right_block_order": ["histogram", "crop", "light"],
    },
    "Crop": {
        "left_panel_visible": True, "right_panel_visible": True, "carousel_visible": True,
        "block_side": {
            "files": "left", "channels": "left", "scan": "left",
            "histogram": "right", "light": "right", "color": "right", "crop": "right", "curves": "right",
        },
        "block_visible": {
            "files": True, "channels": True, "scan": False,
            "histogram": True, "light": False, "color": False, "crop": True, "curves": False,
        },
        "block_collapsed": {k: False for k in _ALL_BLOCK_KEYS},
        "left_block_order": ["files", "channels", "scan"],
        "right_block_order": ["histogram", "crop", "light", "color", "curves"],
    },
    "Scan": {
        "left_panel_visible": True, "right_panel_visible": True, "carousel_visible": True,
        "block_side": {
            "files": "left", "channels": "left", "scan": "left",
            "histogram": "right", "light": "right", "color": "right", "crop": "right", "curves": "right",
        },
        "block_visible": {
            "files": False, "channels": False, "scan": True,
            "histogram": True, "light": False, "color": False, "crop": True, "curves": False,
        },
        "block_collapsed": {k: False for k in _ALL_BLOCK_KEYS},
        "left_block_order": ["files", "channels", "scan"],
        "right_block_order": ["histogram", "crop", "light", "color", "curves"],
    },
}

# Session files: a portable project file (every imported photo's path,
# alignment, tone, and global correction) - distinct from the QSettings-based
# autosave-on-close session, which is implicit and OS-scoped.
SESSION_FILE_EXTENSION = "trirgb"
SESSION_FILE_FILTER = "Trichr-o-matic Session (*.trirgb)"
SESSION_FORMAT_VERSION = 1

ORG_NAME = "TrichromeMaker"
APP_NAME = "TrichromeMaker"

# QSettings key names for _save_session_state/_legacy_restore_session's
# per-field writes/reads, indirected through a prefix so Light mode's own
# single-photo autosave (_save_light_mode_state/_restore_light_mode_state) can
# reuse the exact same field-by-field code under a separate namespace instead
# of hand-copying a third field list. The "session" prefix (the normal
# Advanced-mode autosave) maps to this method's original, pre-existing key
# names exactly as they always were - some already "session_"-prefixed, some
# historically bare - so an existing user's saved session stays readable; any
# other prefix (only "light_session" today) gets a uniformly {prefix}_{suffix}
# namespace, which never collides with the "session" one.
_SESSION_STATE_KEYS = {
    "items": "session_items", "current_index": "session_current_index",
    "sort_mode": "sort_mode", "sort_reversed": "sort_reversed",
    "left_panel_visible": "left_panel_visible", "right_panel_visible": "right_panel_visible",
    "carousel_visible": "carousel_visible", "block_side": "block_side",
    "block_visible": "block_visible", "block_collapsed": "block_collapsed",
    "left_block_order": "left_block_order", "right_block_order": "right_block_order",
}


def _session_state_key(key_prefix: str, suffix: str) -> str:
    if key_prefix == "session":
        return _SESSION_STATE_KEYS[suffix]
    return f"{key_prefix}_{suffix}"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._load_language_setting()
        self._app_menu_translator = _AppMenuTranslator(self)
        QCoreApplication.installTranslator(self._app_menu_translator)

        self.setWindowTitle("Trichr-o-matic")
        self.resize(1500, 950)

        # Light mode (single-photo, simplified UI) - read early since
        # _build_ui() needs it (Help-menu label, disabled close buttons on the
        # 3 light-mode blocks) before either restore path runs.
        self.light_mode_active: bool = QSettings(ORG_NAME, APP_NAME).value(
            "light_mode_active", False, type=bool)

        self.layers = new_project_layers()
        self.global_corr = GlobalCorrection()
        self.crop = CropSettings()
        # Normal mode's single-photo holder (see BatchItem.normal_layer in
        # model.py) - aliased the same way self.layers/global_corr/crop
        # already are, kept in sync with the active item by
        # activate_batch_item/_restore_state/_apply_restored_items.
        self.normal_layer = ChannelLayer(color_index=0, label="Normal")
        self.active_index: int | None = None
        # "Stretch on Canvas" - the Distortion-section peer of active_index,
        # mutually exclusive with it (a canvas drag can only do one or the
        # other at a time - see on_stretch_toggled/ on_active_toggled). Which
        # channel's own ChannelLayer.stretch_pins a canvas drag currently
        # appends/extends.
        self.stretch_index: int | None = None
        # "Show Layer" - which channels contribute to the composed preview, a
        # view-only toggle (not persisted, not undoable - same transient-state
        # convention as _compare_active right below). Unlike Solo (exactly one
        # channel, forced to grayscale), any combination can be shown/hidden
        # and the result stays in color - see compose_rgb_from_channels's own
        # docstring.
        self._visible_channels: set[int] = {0, 1, 2}
        self._is_focus_mode = False
        self._compare_active = False
        # Whether the interactive Crop overlay (draggable rect on the canvas,
        # Enter-to-apply, full-vs-cropped preview) is armed - decoupled from
        # the Crop block's own visibility, since the block can now be shown in
        # any custom layout. See _set_crop_active().
        self._crop_active = False
        # Guided Perspective mode (Framing tool's Geometry section) - see
        # _set_perspective_active().
        self._perspective_active = False
        # Live-solved correction previewed while it's active - see
        # on_perspective_guides_changed/_perspective_frame_params.
        self._perspective_proposal = None
        # Whether any guide was edited since the mode was entered - see
        # on_perspective_apply.
        self._perspective_edited = False
        # Throttles recompute_preview() during a live curve drag - see
        # _CURVE_RECOMPUTE_THROTTLE_MS and on_curve_changed(). Always calls
        # with update_curve_reference=False (via the lambda, since
        # QTimer.timeout carries no args and would otherwise fall back to
        # recompute_preview's own True default) - a curve-only recompute
        # must never refresh the Curves tool's "input" reference histogram.
        self._curve_recompute_timer = QTimer(self)
        self._curve_recompute_timer.setSingleShot(True)
        self._curve_recompute_timer.timeout.connect(lambda: self.recompute_preview(update_curve_reference=False))
        # HQ Preview toggle (see _HQ_PREVIEW_IDLE_MS above) - not persisted
        # across launches, same as Compare/Crop-active, since it's an
        # in-the-moment display choice rather than a saved preference.
        self.hq_preview_enabled = False
        self._hq_idle_timer = QTimer(self)
        self._hq_idle_timer.setSingleShot(True)
        self._hq_idle_timer.timeout.connect(self._start_hq_preview)
        # QThread/HQPreviewWorker currently computing a HQ pass (None if
        # none is in flight - see _start_hq_preview). _hq_result_stale marks
        # whether an in-flight (or already-finished but not yet applied)
        # worker's result should be discarded instead of shown - set True by
        # any edit or by turning HQ Preview off, cleared right when a new
        # worker is dispatched. This is what lets an in-flight computation
        # become "abandoned" without actually being cancellable mid-numpy-call.
        self._hq_thread: QThread | None = None
        self._hq_worker: HQPreviewWorker | None = None
        self._hq_result_stale = True
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
        # Background export (see start_background_export) - owned here, not
        # by ExportDialog, so closing that dialog can't destroy a running
        # QThread (which aborted the whole app).
        self._export_thread: QThread | None = None
        self._export_worker: BatchExportWorker | None = None
        self._export_items: list = []
        self._export_ok_paths: list[str] = []
        self._export_failures: list[tuple[str, str]] = []
        self._export_output_dir: str | None = None
        self._export_reveal: bool = False
        # Session preview cache (preview_cache.py): key -> (array shown,
        # its cache entry, decode params) for previews still showing their
        # cached version; emptied as the background upgrade replaces them.
        self._cached_previews: dict[str, tuple] = {}
        self._incoming_cached_previews: dict[str, tuple] = {}
        self._preview_upgrade_thread: QThread | None = None
        self._preview_upgrade_worker: PreviewUpgradeWorker | None = None
        self._preview_upgrade_restart = False
        self._preview_upgrade_total = 0
        self._preview_upgrade_done = 0
        self._preview_upgrade_affected: set[int] = set()
        # Coalesces thumbnail/preview refreshes while upgrades stream in.
        self._preview_upgrade_flush_timer = QTimer(self)
        self._preview_upgrade_flush_timer.setSingleShot(True)
        self._preview_upgrade_flush_timer.setInterval(150)
        self._preview_upgrade_flush_timer.timeout.connect(self._flush_preview_upgrades)

        # Block system state - see _ALL_BLOCK_KEYS above and
        # _apply_block_layout(). block_side says which panel a block is in;
        # left_block_order/right_block_order is that panel's own full order
        # (hidden blocks keep their slot so re-showing one restores its old
        # position); block_visible/ block_collapsed are independent per-block
        # toggles.
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
        # Preferences > Experimental. Off: Scan is unreachable (see
        # _apply_scan_tool_ui_state); block_visible["scan"] is left alone so
        # turning it back on restores the block where it was.
        self.scan_tool_enabled = setting_bool(ORG_NAME, APP_NAME, SCAN_TOOL_ENABLED_KEY, default=False)
        # Preferences > General > Check for updates at startup. The thread
        # refs follow the same "None when idle" convention as the other
        # background workers (_hq_thread, _export_thread, etc.).
        self.check_updates_on_startup = setting_bool(
            ORG_NAME, APP_NAME, CHECK_UPDATES_ON_STARTUP_KEY, default=True)
        self._startup_update_thread: QThread | None = None
        self._startup_update_worker: UpdateCheckWorker | None = None

        self._build_ui()
        self._connect_signals()
        self._apply_light_mode_ui_state()
        # App-wide, so a click on any other window (a dialog, the batch
        # window) disarms the histogram pick tool too, not just clicks
        # inside this window - see eventFilter().
        QApplication.instance().installEventFilter(self)
        self._refresh_reference_ui()
        self._undo_suppressed = True
        try:
            if self.light_mode_active:
                self._restore_light_mode_state()
            else:
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
        self.settings_action.setText(i18n.tr("menu_settings"))
        self.edit_menu.setTitle(i18n.tr("menu_edit"))
        self.undo_action.setText(i18n.tr("menu_undo"))
        self.redo_action.setText(i18n.tr("menu_redo"))
        self.copy_action.setText(i18n.tr("menu_edit_copy"))
        self.paste_action.setText(i18n.tr("menu_edit_paste"))
        self.rotate_right_action.setText(i18n.tr("menu_edit_rotate_right"))
        self.rotate_left_action.setText(i18n.tr("menu_edit_rotate_left"))
        self.delete_selection_action.setText(i18n.tr("menu_edit_delete") + "\t⌘⌫")
        self.tools_menu.setTitle(i18n.tr("menu_tools"))
        for key, action in self.block_menu_actions.items():
            action.setText(i18n.tr(_BLOCK_MENU_LABEL_KEYS[key]))
        self.view_menu.setTitle(i18n.tr("menu_view"))
        self.view_zoom_in_action.setText(i18n.tr("menu_view_zoom_in") + "\t⌘=")
        self.view_zoom_out_action.setText(i18n.tr("menu_view_zoom_out") + "\t⌘-")
        self.view_zoom_fit_action.setText(i18n.tr("menu_view_zoom_fit") + "\tF")
        self.view_zoom_100_action.setText(i18n.tr("menu_view_zoom_100") + "\tZ")
        self.view_hq_preview_action.setText(i18n.tr("menu_view_hq_preview") + "\tH")
        self.view_compare_action.setText(i18n.tr("menu_view_compare") + "\t:")
        self._update_fullscreen_action_text()
        self.view_thumbnails_action.setText(i18n.tr("menu_view_thumbnails") + "\tP")
        self.view_grid_action.setText(i18n.tr("menu_view_grid") + "\tG")
        self.window_menu.setTitle(i18n.tr("menu_window"))
        self.window_close_action.setText(i18n.tr("menu_window_close") + "\t⌘W")
        self.window_left_panel_action.setText(i18n.tr("menu_window_left_panel") + "\tI")
        self.window_right_panel_action.setText(i18n.tr("menu_window_right_panel") + "\tO")
        self.window_thumbnails_action.setText(i18n.tr("menu_window_thumbnails") + "\tP")
        for name, label_key, shortcut in _BUILT_IN_LAYOUT_PRESETS:
            self.builtin_layout_load_actions[name].setText(
                i18n.tr("menu_window_layout_prefix") + i18n.tr(label_key) + f"\t{shortcut}")
        self.layout_preset_menu.setTitle(i18n.tr("menu_window_layout_preset"))
        self.save_layout_preset_action.setText(i18n.tr("menu_window_save_layout_preset"))
        self._rebuild_layout_preset_menu()
        self.reset_layout_action.setText(i18n.tr("menu_window_reset_layout"))
        self.help_menu.setTitle(i18n.tr("menu_help"))
        self.quick_tour_action.setText(i18n.tr("menu_quick_tour_action"))
        self.quickstart_action.setText(i18n.tr("menu_quickstart_action"))
        self.shortcuts_action.setText(i18n.tr("menu_shortcuts_action"))
        self.check_updates_action.setText(i18n.tr("menu_check_updates_action"))
        self.light_mode_toggle_action.setText(
            i18n.tr("menu_switch_to_advanced_mode") if self.light_mode_active
            else i18n.tr("menu_switch_to_light_mode"))

        self.import_panel.retranslate_ui()
        self.independent_channels_title_label.setText(i18n.tr("independent_channels_group_title"))
        if not self.channels_disabled_label.isHidden():
            self.channels_disabled_label.setText(i18n.tr("channels_disabled_normal_mode"))
        self.display_layer_label.setText(i18n.tr("display_layer_label"))
        for i, label in enumerate(("R", "G", "B")):
            self.display_layer_buttons[i].setToolTip(i18n.tr(CHANNEL_KEY[label]))
        self.auto_align_button.setText(i18n.tr("auto_align_button"))
        self.auto_align_apply_distortion_checkbox.setText(i18n.tr("auto_align_apply_distortion_checkbox"))
        self.lock_label.setText(i18n.tr("lock_layer_position_label"))
        for i, label in enumerate(("R", "G", "B")):
            self.lock_buttons[i].setToolTip(i18n.tr(CHANNEL_KEY[label]))
        self.channel_tab_frame.retranslate_ui()
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
        self.hq_preview_btn.setToolTip(i18n.tr("hq_preview_tooltip"))
        self.rotate_left_btn.setToolTip(i18n.tr("rotate_left_tooltip"))
        self.rotate_right_btn.setToolTip(i18n.tr("rotate_right_tooltip"))
        self.compare_btn.setToolTip(i18n.tr("compare_tooltip"))
        self.compare_indicator.setText(i18n.tr("compare_indicator_label"))
        self._update_canvas_drag_indicator()
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
        self.quick_tour_toolbar_action.setText(i18n.tr("menu_quick_tour_action"))
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
        # Preferences… - PreferencesRole moves it into the macOS application
        # menu (Trichr-o-matic > Preferences…), where Cmd+, is the standard
        # shortcut. Its title there comes from _AppMenuTranslator.
        self.settings_action = QAction(i18n.tr("menu_settings"), self)
        # Built from key codes: in Qt's text form a comma separates
        # sequences, so QKeySequence("Ctrl+,") parses as empty.
        self.settings_action.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_Comma))
        self.settings_action.setMenuRole(QAction.PreferencesRole)
        self.settings_action.triggered.connect(self.open_settings_dialog)
        self.file_menu.addAction(self.settings_action)
        # Keyboard Shortcuts sits right under Preferences in the macOS
        # application menu. ApplicationSpecificRole is what makes Qt's Cocoa
        # plugin move it there (on other platforms it stays in File).
        self.shortcuts_action = QAction(i18n.tr("menu_shortcuts_action"), self)
        self.shortcuts_action.setMenuRole(QAction.ApplicationSpecificRole)
        self.shortcuts_action.triggered.connect(self.show_shortcuts_dialog)
        self.file_menu.addAction(self.shortcuts_action)
        # Check for Updates sits right under Shortcuts in the macOS
        # application menu - same ApplicationSpecificRole trick, added
        # right after it so Qt's Cocoa plugin keeps that order.
        self.check_updates_action = QAction(i18n.tr("menu_check_updates_action"), self)
        self.check_updates_action.setMenuRole(QAction.ApplicationSpecificRole)
        self.check_updates_action.triggered.connect(self.show_check_updates_dialog)
        self.file_menu.addAction(self.check_updates_action)
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
        # Lists every block individually (Files/Channels/
        # Histogram/Light/Color/Crop/Scan), not the old 4 tool-switcher pairs -
        # each a plain independent checkable toggle controlling that one
        # block's visibility (self.block_visible), synced with its own header's
        # close button via set_block_visible(). No QActionGroup: unlike the old
        # exclusive-pair tools, any number of blocks can be shown at once now.
        # Actual checked-state + the toggled connection are wired in
        # _connect_signals(), once self.block_menu_actions exists (built at the
        # end of _build_ui).
        self.block_menu_actions: dict[str, QAction] = {}
        for key in _ALL_BLOCK_KEYS:
            action = QAction(self, checkable=True)
            self.tools_menu.addAction(action)
            self.block_menu_actions[key] = action

        # Mirrors the preview bar's own controls (menu-bar reachability + a
        # text reminder of each one's real shortcut) - present in both Light
        # and Advanced mode, unlike Tools/Window which are hidden entirely in
        # Light mode. No QAction-level setShortcut() on any of these: every one
        # is already bound elsewhere (a QShortcut, a bare keyPressEvent key, or
        # the toolbar button's own click) - setting a second real QKeySequence
        # here would risk Qt's "ambiguous shortcut" conflict, same reasoning as
        # delete_selection_action/window_close_action above, so the shortcut is
        # appended after a tab in retranslate_ui() instead, display-only (the
        # tab puts it in the menu's shortcut column). Actual
        # signal wiring (handler + the 4 checkable ones' bidirectional
        # checked-state sync) is deferred to _connect_signals(), once the
        # preview-bar buttons these mirror actually exist (built later in
        # _build_ui, as part of the canvas/bottom bar).
        self.view_menu = self.menuBar().addMenu(i18n.tr("menu_view"))
        self.view_zoom_in_action = QAction(self)
        self.view_menu.addAction(self.view_zoom_in_action)
        self.view_zoom_out_action = QAction(self)
        self.view_menu.addAction(self.view_zoom_out_action)
        self.view_zoom_fit_action = QAction(self)
        self.view_menu.addAction(self.view_zoom_fit_action)
        self.view_zoom_100_action = QAction(self)
        self.view_menu.addAction(self.view_zoom_100_action)
        self.view_menu.addSeparator()
        self.view_hq_preview_action = QAction(self, checkable=True)
        self.view_menu.addAction(self.view_hq_preview_action)
        self.view_compare_action = QAction(self, checkable=True)
        self.view_menu.addAction(self.view_compare_action)
        self.view_fullscreen_action = QAction(self, checkable=True)
        self.view_menu.addAction(self.view_fullscreen_action)
        self.view_menu.addSeparator()
        # Advanced mode only - hidden entirely in Light mode, which has no
        # filmstrip/grid view at all (see _apply_light_mode_ui_state).
        self.view_thumbnails_action = QAction(self, checkable=True)
        self.view_menu.addAction(self.view_thumbnails_action)
        self.view_grid_action = QAction(self, checkable=True)
        self.view_menu.addAction(self.view_grid_action)

        self.window_menu = self.menuBar().addMenu(i18n.tr("menu_window"))
        # Light mode (single-photo, simplified UI) toggle, first in the Window
        # menu - the one entry point for switching modes in both directions.
        # Label text flips between "Switch to Light Mode"/"Switch to Advanced
        # Mode" in _apply_light_mode_ui_state(). The Window menu therefore
        # stays visible in Light mode, reduced to this toggle and Close Window
        # - every layout item (window_menu_advanced_actions) is hidden there.
        self.light_mode_toggle_action = QAction(self)
        self.light_mode_toggle_action.triggered.connect(self._toggle_light_mode)
        self.window_menu.addAction(self.light_mode_toggle_action)
        window_menu_first_index = len(self.window_menu.actions())
        self.window_menu.addSeparator()
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
        # Added at the very bottom of the menu, after Reset Layout (below).
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

        # The 4 built-in default-layout entries, listed directly in the Window
        # menu (not nested in the Layout Preset submenu below) - each one is a
        # single plain action (not a submenu with its own Update - see
        # _BUILT_IN_LAYOUT_STATES, these 4 slots are fixed dict literals now,
        # not a live QSettings preset, so there's nothing left to "update" from
        # here). Triggering mirrors the matching top toolbar button - both go
        # through the same _activate_default_layout(), so the toolbar's
        # exclusive checked state stays in sync regardless of which one was
        # used.
        self.builtin_layout_load_actions: dict[str, QAction] = {}
        for name, _label_key, _shortcut in _BUILT_IN_LAYOUT_PRESETS:
            load_action = QAction(self.window_menu)
            load_action.triggered.connect(lambda _checked=False, n=name: self._activate_default_layout(n))
            self.window_menu.addAction(load_action)
            self.builtin_layout_load_actions[name] = load_action
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

        # Reset Layout sits directly below Layout Preset, no separator between
        # them - the separator above (before the 4 built-in layout submenus)
        # still marks the start of the whole "layout" section of the menu; tool
        # panels can now be reordered directly by dragging a block's header
        # (BlockHeaderBar/BlockReorderZone) instead of via a menu action, so
        # the old per-tool "move to left/right panel" actions were removed and
        # Reset Layout is the one remaining fixed-arrangement action left in
        # this section.
        self.reset_layout_action = QAction(self)
        self.reset_layout_action.triggered.connect(self.reset_layout)
        self.window_menu.addAction(self.reset_layout_action)
        # Everything between the Light mode toggle and Close Window
        # (including the separator right after the toggle) - hidden in
        # Light mode by _apply_light_mode_ui_state().
        self.window_menu_advanced_actions = self.window_menu.actions()[window_menu_first_index:]
        # Close Window at the very bottom, under a hairline.
        self.window_menu.addSeparator()
        self.window_menu.addAction(self.window_close_action)

        self.help_menu = self.menuBar().addMenu(i18n.tr("menu_help"))
        # Quick Tour: welcome window, then the guided tour - see quick_tour.py.
        self.quick_tour_action = QAction(i18n.tr("menu_quick_tour_action"), self)
        self.quick_tour_action.triggered.connect(lambda: open_quick_tour(self))
        self.help_menu.addAction(self.quick_tour_action)
        self.quickstart_action = QAction(i18n.tr("menu_quickstart_action"), self)
        self.quickstart_action.triggered.connect(self.show_quickstart_dialog)
        self.help_menu.addAction(self.quickstart_action)
        # Language lives in Preferences (widgets/settings_dialog.py) - the
        # old Help > Language submenu was removed once that existed.

        fullscreen_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        fullscreen_shortcut.activated.connect(self.toggle_focus_mode)
        help_shortcut = QShortcut(QKeySequence("F1"), self)
        help_shortcut.activated.connect(self.show_quickstart_dialog)

        zoom_in_shortcut = QShortcut(QKeySequence.ZoomIn, self)
        zoom_in_shortcut.activated.connect(self.on_zoom_in_clicked)
        zoom_in_shortcut_eq = QShortcut(QKeySequence("Ctrl+="), self)
        zoom_in_shortcut_eq.activated.connect(self.on_zoom_in_clicked)
        zoom_out_shortcut = QShortcut(QKeySequence.ZoomOut, self)
        zoom_out_shortcut.activated.connect(self.on_zoom_out_clicked)

        self._build_top_toolbar()

        self.import_panel = ImportPanel()
        self.import_panel.load_requested.connect(self.load_image)
        self.import_panel.mode_change_requested.connect(self.on_import_mode_change_requested)
        self.import_panel.harris_shutter_toggled.connect(self.on_harris_shutter_toggled)
        self.import_panel.channel_swap_requested.connect(self.on_channel_swap_requested)
        self.import_panel.light_mode_reset_requested.connect(self.on_light_mode_reset_channels)

        self.channel_panels = [ChannelPanel(layer.label) for layer in self.layers]
        self.independent_channels_group = QGroupBox()
        independent_channels_outer, independent_channels_header, self.independent_channels_title_label = (
            start_block_chrome(self.independent_channels_group, "channels", "independent_channels_group_title"))
        # Same "?" scope-info convention as Light/Color's own
        # scope_info_button.
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

        # "Show Layer" (R/G/B toggle buttons at the very top of the block,
        # styled prominently: non-greyed label, bigger icons; no "?" info
        # button - the title alone already says what it does) - show/hide each
        # channel's own contribution to the composed preview. Deliberately
        # distinct from Solo (ChannelPanel's own solo_checkbox, one channel at
        # a time, forced grayscale): any combination of the 3 can be shown,
        # including 2 at once, and the result stays in color. Lives here (a
        # sibling of the tab frame, not inside any one ChannelPanel) since it
        # needs to show all 3 R/G/B states at once regardless of which tab is
        # active - unlike solo_checkbox, which is naturally edited "from
        # within" whichever tab is active and so can live one-per-panel. Not a
        # QButtonGroup since the 3 toggle independently
        # (SvgLetterToggleButton's own set_active()-free, plain
        # isChecked()-driven mode already supports this - see the
        # histogram's/curves' own Y/R/G/B toggles, whose size=(32,
        # 28)/icon_size=22 this also reuses - the app's own "prominent" tier
        # for this icon family, as opposed to Lock Layer Position's
        # deliberately-shrunk (24, 22)/16). Internal identifiers
        # (display_layer_row/_label/_buttons, on_display_layer_toggled) are
        # unchanged by the rename - same "display name changes, identifier
        # doesn't" convention as every other renamed block/section in this app.
        display_layer_row = QHBoxLayout()
        self.display_layer_label = QLabel()
        display_layer_row.addWidget(self.display_layer_label)
        self.display_layer_buttons: list[SvgLetterToggleButton] = []
        for i, label in enumerate(("R", "G", "B")):
            color = CHANNEL_COLORS.get(label, "#888")
            btn = SvgLetterToggleButton(label, color, initial_checked=True, size=(32, 28), icon_size=22)
            btn.toggled.connect(lambda checked, idx=i: self.on_display_layer_toggled(idx, checked))
            display_layer_row.addWidget(btn)
            self.display_layer_buttons.append(btn)
        display_layer_row.addStretch(1)
        independent_channels_layout.addLayout(display_layer_row)

        # Shown at the very top of the block, in place of everything below
        # it, while the active photo is in Normal mode - see
        # _sync_channels_panel_availability/set_block_disabled.
        self.channels_disabled_label = make_disabled_message_label()
        independent_channels_layout.addWidget(self.channels_disabled_label)

        # Channel tab selector: only the selected channel's Alignment/Light
        # controls are shown at a time (self.channel_stack) instead of all 3
        # ChannelPanels stacked full-width - the previous always-visible layout
        # ate a lot of both height and width in the fixed-width side panel.
        # ChannelTabFrame (channel_panel.py) is a "folder" tab strip + content
        # frame in one widget - the active tab's colored border rises up out of
        # the frame around it, rather than a separate frame the tab merely
        # touches. It owns self.channel_stack directly (reparents it into its
        # own layout), so build the stack first. Sits at the very top of the
        # block, Auto Align below it - the tabbed Alignment/Light editor is
        # this block's primary content, Auto Align/Lock Layer Position below it
        # are secondary actions that apply *to* it.
        self.channel_stack = QStackedWidget()
        for panel in self.channel_panels:
            self.channel_stack.addWidget(panel)

        self.channel_tab_frame = ChannelTabFrame(
            [layer.label for layer in self.layers], self.channel_stack)
        self.channel_tab_buttons = self.channel_tab_frame.buttons
        self.channel_tab_frame.channel_changed.connect(self.channel_stack.setCurrentIndex)
        independent_channels_layout.addWidget(self.channel_tab_frame)

        self.auto_align_button = QPushButton()
        style_primary_button(self.auto_align_button)
        self.auto_align_button.clicked.connect(self.on_auto_align_all)
        independent_channels_layout.addWidget(self.auto_align_button)

        # "Apply transform to auto align" - same discreet styling as Lock Layer
        # Position right below it. When checked, on_auto_align_all() also runs
        # alignment.optimize_distortion() after its normal dx/dy/scale/
        # rotation estimate, searching for a small per-channel lens correction
        # (Distortion/Vertical/Horizontal/Aspect) that further improves
        # registration - see that method and alignment.optimize_distortion for
        # the full design. QSettings- persisted like Batch Import's own
        # matching checkbox (batch_auto_align_apply_distortion) - a personal
        # workflow preference for the *action*, not project content, same
        # reasoning as Light Mode/Layout Presets.
        apply_distortion_row = QHBoxLayout()
        self.auto_align_apply_distortion_checkbox = CheckBox()
        self.auto_align_apply_distortion_checkbox.setStyleSheet("QCheckBox { color: #888; font-size: 11px; }")
        self.auto_align_apply_distortion_checkbox.setChecked(
            QSettings(ORG_NAME, APP_NAME).value("auto_align_apply_distortion", False, type=bool))
        self.auto_align_apply_distortion_checkbox.toggled.connect(self.on_auto_align_apply_distortion_toggled)
        apply_distortion_row.addWidget(self.auto_align_apply_distortion_checkbox)
        apply_distortion_row.addStretch(1)
        independent_channels_layout.addLayout(apply_distortion_row)

        # Lock Layer Position (here rather than in the Files block, since it
        # only ever applied to the 3 trichrome channels this block itself
        # controls, not to Files' own load-image concerns) - at the very bottom
        # and styled discreetly: a muted, smaller label (the same "#888 / 11px"
        # secondary-text convention used elsewhere in this app) and smaller
        # letter-toggle buttons than before, since which channel is the
        # geometric anchor is a one-time setup choice, not a
        # frequently-revisited control like Auto Align or the tabs above it.
        lock_row = QHBoxLayout()
        self.lock_label = QLabel()
        self.lock_label.setStyleSheet("color: #888; font-size: 11px;")
        lock_row.addWidget(self.lock_label)
        self.lock_buttons: list[SvgLetterToggleButton] = []
        self.lock_group = QButtonGroup(self)
        self.lock_group.setExclusive(True)
        for i, label in enumerate(("R", "G", "B")):
            color = CHANNEL_COLORS.get(label, "#888")
            btn = SvgLetterToggleButton(label, color, size=(24, 22), icon_size=16)
            btn.toggled.connect(lambda checked, idx=i: self.on_reference_toggled(idx, True) if checked else None)
            self.lock_group.addButton(btn)
            lock_row.addWidget(btn)
            self.lock_buttons.append(btn)
        lock_row.addStretch(1)
        self.lock_info_button = InfoButton("lock_layer_position_info")
        lock_row.addWidget(self.lock_info_button)
        independent_channels_layout.addLayout(lock_row)

        # Scan is a first-class block like every other one (grip/collapse/
        # close/title) - the real ScanPanel, ported over from the standalone
        # trichrome.scan_tool package (kept alive there too, for separate beta
        # testing).
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
        # Only ever scrolls vertically - block content must fit the column's
        # width, not spill sideways (blocks must adapt to the panel's width,
        # never the other way around).
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

        self.hq_preview_btn = SvgCheckableToolButton("Filmstrip/high_quality.svg")
        self.hq_preview_btn.toggled.connect(self.on_hq_preview_toggled)

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

        bottom_bar = QWidget()
        bottom_bar_layout = QHBoxLayout(bottom_bar)
        bottom_bar_layout.setContentsMargins(6, 4, 6, 4)
        for btn in (self.zoom_out_btn, self.zoom_in_btn, self.zoom_fit_btn, self.zoom_100_btn,
                    self.hq_preview_btn):
            bottom_bar_layout.addWidget(btn)
        # The yellow "mode is active" indicators (Compare's "Displaying
        # original", Move on Canvas's "Drag the ... layer...") used to sit
        # here, in the gap this stretch now fills alone - moved to the status
        # bar instead (see _build_ui's own status bar section,
        # status_bar_center_container).
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
        self.carousel.convert_to_trichrome_requested.connect(self.convert_items_to_trichrome)
        self.carousel.reordered.connect(self.on_carousel_reordered)
        self.carousel.files_dropped.connect(self.on_carousel_files_dropped)
        self.canvas.files_dropped.connect(self.on_carousel_files_dropped)
        self.scan_panel.add_to_session_requested.connect(self.on_scan_add_to_session_requested)
        self.scan_panel.pick_film_base_from_photo_toggled.connect(self.on_pick_film_base_from_photo_toggled)
        self.scan_panel.apply_film_base_requested.connect(self.on_apply_film_base_requested)
        self.scan_panel.capture_activity_changed.connect(
            lambda text: self._set_status_activity("scan", text or None))

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

        # Has a title, like every other block.
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
        central_outer_layout = QVBoxLayout(central)
        central_outer_layout.setContentsMargins(0, 0, 0, 0)
        central_outer_layout.setSpacing(0)
        # self.top_toolbar is a plain QWidget (not a real QToolBar/
        # addToolBar() dock) - see _build_top_toolbar's own docstring for
        # why - so it's placed here as central's own first row instead.
        central_outer_layout.addWidget(self.top_toolbar)
        central_layout = QHBoxLayout()
        # 0, not the original 10: that gap is gone, not just shrunk - it's
        # folded into _TOP_TOOLBAR_HEIGHT itself now, so the toolbar's own real
        # height is the whole span the icons center within, with the
        # splitter/preview frame starting immediately below it and nothing left
        # in between to read as extra dead space.
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(self.splitter)
        central_outer_layout.addLayout(central_layout)
        self.setCentralWidget(central)

        self.setStatusBar(_DeferringStatusBar())
        # Matches the rest of the app's chrome rather than the native look:
        # a discreet top hairline (same neutral rgba as Crop's
        # section_separator), no native per-item frames, and the same 11px
        # text size the yellow indicators below already use - text colors
        # themselves are left untouched.
        self.statusBar().setStyleSheet(
            "QStatusBar { border-top: 1px solid rgba(127, 127, 127, 70);"
            " font-size: 11px; min-height: 26px; padding-left: 6px; }"
            " QStatusBar::item { border: none; }"
        )

        # Yellow "mode is active" indicators (Compare's "Displaying original",
        # Move on Canvas's "Drag the ... layer...") - centered in the status
        # bar, rather than the preview bar above the canvas where they used to
        # live. Added as a *permanent* widget (addPermanentWidget, not
        # addWidget) specifically because QStatusBar auto-hides ordinary/
        # non-permanent widgets for the duration of any temporary showMessage()
        # text (confirmed directly, empirically) - these indicators must stay
        # visible through an unrelated "Session Saved"/"Auto-aligning..."
        # status message, not disappear underneath it.
        #
        # status_bar_left_spacer (added first, below) + this container
        # (stretch=1) + session_name_label (added last, fixed width) is what
        # makes the centering genuinely symmetric (the first version here had
        # only session_name_label on the right with nothing to balance it on
        # the left, so the indicators centered within a *skewed* leftover
        # space, reading as off-center whenever session_name_label had real
        # text). status_bar_left_spacer is kept exactly as wide as
        # session_name_label at all times (see _update_session_name_label), so
        # the leftover space this container's own stretch=1 absorbs is
        # symmetric and its paired addStretch(1)s truly center the 2 labels in
        # the status bar as a whole, not just in whatever happened to be left
        # over.
        self.status_bar_left_spacer = QWidget()
        self.statusBar().addPermanentWidget(self.status_bar_left_spacer)

        self.status_bar_center_container = QWidget()
        status_bar_center_layout = QHBoxLayout(self.status_bar_center_container)
        status_bar_center_layout.setContentsMargins(0, 0, 0, 0)
        status_bar_center_layout.setSpacing(8)
        self.compare_indicator = QLabel()
        self.compare_indicator.setStyleSheet("color: #f2c40c; font-weight: 600; font-size: 11px;")
        self.compare_indicator.setVisible(False)
        # A thin divider, shown only while BOTH indicators are visible at once
        # - otherwise the 2 yellow messages would run directly into each other
        # with nothing to tell them apart. A hidden widget takes no layout
        # space (same convention as status_activity_container below), so this
        # costs nothing when only one indicator (or neither) is showing - see
        # _update_status_bar_indicator_separator.
        self.status_bar_indicator_separator = QWidget()
        self.status_bar_indicator_separator.setFixedSize(1, 12)
        self.status_bar_indicator_separator.setStyleSheet("background-color: rgba(242, 196, 12, 110);")
        self.status_bar_indicator_separator.setVisible(False)
        # Shared by Move on Canvas and Stretch on Canvas - the 2 are mutually
        # exclusive (see on_active_toggled/on_stretch_toggled), so one label
        # showing whichever is currently active is simpler than 2
        # independently-toggled ones; see _update_canvas_drag_indicator.
        self.canvas_drag_indicator = QLabel()
        self.canvas_drag_indicator.setStyleSheet("color: #f2c40c; font-weight: 600; font-size: 11px;")
        self.canvas_drag_indicator.setVisible(False)
        status_bar_center_layout.addStretch(1)
        status_bar_center_layout.addWidget(self.compare_indicator)
        status_bar_center_layout.addWidget(self.status_bar_indicator_separator)
        status_bar_center_layout.addWidget(self.canvas_drag_indicator)
        status_bar_center_layout.addStretch(1)
        self.statusBar().addPermanentWidget(self.status_bar_center_container, 1)

        self.session_name_label = QLabel()
        # Right padding so the label doesn't sit flush against the window's
        # edge - most noticeable right after New Session/Open Session, when
        # its text changes and draws the eye.
        self.session_name_label.setStyleSheet("color: #888; font-size: 11px; padding-right: 10px;")
        self.statusBar().addPermanentWidget(self.session_name_label)

        # Bottom-left "work in progress" area: a spinning icon + a text label
        # listing every activity currently running (session save/load, photo
        # import N/X, export N/X, HQ Preview) - see _set_status_activity.
        # Originally HQ Preview's own spinner only. The icon uses the same
        # glyph and spin animation as the Scan block's own
        # "refresh"/device-poll button (Global/refresh.svg,
        # ScanPanel._on_refresh_spin_tick), continuously looping here instead
        # of that one's fixed 1-second one-shot spin, since a HQ compute's
        # duration isn't known in advance. Indeterminate ("busy") style, not a
        # real 0-100% meter - a single compose_trichrome/ compose_normal call
        # has no meaningful sub-steps to report. Not made non-interactive via
        # setEnabled(False) - that would dim it (SvgToolButton._glyph_color()'s
        # disabled state), unlike the Scan button it's matching, which stays
        # full-color while spinning; setFocusPolicy/cursor keep it from
        # inviting a click instead. Small square (not SvgToolButton's default
        # 30x26 hit-target box): that box plus margins was taller than the 26px
        # status bar and got pushed below the text's own center line.
        self.status_activity_icon = SvgToolButton("Global/refresh.svg", size=(16, 16), icon_size=14)
        self.status_activity_icon.setFocusPolicy(Qt.NoFocus)
        self.status_activity_icon.setCursor(Qt.ArrowCursor)
        self.status_activity_label = QLabel()
        self.status_activity_container = QWidget()
        status_activity_layout = QHBoxLayout(self.status_activity_container)
        status_activity_layout.setContentsMargins(0, 0, 4, 0)
        status_activity_layout.setSpacing(6)
        status_activity_layout.addWidget(self.status_activity_icon, 0, Qt.AlignVCenter)
        status_activity_layout.addWidget(self.status_activity_label, 0, Qt.AlignVCenter)
        self.status_activity_container.setVisible(False)
        # key -> displayed text, insertion-ordered; see _set_status_activity.
        self._status_activities: dict[str, str] = {}
        # Per key: when it started (time.monotonic()), and a generation
        # counter bumped on every update so a deferred clear can tell the
        # activity was restarted/updated since and must not remove it.
        self._status_activity_started: dict[str, float] = {}
        self._status_activity_gen: dict[str, int] = {}
        # Keys whose clear is deferred (minimum display time) and that hold
        # back showMessage() meanwhile - see _DeferringStatusBar.
        self._status_clears_holding: set[str] = set()
        # insertWidget(0, ...), not addWidget - index 0 is the exact slot
        # QStatusBar's own showMessage() label occupies (e.g. the
        # "Saving session…"-style text) - a hidden widget takes no layout
        # space, so this container sits flush at the status bar's own left
        # margin, the same starting point that text uses, rather than
        # wherever it happened to land after whatever else was already
        # added to the status bar.
        #
        # Being a normal (non-permanent) widget, QStatusBar hides it while a
        # temporary showMessage() text is up and brings it back afterward -
        # a finished task's own "done" message therefore naturally replaces
        # its progress text.
        self.statusBar().insertWidget(0, self.status_activity_container)
        # Continuous version of ScanPanel's own refresh-spin timer (same
        # 16ms/~60fps tick rate and -360deg/sec speed, see
        # _HQ_SPIN_TICK_MS above) - (re)started/stopped by
        # _refresh_status_activity, never directly by the container's own
        # setVisible.
        self._status_spin_angle = 0.0
        self._status_spin_timer = QTimer(self)
        self._status_spin_timer.setInterval(_HQ_SPIN_TICK_MS)
        self._status_spin_timer.timeout.connect(self._on_status_spin_tick)

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

    # This toolbar is a plain QWidget, not QToolBar - a real, confirmed dead
    # end across two separate fix attempts, worth recording so a third attempt
    # doesn't retry either of them: on real macOS, QToolBar's own native layout
    # (QMacStyle) reserves extra vertical room beyond what its fixed-size child
    # widgets need and top-anchors them in it - NOT reproducible under the
    # offscreen platform this app's headless tests use (it always renders a
    # QToolBar at exactly its requested height, no extra space), which is
    # exactly why both earlier attempts looked fixed in a headless render and
    # then weren't in the real build. Attempt 1: setContentsMargins/alignment
    # on the QToolBar itself - confirmed no effect. Attempt 2: setFixedHeight()
    # on the QToolBar, on the theory that a fixed height leaves the native
    # style nothing extra to add - also confirmed no effect; the native layout
    # still reserved its own extra space regardless, and even matching the
    # buttons' own height to that fixed value (this constant) didn't help,
    # since the toolbar's real on-screen height still didn't honor it. **The
    # only thing that actually worked**: stop using
    # QToolBar/QMainWindow.addToolBar() at all - this is now a plain QWidget +
    # QHBoxLayout, added as central's own first row (see _build_ui), which is
    # entirely Qt-managed layout with no native toolbar-area styling to fight.
    # Button height still matches this constant, which is also why it's the
    # *one* number to change for the bar's own total height - see this
    # constant's own value note below.
    #
    # 36, not 30 (a correction to the QToolBar rewrite above): the real problem
    # was never "too much space" - it's that the icons must be centered across
    # the *whole* visible bar, from the hairline below the title bar down to
    # wherever the next real boundary is (the preview canvas's own frame/the
    # first block panel) - not just within some smaller box this code draws a
    # second internal line under. An earlier pass here tried exactly that
    # second line (a border-bottom on the toolbar, with the real gap down to
    # the splitter left as a separate, unstyled margin) - confirmed via a
    # headless crop to look "fixed", but it narrowed the box the icons are
    # centered in instead of actually spanning the full visible bar, which was
    # visibly wrong in the real app. The fix is structural, not cosmetic: this
    # constant now *is* the bar's whole real height (the old 30 plus the old
    # separate 6px gap folded in), the toolbar has no border-bottom at all, and
    # central_layout's own top margin (see _build_ui) is 0 - so there is no
    # second box left to get this wrong a third time, only this one real, fully
    # Qt-managed height, with the button/icon centering this file's own
    # SvgToolButton.paintEvent already does correctly applying across all of
    # it.
    _TOP_TOOLBAR_HEIGHT = 40
    _TOP_TOOLBAR_BTN_SIZE = (32, _TOP_TOOLBAR_HEIGHT)
    _TOP_TOOLBAR_ICON_SIZE = 24

    def _build_top_toolbar(self) -> None:
        """A plain-widget bar sitting below the native title bar, mirroring
        the bottom bar's borderless SVG icon-button style. Left cluster:
        toggle-left-panel + save session + import. Right cluster: export,
        toggle-right-panel, help (Quick Start / Shortcuts).

        Deliberately NOT a real QToolBar and NOT merged into the title bar via
        setUnifiedTitleAndToolBarOnMac - either way of letting Cocoa/QMacStyle
        own this bar's native layout put its real on-screen vertical centering
        outside every Qt-side lever this code tried (see _TOP_TOOLBAR_HEIGHT's
        own comment for the 2 confirmed-dead-end attempts at making QToolBar
        behave). A plain QWidget with its own QHBoxLayout is simple, fully
        Qt-managed layout with no native toolbar chrome to fight - added as
        central's own first row in _build_ui, not via addToolBar()/a real
        QMainWindow toolbar area.
        """
        self.top_toolbar = QWidget()
        self.top_toolbar.setObjectName("topToolbarBar")
        # A bare QWidget doesn't paint its own stylesheet background/border by
        # default - the same gotcha documented for _ChannelFileBlock/the Batch
        # Import header bars - without this, the border-top divider below would
        # silently never paint.
        self.top_toolbar.setAttribute(Qt.WA_StyledBackground, True)
        self.top_toolbar.setFixedHeight(self._TOP_TOOLBAR_HEIGHT)
        # No border-bottom (see _TOP_TOOLBAR_HEIGHT's own comment): the icons
        # must be centered across the bar's *whole* visible height, down to
        # wherever the preview canvas's own frame starts right below, not
        # inside a second, narrower box this line would draw. Only border-top
        # remains, for the hairline under the title bar.
        self.top_toolbar.setStyleSheet(
            "#topToolbarBar { border: none; "
            "border-top: 1px solid rgba(128, 128, 128, 90); }"
        )
        toolbar_layout = QHBoxLayout(self.top_toolbar)
        # 0, not 10px side margins: real fixed-width spacer widgets (below)
        # are used instead for guaranteed, symmetric edge spacing - a plain
        # contentsMargins split wouldn't stay symmetric once e.g. the status
        # label's own width changes.
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(2)

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

        # "?" button: a menu rather than a single action, since it now covers
        # both the quick-start guide and the shortcuts reference. A distinct
        # attribute name from self.help_menu (the real menu-bar Help menu,
        # built earlier in _build_ui) - the two used to share the name
        # "help_menu", silently reassigning it here and leaving
        # retranslate_ui's self.help_menu.setTitle(...) call retitling this
        # popup instead of the real menu-bar entry (a harmless no-op, since a
        # popup QMenu has no visible title bar of its own, but the real Help
        # menu-bar label then never actually got retranslated on a language
        # switch) - fixed.
        self.help_toolbar_btn = SvgToolButton("Toolbar/help.svg", **btn_kwargs)
        self.help_toolbar_btn.setPopupMode(QToolButton.InstantPopup)
        self.help_toolbar_menu = QMenu(self.help_toolbar_btn)
        self.quick_tour_toolbar_action = QAction(self)
        self.quick_tour_toolbar_action.triggered.connect(lambda: open_quick_tour(self))
        self.help_toolbar_menu.addAction(self.quick_tour_toolbar_action)
        self.quickstart_toolbar_action = QAction(self)
        self.quickstart_toolbar_action.triggered.connect(self.show_quickstart_dialog)
        self.help_toolbar_menu.addAction(self.quickstart_toolbar_action)
        self.shortcuts_toolbar_action = QAction(self)
        self.shortcuts_toolbar_action.triggered.connect(self.show_shortcuts_dialog)
        self.help_toolbar_menu.addAction(self.shortcuts_toolbar_action)
        self.help_toolbar_btn.setMenu(self.help_toolbar_menu)

        # Default-layout quick-switch buttons (Trichrome/Color Correction/
        # Crop/Scan) - since layout is fully customizable (the block system
        # above), these 4 no longer toggle a fixed tool panel's visibility;
        # each instead applies its own fixed layout (see
        # _BUILT_IN_LAYOUT_STATES) via _activate_default_layout(). A single
        # exclusive QButtonGroup across all 4 (not two independent pairs like
        # the old tool-switcher) - only one default layout reads as "active"
        # (full color) at a time, the rest dimmed.
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

        # Split into two expanding halves so the 4 default-layout buttons
        # between them sit centered regardless of window width.
        toolbar_spacer_left = QWidget()
        toolbar_spacer_left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar_spacer_right = QWidget()
        toolbar_spacer_right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # -2px: toolbar_layout's own 2px inter-item spacing still applies
        # next to these, so the visible gap ends up exactly 10px.
        left_edge_spacer = QWidget()
        left_edge_spacer.setFixedWidth(8)
        right_edge_spacer = QWidget()
        right_edge_spacer.setFixedWidth(8)

        toolbar_layout.addWidget(left_edge_spacer)
        toolbar_layout.addWidget(self.new_session_toolbar_btn)
        toolbar_layout.addWidget(self.open_session_toolbar_btn)
        toolbar_layout.addWidget(self.save_session_toolbar_btn)
        toolbar_layout.addWidget(self.import_toolbar_btn)
        toolbar_layout.addWidget(toolbar_spacer_left)
        toolbar_layout.addWidget(self.trichrome_toolbar_btn)
        toolbar_layout.addWidget(self.settings_toolbar_btn)
        toolbar_layout.addWidget(self.crop_toolbar_btn)
        toolbar_layout.addWidget(self.scan_toolbar_btn)
        toolbar_layout.addWidget(toolbar_spacer_right)
        toolbar_layout.addWidget(self.export_toolbar_btn)
        toolbar_layout.addWidget(self.left_panel_toggle_btn)
        toolbar_layout.addWidget(self.right_panel_toggle_btn)
        toolbar_layout.addWidget(self.help_toolbar_btn)
        toolbar_layout.addWidget(right_edge_spacer)

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

    # ------------------------------------------------------------------ Block
    # system - which side panel each block lives in, its position there, and
    # its visible/collapsed state. Freely reassignable at runtime via drag
    # (BlockReorderZone/_on_block_dropped), the collapse/close buttons on each
    # block's own header, and the Tools menu; see
    # _DEFAULT_BLOCK_SIDE/_DEFAULT_BLOCK_VISIBLE/
    # _DEFAULT_LEFT_BLOCK_ORDER/_DEFAULT_RIGHT_BLOCK_ORDER for the fallback
    # shape restored by Window > Reset Layout.
    # ------------------------------------------------------------------
    def _block_shown(self, key: str) -> bool:
        """block_visible, except that a disabled Scan tool is never shown."""
        if key == "scan" and not self.scan_tool_enabled:
            return False
        return self.block_visible.get(key, True)

    def _apply_block_layout(self) -> None:
        """Rebuilds left_layout/right_layout from block_side/block_visible/
        left_block_order/right_block_order - the single place block-system
        state turns into actual on-screen layout. Called after every
        drag-drop, visibility toggle, reset, and layout restore."""
        if self.light_mode_active:
            self._apply_light_mode_block_layout()
            return
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
                widget.setVisible(self._block_shown(key) and self.block_side.get(key) == side)

        self.left_container.set_block_widgets(
            {k: w for k, w in self.block_widgets.items() if self.block_side.get(k) == "left"})
        self.right_container.set_block_widgets(
            {k: w for k, w in self.block_widgets.items() if self.block_side.get(k) == "right"})

        for key, action in self.block_menu_actions.items():
            action.blockSignals(True)
            action.setChecked(self._block_shown(key))
            action.blockSignals(False)

        # Force both scroll areas to re-evaluate their contained widget's width
        # against the viewport - without this, a block moved by drag
        # (removeWidget/insertWidget, not a real user resize) could leave a
        # stale cached size behind, and the "no horizontal scrollbar" fix would
        # silently stop applying after a drag.
        for layout in (self.left_layout, self.right_layout):
            layout.invalidate()
            layout.activate()
        for container in (self.left_container, self.right_container):
            container.updateGeometry()

    def _apply_light_mode_block_layout(self) -> None:
        """Light mode's fixed rendering override - forces exactly Files /
        Trichrome Process / Crop into the left panel, in that order, regardless
        of their Advanced-mode block_side/block_visible/order (Crop in
        particular normally defaults to hidden, on the right panel).
        Deliberately does not read or write block_side/
        block_visible/left_block_order/right_block_order at all - those stay
        exactly as Advanced mode left them, so returning to Advanced mode needs
        no restore step. See _LIGHT_MODE_BLOCK_KEYS."""
        for key in _LIGHT_MODE_BLOCK_KEYS:
            widget = self.block_widgets.get(key)
            if widget is not None:
                self.left_layout.removeWidget(widget)
        for i, key in enumerate(_LIGHT_MODE_BLOCK_KEYS):
            widget = self.block_widgets.get(key)
            if widget is not None:
                self.left_layout.insertWidget(i, widget)
                widget.setVisible(True)
        for key, widget in self.block_widgets.items():
            if key not in _LIGHT_MODE_BLOCK_KEYS:
                widget.setVisible(False)
        self.left_container.set_block_widgets(
            {k: self.block_widgets[k] for k in _LIGHT_MODE_BLOCK_KEYS if k in self.block_widgets})
        self.right_container.set_block_widgets({})
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
        if self.light_mode_active:
            # Light mode's layout is a fixed override (see
            # _apply_light_mode_block_layout) - never let a drag inside it
            # write into block_side/left_block_order/right_block_order,
            # which are the same dicts Advanced mode uses and are
            # otherwise left completely untouched while light_mode_active.
            return
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
            if k != dragged_key and self._block_shown(k) and self.block_side.get(k) == target_side
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
            # Hiding the Crop block while active crop mode is armed would leave
            # a live canvas overlay with no panel to interact with - fold
            # active mode off too (same as Escape), just reached via the close
            # button/Tools menu instead of the keyboard. This does NOT run the
            # other way: showing the block never arms active mode on its own -
            # see _set_crop_active.
            self._set_crop_active(False)
        if key == "crop" and not visible:
            self._set_perspective_active(False)
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
        self._set_perspective_active(False)
        self._deactivate_canvas_drag_modes()

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
        """Loads one of the 4 built-in default-layout menu entries (name is the
        fixed display identifier - "Trichrome"/"Color Correction"/
        "Crop"/"Scan") and syncs the matching toolbar button's exclusive
        checked state - the single entry point for all 3 ways to trigger this
        (toolbar click, bare keyboard shortcut, Window menu item), so whichever
        was used, the toolbar always ends up showing the right one active.
        Always reapplies the layout even if that button was already checked
        (e.g. re-pressing T after dragging blocks around resets back to the
        Trichrome layout), unlike a plain radio-button click which would be a
        no-op in that case. Applies the fixed dict literal in
        _BUILT_IN_LAYOUT_STATES directly - not a QSettings custom preset (see
        that dict's own comment) - so this can never silently break if the
        user's custom presets get cleared (e.g. by build_mac.sh). Activating
        the "Crop" slot specifically also arms active crop mode - every other
        slot (and the preset load itself, via _apply_restored_layout)
        deactivates it, since loading a layout otherwise always turns active
        crop mode off."""
        button = self._default_layout_buttons.get(name)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        self._apply_layout_state(_BUILT_IN_LAYOUT_STATES[name])
        self._set_perspective_active(False)
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
        never be Delete-able. These 4 slots no longer resolve to a
        QSettings preset at all (see _BUILT_IN_LAYOUT_STATES) - if a user
        saves an ordinary custom preset under some other name (even one
        that used to be special, like "NewTrichrome"), it's a perfectly
        normal preset with its own Load/Update/Delete here, no special
        casing."""
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
            panel.distortion_changed.connect(lambda idx=i: self.on_distortion_changed(idx))
            panel.tone_changed.connect(lambda idx=i: self.on_tone_changed(idx))
            panel.reset_align_requested.connect(lambda idx=i: self.on_reset_align(idx))
            panel.reset_distortion_requested.connect(lambda idx=i: self.on_reset_distortion(idx))
            panel.reset_stretch_requested.connect(lambda idx=i: self.on_reset_stretch(idx))
            panel.reset_tone_requested.connect(lambda idx=i: self.on_reset_tone(idx))
            panel.solo_toggled.connect(lambda checked, idx=i: self.on_solo_toggled(idx, checked))
            panel.active_toggled.connect(lambda checked, idx=i: self.on_active_toggled(idx, checked))
            panel.stretch_toggled.connect(lambda checked, idx=i: self.on_stretch_toggled(idx, checked))
            # Keep each of the 3 ChannelPanel sections (Light/Position/
            # Distortion) expanded/collapsed in lockstep across all 3 R/G/B
            # tabs - expanding e.g. Position on the Red tab also expands it on
            # Green/Blue, so switching tabs to edit the same kind of setting on
            # another channel doesn't require re-expanding the section every
            # time.
            for section_attr in ("tone_box", "position_box", "distortion_box"):
                box = getattr(panel, section_attr)
                box.toggled.connect(
                    lambda checked, attr=section_attr, idx=i: self._sync_channel_section_toggle(attr, idx, checked))

        self.channel_tab_frame.channel_changed.connect(self.on_channel_tab_changed)

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

        # View menu - mirrors the preview bar's own controls (see _build_ui
        # for why none of these get a real QAction-level shortcut). Present
        # in both Light and Advanced mode; Thumbnails/Grid View are
        # Advanced-only (hidden in Light mode - see
        # _apply_light_mode_ui_state) but are wired the same way
        # regardless, same as window_thumbnails_action above.
        self.view_zoom_in_action.triggered.connect(self.on_zoom_in_clicked)
        self.view_zoom_out_action.triggered.connect(self.on_zoom_out_clicked)
        self.view_zoom_fit_action.triggered.connect(self.canvas.zoom_fit)
        self.view_zoom_100_action.triggered.connect(self.canvas.zoom_100)

        self.view_hq_preview_action.setChecked(self.hq_preview_btn.isChecked())
        self.view_hq_preview_action.triggered.connect(
            lambda checked: self.hq_preview_btn.setChecked(checked))
        self.hq_preview_btn.toggled.connect(self.view_hq_preview_action.setChecked)

        self.view_compare_action.setChecked(self.compare_btn.isChecked())
        self.view_compare_action.triggered.connect(
            lambda checked: self.compare_btn.setChecked(checked))
        self.compare_btn.toggled.connect(self.view_compare_action.setChecked)

        # Fullscreen isn't a plain checkable button (fullscreen_btn.clicked,
        # not .toggled - see toggle_focus_mode, which drives both its own
        # checked state and this action's from self._is_focus_mode
        # explicitly) - triggered just calls the same toggle function every
        # other fullscreen entry point (Cmd+F, Escape, the toolbar button)
        # already uses.
        self.view_fullscreen_action.setChecked(self._is_focus_mode)
        self.view_fullscreen_action.triggered.connect(lambda _checked=False: self.toggle_focus_mode())

        self.view_thumbnails_action.setChecked(self.carousel_toggle_btn.isChecked())
        self.view_thumbnails_action.setEnabled(self.carousel_toggle_btn.isEnabled())
        self.view_thumbnails_action.triggered.connect(
            lambda checked: self.carousel_toggle_btn.setChecked(checked))
        self.carousel_toggle_btn.toggled.connect(self.view_thumbnails_action.setChecked)

        self.view_grid_action.setChecked(self.grid_view_toggle_btn.isChecked())
        self.view_grid_action.triggered.connect(
            lambda checked: self.grid_view_toggle_btn.setChecked(checked))
        self.grid_view_toggle_btn.toggled.connect(self.view_grid_action.setChecked)

        # Tools menu lists every block individually (replacing the old 4
        # tool-switcher-mirroring actions) - each a plain independent checkable
        # toggle wired straight to set_block_visible, which is also what each
        # block's own close button calls, so both stay in sync regardless of
        # which one the user used.
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
        self.crop_panel.geometry_changed.connect(self.on_crop_geometry_changed)
        self.crop_panel.reset_geometry_requested.connect(self.on_crop_geometry_reset)
        self.crop_panel.perspective_toggled.connect(self._set_perspective_active)
        self.canvas.perspective_guides_changed.connect(self.on_perspective_guides_changed)
        self.crop_panel.activate_toggled.connect(self._set_crop_active)

        self.curves_panel.changed.connect(self.on_curve_changed)
        self.curves_panel.reset_requested.connect(self.on_curve_reset)

        self.canvas.drag_delta.connect(self.on_canvas_drag)
        self.canvas.scale_delta.connect(self.on_canvas_scale)
        self.canvas.rotate_delta.connect(self.on_canvas_rotate)
        self.canvas.stretch_drag_started.connect(self.on_canvas_stretch_drag_started)
        self.canvas.stretch_drag_delta.connect(self.on_canvas_stretch_drag)
        self.canvas.stretch_drag_finished.connect(self.on_canvas_stretch_drag_finished)

        self.compare_btn.toggled.connect(self.on_compare_toggled)

    # ------------------------------------------------------------------
    # Fullscreen / focus mode
    # ------------------------------------------------------------------
    def _update_fullscreen_action_text(self) -> None:
        key = "menu_view_exit_fullscreen" if self._is_focus_mode else "menu_view_fullscreen"
        self.view_fullscreen_action.setText(i18n.tr(key) + "\t⌘F")

    def toggle_focus_mode(self) -> None:
        self._is_focus_mode = not self._is_focus_mode
        self.fullscreen_btn.setChecked(self._is_focus_mode)
        self.view_fullscreen_action.setChecked(self._is_focus_mode)
        self._update_fullscreen_action_text()
        if self._is_focus_mode:
            self.left_scroll.setVisible(False)
            self.right_scroll.setVisible(False)
            self.showFullScreen()
            self.fullscreen_btn.setToolTip(i18n.tr("exit_fullscreen_button"))
        else:
            self.showNormal()
            # Respect whatever the left/right panel toggle buttons were set
            # to before entering fullscreen, rather than forcing both back
            # on - except the right panel, which must stay hidden in Light
            # mode regardless of that toggle's own checked state (see
            # _apply_light_mode_ui_state) - a real latent bug otherwise,
            # since fullscreen stays available in Light mode.
            self.left_scroll.setVisible(self.left_panel_toggle_btn.isChecked())
            self.right_scroll.setVisible(not self.light_mode_active and self.right_panel_toggle_btn.isChecked())
            self.fullscreen_btn.setToolTip(i18n.tr("fullscreen_button"))

    # ------------------------------------------------------------------
    # Compare (preview the original, color adjustments bypassed)
    # ------------------------------------------------------------------
    def on_compare_toggled(self, active: bool) -> None:
        self._compare_active = active
        self.compare_indicator.setVisible(active)
        self._update_status_bar_indicator_separator()
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
            # Grid mode becomes the active panel for Up/Down navigation
            # right away, regardless of which panel had focus before
            # activating it (e.g. a side tool panel, which would otherwise
            # keep eating Up/Down to scroll itself instead of moving
            # between photos) - a real click on a cell already moves focus
            # here on its own; this covers activation via the toolbar
            # button or the bare G shortcut too.
            self.carousel.grid_scroll.setFocus()
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
        self.view_thumbnails_action.setEnabled(multi and not grid_active)
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

        if event.key() == Qt.Key_Escape and self._perspective_active:
            # Cancels guided Perspective mode, guides discarded, nothing
            # applied - same convention as Crop's own Escape just below.
            self._set_perspective_active(False)
            event.accept()
            return

        if event.key() == Qt.Key_Escape and self._crop_active:
            # Discards any in-progress drag and exits active crop mode -
            # deliberately does NOT hide the Crop block/change layout unlike a
            # plain set_block_visible("crop", False).
            self._set_crop_active(False)
            event.accept()
            return

        if event.key() == Qt.Key_Escape and (self.active_index is not None or self.stretch_index is not None):
            # Same "Escape backs out of it" convention as Crop's own Escape
            # handler just above.
            self._deactivate_canvas_drag_modes()
            event.accept()
            return

        if event.key() == Qt.Key_Escape and self.grid_view_toggle_btn.isChecked():
            self.grid_view_toggle_btn.setChecked(False)
            event.accept()
            return

        focus = QApplication.focusWidget()
        text_editing = isinstance(focus, (QAbstractSpinBox, QLineEdit))
        if (not text_editing and event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and self.grid_view_toggle_btn.isChecked()):
            self.grid_view_toggle_btn.setChecked(False)
            event.accept()
            return

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

        # Light mode has no Color panel (W's target), no right panel (O),
        # no filmstrip/grid (P/G) - guarded below rather than relying on
        # the now-hidden toolbar buttons alone, since these are bare
        # keyPressEvent shortcuts that bypass menu/toolbar visibility
        # entirely. I (left panel) is left ungated deliberately - Light
        # mode's own 3 blocks live there and toggling the panel itself is
        # harmless (nothing to lose, unlike O/P/G which would reveal or
        # activate a feature Light mode otherwise fully hides).
        if (not text_editing and event.key() == Qt.Key_W
                and event.modifiers() == Qt.NoModifier
                and not self.light_mode_active):
            self.color_panel.pick_white_balance_btn.toggle()
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_I
                and event.modifiers() == Qt.NoModifier):
            self.left_panel_toggle_btn.toggle()
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_O
                and event.modifiers() == Qt.NoModifier
                and not self.light_mode_active):
            self.right_panel_toggle_btn.toggle()
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_P
                and event.modifiers() == Qt.NoModifier
                and not self.light_mode_active
                and self.carousel_toggle_btn.isEnabled()):
            self.carousel_toggle_btn.toggle()
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_G
                and event.modifiers() == Qt.NoModifier
                and not self.light_mode_active):
            self.grid_view_toggle_btn.toggle()
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_H
                and event.modifiers() == Qt.NoModifier):
            self.hq_preview_btn.toggle()
            event.accept()
            return

        # The 4 default-layout quick-switch shortcuts would blow away Light
        # mode's own fixed layout override (and Scan's in particular is
        # fully unavailable there) - guarded the same way as W/O/P/G above.
        if (not text_editing and event.key() == Qt.Key_T
                and event.modifiers() == Qt.NoModifier
                and not self.light_mode_active):
            self._activate_default_layout("Trichrome")
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_S
                and event.modifiers() == Qt.NoModifier
                and not self.light_mode_active and self.scan_tool_enabled):
            self._activate_default_layout("Scan")
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_E
                and event.modifiers() == Qt.NoModifier
                and not self.light_mode_active):
            self._activate_default_layout("Color Correction")
            event.accept()
            return

        if (not text_editing and event.key() == Qt.Key_C
                and event.modifiers() == Qt.NoModifier):
            if self.light_mode_active:
                # No layout to switch to in Light mode (Crop is already
                # one of its permanently-visible blocks) - C instead
                # mirrors the Crop block's own Activate button directly.
                self._set_crop_active(not self._crop_active)
            else:
                self._activate_default_layout("Crop")
            event.accept()
            return

        if (not text_editing and event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and self._perspective_active):
            self.on_perspective_apply()
            event.accept()
            return

        if (not text_editing and event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and self._crop_active):
            self.on_crop_apply()
            event.accept()
            return

        if (not text_editing and event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and (self.active_index is not None or self.stretch_index is not None)):
            # Same "Enter commits/exits it" convention as Crop's own Enter
            # handler just above - there's nothing to commit here (a canvas
            # drag already writes straight into the model on every move, see
            # on_canvas_drag/on_canvas_stretch_drag_*), so this just
            # deactivates, same as Escape.
            self._deactivate_canvas_drag_modes()
            event.accept()
            return

        # Arrow-key alignment nudging (while a channel is marked Active) is
        # handled in eventFilter(), not here - see its own comment for why.
        # By the time an arrow key reaches this method, active_index is
        # already known to be None (eventFilter consumes the event outright
        # otherwise), so no guard is needed here for it.

        if self.carousel.count():
            if not text_editing and event.key() in (Qt.Key_Left, Qt.Key_Right):
                extend = bool(event.modifiers() & Qt.ShiftModifier)
                if event.key() == Qt.Key_Left:
                    self.carousel.go_prev(extend_selection=extend)
                else:
                    self.carousel.go_next(extend_selection=extend)
                event.accept()
                return
            if (not text_editing and event.key() in (Qt.Key_Up, Qt.Key_Down)
                    and self.grid_view_toggle_btn.isChecked()):
                extend = bool(event.modifiers() & Qt.ShiftModifier)
                if event.key() == Qt.Key_Up:
                    self.carousel.go_up(extend_selection=extend)
                else:
                    self.carousel.go_down(extend_selection=extend)
                event.accept()
                return
            if (not text_editing and event.key() == Qt.Key_A
                    and (event.modifiers() & Qt.ControlModifier)
                    and not self.light_mode_active):
                self.carousel.toggle_select_all()
                event.accept()
                return
            # Light mode always has exactly one BatchItem and it must never
            # be deletable (self.carousel.count() is always >= 1 there, so
            # this branch would otherwise still fire and delete the only
            # photo despite the filmstrip itself being hidden).
            if (not text_editing and event.key() in (Qt.Key_Backspace, Qt.Key_Delete)
                    and (event.modifiers() & Qt.ControlModifier)
                    and not self.light_mode_active):
                self.delete_batch_items(self.carousel.selected_indices())
                event.accept()
                return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Help dialogs
    # ------------------------------------------------------------------
    def show_quickstart_dialog(self) -> None:
        # +50% over the shared base width (560 -> 840) - this dialog's content
        # (mode/tool descriptions, numbered Batch Import steps) reads better
        # wider; the Shortcuts dialog keeps the plain base size.
        self._show_help_dialog(
            i18n.tr("help_quickstart_title"), i18n.tr("help_quickstart_content"), width=840)

    def show_shortcuts_dialog(self) -> None:
        content = i18n.tr("help_shortcuts_content").replace(
            _GENERAL_SHORTCUTS_PLACEHOLDER, self._general_shortcuts_html())
        self._show_shortcuts_dialog(i18n.tr("help_shortcuts_title"), content)

    def _shortcut_key_text(self, action: QAction) -> str:
        """Display text for a live QAction shortcut (e.g. "Cmd+Shift+S"),
        used by _general_shortcuts_html() so the Shortcuts dialog can't
        silently drift from what the app actually does - a real bug that
        bit the arrow-key alignment nudge earlier. QKeySequence.PortableText
        always spells the modifier as "Ctrl"/"Shift" regardless of platform
        or language, so both get substituted for this app's own display
        convention (mac "Cmd", and Shift translated for the current UI
        language)."""
        text = action.shortcut().toString(QKeySequence.PortableText)
        return text.replace("Ctrl", "Cmd").replace("Shift", i18n.tr("shortcut_key_shift"))

    def _general_shortcuts_html(self) -> str:
        """The Shortcuts dialog's "Files & Edit" section is part static text
        (in help_shortcuts_files_edit_static: bare keyPressEvent/no-shortcut
        bindings with no derivable QAction shortcut() - Delete Selection,
        Close Window, Guide, Quit, see below) and part generated here
        from each real QAction's own live shortcut(), for the subset that
        has one, so renaming/rebinding one of those can't leave the dialog
        silently describing the wrong key the way a fully hand-typed copy
        could. Quit is deliberately NOT derived from quit_action despite
        having a real QAction: QKeySequence(QKeySequence.Quit).toString() is
        empty on macOS by design (confirmed directly) - Cmd+Q is supplied
        automatically by Cocoa once QAction.QuitRole is set (see
        quit_action's own setup), not tracked as an explicit key sequence Qt
        itself can report. Delete Selection/Close Window have no QAction-
        level shortcut() at all either, by design - see their own setup
        comments - so they can't be derived the same way Quit's text is
        simply missing; both are static for a different reason than Quit."""
        def item(action: QAction, desc: str) -> str:
            return f"<li><kbd>{self._shortcut_key_text(action)}</kbd> — {desc}</li>"

        def combo_item(action_a: QAction, action_b: QAction, desc: str) -> str:
            key_text = f"<kbd>{self._shortcut_key_text(action_a)}</kbd> / <kbd>{self._shortcut_key_text(action_b)}</kbd>"
            return f"<li>{key_text} — {desc}</li>"

        items = [
            item(self.new_session_action, i18n.tr("menu_new_session")),
            item(self.open_session_action, i18n.tr("menu_open_session")),
            item(self.save_session_action, i18n.tr("menu_save_session")),
            item(self.save_session_as_action, i18n.tr("menu_save_session_as")),
            item(self.batch_action, i18n.tr("menu_batch")),
            item(self.export_action,
                 f"{i18n.tr('export_button')} ({i18n.tr('shortcut_export_hint')})"),
            combo_item(self.undo_action, self.redo_action,
                       f"{i18n.tr('menu_undo')} / {i18n.tr('menu_redo')}"),
            combo_item(self.copy_action, self.paste_action, i18n.tr("shortcut_copy_paste_hint")),
            combo_item(self.rotate_right_action, self.rotate_left_action,
                       f"{i18n.tr('menu_edit_rotate_right')} / {i18n.tr('menu_edit_rotate_left')}"),
            i18n.tr("help_shortcuts_files_edit_static"),
        ]
        return "\n".join(items)

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

    def _help_dialog_kbd_bg_color(self) -> str:
        """Background tint for a <kbd> key-cap badge in the Shortcuts dialog -
        same blend direction/weight as quick_tour.py's own TourCallout._kbd_bg,
        so a key reads identically whether it's shown mid-tour or in this
        dialog."""
        fg = self.palette().color(QPalette.WindowText)
        bg = self.palette().color(QPalette.Base)
        t = 0.16
        return "#%02x%02x%02x" % (
            round(bg.red() + (fg.red() - bg.red()) * t),
            round(bg.green() + (fg.green() - bg.green()) * t),
            round(bg.blue() + (fg.blue() - bg.blue()) * t),
        )

    # Each plain <h3> is one framed section, each <h4> a subsection inside
    # it (see _show_help_dialog). Shortcuts splits on the same tags.
    _HELP_H3_SPLIT_RE = re.compile(r"<h3>(.*?)</h3>(.*?)(?=<h3>|\Z)", re.DOTALL)
    _HELP_H4_SPLIT_RE = re.compile(r"<h4>(.*?)</h4>(.*?)(?=<h4>|\Z)", re.DOTALL)
    # Subsection titles tab in under the section title, and their text tabs one
    # step further.
    _HELP_SUBSECTION_INDENT = 22
    _HELP_SUBSECTION_BODY_INDENT = 22
    _HELP_SECTION_GAP = 16

    @staticmethod
    def _help_plain_text(html: str) -> str:
        return _html_unescape(re.sub(r"<[^>]+>", " ", html))

    def _help_rich_html(self, body_html: str, normal: str, muted: str, kbd_bg: str) -> str:
        """Body HTML for a help label: <b> and <h4> take the "normal" color,
        everything else the muted one, and <kbd> becomes a tinted key-cap badge
        (the same look as quick_tour.py's TourCallout). &nbsp; pads it since
        Qt's rich text has no CSS padding."""
        styled = re.sub(r"<b>", f'<b style="color:{normal};">', body_html)
        styled = re.sub(r"<h4>", f'<h4 style="color:{normal};">', styled)
        styled = re.sub(
            r"<kbd>(.*?)</kbd>",
            rf'<span style="background-color:{kbd_bg}; color:{normal}; font-weight:600;">'
            r"&nbsp;\1&nbsp;</span>",
            styled)
        return f'<div style="color:{muted};">{styled}</div>'

    def _help_rich_label(self, html: str) -> QLabel:
        label = QLabel(html)
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        return label

    def _show_help_dialog(self, title: str, html: str, width: int = 560) -> None:
        """Quick Start: a sidebar (search box and section list) beside one
        framed text window, the same panel look as Preferences and Batch Import
        (widgets/dialog_style.py) - but only those two outer frames; categories
        inside the text window are plain titles separated by a hairline, not
        individually framed. Each <h3> is a section title, its <h4>s
        subsections inside it, title then text, tabbed in. Search hides the
        sections and subsections that don't match. Enter or a sidebar click
        scrolls the text window so that row's title lands at the top."""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        QShortcut(QKeySequence.Close, dialog, activated=dialog.close)
        normal, muted = self._help_dialog_text_colors()
        kbd_bg = self._help_dialog_kbd_bg_color()
        # Guide titles are bigger than the body text. Section titles +5pt bold,
        # subsection titles +2pt.
        base_pt = QApplication.font().pointSizeF() or 13.0
        section_font = QApplication.font()
        section_font.setPointSizeF(base_pt + 5)
        section_font.setBold(True)
        sub_pt = base_pt + 2

        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(PANEL_PADDING, 12, PANEL_PADDING, 14)
        column_layout.setSpacing(0)

        # One record per section and per subsection, in document order:
        # the sidebar row, the widget to scroll to, and the widgets the
        # search hides, each with the plain text it matches against.
        sections = []
        toc_rows = []  # (sidebar title, level, search key, scroll target, record)
        highlightable = []  # (label, its unhighlighted HTML) - search marks matches in place
        for index, (h3_title, body) in enumerate(self._HELP_H3_SPLIT_RE.findall(html)):
            divider_wrap = None
            if index > 0:
                divider_wrap = QWidget()
                divider_layout = QVBoxLayout(divider_wrap)
                divider_layout.setContentsMargins(0, 10, 0, 14)
                divider = QFrame()
                divider.setFixedHeight(1)
                divider.setStyleSheet("background: rgba(127, 127, 127, 70); border: none;")
                divider_layout.addWidget(divider)
                column_layout.addWidget(divider_wrap)

            title_label = make_section_title(column_layout)
            title_label.setTextFormat(Qt.RichText)
            title_label.setFont(section_font)
            title_label.setText(_html_escape(_html_unescape(h3_title)))
            highlightable.append((title_label, title_label.text()))

            first_h4 = body.find("<h4>")
            direct_html = body if first_h4 == -1 else body[:first_h4]
            direct_label = None
            if direct_html.strip():
                direct_label = self._help_rich_label(
                    self._help_rich_html(direct_html, normal, muted, kbd_bg))
                column_layout.addWidget(direct_label)
                highlightable.append((direct_label, direct_label.text()))

            section = {
                "title": title_label, "divider": divider_wrap, "direct": direct_label,
                "direct_key": _help_search_key(self._help_plain_text(direct_html)),
                "key": _help_search_key(self._help_plain_text(h3_title + body)),
                "subs": [],
            }
            sections.append(section)
            toc_rows.append((_html_unescape(h3_title), 3, section["key"], title_label, section))
            subs_html = body[first_h4:] if first_h4 != -1 else ""
            for h4_title, h4_body in self._HELP_H4_SPLIT_RE.findall(subs_html):
                wrap = QWidget()
                wrap_layout = QVBoxLayout(wrap)
                wrap_layout.setContentsMargins(0, 8, 0, 0)
                wrap_layout.setSpacing(4)
                sub_title = self._help_rich_label(
                    f'<span style="font-weight:600; font-size:{sub_pt}pt; color:{normal};">'
                    f'{h4_title}</span>')
                title_row = QHBoxLayout()
                title_row.setContentsMargins(self._HELP_SUBSECTION_INDENT, 0, 0, 0)
                title_row.addWidget(sub_title)
                wrap_layout.addLayout(title_row)
                body_row = QHBoxLayout()
                body_row.setContentsMargins(
                    self._HELP_SUBSECTION_INDENT + self._HELP_SUBSECTION_BODY_INDENT, 0, 0, 0)
                sub_body = self._help_rich_label(self._help_rich_html(h4_body, normal, muted, kbd_bg))
                body_row.addWidget(sub_body)
                wrap_layout.addLayout(body_row)
                highlightable.append((sub_title, sub_title.text()))
                highlightable.append((sub_body, sub_body.text()))
                column_layout.addWidget(wrap)
                sub = {
                    "wrap": wrap,
                    "key": _help_search_key(self._help_plain_text(h4_title + h4_body)),
                }
                section["subs"].append(sub)
                toc_rows.append((_html_unescape(h4_title), 4, sub["key"], sub_title, sub))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        column.setStyleSheet("background: transparent;")
        scroll.setWidget(column)

        # The one frame around the whole text window - categories inside it are
        # not individually framed.
        text_frame = QFrame()
        text_frame.setObjectName("dialogPanel")
        text_frame.setStyleSheet(PANEL_STYLE)
        text_frame_layout = QVBoxLayout(text_frame)
        text_frame_layout.setContentsMargins(1, 1, 1, 1)  # inside the 1px border
        text_frame_layout.setSpacing(0)
        text_frame_layout.addWidget(scroll)

        sidebar_column = QWidget()
        sidebar_column.setFixedWidth(_HELP_TOC_WIDTH)
        sidebar_layout = QVBoxLayout(sidebar_column)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar = make_panel(sidebar_layout)
        sidebar.setContentsMargins(8, 8, 8, 8)  # tighter than the text window, the sidebar is narrow

        search_edit = QLineEdit()
        search_edit.setPlaceholderText(i18n.tr("help_search_placeholder"))
        search_edit.setClearButtonEnabled(True)
        search_edit.setStyleSheet(  # rounded like the panels around it (PANEL_STYLE, radius 6px)
            "QLineEdit { padding: 6px 4px; border: 1px solid rgba(127, 127, 127, 70);"
            " border-radius: 6px; background: rgba(127, 127, 127, 30); }")
        search_edit.addAction(
            tinted_svg_icon("Global/search.svg", 16, muted, self.devicePixelRatioF()),
            QLineEdit.LeadingPosition)
        sidebar.addWidget(search_edit)
        sidebar.addSpacing(10)  # air before the category list

        toc = QListWidget()
        toc.setFrameShape(QFrame.NoFrame)
        toc.setStyleSheet("QListWidget { background: transparent; }")
        toc.setWordWrap(True)
        toc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for toc_title, level, _key, _target, _record in toc_rows:
            item = QListWidgetItem(toc_title if level == 3 else f"    {toc_title}")
            if level == 3:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            toc.addItem(item)
        sidebar.addWidget(toc, 1)

        # "No results" / "1 result" / "N results", shown only while searching.
        result_count_label = QLabel()
        result_count_label.setStyleSheet(f"color: {muted};")
        result_count_label.setVisible(False)
        sidebar.addWidget(result_count_label)

        visible_rows = []  # indexes into toc_rows, in document order
        match_pos = {"index": -1}

        def _scroll_to_row(row: int) -> None:
            # The row's title lands at the very top of the text window, not
            # just "somewhere visible".
            target = toc_rows[row][3]
            top = target.mapTo(column, QPoint(0, 0)).y()
            bar = scroll.verticalScrollBar()
            bar.setValue(max(0, min(bar.maximum(), top - 4)))

        def _apply_search(query: str) -> None:
            needle = _help_search_key(query.strip())
            for section in sections:
                section_match = not needle or needle in section["key"]
                section["title"].setVisible(section_match)
                if section["divider"] is not None:
                    section["divider"].setVisible(section_match)
                if section["direct"] is not None:
                    section["direct"].setVisible(not needle or needle in section["direct_key"])
                for sub in section["subs"]:
                    sub["wrap"].setVisible(not needle or needle in sub["key"])
            visible_rows.clear()
            for index, (_t, level, key, _target, record) in enumerate(toc_rows):
                shown = not needle or needle in key
                toc.setRowHidden(index, not shown)
                if shown:
                    visible_rows.append(index)
            match_count = 0
            for label, base_html in highlightable:
                marked_html, n = _help_highlight_html(base_html, needle)
                label.setText(marked_html)
                if not label.isHidden() and not label.parentWidget().isHidden():
                    match_count += n
            if not needle:
                result_count_label.setVisible(False)
            else:
                if not visible_rows or match_count == 0:
                    result_count_label.setText(i18n.tr("help_search_no_results"))
                elif match_count == 1:
                    result_count_label.setText(i18n.tr("help_search_result_count_one"))
                else:
                    result_count_label.setText(i18n.tr("help_search_result_count", n=match_count))
                result_count_label.setVisible(True)
            match_pos["index"] = -1
            if visible_rows:
                _scroll_to_row(visible_rows[0])

        def _find_next() -> None:
            # Enter steps through the visible rows and wraps at the end.
            if not visible_rows:
                return
            match_pos["index"] = (match_pos["index"] + 1) % len(visible_rows)
            _scroll_to_row(visible_rows[match_pos["index"]])

        search_edit.textChanged.connect(_apply_search)
        search_edit.returnPressed.connect(_find_next)
        toc.itemClicked.connect(lambda item: _scroll_to_row(toc.row(item)))

        content_row = QHBoxLayout()
        content_row.setSpacing(self._HELP_SECTION_GAP)
        content_row.addWidget(sidebar_column)
        content_row.addWidget(text_frame, 1)

        layout = QVBoxLayout(dialog)
        layout.addLayout(content_row)
        close_btn = QPushButton("OK")
        style_primary_button(close_btn)
        close_btn.clicked.connect(dialog.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dialog.resize(width + _HELP_TOC_WIDTH + self._HELP_SECTION_GAP, 620)
        dialog.exec()

    def _show_shortcuts_dialog(self, title: str, html: str) -> None:
        """A dedicated builder for the Shortcuts dialog, distinct from the
        table-of-contents layout _show_help_dialog uses for Quick Start:
        Shortcuts never had enough lines to justify a sidebar, so each
        top-level <h3> category instead becomes its own collapsible section
        (CollapsibleSection, expanded by default - only the 5 top-level
        categories collapse, not the <h4> tool subsections nested inside
        "Tools"), separated by a thin hairline - the same flat-divider
        convention batch_window.py's own Import Rules sections already use."""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        QShortcut(QKeySequence.Close, dialog, activated=dialog.close)

        normal, muted = self._help_dialog_text_colors()
        kbd_bg = self._help_dialog_kbd_bg_color()

        sections_container = QWidget()
        sections_layout = QVBoxLayout(sections_container)
        sections_layout.setContentsMargins(4, 4, 4, 4)
        sections_layout.setSpacing(0)

        for index, (section_title, body_html) in enumerate(self._HELP_H3_SPLIT_RE.findall(html)):
            if index > 0:
                sections_layout.addSpacing(4)
                separator = QFrame()
                separator.setFixedHeight(1)
                separator.setStyleSheet("background: rgba(127, 127, 127, 70); border: none;")
                sections_layout.addWidget(separator)
                sections_layout.addSpacing(6)

            section = CollapsibleSection(expanded=True)
            # "&&" escapes a literal "&" (e.g. "Files & Edit") against Qt's own
            # mnemonic-accelerator parsing on a QAbstractButton's text - the
            # exact same bug as solo_checkbox's "(B&W)" (a lone "&" there
            # silently became an underlined mnemonic instead of a literal
            # ampersand).
            section.toggle_button.setText(_html_unescape(section_title).replace("&", "&&"))

            # <b>/<h4> get the same "normal" (non-muted) color the old
            # QTextBrowser-based rendering gave them via its own
            # document().setDefaultStyleSheet - everything else inherits the
            # surrounding div's muted color. <kbd> (an actual key/key combo, as
            # opposed to <b>'s broader "UI term" emphasis) gets the same tinted
            # key-cap badge quick_tour.py's own TourCallout already uses for
            # shortcut mentions mid-tour - &nbsp; padding since Qt's rich text
            # has no CSS padding.
            styled_body = re.sub(r"<b>", f'<b style="color:{normal};">', body_html)
            styled_body = re.sub(r"<h4>", f'<h4 style="color:{normal};">', styled_body)
            styled_body = re.sub(
                r"<kbd>(.*?)</kbd>",
                rf'<span style="background-color:{kbd_bg}; color:{normal}; font-weight:600;">'
                r"&nbsp;\1&nbsp;</span>",
                styled_body)
            body_label = QLabel(f'<div style="color:{muted};">{styled_body}</div>')
            body_label.setTextFormat(Qt.RichText)
            body_label.setWordWrap(True)
            section.content_layout.addWidget(body_label)

            sections_layout.addWidget(section)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(sections_container)

        layout = QVBoxLayout(dialog)
        layout.addWidget(scroll)
        close_btn = QPushButton("OK")
        style_primary_button(close_btn)
        close_btn.clicked.connect(dialog.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dialog.resize(560, 620)
        dialog.exec()

    # ------------------------------------------------------------------
    # Batch mode
    # ------------------------------------------------------------------
    def open_batch_window(self) -> None:
        # Only one Import window at a time (a real bug: this used to
        # unconditionally build a fresh BatchWindow on every call, so repeated
        # Cmd+I presses stacked up multiple import windows instead of surfacing
        # the one already open). BatchWindow has no WA_DeleteOnClose, so
        # closing it only hides it - the Python/C++ object and
        # self.batch_window itself both survive, making isHidden() a safe,
        # cheap check here without needing a try/except for a deleted-wrapper
        # RuntimeError. A closed (hidden) window still gets a genuinely fresh
        # instance below, same as before - its file-matching state never needs
        # to survive across separate batch imports, only across repeated
        # presses while it's already open.
        if self.batch_window is not None and not self.batch_window.isHidden():
            self.batch_window.raise_()
            self.batch_window.activateWindow()
            return
        self.batch_window = BatchWindow(self)
        self.batch_window.show()
        self.batch_window.raise_()
        self.batch_window.activateWindow()

    # ------------------------------------------------------------------
    # Batch import (background load of many triplets into independent items)
    # ------------------------------------------------------------------
    def start_batch_import(
        self, triplets, ref_letter: str, auto_align: bool, apply_distortion: bool,
        replace: bool, harris_shutter: bool,
    ) -> None:
        """``harris_shutter`` is an explicit parameter - the only caller,
        BatchWindow.start_import(), derives it from its own Processing Mode
        radios (B&W/Color Trichrome) rather than this reaching into
        self.import_panel.is_harris_shutter_active(), which used to silently
        read whatever the *main window's currently active photo* happened to
        have set, regardless of what's actually being batch-imported.
        ``apply_distortion`` is BatchWindow's own "Apply transform to auto
        align" checkbox - meaningless (and never read) when ``auto_align`` is
        False."""
        self._import_replace = replace
        self._import_pending = [None] * len(triplets)
        self._set_status_activity("import", i18n.tr("batch_import_status_running", i=0, n=len(triplets)))

        self._import_thread = QThread(self)
        self._import_worker = BatchImportWorker(
            triplets=triplets,
            ref_letter=ref_letter,
            auto_align=auto_align,
            apply_distortion=apply_distortion,
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
        self._set_status_activity("import", i18n.tr("batch_import_status_running", i=done, n=total),
                                  interrupt_message=False)

    def _on_batch_import_item_ready(self, index: int, item, warning: str) -> None:
        self._import_pending[index] = item

    def _on_batch_import_finished(self) -> None:
        items = [it for it in self._import_pending if it is not None]
        self._import_pending = []
        self._load_batch_items(items, replace=self._import_replace)
        self._set_status_activity("import", None)
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

        self.carousel.set_items([it.base for it in self.batch_items], [it.mode for it in self.batch_items])

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
        self.carousel.set_items([it.base for it in self.batch_items], [it.mode for it in self.batch_items])
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
        geo_params = [(l.dx, l.dy, l.scale, l.rotation, l.distortion, l.perspective_v, l.perspective_h,
                       l.anamorphic, l.stretch_pins) for l in item.layers]
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

    # ------------------------------------------------------------------ Normal
    # / Trichrome mode - see BatchItem.mode/ normal_layer in model.py.
    # Trichrome is the app's original behavior (3 R/G/B shots recomposed);
    # Normal is a single already-color photo, loaded straight through without
    # any warp/alignment/recompose step - Light/Color/Crop/Curves still apply
    # on top either way (see recompute_preview's mode branch), only the RGB
    # Channels tool (which only makes sense for the 3-channel case) becomes
    # unavailable.
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
        # ChannelTabFrame reads self.isEnabled() directly in its own
        # paintEvent to gray its folder-border color, so disabling the
        # whole block above (which cascades to every descendant, including
        # channel_tab_frame) is enough on its own for that one.
        self.channel_tab_frame.update()
        # Each ChannelPanel's own 2 colored left-edge accents (Alignment/ Light
        # - see channel_panel.py) still need this explicit call, same reason as
        # ChannelTabFrame doesn't: an explicit QSS color doesn't automatically
        # dim just because the widget's ancestor is disabled.
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
        # Keeps the carousel's own cached per-item mode (used by its "Convert
        # to Trichrome" context-menu eligibility check) in sync with every
        # mode-switch handler below, without each of them needing to call it
        # separately - this is their one shared tail.
        if 0 <= self.batch_current_index < len(self.batch_items):
            self.carousel.set_item_mode(self.batch_current_index, mode)

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
            # would leave 1-2 loaded channels invisible/unused - ask which one
            # to keep editing, instead of silently picking one.
            dialog = ModeSwitchDialog(available, i18n.tr("mode_switch_dialog_text"), self)
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
        if self.normal_layer.has_image():
            # The active Solo photo has a real image - ask which of the 3
            # channels it should become, mirroring _switch_to_normal_mode's
            # own "which channel do you want to keep" dialog in reverse.
            # Skipped entirely for an empty Solo photo (nothing to assign).
            harris_shutter = self.import_panel.is_harris_shutter_active()
            mode_key = "color_trichrome" if harris_shutter else "bw_trichrome"
            text = i18n.tr("mode_switch_to_trichrome_dialog_text",
                            mode=i18n.tr(MODE_LABEL_KEYS[mode_key]))
            dialog = ModeSwitchDialog([True, True, True], text, self)
            dialog.exec()
            if dialog.chosen_index is None:
                self._sync_import_and_channels_ui()  # revert the combo, nothing changed
                return
            self._assign_normal_photo_to_channel(item, dialog.chosen_index, harris_shutter)
            return

        self.push_undo()
        item.mode = "trichrome"
        self._sync_import_and_channels_ui()
        self.recompute_preview()
        self.canvas.zoom_fit()

    def _assign_normal_photo_to_channel(self, item, index: int, harris_shutter: bool) -> None:
        """Loads the active Solo photo's own file into Trichrome channel
        ``index`` - the reverse of _switch_to_normal_mode, used when
        switching Solo -> Trichrome and the user picks which channel this
        photo should become (ModeSwitchDialog). The other 2 channels are
        left completely untouched, same "nothing else is silently
        clobbered" principle _switch_to_normal_mode already follows."""
        path = self.normal_layer.path
        try:
            full = imaging.load_grayscale(path, channel=CHANNEL_NAMES[index] if harris_shutter else None)
        except Exception as exc:
            show_alert(self, i18n.tr("dialog_load_error_title"),
                                  i18n.tr("dialog_load_error_text", error=exc))
            self._sync_import_and_channels_ui()
            return
        if self.normal_layer.quarter_turns:
            full = np.ascontiguousarray(np.rot90(full, self.normal_layer.quarter_turns))
        full = imaging.apply_film_base_correction(full, None, channel=CHANNEL_NAMES[index])

        self.push_undo()
        preview, preview_scale = imaging.make_preview(full)
        layer = item.layers[index]
        layer.path = path
        layer.image_full = full
        layer.image_preview = preview
        layer.preview_scale = preview_scale
        layer.harris_shutter = harris_shutter
        layer.film_base = None
        layer.reset_alignment()
        layer.reset_tone()
        layer.quarter_turns = self.normal_layer.quarter_turns
        # invert is meant to stay uniform across all 3 trichrome channels
        # (see on_invert_toggled) - propagated to all of them rather than
        # only the chosen one, so the Light panel's Negative toggle keeps
        # reading one consistent state afterward.
        for channel_layer in item.layers:
            channel_layer.invert = self.normal_layer.invert
        item.mode = "trichrome"
        # _sync_import_and_channels_ui() only refreshes the Mode combo/Solo
        # File Path row - it never touches the 3 channel filename labels
        # (every other call site that changes layer.path does this itself,
        # see e.g. activate_batch_item/on_channel_swap_requested), so
        # without this the newly-assigned channel kept showing "No image
        # loaded" the first time a fresh item went Solo -> Trichrome.
        self.import_panel.set_filename(index, os.path.basename(layer.path))
        self._sync_panel_from_layer(index)
        self._sync_import_and_channels_ui()
        self.recompute_preview()
        self.canvas.zoom_fit()

    def on_carousel_files_dropped(self, paths: list[str]) -> None:
        """Photos dragged in from Finder directly onto the thumbnail strip, the
        grid view, or the preview canvas itself while it's showing its
        empty-project placeholder (CanvasWidget.files_dropped, only armed while
        there's nothing to show) - each becomes its own new Normal-mode photo,
        appended at the end of the filmstrip and treated as Normal mode by
        default. One unreadable file among several doesn't abort the rest."""
        new_items = []
        failed = []
        try:
            for i, path in enumerate(paths):
                # flush=True: this loop is synchronous, the event loop never
                # gets a chance to paint the N/X progress on its own.
                self._set_status_activity(
                    "import", i18n.tr("batch_import_status_running", i=i + 1, n=len(paths)), flush=True)
                try:
                    new_items.append(self._build_normal_batch_item(path))
                except Exception:
                    failed.append(os.path.basename(path))
        finally:
            self._set_status_activity("import", None)
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

        ``film_base`` (optional {"R"/"G"/"B": float}, the Scan tool's "Sample
        Film Base" reference - a per-channel mean of the film's own
        clear/unexposed base) is stored on each layer *and* divided out of its
        own channel's raw density *before* invert (see ChannelLayer.film_base's
        docstring in model.py) - color negative's orange mask biases the raw
        RGB-Light-scanned channels unevenly (e.g. much less blue transmitted
        than red/green even at a neutral scene point), and that bias does NOT
        survive as a simple uniform tint through the 1-x invert (it becomes
        tone-dependent), which is exactly why a post-invert white- balance pick
        alone can't remove it. Normalizing so the sampled clear-film value maps
        to 1.0 in every channel *before* inverting is what lets the resulting
        positive be genuinely neutral in the shadows, not just at whichever one
        tone was picked."""
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
            # Explicit, not just relying on ChannelLayer's own default - an RGB
            # Light triplet is always recomposed as Standard (B&W) Trichrome,
            # never Color Trichrome ("RGB Light = Standard Trichrome").
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

        ``black_white`` is the Film mode's own "force this composite to true
        neutral gray" flag (True only for B&W) - applied here, uniformly across
        both kinds, onto the freshly-built item's
        GlobalCorrection.black_white_active, per the film-type auto-processing
        rules (see ScanPanel._auto_add_to_session's own docstring for the full
        mapping). The Light-mode half of the same rules ("External/White =
        Solo, RGB Light = Standard Trichrome") needs no extra code here - it's
        already exactly what ``kind`` ("normal" vs "trichrome") and
        _build_trichrome_batch_item_from_paths's own explicit
        harris_shutter=False already produce."""
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

    @staticmethod
    def _is_batch_item_empty(item) -> bool:
        """True if ``item`` has no image data or path in any of its 3
        trichrome channels nor its normal_layer - i.e. still the
        untouched placeholder a fresh session/New Session starts with,
        never a real photo whose channels just failed to load. Same
        "genuinely empty" criterion the session-restore paths
        (_legacy_restore_session/_build_restored_items_from_data) already
        use to drop such an item on load."""
        return not any(l.path for l in item.layers) and not item.normal_layer.path

    def _append_new_batch_items(self, items: list) -> None:
        """Shared tail for dropping files onto the carousel
        (on_carousel_files_dropped) and adding Scan tool captures
        (on_scan_add_to_session_requested) - appends ``items`` at the end
        of batch_items, makes them the sole selection, activates the last
        one, and refreshes the carousel/thumbnails. Mirrors
        duplicate_batch_item's own carousel-update sequence."""
        if not items:
            return
        if self.batch_items and all(self._is_batch_item_empty(it) for it in self.batch_items):
            # These are the very first real photo(s) ever added to this
            # project - the existing batch is nothing but untouched empty
            # placeholder(s) (a fresh session's own default item), so drop
            # them instead of leaving a stray "empty" thumbnail sitting
            # alongside the real photo(s) being added.
            self.batch_items = []
        self.batch_items.extend(items)
        new_index = len(self.batch_items) - 1
        added_ids = {id(it) for it in items}
        for it in self.batch_items:
            it.selected = id(it) in added_ids

        self.carousel.set_items([it.base for it in self.batch_items], [it.mode for it in self.batch_items])
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
        self.stretch_index = None
        self._set_perspective_active(False)
        self._update_canvas_drag_indicator()
        self.carousel.set_current(index)
        self.color_panel.set_pick_white_balance_active(False)
        self.canvas.set_wb_pick_enabled(False)
        self.scan_panel.set_pick_from_photo_active(False)
        self.canvas.set_film_base_pick_enabled(False)

        for i, panel in enumerate(self.channel_panels):
            panel.active_checkbox.blockSignals(True)
            panel.active_checkbox.setChecked(False)
            panel.active_checkbox.blockSignals(False)
            panel.stretch_checkbox.blockSignals(True)
            panel.stretch_checkbox.setChecked(False)
            panel.stretch_checkbox.blockSignals(False)
            panel.solo_checkbox.blockSignals(True)
            panel.solo_checkbox.setChecked(self.layers[i].solo)
            panel.solo_checkbox.blockSignals(False)
        self._sync_canvas_drag_mode()

        for i in range(3):
            layer = self.layers[i]
            self.import_panel.set_filename(i, os.path.basename(layer.path) if layer.path else "")
            self._sync_panel_from_layer(i)
        self.light_panel.set_invert(self._active_invert_state())
        self._refresh_reference_ui()
        self._sync_global_panel_from_model()
        self._sync_import_and_channels_ui()
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
            **cr.geometry_kwargs(),
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
            for name in ("distortion", "perspective_v", "perspective_h", "anamorphic"):
                setattr(cr, name, cd.get(name, 0.0))

        if self.batch_current_index in indices:
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

        self.carousel.set_items([it.base for it in self.batch_items], [it.mode for it in self.batch_items])

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

        self.carousel.set_items([it.base for it in self.batch_items], [it.mode for it in self.batch_items])
        for i, it in enumerate(self.batch_items):
            it.selected = it is dup
            self.carousel.set_selected(i, it.selected)
        self.activate_batch_item(index + 1)
        self._update_carousel_visibility(force_show=True)
        self._refresh_all_carousel_thumbnails()
        self.statusBar().showMessage(i18n.tr("status_photo_duplicated"), 4000)

    def convert_items_to_trichrome(self, indices: list[int]) -> None:
        """Builds one new Classic Trichrome BatchItem out of 1-3 selected Solo
        photos (CarouselWidget's "Convert to Trichrome" context-menu item) - in
        filmstrip order, the first becomes the Red channel, the second (if any)
        Green, the third (if any) Blue, each flattened to luminance the same
        way a real classic-trichrome shot would be (imaging.load_grayscale with
        no channel argument - this is always Classic, never Color Trichrome,
        since a Solo photo has no per-channel decode of its own to preserve).
        Inserted right after the first source photo, named with the same "(N)"
        version suffix Duplicate uses. The source photo(s) are left completely
        untouched - this creates a new item, it doesn't consume them. The menu
        itself (CarouselWidget._on_card_context_menu) already restricts this to
        exactly the eligible case (1-3 targets, all still Solo), so the guards
        below are defensive, not expected to actually fire."""
        indices = sorted(i for i in indices if 0 <= i < len(self.batch_items))
        if not (1 <= len(indices) <= 3):
            return
        sources = [self.batch_items[i] for i in indices]
        if any(it.mode != "normal" for it in sources):
            return

        layers = new_project_layers()
        for ci, src in enumerate(sources):
            if not src.normal_layer.has_image():
                continue
            try:
                full = imaging.load_grayscale(src.normal_layer.path)
            except Exception as exc:
                show_alert(self, i18n.tr("dialog_load_error_title"),
                           i18n.tr("dialog_load_error_text", error=exc))
                return
            if src.normal_layer.quarter_turns:
                full = np.ascontiguousarray(np.rot90(full, src.normal_layer.quarter_turns))
            preview, preview_scale = imaging.make_preview(full)
            layer = layers[ci]
            layer.path = src.normal_layer.path
            layer.image_full = full
            layer.image_preview = preview
            layer.preview_scale = preview_scale
            layer.quarter_turns = src.normal_layer.quarter_turns

        self.push_undo()
        first = sources[0]
        new_item = BatchItem(
            base=self._duplicate_base_name(first.base), paths={}, layers=layers,
            global_corr=GlobalCorrection(), mode="trichrome", selected=False)
        insert_at = indices[0] + 1
        self.batch_items.insert(insert_at, new_item)

        self.carousel.set_items([it.base for it in self.batch_items], [it.mode for it in self.batch_items])
        for i, it in enumerate(self.batch_items):
            it.selected = it is new_item
            self.carousel.set_selected(i, it.selected)
        self.activate_batch_item(insert_at)
        self._update_carousel_visibility(force_show=True)
        self._refresh_all_carousel_thumbnails()
        self.statusBar().showMessage(i18n.tr("status_photo_converted_to_trichrome"), 4000)

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
        self.stretch_index = None
        self._set_perspective_active(False)
        self._update_canvas_drag_indicator()
        self._sync_canvas_drag_mode()

        self.carousel.set_items([it.base for it in self.batch_items], [it.mode for it in self.batch_items])
        for i, it in enumerate(self.batch_items):
            self.carousel.set_selected(i, it.selected)
        self.carousel.set_current(index)
        self._update_carousel_visibility()

        for i, panel in enumerate(self.channel_panels):
            panel.active_checkbox.blockSignals(True)
            panel.active_checkbox.setChecked(False)
            panel.active_checkbox.blockSignals(False)
            panel.stretch_checkbox.blockSignals(True)
            panel.stretch_checkbox.setChecked(False)
            panel.stretch_checkbox.blockSignals(False)
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
        # Called after every _edit_counter change (push_undo/undo/redo),
        # so the status bar's unsaved-changes asterisk stays in sync.
        self._update_session_name_label()

    # ------------------------------------------------------------------
    # Loading images
    # ------------------------------------------------------------------
    def load_image(self, index: int) -> None:
        channel = i18n.channel_name(index)
        name_filter = f"Images ({imaging.qt_image_name_filter_patterns()});;" + i18n.tr("file_filter_all")
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

    # Fields kept pinned to their channel slot when swapping two channels'
    # images (on_channel_swap_requested) - color_index/label are the slot's
    # own identity, is_reference is the Lock Layer Position anchor choice,
    # and solo is a per-panel "preview this channel alone" UI toggle - none
    # of these describe the photo itself, unlike every other ChannelLayer
    # field (path, image data, alignment, tone, invert, harris_shutter,
    # film_base, quarter_turns), which all travel with the photo.
    _CHANNEL_SWAP_PINNED_FIELDS = {"color_index", "label", "is_reference", "solo"}

    def _swap_channel_layers(self, i: int, j: int) -> None:
        li, lj = self.layers[i], self.layers[j]
        for f in dataclasses.fields(ChannelLayer):
            if f.name in self._CHANNEL_SWAP_PINNED_FIELDS:
                continue
            vi, vj = getattr(li, f.name), getattr(lj, f.name)
            setattr(li, f.name, vj)
            setattr(lj, f.name, vi)

    def on_channel_swap_requested(self, from_index: int, to_index: int) -> None:
        """A channel's drag handle (ImportPanel's Files block) was dropped
        onto another channel's filename - swap which photo (and its own
        alignment/tone edits) is loaded into each of the two channels."""
        if from_index == to_index:
            return
        if not (0 <= from_index < len(self.layers) and 0 <= to_index < len(self.layers)):
            return
        self.push_undo()
        self._swap_channel_layers(from_index, to_index)
        for i in (from_index, to_index):
            layer = self.layers[i]
            self.import_panel.set_filename(i, os.path.basename(layer.path) if layer.path else "")
            self._sync_panel_from_layer(i)
        self.recompute_preview()
        self.canvas.zoom_fit()

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
        try:
            for step, (item_index, ci) in enumerate(targets, start=1):
                # Synchronous folder walk + reload - flush so N / X paints.
                self._set_status_activity("locate", i18n.tr(
                    "status_locating_files", i=step, n=len(targets)), flush=True)
                item = self.batch_items[item_index]
                layer = item.layers[ci]
                found = self._find_file_in_folder(folder, os.path.basename(layer.path))
                if found is not None and self._relink_channel(item, ci, found):
                    relinked += 1
                else:
                    unresolved.append((item_index, ci, original_base[item_index], layer.label, layer.path))
        finally:
            self._set_status_activity("locate", None)

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
        name_filter = f"Images ({imaging.qt_image_name_filter_patterns()});;" + i18n.tr("file_filter_all")
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
        .trirgb) or reopening it failed. Settings > "Reopen the last session
        at launch" off skips both, starting on an empty session."""
        if not setting_bool(ORG_NAME, APP_NAME, REOPEN_LAST_SESSION_KEY):
            return
        last_path = QSettings(ORG_NAME, APP_NAME).value("last_session_file_path", "", type=str)
        if last_path and os.path.isfile(last_path):
            try:
                self.load_session_from_path(last_path, show_warnings=False)
                return
            except Exception:
                pass  # corrupted/empty/unreadable - fall through to the legacy restore

        self._legacy_restore_session()

    def _legacy_restore_session(self, key_prefix: str = "session", restore_layout: bool = True) -> None:
        """Rebuild every batch item (photos + their alignment/color settings)
        saved by ``_save_session_state`` on the previous close. Any channel
        whose file changed (or vanished) on disk since then is left unloaded,
        same policy as the old single-item restore. Superseded by the
        .trirgb-based restore in _restore_session, kept as a fallback.

        ``key_prefix``/``restore_layout`` mirror _save_session_state's own
        parameters - see _restore_light_mode_state, which calls this with
        key_prefix="light_session" and restore_layout=False (Light mode's
        layout is always its own fixed override, never a restored one)."""
        settings = QSettings(ORG_NAME, APP_NAME)

        def key(suffix: str) -> str:
            return _session_state_key(key_prefix, suffix)

        # Backward-compat default for a session saved before Harris Shutter
        # became per-channel - such a file only has this one session-wide flag,
        # not a per-channel value, so fall back to it below when the newer
        # per-channel key is missing. Read-only and never written by
        # _save_session_state under any prefix, so it deliberately isn't itself
        # indirected through key().
        legacy_harris_shutter_default = settings.value("harris_shutter_enabled", False, type=bool)
        count = settings.beginReadArray(key("items"))
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
                layer.distortion = settings.value(prefix + "distortion", 0.0, type=float)
                layer.perspective_v = settings.value(prefix + "perspective_v", 0.0, type=float)
                layer.perspective_h = settings.value(prefix + "perspective_h", 0.0, type=float)
                layer.anamorphic = settings.value(prefix + "anamorphic", 0.0, type=float)
                layer.stretch_pins = _decode_stretch_pins(settings.value(prefix + "stretch_pins", "", type=str))
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
            for name in ("distortion", "perspective_v", "perspective_h", "anamorphic"):
                setattr(cr, name, settings.value(f"crop_{name}", 0.0, type=float))
            try:
                cr.perspective_guides = CropSettings.guides_from_json(
                    json.loads(settings.value("crop_perspective_guides", "[]", type=str)))
            except json.JSONDecodeError:
                cr.perspective_guides = ()

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

        saved_index = settings.value(key("current_index"), 0, type=int)
        self._apply_restored_items(
            restored_items,
            settings.value(key("sort_mode"), "import_order", type=str),
            settings.value(key("sort_reversed"), False, type=bool),
            saved_index,
        )
        if not restore_layout:
            return

        def _load_json(qkey: str):
            raw = settings.value(qkey, "", type=str)
            if not raw:
                return None
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return None

        self._apply_restored_layout(
            settings.value(key("left_panel_visible"), True, type=bool),
            settings.value(key("right_panel_visible"), True, type=bool),
            settings.value(key("carousel_visible"), True, type=bool),
            _load_json(key("block_side")),
            _load_json(key("block_visible")),
            _load_json(key("block_collapsed")),
            _load_json(key("left_block_order")),
            _load_json(key("right_block_order")),
        )

    def _restore_light_mode_state(self) -> None:
        """Light mode's own minimal, QSettings-only autosave - restores the
        single photo that was active when the app last closed while in Light
        mode. Deliberately never goes through the .trirgb-based
        _restore_session path (Light mode has no session-file concept at all),
        and never restores layout (restore_layout=False) - Light mode's layout
        is always its own fixed override, applied separately by
        _apply_light_mode_ui_state. See _save_light_mode_state."""
        self._legacy_restore_session(key_prefix="light_session", restore_layout=False)

    def _save_light_mode_state(self) -> None:
        self._save_session_state(key_prefix="light_session")

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
        right_block_order (the block system) are all optional/ None-safe so an
        old saved session or .trirgb from before this feature existed just
        keeps whatever __init__'s own defaults (_DEFAULT_BLOCK_SIDE etc.)
        already set up, rather than needing every caller to know that default
        itself. Only known block keys are accepted, so a future block key
        removed from a newer version can't leave a stale/unreachable entry
        around."""
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
        # Loading any layout (a session restore, or a Layout Preset - built- in
        # or custom) always deactivates active crop mode, whether or not the
        # Crop block ends up visible - "changing layout" turns it off
        # unconditionally. _activate_default_layout re-arms it afterward
        # specifically for the "Crop" slot; nothing else should.
        self._set_crop_active(False)
        self._set_perspective_active(False)
        # Same "changing layout always turns this off" rule, extended to Move
        # on Canvas / Stretch on Canvas.
        self._deactivate_canvas_drag_modes()

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

        self.carousel.set_items([it.base for it in self.batch_items], [it.mode for it in self.batch_items])
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
                    "distortion": layer.distortion, "perspective_v": layer.perspective_v,
                    "perspective_h": layer.perspective_h, "anamorphic": layer.anamorphic,
                    "stretch_pins": [list(p) for p in layer.stretch_pins],
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
                    **cr.geometry_kwargs(),
                    "perspective_guides": cr.guides_to_json(),
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
        # became per-channel - such a file only has this one session-wide key,
        # not a per-channel value.
        legacy_harris_shutter_default = data.get("harris_shutter_enabled", False)
        restored_items = []
        # Every layer to load, grouped by preview_cache.layer_cache_key -
        # filled in after the loop (_resolve_restored_previews), so each
        # distinct file is decoded once, cached ones not at all.
        preview_jobs: dict[str, tuple[tuple, list]] = {}

        def queue_preview(layer, path: str, decode: str, slot: str) -> None:
            key = preview_cache.layer_cache_key(path, decode, slot, layer.film_base, layer.quarter_turns)
            job = preview_jobs.setdefault(
                key, ((path, decode, slot, layer.film_base, layer.quarter_turns), []))
            job[1].append(layer)

        for item_data in data.get("items", []):
            layers = []
            for ci, ch in enumerate(item_data.get("channels", [])):
                layer = ChannelLayer(color_index=ci, label=CHANNEL_NAMES[ci])
                layer.is_reference = ch.get("is_reference", ci == 1)
                layer.invert = ch.get("invert", False)
                layer.harris_shutter = ch.get("harris_shutter", legacy_harris_shutter_default)
                layer.dx = ch.get("dx", 0.0)
                layer.dy = ch.get("dy", 0.0)
                layer.scale = ch.get("scale", 1.0)
                layer.rotation = ch.get("rotation", 0.0)
                layer.distortion = ch.get("distortion", 0.0)
                layer.perspective_v = ch.get("perspective_v", 0.0)
                layer.perspective_h = ch.get("perspective_h", 0.0)
                layer.anamorphic = ch.get("anamorphic", 0.0)
                layer.stretch_pins = [
                    tuple(float(x) for x in pin) for pin in ch.get("stretch_pins", []) if len(pin) == 4
                ]
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
                    queue_preview(layer, path, CHANNEL_NAMES[ci] if layer.harris_shutter else "L",
                                  CHANNEL_NAMES[ci])
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
                queue_preview(normal_layer, normal_path, "RGB", "N")

            if not any(l.path for l in layers) and not normal_path:
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
            for name in ("distortion", "perspective_v", "perspective_h", "anamorphic"):
                setattr(cr, name, float(c.get(name, 0.0)))
            cr.perspective_guides = CropSettings.guides_from_json(c.get("perspective_guides"))

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

        self._resolve_restored_previews(preview_jobs, preview_cache.read_cache_block(data))

        sort_mode = data.get("sort_mode", "import_order")
        sort_reversed = bool(data.get("sort_reversed", False))
        current_index = int(data.get("current_index", 0))
        return restored_items, sort_mode, sort_reversed, current_index

    def _resolve_restored_previews(self, preview_jobs: dict, cache_entries: dict) -> None:
        """Gives every queued layer its preview: from the session's preview
        cache when its source file is unchanged, otherwise decoded from the
        original (each distinct file once, several in parallel). Layers
        sharing a key share one array. Cache-sourced arrays are recorded in
        _cached_previews (once installed) so _start_preview_upgrade can replace them with the
        exact recomputation and save can reuse their entry untouched. A
        file that fails to decode leaves its layers without a preview, i.e.
        is_missing(), same as before."""
        cached: dict[str, tuple] = {}
        resolved: dict[str, tuple] = {}
        to_decode = []
        for key, (params, _layers) in preview_jobs.items():
            entry = cache_entries.get(key)
            hit = preview_cache.decode_entry(entry, params[0]) if isinstance(entry, dict) else None
            if hit is not None:
                resolved[key] = hit
                cached[key] = (hit[0], entry, params)
            else:
                to_decode.append(key)
        if to_decode:
            with ThreadPoolExecutor(max_workers=preview_decode_workers()) as pool:
                futures = {pool.submit(preview_cache.compute_exact_preview, *preview_jobs[k][0]): k
                           for k in to_decode}
                for future in as_completed(futures):
                    try:
                        resolved[futures[future]] = future.result()
                    except Exception:
                        pass
        for key, (preview, scale) in resolved.items():
            for layer in preview_jobs[key][1]:
                layer.image_preview = preview
                layer.preview_scale = scale
        # Only committed (and upgraded) once the session is actually
        # installed - see _load_session_from_path_inner.
        self._incoming_cached_previews = cached

    def _collect_preview_cache(self) -> dict[str, dict]:
        """Cache entries for every layer that currently has a preview. A
        preview still showing its cached version is written back as-is
        (no lossy re-encode); anything else is encoded from the live
        preview."""
        entries: dict[str, dict] = {}
        for item in self.batch_items:
            candidates = [
                (layer, CHANNEL_NAMES[i] if layer.harris_shutter else "L", CHANNEL_NAMES[i])
                for i, layer in enumerate(item.layers)
            ]
            candidates.append((item.normal_layer, "RGB", "N"))
            for layer, decode, slot in candidates:
                if not layer.path or layer.image_preview is None:
                    continue
                key = preview_cache.layer_cache_key(
                    layer.path, decode, slot, layer.film_base, layer.quarter_turns)
                if key in entries:
                    continue
                cached = self._cached_previews.get(key)
                if cached is not None and cached[0] is layer.image_preview:
                    entries[key] = cached[1]
                    continue
                try:
                    entry = preview_cache.encode_entry(layer.image_preview, layer.preview_scale, layer.path)
                except Exception:
                    entry = None
                if entry is not None:
                    entries[key] = entry
        return entries

    # ------------------------------------------------------------------
    # Preview upgrade: cache-sourced previews -> exact recomputation
    # ------------------------------------------------------------------
    def _start_preview_upgrade(self) -> None:
        """Recomputes, in the background, every preview currently shown
        from the session's preview cache, from its original file - so the
        cache is only ever a stand-in for the first seconds after opening."""
        if self._preview_upgrade_thread is not None:
            # Restarted with the current _cached_previews once the running
            # one has stopped (see _on_preview_upgrade_thread_finished).
            self._preview_upgrade_restart = True
            if self._preview_upgrade_worker is not None:
                self._preview_upgrade_worker.cancel()
            return
        jobs = [(key, *params) for key, (_arr, _entry, params) in self._cached_previews.items()]
        if not jobs:
            return
        self._preview_upgrade_total = len(jobs)
        self._preview_upgrade_done = 0
        self._set_status_activity(
            "previews", i18n.tr("status_updating_previews", i=0, n=len(jobs)), interrupt_message=False)
        self._preview_upgrade_thread = QThread(self)
        self._preview_upgrade_worker = PreviewUpgradeWorker(jobs)
        self._preview_upgrade_worker.moveToThread(self._preview_upgrade_thread)
        self._preview_upgrade_thread.started.connect(self._preview_upgrade_worker.run)
        self._preview_upgrade_worker.preview_ready.connect(self._on_preview_upgraded)
        self._preview_upgrade_worker.finished.connect(self._preview_upgrade_thread.quit)
        # Same teardown rule as the export thread: no worker.deleteLater
        # (PySide race), the worker is released on the main thread.
        self._preview_upgrade_thread.finished.connect(self._preview_upgrade_thread.deleteLater)
        self._preview_upgrade_thread.finished.connect(self._on_preview_upgrade_thread_finished)
        self._preview_upgrade_thread.start()

    def _on_preview_upgraded(self, key: str, preview, scale: float) -> None:
        self._preview_upgrade_done += 1
        self._set_status_activity(
            "previews", i18n.tr("status_updating_previews",
                                i=self._preview_upgrade_done, n=self._preview_upgrade_total),
            interrupt_message=False)
        cached = self._cached_previews.pop(key, None)
        if cached is None:
            return
        old = cached[0]
        if old.shape == preview.shape and old.dtype == preview.dtype:
            # In place, so every holder of this array - layers sharing the
            # file, undo snapshots - gets the exact version at once.
            np.copyto(old, preview)
            new = old
        else:
            new = preview
        affected = set()
        for index, item in enumerate(self.batch_items):
            for layer in (*item.layers, item.normal_layer):
                if layer.image_preview is old:
                    layer.image_preview = new
                    layer.preview_scale = scale
                    affected.add(index)
        if affected:
            self._preview_upgrade_affected |= affected
            self._preview_upgrade_flush_timer.start()

    def _flush_preview_upgrades(self) -> None:
        affected, self._preview_upgrade_affected = self._preview_upgrade_affected, set()
        for index in affected:
            if index < len(self.batch_items):
                self._refresh_carousel_thumbnail_for_item(index)
        if self.batch_current_index in affected:
            self.recompute_preview()

    def _on_preview_upgrade_thread_finished(self) -> None:
        # Worker first, while the QThread wrapper is still alive.
        self._preview_upgrade_worker = None
        self._preview_upgrade_thread = None
        if self._preview_upgrade_restart:
            self._preview_upgrade_restart = False
            self._start_preview_upgrade()
        if self._preview_upgrade_thread is None:
            self._set_status_activity("previews", None)

    def _stop_preview_upgrade(self) -> None:
        """Called on quit: never let the QThread be destroyed while running."""
        self._preview_upgrade_restart = False
        if self._preview_upgrade_worker is not None:
            self._preview_upgrade_worker.cancel()
        if self._preview_upgrade_thread is not None:
            # quit() directly - see _confirm_cancel_running_export.
            self._preview_upgrade_thread.quit()
            self._preview_upgrade_thread.wait()

    def _set_session_file_path(self, path: str | None) -> None:
        """Sets the active session file and remembers it in QSettings as
        "the session to reopen on next launch" - see _restore_session."""
        self._session_file_path = path
        QSettings(ORG_NAME, APP_NAME).setValue("last_session_file_path", path or "")

    def save_session_to_path(self, path: str) -> None:
        self._set_status_activity("session", i18n.tr("status_saving_session"), flush=True)
        try:
            data = self._collect_session_data()
            # Kept apart from the settings: one separate top-level block,
            # written last (see preview_cache.py).
            # Settings > "Store previews in session files" off: none written.
            if setting_bool(ORG_NAME, APP_NAME, SESSION_PREVIEW_CACHE_KEY):
                data["preview_cache"] = preview_cache.build_cache_block(self._collect_preview_cache())
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        finally:
            self._set_status_activity("session", None)
        self._set_session_file_path(path)
        self._saved_edit_counter = self._edit_counter
        self._update_session_name_label()
        self._show_save_status()

    def _play_delete_sound(self) -> None:
        if sys.platform == "darwin" and setting_bool(ORG_NAME, APP_NAME, PLAY_SOUNDS_KEY):
            try:
                subprocess.Popen(
                    ["afplay", "/System/Library/Sounds/Pop.aiff"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    def _play_export_done_sound(self) -> None:
        # Hero.aiff, not Glass (saving) or Pop (deleting), so a finished
        # export is told apart by ear.
        if sys.platform == "darwin" and setting_bool(ORG_NAME, APP_NAME, PLAY_SOUNDS_KEY):
            try:
                subprocess.Popen(
                    ["afplay", "/System/Library/Sounds/Hero.aiff"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    def _show_save_status(self) -> None:
        if sys.platform == "darwin" and setting_bool(ORG_NAME, APP_NAME, PLAY_SOUNDS_KEY):
            try:
                subprocess.Popen(
                    ["afplay", "/System/Library/Sounds/Glass.aiff"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
        # No "Session Saved" text afterward - the bottom-left "Saving session…"
        # activity (kept up 1.5s minimum) plus this sound are the whole
        # feedback.

    def _update_session_name_label(self) -> None:
        if self._session_file_path:
            name = os.path.splitext(os.path.basename(self._session_file_path))[0]
        else:
            name = i18n.tr("session_untitled_label")
        # Trailing asterisk while there are unsaved changes - the same
        # _edit_counter/_saved_edit_counter check
        # _confirm_discard_unsaved_changes() uses, so undoing back to the
        # saved state clears it again.
        if self._edit_counter != self._saved_edit_counter:
            name += " *"
        self.session_name_label.setText(i18n.tr("session_open_prefix") + name)
        # Keeps status_bar_left_spacer exactly as wide as this label, so
        # the status bar's center container stays genuinely centered
        # regardless of how long the session name is - see that spacer's
        # own comment in _build_ui.
        self.status_bar_left_spacer.setFixedWidth(self.session_name_label.sizeHint().width())

    def load_session_from_path(self, path: str, show_warnings: bool = True) -> None:
        """``show_warnings=False`` is used by the silent, automatic restore
        at launch (_restore_session): an empty/unreadable remembered session
        should just fall back to the legacy restore, not pop a dialog on
        every startup.

        Always switches to Advanced mode first if Light mode is currently
        active. A real .trirgb is inherently a multi-photo, session-shaped
        thing - loading one straight into Light mode's single-photo UI
        would be a genuinely broken hybrid state. File > Open Session is
        itself hidden+disabled in Light mode, so the only way this can
        actually happen is the macOS FileOpen event (double-clicking a
        .trirgb in Finder, or dragging one onto the app/Dock icon, see
        main.py) while the app is already running in Light mode - switched
        silently, no confirmation, since opening a file is already the
        user's own explicit action. Saves the current Light-mode photo
        first, the same way _exit_light_mode does (_leave_light_mode is
        the shared helper both use), so it isn't lost."""
        if self.light_mode_active:
            self._leave_light_mode()
        self._set_status_activity("session", i18n.tr("status_loading_session"), flush=True)
        try:
            if self._load_session_from_path_inner(path, show_warnings):
                self.statusBar().showMessage(i18n.tr("status_session_loaded"), 3000)
        finally:
            self._set_status_activity("session", None)

    def _load_session_from_path_inner(self, path: str, show_warnings: bool) -> bool:
        """The actual load behind load_session_from_path (split out so the
        bottom-left "Loading session…" activity is always cleared, however
        this exits). Returns True once the session is actually installed."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        restored_items, sort_mode, sort_reversed, current_index = self._build_restored_items_from_data(data)
        if not restored_items:
            if not show_warnings:
                raise ValueError(f"session file has no restorable items: {path!r}")
            show_alert(self, i18n.tr("dialog_session_load_error_title"),
                                 i18n.tr("dialog_session_load_empty"))
            return False

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
        self._cached_previews = self._incoming_cached_previews
        self._incoming_cached_previews = {}
        self._start_preview_upgrade()
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
        return True

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

    def _save_session_state(self, key_prefix: str = "session") -> None:
        """Persist every batch item (photos + their alignment/color settings)
        as a fallback for ``_legacy_restore_session`` - used on next launch
        only when there's no remembered .trirgb to reopen (see
        ``_restore_session``).

        ``key_prefix`` lets Light mode's own single-photo autosave
        (``_save_light_mode_state``) reuse this same field-by-field writer
        under a separate QSettings key namespace instead of hand-copying a
        third field list. The default "session" keeps this method's
        pre-existing key names (see _session_state_key) exactly as they always
        were, so an existing user's saved session stays readable."""
        settings = QSettings(ORG_NAME, APP_NAME)

        def key(suffix: str) -> str:
            return _session_state_key(key_prefix, suffix)

        settings.remove(key("items"))
        settings.beginWriteArray(key("items"), len(self.batch_items))
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
                settings.setValue(prefix + "distortion", layer.distortion)
                settings.setValue(prefix + "perspective_v", layer.perspective_v)
                settings.setValue(prefix + "perspective_h", layer.perspective_h)
                settings.setValue(prefix + "anamorphic", layer.anamorphic)
                settings.setValue(
                    prefix + "stretch_pins",
                    json.dumps([list(p) for p in layer.stretch_pins]) if layer.stretch_pins else "")
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
            for name, value in cr.geometry_kwargs().items():
                settings.setValue(f"crop_{name}", value)
            settings.setValue("crop_perspective_guides", json.dumps(cr.guides_to_json()))
        settings.endArray()
        settings.setValue(key("current_index"), self.batch_current_index)
        settings.setValue(key("sort_mode"), self.sort_mode)
        settings.setValue(key("sort_reversed"), self.sort_reversed)
        settings.setValue(key("left_panel_visible"), self.left_panel_toggle_btn.isChecked())
        settings.setValue(key("right_panel_visible"), self.right_panel_toggle_btn.isChecked())
        settings.setValue(key("carousel_visible"), self.carousel_toggle_btn.isChecked())
        settings.setValue(key("block_side"), json.dumps(self.block_side))
        settings.setValue(key("block_visible"), json.dumps(self.block_visible))
        settings.setValue(key("block_collapsed"), json.dumps(self.block_collapsed))
        settings.setValue(key("left_block_order"), json.dumps(self.left_block_order))
        settings.setValue(key("right_block_order"), json.dumps(self.right_block_order))

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
        self._reset_to_blank_session()

    def _reset_to_blank_session(self) -> None:
        """The actual reset behind action_new_session, split out so a
        caller that has already handled its own confirmation/undo-stack
        concerns (_exit_light_mode's "Open Last Session" fallback) can
        reuse it directly without action_new_session's own
        _confirm_discard_unsaved_changes() call firing a second,
        redundant prompt on top of one already shown."""
        self._set_session_file_path(None)
        fresh_item = BatchItem(base="", paths={}, layers=new_project_layers(),
                                global_corr=GlobalCorrection(), selected=True)
        self._apply_restored_items([fresh_item], "import_order", False, 0)
        self._sync_sort_menu_state()
        self.recompute_preview()
        self.canvas.zoom_fit()
        # A fresh blank session has nothing worth losing relative to itself.
        self._saved_edit_counter = self._edit_counter
        self._update_session_name_label()

    # ------------------------------------------------------------------ Light
    # mode (single-photo, simplified UI). The Window menu's toggle action is
    # the one entry point for both directions.
    # ------------------------------------------------------------------
    def _toggle_light_mode(self) -> None:
        if self.light_mode_active:
            self._exit_light_mode()
        else:
            self._enter_light_mode()

    def _enter_light_mode(self) -> None:
        """Advanced -> Light: prompts to save only if there are unsaved
        changes (reusing the same check New Session/Open Session use, to
        protect the current Advanced session's own work), then restores
        Light mode's own remembered single photo - not a blank slate.
        Light mode has no session concept of its own (always exactly one
        photo): its state simply persists independently of whatever
        Advanced session you were last in, restored the same way at every
        entry (a fresh app launch into Light mode, or switching back from
        Advanced here) - see _restore_light_mode_state/
        _save_light_mode_state. _reset_to_blank_session() still runs first
        for its side effects (clearing _session_file_path, a clean undo
        boundary) even though _restore_light_mode_state immediately
        replaces its blank item - if nothing was ever saved in Light mode
        before (first use), that blank item is exactly the right
        fallback. Calls _reset_to_blank_session() directly, not
        action_new_session() - the confirm check just above already
        covers it, and action_new_session()'s own internal call to the
        same check would otherwise fire a second, redundant prompt.

        **A real, confirmed bug caught by testing this exact path**:
        _reset_to_blank_session() clears "last_session_file_path" in
        QSettings as an intentional side effect of its normal New-Session
        semantics (action_new_session() relies on exactly this elsewhere)
        - but here that value is what _exit_light_mode()'s "Open Last
        Session" choice needs to find the Advanced session that was open
        right before switching to Light mode. Without explicitly
        preserving it across the reset, "Open Last Session" would always
        find nothing, silently defeated by this reuse. Captured before
        the reset and restored into QSettings after (not into
        self._session_file_path itself - Light mode never tracks a
        session file path of its own, only this QSettings memory needs
        to survive)."""
        if not self._confirm_discard_unsaved_changes():
            return
        settings = QSettings(ORG_NAME, APP_NAME)
        last_session_path = settings.value("last_session_file_path", "", type=str)
        self._reset_to_blank_session()
        if last_session_path:
            settings.setValue("last_session_file_path", last_session_path)
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._restore_light_mode_state()
        self.light_mode_active = True
        QSettings(ORG_NAME, APP_NAME).setValue("light_mode_active", True)
        self._apply_light_mode_ui_state()
        self.recompute_preview()
        self.canvas.zoom_fit()

    def _leave_light_mode(self) -> None:
        """The shared "step out of Light mode" tail, used by every path
        that leaves it (both _exit_light_mode branches below, and
        load_session_from_path's own guard for the external-.trirgb
        case): saves the current Light-mode photo (_save_light_mode_state,
        so the next Light-mode entry - here or a future relaunch -
        restores it), flips the persisted mode flag, clears the undo
        stack (Light mode's own edit history has no meaning once the
        photo either becomes a new Advanced session, is left behind for a
        different one, or a real session file gets loaded on top), and
        re-applies the UI. Deliberately does not touch batch_items itself
        - the caller installs whatever Advanced-mode content comes next."""
        self._save_light_mode_state()
        self.light_mode_active = False
        QSettings(ORG_NAME, APP_NAME).setValue("light_mode_active", False)
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._apply_light_mode_ui_state()

    def _exit_light_mode(self) -> None:
        """Light -> Advanced: asks what to land on via a 3-way ConfirmDialog -
        "New Session with This Photo" (the original behavior: the current photo
        carries forward as a new session's first item), "Open Last Session"
        (reopens whatever .trirgb was last open - the exact same
        last_session_file_path QSettings value _restore_session() reads at
        launch - falling back to a blank session if there is none or it fails
        to load), or Cancel (stays in Light mode, nothing happens). Either way
        the Light-mode photo itself is never lost - _leave_light_mode() saves
        it up front, before either choice is acted on, so it's still there the
        next time Light mode is entered."""
        dialog = ConfirmDialog(
            self, i18n.tr("light_mode_exit_confirm_title"), i18n.tr("light_mode_exit_confirm_text"),
            confirm_label=i18n.tr("light_mode_exit_new_session_button"),
            cancel_label=i18n.tr("dialog_quit_cancel_button"),
            alternate_label=i18n.tr("light_mode_exit_open_last_button"))
        dialog.exec()
        if dialog.result == "cancel":
            return

        if dialog.result == "alternate":
            last_path = QSettings(ORG_NAME, APP_NAME).value("last_session_file_path", "", type=str)
            if last_path and os.path.isfile(last_path):
                try:
                    # load_session_from_path() itself detects
                    # light_mode_active and calls _leave_light_mode() as
                    # part of loading - nothing left to do here.
                    self.load_session_from_path(last_path, show_warnings=False)
                    return
                except Exception:
                    pass  # corrupted/unreadable - fall through to blank
            self._leave_light_mode()
            self._reset_to_blank_session()
            return

        # "confirm" - carry the current photo forward as a new session's
        # first item.
        current_item = self.batch_items[self.batch_current_index]
        self._leave_light_mode()
        self._set_session_file_path(None)
        self._apply_restored_items([current_item], "import_order", False, 0)
        self._sync_sort_menu_state()
        self.recompute_preview()
        self.canvas.zoom_fit()
        # The carried-over photo's own edits are all this session has -
        # nothing new to consider unsaved relative to them yet.
        self._saved_edit_counter = self._edit_counter
        self._update_session_name_label()

    def _apply_light_mode_ui_state(self) -> None:
        """The single place light_mode_active turns into actual UI state -
        called once at startup (after _build_ui/_connect_signals, before
        either restore path runs) and from both transition methods above.
        Deliberately never touches block_side/block_visible/
        left_block_order/right_block_order (see _apply_light_mode_block_layout)
        so Advanced mode's own arrangement is never disturbed."""
        active = self.light_mode_active

        self.top_toolbar.setVisible(not active)
        self.statusBar().setVisible(not active)

        # Preview bar: sort/grid-view/thumbnails-toggle hidden, everything
        # else (zoom, rotate, compare, fullscreen, HQ Preview) stays.
        self.sort_btn.setVisible(not active)
        self.grid_view_toggle_btn.setVisible(not active)
        self.carousel_toggle_btn.setVisible(not active)
        if active:
            self.grid_view_toggle_btn.setChecked(False)
            self.carousel.setVisible(False)

        # File menu: keep Load R/G/B + Export, hide+disable session/import
        # actions (disable, not just hide - several of these carry a real
        # QAction shortcut, e.g. Ctrl+N/O/S/Shift+S/I, which stays live
        # through a hidden menu unless explicitly disabled too).
        for act in (self.new_session_action, self.open_session_action,
                    self.save_session_action, self.save_session_as_action, self.batch_action):
            act.setVisible(not active)
            act.setEnabled(not active)
        # Edit menu: keep Undo/Redo + Rotate, hide+disable Copy/Paste/Delete.
        self.copy_action.setVisible(not active)
        self.copy_action.setEnabled(not active)
        self.paste_action.setVisible(not active)
        self.paste_action.setEnabled(not active and self._clipboard_settings is not None)
        self.delete_selection_action.setVisible(not active)
        self.delete_selection_action.setEnabled(not active)
        # Tools menu hidden entirely; Window keeps only the Light mode
        # toggle and Close Window (every layout item is meaningless in
        # Light mode's fixed layout - hidden *and* disabled, so a hidden
        # item's shortcut can't fire either); View stays in both modes,
        # but its Thumbnails/Grid View items are Advanced-only (Light mode
        # has no filmstrip/grid at all).
        self.tools_menu.menuAction().setVisible(not active)
        for act in self.window_menu_advanced_actions:
            act.setVisible(not active)
            act.setEnabled(not active)
        # Thumbnails has its own enabled gating (2+ photos, no grid view -
        # _update_carousel_visibility), shared with its View-menu twin.
        if not active:
            self.window_thumbnails_action.setEnabled(self.view_thumbnails_action.isEnabled())
        self.view_thumbnails_action.setVisible(not active)
        self.view_grid_action.setVisible(not active)

        # Files/Trichrome Process/Crop can be collapsed but never closed -
        # only their close button is disabled, collapse stays available.
        for key in _LIGHT_MODE_BLOCK_KEYS:
            self.block_close_buttons[key].setEnabled(not active)

        self.import_panel.set_light_mode_active(active)

        self.light_mode_toggle_action.setText(
            i18n.tr("menu_switch_to_advanced_mode") if active else i18n.tr("menu_switch_to_light_mode"))
        self._apply_scan_tool_ui_state()

        self._apply_block_layout()
        self.right_scroll.setVisible(not active and self.right_panel_toggle_btn.isChecked())

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

        # Arrow-key alignment nudge (see keyPressEvent's own comment) has to
        # be caught here, at the application-wide event-filter level, not
        # merely in keyPressEvent - too many different widgets can hold
        # keyboard focus while a channel is Active and would otherwise
        # consume the key themselves before it ever reaches this window's
        # own keyPressEvent (a real, confirmed bug: QScrollArea-based
        # widgets - the side panels, the filmstrip, and the canvas itself,
        # which is a QScrollArea too - scroll their own viewport on Up/Down,
        # and any focused SliderSpin steps its own value). Intercepting at
        # the event-filter stage runs before Qt ever delivers the event to
        # whichever widget currently has focus, so it wins regardless of
        # where that focus happens to be - no per-widget forwarding logic
        # can cover every case. Gated on this window being the actually
        # active one so it doesn't hijack arrow keys typed into the Batch
        # Import window, Export dialog, or any other secondary window.
        if (event.type() == QEvent.Type.KeyPress
                and self.active_index is not None
                and QApplication.activeWindow() is self
                and event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down)):
            focus = QApplication.focusWidget()
            if not isinstance(focus, (QAbstractSpinBox, QLineEdit)):
                step = _ALIGN_NUDGE_STEP_SHIFT if event.modifiers() & Qt.ShiftModifier else _ALIGN_NUDGE_STEP
                dx = -step if event.key() == Qt.Key_Left else step if event.key() == Qt.Key_Right else 0.0
                dy = -step if event.key() == Qt.Key_Up else step if event.key() == Qt.Key_Down else 0.0
                self.on_canvas_drag(dx, dy)
                return True

        return super().eventFilter(obj, event)

    def closeEvent(self, event) -> None:
        # Restore the user's own layout first, so the layout saved below
        # is never the Quick Tour's temporary one.
        finish_quick_tour(self)
        if not self._confirm_discard_unsaved_changes():
            event.ignore()
            return
        if not self._confirm_cancel_running_export():
            event.ignore()
            return
        QApplication.instance().removeEventFilter(self)
        if self.light_mode_active:
            self._save_light_mode_state()
        else:
            self._save_session_state()
        if self.batch_window is not None:
            self.batch_window.close()
        # ScanPanel is an embedded block now, not its own top-level window,
        # so it never gets its own closeEvent() - stop its poll timer, close
        # the backlight window if open, and wait for any in-flight process
        # thread explicitly here instead.
        self.scan_panel.shutdown()
        self._stop_preview_upgrade()
        self._stop_startup_update_check()
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

    def on_display_layer_toggled(self, index: int, checked: bool) -> None:
        # View-only - no push_undo, no persistence (see _visible_channels's own
        # comment at __init__). At least one channel must always stay visible -
        # unchecking the last one just re-checks its own button instead, rather
        # than letting the preview go fully black.
        if not checked and self._visible_channels == {index}:
            self.display_layer_buttons[index].blockSignals(True)
            self.display_layer_buttons[index].setChecked(True)
            self.display_layer_buttons[index].blockSignals(False)
            return
        if checked:
            self._visible_channels.add(index)
        else:
            self._visible_channels.discard(index)
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
            # Mutually exclusive with Stretch on Canvas - a canvas drag can
            # only do one or the other at a time.
            if self.stretch_index is not None:
                self.stretch_index = None
                for panel in self.channel_panels:
                    panel.stretch_checkbox.blockSignals(True)
                    panel.stretch_checkbox.setChecked(False)
                    panel.stretch_checkbox.blockSignals(False)
        elif self.active_index == index:
            self.active_index = None
        self._sync_canvas_drag_mode()
        self._update_canvas_drag_indicator()

    def on_stretch_toggled(self, index: int, checked: bool) -> None:
        """Stretch on Canvas - the Distortion section's own peer of
        on_active_toggled, same mutual-exclusivity/cross-tab-follow shape,
        mirrored onto self.stretch_index instead of active_index."""
        if checked:
            self.stretch_index = index
            for i, panel in enumerate(self.channel_panels):
                if i != index:
                    panel.stretch_checkbox.blockSignals(True)
                    panel.stretch_checkbox.setChecked(False)
                    panel.stretch_checkbox.blockSignals(False)
            if self.active_index is not None:
                self.active_index = None
                for panel in self.channel_panels:
                    panel.active_checkbox.blockSignals(True)
                    panel.active_checkbox.setChecked(False)
                    panel.active_checkbox.blockSignals(False)
        elif self.stretch_index == index:
            self.stretch_index = None
        self._sync_canvas_drag_mode()
        self._update_canvas_drag_indicator()

    def _sync_canvas_drag_mode(self) -> None:
        """Single source of truth for which canvas-drag mode (if any) is
        armed, and what the Stretch grid overlay shows - called whenever
        active_index/stretch_index, or the Stretch-active channel's own
        pins, change."""
        if self.active_index is not None or self.stretch_index is not None:
            # Engaging Move/Stretch on Canvas cancels guided Perspective
            # mode - same mutual exclusion it applies the other way round.
            self._set_perspective_active(False)
        self.canvas.set_align_enabled(self.active_index is not None)
        self.canvas.set_stretch_enabled(self.stretch_index is not None)
        if self.stretch_index is not None and 0 <= self.stretch_index < len(self.layers):
            self.canvas.set_stretch_pins(self.layers[self.stretch_index].stretch_pins)
        else:
            self.canvas.set_stretch_pins([])

    def _deactivate_canvas_drag_modes(self) -> None:
        """Turns off Move on Canvas / Stretch on Canvas, if either is active -
        same "a layout change/Escape/Enter always turns this off" convention
        Crop's own _set_crop_active already follows. Reachable from
        keyPressEvent (Escape/Enter, alongside Crop's own handlers) and
        _apply_restored_layout/reset_layout (alongside their own
        _set_crop_active(False) calls). Unchecking routes through the normal
        active_toggled/stretch_toggled signal, which already handles clearing
        the index/updating the canvas and indicator."""
        if self.active_index is not None:
            self.channel_panels[self.active_index].active_checkbox.setChecked(False)
        if self.stretch_index is not None:
            self.channel_panels[self.stretch_index].stretch_checkbox.setChecked(False)

    def _update_canvas_drag_indicator(self) -> None:
        """Shows/hides canvas_drag_indicator (the yellow banner next to
        compare_indicator) to match whichever canvas-drag mode - Move on
        Canvas or Stretch on Canvas, mutually exclusive, see
        on_active_toggled/on_stretch_toggled - is currently active, if any.
        Same "mode is active, here's what it does" convention as Compare's
        own indicator. Called from on_active_toggled/on_stretch_toggled,
        retranslate_ui (language switch while it's showing), and anywhere
        else active_index/stretch_index are forced back to None (switching
        photos, undo/redo). Also carries guided Perspective mode's own
        message (mutually exclusive with both, see _set_perspective_active)."""
        if self._perspective_active:
            self.canvas_drag_indicator.setText(i18n.tr("perspective_indicator_label"))
            self.canvas_drag_indicator.setVisible(True)
        elif self.active_index is not None:
            self.canvas_drag_indicator.setText(i18n.tr(
                "move_on_canvas_indicator_label", channel=i18n.channel_name(self.active_index)))
            self.canvas_drag_indicator.setVisible(True)
        elif self.stretch_index is not None:
            self.canvas_drag_indicator.setText(i18n.tr(
                "stretch_on_canvas_indicator_label", channel=i18n.channel_name(self.stretch_index)))
            self.canvas_drag_indicator.setVisible(True)
        else:
            self.canvas_drag_indicator.setVisible(False)
        self._update_status_bar_indicator_separator()

    def _update_status_bar_indicator_separator(self) -> None:
        """Shows status_bar_indicator_separator only while both
        compare_indicator and canvas_drag_indicator are showing at once - see
        status_bar_center_container's own comment in _build_ui. Reads the flags
        directly (_compare_active, active_index/stretch_index) rather than the
        widgets' own isVisible(), since that would be unreliable before the
        window's first show() (it needs the whole ancestor chain shown)."""
        both = self._compare_active and (
            self.active_index is not None or self.stretch_index is not None or self._perspective_active)
        self.status_bar_indicator_separator.setVisible(both)

    def _sync_channel_section_toggle(self, section_attr: str, source_index: int, checked: bool) -> None:
        """Keeps one ChannelPanel section (tone_box/position_box/
        distortion_box) expanded/collapsed in lockstep across all 3 R/G/B
        tabs - see the comment in _connect_signals where this is wired."""
        for i, panel in enumerate(self.channel_panels):
            if i == source_index:
                continue
            box = getattr(panel, section_attr)
            if box.isChecked() != checked:
                box.setChecked(checked)

    def on_channel_tab_changed(self, index: int) -> None:
        """Move on Canvas / Stretch on Canvas (ChannelPanel's per-channel
        Active/Stretch checkboxes) follow whichever R/G/B tab is currently
        shown, once engaged - switching tabs while one is on re-targets it at
        the new tab instead of leaving it pointed at whichever channel you just
        tabbed away from (for both features). Checking the new tab's own
        checkbox routes through the normal active_toggled/stretch_toggled
        signal, which already handles unchecking the old one and updating
        active_index/ stretch_index/the indicator/the grid overlay."""
        if self.active_index is not None and self.active_index != index:
            self.channel_panels[index].active_checkbox.setChecked(True)
        elif self.stretch_index is not None and self.stretch_index != index:
            self.channel_panels[index].stretch_checkbox.setChecked(True)

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

        Originally implemented by forcing GlobalCorrection.saturation to 0.0 -
        replaced with a real grayscale conversion (imaging.apply_black_white,
        applied as the pipeline's very last step in
        recompute_preview/compose_trichrome/compose_normal), because this app's
        saturation slider works in HSV space, so saturation=0 only grays a
        pixel to HSV's V (max(R,G,B)), not a true perceptually-weighted
        luminance - a saturated red and a saturated blue at the same V would
        read as identical grays, which a real B&W conversion (and the human
        eye) wouldn't. `saturation` itself is now left completely untouched by
        this toggle; only `GlobalCorrection.black_white_active` changes.

        The old "Solo N&B" mechanism this once coexisted with (Files'
        bw_film_button/color_film_button forcing saturation via
        on_harris_shutter_toggled, and ColorPanel.set_disabled_message's
        full-block disable) was retired entirely: this toggle is the *only* way
        to make a photo read as B&W, in any mode. This method and its field
        (GlobalCorrection.black_white_active) are now the sole mechanism, with
        nothing left to coexist with."""
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
        panel.distortion.set_value(layer.distortion)
        panel.perspective_v.set_value(layer.perspective_v)
        panel.perspective_h.set_value(layer.perspective_h)
        panel.anamorphic.set_value(layer.anamorphic)
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

    def on_distortion_changed(self, index: int) -> None:
        self._push_undo_coalesced(f"distortion_{self.batch_current_index}_{index}")
        layer = self.layers[index]
        panel = self.channel_panels[index]
        layer.distortion = panel.distortion.value()
        layer.perspective_v = panel.perspective_v.value()
        layer.perspective_h = panel.perspective_h.value()
        layer.anamorphic = panel.anamorphic.value()
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

    def on_reset_distortion(self, index: int) -> None:
        self.push_undo()
        self.layers[index].reset_distortion()
        self._sync_panel_from_layer(index)
        if index == self.stretch_index:
            # reset_distortion() also clears stretch_pins - re-sync the
            # live grid overlay (canvas.set_stretch_pins) if this is the
            # Stretch-active channel, or it would keep showing the just-
            # cleared deformation until the next drag.
            self.canvas.set_stretch_pins(self.layers[index].stretch_pins)
        self.recompute_preview()

    def on_reset_stretch(self, index: int) -> None:
        """Clears only stretch_pins, not the 4 Distortion sliders - the
        separate Reset button next to Stretch on Canvas itself, distinct from
        reset_distortion_button's own "everything in this section" Reset."""
        if not self.layers[index].stretch_pins:
            return
        self.push_undo()
        self.layers[index].stretch_pins = []
        if index == self.stretch_index:
            self.canvas.set_stretch_pins([])
        self.recompute_preview()

    def on_reset_tone(self, index: int) -> None:
        self.push_undo()
        self.layers[index].reset_tone()
        self._sync_panel_from_layer(index)
        self.recompute_preview()

    def on_reset_all_alignment(self) -> None:
        # Resets Distortion too, not just Position - this is the block
        # header's own "reset everything alignment-related, every channel"
        # button, distinct from each channel's own separate Position/
        # Distortion Reset buttons which stay independent of each other.
        self.push_undo()
        for i, layer in enumerate(self.layers):
            layer.reset_alignment()
            layer.reset_distortion()
            self._sync_panel_from_layer(i)
        if self.stretch_index is not None:
            self.canvas.set_stretch_pins(self.layers[self.stretch_index].stretch_pins)
        self.recompute_preview()

    def on_reset_all_color(self) -> None:
        self.push_undo()
        for i, layer in enumerate(self.layers):
            layer.reset_tone()
            self._sync_panel_from_layer(i)
        self.recompute_preview()

    def on_light_mode_reset_channels(self) -> None:
        """Light mode's own Reset button (next to the Mode combo) - a full
        reset of all 3 channels (image + alignment + tone + rotation +
        invert), replacing each with a fresh ChannelLayer rather than
        mutating fields in place (the "replace, don't mutate" discipline
        this codebase already follows elsewhere, e.g.
        _assign_normal_photo_to_channel - a genuinely fresh start, not an
        edit-preserving move). Preserves harris_shutter and is_reference:
        harris_shutter is "which Mode" (Classic/Color Trichrome), not an
        edit to clear, and is_reference is the Lock Layer Position anchor
        choice, which - like color_index/label - is pinned to the slot,
        not the photo's content."""
        self.push_undo()
        harris_shutter = self.layers[0].harris_shutter if self.layers else False
        for i, layer in enumerate(self.layers):
            self.layers[i] = ChannelLayer(
                color_index=layer.color_index, label=layer.label,
                is_reference=layer.is_reference, harris_shutter=harris_shutter)
            self.import_panel.set_filename(i, "")
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
        entirely.** This used to also drive a "Solo N&B" cosmetic mechanism
        (forcing GlobalCorrection.saturation to 0 via Files' now-removed
        bw_film_button/color_film_button) - retired: the Mode combo is now the
        only indicator of whether Trichrome photos should be processed as B&W
        or Color (Harris Shutter Effect); Solo's own cosmetic B&W concept lives
        entirely in ColorPanel.black_white_button/
        MainWindow.on_black_white_toggled now, fully independent of this
        method. Reloads each channel that has a real loaded image from disk
        under the new interpretation (luminance vs. its own R/G/B channel - see
        imaging.load_grayscale). Future loads (single manual load or batch
        import) pick up the new Trichrome mode automatically since they all
        read ImportPanel.is_harris_shutter_active() at load time."""
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
            geo_params = [(l.dx, l.dy, l.scale, l.rotation, l.distortion, l.perspective_v, l.perspective_h,
                           l.anamorphic, l.stretch_pins) for l in self.layers]
            tone_params = [(l.black_point, l.white_point, l.gamma, l.exposure, l.brightness, l.contrast,
                            l.shadows, l.highlights, l.invert) for l in self.layers]
            pre_wb = imaging.compose_pre_white_balance_rgb(
                images, geo_params, tone_params, ref.color_index, global_params)
        # (u, v) are normalized against what's actually on screen - the
        # straightened/mirrored/cropped frame, same as recompute_preview.
        pre_wb = self._apply_frame_transform(pre_wb)
        if not self._showing_full_frame():
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
        film-base reference from (either mode, not just Trichrome), else
        None."""
        if not (0 <= self.batch_current_index < len(self.batch_items)):
            return None
        item = self.batch_items[self.batch_current_index]
        if item.mode == "trichrome" and all(l.has_image() for l in item.layers):
            return item
        if item.mode == "normal" and item.normal_layer.has_image():
            return item
        return None

    def on_pick_film_base_from_photo_toggled(self, checked: bool) -> None:
        """The Scan tool's eyedropper alternative to a dedicated 3-shot Sample
        Film Base capture - validated *here*, at arm time, rather than only on
        click, so an invalid active photo gives immediate feedback instead of
        arming a tool that can only fail later. Works on a Trichrome photo (all
        3 channels loaded) or a Normal-mode one (its own composited image)."""
        if checked and self._active_item_valid_for_film_base_pick() is None:
            self.scan_panel.set_pick_from_photo_active(False)
            show_alert(self, i18n.tr("scan_error_title"), i18n.tr("scan_pick_film_base_requires_photo"))
            return
        self.canvas.set_film_base_pick_enabled(checked)

    def on_film_base_pick_requested(self, u: float, v: float) -> None:
        """Samples the Scan tool's film-base reference from a point on the
        *active* photo, instead of a dedicated calibration capture - see
        ScanPanel.set_film_base_from_pick and the scan_panel.py module
        docstring for why this reference (and not a post-invert white-balance
        pick) is what actually corrects color negative's orange mask.
        Single-shot, like the white balance/histogram eyedroppers - disarms
        itself immediately.

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
            img = self._apply_frame_transform(item.normal_layer.image_preview)
            if not self._showing_full_frame():
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
                warped = self._apply_frame_transform(warped)
                if not self._showing_full_frame():
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
        overlay on the canvas, Enter-to-apply, and the full-vs-cropped preview
        frame) is armed or disarmed - self._crop_active is the one source of
        truth. Decoupled from the Crop block's own visibility: the block can be
        shown in any custom layout alongside anything else, so tying active
        mode to block-visible alone made the crop overlay pop on/off
        unexpectedly as blocks were dragged around or layouts switched.
        Reachable from: the Crop block's own activate button
        (crop_panel.activate_toggled), Escape (off only - never touches
        layout/visibility), on_crop_apply (off, after committing),
        _activate_default_layout (on only when loading the "Crop" slot, off for
        every other layout), reset_layout, and _apply_restored_layout (both
        always turn it off - loading any layout counts as "changing layout"),
        and set_block_visible (off, if the Crop block itself gets hidden while
        active).

        Activating also force-shows the Crop block via set_block_visible
        (there's no point arming an invisible tool) - but deactivating never
        touches visibility, since that would be a layout change, which
        Escape/apply deliberately are not. Skipped entirely in Light mode: Crop
        is one of its 4 permanently-visible blocks already, and
        set_block_visible writes into block_visible - the same dict Light
        mode's render-override deliberately never touches - so calling it here
        would leak a stray block_visible["crop"] = True into Advanced mode's
        own layout the next time the user switches back."""
        if active:
            # Crop and guided Perspective are mutually exclusive canvas
            # modes (both own the canvas's left-drag and Enter/Escape).
            self._set_perspective_active(False)
        if active and not self.light_mode_active:
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

    def _showing_full_frame(self) -> bool:
        """True while the preview must show the whole frame rather than the
        applied crop rect - active crop mode (the rect is what's being
        edited) and guided Perspective mode (see _apply_frame_transform)."""
        return self._crop_active or self._perspective_active

    def _apply_frame_transform(self, img: np.ndarray) -> np.ndarray:
        """The Framing tool's Geometry + straighten + mirror, applied to
        every preview-side image (the composed frame, its coverage mask,
        the pre-curve/pre-WB intermediates, the eyedropper sources) - the
        one place that decides it, so they can't disagree. While guided
        Perspective mode is active, uses _perspective_frame_params() (the
        live-solved proposal, not yet committed to self.crop) instead."""
        p = self._perspective_frame_params()
        return imaging.apply_straighten_mirror(
            img, p["rotation"], p["mirror_h"], p["mirror_v"], **p["geometry"])

    def _perspective_frame_params(self) -> dict:
        """The straighten/mirror/Geometry parameters the preview uses:
        self.crop's own, overridden while guided Perspective mode has a
        live proposal (_perspective_proposal - solved from 2 coherent
        guides, see on_perspective_guides_changed) by that proposal's
        Vertical/Horizontal coefficient and Straighten angle."""
        geometry = self.crop.geometry_kwargs()
        rotation = self.crop.rotation
        proposal = self._perspective_proposal if self._perspective_active else None
        if proposal is not None:
            for key in ("perspective_v", "perspective_h"):
                if key in proposal:
                    geometry[key] = proposal[key]
            rotation = proposal["rotation"]
        return {"rotation": rotation, "mirror_h": self.crop.mirror_h, "mirror_v": self.crop.mirror_v,
                "geometry": geometry}

    def _update_guide_mapping(self) -> None:
        """Hands the canvas the frame<->display point mapping matching what
        the preview currently shows (_perspective_frame_params), so guides
        - stored in uncorrected-frame coordinates, which is what the solver
        needs - stay drawn on the same image features as the preview
        re-corrects under them."""
        ref = self._reference_layer()
        if not ref.has_image():
            return
        h, w = ref.image_preview.shape[:2]
        p = self._perspective_frame_params()
        args = (w, h, p["rotation"], p["mirror_h"], p["mirror_v"])
        geometry = p["geometry"]
        self.canvas.set_guide_mapping(
            lambda u, v: imaging.frame_point_to_display(u, v, *args, **geometry),
            lambda u, v: imaging.display_point_to_frame(u, v, *args, **geometry))

    def on_perspective_guides_changed(self) -> None:
        """A guide was added/moved/removed/deleted (canvas emits this on
        mouse release/double-click only): re-solves and previews the
        correction live as soon as there's a vertical or a horizontal pair
        (up to both) - nothing is committed to self.crop (or the undo
        stack) until Enter."""
        self._perspective_edited = True
        guides = self.canvas.perspective_guides()
        proposal = None
        ref = self._reference_layer()
        if guides and ref.has_image():
            h, w = ref.image_preview.shape[:2]
            proposal = imaging.solve_guided_perspective(guides, w, h, **self.crop.geometry_kwargs())
        if proposal == self._perspective_proposal:
            return
        self._perspective_proposal = proposal
        self._update_guide_mapping()
        self._sync_crop_panel_with_proposal()
        self.recompute_preview()

    def _sync_crop_panel_with_proposal(self) -> None:
        """Shows the live proposal in the Vertical/Horizontal/Straighten
        sliders as soon as it's solved, not only once Enter commits it -
        display only (set_from_crop never emits), self.crop itself stays
        untouched until Enter; back to self.crop's own values when there's no
        proposal (or the mode is left)."""
        crop = copy.copy(self.crop)
        proposal = self._perspective_proposal if self._perspective_active else None
        if proposal is not None:
            for key in ("perspective_v", "perspective_h"):
                if key in proposal:
                    setattr(crop, key, proposal[key])
            crop.rotation = proposal["rotation"]
        self.crop_panel.set_from_crop(crop)

    def _absorb_perspective_proposal(self) -> None:
        """A Crop/Geometry slider was touched while a live proposal is
        showing in the sliders: commit the proposal into self.crop first
        (the caller already pushed its undo step), so the caller's own
        panel read-back - which only covers its own section's sliders -
        can't leave half the proposal behind. The guides stay on screen;
        Enter then just stores them (see on_perspective_apply)."""
        proposal = self._perspective_proposal if self._perspective_active else None
        if proposal is None:
            return
        for key in ("perspective_v", "perspective_h"):
            if key in proposal:
                setattr(self.crop, key, proposal[key])
        self.crop.rotation = proposal["rotation"]
        self._perspective_proposal = None
        self._update_guide_mapping()

    def _set_perspective_active(self, active: bool) -> None:
        """The single place guided Perspective mode (Framing tool's
        Geometry section, its perspective_button) is armed or disarmed -
        self._perspective_active is the one source of truth, same shape as
        _set_crop_active. While active: the preview shows the uncropped
        frame (_showing_full_frame), the canvas lets the user draw/edit 2
        guide lines, and as soon as 2 coherent guides exist the solved
        correction is previewed live (on_perspective_guides_changed/
        _perspective_frame_params); Enter commits it into the sliders
        (on_perspective_apply), Escape cancels. Turned off
        (cancelled, guides discarded) by: Escape, the button itself, active
        crop mode turning on, any layout change (_activate_default_layout/
        reset_layout/_apply_restored_layout), hiding the Framing block, and
        switching photo or undo/redo (the guides belong to the image they
        were drawn on). A no-op when the state doesn't change, so every
        one of those call sites can call it unconditionally."""
        if active == self._perspective_active:
            return
        if active:
            self._set_crop_active(False)
            if not self.light_mode_active:
                self.set_block_visible("crop", True)
            self.crop_panel.geometry_section.setChecked(True)
            # Same mutual exclusion as crop mode: every other click/drag
            # canvas mode is disarmed.
            self.color_panel.set_pick_white_balance_active(False)
            self.canvas.set_wb_pick_enabled(False)
            self.scan_panel.set_pick_from_photo_active(False)
            self.canvas.set_film_base_pick_enabled(False)
            self._deactivate_canvas_drag_modes()
        self._perspective_active = active
        self._perspective_proposal = None
        self.crop_panel.set_perspective_active(active)
        self.canvas.set_perspective_enabled(active)
        if not active:
            # Drop any proposal still shown in the sliders (Escape/cancel).
            self._sync_crop_panel_with_proposal()
        if active:
            # Previously-applied guides come back for correction - not
            # re-solved until one is actually edited (_perspective_edited),
            # so sliders hand-tuned since then aren't silently overwritten.
            self._perspective_edited = False
            self.canvas.set_perspective_guides(self.crop.perspective_guides)
            self._update_guide_mapping()
        self._update_canvas_drag_indicator()
        self.recompute_preview()

    def _guides_form_a_pair(self, guides) -> bool:
        ref = self._reference_layer()
        if not ref.has_image():
            return False
        h, w = ref.image_preview.shape[:2]
        return imaging.solve_guided_perspective(guides, w, h, **self.crop.geometry_kwargs()) is not None

    def on_perspective_apply(self) -> None:
        """Enter while guided Perspective mode is active: commits the live
        proposal (already solved on the last guide edit, see
        on_perspective_guides_changed) into the Geometry section's
        Vertical/Horizontal slider(s) and the Crop section's Straighten
        slider - so it stays fine-tunable by hand afterward - and stores
        the guides on CropSettings.perspective_guides so re-entering the
        mode shows them again. Then leaves the mode. With no edit since
        the mode was entered, just leaves (nothing to apply - and the
        sliders may have been hand-tuned since the guides were last
        solved, which must not be overwritten). With every guide deleted,
        stores that (no guides) without touching the sliders. Otherwise -
        guides that form no vertical or horizontal pair - stays in the
        mode with a status message."""
        guides = tuple(self.canvas.perspective_guides())
        result = self._perspective_proposal
        if result is not None:
            self.push_undo()
            for key in ("perspective_v", "perspective_h"):
                if key in result:
                    setattr(self.crop, key, result[key])
            self.crop.rotation = result["rotation"]
            self.crop.perspective_guides = guides
            self.crop_panel.set_from_crop(self.crop)
            self.statusBar().showMessage(i18n.tr("status_perspective_applied"), 4000)
        elif not self._perspective_edited:
            pass
        elif not guides:
            self.push_undo()
            self.crop.perspective_guides = ()
        elif self._guides_form_a_pair(guides):
            # Edited guides whose proposal was already absorbed by a
            # slider touch (_absorb_perspective_proposal) - the values are
            # in self.crop already, only the guides are left to store.
            self.push_undo()
            self.crop.perspective_guides = guides
        else:
            self.statusBar().showMessage(i18n.tr("status_perspective_need_two_guides"), 4000)
            return
        self._set_perspective_active(False)

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

    def on_crop_settings_changed(self, reshape_rect: bool = True) -> None:
        """Straighten/mirror/aspect-ratio/grid - these apply live, unlike
        the crop rect itself which only takes effect on Enter (see
        on_crop_apply). reshape_rect=False skips the top-left-anchored
        overlay reshape below, for a caller that has already placed the
        rect itself (on_crop_orientation_invert)."""
        self._push_undo_coalesced(f"crop_{self.batch_current_index}")
        self._absorb_perspective_proposal()
        panel = self.crop_panel
        self.crop.rotation = panel.straighten_value()
        self.crop.mirror_h = panel.is_mirrored_h()
        self.crop.mirror_v = panel.is_mirrored_v()
        self.crop.aspect_ratio = panel.aspect_ratio()
        self.crop.custom_ratio_w, self.crop.custom_ratio_h = panel.custom_ratio()
        ratio = self._current_crop_ratio_value()
        self.canvas.set_crop_ratio(ratio)
        self.canvas.set_crop_grid(panel.grid_mode())
        if ratio and reshape_rect:
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

    def on_crop_geometry_changed(self) -> None:
        """The Crop block's Geometry section - whole-image lens correction,
        applied live like straighten/mirror (see CropSettings.distortion)."""
        self._push_undo_coalesced(f"crop_geometry_{self.batch_current_index}")
        self._absorb_perspective_proposal()
        for name, value in self.crop_panel.geometry_values().items():
            setattr(self.crop, name, value)
        self.recompute_preview()

    def on_crop_geometry_reset(self) -> None:
        # Also clears the stored guides (reset_geometry) - leave the mode
        # first so the canvas doesn't keep showing them.
        self._set_perspective_active(False)
        self.push_undo()
        self.crop.reset_geometry()
        self.crop_panel.set_from_crop(self.crop)
        self.recompute_preview()

    def on_crop_orientation_invert(self) -> None:
        """Swaps the overlay rect's real width/height around its own center
        (scaled down only if the swapped shape no longer fits the image),
        rather than on_crop_settings_changed's top-left-anchored reshape -
        that one keeps the current width and clips the height, so a
        full-image landscape rect inverted to a narrow portrait strip and
        then back never regrew, it only ever shrank. A back-to-back second
        invert restores the exact pre-invert rect (_crop_invert_memory)
        even when the first swap had to scale it down to fit."""
        self.push_undo()
        before = self.canvas.crop_rect()
        memory = getattr(self, "_crop_invert_memory", None)
        self.crop.aspect_portrait = not self.crop.aspect_portrait
        self.crop_panel.set_from_crop(self.crop)
        if memory is not None and memory[0] == before:
            new_rect = memory[1]
        else:
            new_rect = self._swapped_crop_rect(before)
        self.canvas.set_crop_rect(*new_rect)
        self._crop_invert_memory = (tuple(new_rect), tuple(before))
        self.on_crop_settings_changed(reshape_rect=False)

    def _swapped_crop_rect(self, rect) -> tuple[float, float, float, float]:
        """rect with its real (pixel-proportional) width and height swapped,
        centered on the same point, shrunk uniformly if needed to fit the
        image and then shifted back inside its bounds. Normalized w/h are
        fractions of the image's own width/height, hence the image_ratio
        conversion (see _composed_image_ratio)."""
        x, y, w, h = rect
        image_ratio = self._composed_image_ratio() or 1.0
        cx, cy = x + w / 2, y + h / 2
        new_w = h / image_ratio
        new_h = w * image_ratio
        scale = min(1.0, 1.0 / new_w if new_w else 1.0, 1.0 / new_h if new_h else 1.0)
        new_w *= scale
        new_h *= scale
        new_x = min(max(cx - new_w / 2, 0.0), 1.0 - new_w)
        new_y = min(max(cy - new_h / 2, 0.0), 1.0 - new_h)
        return (new_x, new_y, new_w, new_h)

    def on_crop_apply(self) -> None:
        """Commits the interactively-dragged overlay rect as this photo's
        actual crop - bound to Enter while active crop mode is on - then turns
        active crop mode off, same as Escape, so the composited result isn't
        obscured by the drag overlay. Deliberately does NOT hide the Crop
        block/change layout - only Escape and Enter's shared
        _set_crop_active(False) call, never set_block_visible directly."""
        self.push_undo()
        self.crop.x, self.crop.y, self.crop.width, self.crop.height = self.canvas.crop_rect()
        self.statusBar().showMessage(i18n.tr("status_crop_applied"), 4000)
        self._set_crop_active(False)

    def on_crop_reset(self) -> None:
        self.push_undo()
        self.crop.reset_crop()
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
    # "Stretch on Canvas" - a localized click-and-drag warp, the Distortion
    # section's own counterpart to Move on Canvas above. Each completed drag
    # becomes one pin (anchor + delta, both normalized to the reference canvas)
    # in the Stretch-active channel's own ChannelLayer.stretch_pins - see that
    # field's own docstring in model.py and imaging.apply_stretch_warp for the
    # actual warp math. Commits straight into the model on every mouse-move,
    # undo-coalesced, same "no separate live-preview state" pattern
    # on_canvas_drag already uses for Move on Canvas - only the *last* pin (the
    # in-progress one) is ever touched mid-drag, always by replacing the list
    # wholesale (never mutating one in place), per stretch_pins' own
    # "mutable-field aliasing trap" warning.
    # ------------------------------------------------------------------
    def on_canvas_stretch_drag_started(self, u: float, v: float) -> None:
        if self.stretch_index is None:
            return
        layer = self.layers[self.stretch_index]
        self._push_undo_coalesced(f"stretch_{self.batch_current_index}_{self.stretch_index}")
        layer.stretch_pins = layer.stretch_pins + [(u, v, 0.0, 0.0)]
        self.canvas.set_stretch_pins(layer.stretch_pins)
        self.recompute_preview()

    def on_canvas_stretch_drag(self, du: float, dv: float) -> None:
        if self.stretch_index is None:
            return
        layer = self.layers[self.stretch_index]
        if not layer.stretch_pins:
            return
        self._push_undo_coalesced(f"stretch_{self.batch_current_index}_{self.stretch_index}")
        pins = list(layer.stretch_pins)
        anchor_u, anchor_v, delta_u, delta_v = pins[-1]
        pins[-1] = (anchor_u, anchor_v, delta_u + du, delta_v + dv)
        layer.stretch_pins = pins
        self.canvas.set_stretch_pins(layer.stretch_pins)
        self.recompute_preview()

    def on_canvas_stretch_drag_finished(self) -> None:
        """Drops the just-finished pin if the drag ended up being a plain
        click with no real movement - a (0, 0)-delta pin is a harmless
        no-op for the warp itself, but would still flip the Distortion
        section's Reset button on and leave a stray vertex pull showing in
        the grid overlay."""
        if self.stretch_index is None:
            return
        layer = self.layers[self.stretch_index]
        if not layer.stretch_pins:
            return
        anchor_u, anchor_v, delta_u, delta_v = layer.stretch_pins[-1]
        if abs(delta_u) < 1e-4 and abs(delta_v) < 1e-4:
            layer.stretch_pins = layer.stretch_pins[:-1]
            self.canvas.set_stretch_pins(layer.stretch_pins)
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

        # Synchronous and UI-blocking - flush=True so the bottom-left "Auto
        # Align…" text paints before the freeze (one plain message, no
        # per-channel steps); try/finally so it always clears, whatever
        # happens.
        self._set_status_activity("auto_align", i18n.tr("status_auto_align_running"), flush=True)
        try:
            self._auto_align_all(ref, targets)
        finally:
            self._set_status_activity("auto_align", None)

    def _auto_align_all(self, ref, targets: list[int]) -> None:
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
            apply_distortion = self.auto_align_apply_distortion_checkbox.isChecked()
            if apply_distortion:
                # Same "compose against the locked channel's own transform"
                # reasoning as ref_matrix above - results[index]'s dx/dy/
                # scale/rotation already lands moving's pixels relative to
                # where ref's own (possibly non-identity) manual alignment
                # puts it, so the image optimize_distortion scores against
                # must be ref warped by that same ref_matrix, not the raw
                # ref.image_preview alignment.optimize_distortion further
                # below would otherwise silently register against.
                ref_warped = imaging.warp_to_canvas(ref.image_preview, ref_matrix, (ref_w, ref_h))
            for index, (dx, dy, scale, rotation) in results.items():
                layer = self.layers[index]
                layer.dx, layer.dy, layer.scale, layer.rotation = dx, dy, scale, rotation
                if apply_distortion:
                    # Runs after dx/dy/scale/rotation are set, on the exact
                    # same similarity transform, searching for a small lens
                    # correction that further improves registration with as
                    # little distortion as possible. Synchronous, same as the
                    # rest of Auto Align - see alignment.optimize_distortion's
                    # own docstring for why this isn't backgrounded (a QThread
                    # worker, like HQ Preview's) yet.
                    (layer.distortion, layer.perspective_v, layer.perspective_h, layer.anamorphic) = (
                        alignment.optimize_distortion(ref_warped, layer.image_preview, dx, dy, scale, rotation))
                self._sync_panel_from_layer(index)
            self.recompute_preview()

        self._set_status_activity("auto_align", None)
        if failed_channels:
            show_alert(self, i18n.tr("dialog_auto_align_title"),
                                 i18n.tr("dialog_auto_align_failed_channels", channels=", ".join(failed_channels)))
            self.statusBar().showMessage(i18n.tr("status_auto_align_failed"), 5000)
        else:
            self.statusBar().showMessage(i18n.tr("status_auto_align_all_done"), 5000)

    def on_auto_align_apply_distortion_toggled(self, checked: bool) -> None:
        QSettings(ORG_NAME, APP_NAME).setValue("auto_align_apply_distortion", checked)

    # ------------------------------------------------------------------
    # Compositing pipeline (preview resolution)
    # ------------------------------------------------------------------
    def recompute_preview(self, update_curve_reference: bool = True) -> None:
        """``update_curve_reference`` gates whether the Curves tool's own
        "input" reference-histogram overlay
        (curves_panel.set_reference_histogram) gets refreshed this call - it
        must be True for every ordinary recompute (a photo switch, a slider
        drag, anything upstream of the curve changing) but False for the
        throttled recompute a live curve drag itself triggers
        (_curve_recompute_timer, see on_curve_changed): the whole point of that
        histogram is that it reflects the pipeline's state *before* the curve,
        so it must never move while the curve itself is being dragged. Skipping
        it on a curve-only tick also avoids paying for a second
        straighten/crop/to_uint8 pass that would just get thrown away
        unused."""
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
        self.crop_panel.set_geometry_reset_enabled(self.crop.has_geometry())
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
                panel.reset_distortion_button.setEnabled(False)
                panel.reset_stretch_button.setEnabled(False)
                panel.reset_tone_button.setEnabled(False)
            self._recompute_preview_normal(update_curve_reference)
            return

        self.missing_files_banner.set_missing(
            [(l.label, l.path) for l in self.layers if l.is_missing()])
        self.reset_all_alignment_button.setEnabled(
            any(l.has_alignment_correction() or l.has_distortion_correction() for l in self.layers))
        self.reset_all_color_button.setEnabled(
            any(l.has_tone_correction() for l in self.layers))
        for i, layer in enumerate(self.layers):
            panel = self.channel_panels[i]
            panel.reset_align_button.setEnabled(layer.has_alignment_correction())
            panel.reset_distortion_button.setEnabled(layer.has_distortion_correction())
            panel.reset_stretch_button.setEnabled(bool(layer.stretch_pins))
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
            self._invalidate_hq_preview()
            return

        canvas_h, canvas_w = ref.image_preview.shape[:2]
        canvas_size = (canvas_w, canvas_h)

        solo_layer = next((l for l in self.layers if l.solo), None)
        if solo_layer is not None:
            if not solo_layer.has_image():
                self.canvas.clear_image()
                self.histogram.clear()
                self._last_preview_rgb_u8 = None
                self._invalidate_hq_preview()
                return
            warped, pre_curve_toned, gcurve = self._warp_and_tone(solo_layer, canvas_size, ref)
            mask = imaging.warp_coverage_mask(
                solo_layer.image_preview.shape[:2],
                (solo_layer.dx, solo_layer.dy, solo_layer.scale, solo_layer.rotation,
                 solo_layer.distortion, solo_layer.perspective_v, solo_layer.perspective_h,
                 solo_layer.anamorphic, solo_layer.stretch_pins),
                canvas_size)
            toned = imaging.apply_curve(pre_curve_toned, gcurve)
            toned = self._apply_frame_transform(toned)
            mask = self._apply_frame_transform(mask)
            if not self._showing_full_frame():
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
            ref_h, ref_w = gray_u8.shape[:2]
            self.canvas.set_reference_size(ref_w, ref_h, 1.0 / solo_layer.preview_scale)
            self.histogram.set_image(rgb_u8, valid_mask=mask > 0.5)
            self._last_preview_rgb_u8 = rgb_u8
            if update_curve_reference:
                pre_curve_toned = self._apply_frame_transform(pre_curve_toned)
                if not self._showing_full_frame():
                    pre_curve_toned = imaging.apply_crop_rect(
                        pre_curve_toned, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
                pre_curve_gray_u8 = imaging.to_uint8(pre_curve_toned)
                pre_curve_rgb_u8 = np.repeat(pre_curve_gray_u8[:, :, None], 3, axis=2)
                self.curves_panel.set_reference_histogram(pre_curve_rgb_u8, valid_mask=mask > 0.5)
            # No full-res path for Solo preview (see _recompute_hq_preview) -
            # make sure a HQ pass queued from before Solo was toggled on
            # doesn't fire and silently replace this with the composed RGB.
            self._invalidate_hq_preview()
            return

        images = [l.image_preview if l.has_image() else None for l in self.layers]
        geo_params = [(l.dx, l.dy, l.scale, l.rotation, l.distortion, l.perspective_v, l.perspective_h,
                       l.anamorphic, l.stretch_pins) for l in self.layers]
        tone_params = self._current_tone_params()
        global_params = self._current_global_params()
        # Split what compose_trichrome would otherwise do as one call, so
        # the pre-curve intermediate is available for the Curves tool's own
        # reference histogram without warping the 3 channels a second time.
        visible = tuple(i in self._visible_channels for i in range(3))
        rgb0 = imaging.compose_rgb_from_channels(images, geo_params, tone_params, ref.color_index, visible)
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

        rgb = self._apply_frame_transform(rgb)
        mask = self._apply_frame_transform(mask)
        if not self._showing_full_frame():
            # See the matching comment in the Solo-mode branch above:
            # active crop mode always shows the full frame to crop against.
            rgb = imaging.apply_crop_rect(rgb, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
            mask = imaging.apply_crop_rect(mask, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
        rgb_u8 = imaging.to_uint8(rgb)
        self.canvas.set_image_rgb(rgb_u8)
        ref_h, ref_w = rgb_u8.shape[:2]
        self.canvas.set_reference_size(ref_w, ref_h, 1.0 / ref.preview_scale)
        self.histogram.set_image(rgb_u8, valid_mask=mask > 0.5)
        self._last_preview_rgb_u8 = rgb_u8

        if update_curve_reference:
            pre_curve_rgb = self._apply_frame_transform(pre_curve_rgb)
            if not self._showing_full_frame():
                pre_curve_rgb = imaging.apply_crop_rect(
                    pre_curve_rgb, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
            self.curves_panel.set_reference_histogram(imaging.to_uint8(pre_curve_rgb), valid_mask=mask > 0.5)

        if 0 <= self.batch_current_index < len(self.batch_items):
            self._update_carousel_thumbnail(self.batch_current_index, rgb_u8)

        self._arm_hq_preview_if_enabled()

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
            self._invalidate_hq_preview()
            return

        image = imaging.apply_invert(layer.image_preview, layer.invert)
        global_params = self._current_global_params()
        (gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
         gsat, gtemp, gtint, gcurves, gbw) = global_params
        pre_curve_rgb = imaging.apply_global_correction_before_curves(
            image, gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
            gsat, gtemp, gtint)
        rgb = imaging.apply_curves(pre_curve_rgb, gcurves)
        if gbw:
            rgb = imaging.apply_black_white(rgb)
        rgb = np.clip(rgb, 0.0, 1.0)

        rgb = self._apply_frame_transform(rgb)
        if not self._showing_full_frame():
            rgb = imaging.apply_crop_rect(rgb, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
        rgb_u8 = imaging.to_uint8(rgb)
        self.canvas.set_image_rgb(rgb_u8)
        ref_h, ref_w = rgb_u8.shape[:2]
        self.canvas.set_reference_size(ref_w, ref_h, 1.0 / layer.preview_scale)
        self.histogram.set_image(rgb_u8)
        self._last_preview_rgb_u8 = rgb_u8

        if update_curve_reference:
            pre_curve_rgb = self._apply_frame_transform(pre_curve_rgb)
            if not self._showing_full_frame():
                pre_curve_rgb = imaging.apply_crop_rect(
                    pre_curve_rgb, self.crop.x, self.crop.y, self.crop.width, self.crop.height)
            self.curves_panel.set_reference_histogram(imaging.to_uint8(pre_curve_rgb))

        if 0 <= self.batch_current_index < len(self.batch_items):
            self._update_carousel_thumbnail(self.batch_current_index, rgb_u8)

        self._arm_hq_preview_if_enabled()

    def _current_tone_params(self):
        """Per-layer tone tuples for the active edit state - shared by the
        low-res live preview and the HQ full-res pass (_recompute_hq_preview)
        so the two can never drift apart."""
        if self._compare_active:
            return [(*_NEUTRAL_TONE, l.invert) for l in self.layers]
        return [(l.black_point, l.white_point, l.gamma, l.exposure, l.brightness, l.contrast,
                 l.shadows, l.highlights, l.invert) for l in self.layers]

    def _current_global_params(self):
        """Global Light/Color/Curves/B&W tuple for the active edit state -
        same sharing rationale as _current_tone_params above."""
        if self._compare_active:
            return _NEUTRAL_GLOBAL
        gc = self.global_corr
        return (gc.black_point, gc.white_point, gc.gamma, gc.exposure, gc.brightness, gc.contrast,
                gc.shadows, gc.highlights, gc.saturation, gc.temperature, gc.tint,
                {ch: tuple(pts) for ch, pts in gc.curves.items()}, gc.black_white_active)

    def _warp_and_tone(self, layer, canvas_size, ref):
        h, w = layer.image_preview.shape[:2]
        canvas_w, canvas_h = canvas_size
        source = imaging.apply_lens_correction(
            layer.image_preview, layer.distortion, layer.perspective_v, layer.perspective_h, layer.anamorphic)
        matrix = imaging.build_similarity_matrix(
            layer.dx, layer.dy, layer.scale, layer.rotation,
            src_center=(w / 2, h / 2), dst_center=(canvas_w / 2, canvas_h / 2),
        )
        warped = imaging.warp_to_canvas(source, matrix, canvas_size)
        warped = imaging.apply_stretch_warp(warped, layer.stretch_pins)
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
        # Solo/B&W preview shows this one channel's own independent tone *plus*
        # the Global Correction panel's "Light" adjustments layered on top -
        # the same second tone-curve pass compose_trichrome applies to the
        # composed RGB via apply_global_correction, just without the
        # white-balance/saturation portion of that function, which is
        # color-only and meaningless on a single-channel grayscale image. Solo
        # used to skip Global entirely, silently ignoring it while isolating a
        # channel. The Curves tool's "Y" (master) curve is a tone remap, not a
        # color operation, so it applies here too - same relative position
        # (last) as in apply_global_correction, but applied by the caller, not
        # here (see the comment on the return statement below). The per-channel
        # R/G/B curves are NOT applied here, same reasoning as saturation/
        # temperature/tint being excluded - there's no separate R/G/B data in a
        # single-channel Solo preview, only "Y" is meaningful on it.
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
    def _full_res_params(self, layer, ref) -> tuple:
        # distortion/perspective_v/perspective_h/anamorphic/stretch_pins are
        # a real per-shot lens correction, not a relative offset against ref
        # (unlike dx/dy/scale/rotation) - so they come from layer's own
        # values unconditionally, even when layer is the reference channel
        # itself. stretch_pins is already normalized to the *reference*
        # canvas's own [0, 1] space (see ChannelLayer.stretch_pins), which
        # is resolution-independent the same way the 4 plain coefficients
        # already are - unlike dx_full/dy_full/scale_full below, it needs no
        # preview-to-full-res conversion.
        if layer is ref:
            dx_full, dy_full, scale_full, rotation = 0.0, 0.0, 1.0, 0.0
        else:
            ratio = layer.preview_scale / ref.preview_scale
            dx_full = layer.dx / ref.preview_scale
            dy_full = layer.dy / ref.preview_scale
            scale_full = layer.scale * ratio
            rotation = layer.rotation
        return (dx_full, dy_full, scale_full, rotation,
                layer.distortion, layer.perspective_v, layer.perspective_h, layer.anamorphic,
                layer.stretch_pins)

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

    # ------------------------------------------------------------------
    # HQ Preview (on-demand full-resolution display pass)
    # ------------------------------------------------------------------
    def on_hq_preview_toggled(self, checked: bool) -> None:
        self.hq_preview_enabled = checked
        if checked:
            self._arm_hq_preview_if_enabled()
        else:
            self._hq_idle_timer.stop()
            self._hq_result_stale = True
            self._hide_hq_loading_indicator()
            # Revert to the fast low-res frame right away rather than
            # leaving whatever HQ frame is on screen until the next edit
            # happens to call recompute_preview() anyway. Any HQPreviewWorker
            # still running is simply left to finish on its own - its result
            # will be discarded by _on_hq_preview_result (_hq_result_stale).
            self.recompute_preview()

    def _invalidate_hq_preview(self) -> None:
        """Stops the idle timer and marks any in-flight/just-finished
        HQPreviewWorker's result as stale, without touching
        self.hq_preview_enabled or the button's checked state - used at
        recompute_preview() exits that clear the canvas entirely (no image
        loaded), where there is nothing left for a HQ pass to apply to. A
        thread already running is simply left to finish and get discarded,
        same as everywhere else this module deals with a stale HQ result."""
        self._hq_idle_timer.stop()
        self._hq_result_stale = True
        self._hide_hq_loading_indicator()

    def _arm_hq_preview_if_enabled(self) -> None:
        """(Re)start the HQ idle countdown (_HQ_PREVIEW_IDLE_MS) - called
        from every recompute_preview()/_recompute_preview_normal() exit
        that just pushed a fresh low-res frame, so a HQ pass always follows
        once edits actually stop. QTimer.start() on an already-running
        single-shot timer restarts its countdown, so calling this on every
        edit turns it into a settle-delay (fires N ms after the *last*
        edit) rather than a throttle (contrast with the Curves tool's own
        _CURVE_RECOMPUTE_THROTTLE_MS, which fires at most once per burst).
        Also marks any in-flight/just-finished HQPreviewWorker's result as
        stale - a new edit means whatever it's computing (or already
        computed) no longer reflects the current state. No-op outside HQ
        Preview mode, in Solo mode (no full-res path exists for it - see
        _start_hq_preview), or in Compare mode (a transient before/after
        view, not worth a full-res pass)."""
        self._hq_result_stale = True
        if not self.hq_preview_enabled:
            return
        if any(l.solo for l in self.layers) or self._compare_active or self._perspective_active:
            return
        self._hq_idle_timer.start(_HQ_PREVIEW_IDLE_MS)

    def _start_hq_preview(self) -> None:
        """The idle timer's target - dispatches a background HQPreviewWorker
        to recompose the active photo at its true native resolution (see
        _HQ_PREVIEW_IDLE_MS's own comment for why this isn't done on the UI
        thread: measured at ~2.9s for a single pass on a realistic 24MP
        source). Reuses imaging.compose_trichrome/compose_normal, the same
        resolution-agnostic entry points export_worker.py calls for a real
        export, so the result is guaranteed to match the live preview's own
        look, just sharper - see _on_hq_preview_result for how it's applied
        once ready."""
        if not self.hq_preview_enabled:
            return
        if any(l.solo for l in self.layers) or self._compare_active or self._perspective_active:
            return
        if self._hq_thread is not None:
            # Already computing one - this settle period doesn't get a
            # refresh, the next one will (an edit before then already marks
            # the in-flight result stale and re-arms the timer, so this
            # can't turn into a growing pile of workers).
            return
        is_normal_mode = (0 <= self.batch_current_index < len(self.batch_items)
                           and self.batch_items[self.batch_current_index].mode == "normal")
        if is_normal_mode:
            if not self.normal_layer.has_image():
                return
            geo_params, ref_color_index = None, None
            visible = (True, True, True)
        else:
            ref = self._reference_layer()
            if ref is None or not ref.has_image():
                return
            geo_params = [self._full_res_params(l, ref) for l in self.layers]
            ref_color_index = ref.color_index
            # Display Layer (see recompute_preview's own use of this) -
            # HQ Preview is just a sharper version of the same view, so a
            # hidden channel must stay hidden once the native-resolution
            # pass swaps in, not flash back to the full composite.
            visible = tuple(i in self._visible_channels for i in range(3))

        self._hq_result_stale = False
        self._hq_thread = QThread(self)
        self._hq_worker = HQPreviewWorker(
            is_normal_mode=is_normal_mode,
            layers=self.layers,
            normal_layer=self.normal_layer,
            full_res_loader=self._full_res_image,
            full_res_color_loader=self._full_res_color_image,
            geo_params=geo_params,
            tone_params=self._current_tone_params(),
            global_params=self._current_global_params(),
            ref_color_index=ref_color_index,
            visible=visible,
            crop_active=self._crop_active,
            crop_rotation=self.crop.rotation, crop_mirror_h=self.crop.mirror_h, crop_mirror_v=self.crop.mirror_v,
            crop_geometry=self.crop.geometry_kwargs(),
            crop_x=self.crop.x, crop_y=self.crop.y, crop_width=self.crop.width, crop_height=self.crop.height,
        )
        self._hq_worker.moveToThread(self._hq_thread)
        self._hq_thread.started.connect(self._hq_worker.run)
        self._hq_worker.result_ready.connect(self._on_hq_preview_result)
        self._hq_worker.failed.connect(self._on_hq_preview_failed)
        self._hq_worker.finished.connect(self._hq_thread.quit)
        self._hq_worker.finished.connect(self._hq_worker.deleteLater)
        # Same QThread lifecycle rule as batch import/export: only drop refs
        # (and hide the loading bar) once the thread itself reports
        # finished, not merely the worker's own finished signal.
        self._hq_thread.finished.connect(self._hq_thread.deleteLater)
        self._hq_thread.finished.connect(self._clear_hq_thread_refs)
        self._show_hq_loading_indicator()
        self._hq_thread.start()

    def _on_hq_preview_result(self, rgb_u8: np.ndarray, newly_loaded: list) -> None:
        # newly_loaded is a list of (layer, full-res array) pairs
        # HQPreviewWorker just decoded (only for layers that had no cached
        # image_full at dispatch time - not a dict, since ChannelLayer is a
        # plain unhashable dataclass) - caching the decode here, back on the
        # main thread, means a later HQ pass on the same photo skips the
        # disk read (a RAW source's rawpy decode in particular can take a
        # second or more per channel) without ever mutating layer.image_full
        # from the worker thread itself.
        for layer, full in newly_loaded:
            if layer.image_full is None:
                layer.image_full = full
        if self._hq_result_stale or not self.hq_preview_enabled:
            return
        # set_hq_image_rgb, not set_image_rgb - this swaps in a sharper
        # array for the *same* photo/crop state without redefining the
        # zoom-percentage reference (see CanvasWidget.set_reference_size),
        # so the on-screen box size doesn't jump when this native-res
        # result lands or gets replaced by the next low-res edit.
        self.canvas.set_hq_image_rgb(rgb_u8)

    def _on_hq_preview_failed(self, message: str) -> None:
        if self._hq_result_stale or not self.hq_preview_enabled:
            return
        self.statusBar().showMessage(i18n.tr("hq_preview_failed", error=message), 5000)

    def _clear_hq_thread_refs(self) -> None:
        self._hq_thread = None
        self._hq_worker = None
        self._hide_hq_loading_indicator()

    def _show_hq_loading_indicator(self) -> None:
        # interrupt_message=False: HQ fires 500ms after nearly every edit,
        # so it must not wipe that edit's own "Settings pasted"-style
        # message - it just waits for the message to expire.
        self._set_status_activity("hq", i18n.tr("status_hq_preview_loading"), interrupt_message=False)

    def _hide_hq_loading_indicator(self) -> None:
        self._set_status_activity("hq", None)

    def _set_status_activity(self, key: str, text: str | None, *,
                             interrupt_message: bool = True, flush: bool = False) -> None:
        """Shows (``text``) or clears (``None``) one bottom-left "work in
        progress" entry, keyed so concurrent activities (e.g. an export
        while HQ Preview computes) each keep their own line, joined with
        " · ". ``interrupt_message`` clears any temporary showMessage()
        text, which would otherwise hide this area. ``flush`` repaints the
        status bar right away - needed before a synchronous, UI-blocking
        operation (session save/load, a Finder drop), which would
        otherwise finish before the event loop ever painted the text.

        Clearing respects _STATUS_ACTIVITY_MIN_MS: an activity cleared
        sooner stays up for the remainder, and any showMessage() made
        meanwhile (its own "done" message) waits until it's gone. HQ
        Preview is the exception for the hold - it runs in the background
        after nearly every edit, so it must never delay unrelated
        messages."""
        gen = self._status_activity_gen.get(key, 0) + 1
        self._status_activity_gen[key] = gen
        if text is None:
            if key not in self._status_activities:
                return
            elapsed_ms = (time.monotonic() - self._status_activity_started.get(key, 0.0)) * 1000.0
            remaining_ms = int(_STATUS_ACTIVITY_MIN_MS - elapsed_ms)
            if remaining_ms > 0:
                if key != "hq":
                    self._status_clears_holding.add(key)
                    self.statusBar().set_held(True)
                QTimer.singleShot(remaining_ms, lambda: self._end_status_activity(key, gen))
                return
            self._end_status_activity(key, gen)
            return
        if key not in self._status_activities:
            self._status_activity_started[key] = time.monotonic()
        self._status_activities[key] = text
        # A restart/update cancels this key's own pending deferred clear.
        self._status_clears_holding.discard(key)
        if not self._status_clears_holding:
            self.statusBar().set_held(False)
        if interrupt_message:
            self.statusBar().clearMessage()
        self._refresh_status_activity()
        if flush:
            # A bare repaint() isn't enough: the area was just made visible,
            # and its layout/geometry only settles on the next event-loop
            # pass - repainting before that painted nothing on screen ahead
            # of the freeze. Processing pending (non-input) events lets the
            # layout + paint actually happen; excluding user input keeps a
            # click from re-entering mid-operation.
            QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

    def _end_status_activity(self, key: str, gen: int) -> None:
        """The actual removal behind a (possibly deferred) clear - skipped
        when ``key`` was updated/restarted since (its generation moved on)."""
        if self._status_activity_gen.get(key) != gen:
            return
        self._status_activities.pop(key, None)
        self._status_activity_started.pop(key, None)
        self._status_clears_holding.discard(key)
        self._refresh_status_activity()
        if not self._status_clears_holding:
            self.statusBar().set_held(False)

    def _refresh_status_activity(self) -> None:
        busy = bool(self._status_activities)
        self.status_activity_label.setText("  ·  ".join(self._status_activities.values()))
        if busy and not self._status_spin_timer.isActive():
            self._status_spin_angle = 0.0
            self.status_activity_icon.set_rotation(0.0)
            self._status_spin_timer.start()
        elif not busy:
            self._status_spin_timer.stop()
            self.status_activity_icon.set_rotation(0.0)
        self.status_activity_container.setVisible(busy)

    def _on_status_spin_tick(self) -> None:
        self._status_spin_angle = (self._status_spin_angle - _HQ_SPIN_DEGREES_PER_SEC * _HQ_SPIN_TICK_MS / 1000.0) % 360.0
        self.status_activity_icon.set_rotation(self._status_spin_angle)

    def _current_export_base_name(self) -> str:
        if 0 <= self.batch_current_index < len(self.batch_items):
            return self.batch_items[self.batch_current_index].base
        ref = self._reference_layer()
        if ref.path:
            return os.path.splitext(os.path.basename(ref.path))[0]
        return "trichrome"

    def _apply_scan_tool_ui_state(self) -> None:
        """Shows or hides every way into Scan: the toolbar slot, the Tools
        menu entry and the Window ▸ Scan layout. Hidden *and* disabled, so a
        hidden action can't fire. The S key checks scan_tool_enabled itself.
        The toolbar slots sit between two equal expanding spacers, so the 3
        (or 4) visible buttons stay centered on their own."""
        enabled = self.scan_tool_enabled
        self.scan_toolbar_btn.setVisible(enabled)
        tools_action = self.block_menu_actions["scan"]
        tools_action.setVisible(enabled)
        tools_action.setEnabled(enabled)
        layout_action = self.builtin_layout_load_actions["Scan"]
        layout_action.setVisible(enabled and not self.light_mode_active)
        layout_action.setEnabled(enabled and not self.light_mode_active)

    def set_scan_tool_enabled(self, enabled: bool) -> bool:
        """Preferences > Experimental > Enable Scan tool. Refuses to turn it
        off mid-capture. Returns the state actually applied."""
        if not enabled and self.scan_panel._capturing:
            show_alert(self, i18n.tr("settings_scan_tool_busy_title"),
                       i18n.tr("settings_scan_tool_busy_text"))
            return True
        QSettings(ORG_NAME, APP_NAME).setValue(SCAN_TOOL_ENABLED_KEY, enabled)
        if enabled == self.scan_tool_enabled:
            return enabled
        self.scan_tool_enabled = enabled
        if not enabled:
            self.scan_panel.set_pick_from_photo_active(False)
            # The Scan slot can't stay the highlighted one once it's hidden.
            if self.scan_toolbar_btn.isChecked():
                self.default_layout_group.setExclusive(False)
                self.scan_toolbar_btn.setChecked(False)
                self.default_layout_group.setExclusive(True)
        self._apply_scan_tool_ui_state()
        self._apply_block_layout()
        return enabled

    def open_settings_dialog(self) -> None:
        SettingsDialog(self, ORG_NAME, APP_NAME, parent=self).exec()

    def show_check_updates_dialog(self) -> None:
        self._run_update_dialog(UpdateCheckDialog(self))

    def _run_update_dialog(self, dialog: UpdateCheckDialog) -> None:
        """Shows the dialog; if it ends with a downloaded, checked update
        (Restart Now), quits through the normal close path - unsaved changes,
        running export and so on all still ask - and only then starts the
        bundle swap (self_update.launch_installer). If the user cancels the
        quit, the staged update is dropped."""
        if dialog.exec() != QDialog.Accepted or dialog.staged_update is None:
            return
        if self.close():
            self_update.launch_installer(dialog.staged_update)
            QApplication.instance().quit()
        else:
            self_update.discard_staged_update(dialog.staged_update)

    def start_update_check_at_startup(self) -> None:
        """Launch-time entry point (main.py), while Preferences > General >
        "Check for updates at startup" is checked. Quiet by design: a failure
        (most commonly, no internet) is never surfaced - only a newer release
        prompts the dialog, via the same UpdateCheckDialog the menu item opens,
        with the result already in hand so it isn't fetched twice."""
        if not self.check_updates_on_startup or not self.isVisible():
            return
        self._startup_update_thread = QThread(self)
        self._startup_update_worker = UpdateCheckWorker()
        self._startup_update_worker.moveToThread(self._startup_update_thread)
        self._startup_update_thread.started.connect(self._startup_update_worker.run)
        self._startup_update_worker.result_ready.connect(self._on_startup_update_result)
        self._startup_update_worker.finished.connect(self._startup_update_thread.quit)
        self._startup_update_thread.finished.connect(self._startup_update_thread.deleteLater)
        self._startup_update_thread.finished.connect(self._on_startup_update_thread_finished)
        self._startup_update_thread.start()

    def _on_startup_update_thread_finished(self) -> None:
        self._startup_update_worker = None
        self._startup_update_thread = None

    def _on_startup_update_result(self, latest_version: str, release_url: str, assets: dict) -> None:
        # Quick Tour always has priority over this prompt - main.py already
        # sequences the check to start after the tour is done, but a slow
        # request can still resolve while the user has since opened the tour
        # by hand (Help menu), so check _quick_tour here too, not just at
        # dispatch time.
        if (parse_version(latest_version) > parse_version(__version__)
                and self.isVisible() and QApplication.activeModalWidget() is None
                and getattr(self, "_quick_tour", None) is None):
            self._run_update_dialog(UpdateCheckDialog(self, initial_result=(latest_version, release_url, assets)))

    def _stop_startup_update_check(self) -> None:
        """Called on quit: never let the QThread be destroyed while running
        (see widgets/update_dialog.py's "Confirmed crash")."""
        if self._startup_update_worker is not None:
            self._startup_update_worker.result_ready.disconnect(self._on_startup_update_result)
        if self._startup_update_thread is not None:
            self._startup_update_thread.quit()
            self._startup_update_thread.wait()

    def export_image(self) -> None:
        dialog = ExportDialog(self, parent=self)
        dialog.exec()

    # ------------------------------------------------------------------
    # Background export
    # ------------------------------------------------------------------
    def is_export_running(self) -> bool:
        return self._export_thread is not None

    def start_background_export(
        self, items: list, output_dir: str | None, suffix: str, ext: str, bit_depth: int,
        reveal_in_finder: bool,
    ) -> None:
        """Exports ``items`` on a background thread while editing goes on.
        Each item is snapshotted first (same shallow copies as
        _snapshot_state - every write site replaces mutable fields rather
        than mutating them, so this is safe), so edits made while the export
        runs never race with the worker reading the same objects."""
        snapshot = [
            BatchItem(
                base=it.base, paths=dict(it.paths),
                layers=[copy.copy(l) for l in it.layers],
                global_corr=copy.copy(it.global_corr),
                crop=copy.copy(it.crop),
                mode=it.mode, normal_layer=copy.copy(it.normal_layer),
                selected=it.selected, uid=it.uid,
                capture_date=it.capture_date, custom_order=it.custom_order,
            ) for it in items
        ]
        self._export_items = snapshot
        self._export_ok_paths = []
        self._export_failures = []
        self._export_output_dir = output_dir
        self._export_reveal = reveal_in_finder
        self._set_status_activity("export", i18n.tr("status_exporting", i=0, n=len(snapshot)))

        self._export_thread = QThread(self)
        self._export_worker = BatchExportWorker(
            items=snapshot,
            full_res_loader=self._full_res_image,
            full_res_params=self._full_res_params,
            full_res_color_loader=self._full_res_color_image,
            output_dir=output_dir,
            suffix=suffix,
            ext=ext,
            bit_depth=bit_depth,
        )
        self._export_worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.item_result.connect(self._on_export_item_result)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.finished.connect(self._export_thread.quit)
        # No worker.deleteLater here (unlike batch import/HQ Preview): it
        # destroys the worker on the export thread while the main thread may
        # be releasing the QThread wrapper at the same moment - a PySide race
        # that segfaulted (QThreadWrapper::disconnectNotify on a half-freed
        # wrapper). The worker is instead freed on the main thread, by
        # dropping the last ref in _clear_export_thread_refs once the thread
        # has fully finished.
        self._export_thread.finished.connect(self._export_thread.deleteLater)
        self._export_thread.finished.connect(self._clear_export_thread_refs)
        self._export_thread.start()

    def _on_export_progress(self, done: int, total: int) -> None:
        self._set_status_activity(
            "export", i18n.tr("status_exporting", i=done, n=total), interrupt_message=False)

    def _on_export_item_result(self, row: int, success: bool, message: str) -> None:
        if success:
            self._export_ok_paths.append(message)
        else:
            self._export_failures.append((self._export_items[row].base, message))

    def _on_export_finished(self) -> None:
        cancelled = self._export_worker is not None and self._export_worker._cancelled
        total = len(self._export_items)
        ok = len(self._export_ok_paths)
        failed = len(self._export_failures)
        self._set_status_activity("export", None)
        if cancelled and ok + failed < total:
            message = i18n.tr("batch_status_cancelled", i=ok + failed, n=total)
        elif total == 1 and ok == 1:
            message = None
            self.statusBar().showMessage(i18n.tr("status_exported", path=self._export_ok_paths[0]), 8000)
        else:
            message = i18n.tr("batch_status_done", ok=ok, failed=failed)
        if message is not None:
            self.statusBar().showMessage(i18n.tr("status_export_finished", status=message), 8000)
        if ok and self._export_reveal and not cancelled:
            if ok == 1:
                subprocess.run(["open", "-R", self._export_ok_paths[0]])
            elif self._export_output_dir:
                # Nothing to reveal for "same as source" batches - each item
                # lands next to its own source file, no single shared folder.
                subprocess.run(["open", self._export_output_dir])
        if not cancelled:
            self._play_export_done_sound()
        if failed and not cancelled:
            show_alert(
                self, i18n.tr("dialog_export_error_title"),
                i18n.tr("export_failures_text", failed=failed, n=total),
                table_headers=(i18n.tr("export_failures_photo_header"), i18n.tr("export_failures_error_header")),
                table_rows=self._export_failures,
                table_tooltips=[err for _, err in self._export_failures])

    def _clear_export_thread_refs(self) -> None:
        # Worker first, while the QThread wrapper is still alive.
        self._export_worker = None
        self._export_thread = None

    def _confirm_cancel_running_export(self) -> bool:
        """Asks before quitting mid-export. True = go ahead (the export, if
        any, has been cancelled and its thread joined, so the QThread is
        never destroyed while still running)."""
        if self._export_thread is None:
            return True
        dialog = ConfirmDialog(
            self, i18n.tr("export_quit_confirm_title"), i18n.tr("export_quit_confirm_text"),
            confirm_label=i18n.tr("export_quit_confirm_button"),
            cancel_label=i18n.tr("dialog_quit_cancel_button"))
        dialog.exec()
        if dialog.result != "confirm":
            return False
        if self._export_worker is not None:
            self._export_worker.cancel()
        if self._export_thread is not None:
            # quit() directly: worker.finished -> thread.quit is a queued
            # call to this (now blocked) main thread, so waiting on it alone
            # would deadlock. The loop exits once run() returns, i.e. after
            # at most the photo currently being written.
            self._export_thread.quit()
            self._export_thread.wait()
        return True
