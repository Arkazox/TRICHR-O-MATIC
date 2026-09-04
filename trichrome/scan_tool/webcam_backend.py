"""TEMPORARY testing backend (added 2026-09-04): capture stills from a
built-in webcam or an iPhone connected via macOS Continuity Camera,
instead of a real tethered camera via gphoto2 - so scan-workflow testing
doesn't require the real camera to be connected. **The user has explicitly
said this will be removed later** ("nous supprimerons cette option par la
suite") - this file, plus the "Use webcam / iPhone" checkbox and its
handful of branches in widgets/scan_panel.py, are the only things that
need deleting to fully revert; nothing in gphoto_backend.py or the rest of
the tested capture pipeline was touched to add this.

Uses PySide6.QtMultimedia (QCamera/QMediaCaptureSession/QImageCapture),
already bundled with PySide6, no new dependency. **Must run on the GUI
thread** (unlike gphoto_backend's subprocess calls, which are safe from a
worker QThread) - QCamera drives the platform's native AVFoundation camera
session, which isn't meant to be touched off the main thread.

For a real distributed .app bundle (not run from source), macOS also needs
`NSCameraUsageDescription` (and, for Continuity Camera/iPhone specifically,
`NSCameraUseContinuityCameraDeviceType`) in the Info.plist - see the
matching temporary block in trichrome.spec.
"""
from __future__ import annotations

import dataclasses

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtMultimedia import QCamera, QImageCapture, QMediaCaptureSession, QMediaDevices

# If macOS camera permission was ever denied (or the system permission
# prompt is never answered - confirmed to happen under an offscreen/no-
# real-window Qt session while testing this headlessly), the camera never
# reports itself active and neither captured/error would otherwise ever
# fire, leaving the caller's UI stuck mid-capture indefinitely. This is a
# safety net, not the expected path - a real permission grant/denial
# resolves in well under this.
_START_TIMEOUT_MS = 8000


@dataclasses.dataclass
class WebcamDevice:
    description: str
    device: object  # a QCameraDevice - opaque here, passed straight into WebcamCapture


def list_cameras() -> list[WebcamDevice]:
    """Every video input QtMultimedia currently sees - the built-in
    webcam, and an iPhone once connected/trusted via Continuity Camera,
    both show up here exactly like any other camera."""
    return [WebcamDevice(description=d.description(), device=d) for d in QMediaDevices.videoInputs()]


class WebcamCapture(QObject):
    """One-shot still capture from a QCameraDevice, saved directly to
    ``dest_path``. Starts the camera and waits for it to actually report
    itself active (a webcam - and especially Continuity Camera - can take
    a moment to spin up) before triggering the capture, rather than
    assuming it's ready immediately after ``start()`` returns.

    ``captured(path)``/``error(message)`` deliberately mirror
    CaptureWorker's ``finished``/``error`` signal shapes closely enough
    that ScanPanel can feed this straight into the same downstream
    handlers (history logging, RGB-sequence stepping, processing) used for
    a real gphoto2 capture, without needing a separate code path there."""

    captured = Signal(str)
    error = Signal(str)

    def __init__(self, device, dest_path: str, parent: QObject | None = None):
        super().__init__(parent)
        self._dest_path = dest_path
        self._started = False
        self._finished = False
        self._camera = QCamera(device, self)
        self._session = QMediaCaptureSession(self)
        self._session.setCamera(self._camera)
        self._image_capture = QImageCapture(self)
        self._session.setImageCapture(self._image_capture)
        self._camera.activeChanged.connect(self._on_active_changed)
        self._camera.errorOccurred.connect(self._on_camera_error)
        self._image_capture.imageSaved.connect(self._on_image_saved)
        self._image_capture.errorOccurred.connect(self._on_capture_error)
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

    def start(self) -> None:
        self._timeout_timer.start(_START_TIMEOUT_MS)
        self._camera.start()

    def _on_timeout(self) -> None:
        self._finish_error(
            "Camera did not start in time - check camera permission for this app "
            "in System Settings ▸ Privacy & Security ▸ Camera."
        )

    def _on_active_changed(self, active: bool) -> None:
        if active and not self._started:
            self._started = True
            self._image_capture.captureToFile(self._dest_path)

    def _on_camera_error(self, _error, message: str) -> None:
        self._finish_error(message or "Camera error")

    def _on_capture_error(self, _id, _error, message: str) -> None:
        self._finish_error(message or "Capture error")

    def _on_image_saved(self, _id: int, path: str) -> None:
        if self._finished:
            return
        self._finished = True
        self._timeout_timer.stop()
        self._camera.stop()
        self.captured.emit(path)

    def _finish_error(self, message: str) -> None:
        if self._finished:
            return
        self._finished = True
        self._timeout_timer.stop()
        self._camera.stop()
        self.error.emit(message)
