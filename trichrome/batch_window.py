"""Batch Import: pick a set of R/G/B triplets and import them into the main
session as independent, individually-editable photos (see MainWindow's
carousel). Export itself now happens from the main window's Export dialog."""
from __future__ import annotations

import os

from PySide6.QtCore import QSize, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QPushButton, QRadioButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

# Qt's own QWIDGETSIZE_MAX ((1 << 24) - 1) - not exposed as a PySide6
# binding in this Qt version, so the literal value stands in for it when
# clearing a widget's maximumSize() back to "no cap" before remeasuring.
_QWIDGETSIZE_MAX = 16777215

from . import batch, filters as filters_module, i18n, imaging
from .widgets.alert_dialog import show_alert
from .widgets.channel_panel import CHANNEL_COLORS
from .widgets.controls import CollapsibleSection
from .widgets.import_panel import MODE_ICONS, MODE_KEYS, MODE_LABEL_KEYS
from .widgets.info_bubble import InfoButton, show_list_bubble
from .widgets.svg_icons import SvgToolButton, raw_svg_icon, tinted_svg_icon

ORG_NAME = "TrichromeMaker"
APP_NAME = "TrichromeMaker"
CHANNEL_LETTERS = ("R", "G", "B")
IMAGE_EXTENSIONS = imaging.IMPORTABLE_EXTENSIONS
ADVANCED_MODE_IDS = ("classic", "ir", "aerochrome", "custom")

# Processing Mode's own 3 choices (2026-09-07) - a plain QRadioButton's
# native bullet ("puce") reads poorly next to a real icon+label, so the
# indicator is hidden entirely and the selected choice is framed instead -
# a bordered/tinted box around the whole icon+text, same accent blue
# (#5b9bd5) the Files-block Mode combo's own popup highlight already
# uses, for visual consistency between the two "pick one of these 3
# modes" controls in this app.
_PROCESSING_MODE_RADIO_STYLE = """
QRadioButton {
    border: 2px solid transparent;
    border-radius: 6px;
    padding: 5px 10px;
    background: transparent;
}
QRadioButton::indicator {
    width: 0px;
    height: 0px;
}
QRadioButton:hover {
    background: rgba(255, 255, 255, 14);
}
QRadioButton:checked {
    border: 2px solid #5b9bd5;
    background: rgba(91, 155, 213, 30);
}
"""

# Every per-channel file list (Automatic's 3 read-only lists, Manual's 3
# editable ones) gets a full-width label above it naming the channel
# (Red/Green/Blue) - styled to read as a real table header bar (background
# + border) rather than a plain floating caption, so both modes' file lists
# look like consistent "tables" (2026-09-10). Automatic's are plain labels
# with no buttons, so this direct label styling still applies as-is there.
_CHANNEL_COLUMN_HEADER_STYLE = """
QLabel {{
    color: {color};
    font-weight: bold;
    background: rgba(127, 127, 127, 40);
    border: 1px solid rgba(127, 127, 127, 70);
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    padding: 4px 0px;
}}
"""

# Manual's and Sequential's header bars (2026-09-11) also host the
# Add/Remove/Clear icon buttons, not just a label - so the frame styling
# (background/border) lives on a plain QWidget wrapping label+buttons
# together, not on the label itself. Needs WA_StyledBackground to actually
# paint its own background/border at all (see the _ChannelFileBlock
# gotcha this mirrors, main_window.py's Files-block channel-swap rows) -
# and the label inside it needs its own "border: none; background:
# transparent" so it stops inheriting the wrapper's frame via the
# stylesheet cascade, same fix applied there.
_CHANNEL_HEADER_BAR_STYLE = """
QWidget {
    background: rgba(127, 127, 127, 40);
    border: 1px solid rgba(127, 127, 127, 70);
    border-radius: 4px;
}
"""
_CHANNEL_HEADER_LABEL_STYLE = """
QLabel {{
    color: {color};
    font-weight: bold;
    background: transparent;
    border: none;
}}
"""
# Shared by Manual's per-column header_layout and Sequential's own
# semi_header_layout so both bars render at the exact same height
# (2026-09-12, per the user's own ask - the two previously used different
# margins and so didn't line up).
_CHANNEL_HEADER_BAR_MARGINS = (6, 2, 6, 2)
# The header bars themselves (not just their internal margins) get this
# exact fixed height too (2026-09-12, per the user's own ask - "les
# encarts" must be fixed-size like the tables, not just visually
# consistent) - the button height mirrors SvgToolButton's own default
# `size` parameter (30, 26), so this must be updated together with any
# future change to the icon buttons used inside these bars.
_HEADER_BAR_BUTTON_HEIGHT = 26
_HEADER_BAR_HEIGHT = _HEADER_BAR_BUTTON_HEIGHT + _CHANNEL_HEADER_BAR_MARGINS[1] + _CHANNEL_HEADER_BAR_MARGINS[3]

# All 3 modes' file lists/tables (Automatic's 3 lists, Sequential's 1 list,
# Manual's 3 lists) get this exact same *fixed* (not minimum) height, so
# they show the same number of rows and take up the same vertical space
# regardless of which mode is active - a plain per-row pixel estimate
# (font height + fixed padding) rather than QListWidget.sizeHintForRow(),
# which returns -1 on an empty list and so can't be used before any items
# exist. Genuinely fixed (2026-09-12, changed from a minimum) - the
# tables/header bars ("les encarts") are what must be fixed-size; each
# mode's own container is deliberately *not* forced to match the others
# (see _fit_window_to_active_mode) - an earlier version did exactly that
# and left Manual/Sequential padded out with a large dead blank area
# under their real content just to match Automatic's own taller one.
_LIST_ROWS = 5
_LIST_ROW_PADDING_PX = 10


def _apply_list_fixed_height(widget, rows: int = _LIST_ROWS) -> None:
    row_height = widget.fontMetrics().height() + _LIST_ROW_PADDING_PX
    frame = 2 * widget.frameWidth()
    widget.setFixedHeight(row_height * rows + frame)


