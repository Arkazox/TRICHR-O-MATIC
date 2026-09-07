"""Top-of-sidebar panel: a single Mode selector (Solo / B&W Trichrome /
Color Trichrome), then either load the 3 channel images (either Trichrome
variant) or a single photo (Solo). Auto Align and Lock Layer Position moved
to the top of the "Trichrome Process" block (main_window.py's
independent_channels_group) - 2026-09-04.

Negative (invert) moved here, above the mode selector, 2026-09-07 - it's
per-photo source-interpretation state (which polarity this specific
photo's files were loaded under), not a "correction" applied afterward, so
it belongs with the rest of this block's load/mode concerns rather than in
Light (Negative used to live in LightPanel's header).

Mode selector, unified 2026-09-07 from what used to be two separate
controls: a plain Normal/Trichrome toggle here, plus an independent
"Harris Shutter Effect" checkbox down in the Trichrome Process block. Both
described the same underlying thing - how this photo's files should be
interpreted - so they're now one 3-way choice, styled like the Crop tool's
own aspect-ratio selector (icon + label + combo + a "?" info button):
**Solo** (BatchItem.mode == "normal" - a single already-composed photo),
**B&W Trichrome** (mode == "trichrome", ChannelLayer.harris_shutter ==
False - the classic case, 3 B&W photos through color filters), **Color
Trichrome** (mode == "trichrome", harris_shutter == True - 3 real color
photos, each keeping its own R/G/B channel). See CLAUDE.md's Harris
Shutter Effect section for the full processing-difference explanation."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from .. import i18n
from .block_header_bar import finish_block_chrome, start_block_chrome
from .channel_panel import CHANNEL_COLORS, CHANNEL_KEY
from .controls import ElidingLabel
from .info_bubble import show_info_bubble
from .svg_icons import (
    HEADER_COMPANION_BTN_SIZE, HEADER_COMPANION_ICON_SIZE, SvgCheckableToolButton, SvgColorCheckableToolButton,
    SvgIconLabel, SvgToolButton,
)

# Color Film button's fixed "on" tint - deliberately not one of
# channel_panel.CHANNEL_COLORS (which are reserved for R/G/B) and, per the
# user's own thematic choice, echoes color negative film's own orange base/
# mask.
_COLOR_FILM_TINT = "#e67e22"

# Order matches the combo's own item order. Icons are rendered "raw" (their
# own embedded colors, not the usual single-tint convention - see
# svg_icons.raw_svg_pixmap) since the whole point is 3 visually distinct
# glyphs. bw_trichrome/color_trichrome are General/layers-mode-{bw,color}.svg
# - the app's own filled "stack" glyph (resources/icons/General/stack.svg,
# a solid front diamond + 2 chevron slivers, as opposed to the plain-
# outline layers-outline.svg these 2 files used to derive from until
# 2026-09-07) with its 2 <path> elements split into 3 (the original has
# the top+bottom shapes sharing one path, same structure layers-outline.svg
# had) so each layer can carry its own explicit fill: B&W Trichrome grades
# from white at the front down to darker light-grays at the back
# (#ffffff/#e5e5e5/#cccccc - "white", "90% gray", "80% gray"); Color
# Trichrome colors each layer in its real R/G/B channel color (matching
# channel_panel.CHANNEL_COLORS exactly). solo is General/stack-middle.svg -
# a new asset built to match stack-front.svg/stack-back.svg's own family
# (front/back's card fully outlined AND filled; a card occluded by the one
# in front of it is outline-only with just a filled chevron sliver peeking
# through) with the *middle* card filled instead - the old outline-based
# General/layers-mode-solo.svg is left on disk, unreferenced, same
# leave-it-there convention as every other superseded icon in this project.
_MODE_KEYS = ("solo", "bw_trichrome", "color_trichrome")
_MODE_ICONS = {
    "solo": "General/stack-middle.svg",
    "bw_trichrome": "General/layers-mode-bw.svg",
    "color_trichrome": "General/layers-mode-color.svg",
}
_MODE_LABEL_KEYS = {
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
    load_normal_requested = Signal()
    add_photo_requested = Signal()
    invert_toggled = Signal(bool)
    harris_shutter_toggled = Signal(bool)

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
        # "Add Photo" - appends a new photo to the carousel, same header-
        # action-button convention as every other block's Reset (companion
        # size, trailing edge) - see MainWindow.on_add_photo_clicked for
        # what it actually does per mode.
        self.add_photo_button = SvgToolButton(
            "Toolbar/image-plus.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.add_photo_button.clicked.connect(self.add_photo_requested.emit)
        header_row.addWidget(self.add_photo_button)
        self.body, root, self.collapse_button, self.close_button = finish_block_chrome(outer, header_row)

        # --- Mode: Solo / B&W Trichrome / Color Trichrome - same visual
        # recipe as CropPanel's own aspect-ratio row (icon, label, combo,
        # trailing button), see the module docstring for what each choice
        # actually means underneath.
        mode_row = QHBoxLayout()
        self.mode_icon = SvgIconLabel(_MODE_ICONS["bw_trichrome"])
        mode_row.addWidget(self.mode_icon)
        self.mode_select_label = QLabel()
        mode_row.addWidget(self.mode_select_label)
        self.mode_combo = QComboBox()
        self.mode_combo.currentIndexChanged.connect(lambda _i: self._on_mode_combo_changed())
        mode_row.addWidget(self.mode_combo, stretch=1)
        self.mode_info_button = QToolButton()
        self.mode_info_button.setText("?")
        self.mode_info_button.setFixedSize(18, 18)
        self.mode_info_button.setStyleSheet("QToolButton { border-radius: 9px; }")
        self.mode_info_button.clicked.connect(
            lambda: show_info_bubble(i18n.tr("mode_select_info"), self.mode_info_button))
        mode_row.addWidget(self.mode_info_button)
        root.addLayout(mode_row)

        # --- Below Mode: a quicker, at-a-glance way to set the same
        # B&W/Color Trichrome choice the combo's last 2 entries already
        # cover (Film Roll icon, colored by which one's active - gray/white
        # for B&W, orange/grayed-orange for Color, per the user's explicit
        # spec), plus Negative (invert) - per-photo source state, not a
        # correction applied afterward, grouped here rather than living
        # anywhere else in the app.
        film_row = QHBoxLayout()
        self.bw_film_button = SvgCheckableToolButton(
            "Scan/film.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.bw_film_button.setCheckable(True)
        self.bw_film_button.clicked.connect(lambda: self._on_film_type_clicked(False))
        film_row.addWidget(self.bw_film_button)
        self.color_film_button = SvgColorCheckableToolButton(
            "Scan/film.svg", _COLOR_FILM_TINT,
            size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.color_film_button.clicked.connect(lambda: self._on_film_type_clicked(True))
        film_row.addWidget(self.color_film_button)
        # Not a QButtonGroup - both buttons stay independently clickable
        # (clicking either always re-applies its own film type, same
        # re-click-still-applies convention as the Mode combo/default
        # layout buttons elsewhere in this app) and both can read
        # unchecked at once (Solo mode - see set_mode_selection), which an
        # exclusive QButtonGroup can't represent.
        self.invert_button = SvgCheckableToolButton(
            "Preview/invert.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.invert_button.toggled.connect(self.invert_toggled.emit)
        film_row.addWidget(self.invert_button)
        film_row.addStretch(1)
        root.addLayout(film_row)

        # --- Trichrome mode: the 3 channel rows + auto-align + lock ---
        self.trichrome_container = QWidget()
        trichrome_layout = QVBoxLayout(self.trichrome_container)
        trichrome_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.trichrome_container)

        self.channel_labels: list[QLabel] = []
        self.filename_labels: list[ElidingLabel] = []
        self.load_buttons: list[QPushButton] = []

        for label in ("R", "G", "B"):
            row = QHBoxLayout()
            color = CHANNEL_COLORS.get(label, "#888")
            channel_label = QLabel()
            channel_label.setStyleSheet(f"color: {color}; font-weight: bold;")
            channel_label.setFixedWidth(50)
            row.addWidget(channel_label)

            filename_label = ElidingLabel()
            filename_label.setStyleSheet("color: #888; font-size: 11px;")
            row.addWidget(filename_label, stretch=1)

            load_button = QPushButton()
            load_button.clicked.connect(lambda _checked=False, i=len(self.channel_labels): self.load_requested.emit(i))
            row.addWidget(load_button)

            trichrome_layout.addLayout(row)
            self.channel_labels.append(channel_label)
            self.filename_labels.append(filename_label)
            self.load_buttons.append(load_button)

        # --- Normal mode: a single photo, no alignment/recompose ---
        self.normal_container = QWidget()
        normal_layout = QVBoxLayout(self.normal_container)
        normal_layout.setContentsMargins(0, 0, 0, 0)
        normal_row = QHBoxLayout()
        self.normal_filename_label = ElidingLabel()
        self.normal_filename_label.setStyleSheet("color: #888; font-size: 11px;")
        normal_row.addWidget(self.normal_filename_label, stretch=1)
        self.load_normal_button = QPushButton()
        self.load_normal_button.clicked.connect(self.load_normal_requested.emit)
        normal_row.addWidget(self.load_normal_button)
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

    def set_filename(self, index: int, text: str) -> None:
        self._has_image[index] = bool(text)
        self.filename_labels[index].setText(text or i18n.tr("no_image_loaded"))
        self.load_buttons[index].setText(
            i18n.tr("change_image_button") if text else i18n.tr("load_image_button"))

    def set_normal_filename(self, text: str) -> None:
        self._has_normal_image = bool(text)
        self.normal_filename_label.setText(text or i18n.tr("no_image_loaded"))
        self.load_normal_button.setText(
            i18n.tr("change_image_button") if text else i18n.tr("load_image_button"))

    def set_invert(self, checked: bool) -> None:
        self.invert_button.blockSignals(True)
        self.invert_button.setChecked(checked)
        self.invert_button.blockSignals(False)

    def is_harris_shutter_active(self) -> bool:
        """Whether the combo's current selection is Color Trichrome - the
        replacement for what used to be a standalone checkbox's
        isChecked(), read by MainWindow at load time (single manual load,
        batch import) to decide luminance vs. real-channel extraction."""
        idx = self.mode_combo.currentIndex()
        return 0 <= idx < len(_MODE_KEYS) and _MODE_KEYS[idx] == "color_trichrome"

    def _on_mode_combo_changed(self) -> None:
        idx = self.mode_combo.currentIndex()
        if idx < 0:
            return
        key = _MODE_KEYS[idx]
        self.mode_icon.set_icon_raw(_MODE_ICONS[key])
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

    def _on_film_type_clicked(self, is_color: bool) -> None:
        """Deliberately never touches mode_change_requested - the film
        buttons only ever set harris_shutter, in *every* mode, per the
        user's explicit spec (see CLAUDE.md's "Film type" section): in
        Trichrome mode this flips which Trichrome variant is active
        without leaving Trichrome; in Solo mode it stays in Solo and only
        changes whether this single photo is treated as color or B&W
        (MainWindow.on_harris_shutter_toggled forces Saturation to 0 and
        disables the Color block for that case). Uses .clicked (not
        .toggled) so re-clicking an already-active film button still
        re-applies it, same "re-click still applies" convention as the
        built-in default-layout toolbar buttons elsewhere in this app -
        relevant since these 2 buttons aren't in an exclusive
        QButtonGroup (see film_row's own construction comment), so a
        second click on the already-checked one wouldn't otherwise change
        its checked state at all. Doesn't touch the combo/icon/button
        checked-state directly - MainWindow round-trips
        harris_shutter_toggled back into set_mode_selection() below,
        which resyncs the combo, its icon, and both film buttons together
        from the model's own state, same as every other per-photo control
        here."""
        self.harris_shutter_toggled.emit(is_color)

    def set_mode_selection(self, mode: str, harris_shutter: bool) -> None:
        """Programmatic sync of the Mode combo and the 2 film-type buttons
        below it (activating a different photo, session restore, undo/
        redo, a reverted/cancelled mode switch, or a film button's own
        click round-tripping back here) - blocks signals so this never
        re-emits mode_change_requested/harris_shutter_toggled.

        ``harris_shutter`` is the *mode-appropriate* value - MainWindow
        passes self.normal_layer.harris_shutter while in Solo mode (Solo
        Couleur/Solo N&B) or self.layers[0].harris_shutter otherwise
        (B&W/Color Trichrome) - two independent per-item flags that both
        happen to drive the same 2 buttons, one at a time depending on
        the active mode (see _sync_import_and_channels_ui in
        main_window.py). Unlike the first pass, the film buttons are no
        longer forced unchecked in Solo mode - exactly one of them always
        reflects the current selection, in every mode."""
        is_normal = mode == "normal"
        key = "solo" if is_normal else ("color_trichrome" if harris_shutter else "bw_trichrome")
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(_MODE_KEYS.index(key))
        self.mode_combo.blockSignals(False)
        self.mode_icon.set_icon_raw(_MODE_ICONS[key])
        self.trichrome_container.setVisible(not is_normal)
        self.normal_container.setVisible(is_normal)
        self.bw_film_button.blockSignals(True)
        self.bw_film_button.setChecked(not harris_shutter)
        self.bw_film_button.blockSignals(False)
        self.color_film_button.blockSignals(True)
        self.color_film_button.setChecked(harris_shutter)
        self.color_film_button.blockSignals(False)

    def retranslate_ui(self) -> None:
        self.title_label.setText(i18n.tr("import_panel_title"))
        self.bw_film_button.setToolTip(i18n.tr("bw_film_button_tooltip"))
        self.color_film_button.setToolTip(i18n.tr("color_film_button_tooltip"))
        self.invert_button.setToolTip(i18n.tr("invert_checkbox_tooltip"))
        self.mode_select_label.setText(i18n.tr("mode_select_label"))
        current = self.mode_combo.currentIndex()
        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        for key in _MODE_KEYS:
            self.mode_combo.addItem(i18n.tr(_MODE_LABEL_KEYS[key]))
        self.mode_combo.setCurrentIndex(max(0, current))
        self.mode_combo.blockSignals(False)
        for i, label in enumerate(("R", "G", "B")):
            self.channel_labels[i].setText(i18n.tr(CHANNEL_KEY[label]) + ":")
            self.load_buttons[i].setText(
                i18n.tr("change_image_button") if self._has_image[i] else i18n.tr("load_image_button"))
            if not self._has_image[i]:
                self.filename_labels[i].setText(i18n.tr("no_image_loaded"))
        self.load_normal_button.setText(
            i18n.tr("change_image_button") if self._has_normal_image else i18n.tr("load_image_button"))
        if not self._has_normal_image:
            self.normal_filename_label.setText(i18n.tr("no_image_loaded"))
        self.add_photo_button.setToolTip(i18n.tr("add_photo_tooltip"))
