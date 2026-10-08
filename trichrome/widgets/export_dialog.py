"""Export settings dialog: current photo, a selection, or the whole batch."""
from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLayout, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from .. import i18n
from .alert_dialog import show_alert
from .button_style import style_primary_button, style_secondary_button
from .settings_dialog import DEFAULT_EXPORT_SUFFIX, EXPORT_FORMAT_KEY, EXPORT_SUFFIX_KEY
from .checkbox import CheckBox, RadioButton
from .combo_box import ComboBox

ORG_NAME = "TrichromeMaker"
APP_NAME = "TrichromeMaker"



class ExportDialog(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window

        self._build_ui()
        self._restore_output_dir()
        self.retranslate_ui()
        self._restore_format_and_suffix()
        QShortcut(QKeySequence.Close, self, activated=self.close)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        # Size follows the content, like Preferences (SetFixedSize), so the
        # window can't be sized from one font metric and clip another.
        root.setSizeConstraint(QLayout.SetFixedSize)

        out_row = QHBoxLayout()
        self.output_folder_label = QLabel()
        self.same_as_source_checkbox = CheckBox()
        self.same_as_source_checkbox.toggled.connect(self._on_same_as_source_toggled)
        self.browse_output_button = QPushButton()
        style_secondary_button(self.browse_output_button)
        self.browse_output_button.clicked.connect(self.browse_output_folder)
        out_row.addWidget(self.output_folder_label)
        out_row.addStretch(1)
        out_row.addWidget(self.same_as_source_checkbox)
        out_row.addWidget(self.browse_output_button)
        root.addLayout(out_row)

        self.output_path_edit = QLineEdit()
        self.output_path_edit.setReadOnly(True)
        root.addWidget(self.output_path_edit)

        suffix_row = QHBoxLayout()
        self.suffix_label = QLabel()
        self.suffix_edit = QLineEdit()
        suffix_row.addWidget(self.suffix_label)
        suffix_row.addWidget(self.suffix_edit, stretch=1)
        root.addLayout(suffix_row)

        format_row = QHBoxLayout()
        self.format_label = QLabel()
        self.format_combo = ComboBox()
        format_row.addWidget(self.format_label)
        format_row.addWidget(self.format_combo, stretch=1)
        root.addLayout(format_row)

        self._batch_active = len(self.main_window.batch_items) >= 2
        self.scope_current_radio = RadioButton()
        self.scope_selected_radio = RadioButton()
        self.scope_all_radio = RadioButton()
        self._scope_radios = {
            "current": self.scope_current_radio,
            "selected": self.scope_selected_radio,
            "all": self.scope_all_radio,
        }
        # Last-used scope, remembered across launches (saved on toggle).
        saved_scope = QSettings(ORG_NAME, APP_NAME).value("export_scope", "current")
        self._scope_radios.get(saved_scope, self.scope_current_radio).setChecked(True)
        for key, rb in self._scope_radios.items():
            root.addWidget(rb)
            rb.setVisible(self._batch_active)
            rb.toggled.connect(lambda checked, key=key: self._on_scope_toggled(key, checked))

        self.reveal_in_finder_checkbox = CheckBox()
        root.addWidget(self.reveal_in_finder_checkbox)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.export_button = QPushButton()
        style_primary_button(self.export_button)
        self.export_button.setDefault(True)  # Enter/Return triggers export with current settings
        self.export_button.clicked.connect(self.start_export)
        footer.addWidget(self.export_button)
        root.addSpacing(14)
        root.addLayout(footer)

        # Keeps the window a constant width whatever the language, like
        # Preferences does (420px content + 2x20px margins).
        spacer = QWidget()
        spacer.setFixedSize(440, 0)
        root.addWidget(spacer)

    def _restore_output_dir(self) -> None:
        settings = QSettings(ORG_NAME, APP_NAME)
        output_dir = settings.value("export_output_dir", "") or settings.value("last_export_dir", "")
        if output_dir:
            self.output_path_edit.setText(output_dir)
        same_as_source = settings.value("export_same_as_source", False, type=bool)
        self.same_as_source_checkbox.setChecked(same_as_source)
        self._on_same_as_source_toggled(same_as_source)
        reveal_in_finder = settings.value("export_reveal_in_finder", True, type=bool)
        self.reveal_in_finder_checkbox.setChecked(reveal_in_finder)
        self.reveal_in_finder_checkbox.toggled.connect(self._on_reveal_in_finder_toggled)

    def _restore_format_and_suffix(self) -> None:
        """Last-used format/suffix - the same QSettings keys Settings > Export
        edits, so the two always agree."""
        settings = QSettings(ORG_NAME, APP_NAME)
        index = settings.value(EXPORT_FORMAT_KEY, 0, type=int)
        self.format_combo.setCurrentIndex(index if 0 <= index < self.format_combo.count() else 0)
        self.suffix_edit.setText(settings.value(EXPORT_SUFFIX_KEY, DEFAULT_EXPORT_SUFFIX, type=str))
        self.format_combo.currentIndexChanged.connect(
            lambda i: QSettings(ORG_NAME, APP_NAME).setValue(EXPORT_FORMAT_KEY, i) if i >= 0 else None)
        self.suffix_edit.textEdited.connect(
            lambda text: QSettings(ORG_NAME, APP_NAME).setValue(EXPORT_SUFFIX_KEY, text))

    def _on_same_as_source_toggled(self, checked: bool) -> None:
        self.output_path_edit.setEnabled(not checked)
        self.browse_output_button.setEnabled(not checked)
        QSettings(ORG_NAME, APP_NAME).setValue("export_same_as_source", checked)

    def _on_scope_toggled(self, key: str, checked: bool) -> None:
        if checked:
            QSettings(ORG_NAME, APP_NAME).setValue("export_scope", key)

    def _on_reveal_in_finder_toggled(self, checked: bool) -> None:
        QSettings(ORG_NAME, APP_NAME).setValue("export_reveal_in_finder", checked)

    # ------------------------------------------------------------------
    def retranslate_ui(self) -> None:
        self.setWindowTitle(i18n.tr("export_dialog_title"))
        self.output_folder_label.setText(i18n.tr("batch_output_folder_label"))
        self.browse_output_button.setText(i18n.tr("batch_browse_button"))
        self.same_as_source_checkbox.setText(i18n.tr("export_same_as_source"))
        self.same_as_source_checkbox.setToolTip(i18n.tr("export_same_as_source_tooltip"))
        self.reveal_in_finder_checkbox.setText(i18n.tr("export_reveal_in_finder"))
        self.suffix_label.setText(i18n.tr("batch_suffix_label"))
        self.format_label.setText(i18n.tr("batch_format_label"))

        current_format = self.format_combo.currentIndex()
        self.format_combo.blockSignals(True)
        self.format_combo.clear()
        self.format_combo.addItem(i18n.tr("export_filter_png"))
        self.format_combo.addItem(i18n.tr("export_filter_jpg"))
        self.format_combo.addItem(i18n.tr("export_filter_tiff"))
        self.format_combo.setCurrentIndex(max(0, current_format))
        self.format_combo.blockSignals(False)

        mw = self.main_window
        n_all = len(mw.batch_items)
        n_selected = sum(1 for it in mw.batch_items if it.selected)
        self.scope_current_radio.setText(i18n.tr("export_scope_current"))
        self.scope_selected_radio.setText(i18n.tr("export_scope_selected", n=n_selected))
        self.scope_all_radio.setText(i18n.tr("export_scope_all", n=n_all))

        self.export_button.setText(i18n.tr("export_confirm_button"))

    # ------------------------------------------------------------------
    def browse_output_folder(self) -> None:
        start = self.output_path_edit.text() or ""
        folder = QFileDialog.getExistingDirectory(self, i18n.tr("batch_select_output_title"), start)
        if not folder:
            return
        self.output_path_edit.setText(folder)
        QSettings(ORG_NAME, APP_NAME).setValue("export_output_dir", folder)

    # ------------------------------------------------------------------
    def start_export(self) -> None:
        """Validates the settings, hands the job to MainWindow (which owns
        the background thread, so closing this dialog can never destroy a
        running QThread) and closes right away - progress shows in the
        main window's status bar."""
        mw = self.main_window
        if mw.is_export_running():
            show_alert(self, i18n.tr("export_dialog_title"), i18n.tr("export_already_running"))
            return
        same_as_source = self.same_as_source_checkbox.isChecked()
        if not same_as_source and not self.output_path_edit.text():
            show_alert(self, i18n.tr("export_dialog_title"), i18n.tr("batch_error_no_output"))
            return

        format_map = {0: (".png", 8), 1: (".jpg", 8), 2: (".tiff", 16)}
        ext, bit_depth = format_map[self.format_combo.currentIndex()]
        suffix = self.suffix_edit.text()
        output_dir = None if same_as_source else self.output_path_edit.text()

        if not self._batch_active or self.scope_current_radio.isChecked():
            if not (0 <= mw.batch_current_index < len(mw.batch_items)):
                show_alert(self, i18n.tr("export_dialog_title"), i18n.tr("export_no_items"))
                return
            item = mw.batch_items[mw.batch_current_index]
            layers = [item.normal_layer] if item.mode == "normal" else item.layers
            if not all(l.has_image() for l in layers):
                show_alert(self, i18n.tr("export_dialog_title"), i18n.tr("dialog_export_missing"))
                return
            items = [item]
        elif self.scope_selected_radio.isChecked():
            items = [it for it in mw.batch_items if it.selected]
        else:
            items = list(mw.batch_items)

        if not items:
            show_alert(self, i18n.tr("export_dialog_title"), i18n.tr("export_no_items"))
            return

        if not same_as_source:
            QSettings(ORG_NAME, APP_NAME).setValue("export_output_dir", output_dir)
        mw.start_background_export(
            items, output_dir, suffix, ext, bit_depth,
            reveal_in_finder=self.reveal_in_finder_checkbox.isChecked())
        self.accept()
