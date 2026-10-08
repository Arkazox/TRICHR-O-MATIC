"""Check for Updates - app menu, right below Preferences and Keyboard
Shortcuts. Logo, app name, current version, and (once the background
check resolves) either "You're up to date" or an Update button. Where
self-update can run (self_update.can_self_update), Update downloads and
checks the new version here with a progress bar, then offers Restart Now;
MainWindow reads `staged_update` after exec() and does the quit-and-swap.
Otherwise, or if the download fails, it opens the release page. Styled like
the app's other own dialogs (WelcomeDialog, ConfirmDialog), not native
QMessageBox chrome.

Owns its own QThread rather than routing through MainWindow: unlike
export/HQ Preview/batch import, this check has no MainWindow state to
snapshot, so there's nothing MainWindow-side to gain from it.

**Confirmed crash**: the worker's run() is one blocking urlopen() call, not
an event loop we can interrupt, and `show_check_updates_dialog` holds no
reference to the dialog past `.exec()` - so if the thread is still running
when the dialog closes, the dialog (and the QThread with it) is garbage
collected while that thread is still live, which aborts the process
("QThread: Destroyed while thread is still running"), reproduced with a
sandboxed/offline run. done() calls quit()+wait() to block until the
request actually returns (bounded by the request's own timeout) before
letting the dialog close, the same trade _stop_preview_upgrade makes on
app quit - closing the dialog the instant it opens is the rare case, and
the request is normally sub-second."""
from __future__ import annotations

from PySide6.QtCore import QThread, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLayout, QProgressBar, QPushButton, QVBoxLayout

from .. import i18n, self_update
from ..paths import resource_path
from ..update_checker import UpdateCheckWorker, parse_version
from ..version import __version__
from .button_style import style_primary_button, style_secondary_button
from .checkbox import ACCENT, ACCENT_LIGHT

_LOGO_SIZE = 96
_TEXT_WIDTH = 320


