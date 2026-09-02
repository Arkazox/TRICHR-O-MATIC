"""Background worker for the post-capture JPG processing preview (see
process.py) - auto-align + compose for an RGB triplet can take a couple of
seconds, so this stays off the GUI thread. Same QObject-with-run()-moved-
to-a-QThread convention as capture_worker.py."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal


class ProcessWorker(QObject):
    finished = Signal(list)  # list[str] of saved output paths
    error = Signal(str)

    def __init__(self, fn: Callable[[], list[str]]):
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            out_paths = self._fn()
        except Exception as exc:  # noqa: BLE001 - surface any processing failure to the UI
            self.error.emit(str(exc))
            return
        self.finished.emit(out_paths)
