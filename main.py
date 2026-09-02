"""Trichr-o-matic - entry point."""
import subprocess
import sys

from PySide6.QtCore import QEvent, Signal
from PySide6.QtWidgets import QApplication

from trichrome.main_window import MainWindow


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


class TrichromaticApp(QApplication):
    """Catches the macOS "open this file with Trichr-o-matic" event (double-
    clicking a .trirgb in Finder, or dragging one onto the app/Dock icon).
    That event can arrive before a MainWindow even exists (launching the app
    this way), so the path is buffered until something is ready to consume it."""
    file_open_requested = Signal(str)

    def __init__(self, argv):
        super().__init__(argv)
        self.pending_open_path: str | None = None

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


def main() -> int:
    _suppress_macos_edit_menu_extras()
    app = TrichromaticApp(sys.argv)
    app.setApplicationName("Trichr-o-matic")
    window = MainWindow()
    app.file_open_requested.connect(lambda path: _open_session_file(window, path))
    # The FileOpen event can arrive before `window` existed to receive the
    # signal above (launching the app by double-clicking a .trirgb) - catch
    # that case explicitly rather than losing the request.
    if app.pending_open_path:
        _open_session_file(window, app.pending_open_path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
