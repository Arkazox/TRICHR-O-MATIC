"""Background worker for a single shutter-release + download, so a RAW
file's transfer time (a few seconds over USB) doesn't freeze the UI. Same
QObject-with-run()-moved-to-a-QThread convention as import_worker.py/
export_worker.py."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from . import gphoto_backend


class CaptureWorker(QObject):
    finished = Signal(list)  # list[str] of saved file paths
    error = Signal(str)

    def __init__(self, port: str, dest_pattern: str):
        super().__init__()
        self.port = port
        self.dest_pattern = dest_pattern

    def run(self) -> None:
        try:
            saved = gphoto_backend.capture_and_download(self.port, self.dest_pattern)
        except gphoto_backend.GPhotoError as exc:
            self.error.emit(str(exc))
            return
        self.finished.emit(saved)
