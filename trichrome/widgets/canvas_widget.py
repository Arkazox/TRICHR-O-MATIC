"""Interactive canvas: displays the composite preview and lets the user
drag the active channel to move it, or use the wheel (+Shift/Alt) to
scale / rotate it. Plain trackpad scroll pans the view; Ctrl+wheel or a
trackpad pinch gesture zooms it."""
from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea

from .. import i18n, imaging
from .svg_icons import tinted_svg_pixmap

MIN_ZOOM = 0.05
MAX_ZOOM = 8.0

_CROP_HANDLE_HIT_RADIUS = 10.0
_CROP_HANDLE_SIZE = 8.0
_CROP_MIN_SIZE = 0.02
_FIXED_GRID_SPACING_PX = 24.0
_GOLDEN_RATIO = (1.0 + 5 ** 0.5) / 2.0
_GOLDEN_FRACTION_HIGH = 1.0 / _GOLDEN_RATIO       # ~0.618
_GOLDEN_FRACTION_LOW = 1.0 - _GOLDEN_FRACTION_HIGH  # ~0.382


def _local_image_paths(mime_data) -> list[str]:
    """Same filtering convention as carousel_widget.py's own helper of the
    same name - local files only, extension checked against every format
    load_grayscale/load_color can actually open."""
    if not mime_data.hasUrls():
        return []
    return [
        url.toLocalFile() for url in mime_data.urls()
        if url.isLocalFile() and os.path.splitext(url.toLocalFile())[1].lower() in imaging.IMPORTABLE_EXTENSIONS
    ]