class UpdateCheckDialog(QDialog):
    def __init__(self, parent, initial_result: tuple[str, str, dict] | None = None):
        """``initial_result`` (latest_version, release_url, assets) skips the
        network check and shows that result right away - used when the
        startup auto-check (MainWindow._start_update_check_at_startup)
        already found a newer release and just needs to prompt about it,
        so it isn't fetched twice."""
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: UpdateCheckWorker | None = None
        self._download_thread: QThread | None = None
        self._download_worker: self_update.UpdateDownloadWorker | None = None
        self._release_url = ""
        self._latest_version = ""
        self._assets: dict[str, str] = {}
        self._staging_dir: str | None = None
        # The checked new .app once downloaded; MainWindow installs it
        # after exec() returns Accepted (see show_check_updates_dialog).
        self.staged_update: str | None = None
        self.setWindowTitle(i18n.tr("update_check_window_title"))
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 18)
        root.setSpacing(0)

        logo = QLabel()
        dpr = self.devicePixelRatioF() or 1.0
        pixmap = QPixmap(resource_path("resources", "app_logo.png"))
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                int(_LOGO_SIZE * dpr), int(_LOGO_SIZE * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pixmap.setDevicePixelRatio(dpr)
            logo.setPixmap(pixmap)
        logo.setFixedSize(_LOGO_SIZE, _LOGO_SIZE)
        root.addWidget(logo, alignment=Qt.AlignHCenter)
        root.addSpacing(10)

        # Not run through i18n - the display name is fixed, same as the
        # window title (see MainWindow.__init__) and main.py's applicationName.
        title = QLabel("Trichr-o-matic")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        root.addWidget(title, alignment=Qt.AlignHCenter)
        root.addSpacing(3)

        version = QLabel(i18n.tr("update_check_current_version", version=__version__))
        version.setStyleSheet("color: #999; font-size: 11px;")
        root.addWidget(version, alignment=Qt.AlignHCenter)
        root.addSpacing(14)

        self.status_label = QLabel(i18n.tr("update_check_checking"))
        self.status_label.setWordWrap(True)
        # Fixed (not maximum) width - see ConfirmDialog's detail_label for
        # why a word-wrapped QLabel needs this to report its real height.
        self.status_label.setFixedWidth(_TEXT_WIDTH)
        self.status_label.setAlignment(Qt.AlignHCenter)
        root.addWidget(self.status_label, alignment=Qt.AlignHCenter)

        # Shown only while downloading.
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(_TEXT_WIDTH)
        self.progress_bar.setTextVisible(False)
        # Accent fill (the native bar uses the system accent colour).
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: none; border-radius: 3px; background: rgba(127, 127, 127, 60); }"
            " QProgressBar::chunk { border-radius: 3px; background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            f" stop:0 {ACCENT_LIGHT}, stop:1 {ACCENT}); }}")
        self.progress_bar.hide()
        root.addSpacing(10)
        root.addWidget(self.progress_bar, alignment=Qt.AlignHCenter)
        root.addSpacing(10)

        # Buttons centred under the centred text, like WelcomeDialog's.
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addStretch(1)
        self.close_button = QPushButton(i18n.tr("update_check_close"))
        style_secondary_button(self.close_button)
        self.close_button.clicked.connect(self.reject)
        row.addWidget(self.close_button)
        # Hidden until the check finds a newer release - see _on_result. Its
        # action depends on the state: _update_action.
        self.update_button = QPushButton(i18n.tr("update_check_update_button"))
        style_primary_button(self.update_button)
        self.update_button.clicked.connect(lambda: self._update_action())
        self.update_button.hide()
        self._update_action = self._open_release_page
        row.addWidget(self.update_button)
        row.addStretch(1)
        root.addLayout(row)

        root.setSizeConstraint(QLayout.SetFixedSize)
        self.close_button.setFocus()

        if initial_result is not None:
            self._on_result(*initial_result)
        else:
            self._start_check()

    def _start_check(self) -> None:
        self._thread = QThread()
        self._worker = UpdateCheckWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.result_ready.connect(self._on_result)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    def _on_thread_finished(self) -> None:
        self._worker = None
        self._thread = None

    def _on_result(self, latest_version: str, release_url: str, assets: dict) -> None:
        if parse_version(latest_version) > parse_version(__version__):
            self._release_url = release_url
            self._latest_version = latest_version
            self._assets = dict(assets or {})
            self.status_label.setText(i18n.tr("update_check_available", version=latest_version))
            if self_update.can_self_update(self._assets, latest_version):
                self._set_update_button("update_check_install_button", self._start_download)
            else:
                self._set_update_button("update_check_update_button", self._open_release_page)
        else:
            self.status_label.setText(i18n.tr("update_check_up_to_date"))

    def _on_failed(self, _message: str) -> None:
        self.status_label.setText(i18n.tr("update_check_failed"))

    def _set_update_button(self, text_key: str, action) -> None:
        self.update_button.setText(i18n.tr(text_key))
        self._update_action = action
        self.update_button.show()
        self.update_button.setFocus()

    def _open_release_page(self) -> None:
        if self._release_url:
            QDesktopServices.openUrl(QUrl(self._release_url))
        self.reject()

    def _start_download(self) -> None:
        self.update_button.hide()
        self.close_button.setText(i18n.tr("update_check_cancel"))
        self.status_label.setText(i18n.tr("update_check_downloading", version=self._latest_version))
        self.progress_bar.setRange(0, 0)  # busy until the size is known
        self.progress_bar.show()
        self._download_thread = QThread()
        self._download_worker = self_update.UpdateDownloadWorker(self._latest_version, self._assets)
        self._download_worker.moveToThread(self._download_thread)
        self._download_thread.started.connect(self._download_worker.run)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.ready.connect(self._on_download_ready)
        self._download_worker.failed.connect(self._on_download_failed)
        self._download_worker.finished.connect(self._download_thread.quit)
        self._download_thread.finished.connect(self._on_download_thread_finished)
        self._download_thread.start()

    def _on_download_progress(self, received: int, total: int) -> None:
        if total > 0:
            # Per mille, so a ~120 MB download fits QProgressBar's int range.
            self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(min(1000, received * 1000 // total))

    def _on_download_ready(self, new_app: str) -> None:
        self._staging_dir = self._download_worker.staging_dir
        self.staged_update = new_app
        self.progress_bar.hide()
        self.status_label.setText(i18n.tr("update_check_ready", version=self._latest_version))
        self.close_button.setText(i18n.tr("update_check_later"))
        self._set_update_button("update_check_restart_button", self.accept)

    def _on_download_failed(self, _message: str) -> None:
        self.progress_bar.hide()
        self.status_label.setText(i18n.tr("update_check_download_failed"))
        self.close_button.setText(i18n.tr("update_check_close"))
        self._set_update_button("update_check_open_page_button", self._open_release_page)

    def _on_download_thread_finished(self) -> None:
        # Freed here on the main thread, not via deleteLater (same reasoning
        # as MainWindow._clear_export_thread_refs).
        self._download_worker = None
        self._download_thread = None

    def done(self, result: int) -> None:
        # The single choke point for accept()/reject()/Escape/titlebar
        # close - see the class docstring for why this, not closeEvent().
        if self._worker is not None:
            self._worker.result_ready.disconnect(self._on_result)
            self._worker.failed.disconnect(self._on_failed)
        if self._thread is not None:
            self._thread.finished.disconnect(self._on_thread_finished)
            # Blocks until the in-flight request returns - see the class
            # docstring's "Confirmed crash".
            self._thread.quit()
            self._thread.wait()
        if self._download_thread is not None:
            # Cancel stops at the next chunk; staging is then removed by the
            # worker itself.
            self._download_worker.cancel()
            self._download_worker.ready.disconnect(self._on_download_ready)
            self._download_worker.failed.disconnect(self._on_download_failed)
            self._download_thread.quit()
            self._download_thread.wait()
            self._download_worker = None
            self._download_thread = None
        if result != QDialog.Accepted and self.staged_update is not None:
            self_update.discard_staging(self._staging_dir)
            self.staged_update = None
        super().done(result)
