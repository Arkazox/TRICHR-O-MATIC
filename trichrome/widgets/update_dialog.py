"""Check for Updates - app menu, right below Preferences and Keyboard
Shortcuts. Logo, app name, current version, and (once the background
check resolves) either "You're up to date" or an Update button that opens
the latest GitHub release in the browser. Styled like the app's other own
dialogs (WelcomeDialog, ConfirmDialog), not native QMessageBox chrome.

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
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLayout, QPushButton, QVBoxLayout

from .. import i18n
from ..paths import resource_path
from ..update_checker import UpdateCheckWorker, parse_version
from ..version import __version__
from .button_style import style_primary_button, style_secondary_button

_LOGO_SIZE = 96
_TEXT_WIDTH = 320


class UpdateCheckDialog(QDialog):
    def __init__(self, parent, initial_result: tuple[str, str] | None = None):
        """``initial_result`` (latest_version, release_url) skips the
        network check and shows that result right away - used when the
        startup auto-check (MainWindow._start_update_check_at_startup)
        already found a newer release and just needs to prompt about it,
        so it isn't fetched twice."""
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: UpdateCheckWorker | None = None
        self._release_url = ""
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
        root.addSpacing(20)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addStretch(1)
        close_button = QPushButton(i18n.tr("update_check_close"))
        style_secondary_button(close_button)
        close_button.clicked.connect(self.reject)
        row.addWidget(close_button)
        # Hidden until the check finds a newer release - see _on_result.
        self.update_button = QPushButton(i18n.tr("update_check_update_button"))
        style_primary_button(self.update_button)
        self.update_button.clicked.connect(self._on_update_clicked)
        self.update_button.hide()
        row.addWidget(self.update_button)
        root.addLayout(row)

        root.setSizeConstraint(QLayout.SetFixedSize)
        close_button.setFocus()

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

    def _on_result(self, latest_version: str, release_url: str) -> None:
        if parse_version(latest_version) > parse_version(__version__):
            self._release_url = release_url
            self.status_label.setText(i18n.tr("update_check_available", version=latest_version))
            self.update_button.show()
        else:
            self.status_label.setText(i18n.tr("update_check_up_to_date"))

    def _on_failed(self, _message: str) -> None:
        self.status_label.setText(i18n.tr("update_check_failed"))

    def _on_update_clicked(self) -> None:
        if self._release_url:
            QDesktopServices.openUrl(QUrl(self._release_url))
        self.accept()

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
        super().done(result)
