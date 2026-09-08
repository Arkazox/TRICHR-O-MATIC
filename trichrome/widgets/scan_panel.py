"""Scan tool block - the integrated version of the standalone
trichrome.scan_tool package (2026-09-04), wrapped in the same block chrome
(grip/title/collapse/close) as every other tool block. All the actual
capture/device logic is imported straight from trichrome.scan_tool rather
than re-implemented here - gphoto_backend, manifest, naming, CaptureWorker,
BacklightWindow, and the MODES/light-mode/RGB-sequence constants are the
exact same tested code the standalone tool uses, kept alive at
trichrome/scan_tool/ for separate beta testing per the user's explicit
request ("Don't delete the standalone scan tool yet, we'll keep it for
later betatesting"). Only the UI *shell* is different: the standalone tool
builds its own top-level QWidget with plain QGroupBox sections; this class
builds the same sections directly into a block's body_layout, separated by
thin hairlines instead of nested group-box borders (redundant once
everything already lives inside one block's own border) - and shares the
exact same QSettings domain (scan_tool.scan_window.ORG_NAME/APP_NAME) so
roll name/counter/folder state stays consistent regardless of which one you
actually run.

Every successful capture is added to the main session/carousel
automatically (added 2026-09-04, superseding the original manual "Captured
this session" history list + "Add to Current Session" button - the user
asked to drop the intermediate list entirely). `_finish_capture` still
emits `add_to_session_requested` internally, right after logging to
`manifest.append_entry` - MainWindow owns the actual BatchItem construction
(imaging/model.py), same "panel emits, MainWindow builds" split as
import_panel.py's load_normal_requested. The standalone tool's own
history list + "Add to Current Session" button are
untouched - it has no MainWindow to hand off to, and keeps its own
original UI. The standalone tool's optional "processed JPG preview"
(process.py/ProcessWorker) was deliberately dropped from this integrated
panel per the user's request (2026-09-04) - it's still available in the
standalone tool.

"Sample Film Base" (added 2026-09-04) is the one narrow exception to
"this panel never imports imaging.py" above: it needs the mean pixel
value of 3 quick calibration shots (a lightweight scalar summary, not
image manipulation or BatchItem construction) to know what to attach to
a later Add-to-Session request - see its own section in CLAUDE.md for the
full rationale (why RGB-Light-scanned color negatives need this, and why
a plain white-balance pick isn't enough) and the actual per-channel
correction math, which still lives in MainWindow
(_build_trichrome_batch_item_from_paths), not here. The alternative
eyedropper way to set the same reference - clicking a point on an
already-scanned photo already in the session, instead of running a
dedicated 3-shot calibration capture - lives mostly in MainWindow
(on_film_base_pick_requested), for the same reason: it needs to warp/read
BatchItem channel data, which this panel doesn't otherwise touch."""
from __future__ import annotations

import os
import shutil
import tempfile

from PySide6.QtCore import QSettings, QSize, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QLinearGradient, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QSpinBox, QWidget,
)

from .. import i18n, imaging
from ..scan_tool import gphoto_backend, manifest, naming
from ..scan_tool import scan_window
from ..scan_tool.capture_worker import CaptureWorker
from ..scan_tool.scan_window import (
    _LIGHT_MODE_KEYS, _LIGHT_SETTLE_DELAY_MS, _POLL_INTERVAL_MS, _RGB_CHANNEL_COLORS,
    _RGB_SEQUENCE, MODES, BacklightWindow,
)

# Deliberately read as scan_window.ORG_NAME/.APP_NAME at the point of use
# (__init__ below), not imported as bare names - a bare `from ... import
# ORG_NAME` would bind an independent copy in *this* module's namespace,
# so a headless test patching scan_window.ORG_NAME for isolation (the
# documented pattern - see CLAUDE.md/the QSettings-isolation memory) would
# silently fail to isolate this class too. Keeping one canonical
# attribute lookup means patching scan_window.ORG_NAME/.APP_NAME isolates
# both the standalone tool and this integrated panel at once.
from .alert_dialog import show_alert
from .block_header_bar import (
    DISABLED_MESSAGE_STYLE, finish_block_chrome, start_block_chrome,
)
from .controls import CollapsibleSection
from .svg_icons import (
    SvgCheckableToolButton, SvgToolButton, gradient_tinted_svg_icon, tinted_svg_icon,
)

# Muted, small-caps-weight label for a section inside the block - since the
# whole Scan tool already lives inside one block's own bordered chrome,
# nested QGroupBox sections (each with their own border/title) were
# redundant visual noise; a plain label plus a hairline (see _make_hairline
# below) reads as a section break without adding another border.
_SECTION_LABEL_STYLE = "font-weight: 600; color: #9a9a9a; font-size: 11px;"

# Each of the 4 sections below (Device/Film/Scan Light/Save Location) is a
# plain controls.CollapsibleSection (2026-09-08, "ajoute la possibilité de
# masquer les sous blocs") rather than a new custom widget - it's already
# borderless by default (confirmed by reading its own source: no frame/
# QSS is applied unless a caller adds one, e.g. ChannelPanel's
# align_box/tone_box do, batch_window.py's advanced_options_section
# doesn't), so reusing it here doesn't reintroduce the nested-border
# visual noise this panel's flat, hairline-divided convention was built
# to avoid - only its own toggle_button needed restyling, to match this
# panel's established muted small-caps header look instead of
# CollapsibleSection's own bold default.
_SECTION_TOGGLE_STYLE = f"QToolButton {{ border: none; text-align: left; {_SECTION_LABEL_STYLE} }}"


def _make_hairline() -> QWidget:
    line = QWidget()
    line.setFixedHeight(1)
    line.setStyleSheet("background-color: rgba(255, 255, 255, 28);")
    return line


