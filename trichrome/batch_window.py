"""Batch Import: pick a set of R/G/B triplets and import them into the main
session as independent, individually-editable photos (see MainWindow's
carousel). Export itself now happens from the main window's Export dialog."""
from __future__ import annotations

import os

from PySide6.QtCore import QSize, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QPushButton, QRadioButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import batch, filters as filters_module, i18n, imaging
from .widgets.alert_dialog import show_alert
from .widgets.channel_panel import CHANNEL_COLORS
from .widgets.controls import CollapsibleSection
from .widgets.import_panel import MODE_ICONS, MODE_KEYS, MODE_LABEL_KEYS
from .widgets.info_bubble import InfoButton, show_list_bubble
from .widgets.svg_icons import raw_svg_icon

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

        self._build_ui()
        self._restore_folder()
        self.retranslate_ui()
        QShortcut(QKeySequence.Close, self, activated=self.close)

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

        # --- Processing Mode: Solo / B&W Trichrome / Color Trichrome -
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
        auto_layout = QVBoxLayout(self.auto_container)
        auto_layout.setContentsMargins(0, 0, 0, 0)
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

        self.table = QTableWidget(0, 4)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setHorizontalHeaderLabels(["#", "R", "G", "B"])
        self.table.setColumnWidth(0, 40)
        auto_layout.addWidget(self.table)

        # --- advanced options (automatic mode only): channel-swap presets
        # for infrared/aerochrome-style trichromes where the R/G/B filters
        # don't map 1:1 to the R/G/B digital channels.
        self.advanced_options_section = CollapsibleSection()
        self.advanced_options_section.toggle_button.setStyleSheet(
            "QToolButton { border: none; font-weight: bold; font-size: 13px; text-align: left; "
            "background: rgba(120, 150, 220, 45); border-radius: 4px; padding: 5px 8px; }"
        )
        # A second "?" button, in the app's accent blue, sits right next to
        # the section's own disclosure title (added 2026-09-08) - a general
        # explanation of what this whole section is for, distinct from the
        # per-rule breakdown below.
        self.auto_import_rules_info_button = InfoButton(
            "batch_auto_import_rules_info", color="#5b9bd5")
        self.advanced_options_section.header_row.addWidget(self.auto_import_rules_info_button)
        self.advanced_mode_radios: dict[str, QRadioButton] = {}
        mode_row2 = QHBoxLayout()
        for mode_id in ADVANCED_MODE_IDS:
            radio = QRadioButton()
            mode_row2.addWidget(radio)
            self.advanced_mode_radios[mode_id] = radio
        # "?" info button explaining the 4 rules themselves (Classic/IR/
        # Aerochrome/Custom) - sits right next to the 4 choices it
        # describes, not the section title (moved here 2026-09-08,
        # originally lived in the header row next to the title instead).
        self.advanced_options_info_button = InfoButton("batch_advanced_options_info")
        mode_row2.addWidget(self.advanced_options_info_button)
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

        input_layout.addWidget(self.auto_container)

        # --- semi-automatic mode UI ---
        self.semi_container = QWidget()
        semi_layout = QVBoxLayout(self.semi_container)
        semi_layout.setContentsMargins(0, 0, 0, 0)

        self.semi_list = QListWidget()
        self.semi_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.semi_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.semi_list.model().rowsInserted.connect(lambda *_a: self._refresh_semi_triplets())
        self.semi_list.model().rowsRemoved.connect(lambda *_a: self._refresh_semi_triplets())
        # Drag-to-reorder moves rows via moveRows(), which only emits
        # rowsMoved - not rowsInserted/rowsRemoved - so it must be watched
        # separately, otherwise a reorder silently keeps the stale triplets.
        self.semi_list.model().rowsMoved.connect(lambda *_a: self._refresh_semi_triplets())
        semi_layout.addWidget(self.semi_list)

        semi_btn_row = QHBoxLayout()
        self.semi_add_button = QPushButton()
        self.semi_add_button.clicked.connect(self._add_semi_files)
        self.semi_remove_button = QPushButton()
        self.semi_remove_button.clicked.connect(self._remove_semi_selected)
        self.semi_clear_button = QPushButton()
        self.semi_clear_button.clicked.connect(self._clear_semi)
        semi_btn_row.addWidget(self.semi_add_button)
        semi_btn_row.addWidget(self.semi_remove_button)
        semi_btn_row.addWidget(self.semi_clear_button)
        semi_layout.addLayout(semi_btn_row)

        self.semi_hint_label = QLabel()
        self.semi_hint_label.setWordWrap(True)
        self.semi_hint_label.setStyleSheet("color: #999; font-style: italic;")
        semi_layout.addWidget(self.semi_hint_label)
        input_layout.addWidget(self.semi_container)
        self.semi_container.setVisible(False)

        # --- manual mode UI ---
        self.manual_container = QWidget()
        manual_layout = QVBoxLayout(self.manual_container)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        columns_row = QHBoxLayout()
        self.manual_lists: dict[str, QListWidget] = {}
        self.manual_column_labels: dict[str, QLabel] = {}
        self.manual_add_buttons: dict[str, QPushButton] = {}
        self.manual_remove_buttons: dict[str, QPushButton] = {}
        self.manual_clear_buttons: dict[str, QPushButton] = {}
        for letter in CHANNEL_LETTERS:
            col_widget = QWidget()
            col_layout = QVBoxLayout(col_widget)
            col_layout.setContentsMargins(0, 0, 0, 0)
            color = CHANNEL_COLORS.get(letter, "#888")
            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(f"color: {color}; font-weight: bold;")
            col_layout.addWidget(label)

            lst = _DropImageListWidget()
            lst.setSelectionMode(QAbstractItemView.ExtendedSelection)
            lst.model().rowsInserted.connect(lambda *_a: self._refresh_manual_triplets())
            lst.model().rowsRemoved.connect(lambda *_a: self._refresh_manual_triplets())
            # See the comment on the semi-automatic list: reordering by drag
            # only fires rowsMoved.
            lst.model().rowsMoved.connect(lambda *_a: self._refresh_manual_triplets())
            lst.files_dropped.connect(lambda paths, ch=letter: self._add_manual_paths(ch, paths))
            col_layout.addWidget(lst)

            btn_row = QHBoxLayout()
            add_btn = QPushButton()
            add_btn.clicked.connect(lambda _c=False, ch=letter: self._add_manual_files(ch))
            remove_btn = QPushButton()
            remove_btn.clicked.connect(lambda _c=False, ch=letter: self._remove_manual_selected(ch))
            clear_btn = QPushButton()
            clear_btn.clicked.connect(lambda _c=False, ch=letter: self._clear_manual(ch))
            btn_row.addWidget(add_btn)
            btn_row.addWidget(remove_btn)
            btn_row.addWidget(clear_btn)
            col_layout.addLayout(btn_row)

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

        # Matched-triplets count (left) and Automatic mode's own
        # unmatched-files summary (right) share one line (2026-09-07, per
        # the user's own "place l'indication 'unmatched' sur la même
        # ligne, justifié sur la droite" spec). The unmatched summary went
        # through 3 shapes the same day: one wrapped QLabel showing
        # "{n} unmatched files (ignored): a.png, b.png, ..." all at once
        # (comma-joined, could grow very long); then a real QListWidget
        # behind an explicit "Show list" toggle button; then that same
        # list revealed inline on hover instead of a click; now a
        # ListBubble popup on hover (_UnmatchedSummaryLabel, same chrome
        # as this app's "?" info buttons) - "dans une fenêtre similaire à
        # celle des boutons infos." Kept separate from unmatched_label
        # below (the Manual/Semi-automatic mismatch warnings, which are
        # single-line text, not a file list, so they keep their original
        # plain-label treatment on their own line, unchanged).
        triplets_row = QHBoxLayout()
        self.triplets_label = QLabel()
        triplets_row.addWidget(self.triplets_label)
        triplets_row.addStretch(1)
        self.unmatched_summary_label = _UnmatchedSummaryLabel()
        self.unmatched_summary_label.setStyleSheet("color: #c99;")
        triplets_row.addWidget(self.unmatched_summary_label)
        self.unmatched_summary_label.setVisible(False)
        input_layout.addLayout(triplets_row)

        self.unmatched_label = QLabel()
        self.unmatched_label.setWordWrap(True)
        self.unmatched_label.setStyleSheet("color: #c99;")
        input_layout.addWidget(self.unmatched_label)

        # Advanced Options lives below the (shared) triplet count on purpose,
        # and only makes sense for the Automatic matcher.
        input_layout.addWidget(self.advanced_options_section)

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

    def _restore_folder(self) -> None:
        settings = QSettings(ORG_NAME, APP_NAME)
        input_dir = settings.value("batch_input_dir", "")
        if input_dir and os.path.isdir(input_dir):
            self.input_path_edit.setText(input_dir)
            self.rescan()

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
        self.solo_group.setTitle(i18n.tr("batch_solo_group"))
        self.solo_select_images_button.setText(i18n.tr("batch_solo_select_images_button"))
        self.solo_select_folder_button.setText(i18n.tr("batch_solo_select_folder_button"))
        self.solo_clear_button.setText(i18n.tr("batch_manual_clear_button"))
        self._update_solo_count()
        self.input_group.setTitle(i18n.tr("batch_input_group"))
        self.mode_auto_radio.setText(i18n.tr("batch_mode_auto_radio"))
        self.mode_semi_radio.setText(i18n.tr("batch_mode_semi_radio"))
        self.mode_manual_radio.setText(i18n.tr("batch_mode_manual_radio"))

        self.semi_add_button.setText(i18n.tr("batch_semi_select_button"))
        self.semi_remove_button.setText(i18n.tr("batch_manual_remove_button"))
        self.semi_clear_button.setText(i18n.tr("batch_manual_clear_button"))
        self.semi_hint_label.setText(i18n.tr("batch_semi_hint"))

        self.browse_input_button.setText(i18n.tr("batch_browse_button"))
        self.rescan_button.setText(i18n.tr("batch_rescan_button"))
        if not self.input_path_edit.text():
            self.input_path_edit.setPlaceholderText(i18n.tr("batch_no_folder"))
        self.table.setHorizontalHeaderLabels(["#", "R", "G", "B"])

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
            self.manual_add_buttons[letter].setText(i18n.tr("batch_manual_add_button"))
            self.manual_remove_buttons[letter].setText(i18n.tr("batch_manual_remove_button"))
            self.manual_clear_buttons[letter].setText(i18n.tr("batch_manual_clear_button"))
        self.manual_hint_label.setText(i18n.tr("batch_manual_hint"))

        self.align_group.setTitle(i18n.tr("alignment_group"))
        self.auto_align_checkbox.setText(i18n.tr("batch_align_auto_checkbox"))

        self.add_button.setText(i18n.tr("batch_import_button"))

        if self.mode_auto_radio.isChecked():
            self.unmatched_label.setVisible(False)
            self._update_triplets_label()
        elif self.mode_semi_radio.isChecked():
            self._set_unmatched_summary_visible(False)
            self._refresh_semi_triplets()
        else:
            self._set_unmatched_summary_visible(False)
            self._refresh_manual_triplets()

    def _set_unmatched_summary_visible(self, visible: bool) -> None:
        """Hides (or shows) the Automatic-mode unmatched-files summary -
        used whenever switching away from (or back to) Automatic mode, so
        a stale count/hover-bubble from a previous scan can't linger
        visible under Manual/Semi-automatic, which have their own
        separate unmatched_label warning instead."""
        self.unmatched_summary_label.setVisible(visible)
        if not visible:
            self.unmatched_summary_label.close_bubble()

    def _update_triplets_label(self) -> None:
        self.triplets_label.setText(i18n.tr("batch_triplets_found", n=len(self.triplets)))
        self.unmatched_label.setVisible(False)
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

    def _on_mode_changed(self) -> None:
        auto = self.mode_auto_radio.isChecked()
        semi = self.mode_semi_radio.isChecked()
        manual = self.mode_manual_radio.isChecked()
        self.auto_container.setVisible(auto)
        self.semi_container.setVisible(semi)
        self.manual_container.setVisible(manual)
        if auto:
            self.unmatched_label.setVisible(False)
            self._update_triplets_label()
        elif semi:
            self._set_unmatched_summary_visible(False)
            self._refresh_semi_triplets()
        else:
            self._set_unmatched_summary_visible(False)
            self._refresh_manual_triplets()

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
        self._populate_table()
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

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self.triplets))
        for row, triplet in enumerate(self.triplets):
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            for col, channel in enumerate(CHANNEL_LETTERS, start=1):
                name = os.path.basename(triplet.paths[channel])
                self.table.setItem(row, col, QTableWidgetItem(name))

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
            counts = {len(r_paths), len(g_paths), len(b_paths)}
            if len(counts) > 1:
                self.unmatched_label.setText(i18n.tr(
                    "batch_manual_mismatch_warning", r=len(r_paths), g=len(g_paths), b=len(b_paths),
                    n=len(self._manual_triplets)))
                self.unmatched_label.setVisible(True)
            else:
                self.unmatched_label.setVisible(False)

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
        for path in paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.semi_list.addItem(item)
        settings.setValue("last_import_dir", os.path.dirname(paths[-1]))
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

    def _refresh_semi_triplets(self, *_args) -> None:
        paths = self._semi_paths()
        self._semi_triplets = batch.build_semiauto_triplets(paths, self._ref_letter())

        if self.mode_semi_radio.isChecked():
            self.triplets_label.setText(i18n.tr("batch_triplets_found", n=len(self._semi_triplets)))
            remainder = len(paths) % 3
            if remainder != 0:
                self.unmatched_label.setText(
                    i18n.tr("batch_semi_invalid_count", n=len(paths), remainder=remainder))
                self.unmatched_label.setVisible(True)
            else:
                self.unmatched_label.setVisible(False)

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