class _ImageLabel(QLabel):
    drag_delta = Signal(float, float)  # in source-image pixels
    scale_delta = Signal(float)        # multiplicative factor
    rotate_delta = Signal(float)       # degrees
    zoom_delta = Signal(float)         # multiplicative factor (view zoom, not a layer)
    crop_rect_dragged = Signal(float, float, float, float)  # normalized x, y, w, h
    white_balance_pick_requested = Signal(float, float)  # normalized x, y
    film_base_pick_requested = Signal(float, float)  # normalized x, y
    histogram_pixel_hovered = Signal(float, float)  # normalized x, y
    histogram_pixel_left = Signal()
    files_dropped = Signal(list)  # local file paths dragged in from Finder

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.display_scale = 1.0
        self.align_enabled = False
        self._dragging = False
        self._last_pos = None
        self.wb_pick_enabled = False
        self.film_base_pick_enabled = False
        self.histogram_pick_enabled = False
        self._accept_file_drops = False

        self.crop_enabled = False
        self._crop_rect = (0.0, 0.0, 1.0, 1.0)  # normalized x, y, w, h
        self._crop_ratio: float | None = None
        self._crop_grid = "off"
        self._crop_drag_mode: str | None = None
        self._crop_drag_start_pos: QPointF | None = None
        self._crop_drag_start_rect: tuple[float, float, float, float] | None = None

    def set_align_enabled(self, enabled: bool) -> None:
        self.align_enabled = enabled
        self._refresh_cursor()

    # -- white balance eyedropper / histogram pixel pick --------------------
    def _refresh_cursor(self) -> None:
        # All 3 eyedropper-style tools (white balance pick, histogram pixel
        # pick, film base pick) share the same cursor - whichever reason
        # it's armed for, the gesture (point at a pixel) is the same.
        if self.wb_pick_enabled or self.histogram_pick_enabled or self.film_base_pick_enabled:
            dpr = self.devicePixelRatioF() or 1.0
            size = 28
            pixmap = tinted_svg_pixmap("Global/eyedropper.svg", size, QColor(Qt.white), dpr)
            # Hotspot near the icon's own sampling tip (bottom-left area of
            # the glyph), not its center - matches where the cursor visually
            # points when sampling a pixel.
            self.setCursor(QCursor(pixmap, int(size * 0.2), int(size * 0.85)))
        elif self.align_enabled:
            self.setCursor(QCursor(Qt.OpenHandCursor))
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))

    def set_wb_pick_enabled(self, enabled: bool) -> None:
        self.wb_pick_enabled = enabled
        self._refresh_cursor()

    def set_film_base_pick_enabled(self, enabled: bool) -> None:
        self.film_base_pick_enabled = enabled
        self._refresh_cursor()

    def set_histogram_pick_enabled(self, enabled: bool) -> None:
        self.histogram_pick_enabled = enabled
        # Only track the mouse (get move events without a button held) while
        # this live-hover tool is actually armed - no other tool here needs
        # hover, only drags, which always deliver move events regardless.
        self.setMouseTracking(enabled)
        self._refresh_cursor()
        if not enabled:
            self.histogram_pixel_left.emit()

    # -- crop overlay -----------------------------------------------------
    def set_crop_enabled(self, enabled: bool) -> None:
        self.crop_enabled = enabled
        self._crop_drag_mode = None
        self.update()

    def set_crop_rect(self, x: float, y: float, w: float, h: float) -> None:
        self._crop_rect = (x, y, w, h)
        self.update()

    def set_crop_ratio(self, ratio: float | None) -> None:
        self._crop_ratio = ratio

    def set_crop_grid(self, mode: str) -> None:
        self._crop_grid = mode
        self.update()

    def _crop_rect_px(self) -> QRectF:
        x, y, w, h = self._crop_rect
        return QRectF(x * self.width(), y * self.height(), w * self.width(), h * self.height())

    def _hit_test_crop(self, pos: QPointF) -> str | None:
        rect = self._crop_rect_px()
        for name, corner in (
            ("tl", rect.topLeft()), ("tr", rect.topRight()),
            ("bl", rect.bottomLeft()), ("br", rect.bottomRight()),
        ):
            if (pos - corner).manhattanLength() <= _CROP_HANDLE_HIT_RADIUS:
                return name
        if rect.contains(pos):
            return "move"
        return None

    def _resize_crop_rect(
        self, x0: float, y0: float, w0: float, h0: float, dx: float, dy: float, corner: str,
    ) -> tuple[float, float, float, float]:
        anchor = {
            "tl": (x0 + w0, y0 + h0), "tr": (x0, y0 + h0),
            "bl": (x0 + w0, y0), "br": (x0, y0),
        }[corner]
        orig = {
            "tl": (x0, y0), "tr": (x0 + w0, y0),
            "bl": (x0, y0 + h0), "br": (x0 + w0, y0 + h0),
        }[corner]
        ax, ay = anchor
        px = min(max(0.0, orig[0] + dx), 1.0)
        py = min(max(0.0, orig[1] + dy), 1.0)

        new_x, new_w = min(ax, px), abs(px - ax)
        new_y, new_h = min(ay, py), abs(py - ay)

        if self._crop_ratio and new_w > 0 and new_h > 0:
            # new_w/new_h are normalized fractions of the image's own width
            # and height respectively - not the same physical unit unless
            # the image is square, so a target *real* ratio (self._crop_ratio,
            # true pixel width/height) needs correcting by the image's own
            # aspect ratio (label_ratio) before comparing/assigning between
            # them, or the resulting rect ends up the wrong shape entirely
            # for any non-square photo.
            label_ratio = max(1, self.width()) / max(1, self.height())
            if abs(px - orig[0]) >= abs(py - orig[1]):
                new_h = new_w * label_ratio / self._crop_ratio
            else:
                new_w = new_h * self._crop_ratio / label_ratio

            # The rect grows away from the fixed anchor corner (ax, ay) - the
            # most it can grow in either axis before running off that edge
            # of the frame is bounded by the anchor's own position. Shrink
            # *both* dimensions by the same factor to stay within whichever
            # bound is tighter, instead of clamping each axis independently
            # (which broke the locked ratio right at the frame's edges).
            max_w = ax if px < ax else 1.0 - ax
            max_h = ay if py < ay else 1.0 - ay
            scale = min(1.0, max_w / new_w if new_w > max_w else 1.0,
                        max_h / new_h if new_h > max_h else 1.0)
            new_w *= scale
            new_h *= scale
            new_x = ax - new_w if px < ax else ax
            new_y = ay - new_h if py < ay else ay

        return new_x, new_y, max(_CROP_MIN_SIZE, new_w), max(_CROP_MIN_SIZE, new_h)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.wb_pick_enabled:
            pos = event.position()
            w, h = max(1, self.width()), max(1, self.height())
            u = min(max(pos.x() / w, 0.0), 1.0)
            v = min(max(pos.y() / h, 0.0), 1.0)
            self.white_balance_pick_requested.emit(u, v)
            event.accept()
        elif event.button() == Qt.LeftButton and self.film_base_pick_enabled:
            pos = event.position()
            w, h = max(1, self.width()), max(1, self.height())
            u = min(max(pos.x() / w, 0.0), 1.0)
            v = min(max(pos.y() / h, 0.0), 1.0)
            self.film_base_pick_requested.emit(u, v)
            event.accept()
        elif event.button() == Qt.LeftButton and self.crop_enabled:
            mode = self._hit_test_crop(event.position())
            if mode:
                self._crop_drag_mode = mode
                self._crop_drag_start_pos = event.position()
                self._crop_drag_start_rect = self._crop_rect
            event.accept()
        elif event.button() == Qt.LeftButton and self.align_enabled:
            self._dragging = True
            self._last_pos = event.position()
            self.setCursor(QCursor(Qt.ClosedHandCursor))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.histogram_pick_enabled:
            pos = event.position()
            w, h = max(1, self.width()), max(1, self.height())
            u = min(max(pos.x() / w, 0.0), 1.0)
            v = min(max(pos.y() / h, 0.0), 1.0)
            self.histogram_pixel_hovered.emit(u, v)
        if self.crop_enabled and self._crop_drag_mode and self._crop_drag_start_pos is not None:
            pos = event.position()
            w_px, h_px = max(1, self.width()), max(1, self.height())
            dx = (pos.x() - self._crop_drag_start_pos.x()) / w_px
            dy = (pos.y() - self._crop_drag_start_pos.y()) / h_px
            x0, y0, w0, h0 = self._crop_drag_start_rect
            if self._crop_drag_mode == "move":
                new_rect = (
                    min(max(0.0, x0 + dx), 1.0 - w0),
                    min(max(0.0, y0 + dy), 1.0 - h0),
                    w0, h0,
                )
            else:
                new_rect = self._resize_crop_rect(x0, y0, w0, h0, dx, dy, self._crop_drag_mode)
            self._crop_rect = new_rect
            self.update()
            self.crop_rect_dragged.emit(*new_rect)
            event.accept()
        elif self._dragging and self._last_pos is not None:
            pos = event.position()
            delta = pos - self._last_pos
            self._last_pos = pos
            scale = self.display_scale or 1.0
            self.drag_delta.emit(delta.x() / scale, delta.y() / scale)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.crop_enabled and self._crop_drag_mode and event.button() == Qt.LeftButton:
            self._crop_drag_mode = None
            self._crop_drag_start_pos = None
            self._crop_drag_start_rect = None
            event.accept()
        elif self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            self.setCursor(QCursor(Qt.OpenHandCursor) if self.align_enabled else QCursor(Qt.ArrowCursor))
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        if self.histogram_pick_enabled:
            self.histogram_pixel_left.emit()
        super().leaveEvent(event)

    # -- external file drop (empty-project placeholder only) --------------
    def set_accept_file_drops(self, enabled: bool) -> None:
        """Only armed while the canvas is showing its empty-project
        placeholder (see CanvasWidget.clear_image/set_image_rgb/
        set_image_gray) - once a real image is shown, this same area is
        already used for align-drag/crop-drag/eyedropper interactions, so
        a generic file drop isn't offered there anymore."""
        self._accept_file_drops = enabled
        self.setAcceptDrops(enabled)

    def dragEnterEvent(self, event) -> None:
        if self._accept_file_drops and _local_image_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._accept_file_drops and _local_image_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        paths = _local_image_paths(event.mimeData()) if self._accept_file_drops else []
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def wheelEvent(self, event) -> None:
        modifiers = event.modifiers()
        if self.align_enabled and (modifiers & Qt.ShiftModifier):
            factor = 1.0 + (event.angleDelta().y() / 1200.0)
            self.scale_delta.emit(max(0.01, factor))
            event.accept()
        elif self.align_enabled and (modifiers & Qt.AltModifier):
            self.rotate_delta.emit(event.angleDelta().y() / 1200.0 * 5.0)
            event.accept()
        elif modifiers & Qt.ControlModifier:
            factor = 1.0 + (event.angleDelta().y() / 1000.0)
            self.zoom_delta.emit(max(0.01, factor))
            event.accept()
        else:
            super().wheelEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.crop_enabled:
            return
        rect = self._crop_rect_px()
        full_w, full_h = float(self.width()), float(self.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        dim_color = QColor(0, 0, 0, 140)
        painter.fillRect(QRectF(0, 0, full_w, rect.top()), dim_color)
        painter.fillRect(QRectF(0, rect.bottom(), full_w, full_h - rect.bottom()), dim_color)
        painter.fillRect(QRectF(0, rect.top(), rect.left(), rect.height()), dim_color)
        painter.fillRect(QRectF(rect.right(), rect.top(), full_w - rect.right(), rect.height()), dim_color)

        if self._crop_grid != "off":
            painter.setPen(QPen(QColor(255, 255, 255, 140), 1))
            if self._crop_grid == "grid":
                # Fixed-size squares (constant screen pixels) rather than a
                # fraction of the crop rect - unlike the other three modes,
                # this one deliberately does NOT adapt to the rect's own
                # size/ratio.
                x = rect.left() + _FIXED_GRID_SPACING_PX
                while x < rect.right():
                    painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
                    x += _FIXED_GRID_SPACING_PX
                y = rect.top() + _FIXED_GRID_SPACING_PX
                while y < rect.bottom():
                    painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
                    y += _FIXED_GRID_SPACING_PX
            else:
                fractions = {
                    "3x3": (1 / 3, 2 / 3),
                    "2x2": (0.5,),
                    "golden": (_GOLDEN_FRACTION_LOW, _GOLDEN_FRACTION_HIGH),
                }.get(self._crop_grid, ())
                for f in fractions:
                    x = rect.left() + rect.width() * f
                    painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
                    y = rect.top() + rect.height() * f
                    painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        painter.setPen(QPen(QColor(255, 255, 255, 230), 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)

        hs = _CROP_HANDLE_SIZE
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.setPen(Qt.NoPen)
        for corner in (rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()):
            painter.drawRect(QRectF(corner.x() - hs / 2, corner.y() - hs / 2, hs, hs))
        painter.end()

    def event(self, e) -> bool:
        if e.type() == QEvent.NativeGesture:
            try:
                if e.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                    self.zoom_delta.emit(max(0.01, 1.0 + e.value()))
                    return True
            except AttributeError:
                pass
        return super().event(e)


class CanvasWidget(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignCenter)
        self.setBackgroundRole(self.backgroundRole())

        self.image_label = _ImageLabel()
        self.setWidget(self.image_label)

        self.drag_delta = self.image_label.drag_delta
        self.scale_delta = self.image_label.scale_delta
        self.rotate_delta = self.image_label.rotate_delta
        self.crop_rect_dragged = self.image_label.crop_rect_dragged
        self.white_balance_pick_requested = self.image_label.white_balance_pick_requested
        self.film_base_pick_requested = self.image_label.film_base_pick_requested
        self.histogram_pixel_hovered = self.image_label.histogram_pixel_hovered
        self.histogram_pixel_left = self.image_label.histogram_pixel_left
        self.files_dropped = self.image_label.files_dropped
        self.image_label.zoom_delta.connect(self._on_zoom_delta)

        self.zoom = 1.0
        self._qimage: QImage | None = None
        self._showing_placeholder = False

    def _on_zoom_delta(self, factor: float) -> None:
        self.set_zoom(self.zoom * factor)

    # -- crop overlay -----------------------------------------------------
    def set_crop_enabled(self, enabled: bool) -> None:
        self.image_label.set_crop_enabled(enabled)

    def set_crop_rect(self, x: float, y: float, w: float, h: float) -> None:
        self.image_label.set_crop_rect(x, y, w, h)

    def crop_rect(self) -> tuple[float, float, float, float]:
        return self.image_label._crop_rect

    def set_crop_ratio(self, ratio: float | None) -> None:
        self.image_label.set_crop_ratio(ratio)

    def set_crop_grid(self, mode: str) -> None:
        self.image_label.set_crop_grid(mode)

    def keyPressEvent(self, event) -> None:
        # QScrollArea normally consumes arrow keys to scroll its viewport,
        # which silently swallows the filmstrip's Left/Right navigation
        # whenever the canvas (its usual default focus holder) is focused.
        # Left/Right panning is already covered by drag/trackpad, so hand
        # these two off to the parent (MainWindow) instead.
        if event.key() in (Qt.Key_Left, Qt.Key_Right):
            event.ignore()
            return
        super().keyPressEvent(event)

    def set_align_enabled(self, enabled: bool) -> None:
        self.image_label.set_align_enabled(enabled)

    def set_wb_pick_enabled(self, enabled: bool) -> None:
        self.image_label.set_wb_pick_enabled(enabled)

    def set_film_base_pick_enabled(self, enabled: bool) -> None:
        self.image_label.set_film_base_pick_enabled(enabled)

    def set_histogram_pick_enabled(self, enabled: bool) -> None:
        self.image_label.set_histogram_pick_enabled(enabled)

    def set_image_rgb(self, rgb_uint8: np.ndarray) -> None:
        if self._showing_placeholder:
            self.setWidgetResizable(False)
        self._showing_placeholder = False
        self.image_label.set_accept_file_drops(False)
        rgb_uint8 = np.ascontiguousarray(rgb_uint8)
        h, w, _ = rgb_uint8.shape
        qimg = QImage(rgb_uint8.data, w, h, w * 3, QImage.Format_RGB888).copy()
        self._qimage = qimg
        self._refresh_pixmap()

    def set_image_gray(self, gray_uint8: np.ndarray) -> None:
        if self._showing_placeholder:
            self.setWidgetResizable(False)
        self._showing_placeholder = False
        self.image_label.set_accept_file_drops(False)
        gray_uint8 = np.ascontiguousarray(gray_uint8)
        h, w = gray_uint8.shape
        qimg = QImage(gray_uint8.data, w, h, w, QImage.Format_Grayscale8).copy()
        self._qimage = qimg
        self._refresh_pixmap()

    def clear_image(self) -> None:
        self._showing_placeholder = True
        self.image_label.set_accept_file_drops(True)
        self._qimage = None
        self.image_label.setPixmap(QPixmap())
        self.image_label.setWordWrap(True)
        self.image_label.setText(i18n.tr("canvas_placeholder"))
        # Let the label fill the viewport so the centered text is fully visible,
        # instead of keeping whatever fixed size the last zoomed pixmap had.
        self.setWidgetResizable(True)

    def retranslate_ui(self) -> None:
        if self._showing_placeholder:
            self.image_label.setText(i18n.tr("canvas_placeholder"))

    def _refresh_pixmap(self) -> None:
        if self._qimage is None:
            return
        w = max(1, int(self._qimage.width() * self.zoom))
        h = max(1, int(self._qimage.height() * self.zoom))
        pix = QPixmap.fromImage(self._qimage).scaled(
            w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(pix)
        self.image_label.resize(pix.size())
        self.image_label.display_scale = pix.width() / self._qimage.width() if self._qimage.width() else 1.0

    def set_zoom(self, zoom: float) -> None:
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        self._refresh_pixmap()

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom / 1.25)

    def zoom_fit(self) -> None:
        if self._qimage is None or self._qimage.width() == 0:
            return
        avail = self.viewport().size()
        scale = min(avail.width() / self._qimage.width(), avail.height() / self._qimage.height())
        self.set_zoom(scale if scale > 0 else 1.0)

    def zoom_100(self) -> None:
        self.set_zoom(1.0)
