"""Preferences window (Trichr-o-matic > Preferences…, Cmd+,; also in the
toolbar's "?" menu). Every change applies and is saved immediately,
macOS-style - there's no OK/Cancel, only Done. Each section is a bordered
panel with its section title above it, the same look as Batch Import
(see widgets/dialog_style.py)."""
from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QLayout,
    QLineEdit, QPushButton, QStyle, QVBoxLayout, QWidget,
)

from .. import i18n
from .button_style import style_primary_button
from .dialog_style import PANEL_PADDING, make_panel, make_section_title
from .info_bubble import InfoButton
from .welcome_dialog import SHOW_AT_STARTUP_KEY
from .checkbox import CheckBox, RadioButton
from .combo_box import ComboBox

# QSettings keys (main app domain) owned by this window. The export ones are
# also read and written by ExportDialog, so its last-used values and these
# defaults are one and the same.
REOPEN_LAST_SESSION_KEY = "reopen_last_session_at_launch"
CHECK_UPDATES_ON_STARTUP_KEY = "check_updates_on_startup"
PLAY_SOUNDS_KEY = "play_sounds"
SESSION_PREVIEW_CACHE_KEY = "session_preview_cache"
EXPORT_FORMAT_KEY = "export_format_index"   # 0 PNG, 1 JPEG, 2 TIFF
EXPORT_SUFFIX_KEY = "export_suffix"
DEFAULT_EXPORT_SUFFIX = "_trichrome"
# Off by default: Scan is still alpha, hidden from public beta users unless
# they opt in (toolbar slot, S key, Tools/Window menu entries, Quick Tour step).
SCAN_TOOL_ENABLED_KEY = "scan_tool_enabled"

_CONTENT_WIDTH = 420
_BOX_PADDING = PANEL_PADDING
_INNER_WIDTH = _CONTENT_WIDTH - 2 * _BOX_PADDING
_HELP_STYLE = "color: #888; font-size: 11px;"
# Same yellow as the status bar's "mode is active" indicators.
_EXPERIMENTAL_RGB = "242, 196, 12"
_LANGUAGES = (("en", "English"), ("fr", "Français"))


def setting_bool(org_name: str, app_name: str, key: str, default: bool = True) -> bool:
    return QSettings(org_name, app_name).value(key, default, type=bool)