class _UnmatchedSummaryLabel(QLabel):
    """Automatic mode's unmatched-files count - shows the actual filenames
    in a ListBubble (the same popup chrome this app's "?" info buttons
    use) while hovered, per the user's own "afficher la liste au survol
    dans une fenêtre similaire à celle des boutons infos" spec
    (2026-09-07) - replacing both the earlier "Show list" button pass and
    the hover-reveals-an-inline-widget pass right before this one.

    Since the bubble is a separate top-level popup window (not a child
    widget the way the earlier inline list was), leaving this label and
    leaving the bubble are two different widgets' events - `leaveEvent`
    below doesn't close the bubble immediately, it defers by a beat via
    `QTimer.singleShot` so a cursor crossing the small gap between the
    label and the bubble has a chance to actually land on the bubble
    first; `ListBubble.leaveEvent` (info_bubble.py) is what closes it once
    the cursor has genuinely left the bubble itself."""

    _CLOSE_GRACE_MS = 80

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[str] = []
        self._bubble = None

    def enterEvent(self, event) -> None:
        if self.items and self._bubble is None:
            self._bubble = show_list_bubble(self.items, self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        QTimer.singleShot(self._CLOSE_GRACE_MS, self._maybe_close_bubble)
        super().leaveEvent(event)

    def _maybe_close_bubble(self) -> None:
        if self._bubble is not None and not self._bubble.underMouse():
            self._bubble.close()
            self._bubble = None

    def close_bubble(self) -> None:
        """Forces the bubble closed immediately - used whenever the
        summary itself is about to be hidden (mode switch, a fresh
        rescan), so a still-open bubble can't linger over stale data."""
        if self._bubble is not None:
            self._bubble.close()
            self._bubble = None


class _DropImageListWidget(QListWidget):
    """A QListWidget that supports both internal drag-to-reorder and
    dropping image files onto it from outside the app (e.g. Finder)."""

    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setAcceptDrops(True)

    def _external_urls(self, event):
        if event.source() is self or not event.mimeData().hasUrls():
            return None
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        paths = [p for p in paths if os.path.isfile(p) and p.lower().endswith(IMAGE_EXTENSIONS)]
        return paths or None

    def dragEnterEvent(self, event) -> None:
        if self._external_urls(event) is not None:
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._external_urls(event) is not None:
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        paths = self._external_urls(event)
        if paths is not None:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class BatchWindow(QMainWindow):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.resize(780, 460)

        self.triplets: list[batch.Triplet] = []
        self.unmatched: list[str] = []
        self._semi_triplets: list[batch.Triplet] = []
        self._manual_triplets: list[batch.Triplet] = []
        self._window_shown_once = False

        self._build_ui()
        self._restore_folder()
        self._restore_last_settings()
        self.retranslate_ui()
        QShortcut(QKeySequence.Close, self, activated=self.close)

    def showEvent(self, event) -> None:
        """sizeHint() for a complex nested widget (Import Rules'
        CollapsibleSection, holding a real QTableWidget/QComboBoxes)
        measures smaller before the window has ever actually been shown/
        polished once than it does afterward - so the window needs
        re-fitting again here (base showEvent first, so the real show/
        polish happens before remeasuring), not just from retranslate_ui()
        inside __init__ (necessarily pre-show, where it would otherwise
        freeze the window at that too-small pre-show size)."""
        super().showEvent(event)
        self._window_shown_once = True
        self._fix_mode_container_widths()
        self._fit_window_to_active_mode()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)

        # --- Processing Mode: Solo / Classic Trichrome / Color Trichrome -
        # added 2026-09-07, sitting above everything else so it's the
        # first decision a user makes here, same 3 choices/icons/labels as
        # the main window's own Files-block Mode selector
        # (widgets/import_panel.py's MODE_KEYS/MODE_ICONS/MODE_LABEL_KEYS -
        # imported rather than redefined, so the two stay in lockstep by
        # construction). Trichrome (either variant) leaves the existing
        # "Input Folder"-style triplet-matching UI (input_group) exactly
        # as it already worked; Solo replaces it with a much simpler
        # "select image(s) / select folder / clear" flow (solo_group) -
        # see _on_processing_mode_changed. The "?" reuses the exact info
        # bubble text the Files-block combo already uses (mode_select_info)
        # - same 3 modes, same explanation, no need for a second one.
        self.processing_mode_group = QGroupBox()
        processing_mode_row = QHBoxLayout(self.processing_mode_group)
        self.processing_mode_button_group = QButtonGroup(self)
        self.processing_mode_radios: dict[str, QRadioButton] = {}
        dpr = self.devicePixelRatioF() or 1.0
        for key in MODE_KEYS:
            radio = QRadioButton()
            radio.setIcon(raw_svg_icon(MODE_ICONS[key], 20, dpr))
            radio.setIconSize(QSize(20, 20))
            radio.setStyleSheet(_PROCESSING_MODE_RADIO_STYLE)
            radio.toggled.connect(lambda checked: self._on_processing_mode_changed() if checked else None)
            radio.toggled.connect(lambda checked, k=key: self._save_processing_mode_setting(k) if checked else None)
            self.processing_mode_button_group.addButton(radio)
            processing_mode_row.addWidget(radio)
            processing_mode_row.addSpacing(6)
            self.processing_mode_radios[key] = radio
        processing_mode_row.addStretch(1)
        self.processing_mode_info_button = self._make_info_button("mode_select_info")
        processing_mode_row.addWidget(self.processing_mode_info_button)
        # Default matches the Files-block combo's own default (B&W
        # Trichrome) - this window's whole pre-existing purpose (triplet
        # matching) is trichrome-focused, so that's the least surprising
        # starting point. blockSignals here since input_group/solo_group/
        # align_group don't exist yet at this point in _build_ui - a real
        # AttributeError caught by a headless boot otherwise, since
        # setChecked(True) fires `toggled` synchronously - the initial
        # visibility sync happens explicitly at the end of _build_ui
        # instead, once every referenced widget exists.
        self.processing_mode_radios["bw_trichrome"].blockSignals(True)
        self.processing_mode_radios["bw_trichrome"].setChecked(True)
        self.processing_mode_radios["bw_trichrome"].blockSignals(False)
        root.addWidget(self.processing_mode_group)

        self.input_group = QGroupBox()
        input_layout = QVBoxLayout(self.input_group)

        mode_row = QHBoxLayout()
        self.mode_auto_radio = QRadioButton()
        self.mode_auto_radio.setChecked(True)
        self.mode_auto_radio.toggled.connect(self._on_mode_changed)
        self.mode_semi_radio = QRadioButton()
        self.mode_semi_radio.toggled.connect(self._on_mode_changed)
        self.mode_manual_radio = QRadioButton()
        self.mode_manual_radio.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_auto_radio)
        mode_row.addSpacing(24)
        mode_row.addWidget(self.mode_semi_radio)
        mode_row.addSpacing(24)
        mode_row.addWidget(self.mode_manual_radio)
        mode_row.addStretch(1)
        self.mode_info_button = self._make_info_button("batch_mode_info")
        mode_row.addWidget(self.mode_info_button)
        input_layout.addLayout(mode_row)

        # --- automatic mode UI ---
        self.auto_container = QWidget()
        self.auto_layout = auto_layout = QVBoxLayout(self.auto_container)
        auto_layout.setContentsMargins(0, 0, 0, 0)

        # 3 distinct read-only lists, one per channel (2026-09-10) - same
        # visual shape as Manual mode's 3 columns (colored "Rouge/Vert/
        # Bleu" header bar above each list, same shared min-height so all
        # 3 modes' lists default to the same footprint), just auto-
        # populated from the matched triplets instead of user-editable.
        auto_columns_row = QHBoxLayout()
        self.auto_lists: dict[str, QListWidget] = {}
        self.auto_column_labels: dict[str, QLabel] = {}
        for letter in CHANNEL_LETTERS:
            col_widget = QWidget()
            col_layout = QVBoxLayout(col_widget)
            col_layout.setContentsMargins(0, 0, 0, 0)
            color = CHANNEL_COLORS.get(letter, "#888")
            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(_CHANNEL_COLUMN_HEADER_STYLE.format(color=color))
            # Same fixed height as Manual's/Sequential's own header bars
            # (2026-09-12, per the user's own ask) - this one is a plain
            # QLabel with no buttons of its own, but it must still match
            # their height exactly for visual consistency across all 3
            # modes' headers.
            label.setFixedHeight(_HEADER_BAR_HEIGHT)
            col_layout.addWidget(label)

            lst = QListWidget()
            lst.setEditTriggers(QAbstractItemView.NoEditTriggers)
            lst.setSelectionMode(QAbstractItemView.NoSelection)
            _apply_list_fixed_height(lst)
            col_layout.addWidget(lst)

            auto_columns_row.addWidget(col_widget)
            self.auto_lists[letter] = lst
            self.auto_column_labels[letter] = label
        auto_layout.addLayout(auto_columns_row)

        input_row = QHBoxLayout()
        self.input_path_edit = QLineEdit()
        self.input_path_edit.setReadOnly(True)
        self.browse_input_button = QPushButton()
        self.browse_input_button.clicked.connect(self.browse_input_folder)
        self.rescan_button = QPushButton()
        self.rescan_button.clicked.connect(self.rescan)
        input_row.addWidget(self.input_path_edit, stretch=1)
        input_row.addWidget(self.browse_input_button)
        input_row.addWidget(self.rescan_button)
        auto_layout.addLayout(input_row)

        # --- advanced options (automatic mode only): channel-swap presets
        # for infrared/aerochrome-style trichromes where the R/G/B filters
        # don't map 1:1 to the R/G/B digital channels.
        self.advanced_options_section = CollapsibleSection()
        self.advanced_options_section.toggle_button.setStyleSheet(
            "QToolButton { border: none; font-weight: bold; font-size: 13px; text-align: left; "
            "background: rgba(120, 150, 220, 45); border-radius: 4px; padding: 5px 8px; }"
        )
        # Expanding/collapsing it is the one remaining dynamically-sized
        # part of any mode container now that tables/header bars are all
        # fixed-size - resize the window to match instead of clipping its
        # content or leaving dead space (2026-09-12, see
        # _fit_window_to_active_mode).
        #
        # **Deferred via QTimer.singleShot(0, ...), not called directly**:
        # confirmed directly that calling it synchronously here (inside
        # CollapsibleSection._on_clicked's own toggled.emit(), itself
        # several layout levels deeper than a mode-switch radio's own
        # toggled) still read a stale sizeHint() even after the usual
        # invalidate()/activate()/processEvents() sequence - collapsing
        # measured the *expanded* height back, every time. The exact same
        # processEvents() call, made instead from *outside* any signal
        # handler (i.e. after this whole toggled chain has already
        # returned), read the correct, already-updated value - so
        # scheduling this for the next event-loop turn instead of running
        # it inline is what actually makes it accurate, not the
        # measurement sequence itself. Mode switches don't need this same
        # deferral (their own container visibility changes are shallower
        # in the layout tree and settle within the immediate,
        # synchronous call).
        self.advanced_options_section.toggled.connect(
            lambda _checked: QTimer.singleShot(0, self._fit_window_to_active_mode))
        # A second "?" button, in the app's accent blue, sits right next to
        # the section's own disclosure title (added 2026-09-08) - a general
        # explanation of what this whole section is for, distinct from the
        # per-rule breakdown below.
        self.auto_import_rules_info_button = InfoButton(
            "batch_auto_import_rules_info", color="#5b9bd5")
        self.advanced_options_section.header_row.addWidget(self.auto_import_rules_info_button)
        # "?" info button explaining the 4 rules themselves (Classic/IR/
        # Aerochrome/Custom) - moved back into the header row (2026-09-11,
        # per the user's own ask), right after the general one above -
        # toggle_button's own Expanding size policy is what pushes both
        # "?" buttons flush to the header's right edge, inside the same
        # blue-tinted frame, rather than needing an explicit stretch here.
        # Plain default InfoButton style (no color override), same as
        # every other "?" button in the app - only the general one above
        # gets the accent-blue "more important" ring.
        self.advanced_options_info_button = InfoButton("batch_advanced_options_info")
        self.advanced_options_section.header_row.addWidget(self.advanced_options_info_button)
        self.advanced_mode_radios: dict[str, QRadioButton] = {}
        mode_row2 = QHBoxLayout()
        for mode_id in ADVANCED_MODE_IDS:
            radio = QRadioButton()
            mode_row2.addWidget(radio)
            self.advanced_mode_radios[mode_id] = radio
        mode_row2.addStretch(1)
        self.advanced_options_section.content_layout.addLayout(mode_row2)

        groups_row = QHBoxLayout()

        # -- channel mapping: which filter feeds R/G/B for the active mode.
        # Fixed (disabled) for Classic/IR/Aerochrome, freely editable for Custom.
        # Sized to its content, not stretched, so Filters can use the rest.
        self.mapping_group = QGroupBox()
        mapping_grid = QGridLayout(self.mapping_group)
        mapping_grid.setHorizontalSpacing(8)
        self.mapping_combos: dict[str, QComboBox] = {}
        for row, channel in enumerate(CHANNEL_LETTERS):
            combo = QComboBox()
            combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            combo.currentIndexChanged.connect(lambda _i, ch=channel: self._on_mapping_combo_changed(ch))
            arrow_label = QLabel("→")
            channel_label = QLabel(channel)
            channel_label.setStyleSheet(
                f"color: {CHANNEL_COLORS.get(channel, '#888')}; font-weight: bold;")
            mapping_grid.addWidget(combo, row, 0)
            mapping_grid.addWidget(arrow_label, row, 1)
            mapping_grid.addWidget(channel_label, row, 2)
            self.mapping_combos[channel] = combo
        groups_row.addWidget(self.mapping_group)

        # -- camera filters: add/edit/delete the named filters (and the
        # filename keywords that identify them) available to map above.
        self.filters_group = QGroupBox()
        filters_layout = QVBoxLayout(self.filters_group)

        self.filters_table = QTableWidget(0, 3)
        self.filters_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.filters_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.filters_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.filters_table.verticalHeader().setVisible(False)
        self.filters_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.filters_table.setMinimumHeight(180)
        self.filters_table.itemChanged.connect(self._on_filter_item_changed)
        filters_layout.addWidget(self.filters_table)

        filters_footer_row = QHBoxLayout()
        self.add_filter_button = QPushButton()
        self.add_filter_button.clicked.connect(self._add_filter)
        filters_footer_row.addWidget(self.add_filter_button)
        self.filters_info_button = self._make_info_button("batch_filters_hint")
        filters_footer_row.addWidget(self.filters_info_button)
        filters_footer_row.addStretch(1)
        filters_layout.addLayout(filters_footer_row)
        groups_row.addWidget(self.filters_group, stretch=1)

        self.advanced_options_section.content_layout.addLayout(groups_row)

        self.advanced_mode_radios["classic"].setChecked(True)

        # Import Rules lives inside auto_container (not a shared sibling)
        # so it only ever shows in Automatic mode - it only makes sense for
        # the Automatic matcher, and auto_container's own visibility toggle
        # in _on_mode_changed handles hiding/showing it for free.
        auto_layout.addWidget(self.advanced_options_section)

        input_layout.addWidget(self.auto_container)

        # --- semi-automatic mode UI ---
        self.semi_container = QWidget()
        self.semi_layout = semi_layout = QVBoxLayout(self.semi_container)
        semi_layout.setContentsMargins(0, 0, 0, 0)

        # semi_table_widget bundles the header bar + list into one item (so
        # from semi_layout's own perspective it's still a single "table"
        # occupying index 0, keeping _move_triplets_info_into's "insert at
        # index 1, right after the table" convention valid without special-
        # casing Sequential).
        semi_table_widget = QWidget()
        semi_table_layout = QVBoxLayout(semi_table_widget)
        # Deliberately no setContentsMargins/setSpacing override here - the
        # default QVBoxLayout spacing is what separates Manual's own
        # per-column header_bar from its list (col_layout, below), so
        # leaving this at the same default keeps the header-to-table gap
        # identical between the two modes (2026-09-12, per the user's own
        # ask - a `setSpacing(0)` here previously made Sequential's gap
        # visibly tighter than Manual's).
        semi_table_layout.setContentsMargins(0, 0, 0, 0)

        # Header bar matching Manual's per-column ones (same frame style,
        # same margins so the two are the same height, same icon buttons)
        # but with no label - Sequential has no per-channel columns to
        # name (2026-09-11, per the user's own ask).
        semi_header_bar = QWidget()
        semi_header_bar.setAttribute(Qt.WA_StyledBackground, True)
        semi_header_bar.setStyleSheet(_CHANNEL_HEADER_BAR_STYLE)
        semi_header_bar.setFixedHeight(_HEADER_BAR_HEIGHT)
        semi_header_layout = QHBoxLayout(semi_header_bar)
        semi_header_layout.setContentsMargins(*_CHANNEL_HEADER_BAR_MARGINS)
        semi_header_layout.addStretch(1)
        self.semi_add_button = SvgToolButton("Global/photo-plus.svg")
        self.semi_add_button.clicked.connect(self._add_semi_files)
        self.semi_remove_button = SvgToolButton("Global/photo-minus.svg")
        self.semi_remove_button.clicked.connect(self._remove_semi_selected)
        self.semi_clear_button = SvgToolButton("Global/Reset.svg")
        self.semi_clear_button.clicked.connect(self._clear_semi)
        semi_header_layout.addWidget(self.semi_add_button)
        semi_header_layout.addWidget(self.semi_remove_button)
        semi_header_layout.addWidget(self.semi_clear_button)
        semi_header_layout.addStretch(1)
        semi_table_layout.addWidget(semi_header_bar)

        self.semi_list = _DropImageListWidget()
        self.semi_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        _apply_list_fixed_height(self.semi_list)
        self.semi_list.files_dropped.connect(self._add_semi_paths)
        self.semi_list.model().rowsInserted.connect(lambda *_a: self._refresh_semi_triplets())
        self.semi_list.model().rowsRemoved.connect(lambda *_a: self._refresh_semi_triplets())
        # Drag-to-reorder moves rows via moveRows(), which only emits
        # rowsMoved - not rowsInserted/rowsRemoved - so it must be watched
        # separately, otherwise a reorder silently keeps the stale triplets.
        self.semi_list.model().rowsMoved.connect(lambda *_a: self._refresh_semi_triplets())
        semi_table_layout.addWidget(self.semi_list)

        semi_layout.addWidget(semi_table_widget)

        self.semi_hint_label = QLabel()
        self.semi_hint_label.setWordWrap(True)
        self.semi_hint_label.setStyleSheet("color: #999; font-style: italic;")
        semi_layout.addWidget(self.semi_hint_label)
        input_layout.addWidget(self.semi_container)
        self.semi_container.setVisible(False)

        # --- manual mode UI ---
        self.manual_container = QWidget()
        self.manual_layout = manual_layout = QVBoxLayout(self.manual_container)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        # Each column is a header bar (channel label + its own Add/Remove/
        # Clear icon buttons, all one frame - 2026-09-11, per the user's
        # own ask to move the icons into the Red/Green/Blue boxes rather
        # than a separate button row below) directly above its list.
        # columns_row is still manual_layout's own single index-0 item
        # (added via addLayout), so _move_triplets_info_into's "insert at
        # index 1, right after the table" convention needs no change here.
        columns_row = QHBoxLayout()
        self.manual_lists: dict[str, QListWidget] = {}
        self.manual_column_labels: dict[str, QLabel] = {}
        self.manual_add_buttons: dict[str, SvgToolButton] = {}
        self.manual_remove_buttons: dict[str, SvgToolButton] = {}
        self.manual_clear_buttons: dict[str, SvgToolButton] = {}
        for letter in CHANNEL_LETTERS:
            col_widget = QWidget()
            col_layout = QVBoxLayout(col_widget)
            col_layout.setContentsMargins(0, 0, 0, 0)
            color = CHANNEL_COLORS.get(letter, "#888")

            header_bar = QWidget()
            header_bar.setAttribute(Qt.WA_StyledBackground, True)
            header_bar.setStyleSheet(_CHANNEL_HEADER_BAR_STYLE)
            header_bar.setFixedHeight(_HEADER_BAR_HEIGHT)
            header_layout = QHBoxLayout(header_bar)
            header_layout.setContentsMargins(*_CHANNEL_HEADER_BAR_MARGINS)
            label = QLabel()
            label.setStyleSheet(_CHANNEL_HEADER_LABEL_STYLE.format(color=color))
            header_layout.addWidget(label)
            header_layout.addStretch(1)
            add_btn = SvgToolButton("Global/photo-plus.svg")
            add_btn.clicked.connect(lambda _c=False, ch=letter: self._add_manual_files(ch))
            remove_btn = SvgToolButton("Global/photo-minus.svg")
            remove_btn.clicked.connect(lambda _c=False, ch=letter: self._remove_manual_selected(ch))
            clear_btn = SvgToolButton("Global/Reset.svg")
            clear_btn.clicked.connect(lambda _c=False, ch=letter: self._clear_manual(ch))
            header_layout.addWidget(add_btn)
            header_layout.addWidget(remove_btn)
            header_layout.addWidget(clear_btn)
            col_layout.addWidget(header_bar)

            lst = _DropImageListWidget()
            lst.setSelectionMode(QAbstractItemView.ExtendedSelection)
            _apply_list_fixed_height(lst)
            lst.model().rowsInserted.connect(lambda *_a: self._refresh_manual_triplets())
            lst.model().rowsRemoved.connect(lambda *_a: self._refresh_manual_triplets())
            # See the comment on the semi-automatic list: reordering by drag
            # only fires rowsMoved.
            lst.model().rowsMoved.connect(lambda *_a: self._refresh_manual_triplets())
            lst.files_dropped.connect(lambda paths, ch=letter: self._add_manual_paths(ch, paths))
            col_layout.addWidget(lst)
            columns_row.addWidget(col_widget)
            self.manual_lists[letter] = lst
            self.manual_column_labels[letter] = label
            self.manual_add_buttons[letter] = add_btn
            self.manual_remove_buttons[letter] = remove_btn
            self.manual_clear_buttons[letter] = clear_btn
        manual_layout.addLayout(columns_row)

        self.manual_hint_label = QLabel()
        self.manual_hint_label.setWordWrap(True)
        self.manual_hint_label.setStyleSheet("color: #999; font-style: italic;")
        manual_layout.addWidget(self.manual_hint_label)
        input_layout.addWidget(self.manual_container)
        self.manual_container.setVisible(False)

        # Matched-triplets count (left) and the unmatched-files summary
        # (right) share one line (2026-09-07, per the user's own "place
        # l'indication 'unmatched' sur la même ligne, justifié sur la
        # droite" spec). The unmatched summary went through 3 shapes the
        # same day: one wrapped QLabel showing "{n} unmatched files
        # (ignored): a.png, b.png, ..." all at once (comma-joined, could
        # grow very long); then a real QListWidget behind an explicit
        # "Show list" toggle button; then that same list revealed inline
        # on hover instead of a click; now a ListBubble popup on hover
        # (_UnmatchedSummaryLabel, same chrome as this app's "?" info
        # buttons) - "dans une fenêtre similaire à celle des boutons
        # infos." Used by all 3 modes (Automatic's own unmatched files;
        # Manual's leftover, unpaired files since 2026-09-11; Sequential's
        # own leftover remainder files since 2026-09-12 - see
        # _refresh_manual_triplets/_refresh_semi_triplets). A separate,
        # more detailed plain-text warning used to sit below this row for
        # Manual/Sequential (explaining *why*, e.g. mismatched column
        # counts) - removed 2026-09-12 per the user's own ask to show only
        # this one compact "unmatched files" indicator everywhere, same as
        # Automatic already did; that detailed wording is kept only in the
        # blocking validation alert `start_import()` shows on an actual
        # Import click with an invalid Sequential count, a genuinely
        # different, one-shot context.
        #
        # Bundled into its own widget (rather than added straight into
        # input_layout) so it can be reparented to sit directly below
        # whichever mode's table/list is currently active (2026-09-11, per
        # the user's own ask) - see _move_triplets_info_into, called from
        # _on_mode_changed/_build_ui/retranslate_ui - instead of always
        # sitting below all 3 (mutually-exclusive) mode containers, which
        # visually put it below whatever extra mode-specific controls
        # (the folder-path row, Import Rules, per-column buttons, hint
        # labels) happened to sit inside the active container too. Now
        # holding only triplets_row (a single fixed-height line), this
        # widget's own height no longer varies with content state at all -
        # a real, if secondary, contributor to the window-resize bug
        # fixed alongside this (see _fit_window_to_active_mode).
        self.triplets_info_widget = QWidget()
        triplets_info_layout = QVBoxLayout(self.triplets_info_widget)
        triplets_info_layout.setContentsMargins(0, 0, 0, 0)

        triplets_row = QHBoxLayout()
        self.triplets_label = QLabel()
        triplets_row.addWidget(self.triplets_label)
        triplets_row.addStretch(1)
        self.unmatched_summary_label = _UnmatchedSummaryLabel()
        self.unmatched_summary_label.setStyleSheet("color: #c99;")
        triplets_row.addWidget(self.unmatched_summary_label)
        self.unmatched_summary_label.setVisible(False)
        triplets_info_layout.addLayout(triplets_row)

        self._triplets_info_parent_layout = None

        root.addWidget(self.input_group)

        # --- Solo: a much simpler alternative to the triplet-matching UI
        # above, shown instead of input_group when Processing Mode is
        # Solo - see _on_processing_mode_changed. Reuses
        # _DropImageListWidget for the same drag-and-drop-from-Finder
        # convenience the manual per-channel lists already have.
        self.solo_group = QGroupBox()
        solo_layout = QVBoxLayout(self.solo_group)
        solo_btn_row = QHBoxLayout()
        self.solo_select_images_button = QPushButton()
        self.solo_select_images_button.clicked.connect(self._add_solo_images)
        self.solo_select_folder_button = QPushButton()
        self.solo_select_folder_button.clicked.connect(self._add_solo_folder)
        self.solo_clear_button = QPushButton()
        self.solo_clear_button.clicked.connect(self._clear_solo)
        solo_btn_row.addWidget(self.solo_select_images_button)
        solo_btn_row.addWidget(self.solo_select_folder_button)
        solo_btn_row.addWidget(self.solo_clear_button)
        solo_layout.addLayout(solo_btn_row)

        self.solo_list = _DropImageListWidget()
        self.solo_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        _apply_list_fixed_height(self.solo_list)
        self.solo_list.files_dropped.connect(self._add_solo_paths)
        self.solo_list.model().rowsInserted.connect(self._update_solo_count)
        self.solo_list.model().rowsRemoved.connect(self._update_solo_count)
        solo_layout.addWidget(self.solo_list)

        self.solo_count_label = QLabel()
        solo_layout.addWidget(self.solo_count_label)
        root.addWidget(self.solo_group)
        self.solo_group.setVisible(False)

        self.align_group = QGroupBox()
        align_layout = QVBoxLayout(self.align_group)
        self.auto_align_checkbox = QCheckBox()
        self.auto_align_checkbox.setChecked(True)
        self.auto_align_checkbox.toggled.connect(
            lambda checked: QSettings(ORG_NAME, APP_NAME).setValue("batch_auto_align", checked))
        align_layout.addWidget(self.auto_align_checkbox)
        root.addWidget(self.align_group)

        root.addStretch(1)

        import_row = QHBoxLayout()
        import_row.addStretch(1)
        self.add_button = QPushButton()
        self.add_button.setStyleSheet("font-weight: bold;")
        self.add_button.clicked.connect(self.start_import)
        import_row.addWidget(self.add_button)
        root.addLayout(import_row)

        self.setCentralWidget(central)

        # Connected only now that every widget _on_advanced_mode_changed
        # touches (triplets_label, table, mapping labels...) actually exists.
        for radio in self.advanced_mode_radios.values():
            radio.toggled.connect(lambda checked: self._on_advanced_mode_changed() if checked else None)

        # Applies the default Processing Mode's visibility now that every
        # widget it touches (input_group/solo_group/align_group) exists -
        # see the blockSignals note above.
        self._on_processing_mode_changed()

        # Places triplets_info_widget below Automatic's own table, matching
        # the default mode - _on_mode_changed (the mechanism that keeps it
        # correctly placed for the other 2 modes) never fires on its own at
        # startup, same "connected after setChecked" reasoning as above.
        self._move_triplets_info_into(self.auto_layout)

    def _restore_folder(self) -> None:
        settings = QSettings(ORG_NAME, APP_NAME)
        input_dir = settings.value("batch_input_dir", "")
        if input_dir and os.path.isdir(input_dir):
            self.input_path_edit.setText(input_dir)
            self.rescan()

    def _restore_last_settings(self) -> None:
        """Reopens the window on whatever Processing Mode/File Selection
        mode/Auto Align state the user last left it on (2026-09-11, per
        the user's own ask) - each is saved as it changes (see
        _on_processing_mode_changed, _on_mode_changed, and the
        auto_align_checkbox.toggled connection above), independent of the
        remembered input folder (_restore_folder) and of Import Rules'
        own filter/mapping settings (filters_module.registry, its own
        separate persistence). Runs after _build_ui() so every widget it
        touches already exists, and setChecked() here fires the normal
        (unblocked) toggled signal same as a real click would."""
        settings = QSettings(ORG_NAME, APP_NAME)
        processing_mode = settings.value("batch_last_processing_mode", "bw_trichrome")
        if processing_mode in self.processing_mode_radios:
            self.processing_mode_radios[processing_mode].setChecked(True)

        file_selection_mode = settings.value("batch_last_file_selection_mode", "auto")
        file_selection_radio = {
            "auto": self.mode_auto_radio, "semi": self.mode_semi_radio, "manual": self.mode_manual_radio,
        }.get(file_selection_mode)
        if file_selection_radio is not None:
            file_selection_radio.setChecked(True)

        self.auto_align_checkbox.setChecked(settings.value("batch_auto_align", True, type=bool))

    # ------------------------------------------------------------------
    def retranslate_ui(self) -> None:
        self.setWindowTitle(i18n.tr("batch_window_title"))
        self.processing_mode_group.setTitle(i18n.tr("batch_processing_mode_group"))
        for key in MODE_KEYS:
            # QRadioButton, unlike QComboBox's addItem, interprets a lone
            # "&" as a mnemonic accelerator (consuming it and underlining
            # the next letter instead of displaying it) - "&&" escapes it
            # to a literal ampersand, same convention already used for
            # scan_panel.py's "B&W" button label.
            self.processing_mode_radios[key].setText(i18n.tr(MODE_LABEL_KEYS[key]).replace("&", "&&"))
        self.solo_group.setTitle(i18n.tr("batch_input_group"))
        self.solo_select_images_button.setText(i18n.tr("batch_solo_select_images_button"))
        self.solo_select_folder_button.setText(i18n.tr("batch_solo_select_folder_button"))
        self.solo_clear_button.setText(i18n.tr("batch_manual_clear_button"))
        self._update_solo_count()
        self.input_group.setTitle(i18n.tr("batch_input_group"))
        self.mode_auto_radio.setText(i18n.tr("batch_mode_auto_radio"))
        self.mode_semi_radio.setText(i18n.tr("batch_mode_semi_radio"))
        self.mode_manual_radio.setText(i18n.tr("batch_mode_manual_radio"))

        self.semi_add_button.setToolTip(i18n.tr("batch_semi_select_button"))
        self.semi_remove_button.setToolTip(i18n.tr("batch_manual_remove_button"))
        self.semi_clear_button.setToolTip(i18n.tr("batch_manual_clear_button"))
        self.semi_hint_label.setText(i18n.tr("batch_semi_hint"))

        self.browse_input_button.setText(i18n.tr("batch_browse_button"))
        self.rescan_button.setText(i18n.tr("batch_rescan_button"))
        if not self.input_path_edit.text():
            self.input_path_edit.setPlaceholderText(i18n.tr("batch_no_folder"))
        for letter in CHANNEL_LETTERS:
            self.auto_column_labels[letter].setText(i18n.channel_name(letter))

        self.advanced_options_section.setTitle(i18n.tr("batch_advanced_options_title"))
        for mode_id in ADVANCED_MODE_IDS:
            self.advanced_mode_radios[mode_id].setText(i18n.tr(f"batch_advanced_mode_{mode_id}"))

        self.mapping_group.setTitle(i18n.tr("batch_channel_mapping_title"))
        self._refresh_mapping_combos()

        self.filters_group.setTitle(i18n.tr("batch_filters_title"))
        self.filters_table.setHorizontalHeaderLabels(
            [i18n.tr("batch_filters_name_header"), i18n.tr("batch_filters_tokens_header"), ""])
        self.add_filter_button.setText(i18n.tr("batch_filters_add_button"))
        self._refresh_filters_table()

        for letter in CHANNEL_LETTERS:
            self.manual_column_labels[letter].setText(i18n.channel_name(letter))
            self.manual_add_buttons[letter].setToolTip(i18n.tr("batch_manual_add_button"))
            self.manual_remove_buttons[letter].setToolTip(i18n.tr("batch_manual_remove_button"))
            self.manual_clear_buttons[letter].setToolTip(i18n.tr("batch_manual_clear_button"))
        self.manual_hint_label.setText(i18n.tr("batch_manual_hint"))

        self.align_group.setTitle(i18n.tr("alignment_group"))
        self.auto_align_checkbox.setText(i18n.tr("batch_align_auto_checkbox"))

        self.add_button.setText(i18n.tr("batch_import_button"))

        if self.mode_auto_radio.isChecked():
            self._update_triplets_label()
        elif self.mode_semi_radio.isChecked():
            self._set_unmatched_summary_visible(False)
            self._refresh_semi_triplets()
        else:
            self._set_unmatched_summary_visible(False)
            self._refresh_manual_triplets()

        self._fix_mode_container_widths()
        self._fit_window_to_active_mode()

    def _fit_window_to_active_mode(self) -> None:
        """Resizes this window to fit whichever mode container is
        currently visible, then fixes it there (so the user can't drag it
        to a size the fixed-size tables/headers inside can't use) until
        the next call revises it - unlike the padded, one-size-for-all
        approach this replaced, each mode now gets its own genuinely
        well-fitted size, and switching modes is a real, visible (but
        clean, single-step) resize rather than a static, oversized shape.
        Connected to Import Rules' own `toggled` signal too, in
        `_build_ui()`, so expanding/collapsing it - the one remaining
        dynamically-sized part of any container - resizes the window to
        match instead of clipping or leaving dead space.

        Reuses 2 hard-won fixes from an earlier version of this mechanism
        that padded every mode container to one shared size instead of
        letting the window itself adapt (reverted once the user pointed
        out the padded result was "disgracieux" - Manual/Sequential ended
        up with dead blank space just to match Automatic's own taller,
        Import-Rules-carrying footprint): `centralWidget().sizeHint()`,
        not `self.adjustSize()`+`self.size()` - confirmed directly that
        the latter is unreliable here (the exact same unchanged content,
        measured twice with nothing but a hide()/show() cycle in between,
        gave two different results, while centralWidget().sizeHint() gave
        the same value both times); and an explicit `invalidate()`/
        `activate()`/`processEvents()` sequence first, since a
        `setVisible()`/`setFixedSize()` change made moments earlier (the
        mode switch, or Import Rules expanding) posts a deferred
        `QEvent.LayoutRequest` up the widget tree rather than propagating
        synchronously - without forcing it to run first, sizeHint() can
        still reflect stale, pre-update geometry."""
        if not getattr(self, "_window_shown_once", False):
            return
        self.setMinimumSize(0, 0)
        self.setMaximumSize(_QWIDGETSIZE_MAX, _QWIDGETSIZE_MAX)
        central_layout = self.centralWidget().layout()
        central_layout.invalidate()
        central_layout.activate()
        QApplication.processEvents()
        self.setFixedSize(self.centralWidget().sizeHint())

    def _fix_mode_container_widths(self) -> None:
        """The window's own **width must stay constant regardless of
        mode** (2026-09-12, per the user's own explicit clarification -
        only the height should adapt per mode, never the width).

        Fixes the width of **input_group and solo_group themselves** -
        the 2 actual top-level siblings whose own width drives the
        window's rendered width - not the nested auto/semi/manual
        containers individually. An earlier version fixed those instead,
        using Manual's own measured *content* width - which excludes
        input_group's own QGroupBox border/padding, so applying that same
        raw number directly to solo_group (itself a QGroupBox, whose
        setFixedWidth *does* include its own border/padding) produced a
        visibly narrower Solo window than Automatic/Manual/Sequential's,
        a real, confirmed mismatch (798px vs 822px). Fixing input_group's
        own outer width instead sidesteps this entirely: whichever of
        auto/semi/manual is the visible child then simply stretches to
        fill it (a QVBoxLayout's normal behavior for an unconstrained
        child, needing no separate width fix on that child at all) -
        which is also *why* Sequential's own single list now visibly
        spans the same width as Automatic's/Manual's 3 columns combined,
        per the user's own ask, with no extra code specific to Sequential.

        Measures input_group's own natural width while Manual is its
        visible child (3 fixed-height/fixed-header columns - simpler to
        measure than Automatic's, which also carries the dynamically-
        toggleable Import Rules section, and naturally identical anyway
        since both are the same 3-column layout). Reuses the same
        isHidden()-based temporary-visibility trick as
        `_fit_window_to_active_mode` (see its own docstring for why) since
        this must be measured while genuinely visible to be accurate."""
        if not getattr(self, "_window_shown_once", False):
            return
        mode_containers = (self.auto_container, self.semi_container, self.manual_container)
        was_hidden = [container.isHidden() for container in mode_containers]
        was_input_group_hidden = self.input_group.isHidden()
        self.input_group.setMinimumWidth(0)
        self.input_group.setMaximumWidth(_QWIDGETSIZE_MAX)
        self.solo_group.setMinimumWidth(0)
        self.solo_group.setMaximumWidth(_QWIDGETSIZE_MAX)
        self.input_group.setVisible(True)
        for container in mode_containers:
            container.setVisible(container is self.manual_container)
        central_layout = self.centralWidget().layout()
        central_layout.invalidate()
        central_layout.activate()
        QApplication.processEvents()
        width = self.input_group.sizeHint().width()
        for container, hidden in zip(mode_containers, was_hidden):
            container.setVisible(not hidden)
        self.input_group.setVisible(not was_input_group_hidden)
        self.input_group.setFixedWidth(width)
        self.solo_group.setFixedWidth(width)

    def _set_unmatched_summary_visible(self, visible: bool) -> None:
        """Hides (or shows) the unmatched-files summary - used whenever
        switching away from (or back to) a mode, so a stale count/hover-
        bubble from a previous scan/edit can't linger visible under a
        different mode."""
        self.unmatched_summary_label.setVisible(visible)
        if not visible:
            self.unmatched_summary_label.close_bubble()

    def _update_triplets_label(self) -> None:
        self.triplets_label.setText(i18n.tr("batch_triplets_found", n=len(self.triplets)))
        if self.unmatched:
            self.unmatched_summary_label.setText(i18n.tr("batch_unmatched_label", n=len(self.unmatched)))
            self.unmatched_summary_label.items = list(self.unmatched)
            self.unmatched_summary_label.close_bubble()
            self.unmatched_summary_label.setVisible(True)
        else:
            self._set_unmatched_summary_visible(False)
            self.unmatched_summary_label.items = []

    # ------------------------------------------------------------------
    # Matching mode
    # ------------------------------------------------------------------
    def _make_info_button(self, info_key: str) -> InfoButton:
        return InfoButton(info_key)

    def _move_triplets_info_into(self, layout) -> None:
        """Reparents triplets_info_widget (the matched-triplets count +
        unmatched-files summary) into `layout`, right below its table/list
        section (index 1: index 0 is always that mode's own columns_row/
        table/list, added first) - see the comment where
        triplets_info_widget is built for why this needs to move at all.

        Real bug fixed here (2026-09-11): moving a widget from one
        container to another means Qt reparents it to a different parent
        *widget* under the hood (insertWidget -> addChildWidget ->
        setParent) - and QWidget.setParent() implicitly hides the widget
        as a side effect of reparenting, even though it was visible a
        moment ago. Without an explicit show() after every such move, the
        whole matched-triplets/unmatched-files summary silently vanished
        on every single mode switch away from Automatic (the very first
        one) - not just mispositioned, genuinely invisible - which is
        almost certainly what the user actually saw and reported."""
        if self._triplets_info_parent_layout is layout:
            return
        if self._triplets_info_parent_layout is not None:
            self._triplets_info_parent_layout.removeWidget(self.triplets_info_widget)
        layout.insertWidget(1, self.triplets_info_widget)
        self.triplets_info_widget.show()
        self._triplets_info_parent_layout = layout

    def _on_mode_changed(self) -> None:
        auto = self.mode_auto_radio.isChecked()
        semi = self.mode_semi_radio.isChecked()
        manual = self.mode_manual_radio.isChecked()
        self.auto_container.setVisible(auto)
        self.semi_container.setVisible(semi)
        self.manual_container.setVisible(manual)
        self._move_triplets_info_into(
            self.auto_layout if auto else self.semi_layout if semi else self.manual_layout)
        if auto:
            self._update_triplets_label()
        elif semi:
            self._set_unmatched_summary_visible(False)
            self._refresh_semi_triplets()
        else:
            self._set_unmatched_summary_visible(False)
            self._refresh_manual_triplets()
        self._fix_mode_container_widths()
        self._fit_window_to_active_mode()
        QSettings(ORG_NAME, APP_NAME).setValue(
            "batch_last_file_selection_mode", "auto" if auto else "semi" if semi else "manual")

    def _on_processing_mode_changed(self) -> None:
        """Solo has nothing to match into triplets and nothing to align -
        swaps input_group's whole triplet-matching UI (Auto/Semi/Manual,
        table, Advanced Options - all of it, unchanged) for the much
        simpler solo_group, and hides Auto Align entirely (align_group)
        since there are no channels to align in Solo mode."""
        is_solo = self.processing_mode_radios["solo"].isChecked()
        self.input_group.setVisible(not is_solo)
        self.solo_group.setVisible(is_solo)
        self.align_group.setVisible(not is_solo)
        self._fix_mode_container_widths()
        self._fit_window_to_active_mode()

    def _save_processing_mode_setting(self, key: str) -> None:
        """Separate from _on_processing_mode_changed (not merely folded
        into it) because that method is also called once, explicitly and
        unconditionally, at the end of _build_ui() to apply the default
        radio's visibility *before* _restore_last_settings() ever runs -
        a real bug, caught only by testing an actual restore round-trip
        (not just checking each write independently): saving from inside
        it clobbered a genuinely-restored non-default value (e.g. "solo")
        back to the hardcoded "bw_trichrome" default the moment the next
        BatchWindow was constructed, before restoration got a chance to
        read it. This one is wired directly to each radio's own toggled
        signal instead, which only fires on a real state change - never
        from that unconditional _build_ui() call."""
        QSettings(ORG_NAME, APP_NAME).setValue("batch_last_processing_mode", key)

    # ------------------------------------------------------------------
    # Solo mode
    # ------------------------------------------------------------------
    def _add_solo_images(self) -> None:
        settings = QSettings(ORG_NAME, APP_NAME)
        start_dir = settings.value("last_import_dir", "") or ""
        name_filter = f"Images ({imaging.qt_image_name_filter_patterns()});;" + i18n.tr("file_filter_all")
        paths, _ = QFileDialog.getOpenFileNames(
            self, i18n.tr("batch_solo_select_images_title"), start_dir, name_filter)
        if not paths:
            return
        settings.setValue("last_import_dir", os.path.dirname(paths[-1]))
        self._add_solo_paths(paths)

    def _add_solo_folder(self) -> None:
        settings = QSettings(ORG_NAME, APP_NAME)
        start_dir = settings.value("last_import_dir", "") or ""
        folder = QFileDialog.getExistingDirectory(self, i18n.tr("batch_solo_select_folder_title"), start_dir)
        if not folder:
            return
        settings.setValue("last_import_dir", folder)
        found = sorted(
            os.path.join(folder, name) for name in os.listdir(folder)
            if name.lower().endswith(IMAGE_EXTENSIONS) and os.path.isfile(os.path.join(folder, name)))
        self._add_solo_paths(found)

    def _add_solo_paths(self, paths: list[str]) -> None:
        for path in paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.solo_list.addItem(item)

    def _clear_solo(self) -> None:
        self.solo_list.clear()

    def _solo_paths(self) -> list[str]:
        return [self.solo_list.item(i).data(Qt.UserRole) for i in range(self.solo_list.count())]

    def _update_solo_count(self, *_args) -> None:
        self.solo_count_label.setText(i18n.tr("batch_solo_count", n=self.solo_list.count()))

    def _current_triplets(self) -> list:
        if self.mode_auto_radio.isChecked():
            return self.triplets
        if self.mode_semi_radio.isChecked():
            return self._semi_triplets
        return self._manual_triplets

    # ------------------------------------------------------------------
    # Automatic mode
    # ------------------------------------------------------------------
    def browse_input_folder(self) -> None:
        start = self.input_path_edit.text() or ""
        folder = QFileDialog.getExistingDirectory(self, i18n.tr("batch_select_input_title"), start)
        if not folder:
            return
        self.input_path_edit.setText(folder)
        QSettings(ORG_NAME, APP_NAME).setValue("batch_input_dir", folder)
        self.rescan()

    def rescan(self) -> None:
        folder = self.input_path_edit.text()
        if not folder or not os.path.isdir(folder):
            self.triplets, self.unmatched = [], []
        else:
            self.triplets, self.unmatched = batch.find_triplets(folder, mode=self._current_advanced_mode())
        self._populate_auto_lists()
        self._update_triplets_label()

    def _current_advanced_mode(self) -> str:
        for mode_id, radio in self.advanced_mode_radios.items():
            if radio.isChecked():
                return mode_id
        return "classic"

    def _on_advanced_mode_changed(self) -> None:
        self._refresh_mapping_combos()
        self.rescan()

    def _refresh_mapping_combos(self) -> None:
        mode = self._current_advanced_mode()
        is_custom = mode == "custom"
        channel_filters = batch.mode_channel_filters(mode)
        all_filters = filters_module.registry.list_filters()
        for channel, combo in self.mapping_combos.items():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("—", None)
            for f in all_filters:
                combo.addItem(f.name, f.id)
            target_id = channel_filters.get(channel)
            idx = combo.findData(target_id) if target_id else -1
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.setEnabled(is_custom)
            combo.blockSignals(False)

    def _on_mapping_combo_changed(self, channel: str) -> None:
        if self._current_advanced_mode() != "custom":
            return
        filter_id = self.mapping_combos[channel].currentData()
        filters_module.registry.set_custom_mapping(channel, filter_id)
        self.rescan()

    # ------------------------------------------------------------------
    # Filter definitions (Advanced Options)
    # ------------------------------------------------------------------
    def _refresh_filters_table(self) -> None:
        self.filters_table.blockSignals(True)
        defs = filters_module.registry.list_filters()
        self.filters_table.setRowCount(len(defs))
        for row, f in enumerate(defs):
            name_item = QTableWidgetItem(f.name)
            name_item.setData(Qt.UserRole, f.id)
            self.filters_table.setItem(row, 0, name_item)

            tokens_item = QTableWidgetItem(", ".join(f.tokens))
            tokens_item.setData(Qt.UserRole, f.id)
            self.filters_table.setItem(row, 1, tokens_item)

            if f.builtin:
                placeholder = QTableWidgetItem("")
                placeholder.setFlags(Qt.NoItemFlags)
                self.filters_table.setItem(row, 2, placeholder)
                self.filters_table.removeCellWidget(row, 2)
            else:
                delete_btn = QPushButton("×")
                delete_btn.setFixedWidth(28)
                delete_btn.setToolTip(i18n.tr("batch_filters_delete_tooltip"))
                delete_btn.clicked.connect(lambda _c=False, fid=f.id: self._delete_filter(fid))
                self.filters_table.setCellWidget(row, 2, delete_btn)
        self.filters_table.blockSignals(False)

    def _on_filter_item_changed(self, item: QTableWidgetItem) -> None:
        filter_id = item.data(Qt.UserRole)
        if not filter_id:
            return
        if item.column() == 0:
            name = item.text().strip()
            if not name:
                self._refresh_filters_table()
                return
            filters_module.registry.update_filter(filter_id, name=name)
        elif item.column() == 1:
            tokens = [t.strip() for t in item.text().split(",") if t.strip()]
            filters_module.registry.update_filter(filter_id, tokens=tokens)
        else:
            return
        self._refresh_filters_table()
        self._refresh_mapping_combos()
        self.rescan()

    def _add_filter(self) -> None:
        new_filter = filters_module.registry.add_filter(i18n.tr("batch_filters_new_name_placeholder"), [])
        self._refresh_filters_table()
        self._refresh_mapping_combos()
        for row in range(self.filters_table.rowCount()):
            item = self.filters_table.item(row, 0)
            if item and item.data(Qt.UserRole) == new_filter.id:
                self.filters_table.editItem(item)
                break

    def _delete_filter(self, filter_id: str) -> None:
        filters_module.registry.remove_filter(filter_id)
        self._refresh_filters_table()
        self._refresh_mapping_combos()
        self.rescan()

    def _populate_auto_lists(self) -> None:
        for channel in CHANNEL_LETTERS:
            lst = self.auto_lists[channel]
            lst.clear()
            for triplet in self.triplets:
                name = os.path.basename(triplet.paths[channel])
                item = QListWidgetItem(name)
                item.setToolTip(triplet.paths[channel])
                lst.addItem(item)

    # ------------------------------------------------------------------
    # Manual mode
    # ------------------------------------------------------------------
    def _add_manual_files(self, channel: str) -> None:
        settings = QSettings(ORG_NAME, APP_NAME)
        start_dir = settings.value("last_import_dir", "") or self.input_path_edit.text() or ""
        name_filter = f"Images ({imaging.qt_image_name_filter_patterns()});;" + i18n.tr("file_filter_all")
        paths, _ = QFileDialog.getOpenFileNames(
            self, i18n.tr("batch_select_files_title", channel=i18n.channel_name(channel)), start_dir, name_filter)
        if not paths:
            return
        self._add_manual_paths(channel, paths)

    def _add_manual_paths(self, channel: str, paths: list[str]) -> None:
        if not paths:
            return
        lst = self.manual_lists[channel]
        for path in paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            lst.addItem(item)
        QSettings(ORG_NAME, APP_NAME).setValue("last_import_dir", os.path.dirname(paths[-1]))
        self._refresh_manual_triplets()

    def _remove_manual_selected(self, channel: str) -> None:
        lst = self.manual_lists[channel]
        for item in lst.selectedItems():
            lst.takeItem(lst.row(item))
        self._refresh_manual_triplets()

    def _clear_manual(self, channel: str) -> None:
        self.manual_lists[channel].clear()
        self._refresh_manual_triplets()

    def _manual_paths(self, channel: str) -> list[str]:
        lst = self.manual_lists[channel]
        return [lst.item(i).data(Qt.UserRole) for i in range(lst.count())]

    def _ref_letter(self) -> str:
        ref = self.main_window._reference_layer()
        return CHANNEL_LETTERS[ref.color_index]

    def _refresh_manual_triplets(self, *_args) -> None:
        r_paths = self._manual_paths("R")
        g_paths = self._manual_paths("G")
        b_paths = self._manual_paths("B")
        self._manual_triplets = batch.build_manual_triplets(r_paths, g_paths, b_paths, self._ref_letter())

        if self.mode_manual_radio.isChecked():
            self.triplets_label.setText(i18n.tr("batch_triplets_found", n=len(self._manual_triplets)))

            # A row past the shortest column has fewer than 3 photos and
            # so never became a triplet - flag those leftover files the
            # same way Automatic mode flags its own unmatched files (same
            # i18n string, same hover-list summary), per the user's own
            # 2026-09-11 ask. A separate, more detailed plain-text warning
            # (mismatched column counts) used to show here too - removed
            # 2026-09-12 per the user's own ask to show just this one
            # compact indicator, same as every other mode.
            n = len(self._manual_triplets)
            leftover = [os.path.basename(p) for p in r_paths[n:] + g_paths[n:] + b_paths[n:]]
            if leftover:
                self.unmatched_summary_label.setText(i18n.tr("batch_unmatched_label", n=len(leftover)))
                self.unmatched_summary_label.items = leftover
                self.unmatched_summary_label.close_bubble()
                self._set_unmatched_summary_visible(True)
            else:
                self._set_unmatched_summary_visible(False)
                self.unmatched_summary_label.items = []

    # ------------------------------------------------------------------
    # Semi-automatic mode
    # ------------------------------------------------------------------
    def _add_semi_files(self) -> None:
        settings = QSettings(ORG_NAME, APP_NAME)
        start_dir = settings.value("last_import_dir", "") or self.input_path_edit.text() or ""
        name_filter = f"Images ({imaging.qt_image_name_filter_patterns()});;" + i18n.tr("file_filter_all")
        paths, _ = QFileDialog.getOpenFileNames(
            self, i18n.tr("batch_semi_select_title"), start_dir, name_filter)
        if not paths:
            return
        self._add_semi_paths(paths)

    def _add_semi_paths(self, paths: list[str]) -> None:
        if not paths:
            return
        for path in paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.semi_list.addItem(item)
        QSettings(ORG_NAME, APP_NAME).setValue("last_import_dir", os.path.dirname(paths[-1]))
        self._refresh_semi_triplets()

    def _remove_semi_selected(self) -> None:
        for item in self.semi_list.selectedItems():
            self.semi_list.takeItem(self.semi_list.row(item))
        self._refresh_semi_triplets()

    def _clear_semi(self) -> None:
        self.semi_list.clear()
        self._refresh_semi_triplets()

    def _semi_paths(self) -> list[str]:
        return [self.semi_list.item(i).data(Qt.UserRole) for i in range(self.semi_list.count())]

    _SEMI_ITEM_ICON_SIZE = 16

    def _channel_icon_for_index(self, index: int) -> QIcon:
        """The colored circle-letter glyph (same icon family used by
        ModeSwitchDialog/Histogram/Curves) for whichever channel a
        Sequential-mode list position maps to - build_semiauto_triplets
        always consumes files 3-at-a-time in a fixed R,G,B,R,G,B... order
        regardless of the reference-channel choice, so `index % 3` is the
        same mapping it already relies on."""
        letter = CHANNEL_LETTERS[index % 3]
        color = QColor(CHANNEL_COLORS.get(letter, "#888"))
        dpr = self.devicePixelRatioF() or 1.0
        return tinted_svg_icon(f"Global/circle-letter-{letter.lower()}.svg", self._SEMI_ITEM_ICON_SIZE, color, dpr)

    def _refresh_semi_icons(self) -> None:
        """Re-stamps every item's R/G/B icon from its current position
        (2026-09-11, per the user's own ask) - needs a full pass, not just
        on newly-added items, since a drag-reorder changes which channel
        every subsequent item maps to."""
        for i in range(self.semi_list.count()):
            self.semi_list.item(i).setIcon(self._channel_icon_for_index(i))

    def _refresh_semi_triplets(self, *_args) -> None:
        self._refresh_semi_icons()
        paths = self._semi_paths()
        self._semi_triplets = batch.build_semiauto_triplets(paths, self._ref_letter())

        if self.mode_semi_radio.isChecked():
            self.triplets_label.setText(i18n.tr("batch_triplets_found", n=len(self._semi_triplets)))
            # Trailing files past the last full triplet never got grouped -
            # flag them the same compact way every other mode's own
            # leftover/unmatched files are flagged (2026-09-12, per the
            # user's own ask - replacing a more detailed plain-text count
            # breakdown that used to show here; that detailed wording is
            # kept only in start_import()'s blocking validation alert for
            # an actual Import click with an invalid count).
            remainder = len(paths) % 3
            leftover = [os.path.basename(p) for p in paths[-remainder:]] if remainder else []
            if leftover:
                self.unmatched_summary_label.setText(i18n.tr("batch_unmatched_label", n=len(leftover)))
                self.unmatched_summary_label.items = leftover
                self.unmatched_summary_label.close_bubble()
                self._set_unmatched_summary_visible(True)
            else:
                self._set_unmatched_summary_visible(False)
                self.unmatched_summary_label.items = []

    # ------------------------------------------------------------------
    # Confirm & hand off to the main window
    # ------------------------------------------------------------------
    def start_import(self) -> None:
        if self.processing_mode_radios["solo"].isChecked():
            paths = self._solo_paths()
            if not paths:
                show_alert(self, i18n.tr("batch_window_title"), i18n.tr("batch_solo_no_photos"))
                return
            # Same "build a fresh Solo BatchItem per path, load what you
            # can, report the rest" flow Finder drag-and-drop already
            # uses on the main carousel - no separate Solo-import method
            # needed on MainWindow.
            self.main_window.on_carousel_files_dropped(paths)
            self.close()
            return

        auto_mode = self.mode_auto_radio.isChecked()
        semi_mode = self.mode_semi_radio.isChecked()
        if auto_mode and not self.input_path_edit.text():
            show_alert(self, i18n.tr("batch_window_title"), i18n.tr("batch_error_no_input"))
            return
        if semi_mode:
            paths = self._semi_paths()
            remainder = len(paths) % 3
            if paths and remainder != 0:
                show_alert(self, i18n.tr("batch_window_title"),
                                     i18n.tr("batch_semi_invalid_count", n=len(paths), remainder=remainder))
                return
        triplets = self._current_triplets()
        if not triplets:
            show_alert(self, i18n.tr("batch_window_title"), i18n.tr("batch_status_no_triplets"))
            return

        self.main_window.start_batch_import(
            triplets=triplets,
            ref_letter=self._ref_letter(),
            auto_align=self.auto_align_checkbox.isChecked(),
            replace=False,
            harris_shutter=self.processing_mode_radios["color_trichrome"].isChecked(),
        )
        self.close()
