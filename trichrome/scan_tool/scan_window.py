"""Standalone scan-capture tool window.

Trigger a shutter release on a tethered camera, download the result to a
configured folder under a roll-name+increment naming scheme, and record which
of the 3 capture modes it was shot in. Optionally also saves a processed JPG
preview (see process.py) - still does **not** import anything into a
Trichr-o-matic session (the "Add to Current Session" button is a
placeholder for that, wired up once this tool moves out of standalone
testing) - see CLAUDE.md's "Negative scan tool" section for the standalone-
first rationale. Run standalone via ``python3 -m trichrome.scan_tool``.
"""
from __future__ import annotations

import datetime
import os
from typing import Callable

from PySide6.QtCore import QSettings, Qt, QThread, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from .. import i18n
from ..widgets.alert_dialog import show_alert
from . import gphoto_backend, manifest, naming, process
from .capture_worker import CaptureWorker
from .process_worker import ProcessWorker

ORG_NAME = "TrichromeMaker"
APP_NAME = "ScanTool"

# (mode key, i18n label key, invert-on-import default)
MODES = (
    ("bw", "scan_mode_bw", True),
    ("color", "scan_mode_color", True),
    ("color_reversal", "scan_mode_color_reversal", False),
)

# Light mode 0 = external (no on-screen backlight), 1 = white (always on),
# 2 = RGB (white at rest for framing; Capture drives it through the 3
# sequence colors below and back).
_LIGHT_MODE_KEYS = ("scan_light_external", "scan_light_white", "scan_light_rgb")
_RGB_CHANNEL_COLORS = {"R": QColor(255, 0, 0), "G": QColor(0, 255, 0), "B": QColor(0, 0, 255)}
_RGB_SEQUENCE = ("R", "G", "B")
# Gives the screen (and any camera auto-metering) a moment to settle on the
# new color before the shutter fires - an LCD/OLED color swap and macOS's
# own window compositing aren't instantaneous.
_LIGHT_SETTLE_DELAY_MS = 400

_POLL_INTERVAL_MS = 3000