# Both button rows below (Film: 3 buttons, Scan Light: 3 buttons) must fit
# side by side inside the narrowest allowed side panel (_SIDE_PANEL_MIN_WIDTH
# in main_window.py, 360px, minus the block's own chrome margins) - the
# panel's width must adapt to whichever side it's dragged into, not the
# other way around (2026-09-04 feedback: "le bloc doit s'adapter en largeur
# à la taille du panel latéral, quitte à réduire légèrement les boutons").
# Both rows now use the same framed/icon-left QRadioButton look as the Batch
# Import window's own Processing Mode row (added 2026-09-08, per the user's
# explicit "utilise le même style... encadré, icone à gauche") - same
# accent-blue checked frame (#5b9bd5), hidden native indicator, just tighter
# padding/font than that row's own style to still fit 3 real-text buttons
# (worst case "Color Reversal"/"Couleur Inversible") in this narrower panel.
_FRAMED_MODE_BUTTON_STYLE = """
QRadioButton {
    border: 2px solid transparent;
    border-radius: 5px;
    padding: 3px 5px;
    font-size: 11px;
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
_MODE_BUTTON_ICON_SIZE = 16

# One icon (Tools/Scan/camera_roll.svg) reused for all 3 Film buttons, tinted a
# different fixed color per film type instead of the app's usual single
# palette-driven tint - the color itself is the primary visual cue for
# which film type is selected (2026-09-08, exact colors given by the
# user): white for B&W, orange for Color, blue for Color Reversal. Order
# matches MODES exactly (bw, color, color_reversal).
_FILM_ICON_COLORS = ("#ffffff", "#e67e22", "#5b9bd5")

# Per-mode note text below the Film row (2026-09-08), keyed by MODES' own
# mode key - states exactly what _auto_add_to_session actually applies
# automatically on import for that film type (invert, and for B&W, a real
# Black & White conversion too - see GlobalCorrection.black_white_active).
_MODE_NOTE_KEYS = {
    "bw": "scan_mode_note_bw",
    "color": "scan_mode_note_color",
    "color_reversal": "scan_mode_note_color_reversal",
}

# Scan Light's own 3 modes (External/White/RGB), 2026-09-08: External gets
# the Sun Light glyph (a plain external light source, as opposed to the
# on-screen backlight the other 2 modes use); White keeps the plain
# light-bulb glyph, white; RGB also keeps the light-bulb glyph but banded
# red/green/blue top-to-bottom (via gradient_tinted_svg_icon) so it reads
# as "RGB" while staying recognizably the same bulb shape as White's - a
# tri-color Scan/rainbow-rgb.svg glyph was tried instead the same day but
# the user preferred this banded-bulb version once they'd seen both, so
# it was kept/reverted to rather than the rainbow.
_EXTERNAL_LIGHT_ICON = "Tools/Scan/sun-light.svg"
_WHITE_LIGHT_ICON = "Tools/Scan/light-bulb.svg"
_RGB_LIGHT_ICON = "Tools/Scan/light-bulb.svg"
_LIGHT_ICON_COLOR = "#ffffff"

# One full spin over 1 second when the Refresh button is clicked - timer-
# driven (SvgToolButton.set_rotation() is a plain method, not a Qt
# `Property`, so it isn't a QPropertyAnimation target) at a plain 60fps tick,
# matching this codebase's other 60Hz-timer precedent (the Curves tool's
# drag-recompute throttle).
_REFRESH_SPIN_DURATION_MS = 1000
_REFRESH_SPIN_INTERVAL_MS = 16


class ScanPanel(QGroupBox):
    # Emitted by _finish_capture, automatically, right after every
    # successful capture (2026-09-04 - no manual "Add to Session" step
    # anymore) with a list holding exactly one capture-group dict -
    # {"kind": "normal", "path": str, "invert": bool} or
    # {"kind": "trichrome", "paths": {"R": str, "G": str, "B": str},
    # "invert": bool, "film_base": {"R": float, "G": float, "B": float} | None}.
    # MainWindow (on_scan_add_to_session_requested) owns turning these into
    # real BatchItems - this panel never imports model.py itself (imaging.py
    # is imported, narrowly, only for the film-base mean calculation below).
    add_to_session_requested = Signal(list)
    # Emitted by the "pick from photo" eyedropper button - MainWindow arms/
    # disarms the canvas's own film-base pick mode and, on a click, calls
    # back into set_film_base_from_pick()/set_pick_from_photo_active()
    # below (see on_pick_film_base_from_photo_toggled/
    # on_film_base_pick_requested in main_window.py).
    pick_film_base_from_photo_toggled = Signal(bool)
    # Emitted by the "Apply to Selected Photo(s)" button - the "a
    # posteriori" case (already-imported photos, however they got into the
    # session). MainWindow (on_apply_film_base_requested) reads the
    # current reference via film_base() and reloads/corrects whichever
    # photo(s) are targeted.
    apply_film_base_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._settings = QSettings(scan_window.ORG_NAME, scan_window.APP_NAME)
        self._cameras: list[gphoto_backend.DetectedCamera] = []
        self._capturing = False
        self._quality_config_path: str | None = None
        self._backlight_window: BacklightWindow | None = None
        self._rgb_sequence_active = False
        self._rgb_sequence_step = 0
        self._rgb_sequence_paths: list[tuple[str, str]] = []
        self._rgb_sequence_port: str | None = None
        self._thread: QThread | None = None
        self._worker: CaptureWorker | None = None
        self._refresh_spin_elapsed_ms = 0
        # Film base sampling (2026-09-04) - see the "Sample Film Base"
        # section in CLAUDE.md. Session-scoped only (not QSettings-
        # persisted) - deliberately simple for this first pass.
        self._film_base: dict[str, float] | None = None
        self._film_base_temp_dir: str | None = None
        self._sampling_base = False

        outer, header_row, self.title_label = start_block_chrome(self, "scan", "menu_tools_scan")
        header_row.addStretch(1)
        self.body, self.body_layout, self.collapse_button, self.close_button = finish_block_chrome(
            outer, header_row)

        self._build_ui()
        self._load_settings()
        self._sync_mode_note()

        # Ctrl+Return/Cmd+Return (Qt maps Ctrl<->Cmd on macOS) triggers
        # Capture - default QShortcut context (WindowShortcut) fires
        # whenever the *main window* has focus, regardless of which child
        # widget inside it does, same as every other bare-key shortcut in
        # this app (see MainWindow.keyPressEvent) - not scoped to just this
        # panel having focus.
        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            shortcut = QShortcut(QKeySequence(seq), self)
            shortcut.activated.connect(self._on_capture_clicked)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_devices)
        self._poll_timer.start()
        self._poll_devices()

        self._refresh_spin_timer = QTimer(self)
        self._refresh_spin_timer.setInterval(_REFRESH_SPIN_INTERVAL_MS)
        self._refresh_spin_timer.timeout.connect(self._on_refresh_spin_tick)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _make_section(self, layout) -> CollapsibleSection:
        """Builds one collapsible sub-section, expanded by default, styled
        to match this panel's own muted small-caps section-label look, and
        wired so any collapse/expand click is immediately persisted (its
        own toggled signal feeds the same catch-all _save_settings() every
        other field here already goes through)."""
        section = CollapsibleSection()
        section.setChecked(True)
        section.toggle_button.setStyleSheet(_SECTION_TOGGLE_STYLE)
        section.toggled.connect(lambda _checked: self._save_settings())
        layout.addWidget(section)
        return section

    def _build_ui(self) -> None:
        layout = self.body_layout

        # Permanent "still under development" notice - unlike
        # make_disabled_message_label()'s banner (hidden unless the block
        # is disabled), this one is always visible; reuses the same yellow
        # so it reads as the same "heads up" signal as everywhere else in
        # the app (2026-09-08).
        self.wip_notice_label = QLabel(i18n.tr("scan_wip_notice"))
        self.wip_notice_label.setWordWrap(True)
        self.wip_notice_label.setStyleSheet(DISABLED_MESSAGE_STYLE)
        layout.addWidget(self.wip_notice_label)

        self.device_section = self._make_section(layout)
        device_content = self.device_section.content_layout
        status_row = QHBoxLayout()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #888; font-size: 14px;")
        status_row.addWidget(self.status_dot)
        self.status_label = QLabel()
        status_row.addWidget(self.status_label, 1)
        self.refresh_button = SvgToolButton("Tools/Scan/refresh.svg")
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        status_row.addWidget(self.refresh_button)
        device_content.addLayout(status_row)
        self.camera_combo = QComboBox()
        self.camera_combo.currentIndexChanged.connect(self._on_camera_selected)
        device_content.addWidget(self.camera_combo)
        self.quality_label = QLabel()
        device_content.addWidget(self.quality_label)
        self.quality_combo = QComboBox()
        self.quality_combo.currentTextChanged.connect(self._on_quality_changed)
        self.quality_combo.hide()
        device_content.addWidget(self.quality_combo)

        layout.addWidget(_make_hairline())

        self.mode_section = self._make_section(layout)
        mode_content = self.mode_section.content_layout
        mode_buttons_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self._mode_buttons: list[QRadioButton] = []
        dpr = self.devicePixelRatioF() or 1.0
        for idx, _mode in enumerate(MODES):
            btn = QRadioButton()
            btn.setIcon(tinted_svg_icon(
                "Tools/Scan/camera_roll.svg", _MODE_BUTTON_ICON_SIZE, QColor(_FILM_ICON_COLORS[idx]), dpr))
            btn.setIconSize(QSize(_MODE_BUTTON_ICON_SIZE, _MODE_BUTTON_ICON_SIZE))
            btn.setStyleSheet(_FRAMED_MODE_BUTTON_STYLE)
            self.mode_group.addButton(btn, idx)
            mode_buttons_row.addWidget(btn)
            if idx < len(MODES) - 1:
                mode_buttons_row.addSpacing(4)
            self._mode_buttons.append(btn)
        # A trailing stretch (not just addWidget with no stretch factor) is
        # what actually keeps each button sized to its own icon+text -
        # without it, QRadioButton's default horizontal size policy
        # (Minimum, confirmed by measuring it directly) lets leftover row
        # width stretch the buttons themselves instead of the empty space
        # at the row's end; same fix already used by the Batch Import
        # window's own Processing Mode row (2026-09-08).
        mode_buttons_row.addStretch(1)
        self._mode_buttons[0].setChecked(True)
        self.mode_group.idClicked.connect(lambda _id: self._sync_mode_note())
        mode_content.addLayout(mode_buttons_row)
        self.mode_note_label = QLabel()
        self.mode_note_label.setWordWrap(True)
        self.mode_note_label.setStyleSheet("color: #888; font-size: 11px;")
        mode_content.addWidget(self.mode_note_label)

        layout.addWidget(_make_hairline())

        self.light_section = self._make_section(layout)
        light_content = self.light_section.content_layout
        light_buttons_row = QHBoxLayout()
        self.light_mode_group = QButtonGroup(self)
        self.light_mode_group.setExclusive(True)
        self._light_mode_buttons: list[QRadioButton] = []
        # RGB Light's own icon is the same light-bulb glyph as White, but
        # banded red/green/blue via a linear gradient - reusing the same
        # pure primary colors the backlight window itself actually cycles
        # through during an RGB capture (_RGB_CHANNEL_COLORS), not the
        # app's more muted trichrome-channel palette, since this icon
        # represents that literal on-screen light sequence. A tri-color
        # Rainbow glyph (Scan/rainbow-rgb.svg) was tried instead the same
        # day, but the user preferred this banded-bulb version once
        # they'd compared both in the real app.
        rgb_gradient = QLinearGradient(0, 0, 0, _MODE_BUTTON_ICON_SIZE)
        rgb_gradient.setColorAt(0.0, _RGB_CHANNEL_COLORS["R"])
        rgb_gradient.setColorAt(0.5, _RGB_CHANNEL_COLORS["G"])
        rgb_gradient.setColorAt(1.0, _RGB_CHANNEL_COLORS["B"])
        light_icons = (
            tinted_svg_icon(_EXTERNAL_LIGHT_ICON, _MODE_BUTTON_ICON_SIZE, QColor(_LIGHT_ICON_COLOR), dpr),
            tinted_svg_icon(_WHITE_LIGHT_ICON, _MODE_BUTTON_ICON_SIZE, QColor(_LIGHT_ICON_COLOR), dpr),
            gradient_tinted_svg_icon(_RGB_LIGHT_ICON, _MODE_BUTTON_ICON_SIZE, rgb_gradient, dpr),
        )
        for idx, _label_key in enumerate(_LIGHT_MODE_KEYS):
            btn = QRadioButton()
            btn.setIcon(light_icons[idx])
            btn.setIconSize(QSize(_MODE_BUTTON_ICON_SIZE, _MODE_BUTTON_ICON_SIZE))
            btn.setStyleSheet(_FRAMED_MODE_BUTTON_STYLE)
            self.light_mode_group.addButton(btn, idx)
            light_buttons_row.addWidget(btn)
            if idx < len(_LIGHT_MODE_KEYS) - 1:
                light_buttons_row.addSpacing(4)
            self._light_mode_buttons.append(btn)
        light_buttons_row.addStretch(1)
        self._light_mode_buttons[0].setChecked(True)
        self.light_mode_group.idClicked.connect(lambda _id: self._on_light_mode_changed())
        light_content.addLayout(light_buttons_row)
        self.light_note_label = QLabel()
        self.light_note_label.setWordWrap(True)
        self.light_note_label.setStyleSheet("color: #888; font-size: 11px;")
        self.light_note_label.hide()
        light_content.addWidget(self.light_note_label)

        # Not gated by light mode (2026-09-04) - originally RGB-Light-only,
        # widened once film base correction applied to any photo (Normal
        # mode included) and to already-imported photos, not just live
        # captures. A per-channel reference sampled from the film's own
        # clear/unexposed base, used to correct color negative's orange
        # mask (and any similar base tint) before invert, since a plain
        # white-balance pick applied after invert can't fully remove it
        # (see CLAUDE.md). 3 ways to use it: a dedicated 3-shot RGB Light
        # calibration capture (sample_base_button, still RGB-Light-only -
        # validated on click, not gated on visibility, same as
        # _ensure_base_folder's own pattern), an eyedropper alternative
        # (pick_from_photo_button) that samples a point on a photo already
        # in the session instead (Normal or Trichrome), or applying the
        # already-sampled reference directly to already-imported photo(s)
        # (apply_film_base_button) - the "a posteriori" case, for photos
        # imported after having been scanned some other way. The first two
        # set self._film_base; the checkbox only gates whether *new* Scan
        # tool captures pick it up automatically, independent of the
        # explicit Apply button below.
        sample_base_row = QHBoxLayout()
        self.sample_base_button = QPushButton()
        self.sample_base_button.clicked.connect(self._on_sample_base_clicked)
        sample_base_row.addWidget(self.sample_base_button, 1)
        self.pick_from_photo_button = SvgCheckableToolButton("Global/eyedropper.svg")
        self.pick_from_photo_button.toggled.connect(self.pick_film_base_from_photo_toggled.emit)
        sample_base_row.addWidget(self.pick_from_photo_button)
        light_content.addLayout(sample_base_row)
        self.film_base_status_label = QLabel()
        self.film_base_status_label.setWordWrap(True)
        self.film_base_status_label.setStyleSheet("color: #888; font-size: 11px;")
        light_content.addWidget(self.film_base_status_label)
        self.apply_film_base_checkbox = QCheckBox()
        self.apply_film_base_checkbox.setChecked(True)
        light_content.addWidget(self.apply_film_base_checkbox)
        self.apply_film_base_button = QPushButton()
        self.apply_film_base_button.clicked.connect(self._on_apply_film_base_clicked)
        light_content.addWidget(self.apply_film_base_button)

        layout.addWidget(_make_hairline())

        self.location_section = self._make_section(layout)
        location_content = self.location_section.content_layout

        folder_row = QHBoxLayout()
        self.base_folder_label = QLabel()
        folder_row.addWidget(self.base_folder_label)
        self.base_folder_edit = QLineEdit()
        self.base_folder_edit.textChanged.connect(self._save_settings)
        folder_row.addWidget(self.base_folder_edit, 1)
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._browse_base_folder)
        folder_row.addWidget(self.browse_button)
        location_content.addLayout(folder_row)

        subfolder_row = QHBoxLayout()
        self.subfolder_label = QLabel()
        subfolder_row.addWidget(self.subfolder_label)
        self.subfolder_edit = QLineEdit()
        self.subfolder_edit.textChanged.connect(self._save_settings)
        subfolder_row.addWidget(self.subfolder_edit, 1)
        location_content.addLayout(subfolder_row)

        self.use_roll_subfolder_checkbox = QCheckBox()
        self.use_roll_subfolder_checkbox.toggled.connect(self._on_use_roll_subfolder_toggled)
        location_content.addWidget(self.use_roll_subfolder_checkbox)

        roll_row = QHBoxLayout()
        self.roll_name_label = QLabel()
        roll_row.addWidget(self.roll_name_label)
        self.roll_name_edit = QLineEdit()
        self.roll_name_edit.textChanged.connect(self._on_roll_name_changed)
        roll_row.addWidget(self.roll_name_edit, 1)
        location_content.addLayout(roll_row)

        self.subfolder_preview_label = QLabel()
        self.subfolder_preview_label.setStyleSheet("color: #888; font-size: 11px;")
        self.subfolder_preview_label.hide()
        location_content.addWidget(self.subfolder_preview_label)

        next_row = QHBoxLayout()
        self.next_number_label = QLabel()
        next_row.addWidget(self.next_number_label)
        self.next_number_spin = QSpinBox()
        self.next_number_spin.setRange(1, 9999)
        self.next_number_spin.valueChanged.connect(self._save_settings)
        next_row.addWidget(self.next_number_spin, 1)
        location_content.addLayout(next_row)

        layout.addWidget(_make_hairline())

        self.capture_button = QPushButton()
        self.capture_button.setEnabled(False)
        self.capture_button.setMinimumHeight(40)
        self.capture_button.clicked.connect(self._on_capture_clicked)
        layout.addWidget(self.capture_button)

        self.capture_status_label = QLabel()
        self.capture_status_label.setStyleSheet("color: #888;")
        layout.addWidget(self.capture_status_label)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.title_label.setText(i18n.tr("menu_tools_scan"))
        self.wip_notice_label.setText(i18n.tr("scan_wip_notice"))
        self.device_section.setTitle(i18n.tr("scan_device_group"))
        self.refresh_button.setToolTip(i18n.tr("scan_device_refresh"))
        self.mode_section.setTitle(i18n.tr("scan_mode_group"))
        for btn, (_key, label_key, _invert) in zip(self._mode_buttons, MODES):
            # QPushButton treats a single "&" as a mnemonic marker (would
            # otherwise render "Black & White" as "Black _White") - escape
            # it as a literal ampersand.
            btn.setText(i18n.tr(label_key).replace("&", "&&"))
        self.light_section.setTitle(i18n.tr("scan_light_group"))
        for btn, label_key in zip(self._light_mode_buttons, _LIGHT_MODE_KEYS):
            btn.setText(i18n.tr(label_key).replace("&", "&&"))
        self.sample_base_button.setText(i18n.tr("scan_sample_base_button"))
        self.sample_base_button.setToolTip(i18n.tr("scan_sample_base_tooltip"))
        self.pick_from_photo_button.setToolTip(i18n.tr("scan_pick_film_base_tooltip"))
        self.apply_film_base_checkbox.setText(i18n.tr("scan_apply_film_base_checkbox"))
        self.apply_film_base_checkbox.setToolTip(i18n.tr("scan_apply_film_base_tooltip"))
        self.apply_film_base_button.setText(i18n.tr("scan_apply_film_base_button"))
        self.apply_film_base_button.setToolTip(i18n.tr("scan_apply_film_base_button_tooltip"))
        self.location_section.setTitle(i18n.tr("scan_location_group"))
        self.base_folder_label.setText(i18n.tr("scan_base_folder_label"))
        self.browse_button.setText(i18n.tr("scan_base_folder_browse"))
        self.subfolder_label.setText(i18n.tr("scan_subfolder_label"))
        self.use_roll_subfolder_checkbox.setText(i18n.tr("scan_use_roll_as_subfolder"))
        self.roll_name_label.setText(i18n.tr("scan_roll_name_label"))
        self.next_number_label.setText(i18n.tr("scan_next_number_label"))
        self.capture_button.setText(i18n.tr("scan_capture_button"))
        # State-dependent text/visibility is re-derived from current state
        # rather than cached, so a language switch mid-connection or
        # mid-capture still reads correctly instead of just re-translating
        # whatever text happened to be set last.
        if self.quality_label.isVisible():
            self.quality_label.setText(i18n.tr("scan_quality_label"))
        if not self._cameras:
            self.status_label.setText(i18n.tr("scan_device_not_connected"))
        elif self.status_label.text():
            self.status_label.setText(i18n.tr("scan_device_connected", model=self._cameras[0].model))
        if not self._capturing:
            self.capture_status_label.setText(i18n.tr("scan_ready_status"))
        self._sync_mode_note()
        self._sync_light_note()
        self._sync_film_base_status_label()
        self._sync_subfolder_preview()

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------
    def _load_settings(self) -> None:
        # Each field's own textChanged/valueChanged is wired straight to
        # _save_settings() (see below), which writes every field's *current*
        # widget value - including whichever of these fields haven't been
        # loaded yet. Without blocking signals here, loading field N would
        # echo field N+1's still-default value back into the store before
        # it's ever read, clobbering it.
        #
        # The 4 section-collapse values are read into locals right here,
        # before anything else runs, for the same reason but a sharper
        # trap: CollapsibleSection.setChecked() always calls _save_settings()
        # (no blockSignals escape hatch - see the comment further down),
        # so mode_index/light_mode_index loading below would otherwise
        # trigger an intermediate _save_settings() that reads each
        # section's still-default (expanded) widget state and writes it
        # straight back into QSettings, clobbering the real persisted
        # value *before* this method ever gets to read it - a real bug
        # caught by testing (constructing a second ScanPanel() in the same
        # process to "simulate a restart" is the documented-unreliable way
        # to catch this - re-calling _load_settings() on the same instance
        # after desyncing its widgets from what's on disk is what actually
        # reproduced it).
        device_expanded = self._settings.value("section_expanded_device", True, type=bool)
        film_expanded = self._settings.value("section_expanded_film", True, type=bool)
        light_expanded = self._settings.value("section_expanded_light", True, type=bool)
        location_expanded = self._settings.value("section_expanded_location", True, type=bool)
        fields = (
            self.base_folder_edit, self.subfolder_edit, self.roll_name_edit,
            self.next_number_spin, self.use_roll_subfolder_checkbox,
        )
        for w in fields:
            w.blockSignals(True)
        self.base_folder_edit.setText(self._settings.value("base_folder", "", type=str))
        self.subfolder_edit.setText(self._settings.value("subfolder", "", type=str))
        self.roll_name_edit.setText(self._settings.value("roll_name", "Roll01", type=str))
        self.next_number_spin.setValue(self._settings.value("next_number", 1, type=int))
        self.use_roll_subfolder_checkbox.setChecked(
            self._settings.value("use_roll_as_subfolder", False, type=bool)
        )
        for w in fields:
            w.blockSignals(False)
        self.subfolder_edit.setEnabled(not self.use_roll_subfolder_checkbox.isChecked())
        self._sync_subfolder_preview()
        mode_index = self._settings.value("mode_index", 0, type=int)
        if 0 <= mode_index < len(self._mode_buttons):
            self._mode_buttons[mode_index].setChecked(True)
        light_mode_index = self._settings.value("light_mode_index", 0, type=int)
        if 0 <= light_mode_index < len(self._light_mode_buttons):
            self._light_mode_buttons[light_mode_index].setChecked(True)
        # Just the note text, not _sync_backlight_window() - a saved
        # White/RGB mode should not silently pop a colored window open the
        # moment the block becomes visible, only once the user actively
        # picks a mode.
        self._sync_light_note()
        # Applying the values captured at the very top, not re-reading
        # QSettings here - see that comment for why re-reading at this
        # point would pick up a clobbered value instead of the real one.
        # CollapsibleSection.setChecked() always fires _save_settings()
        # regardless of whether the value actually changed, so this also
        # correctly re-persists mode_index/light_mode_index (already
        # loaded above) alongside each section's own restored state -
        # by the time the last of these 4 calls runs, every field
        # _save_settings() reads is already correct, so the net result on
        # disk is fully consistent again.
        self.device_section.setChecked(device_expanded)
        self.mode_section.setChecked(film_expanded)
        self.light_section.setChecked(light_expanded)
        self.location_section.setChecked(location_expanded)

    def settings_snapshot(self) -> dict:
        """Every field this tool's configuration should be captured by -
        same fields _save_settings() already persists to the Scan tool's
        own separate, cross-session QSettings domain, but returned here so
        a specific .trirgb session file can also embed them (see
        MainWindow._collect_session_data/load_session_from_path and the
        "per-session scan settings" entry in CLAUDE.md for why this is
        .trirgb-only, not also threaded through the main app's QSettings-
        autosave fallback)."""
        return {
            "base_folder": self.base_folder_edit.text(),
            "subfolder": self.subfolder_edit.text(),
            "roll_name": self.roll_name_edit.text(),
            "next_number": self.next_number_spin.value(),
            "use_roll_as_subfolder": self.use_roll_subfolder_checkbox.isChecked(),
            "mode_index": self.mode_group.checkedId(),
            "light_mode_index": self.light_mode_group.checkedId(),
        }

    def apply_settings_snapshot(self, data: dict) -> None:
        """Inverse of settings_snapshot() - restores this tool's
        configuration from a specific session file's own saved values.
        Same blockSignals discipline as _load_settings() (each field's own
        textChanged/valueChanged is wired straight to _save_settings(),
        which writes every field's *current* value - without blocking
        signals here, restoring field N would echo field N+1's still-old
        value back into the Scan tool's own QSettings domain before it's
        ever restored, clobbering it). Missing keys (an older .trirgb saved
        before this feature existed, or a bare ``{}`` for a fresh session)
        simply leave whatever's already showing untouched, not a
        hardcoded default. Ends by re-saving into the Scan tool's own
        domain too, so it also becomes the new baseline for a brand-new
        capture in *this* session, and stays the "last used anywhere"
        default for the next session that has no saved values of its own."""
        if not data:
            return
        fields = (
            self.base_folder_edit, self.subfolder_edit, self.roll_name_edit,
            self.next_number_spin, self.use_roll_subfolder_checkbox,
        )
        for w in fields:
            w.blockSignals(True)
        if "base_folder" in data:
            self.base_folder_edit.setText(data["base_folder"])
        if "subfolder" in data:
            self.subfolder_edit.setText(data["subfolder"])
        if "roll_name" in data:
            self.roll_name_edit.setText(data["roll_name"])
        if "next_number" in data:
            self.next_number_spin.setValue(data["next_number"])
        if "use_roll_as_subfolder" in data:
            self.use_roll_subfolder_checkbox.setChecked(data["use_roll_as_subfolder"])
        for w in fields:
            w.blockSignals(False)
        self.subfolder_edit.setEnabled(not self.use_roll_subfolder_checkbox.isChecked())
        self._sync_subfolder_preview()
        mode_index = data.get("mode_index")
        if mode_index is not None and 0 <= mode_index < len(self._mode_buttons):
            self._mode_buttons[mode_index].setChecked(True)
        light_mode_index = data.get("light_mode_index")
        if light_mode_index is not None and 0 <= light_mode_index < len(self._light_mode_buttons):
            self._light_mode_buttons[light_mode_index].setChecked(True)
        self._sync_mode_note()
        self._sync_light_note()
        self._sync_film_base_status_label()
        self._save_settings()
        self._poll_devices()

    def _save_settings(self) -> None:
        self._settings.setValue("base_folder", self.base_folder_edit.text())
        self._settings.setValue("subfolder", self.subfolder_edit.text())
        self._settings.setValue("roll_name", self.roll_name_edit.text())
        self._settings.setValue("next_number", self.next_number_spin.value())
        self._settings.setValue("use_roll_as_subfolder", self.use_roll_subfolder_checkbox.isChecked())
        self._settings.setValue("mode_index", self.mode_group.checkedId())
        self._settings.setValue("light_mode_index", self.light_mode_group.checkedId())
        self._settings.setValue("section_expanded_device", self.device_section.isChecked())
        self._settings.setValue("section_expanded_film", self.mode_section.isChecked())
        self._settings.setValue("section_expanded_light", self.light_section.isChecked())
        self._settings.setValue("section_expanded_location", self.location_section.isChecked())

    # ------------------------------------------------------------------
    # Mode
    # ------------------------------------------------------------------
    def _current_mode(self) -> tuple[str, str, bool]:
        return MODES[max(0, self.mode_group.checkedId())]

    def _sync_mode_note(self) -> None:
        # Per-mode note text (2026-09-08), replacing the older plain
        # invert-vs-not phrasing (kept as scan_mode_invert_note/
        # scan_mode_no_invert_note for the standalone scan_tool/
        # scan_window.py, untouched) - each mode now also states whether
        # Black & White is applied automatically, not just Invert, since
        # that's now real automatic behavior on import too (see
        # _auto_add_to_session's own "black_white" below).
        key, _label_key, _invert = self._current_mode()
        self.mode_note_label.setText(i18n.tr(_MODE_NOTE_KEYS[key]))
        self._save_settings()

    # ------------------------------------------------------------------
    # Scan light - uses the computer screen as an improvised backlight for
    # negative scanning. White and RGB modes both show the same plain white
    # window at rest (RGB just for framing/focus before a capture - white is
    # easier to see by than any single primary color); RGB mode additionally
    # drives the window through a red/green/blue capture sequence (see
    # _advance_rgb_sequence below) whenever Capture is pressed, then returns
    # it to white afterward.
    # ------------------------------------------------------------------
    def _on_light_mode_changed(self) -> None:
        self._sync_light_note()
        self._sync_film_base_status_label()
        self._sync_backlight_window()
        self._save_settings()

    def _sync_light_note(self) -> None:
        if self.light_mode_group.checkedId() == 2:
            self.light_note_label.setText(i18n.tr("scan_light_rgb_note"))
            self.light_note_label.show()
        else:
            self.light_note_label.hide()

    # ------------------------------------------------------------------
    # Film base sampling - see the class docstring and CLAUDE.md for the
    # full rationale. RGB Light only: a per-channel reference (mean pixel
    # value of 3 shots of the film's own clear/unexposed base) applied as
    # a pre-invert correction to later RGB Light triplets added to the
    # session, to remove color negative's orange-mask bias (and any
    # similar base tint) that a post-invert white-balance pick alone
    # can't fully undo.
    # ------------------------------------------------------------------
    def _sync_film_base_status_label(self) -> None:
        if self._film_base is None:
            self.film_base_status_label.setText(i18n.tr("scan_film_base_status_not_set"))
        else:
            self.film_base_status_label.setText(i18n.tr(
                "scan_film_base_status_set",
                r=f"{self._film_base['R']:.2f}", g=f"{self._film_base['G']:.2f}", b=f"{self._film_base['B']:.2f}",
            ))
        self._sync_film_base_visibility()

    def _sync_film_base_visibility(self) -> None:
        # Not light-mode-gated (2026-09-04) - see the _build_ui comment
        # above these widgets for why. apply_film_base_button and the
        # status label only need a sampled reference to be useful;
        # sample_base_button/pick_from_photo_button validate their own
        # RGB-Light/active-photo preconditions on click instead.
        self.apply_film_base_checkbox.setVisible(self._film_base is not None)
        self.apply_film_base_button.setVisible(self._film_base is not None)

    def film_base(self) -> dict | None:
        """Public getter for MainWindow.on_apply_film_base_requested -
        returns a fresh copy (never the internal reference) so a later
        resample can't retroactively mutate a correction already handed
        out and applied to some photo."""
        return dict(self._film_base) if self._film_base else None

    def set_film_base_from_pick(self, base: dict) -> None:
        """Called by MainWindow.on_film_base_pick_requested once it's
        sampled a point from the active photo (Normal mode: its own R/G/B
        pixel value; Trichrome: each of its 3 channels) - sets the same
        self._film_base a dedicated 3-shot Sample Film Base run would,
        applied to the *next* capture the same way either path would be,
        or to an explicit "Apply to Selected Photo(s)" click."""
        self._film_base = dict(base)
        self._sync_film_base_status_label()

    def set_pick_from_photo_active(self, active: bool) -> None:
        self.pick_from_photo_button.blockSignals(True)
        self.pick_from_photo_button.setChecked(active)
        self.pick_from_photo_button.blockSignals(False)

    def _on_apply_film_base_clicked(self) -> None:
        if self._film_base is None:
            show_alert(self, i18n.tr("scan_error_title"), i18n.tr("scan_apply_film_base_none_sampled"))
            return
        self.apply_film_base_requested.emit()

    def _on_sample_base_clicked(self) -> None:
        if self._capturing:
            return
        if self.light_mode_group.checkedId() != 2:
            show_alert(self, i18n.tr("scan_error_title"), i18n.tr("scan_sample_base_requires_rgb_light"))
            return
        port = self._selected_port()
        if not port:
            show_alert(self, i18n.tr("scan_error_title"), i18n.tr("scan_no_camera_error"))
            return

        self._sync_backlight_window()
        self._sampling_base = True
        self._film_base_temp_dir = tempfile.mkdtemp(prefix="trichrome_filmbase_")
        self._rgb_sequence_active = True
        self._rgb_sequence_step = 0
        self._rgb_sequence_paths = []
        self._rgb_sequence_port = port
        self._capturing = True
        self.capture_button.setEnabled(False)
        self.sample_base_button.setEnabled(False)
        self._advance_rgb_sequence()

    def _finish_base_sampling(self, entries: list[tuple[str, str | None]]) -> None:
        """Counterpart of _finish_capture for a Sample Film Base run - same
        3-shot RGB sequence machinery, but the result is a calibration
        scalar kept in memory, not a session photo: nothing is written to
        history/manifest and the counter doesn't advance. Only overwrites
        self._film_base when all 3 channels actually succeeded - a partial
        sample (e.g. one channel failed mid-sequence) leaves a previous
        good sample, if any, untouched rather than replacing it with an
        incomplete one."""
        self._sampling_base = False
        self.sample_base_button.setEnabled(True)
        means: dict[str, float] = {}
        for path, channel in entries:
            if not channel:
                continue
            try:
                means[channel] = float(imaging.load_grayscale(path).mean())
            except Exception:
                continue
        if self._film_base_temp_dir:
            shutil.rmtree(self._film_base_temp_dir, ignore_errors=True)
            self._film_base_temp_dir = None
        if set(means) == {"R", "G", "B"}:
            self._film_base = means
        self._sync_film_base_status_label()
        self._end_capture_ui()

    def _ensure_backlight_window(self) -> BacklightWindow:
        if self._backlight_window is None:
            self._backlight_window = BacklightWindow(on_capture=self._on_capture_clicked)
        return self._backlight_window

    def _sync_backlight_window(self) -> None:
        """Rest-state sync only - always plain white when a light mode is
        active. The mid-capture R/G/B cycling in _advance_rgb_sequence()
        talks to self._backlight_window directly instead of going through
        this method, since it needs one specific color at a time, not the
        at-rest default."""
        if self.light_mode_group.checkedId() <= 0:
            if self._backlight_window is not None:
                self._backlight_window.close()
            return
        window = self._ensure_backlight_window()
        window.set_color(QColor("white"))
        window.show()
        window.raise_()

    # ------------------------------------------------------------------
    # Device detection
    # ------------------------------------------------------------------
    def _selected_port(self) -> str | None:
        idx = self.camera_combo.currentIndex()
        if 0 <= idx < len(self._cameras):
            return self._cameras[idx].port
        return None

    def _on_refresh_clicked(self) -> None:
        self._poll_devices()
        if not self._refresh_spin_timer.isActive():
            self._refresh_spin_elapsed_ms = 0
            self._refresh_spin_timer.start()

    def _on_refresh_spin_tick(self) -> None:
        self._refresh_spin_elapsed_ms += _REFRESH_SPIN_INTERVAL_MS
        if self._refresh_spin_elapsed_ms >= _REFRESH_SPIN_DURATION_MS:
            self._refresh_spin_timer.stop()
            self.refresh_button.set_rotation(0.0)
            return
        self.refresh_button.set_rotation(-360.0 * self._refresh_spin_elapsed_ms / _REFRESH_SPIN_DURATION_MS)

    def _poll_devices(self) -> None:
        if self._capturing:
            return
        try:
            cameras = gphoto_backend.auto_detect(timeout=3.0)
        except gphoto_backend.GPhotoError as exc:
            self.status_dot.setStyleSheet("color: #c0392b; font-size: 14px;")
            self.status_label.setText(str(exc))
            self._cameras = []
            self.camera_combo.clear()
            self.capture_button.setEnabled(False)
            return

        previous_ports = [c.port for c in self._cameras]
        new_ports = [c.port for c in cameras]
        self._cameras = cameras

        if not cameras:
            self.status_dot.setStyleSheet("color: #888; font-size: 14px;")
            self.status_label.setText(i18n.tr("scan_device_not_connected"))
            self.camera_combo.clear()
            self.quality_label.hide()
            self.quality_combo.hide()
            self.capture_button.setEnabled(False)
            return

        self.status_dot.setStyleSheet("color: #2ecc71; font-size: 14px;")
        self.status_label.setText(i18n.tr("scan_device_connected", model=cameras[0].model))
        self.capture_button.setEnabled(True)

        if new_ports != previous_ports:
            self.camera_combo.blockSignals(True)
            self.camera_combo.clear()
            for cam in cameras:
                self.camera_combo.addItem(f"{cam.model} ({cam.port})")
            self.camera_combo.setCurrentIndex(0)
            self.camera_combo.blockSignals(False)
            self._on_camera_selected(0)

    def _on_camera_selected(self, _index: int) -> None:
        port = self._selected_port()
        self._quality_config_path = None
        self.quality_label.hide()
        self.quality_combo.hide()
        if not port:
            return
        try:
            path = gphoto_backend.find_quality_config(port, timeout=5.0)
            if not path:
                return
            info = gphoto_backend.get_config(port, path, timeout=5.0)
        except gphoto_backend.GPhotoError:
            return
        if not info.choices:
            return
        self._quality_config_path = path
        self.quality_label.setText(i18n.tr("scan_quality_label"))
        self.quality_label.show()
        self.quality_combo.blockSignals(True)
        self.quality_combo.clear()
        self.quality_combo.addItems(info.choices)
        current_index = info.choices.index(info.current) if info.current in info.choices else -1
        if current_index < 0:
            # Best-effort default to a RAW-looking choice when the camera's
            # own reported current value doesn't match any listed choice
            # verbatim (seen on some PTP drivers).
            for i, choice in enumerate(info.choices):
                if "raw" in choice.lower():
                    current_index = i
                    break
        if current_index >= 0:
            self.quality_combo.setCurrentIndex(current_index)
        self.quality_combo.blockSignals(False)
        self.quality_combo.show()

    def _on_quality_changed(self, value: str) -> None:
        port = self._selected_port()
        if not port or not self._quality_config_path or not value:
            return
        try:
            gphoto_backend.set_config(port, self._quality_config_path, value, timeout=5.0)
        except gphoto_backend.GPhotoError as exc:
            show_alert(self, i18n.tr("scan_error_title"), str(exc))

    # ------------------------------------------------------------------
    # Save location
    # ------------------------------------------------------------------
    def _browse_base_folder(self) -> None:
        start_dir = self.base_folder_edit.text() or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, i18n.tr("scan_base_folder_browse"), start_dir)
        if path:
            self.base_folder_edit.setText(path)

    def _on_use_roll_subfolder_toggled(self, checked: bool) -> None:
        self.subfolder_edit.setEnabled(not checked)
        self._sync_subfolder_preview()
        self._save_settings()

    def _on_roll_name_changed(self) -> None:
        self._sync_subfolder_preview()
        self._save_settings()

    def _sync_subfolder_preview(self) -> None:
        # The subfolder field is disabled (not hidden) while roll-name mode
        # is on, so this preview is what tells the user what will actually
        # be used in its place - the sanitized roll name never matches the
        # raw text verbatim when it contains characters unsafe for a folder
        # name.
        if self.use_roll_subfolder_checkbox.isChecked():
            name = naming.sanitize_roll_name(self.roll_name_edit.text())
            self.subfolder_preview_label.setText(i18n.tr("scan_subfolder_preview", name=name))
            self.subfolder_preview_label.show()
        else:
            self.subfolder_preview_label.hide()

    def _destination_folder(self) -> str:
        base = self.base_folder_edit.text().strip() or os.path.expanduser("~")
        if self.use_roll_subfolder_checkbox.isChecked():
            sub = naming.sanitize_roll_name(self.roll_name_edit.text())
        else:
            sub = self.subfolder_edit.text().strip()
        return os.path.join(base, sub) if sub else base

    def _capture_destination_folder(self) -> str:
        """Same as _destination_folder(), except while sampling the film
        base (self._sampling_base) - those 3 shots are pure calibration
        data, written to a throwaway temp dir (cleaned up in
        _finish_base_sampling) rather than the user's own save folder,
        and never need _ensure_base_folder()'s prompt."""
        if self._sampling_base and self._film_base_temp_dir:
            return self._film_base_temp_dir
        return self._destination_folder()

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------
    def _ensure_base_folder(self) -> bool:
        """If no save folder is set yet, prompts for one right away instead
        of silently falling back to the home directory (which
        _destination_folder() still does as a defensive last resort for
        any other caller) - returns False (capture must not proceed) only
        if the user cancels that prompt."""
        if self.base_folder_edit.text().strip():
            return True
        path = QFileDialog.getExistingDirectory(
            self, i18n.tr("scan_select_folder_prompt_title"), os.path.expanduser("~"))
        if not path:
            return False
        self.base_folder_edit.setText(path)
        return True

    def _on_capture_clicked(self) -> None:
        # The Capture button already disables itself while a capture is in
        # flight, but the Ctrl+Return shortcut (wired on this block and the
        # backlight window both) bypasses that - guard here too.
        if self._capturing:
            return
        if not self._ensure_base_folder():
            return
        port = self._selected_port()
        if not port:
            show_alert(self, i18n.tr("scan_error_title"), i18n.tr("scan_no_camera_error"))
            return

        # Bug fix (2026-09-04): under White light, the backlight window was
        # only ever raised on the light-mode *switch* (_on_light_mode_changed)
        # - if it lost focus/got buried behind another window afterward,
        # clicking Capture left it there. _sync_backlight_window() is a
        # no-op for External and, for RGB, gets immediately overridden by
        # _advance_rgb_sequence()'s own per-channel raise below anyway - so
        # calling it here unconditionally fixes White without needing a
        # special case.
        self._sync_backlight_window()

        if self.light_mode_group.checkedId() == 2:
            # RGB backlight: one Capture click drives the whole red/green/
            # blue triplet automatically rather than taking a single shot.
            self._rgb_sequence_active = True
            self._rgb_sequence_step = 0
            self._rgb_sequence_paths = []
            self._rgb_sequence_port = port
            self._capturing = True
            self.capture_button.setEnabled(False)
            self._advance_rgb_sequence()
        else:
            self._rgb_sequence_active = False
            self._start_capture(port, suffix=None)

    def _advance_rgb_sequence(self) -> None:
        letter = _RGB_SEQUENCE[self._rgb_sequence_step]
        window = self._ensure_backlight_window()
        window.set_color(_RGB_CHANNEL_COLORS[letter])
        window.show()
        window.raise_()
        self.capture_status_label.setText(i18n.tr("scan_capturing_channel_status", channel=letter))
        QTimer.singleShot(
            _LIGHT_SETTLE_DELAY_MS,
            lambda: self._start_capture(self._rgb_sequence_port, letter),
        )

    def _start_capture(self, port: str, suffix: str | None) -> None:
        dest_folder = self._capture_destination_folder()
        try:
            os.makedirs(dest_folder, exist_ok=True)
        except OSError as exc:
            self._handle_capture_failure(str(exc))
            return

        index = self.next_number_spin.value()
        pattern = naming.build_filename_pattern(self.roll_name_edit.text(), index, suffix)
        dest_pattern = os.path.join(dest_folder, pattern)

        self._capturing = True
        self.capture_button.setEnabled(False)
        if not suffix:
            self.capture_status_label.setText(i18n.tr("scan_capturing_status"))
        # else: _advance_rgb_sequence() already set the per-channel status
        # text above, before the settle delay - don't overwrite it here.

        self._thread = QThread(self)
        self._worker = CaptureWorker(port, dest_pattern)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_capture_step_finished)
        self._worker.error.connect(self._on_capture_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.error.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_capture_thread_refs)
        self._thread.start()

    def _clear_capture_thread_refs(self) -> None:
        self._thread = None
        self._worker = None

    def _end_capture_ui(self) -> None:
        self._capturing = False
        self.capture_button.setEnabled(bool(self._cameras))
        self.capture_status_label.setText(i18n.tr("scan_ready_status"))

    def _on_capture_step_finished(self, saved_paths: list[str]) -> None:
        if not self._rgb_sequence_active:
            self._finish_capture([(p, None) for p in saved_paths])
            return
        letter = _RGB_SEQUENCE[self._rgb_sequence_step]
        self._rgb_sequence_paths.extend((p, letter) for p in saved_paths)
        self._rgb_sequence_step += 1
        if self._rgb_sequence_step < len(_RGB_SEQUENCE):
            self._advance_rgb_sequence()
            return
        entries = self._rgb_sequence_paths
        self._rgb_sequence_active = False
        self._rgb_sequence_paths = []
        self._sync_backlight_window()  # back to white
        self._finish_capture(entries)

    def _finish_capture(
        self, entries: list[tuple[str, str | None]], advance_index: bool = True,
    ) -> None:
        """``entries`` is (saved path, channel-or-None) pairs - a single
        pair for a normal shot, 3 for a completed (or partially completed,
        on error) RGB triplet, all sharing one index number. Every entry
        still gets logged to manifest.append_entry (per-photo metadata on
        disk, unrelated to the UI); on a *complete* capture (a normal shot,
        or a full 3-channel RGB triplet - never a partial one, which
        ``advance_index=False`` signals), it's also added straight to the
        main session/carousel via add_to_session_requested - no
        intermediate history list or manual "Add to Session" step anymore
        (2026-09-04, per the user's explicit ask)."""
        if self._sampling_base:
            # A Sample Film Base run reuses this exact RGB-sequence
            # machinery (device selection, backlight cycling, error
            # handling) but its result is calibration data, not a session
            # photo - see _finish_base_sampling.
            self._finish_base_sampling(entries)
            return
        dest_folder = self._destination_folder()
        mode_key, label_key, invert = self._current_mode()
        light_mode_id = self.light_mode_group.checkedId()
        index = self.next_number_spin.value()
        for path, channel in entries:
            manifest.append_entry(dest_folder, os.path.basename(path), mode_key, invert, channel=channel)
        if advance_index and entries:
            self.next_number_spin.setValue(index + 1)
            self._auto_add_to_session(entries, light_mode_id, invert, mode_key == "bw")
        self._save_settings()
        self._end_capture_ui()

    def _auto_add_to_session(
        self, entries: list[tuple[str, str | None]], light_mode_id: int, invert: bool,
        black_white: bool,
    ) -> None:
        """Builds the one capture-group request for this completed capture
        and emits add_to_session_requested - only ever called from
        _finish_capture's ``advance_index`` branch, i.e. never for a
        partial/failed RGB triplet (advance_index=False there), so
        ``entries`` is always either a single normal shot or a real,
        complete R/G/B triplet here.

        ``black_white`` (True only for Film=B&W, see _finish_capture)
        flows straight onto the built BatchItem's own
        GlobalCorrection.black_white_active (main_window.py's
        on_scan_add_to_session_requested) - automatically forcing a true
        neutral-gray composite for B&W source material regardless of how
        it was captured (added 2026-09-08, alongside the Light-mode ->
        Solo/Trichrome mapping right below, both "apply the matching
        processing automatically on import" per the user's own request)."""
        if light_mode_id == 2:
            by_channel = {ch: p for p, ch in entries if ch}
            if set(by_channel) != {"R", "G", "B"}:
                return
            # film_base is only ever attached to a "trichrome" (RGB Light)
            # request - the sampled reference and the correction it drives
            # (see _build_trichrome_batch_item_from_paths in main_window.py)
            # are meaningless for a single already-composited Normal-mode
            # shot.
            use_base = self._film_base is not None and self.apply_film_base_checkbox.isChecked()
            request = {
                "kind": "trichrome", "paths": by_channel, "invert": invert,
                "film_base": dict(self._film_base) if use_base else None,
                "black_white": black_white,
            }
        else:
            if not entries:
                return
            request = {"kind": "normal", "path": entries[0][0], "invert": invert, "black_white": black_white}
        self.add_to_session_requested.emit([request])

    def _handle_capture_failure(self, message: str) -> None:
        # Log whichever RGB channel(s) already succeeded before the failure
        # rather than silently losing them - but don't advance the counter,
        # since the triplet is incomplete and a retry should reuse the same
        # index. Reset the sequence's own state before showing the (modal)
        # alert so nothing re-enters mid-sequence while it's up.
        entries_to_log: list[tuple[str, str | None]] = []
        if self._rgb_sequence_active:
            entries_to_log = self._rgb_sequence_paths
            self._rgb_sequence_active = False
            self._rgb_sequence_paths = []
            self._sync_backlight_window()
        show_alert(self, i18n.tr("scan_error_title"), message)
        if self._sampling_base:
            self._finish_base_sampling(entries_to_log)
        elif entries_to_log:
            self._finish_capture(entries_to_log, advance_index=False)
        else:
            self._end_capture_ui()

    def _on_capture_error(self, message: str) -> None:
        self._handle_capture_failure(message)

    # ------------------------------------------------------------------
    # Shutdown - called from MainWindow.closeEvent(), since this is now an
    # embedded block rather than its own top-level window and so never gets
    # its own closeEvent().
    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        self._poll_timer.stop()
        self._refresh_spin_timer.stop()
        if self._backlight_window is not None:
            self._backlight_window.close()
        if self._film_base_temp_dir:
            shutil.rmtree(self._film_base_temp_dir, ignore_errors=True)
            self._film_base_temp_dir = None
