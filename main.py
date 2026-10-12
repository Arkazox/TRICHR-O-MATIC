"""Trichr-o-matic - entry point."""
import getpass
import os
import subprocess
import sys

from PySide6.QtCore import QEvent, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from trichrome.main_window import MainWindow
from trichrome.paths import resource_path
from trichrome.quick_tour import open_quick_tour_at_startup


def _suppress_macos_edit_menu_extras() -> None:
    """Hide the "Start Dictation…" / "Emoji & Symbols" / text-substitution
    items macOS injects automatically into any menu titled "Edit"."""
    if sys.platform != "darwin":
        return
    bundle_id = "com.simonjayet.trichromemaker"
    for key in ("NSDisabledDictationMenuItem", "NSDisabledCharacterPaletteMenuItem"):
        try:
            subprocess.run(
                ["defaults", "write", bundle_id, key, "-bool", "true"],
                check=False, capture_output=True, timeout=2,
            )
        except Exception:
            pass


# Windows hands a double-clicked .trirgb to a brand-new process as argv[1]
# (macOS sends a FileOpen event to the running app instead). The first
# process listens on this local socket; a later one forwards its path there
# and exits, so the session opens in the existing window.
_WINDOWS_INSTANCE_SERVER = f"Trichr-o-matic-{getpass.getuser()}"


def _session_path_from_argv(argv: list[str]) -> str | None:
    for arg in argv[1:]:
        if arg.lower().endswith(".trirgb") and os.path.isfile(arg):
            return os.path.abspath(arg)
    return None


def _forward_to_running_instance(path: str | None) -> bool:
    """True if another instance took the request (this one should exit)."""
    socket = QLocalSocket()
    socket.connectToServer(_WINDOWS_INSTANCE_SERVER)
    if not socket.waitForConnected(500):
        return False
    # Always one line, empty when there's no file: the receiver only needs
    # to bring its window forward then.
    socket.write(((path or "") + "\n").encode("utf-8"))
    socket.flush()
    socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
    return True


class TrichromaticApp(QApplication):
    """Catches the macOS "open this file with Trichr-o-matic" event (double-
    clicking a .trirgb in Finder, or dragging one onto the app/Dock icon).
    That event can arrive before a MainWindow even exists (launching the app
    this way), so the path is buffered until something is ready to consume it."""
    file_open_requested = Signal(str)

    def __init__(self, argv):
        super().__init__(argv)
        self.pending_open_path: str | None = None
        self.raise_requested = None  # set by main() on Windows
        self._instance_server: QLocalServer | None = None
        if sys.platform == "win32":
            self.pending_open_path = _session_path_from_argv(argv)

    def listen_for_other_instances(self) -> None:
        server = QLocalServer(self)
        # A server name left over from a crashed instance would make
        # listen() fail; nothing else can be using it at this point.
        QLocalServer.removeServer(_WINDOWS_INSTANCE_SERVER)
        if server.listen(_WINDOWS_INSTANCE_SERVER):
            server.newConnection.connect(self._on_other_instance)
            self._instance_server = server

    def _on_other_instance(self) -> None:
        socket = self._instance_server.nextPendingConnection()
        if socket is None:
            return
        if socket.bytesAvailable() or socket.waitForReadyRead(1000):
            path = bytes(socket.readLine()).decode("utf-8").strip()
            if path:
                self.file_open_requested.emit(path)
        socket.disconnectFromServer()
        socket.deleteLater()
        if self.raise_requested is not None:
            self.raise_requested()

    def event(self, event) -> bool:
        if event.type() == QEvent.FileOpen:
            path = event.file()
            self.pending_open_path = path
            self.file_open_requested.emit(path)
            return True
        return super().event(event)


def _open_session_file(window: MainWindow, path: str) -> None:
    try:
        window.load_session_from_path(path)
    except Exception as exc:
        print(f"Failed to open session file {path!r}: {exc}", file=sys.stderr)


def _start_update_check_after_quick_tour(window: MainWindow) -> None:
    """Quick Tour always has priority over the update prompt: this runs
    right after open_quick_tour_at_startup returns, which only happens once
    the (modal) welcome window has already closed - so this point only
    needs to additionally wait out the guided tour itself, if "Start the
    Tour" was picked (MainWindow._quick_tour is set while it runs, non-modal
    so the call above doesn't block on it). Otherwise - "Open at startup"
    off, the user picked Close, or a .trirgb skipped the tour entirely -
    there's nothing to wait for and the check starts now."""
    tour = getattr(window, "_quick_tour", None)
    if tour is not None:
        tour.finished.connect(window.start_update_check_at_startup)
    else:
        window.start_update_check_at_startup()


def main() -> int:
    _suppress_macos_edit_menu_extras()
    app = TrichromaticApp(sys.argv)
    app.setApplicationName("Trichr-o-matic")
    if sys.platform == "win32":
        # Title bars and the taskbar: Qt doesn't take the .exe's own icon.
        # Windows only - on macOS this would replace the Dock icon.
        app.setWindowIcon(QIcon(resource_path("resources", "icon.ico")))
        if _forward_to_running_instance(app.pending_open_path):
            return 0
        app.listen_for_other_instances()
    window = MainWindow()
    app.file_open_requested.connect(lambda path: _open_session_file(window, path))

    def _bring_window_forward() -> None:
        if window.isMinimized():
            window.showNormal()
        window.raise_()
        window.activateWindow()

    app.raise_requested = _bring_window_forward
    # The FileOpen event can arrive before `window` existed to receive the
    # signal above (launching the app by double-clicking a .trirgb) - catch
    # that case explicitly rather than losing the request.
    if app.pending_open_path:
        _open_session_file(window, app.pending_open_path)
    window.show()

    def _startup_sequence() -> None:
        # Quick Tour welcome window, while "Open at startup" is checked -
        # but not when the app was launched by opening a .trirgb (that user
        # already knows the app). This blocks here until the welcome window
        # closes (it's modal), and _start_update_check_after_quick_tour then
        # additionally waits out the guided tour itself if it was started -
        # Quick Tour always has priority over the update prompt.
        if not app.pending_open_path:
            open_quick_tour_at_startup(window)
        _start_update_check_after_quick_tour(window)

    # Delayed because macOS delivers the FileOpen event (checked via
    # app.pending_open_path above) only once the event loop is running,
    # after this point. On Windows the path comes from argv and is already
    # set; the same delay keeps startup identical on both.
    QTimer.singleShot(800, _startup_sequence)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
