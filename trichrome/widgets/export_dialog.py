"""Export settings dialog: current photo, a selection, or the whole batch."""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QSettings, QThread
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QProgressBar, QPushButton, QRadioButton, QVBoxLayout,
)

from .. import i18n, imaging
from ..export_worker import BatchExportWorker
from .alert_dialog import show_alert

ORG_NAME = "TrichromeMaker"
APP_NAME = "TrichromeMaker"


class ExportDialog(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.resize(480, 440)
        self._thread: QThread | None = None
        self._worker: BatchExportWorker | None = None
        self._items_to_export: list = []
        self._ok_count = 0
        self._failed_count = 0
        self._last_output_dir: str | None = None

        self._build_ui()
        self._restore_output_dir()
        self.retranslate_ui()
        QShortcut(QKeySequence.Close, self, activated=self.close)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        out_row = QHBoxLayout()
        self.output_folder_label = QLabel()
        self.same_as_source_checkbox = QCheckBox()
        self.same_as_source_checkbox.toggled.connect(self._on_same_as_source_toggled)
        self.browse_output_button = QPushButton()
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
        self.suffix_edit = QLineEdit("_trichrome")
        suffix_row.addWidget(self.suffix_label)
        suffix_row.addWidget(self.suffix_edit, stretch=1)
        root.addLayout(suffix_row)

        format_row = QHBoxLayout()
        self.format_label = QLabel()
        self.format_combo = QComboBox()
        format_row.addWidget(self.format_label)
        format_row.addWidget(self.format_combo, stretch=1)
        root.addLayout(format_row)

        self._batch_active = len(self.main_window.batch_items) >= 2
        self.scope_group_label = QLabel()
        self.scope_current_radio = QRadioButton()
        self.scope_selected_radio = QRadioButton()
        self.scope_all_radio = QRadioButton()
        self.scope_current_radio.setChecked(True)
        self.scope_group_label.setVisible(self._batch_active)
        root.addWidget(self.scope_group_label)
        for rb in (self.scope_current_radio, self.scope_selected_radio, self.scope_all_radio):
            root.addWidget(rb)
            rb.setVisible(self._batch_active)

        self.reveal_in_finder_checkbox = QCheckBox()
        root.addWidget(self.reveal_in_finder_checkbox)

        run_row = QHBoxLayout()
        self.export_button = QPushButton()
        self.export_button.setStyleSheet("font-weight: bold;")
        self.export_button.setDefault(True)  # Enter/Return triggers export with current settings
        self.export_button.clicked.connect(self.start_export)
        self.close_button = QPushButton()
        self.close_button.clicked.connect(self._on_close_clicked)
        run_row.addWidget(self.export_button, stretch=1)
        run_row.addWidget(self.close_button)
        root.addLayout(run_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        root.addWidget(self.progress_bar)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.log_list = QListWidget()
        self.log_list.setMaximumHeight(120)
        root.addWidget(self.log_list)

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

    def _on_same_as_source_toggled(self, checked: bool) -> None:
        self.output_path_edit.setEnabled(not checked)
        self.browse_output_button.setEnabled(not checked)
        QSettings(ORG_NAME, APP_NAME).setValue("export_same_as_source", checked)

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
        self.scope_group_label.setText(i18n.tr("export_scope_group"))
        self.scope_current_radio.setText(i18n.tr("export_scope_current"))
        self.scope_selected_radio.setText(i18n.tr("export_scope_selected", n=n_selected))
        self.scope_all_radio.setText(i18n.tr("export_scope_all", n=n_all))

        self.export_button.setText(i18n.tr("export_confirm_button"))
        self.close_button.setText(i18n.tr("batch_cancel_button") if self._thread is not None else i18n.tr("close_button"))

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
        same_as_source = self.same_as_source_checkbox.isChecked()
        if not same_as_source and not self.output_path_edit.text():
            show_alert(self, i18n.tr("export_dialog_title"), i18n.tr("batch_error_no_output"))
            return

        mw = self.main_window
        format_map = {0: (".png", 8), 1: (".jpg", 8), 2: (".tiff", 16)}
        ext, bit_depth = format_map[self.format_combo.currentIndex()]
        suffix = self.suffix_edit.text()
        output_dir = None if same_as_source else self.output_path_edit.text()

        if not self._batch_active or self.scope_current_radio.isChecked():
            self._export_current(output_dir, suffix, ext, bit_depth)
            return

        if self.scope_selected_radio.isChecked():
            items = [it for it in mw.batch_items if it.selected]
        else:
            items = list(mw.batch_items)

        if not items:
            show_alert(self, i18n.tr("export_dialog_title"), i18n.tr("export_no_items"))
            return

        self._items_to_export = items
        self._last_output_dir = output_dir
        self.log_list.clear()
        self._ok_count = 0
        self._failed_count = 0
        self.progress_bar.setRange(0, len(items))
        self.progress_bar.setValue(0)
        self._set_running(True)

        self._thread = QThread(self)
        self._worker = BatchExportWorker(
            items=items,
            full_res_loader=mw._full_res_image,
            full_res_params=mw._full_res_params,
            full_res_color_loader=mw._full_res_color_image,
            output_dir=output_dir,
            suffix=suffix,
            ext=ext,
            bit_depth=bit_depth,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.item_result.connect(self._on_item_result)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        # See the QThread lifecycle note in batch_window.py: only drop refs
        # once QThread.finished fires, not merely worker.finished.
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_thread_refs)
        self._thread.start()

    def _export_current(self, output_dir: str | None, suffix: str, ext: str, bit_depth: int) -> None:
        mw = self.main_window
        is_normal = (0 <= mw.batch_current_index < len(mw.batch_items)
                     and mw.batch_items[mw.batch_current_index].mode == "normal")
        ref = mw._reference_layer()
        if is_normal:
            if not ref.has_image():
                show_alert(self, i18n.tr("export_dialog_title"), i18n.tr("dialog_export_missing"))
                return
            if output_dir is None:
                output_dir = os.path.dirname(ref.path) if ref.path else ""
            image = imaging.apply_invert(mw._full_res_color_image(ref), ref.invert)
            gc = mw.global_corr
            global_params = (gc.black_point, gc.white_point, gc.gamma, gc.exposure, gc.brightness, gc.contrast,
                              gc.shadows, gc.highlights, gc.saturation, gc.temperature, gc.tint,
                              {ch: tuple(pts) for ch, pts in gc.curves.items()}, gc.black_white_active)
            rgb = imaging.compose_normal(image, global_params)
        else:
            if not all(l.has_image() for l in mw.layers):
                show_alert(self, i18n.tr("export_dialog_title"), i18n.tr("dialog_export_missing"))
                return
            if output_dir is None:
                output_dir = os.path.dirname(ref.path) if ref.path else ""
            images = [mw._full_res_image(l) for l in mw.layers]
            geo_params = [mw._full_res_params(l, ref) for l in mw.layers]
            tone_params = [(l.black_point, l.white_point, l.gamma, l.exposure, l.brightness, l.contrast,
                            l.shadows, l.highlights, l.invert) for l in mw.layers]
            gc = mw.global_corr
            global_params = (gc.black_point, gc.white_point, gc.gamma, gc.exposure, gc.brightness, gc.contrast,
                              gc.shadows, gc.highlights, gc.saturation, gc.temperature, gc.tint,
                              {ch: tuple(pts) for ch, pts in gc.curves.items()}, gc.black_white_active)
            rgb = imaging.compose_trichrome(images, geo_params, tone_params, ref.color_index, global_params)
        cr = mw.crop
        rgb = imaging.apply_crop(rgb, cr.rotation, cr.mirror_h, cr.mirror_v, cr.x, cr.y, cr.width, cr.height)

        base = mw._current_export_base_name()
        out_path = os.path.join(output_dir, f"{base}{suffix}{ext}")
        try:
            imaging.save_image(out_path, rgb, bit_depth=bit_depth)
        except Exception as exc:
            show_alert(self, i18n.tr("dialog_export_error_title"),
                                  i18n.tr("dialog_export_error_text", error=exc))
            return
        if not self.same_as_source_checkbox.isChecked():
            QSettings(ORG_NAME, APP_NAME).setValue("export_output_dir", output_dir)
        mw.statusBar().showMessage(i18n.tr("status_exported", path=out_path), 8000)
        if self.reveal_in_finder_checkbox.isChecked():
            subprocess.run(["open", "-R", out_path])
        self.accept()

    # ------------------------------------------------------------------
    def _set_running(self, running: bool) -> None:
        self.export_button.setEnabled(not running)
        self.browse_output_button.setEnabled(not running and not self.same_as_source_checkbox.isChecked())
        self.same_as_source_checkbox.setEnabled(not running)
        self.suffix_edit.setEnabled(not running)
        self.format_combo.setEnabled(not running)
        self.scope_current_radio.setEnabled(not running)
        self.scope_selected_radio.setEnabled(not running)
        self.scope_all_radio.setEnabled(not running)
        self.close_button.setText(i18n.tr("batch_cancel_button") if running else i18n.tr("close_button"))

    def _on_progress(self, done: int, total: int) -> None:
        self.progress_bar.setValue(done)
        self.status_label.setText(i18n.tr("batch_status_running", i=done, n=total))

    def _on_item_result(self, row: int, success: bool, message: str) -> None:
        item = self._items_to_export[row]
        if success:
            self._ok_count += 1
            self.log_list.addItem(f"OK  {item.base} → {message}")
        else:
            self._failed_count += 1
            self.log_list.addItem(f"FAIL  {item.base}: {message}")

    def _on_finished(self) -> None:
        cancelled = self._worker is not None and self._worker._cancelled
        total = len(self._items_to_export)
        done = self._ok_count + self._failed_count
        self._set_running(False)
        if cancelled and done < total:
            self.status_label.setText(i18n.tr("batch_status_cancelled", i=done, n=total))
        else:
            self.status_label.setText(i18n.tr("batch_status_done", ok=self._ok_count, failed=self._failed_count))
        if not self.same_as_source_checkbox.isChecked():
            QSettings(ORG_NAME, APP_NAME).setValue("export_output_dir", self.output_path_edit.text())
        # Nothing to reveal for "same as source" batches - each item lands
        # next to its own source file, so there's no single shared folder.
        if self._ok_count > 0 and self._last_output_dir and self.reveal_in_finder_checkbox.isChecked():
            subprocess.run(["open", self._last_output_dir])

    def _clear_thread_refs(self) -> None:
        self._thread = None
        self._worker = None

    def _on_close_clicked(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
        else:
            self.reject()

    def closeEvent(self, event) -> None:
        if self._worker is not None:
            self._worker.cancel()
        super().closeEvent(event)
