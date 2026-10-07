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
# Guided Perspective mode's guide lines (Framing tool's Geometry section):
# how close (screen px) a press must land to an existing endpoint to grab
# it instead of starting a new guide (also how close a double-click must
# land to a guide to delete it), the shortest guide kept on release, and
# how many guides of each orientation may exist (2 vertical + 2 horizontal
# - a 5th, or a 3rd in the same direction, is refused).
_GUIDE_GRAB_RADIUS_PX = 10.0
_GUIDE_MIN_LENGTH_PX = 8.0
_GUIDE_MAX_PER_ORIENTATION = 2
_GUIDE_COLOR = QColor(255, 255, 255)
_GUIDE_MISMATCH_COLOR = QColor("#e06c6c")
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
    # "Stretch on Canvas" - started with the press point (normalized u, v -
    # same convention as crop/wb-pick), then one incremental (du, dv) per
    # mouse-move (normalized, delta since the *last* move event, not since the
    # drag started - same "incremental, not cumulative" convention drag_delta
    # already uses for align-drag), finished on release. See
    # MainWindow.on_canvas_stretch_drag_* - mutated directly into the active
    # channel's own ChannelLayer. stretch_pins, same "drag commits straight
    # into the model, no separate live-preview state" pattern align-drag
    # already uses.
    stretch_drag_started = Signal(float, float)
    stretch_drag_delta = Signal(float, float)
    stretch_drag_finished = Signal()
    # Guided Perspective: a guide was added/edited/removed (emitted on
    # mouse release only - the live correction is re-solved then, never
    # mid-drag, so the image doesn't move under the cursor).
    perspective_guides_changed = Signal()

    # Reference-grid overlay target cell size (screen pixels) while Stretch on
    # Canvas is armed - see _paint_stretch_grid. A target size, not a fixed
    # division count, so cells come out square regardless of the canvas's own
    # aspect ratio (a fixed division count for both axes produced rectangular
    # cells on any non-square image, which read less clearly as a deformation
    # gauge). Smaller than the ~58px cells the old fixed 12-division count gave
    # on a typical canvas width, for a finer gauge.
    _STRETCH_GRID_CELL_PX = 36

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

        self.stretch_enabled = False
        self._stretch_dragging = False
        self._stretch_last_pos: QPointF | None = None
        self._stretch_grid_pins: list = []

        # Guided Perspective mode - each guide is [(u0, v0), (u1, v1)],
        # normalized [0, 1] over the displayed (uncorrected) frame.
        self.perspective_enabled = False
        self._guides: list[list[tuple[float, float]]] = []
        self._guide_drag: tuple[int, int] | None = None  # (guide index, endpoint index)
        self._guides_before_drag: list = []
        # Guides live in *uncorrected-frame* coordinates (what the solver
        # needs), while the canvas may be showing the live-corrected
        # preview - these map between the two (see set_guide_mapping).
        self._guide_to_display = lambda u, v: (u, v)
        self._guide_from_display = lambda u, v: (u, v)

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

    # -- "Stretch on Canvas" -----------------------------------------------
    def set_stretch_enabled(self, enabled: bool) -> None:
        self.stretch_enabled = enabled
        self._refresh_cursor()
        self.update()

    def set_stretch_pins(self, pins: list) -> None:
        """Feeds the live reference-grid overlay - called by MainWindow
        whenever the Stretch-active channel's own pins change, including on
        every mouse-move of an in-progress drag, so the grid visibly
        follows the deformation in real time."""
        self._stretch_grid_pins = pins
        self.update()

    # -- guided Perspective mode -------------------------------------------
    def set_perspective_enabled(self, enabled: bool) -> None:
        """Arms/disarms guide drawing - always starts and ends with no
        guides, so a cancelled session never leaks into the next one."""
        self.perspective_enabled = enabled
        self._guides = []
        self._guide_drag = None
        self._guide_to_display = lambda u, v: (u, v)
        self._guide_from_display = lambda u, v: (u, v)
        # Hover tracking for the endpoint move cursor (see mouseMoveEvent).
        self.setMouseTracking(enabled or self.histogram_pick_enabled)
        self._refresh_cursor()
        self.update()

    def perspective_guides(self) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """In uncorrected-frame normalized coordinates."""
        return [(tuple(a), tuple(b)) for a, b in self._guides]

    def set_guide_mapping(self, to_display, from_display) -> None:
        """Set by MainWindow whenever what the preview shows changes (a new
        live-solved proposal, or none): to_display(u, v) -> display (u, v)
        or None, from_display(u, v) -> frame (u, v), both normalized. Keeps
        each guide pinned to the same image feature as the preview
        re-corrects underneath it."""
        self._guide_to_display = to_display
        self._guide_from_display = from_display
        self.update()

    def is_dragging_guide(self) -> bool:
        return self._guide_drag is not None

    def _normalized(self, pos: QPointF) -> tuple[float, float]:
        w, h = max(1, self.width()), max(1, self.height())
        return min(max(pos.x() / w, 0.0), 1.0), min(max(pos.y() / h, 0.0), 1.0)

    def _frame_point_at(self, pos: QPointF) -> tuple[float, float]:
        return tuple(self._guide_from_display(*self._normalized(pos)))

    def _display_guide_px(self, guide) -> tuple[QPointF, QPointF] | None:
        w, h = float(self.width()), float(self.height())
        a = self._guide_to_display(*guide[0])
        b = self._guide_to_display(*guide[1])
        if a is None or b is None:
            return None
        return QPointF(a[0] * w, a[1] * h), QPointF(b[0] * w, b[1] * h)

    def _hit_test_guide_endpoint(self, pos: QPointF) -> tuple[int, int] | None:
        best, best_dist = None, _GUIDE_GRAB_RADIUS_PX
        for gi, guide in enumerate(self._guides):
            pts = self._display_guide_px(guide)
            if pts is None:
                continue
            for ei, p in enumerate(pts):
                dist = ((p.x() - pos.x()) ** 2 + (p.y() - pos.y()) ** 2) ** 0.5
                if dist <= best_dist:
                    best, best_dist = (gi, ei), dist
        return best

    def _extended_line(self, p0: QPointF, p1: QPointF) -> tuple[QPointF, QPointF] | None:
        """The infinite line through p0/p1, clipped to this widget's own
        rect - for the dotted "where this guide leads" extension shown
        while a guide is being dragged."""
        w, h = float(self.width()), float(self.height())
        dx, dy = p1.x() - p0.x(), p1.y() - p0.y()
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return None
        t_lo, t_hi = -1e9, 1e9
        for p, d, lo, hi in ((p0.x(), dx, 0.0, w), (p0.y(), dy, 0.0, h)):
            if abs(d) < 1e-9:
                if not lo <= p <= hi:
                    return None
                continue
            t0, t1 = (lo - p) / d, (hi - p) / d
            t_lo, t_hi = max(t_lo, min(t0, t1)), min(t_hi, max(t0, t1))
        if t_lo > t_hi:
            return None
        return (QPointF(p0.x() + dx * t_lo, p0.y() + dy * t_lo),
                QPointF(p0.x() + dx * t_hi, p0.y() + dy * t_hi))

    def _guide_is_vertical(self, guide) -> bool:
        (u0, v0), (u1, v1) = guide
        return abs((v1 - v0) * self.height()) >= abs((u1 - u0) * self.width())

    def set_perspective_guides(self, guides) -> None:
        """Preloads previously-applied guides (CropSettings.perspective_guides)
        when the mode is re-entered, so they can be corrected."""
        self._guides = [[tuple(a), tuple(b)] for a, b in guides]
        self.update()

    def _guides_valid(self, guides) -> bool:
        vertical = sum(1 for g in guides if self._guide_is_vertical(g))
        return vertical <= _GUIDE_MAX_PER_ORIENTATION and len(guides) - vertical <= _GUIDE_MAX_PER_ORIENTATION

    def _unusable_guides(self) -> set[int]:
        """Indices of guides drawn red (rules chosen so a guide doesn't flash
        red while simply placing a 1st or 3rd guide):

        - At rest: a guide alone in its orientation (odd count placed and
          released - it needs a partner to measure convergence).
        - Mid-drag, the guide being dragged is red only if it points the
          wrong way: if another guide is waiting for a partner, the right
          direction is that guide's; otherwise any direction that still
          has room (a 3rd in one orientation would be refused). Never red
          just for being alone - it's still being placed.
        - Mid-drag, every other guide follows the at-rest rule, counting
          the dragged guide as present when it points the right way (so
          the lone guide it's about to pair turns white right away)."""
        orient = [self._guide_is_vertical(g) for g in self._guides]
        dragged = self._guide_drag[0] if self._guide_drag is not None else None
        bad = set()
        counted = list(range(len(self._guides)))
        if dragged is not None:
            others = [orient[i] for i in counted if i != dragged]
            waiting = {o for o in (True, False) if others.count(o) == 1}
            room = {o for o in (True, False) if others.count(o) < _GUIDE_MAX_PER_ORIENTATION}
            if orient[dragged] not in (waiting or room):
                bad.add(dragged)
                counted.remove(dragged)
        for i in counted:
            if i != dragged and sum(1 for j in counted if orient[j] == orient[i]) == 1:
                bad.add(i)
        return bad

    def _guide_near(self, pos: QPointF) -> int | None:
        """Index of the guide whose segment passes within
        _GUIDE_GRAB_RADIUS_PX of pos (for double-click delete)."""
        best, best_dist = None, _GUIDE_GRAB_RADIUS_PX
        for gi, guide in enumerate(self._guides):
            pts = self._display_guide_px(guide)
            if pts is None:
                continue
            a, b = pts
            dx, dy = b.x() - a.x(), b.y() - a.y()
            length2 = dx * dx + dy * dy
            t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((pos.x() - a.x()) * dx + (pos.y() - a.y()) * dy) / length2))
            dist = ((a.x() + t * dx - pos.x()) ** 2 + (a.y() + t * dy - pos.y()) ** 2) ** 0.5
            if dist <= best_dist:
                best, best_dist = gi, dist
        return best

    def _paint_perspective_guides(self) -> None:
        """Each guide as a white line with round endpoint handles over a
        dark halo (readable on any photo) - red when the solver can't use
        it (see _unusable_guides). The guide being dragged also shows a
        dotted extension across the whole frame, to line it up against a
        long edge."""
        if not self._guides:
            return
        unusable = self._unusable_guides()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for gi, guide in enumerate(self._guides):
            pts = self._display_guide_px(guide)
            if pts is None:
                continue
            p0, p1 = pts
            color = _GUIDE_MISMATCH_COLOR if gi in unusable else _GUIDE_COLOR
            if self._guide_drag is not None and self._guide_drag[0] == gi:
                extended = self._extended_line(p0, p1)
                if extended is not None:
                    halo = QPen(QColor(0, 0, 0, 90), 3)
                    halo.setStyle(Qt.DotLine)
                    painter.setPen(halo)
                    painter.drawLine(*extended)
                    dotted = QPen(QColor(color.red(), color.green(), color.blue(), 200), 1.5)
                    dotted.setStyle(Qt.DotLine)
                    painter.setPen(dotted)
                    painter.drawLine(*extended)
            painter.setPen(QPen(QColor(0, 0, 0, 120), 4))
            painter.drawLine(p0, p1)
            painter.setPen(QPen(color, 2))
            painter.drawLine(p0, p1)
            painter.setPen(QPen(QColor(0, 0, 0, 160), 1.5))
            painter.setBrush(color)
            for p in (p0, p1):
                painter.drawEllipse(p, 5.0, 5.0)
            painter.setBrush(Qt.NoBrush)
        painter.end()

    # -- white balance eyedropper / histogram pixel pick --------------------
    def _refresh_cursor(self) -> None:
        # All 3 eyedropper-style tools (white balance pick, histogram pixel
        # pick, film base pick) share the same cursor - whichever reason
        # it's armed for, the gesture (point at a pixel) is the same.
        if self.wb_pick_enabled or self.histogram_pick_enabled or self.film_base_pick_enabled:
            dpr = self.devicePixelRatioF() or 1.0
            size = 28
            # The Color/Histogram buttons' own eyedropper glyph, white over a
            # dark outline: a bare white glyph vanished over bright photos.
            glyph = tinted_svg_pixmap("Global/eyedropper.svg", size, QColor(Qt.white), dpr)
            outline = tinted_svg_pixmap("Global/eyedropper.svg", size, QColor(0, 0, 0, 220), dpr)
            pixmap = QPixmap(glyph.size())
            pixmap.setDevicePixelRatio(dpr)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
                painter.drawPixmap(dx, dy, outline)
            painter.drawPixmap(0, 0, glyph)
            painter.end()
            # Hotspot near the icon's own sampling tip (bottom-left area of
            # the glyph), not its center - matches where the cursor visually
            # points when sampling a pixel.
            self.setCursor(QCursor(pixmap, int(size * 0.2), int(size * 0.85)))
        elif self.perspective_enabled:
            self.setCursor(QCursor(Qt.CrossCursor))
        elif self.stretch_enabled:
            # A 4-way "drag in any direction" cross, not the open-hand Move on
            # Canvas uses - reads as "pull from this point" rather than "pick
            # this point" (a plain crosshair, tried first, was not expressive
            # enough).
            self.setCursor(QCursor(Qt.SizeAllCursor))
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
        # a live-hover tool is actually armed - this one, or guided
        # Perspective's endpoint-hover cursor.
        self.setMouseTracking(enabled or self.perspective_enabled)
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
        if (event.button() == Qt.LeftButton and self.perspective_enabled
                and not (self.wb_pick_enabled or self.film_base_pick_enabled)):
            # Grab an existing endpoint if one is close enough, otherwise
            # start a new guide whose far end follows the drag - unless 4
            # already exist (2 per orientation is the max, so a 5th could
            # never be valid). The pre-press state is kept so an edit that
            # turns out invalid on release can be undone (see release).
            hit = self._hit_test_guide_endpoint(event.position())
            if hit is None and len(self._guides) < 2 * _GUIDE_MAX_PER_ORIENTATION:
                self._guides_before_drag = [list(g) for g in self._guides]
                point = self._frame_point_at(event.position())
                self._guides.append([point, point])
                hit = (len(self._guides) - 1, 1)
            elif hit is not None:
                self._guides_before_drag = [list(g) for g in self._guides]
                # Moving an existing guide - the "move" cursor for the
                # whole drag (_refresh_cursor puts the crosshair back).
                self.setCursor(QCursor(Qt.SizeAllCursor))
            self._guide_drag = hit
            self.update()
            event.accept()
        elif event.button() == Qt.LeftButton and self.wb_pick_enabled:
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
        elif event.button() == Qt.LeftButton and self.stretch_enabled:
            pos = event.position()
            w, h = max(1, self.width()), max(1, self.height())
            u = min(max(pos.x() / w, 0.0), 1.0)
            v = min(max(pos.y() / h, 0.0), 1.0)
            self._stretch_dragging = True
            self._stretch_last_pos = pos
            self.stretch_drag_started.emit(u, v)
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
        if self.perspective_enabled and self._guide_drag is None:
            # Hover: the move cursor over a grabbable endpoint, the
            # crosshair (draw a new guide) everywhere else.
            over = self._hit_test_guide_endpoint(event.position()) is not None
            self.setCursor(QCursor(Qt.SizeAllCursor if over else Qt.CrossCursor))
        if self.perspective_enabled and self._guide_drag is not None:
            gi, ei = self._guide_drag
            self._guides[gi][ei] = self._frame_point_at(event.position())
            self.update()
            event.accept()
        elif self.crop_enabled and self._crop_drag_mode and self._crop_drag_start_pos is not None:
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
        elif self._stretch_dragging and self._stretch_last_pos is not None:
            pos = event.position()
            delta = pos - self._stretch_last_pos
            self._stretch_last_pos = pos
            w, h = max(1, self.width()), max(1, self.height())
            self.stretch_drag_delta.emit(delta.x() / w, delta.y() / h)
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

    def mouseDoubleClickEvent(self, event) -> None:
        # Guided Perspective: double-click a guide to delete it (the
        # default implementation would treat this as a 2nd press and start
        # a new guide instead).
        if (event.button() == Qt.LeftButton and self.perspective_enabled
                and not (self.wb_pick_enabled or self.film_base_pick_enabled)):
            gi = self._guide_near(event.position())
            if gi is not None:
                self._guides.pop(gi)
                self.update()
                self.perspective_guides_changed.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.perspective_enabled and self._guide_drag is not None and event.button() == Qt.LeftButton:
            gi, _ei = self._guide_drag
            self._guide_drag = None
            self._refresh_cursor()
            pts = self._display_guide_px(self._guides[gi])
            length = 0.0 if pts is None else ((pts[1].x() - pts[0].x()) ** 2 + (pts[1].y() - pts[0].y()) ** 2) ** 0.5
            if length < _GUIDE_MIN_LENGTH_PX or not self._guides_valid(self._guides):
                # A plain click/tiny drag (not a usable guide), or a 3rd
                # guide in one orientation - back to the pre-press state
                # (removes a new guide, reverts an edited one).
                self._guides = self._guides_before_drag
            self.update()
            if self._guides != self._guides_before_drag:
                self.perspective_guides_changed.emit()
            event.accept()
        elif self.crop_enabled and self._crop_drag_mode and event.button() == Qt.LeftButton:
            self._crop_drag_mode = None
            self._crop_drag_start_pos = None
            self._crop_drag_start_rect = None
            event.accept()
        elif self._stretch_dragging and event.button() == Qt.LeftButton:
            self._stretch_dragging = False
            self._stretch_last_pos = None
            self.stretch_drag_finished.emit()
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

    def _paint_stretch_grid(self) -> None:
        """Reference grid overlay for Stretch on Canvas, sized to the active
        layer and following its deformation: a grid spanning the whole canvas,
        each vertex forward-warped by imaging.warp_stretch_point using the
        active channel's own current pins (self._stretch_grid_pins, fed live by
        MainWindow on every pin change, including mid-drag), so it visibly
        deforms the same way the image itself does.

        Column and row counts are derived *independently* from the canvas's own
        on-screen width/height (each divided separately by
        _STRETCH_GRID_CELL_PX) so the unwarped cells come out square - not a
        single shared division count for both axes, which produced rectangular
        cells on any non-square canvas and made the deformation harder to
        read."""
        w, h = float(self.width()), float(self.height())
        if w <= 0 or h <= 0:
            return
        cell = self._STRETCH_GRID_CELL_PX
        cols = max(1, round(w / cell))
        rows = max(1, round(h / cell))
        pins = self._stretch_grid_pins
        verts = [[None] * (cols + 1) for _ in range(rows + 1)]
        for row in range(rows + 1):
            v = row / rows
            for col in range(cols + 1):
                u = col / cols
                wu, wv = imaging.warp_stretch_point(u, v, pins) if pins else (u, v)
                verts[row][col] = QPointF(wu * w, wv * h)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(255, 255, 255, 110), 1))
        for row in range(rows + 1):
            for col in range(cols):
                painter.drawLine(verts[row][col], verts[row][col + 1])
        for col in range(cols + 1):
            for row in range(rows):
                painter.drawLine(verts[row][col], verts[row + 1][col])
        painter.end()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.stretch_enabled:
            self._paint_stretch_grid()
        if self.perspective_enabled:
            self._paint_perspective_guides()
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
        self.stretch_drag_started = self.image_label.stretch_drag_started
        self.stretch_drag_delta = self.image_label.stretch_drag_delta
        self.stretch_drag_finished = self.image_label.stretch_drag_finished
        self.perspective_guides_changed = self.image_label.perspective_guides_changed
        self.image_label.zoom_delta.connect(self._on_zoom_delta)

        self.zoom = 1.0
        self._qimage: QImage | None = None
        self._showing_placeholder = False
        # The "100%"/zoom-percentage reference size - deliberately NOT
        # self._qimage's own width/height, so swapping between the live ~1400px
        # preview and an HQ Preview native-resolution pass for the *same*
        # photo/crop state (see MainWindow's HQ Preview) doesn't change the
        # on-screen box size, only how sharp the content inside it is (it used
        # to jump/shrink visibly on every such swap). Set via
        # set_reference_size(), called by
        # MainWindow.recompute_preview()/_recompute_preview_normal() alongside
        # set_image_rgb/set_image_gray - never by set_hq_image_rgb, which
        # intentionally leaves it untouched.
        self._ref_width = 0
        self._ref_height = 0
        # zoom_100()'s own target zoom value - "how many reference-space
        # pixels make up one native pixel" (1/preview_scale for the active
        # reference channel), so Real Size means true 1:1 native-pixel-to-
        # screen-pixel, not "100% of the capped preview" (which was never
        # actually real size to begin with - just the sharpest the live
        # pipeline could show before HQ Preview existed).
        self._native_zoom = 1.0
        # Whether Fit-to-window is the active persistent mode (see
        # zoom_fit()) - re-applied by set_reference_size() on every new
        # photo/crop state, not just computed once. Exited by any manual
        # zoom (set_zoom and everything that calls it).
        self._fit_mode = False

    def _on_zoom_delta(self, factor: float) -> None:
        self.set_zoom(self.zoom * factor)

    # -- crop overlay -----------------------------------------------------
    def set_crop_enabled(self, enabled: bool) -> None:
        self.image_label.set_crop_enabled(enabled)

    def set_crop_rect(self, x: float, y: float, w: float, h: float) -> None:
        self.image_label.set_crop_rect(x, y, w, h)

    def set_perspective_enabled(self, enabled: bool) -> None:
        self.image_label.set_perspective_enabled(enabled)

    def perspective_guides(self) -> list:
        return self.image_label.perspective_guides()

    def set_guide_mapping(self, to_display, from_display) -> None:
        self.image_label.set_guide_mapping(to_display, from_display)

    def set_perspective_guides(self, guides) -> None:
        self.image_label.set_perspective_guides(guides)

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

    def set_stretch_enabled(self, enabled: bool) -> None:
        self.image_label.set_stretch_enabled(enabled)

    def set_stretch_pins(self, pins: list) -> None:
        self.image_label.set_stretch_pins(pins)

    def set_wb_pick_enabled(self, enabled: bool) -> None:
        self.image_label.set_wb_pick_enabled(enabled)

    def set_film_base_pick_enabled(self, enabled: bool) -> None:
        self.image_label.set_film_base_pick_enabled(enabled)

    def set_histogram_pick_enabled(self, enabled: bool) -> None:
        self.image_label.set_histogram_pick_enabled(enabled)

    def set_reference_size(self, width: int, height: int, native_zoom: float = 1.0) -> None:
        """Redefines what the zoom percentage/Real Size are relative to -
        see the matching comment on self._ref_width in __init__. Called by
        MainWindow alongside set_image_rgb/set_image_gray (the live
        ~1400px-preview path), never alongside set_hq_image_rgb. While Fit
        mode is active (self._fit_mode, see zoom_fit()), re-applies it for
        the new dimensions instead of leaving the previous photo's own fit
        zoom value in place - a landscape photo's fit zoom shown at a
        portrait photo's own aspect ratio (or vice versa) doesn't actually
        fit it. Also re-paints either way (this used to only take effect on
        the *next* repaint, one frame behind set_image_rgb's own paint with
        the still-stale reference)."""
        self._ref_width = max(1, width)
        self._ref_height = max(1, height)
        self._native_zoom = max(MIN_ZOOM, native_zoom)
        if self._fit_mode:
            self._apply_fit_zoom()
        else:
            self._refresh_pixmap()

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

    def set_hq_image_rgb(self, rgb_uint8: np.ndarray) -> None:
        """HQ Preview's own entry point (see MainWindow._on_hq_preview_result)
        - swaps in a sharper array for the *same* photo/crop state without
        touching the zoom reference (set_reference_size) - same on-screen
        box size as just before, just a sharper fill. Never used for an
        actually different photo/crop; callers use set_image_rgb for that,
        which is always paired with a matching set_reference_size call."""
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
        # Target on-screen size comes from the stable reference dimensions,
        # not self._qimage's own (possibly HQ-swapped) size - see
        # set_reference_size. .scaled() still resamples whatever resolution
        # self._qimage actually holds into that fixed box, so a higher-res
        # source here reads sharper without changing the box size itself.
        w = max(1, int(self._ref_width * self.zoom))
        h = max(1, int(self._ref_height * self.zoom))
        pix = QPixmap.fromImage(self._qimage).scaled(
            w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(pix)
        self.image_label.resize(pix.size())
        # Screen pixels per *reference*-space pixel, not per self._qimage
        # pixel - align-drag deltas (mouseMoveEvent) get divided by this to
        # land in ChannelLayer.dx/dy's own unit, which is always preview-
        # space regardless of which resolution is currently on screen.
        self.image_label.display_scale = pix.width() / self._ref_width if self._ref_width else 1.0

    def _set_zoom_raw(self, zoom: float) -> None:
        """Applies a zoom value without touching self._fit_mode - the
        shared tail for both a manual zoom (set_zoom, which exits Fit mode)
        and Fit mode's own internal recompute (_apply_fit_zoom, which must
        NOT exit the very mode it's maintaining)."""
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        self._refresh_pixmap()

    def set_zoom(self, zoom: float) -> None:
        self._fit_mode = False
        self._set_zoom_raw(zoom)

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom / 1.25)

    def _fit_zoom_value(self) -> float:
        avail = self.viewport().size()
        scale = min(avail.width() / self._ref_width, avail.height() / self._ref_height)
        return scale if scale > 0 else 1.0

    def _apply_fit_zoom(self) -> None:
        self._set_zoom_raw(self._fit_zoom_value())

    def zoom_fit(self) -> None:
        """Fit-to-window is a persistent *mode* (self._fit_mode), not a
        one-time zoom value - set_reference_size() re-applies it on every new
        photo/crop state, so switching from e.g. a landscape to a portrait
        photo keeps actually fitting the viewport instead of reusing the
        previous photo's own fit zoom number (that reuse is what made some
        photos show too small/only partially visible right after this whole
        zoom-stability rework landed). Exited by any manual zoom (set_zoom, and
        therefore zoom_in/out/ wheel/pinch/Real Size)."""
        if self._qimage is None or self._ref_width == 0:
            return
        self._fit_mode = True
        self._apply_fit_zoom()

    def zoom_100(self) -> None:
        """"Real Size" - true 1:1 native-pixel-to-screen-pixel, via
        self._native_zoom (see set_reference_size) - not literally
        zoom==1.0, which would just be 100% of the (possibly much smaller)
        reference/preview size."""
        self.set_zoom(self._native_zoom)