class SettingsDialog(QDialog):
    def __init__(self, main_window, org_name: str, app_name: str, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._org_name = org_name
        self._app_name = app_name
        self._build_ui()
        self._load_values()
        self.retranslate_ui()
        QShortcut(QKeySequence.Close, self, activated=self.close)

    def _settings(self) -> QSettings:
        return QSettings(self._org_name, self._app_name)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(0)
        # Size always follows the content (same approach as ConfirmDialog),
        # so a language switch can't clip or pad anything.
        root.setSizeConstraint(QLayout.SetFixedSize)

        # --- General -------------------------------------------------
        self.general_title, box = self._box(root)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self.language_label = QLabel()
        # A radio pair, not a dropdown - only ever 2 languages, so both choices
        # can stay in view at once.
        self.language_button_group = QButtonGroup(self)
        self.language_radios: dict[str, RadioButton] = {}
        language_row = QHBoxLayout()
        language_row.setSpacing(14)
        for code, name in _LANGUAGES:
            radio = RadioButton(name)
            radio.toggled.connect(
                lambda checked, c=code: self._on_language_changed(c) if checked else None)
            self.language_button_group.addButton(radio)
            self.language_radios[code] = radio
            language_row.addWidget(radio)
        language_row.addStretch(1)
        grid.addWidget(self.language_label, 0, 0)
        grid.addLayout(language_row, 0, 1)
        grid.setColumnStretch(1, 1)
        box.addLayout(grid)
        box.addSpacing(10)
        self.reopen_checkbox = self._checkbox(box, REOPEN_LAST_SESSION_KEY)
        self.quick_tour_checkbox = self._checkbox(box, SHOW_AT_STARTUP_KEY)
        self.check_updates_checkbox = self._checkbox(box, CHECK_UPDATES_ON_STARTUP_KEY)
        self.sounds_checkbox = self._checkbox(box, PLAY_SOUNDS_KEY, last=True)

        root.addSpacing(14)

        # --- Sessions ------------------------------------------------
        self.sessions_title, box = self._box(root)
        self.cache_checkbox = self._checkbox(box, SESSION_PREVIEW_CACHE_KEY, last=True)
        # Indented to line up with the checkbox's own text, not its box.
        style = self.cache_checkbox.style()
        indent = (style.pixelMetric(QStyle.PM_IndicatorWidth)
                  + style.pixelMetric(QStyle.PM_CheckBoxLabelSpacing))
        self.cache_help = self._help_label(box, indent)

        root.addSpacing(14)

        # --- Export --------------------------------------------------
        self.export_title, box = self._box(root)
        export_grid = QGridLayout()
        export_grid.setContentsMargins(0, 0, 0, 0)
        export_grid.setHorizontalSpacing(12)
        export_grid.setVerticalSpacing(8)
        self.format_label = QLabel()
        self.format_combo = ComboBox()
        self.format_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        self.suffix_label = QLabel()
        self.suffix_edit = QLineEdit()
        self.suffix_edit.setFixedWidth(180)
        self.suffix_edit.textEdited.connect(self._on_suffix_edited)
        export_grid.addWidget(self.format_label, 0, 0)
        export_grid.addWidget(self.format_combo, 0, 1, alignment=Qt.AlignLeft)
        export_grid.addWidget(self.suffix_label, 1, 0)
        export_grid.addWidget(self.suffix_edit, 1, 1, alignment=Qt.AlignLeft)
        export_grid.setColumnStretch(1, 1)
        box.addLayout(export_grid)
        self.export_help = self._help_label(box)

        root.addSpacing(14)

        # --- Experimental ---------------------------------------------
        self.experimental_title, box = self._box(root)
        # A muted yellow tint on the whole panel, not just the checkbox
        # text, sets the alpha section apart. Its own object name, so this
        # one frame overrides the shared PANEL_STYLE instead of adding to it.
        experimental_panel = box.parentWidget()
        experimental_panel.setObjectName("experimentalPanel")
        experimental_panel.setStyleSheet(f"""
            QFrame#experimentalPanel {{
                background: rgba({_EXPERIMENTAL_RGB}, 28);
                border: 1px solid rgba({_EXPERIMENTAL_RGB}, 80);
                border-radius: 6px;
            }}
        """)
        # The checkbox carries its own text: a separate label beside it
        # overlapped the box on macOS, since the row had no spacing.
        scan_row = QHBoxLayout()
        scan_row.setContentsMargins(0, 0, 0, 0)
        self.scan_tool_checkbox = CheckBox()
        self.scan_tool_checkbox.toggled.connect(self._on_scan_tool_toggled)
        scan_row.addWidget(self.scan_tool_checkbox)
        scan_row.addStretch(1)
        scan_row.addWidget(InfoButton("settings_experimental_info"))
        box.addLayout(scan_row)
        self.scan_tool_help = self._help_label(box, indent)

        # --- Footer --------------------------------------------------
        root.addSpacing(20)
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.done_button = QPushButton()
        style_primary_button(self.done_button)
        self.done_button.setDefault(True)
        self.done_button.clicked.connect(self.accept)
        footer.addWidget(self.done_button)
        root.addLayout(footer)

        # Keeps the window a constant width whatever the language.
        spacer = QWidget()
        spacer.setFixedSize(_CONTENT_WIDTH, 0)
        root.addWidget(spacer)

    def _box(self, layout: QVBoxLayout) -> tuple[QLabel, QVBoxLayout]:
        """A section: its title above a framed panel. Returns the title label
        and the panel's content layout."""
        title = make_section_title(layout)
        return title, make_panel(layout)

    def _checkbox(self, layout: QVBoxLayout, key: str, last: bool = False) -> CheckBox:
        checkbox = CheckBox()
        checkbox.toggled.connect(lambda checked: self._settings().setValue(key, checked))
        checkbox.setProperty("settings_key", key)
        layout.addWidget(checkbox)
        if not last:
            layout.addSpacing(6)
        return checkbox

    def _help_label(self, layout: QVBoxLayout, indent: int = 0) -> QLabel:
        layout.addSpacing(4)
        label = QLabel()
        label.setStyleSheet(_HELP_STYLE)
        label.setWordWrap(True)
        # Fixed (not maximum) width, so the wrapped height is computed
        # correctly (the same approach as ModeSwitchDialog's detail label).
        label.setFixedWidth(_INNER_WIDTH - indent)
        row = QHBoxLayout()
        row.setContentsMargins(indent, 0, 0, 0)
        row.addWidget(label)
        layout.addLayout(row)
        return label

    # ------------------------------------------------------------------
    def _load_values(self) -> None:
        settings = self._settings()
        for checkbox in (self.reopen_checkbox, self.quick_tour_checkbox, self.check_updates_checkbox,
                         self.sounds_checkbox, self.cache_checkbox):
            key = checkbox.property("settings_key")
            checkbox.blockSignals(True)
            checkbox.setChecked(settings.value(key, True, type=bool))
            checkbox.blockSignals(False)
        current = i18n.current_language()
        radio = self.language_radios.get(current) or next(iter(self.language_radios.values()))
        radio.blockSignals(True)
        radio.setChecked(True)
        radio.blockSignals(False)
        self.suffix_edit.setText(settings.value(EXPORT_SUFFIX_KEY, DEFAULT_EXPORT_SUFFIX, type=str))
        self.scan_tool_checkbox.blockSignals(True)
        self.scan_tool_checkbox.setChecked(settings.value(SCAN_TOOL_ENABLED_KEY, False, type=bool))
        self.scan_tool_checkbox.blockSignals(False)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(i18n.tr("settings_title"))
        self.general_title.setText(i18n.tr("settings_section_general"))
        self.language_label.setText(i18n.tr("settings_language"))
        self.reopen_checkbox.setText(i18n.tr("settings_reopen_last_session"))
        self.quick_tour_checkbox.setText(i18n.tr("settings_quick_tour_at_startup"))
        self.check_updates_checkbox.setText(i18n.tr("settings_check_updates_at_startup"))
        self.sounds_checkbox.setText(i18n.tr("settings_play_sounds"))
        self.sessions_title.setText(i18n.tr("settings_section_sessions"))
        self.cache_checkbox.setText(i18n.tr("settings_session_preview_cache"))
        self.cache_help.setText(i18n.tr("settings_session_preview_cache_help"))
        self.export_title.setText(i18n.tr("settings_section_export"))
        self.format_label.setText(i18n.tr("settings_export_format"))
        self.suffix_label.setText(i18n.tr("settings_export_suffix"))
        self.export_help.setText(i18n.tr("settings_export_help"))
        self.experimental_title.setText(i18n.tr("settings_section_experimental"))
        self.scan_tool_checkbox.setText(i18n.tr("settings_scan_tool_enabled"))
        self.scan_tool_help.setText(i18n.tr("settings_scan_tool_enabled_help"))
        self.done_button.setText(i18n.tr("settings_done_button"))
        # The two grids (General, Export) share one label-column width, so
        # every dropdown/field starts at the same x.
        labels = (self.language_label, self.format_label, self.suffix_label)
        for label in labels:
            label.setMinimumWidth(0)
        width = max(label.sizeHint().width() for label in labels)
        for label in labels:
            label.setMinimumWidth(width)

        index = self._settings().value(EXPORT_FORMAT_KEY, 0, type=int)
        self.format_combo.blockSignals(True)
        self.format_combo.clear()
        for key in ("export_filter_png", "export_filter_jpg", "export_filter_tiff"):
            self.format_combo.addItem(i18n.tr(key))
        self.format_combo.setCurrentIndex(index if 0 <= index < 3 else 0)
        self.format_combo.blockSignals(False)

    # ------------------------------------------------------------------
    def _on_language_changed(self, code: str) -> None:
        self.main_window.change_language(code)
        self.retranslate_ui()

    def _on_scan_tool_toggled(self, checked: bool) -> None:
        # The main window may refuse (a capture is running): resync the box.
        applied = self.main_window.set_scan_tool_enabled(checked)
        if applied != checked:
            self.scan_tool_checkbox.blockSignals(True)
            self.scan_tool_checkbox.setChecked(applied)
            self.scan_tool_checkbox.blockSignals(False)

    def _on_format_changed(self, index: int) -> None:
        if index >= 0:
            self._settings().setValue(EXPORT_FORMAT_KEY, index)

    def _on_suffix_edited(self, text: str) -> None:
        self._settings().setValue(EXPORT_SUFFIX_KEY, text)