class BacklightWindow(QWidget):
    """A plain solid-color top-level window - drag it onto whichever
    display sits behind the scanning rig and use macOS's own fullscreen
    (green traffic-light button) to turn that whole screen into a light
    source. Deliberately not a QDialog - it must stay open, movable and
    independently resizable/fullscreenable while the main tool window keeps
    working, not modal to it.

    ``on_capture``, when given, is wired to Cmd+Return/Cmd+Enter (Qt maps
    Ctrl<->Cmd automatically on macOS) so Capture can be triggered without
    clicking back over to the main tool window - useful since this window is
    usually the one actually in front/focused while positioning film on the
    backlight."""

    def __init__(self, on_capture: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.setWindowTitle(i18n.tr("scan_light_window_title"))
        self.resize(800, 600)
        if on_capture is not None:
            for seq in ("Ctrl+Return", "Ctrl+Enter"):
                shortcut = QShortcut(QKeySequence(seq), self)
                shortcut.activated.connect(on_capture)

    def set_color(self, color: QColor) -> None:
        self.setStyleSheet(f"background-color: {color.name()};")

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


class ScanToolWindow(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("scan_window_title"))
        self.resize(380, 640)

        self._settings = QSettings(ORG_NAME, APP_NAME)
        self._cameras: list[gphoto_backend.DetectedCamera] = []
        self._capturing = False
        self._quality_config_path: str | None = None
        self._backlight_window: BacklightWindow | None = None
        self._rgb_sequence_active = False
        self._rgb_sequence_step = 0
        self._rgb_sequence_paths: list[str] = []
        self._rgb_sequence_port: str | None = None

        self._build_ui()
        self._load_settings()
        self._sync_mode_note()

        self._thread: QThread | None = None
        self._worker: CaptureWorker | None = None
        self._process_thread: QThread | None = None
        self._process_worker: ProcessWorker | None = None

        # Cmd+Return/Cmd+Enter triggers Capture from this window too, not
        # just the backlight window (BacklightWindow's own on_capture) -
        # useful when the tool window itself still has focus.
        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            shortcut = QShortcut(QKeySequence(seq), self)
            shortcut.activated.connect(self._on_capture_clicked)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_devices)
        self._poll_timer.start()
        self._poll_devices()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        device_group = QGroupBox(i18n.tr("scan_device_group"))
        device_layout = QVBoxLayout(device_group)
        status_row = QHBoxLayout()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #888; font-size: 14px;")
        status_row.addWidget(self.status_dot)
        self.status_label = QLabel(i18n.tr("scan_device_not_connected"))
        status_row.addWidget(self.status_label, 1)
        self.refresh_button = QPushButton(i18n.tr("scan_device_refresh"))
        self.refresh_button.clicked.connect(self._poll_devices)
        status_row.addWidget(self.refresh_button)
        device_layout.addLayout(status_row)
        self.camera_combo = QComboBox()
        self.camera_combo.currentIndexChanged.connect(self._on_camera_selected)
        device_layout.addWidget(self.camera_combo)
        self.quality_label = QLabel()
        device_layout.addWidget(self.quality_label)
        self.quality_combo = QComboBox()
        self.quality_combo.currentTextChanged.connect(self._on_quality_changed)
        self.quality_combo.hide()
        device_layout.addWidget(self.quality_combo)
        layout.addWidget(device_group)

        mode_group = QGroupBox(i18n.tr("scan_mode_group"))
        mode_layout = QVBoxLayout(mode_group)
        mode_buttons_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self._mode_buttons = []
        for idx, (_key, label_key, _invert) in enumerate(MODES):
            # QPushButton treats a single "&" as a mnemonic marker (would
            # otherwise render "Black & White" as "Black _White") - escape
            # it as a literal ampersand.
            btn = QPushButton(i18n.tr(label_key).replace("&", "&&"))
            btn.setCheckable(True)
            self.mode_group.addButton(btn, idx)
            mode_buttons_row.addWidget(btn)
            self._mode_buttons.append(btn)
        self._mode_buttons[0].setChecked(True)
        self.mode_group.idClicked.connect(lambda _id: self._sync_mode_note())
        mode_layout.addLayout(mode_buttons_row)
        self.mode_note_label = QLabel()
        self.mode_note_label.setWordWrap(True)
        self.mode_note_label.setStyleSheet("color: #888; font-size: 11px;")
        mode_layout.addWidget(self.mode_note_label)
        layout.addWidget(mode_group)

        light_group = QGroupBox(i18n.tr("scan_light_group"))
        light_layout = QVBoxLayout(light_group)
        light_buttons_row = QHBoxLayout()
        self.light_mode_group = QButtonGroup(self)
        self.light_mode_group.setExclusive(True)
        self._light_mode_buttons = []
        for idx, label_key in enumerate(_LIGHT_MODE_KEYS):
            btn = QPushButton(i18n.tr(label_key).replace("&", "&&"))
            btn.setCheckable(True)
            self.light_mode_group.addButton(btn, idx)
            light_buttons_row.addWidget(btn)
            self._light_mode_buttons.append(btn)
        self._light_mode_buttons[0].setChecked(True)
        self.light_mode_group.idClicked.connect(lambda _id: self._on_light_mode_changed())
        light_layout.addLayout(light_buttons_row)
        self.light_note_label = QLabel()
        self.light_note_label.setWordWrap(True)
        self.light_note_label.setStyleSheet("color: #888; font-size: 11px;")
        self.light_note_label.hide()
        light_layout.addWidget(self.light_note_label)
        self.process_checkbox = QCheckBox(i18n.tr("scan_process_checkbox"))
        self.process_checkbox.setToolTip(i18n.tr("scan_process_tooltip"))
        self.process_checkbox.toggled.connect(lambda _checked: self._save_settings())
        light_layout.addWidget(self.process_checkbox)
        layout.addWidget(light_group)

        location_group = QGroupBox(i18n.tr("scan_location_group"))
        location_layout = QVBoxLayout(location_group)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel(i18n.tr("scan_base_folder_label")))
        self.base_folder_edit = QLineEdit()
        self.base_folder_edit.textChanged.connect(self._save_settings)
        folder_row.addWidget(self.base_folder_edit, 1)
        browse_button = QPushButton(i18n.tr("scan_base_folder_browse"))
        browse_button.clicked.connect(self._browse_base_folder)
        folder_row.addWidget(browse_button)
        location_layout.addLayout(folder_row)

        subfolder_row = QHBoxLayout()
        subfolder_row.addWidget(QLabel(i18n.tr("scan_subfolder_label")))
        self.subfolder_edit = QLineEdit()
        self.subfolder_edit.textChanged.connect(self._save_settings)
        subfolder_row.addWidget(self.subfolder_edit, 1)
        location_layout.addLayout(subfolder_row)

        self.use_roll_subfolder_checkbox = QCheckBox(i18n.tr("scan_use_roll_as_subfolder"))
        self.use_roll_subfolder_checkbox.toggled.connect(self._on_use_roll_subfolder_toggled)
        location_layout.addWidget(self.use_roll_subfolder_checkbox)

        roll_row = QHBoxLayout()
        roll_row.addWidget(QLabel(i18n.tr("scan_roll_name_label")))
        self.roll_name_edit = QLineEdit()
        self.roll_name_edit.textChanged.connect(self._on_roll_name_changed)
        roll_row.addWidget(self.roll_name_edit, 1)
        location_layout.addLayout(roll_row)

        self.subfolder_preview_label = QLabel()
        self.subfolder_preview_label.setStyleSheet("color: #888; font-size: 11px;")
        self.subfolder_preview_label.hide()
        location_layout.addWidget(self.subfolder_preview_label)

        next_row = QHBoxLayout()
        next_row.addWidget(QLabel(i18n.tr("scan_next_number_label")))
        self.next_number_spin = QSpinBox()
        self.next_number_spin.setRange(1, 9999)
        self.next_number_spin.valueChanged.connect(self._save_settings)
        next_row.addWidget(self.next_number_spin, 1)
        location_layout.addLayout(next_row)

        layout.addWidget(location_group)

        self.capture_button = QPushButton(i18n.tr("scan_capture_button"))
        self.capture_button.setEnabled(False)
        self.capture_button.setMinimumHeight(40)
        self.capture_button.clicked.connect(self._on_capture_clicked)
        layout.addWidget(self.capture_button)

        self.capture_status_label = QLabel(i18n.tr("scan_ready_status"))
        self.capture_status_label.setStyleSheet("color: #888;")
        layout.addWidget(self.capture_status_label)

        history_group = QGroupBox(i18n.tr("scan_history_group"))
        history_layout = QVBoxLayout(history_group)
        self.history_list = QListWidget()
        history_layout.addWidget(self.history_list)
        self.add_to_session_button = QPushButton(i18n.tr("scan_add_to_session_button"))
        self.add_to_session_button.clicked.connect(self._on_add_to_session_clicked)
        history_layout.addWidget(self.add_to_session_button)
        layout.addWidget(history_group, 1)

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
        fields = (
            self.base_folder_edit, self.subfolder_edit, self.roll_name_edit,
            self.next_number_spin, self.use_roll_subfolder_checkbox, self.process_checkbox,
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
        self.process_checkbox.setChecked(self._settings.value("process_enabled", False, type=bool))
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
        # moment the tool is relaunched, only once the user actively picks
        # a mode.
        self._sync_light_note()

    def _save_settings(self) -> None:
        self._settings.setValue("base_folder", self.base_folder_edit.text())
        self._settings.setValue("subfolder", self.subfolder_edit.text())
        self._settings.setValue("roll_name", self.roll_name_edit.text())
        self._settings.setValue("next_number", self.next_number_spin.value())
        self._settings.setValue("use_roll_as_subfolder", self.use_roll_subfolder_checkbox.isChecked())
        self._settings.setValue("process_enabled", self.process_checkbox.isChecked())
        self._settings.setValue("mode_index", self.mode_group.checkedId())
        self._settings.setValue("light_mode_index", self.light_mode_group.checkedId())

    # ------------------------------------------------------------------
    # Mode
    # ------------------------------------------------------------------
    def _current_mode(self) -> tuple[str, str, bool]:
        return MODES[max(0, self.mode_group.checkedId())]

    def _sync_mode_note(self) -> None:
        _key, _label_key, invert = self._current_mode()
        note_key = "scan_mode_invert_note" if invert else "scan_mode_no_invert_note"
        self.mode_note_label.setText(i18n.tr(note_key))
        self._save_settings()

    # ------------------------------------------------------------------
    # Scan light - uses the computer screen as an improvised backlight for
    # negative scanning. White and RGB modes both show the same plain white
    # window at rest (RGB just for framing/focus before a capture - white is
    # easier to see by than any single primary color); RGB mode additionally
    # drives the window through a red/green/blue capture sequence (see
    # _start_rgb_sequence below) whenever Capture is pressed, then returns it
    # to white afterward.
    # ------------------------------------------------------------------
    def _on_light_mode_changed(self) -> None:
        self._sync_light_note()
        self._sync_backlight_window()
        self._save_settings()

    def _sync_light_note(self) -> None:
        if self.light_mode_group.checkedId() == 2:
            self.light_note_label.setText(i18n.tr("scan_light_rgb_note"))
            self.light_note_label.show()
        else:
            self.light_note_label.hide()

    def _ensure_backlight_window(self) -> "BacklightWindow":
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

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------
    def _on_capture_clicked(self) -> None:
        # The Capture button already disables itself while a capture is in
        # flight, but the Cmd+Return shortcut (wired on this window and the
        # backlight window both) bypasses that - guard here too.
        if self._capturing:
            return
        port = self._selected_port()
        if not port:
            show_alert(self, i18n.tr("scan_error_title"), i18n.tr("scan_no_camera_error"))
            return

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
        dest_folder = self._destination_folder()
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
        allow_process: bool = True,
    ) -> None:
        """``entries`` is (saved path, channel-or-None) pairs - a single
        pair for a normal shot, 3 for a completed (or partially completed,
        on error) RGB triplet, all sharing one index number."""
        dest_folder = self._destination_folder()
        mode_key, label_key, invert = self._current_mode()
        index = self.next_number_spin.value()
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        for path, channel in entries:
            basename = os.path.basename(path)
            manifest.append_entry(dest_folder, basename, mode_key, invert, channel=channel)
            suffix_text = f" ({channel})" if channel else ""
            self.history_list.addItem(
                f"#{index:03d}{suffix_text} — {basename} — {i18n.tr(label_key)} — {timestamp}"
            )
        if advance_index and entries:
            self.next_number_spin.setValue(index + 1)
        self._save_settings()
        self._end_capture_ui()
        if allow_process and entries and self.process_checkbox.isChecked():
            self._start_processing(entries, mode_key, invert, dest_folder, index)

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
        if entries_to_log:
            # A partial (failed mid-triplet) RGB sequence can't be
            # processed - process_rgb_triplet needs all 3 channels.
            self._finish_capture(entries_to_log, advance_index=False, allow_process=False)
        else:
            self._end_capture_ui()

    def _on_capture_error(self, message: str) -> None:
        self._handle_capture_failure(message)

    # ------------------------------------------------------------------
    # Post-capture processing (see process.py) - optional, gated by
    # process_checkbox in the Scan Light panel. Runs in its own QThread,
    # entirely independent of the capture thread/state above, so a slow
    # RGB-triplet recompose never blocks the next capture.
    # ------------------------------------------------------------------
    def _start_processing(
        self, entries: list[tuple[str, str | None]], mode_key: str, invert: bool,
        dest_folder: str, index: int,
    ) -> None:
        is_color = mode_key != "bw"
        channel_paths = {ch: p for p, ch in entries if ch}

        if len(channel_paths) == 3:
            out_basename = naming.base_name(self.roll_name_edit.text(), index)

            def job() -> list[str]:
                return [process.process_rgb_triplet(channel_paths, invert, dest_folder, out_basename)]
        else:
            paths = [p for p, _ch in entries]

            def job() -> list[str]:
                results = []
                for p in paths:
                    try:
                        results.append(process.process_single(p, invert, is_color, dest_folder))
                    except Exception:
                        # Best-effort preview - one unreadable file (e.g. a
                        # RAW format PIL can't decode) shouldn't stop the
                        # rest of the batch from being processed.
                        continue
                return results

        self.capture_status_label.setText(i18n.tr("scan_processing_status"))
        self._process_thread = QThread(self)
        self._process_worker = ProcessWorker(job)
        self._process_worker.moveToThread(self._process_thread)
        self._process_thread.started.connect(self._process_worker.run)
        self._process_worker.finished.connect(self._on_process_finished)
        self._process_worker.error.connect(self._on_process_error)
        self._process_worker.finished.connect(self._process_thread.quit)
        self._process_worker.error.connect(self._process_thread.quit)
        self._process_worker.finished.connect(self._process_worker.deleteLater)
        self._process_worker.error.connect(self._process_worker.deleteLater)
        self._process_thread.finished.connect(self._process_thread.deleteLater)
        self._process_thread.finished.connect(self._clear_process_thread_refs)
        self._process_thread.start()

    def _clear_process_thread_refs(self) -> None:
        self._process_thread = None
        self._process_worker = None

    def _on_process_finished(self, paths: list[str]) -> None:
        for path in paths:
            self.history_list.addItem(f"    ↳ {i18n.tr('scan_processed_label')}: {os.path.basename(path)}")
        self.capture_status_label.setText(i18n.tr("scan_ready_status"))

    def _on_process_error(self, message: str) -> None:
        show_alert(self, i18n.tr("scan_error_title"), message)
        self.capture_status_label.setText(i18n.tr("scan_ready_status"))

    # ------------------------------------------------------------------
    # Add to session (placeholder)
    # ------------------------------------------------------------------
    def _on_add_to_session_clicked(self) -> None:
        # Intentionally a no-op for now - will import this session's
        # captures into the main app's active Trichr-o-matic session once
        # this tool is wired in there (still deliberately standalone-only
        # for now, per the original build plan in CLAUDE.md).
        pass

    def closeEvent(self, event) -> None:
        self._poll_timer.stop()
        if self._backlight_window is not None:
            self._backlight_window.close()
        if self._process_thread is not None and self._process_thread.isRunning():
            # A processed-JPG job (auto-align + compose can take a couple of
            # seconds) may still be running - wait for it rather than
            # letting the window disappear out from under a live QThread.
            self._process_thread.wait()
        super().closeEvent(event)
