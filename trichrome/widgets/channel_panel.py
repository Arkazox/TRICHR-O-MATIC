"""Per-channel (R, G or B) control panel: load image, alignment, tone correction."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout,
    QToolButton, QVBoxLayout, QWidget,
)

from .. import i18n
from .controls import CollapsibleSection, SliderSpin
from .info_bubble import InfoButton
from .svg_icons import HEADER_COMPANION_BTN_SIZE, HEADER_COMPANION_ICON_SIZE, SvgToolButton
from .checkbox import CheckBox

CHANNEL_COLORS = {"R": "#e05555", "G": "#3fae4a", "B": "#4a7fe0"}
CHANNEL_KEY = {"R": "channel_r", "G": "channel_g", "B": "channel_b"}

# The already-established "muted gray" elsewhere in this app (e.g. the
# Mode selector's Solo icon) - used to gray out a section's own colored
# accent border when the whole Trichrome Process block is disabled (Solo
# mode), since an explicit QSS color doesn't automatically dim the way a
# plain unstyled border would when the widget/its ancestor is disabled.
_DISABLED_BORDER_COLOR = "#5c5c5c"

# SvgToolButton's own hit-target box (HEADER_COMPANION_BTN_SIZE, 34x30) pads
# its icon (HEADER_COMPANION_ICON_SIZE, 20px) centered - a sensible click
# target, but it means the icon itself sits ~7px left of the button's own
# bounding-box edge. A section's Reset button needs to align with the slider
# rows' own right edge below it (ClickToEditValue's right-aligned numeric
# value) - since the button's bounding box (right-justified in header_row) and
# the slider rows (filling content_layout) both already stop at the same x by
# default, closing that ~7px gap means giving content_layout a matching *extra*
# right margin instead, so the values themselves shift left to meet the icon,
# so the Reset buttons line up with the slider values. A negative right
# margin/spacing on header_row - the more obvious-looking fix, pulling the
# button the other way - doesn't work: confirmed directly that Qt clamps any
# negative QLayout margin/spacing to 0, silently discarding it.
_RESET_BUTTON_OPTICAL_INSET = (HEADER_COMPANION_BTN_SIZE[0] - HEADER_COMPANION_ICON_SIZE) // 2


def _add_header_reset_button(section: CollapsibleSection, button: SvgToolButton) -> None:
    """Right-justifies ``button`` in ``section``'s own header row - see
    _RESET_BUTTON_OPTICAL_INSET for the optical alignment against the
    section's own slider values, applied separately to content_layout."""
    section.header_row.addStretch(1)
    section.header_row.addWidget(button)


def _section_style(color: str) -> str:
    # A single colored left-edge accent, not a full colored box - avoids
    # doubling up with ChannelTabFrame's own colored folder border. Used
    # by all 3 of tone_box/position_box/distortion_box, purely to visually
    # split them from each other within one ChannelPanel - the color itself
    # doesn't add any information the folder frame above doesn't already
    # show.
    return (f"CollapsibleSection {{ border: none; border-left: 3px solid {color}; "
            f"border-radius: 0px; }}")


def _rounded_polygon_path(points: list[tuple[float, float]], radius: float) -> QPainterPath:
    """Builds a closed path from an ordered polygon outline (clockwise or
    counter-clockwise, doesn't matter), rounding every single vertex by the
    same radius - each corner is clamped to half its shorter adjacent edge, so
    a short edge (e.g. the notch's own width when a channel's tab is narrow)
    degrades gracefully instead of overshooting into the next corner. Used for
    ChannelTabFrame's whole folder outline so every corner - the frame's own
    bottom corners, the notch's 2 shoulders, its own top-left/top-right - gets
    the exact same treatment, instead of an earlier version that explicitly
    rounded some corners at one radius, others at a different radius, and left
    a few as bare sharp lineTo-lineTo joints for the pen's own join style to
    render however it pleased - a real, confirmed inconsistency that made the
    border look irregular."""
    n = len(points)
    path = QPainterPath()
    for i in range(n):
        px, py = points[(i - 1) % n]
        cx, cy = points[i]
        nx, ny = points[(i + 1) % n]
        in_dx, in_dy = cx - px, cy - py
        out_dx, out_dy = nx - cx, ny - cy
        in_len = (in_dx ** 2 + in_dy ** 2) ** 0.5
        out_len = (out_dx ** 2 + out_dy ** 2) ** 0.5
        r = min(radius, in_len / 2 if in_len else 0.0, out_len / 2 if out_len else 0.0)
        start = (cx - in_dx / in_len * r, cy - in_dy / in_len * r) if in_len else (cx, cy)
        end = (cx + out_dx / out_len * r, cy + out_dy / out_len * r) if out_len else (cx, cy)
        if i == 0:
            path.moveTo(*start)
        else:
            path.lineTo(*start)
        path.quadTo(cx, cy, *end)
    path.closeSubpath()
    return path


class _ChannelTabButton(QToolButton):
    """One tab inside ChannelTabFrame - shows the channel's name as plain bold
    text (replacing an earlier colored circle-letter icon), tinted in the
    channel's own color - full color while active, dimmed while not, brighter
    on hover. Not checkable/exclusive by itself - ChannelTabFrame tracks which
    index is active and calls set_active() on the outgoing/incoming buttons,
    since the active tab's look is also expressed geometrically (its rect
    matches the frame's own painted "folder" notch, see
    ChannelTabFrame.paintEvent) rather than through Qt's normal
    checkable/QButtonGroup styling.

    Paints only its own text - every other pixel of the tab strip's
    chrome (the shelf fill behind inactive tabs, the divider between 2
    adjacent inactive tabs, the active tab's folder notch) is painted
    centrally by ChannelTabFrame instead of by each button individually.
    An earlier version had each inactive tab paint its own independent
    rounded-corner shelf fill, which left a stray gap of the frame's own
    plain background peeking through at the seam between an inactive tab
    and the active one right next to it (every tab rounded both of its
    own top corners regardless of whether that side actually bordered
    another tab, or the active one) - a real, confirmed bug, not just a
    style preference, fixed by moving all of it to one shared paintEvent
    that can reason about which edges are actually outer edges."""

    def __init__(self, text: str, color, parent: QWidget | None = None):
        super().__init__(parent)
        self.setText(text)
        self._color = QColor(color)
        self._active = False
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QToolButton { border: none; background: transparent; }")
        # Bold, plain app-default point size - matches the Files block's own
        # "Red:"/"Green:"/"Blue:" channel labels (import_panel.py's
        # channel_label, a QLabel styled "color: {color}; font-weight: bold;",
        # no size override), so it matches the Files block - replacing an
        # earlier +2pt bump that made this bigger than that reference instead
        # of matching it. Copies QApplication.font() rather than this
        # QToolButton's own self.font(), for the same reason
        # CollapsibleSection's header does (controls.py) - a plain QToolButton
        # doesn't reliably inherit the app-wide default point size here (a
        # native "small control" sizing quirk), so reading self.font() first
        # would still land on that smaller size, not the QLabel-matching one
        # this is trying to match.
        app_font = QApplication.font()
        font = QFont(app_font.family(), app_font.pointSize(), QFont.Bold)
        self.setFont(font)

    def set_active(self, active: bool) -> None:
        if self._active != active:
            self._active = active
            self.update()

    def _text_color(self) -> QColor:
        color = QColor(self._color)
        if not self.isEnabled():
            color.setAlpha(90)
        elif self._active:
            color.setAlpha(255)
        elif self.underMouse():
            color.setAlpha(210)
        else:
            color.setAlpha(150)
        return color

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(self._text_color())
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())
        painter.end()

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)


class ChannelTabFrame(QFrame):
    """A "folder" tab strip + content frame in one widget: the R/G/B tabs above
    MainWindow.channel_stack (``content``), where the active tab's colored
    border rises up out of the frame around it - a manila-folder silhouette,
    not a separate frame the tab merely touches (prototyped first as a
    throwaway HTML mockup using a CSS negative-margin overlap trick; that trick
    doesn't translate to Qt, so this draws the whole outline itself instead).

    ``content`` (MainWindow.channel_stack) is added through this widget's
    own QVBoxLayout, inset by a top margin reserving room for the tab
    strip - so its sizing/updateGeometry propagation works exactly like
    any other layout-managed widget in this app. Only the 3 tab buttons
    are positioned manually (resizeEvent) rather than through that
    layout, since their geometry is fixed/simple (equal thirds of the
    width, a known height) and needs to line up pixel-for-pixel with the
    notch this class paints - two independent layouts trying to agree on
    that boundary is exactly the fragility the CSS version had to work
    around. All 3 tabs' own background/border chrome is painted here too
    (not by the buttons themselves) for the same reason - see
    _ChannelTabButton's own docstring for the seam bug that caused.
    """

    channel_changed = Signal(int)

    _TAB_HEIGHT = 30
    _TAB_GAP = 6  # how far an inactive tab's own text sits above the frame line
    _BORDER_WIDTH = 3.0
    # One shared radius for every corner in the folder outline (bottom corners,
    # notch shoulders, frame-top corners) - a real, confirmed fix for what 2
    # different radii (_BODY_RADIUS=8/_TAB_RADIUS=6) plus a mix of
    # explicitly-rounded corners and bare sharp lineTo-lineTo corners left to
    # the pen's own join style were doing: different corners of the same
    # outline visibly curving differently. See _folder_path()'s own docstring
    # for how this is now applied uniformly.
    _CORNER_RADIUS = 8.0
    _CONTENT_MARGIN = 10
    # Extra top-only padding, on top of _CONTENT_MARGIN, between the frame line
    # and "Alignment" - matches the visual gap ChannelPanel already puts
    # between its own Alignment/Light sections. Left/right/bottom stay at plain
    # _CONTENT_MARGIN.
    _TOP_EXTRA_GAP = 8
    _SHELF_COLOR = QColor(255, 255, 255, 16)
    _DIVIDER_COLOR = QColor(255, 255, 255, 40)
    _PANE_BG = QColor("#232227")

    def __init__(self, labels: list[str], content: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self._labels = list(labels)
        self._colors = [QColor(CHANNEL_COLORS.get(label, "#888")) for label in labels]
        self._active_index = 0

        bw = round(self._BORDER_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            bw + self._CONTENT_MARGIN, self._TAB_HEIGHT + self._CONTENT_MARGIN + self._TOP_EXTRA_GAP,
            bw + self._CONTENT_MARGIN, bw + self._CONTENT_MARGIN)
        layout.addWidget(content)

        self.buttons: list[_ChannelTabButton] = []
        for i, label in enumerate(labels):
            text = i18n.tr(CHANNEL_KEY.get(label, label))
            btn = _ChannelTabButton(text, self._colors[i], self)
            btn.clicked.connect(lambda _checked=False, idx=i: self._select(idx))
            self.buttons.append(btn)
        self.buttons[0].set_active(True)

    def retranslate_ui(self) -> None:
        for label, btn in zip(self._labels, self.buttons):
            btn.setText(i18n.tr(CHANNEL_KEY.get(label, label)))

    def _select(self, index: int) -> None:
        if index == self._active_index:
            return
        self.buttons[self._active_index].set_active(False)
        self._active_index = index
        self.buttons[index].set_active(True)
        self.update()
        self.channel_changed.emit(index)

    def _tab_bounds(self, index: int) -> tuple[int, int]:
        # Rounded to whole pixels (not left as raw floats) so every use -
        # button geometry, the folder notch, the inactive shelf segments, the
        # divider line - agrees on the exact same boundary; a stray sub-pixel
        # mismatch between them was making the folder border look soft/uneven
        # in different spots (a real, confirmed rendering bug: the border must
        # be even all the way around).
        n = len(self.buttons)
        w = self.width()
        return (round(index * w / n), round((index + 1) * w / n))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        for i, btn in enumerate(self.buttons):
            x, x2 = self._tab_bounds(i)
            h = self._TAB_HEIGHT if i == self._active_index else self._TAB_HEIGHT - self._TAB_GAP
            btn.setGeometry(x, 0, x2 - x, h)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        self._paint_shelf(painter)

        path = self._folder_path()
        painter.fillPath(path, self._PANE_BG)
        # No colored border stroke - just the fill silhouette. See the notes
        # above for the full pen/path setup if a border comes back.
        painter.end()

    def _paint_shelf(self, painter: QPainter) -> None:
        """Fills the "shelf" area above the frame line for every inactive tab,
        as one contiguous fill per contiguous run of inactive tabs - there can
        be 2 separate runs at once (e.g. R alone / B alone when G is active) -
        rounded only at a run's edge that's also the whole strip's own outer
        edge (index 0's left edge, or the last index's right edge); an edge
        that instead touches the active tab is always left square. That
        square-inner-edge rule is what avoids a stray rounded-corner gap of
        this widget's own plain background showing through right next to the
        active tab's own border - a real, confirmed bug in an earlier version
        where every tab rounded both of its own top corners regardless of what
        sat next to it (it left a visible gray gap between the tabs and the
        active tab). Also draws a thin divider between the 2 tabs of any 2-wide
        run - a light separation between adjacent inactive tabs (only drawn
        between 2 tabs that are actually adjacent to each other, e.g. not
        between R and B when G is active and sits between them).

        The fill reaches all the way down to the frame line (_TAB_HEIGHT, not
        _TAB_HEIGHT - _TAB_GAP) - an inactive tab's own *button* still stops
        short by _TAB_GAP (resizeEvent), so its text still reads as "receded"
        versus the active tab's, but the fill underneath it now touches the
        border instead of leaving a plain- background gap between the shelf and
        the frame - a real, confirmed bug: a gap between the tabs and the
        colored border."""
        n = len(self.buttons)
        shelf_h = float(self._TAB_HEIGHT)
        i = 0
        while i < n:
            if i == self._active_index:
                i += 1
                continue
            start = i
            while i < n and i != self._active_index:
                i += 1
            end = i  # exclusive
            x0, _ = self._tab_bounds(start)
            _, x1 = self._tab_bounds(end - 1)
            round_left = start == 0
            round_right = end == n
            painter.fillPath(
                self._shelf_segment_path(x0, x1, shelf_h, round_left, round_right), self._SHELF_COLOR)
            if end - start == 2:
                mid, _ = self._tab_bounds(start + 1)
                painter.setPen(QPen(self._DIVIDER_COLOR, 1))
                painter.drawLine(QPointF(mid, 4), QPointF(mid, shelf_h - 4))

    def _shelf_segment_path(self, x0: float, x1: float, h: float, round_left: bool, round_right: bool) -> QPainterPath:
        r = self._CORNER_RADIUS
        path = QPainterPath()
        path.moveTo(x0, h)
        if round_left:
            path.lineTo(x0, r)
            path.quadTo(x0, 0, x0 + r, 0)
        else:
            path.lineTo(x0, 0)
        if round_right:
            path.lineTo(x1 - r, 0)
            path.quadTo(x1, 0, x1, r)
        else:
            path.lineTo(x1, 0)
        path.lineTo(x1, h)
        path.closeSubpath()
        return path

    def _folder_path(self) -> QPainterPath:
        """The full folder outline as one ordered polygon (8 corners,
        clockwise from bottom-left), rounded uniformly by
        _rounded_polygon_path() - see that function for why every corner
        needs to go through the same helper rather than some being
        hand-rounded here and others left as bare sharp lineTo-lineTo
        corners for the pen's own join style to render (inconsistently)
        instead."""
        w = float(self.width())
        h = float(self.height())
        top = float(self._TAB_HEIGHT)
        active_left, active_right = self._tab_bounds(self._active_index)

        points = [
            (0.0, h),                    # bottom-left
            (w, h),                      # bottom-right
            (w, top),                    # right side, up to the tab row
            (active_right, top),         # shoulder: into the notch
            (active_right, 0.0),         # notch top-right
            (active_left, 0.0),          # notch top-left
            (active_left, top),          # shoulder: out of the notch
            (0.0, top),                  # left side, up to the tab row
        ]
        return _rounded_polygon_path(points, self._CORNER_RADIUS)


class ChannelPanel(QWidget):
    align_changed = Signal()
    distortion_changed = Signal()
    tone_changed = Signal()
    reset_align_requested = Signal()
    reset_distortion_requested = Signal()
    reset_tone_requested = Signal()
    reset_stretch_requested = Signal()
    solo_toggled = Signal(bool)
    active_toggled = Signal(bool)
    stretch_toggled = Signal(bool)

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.label = label
        self._color = CHANNEL_COLORS.get(label, "#888")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.active_checkbox = CheckBox()
        self.active_checkbox.toggled.connect(self.active_toggled.emit)
        self.active_info_button = InfoButton("active_layer_info")

        # "Stretch on Canvas" - same "Active"-style checkbox + info-button pair
        # as Move on Canvas above, but for the Distortion section's own
        # localized pin-drag warp (ChannelLayer.stretch_pins,
        # imaging.apply_stretch_warp) - see MainWindow.stretch_index/
        # on_stretch_toggled for the mutual-exclusion-with-Move-on-Canvas and
        # cross-tab-follow behavior, mirroring active_index exactly.
        self.stretch_checkbox = CheckBox()
        self.stretch_checkbox.toggled.connect(self.stretch_toggled.emit)
        self.stretch_info_button = InfoButton("stretch_layer_info")
        # Resets only stretch_pins, not the 4 Distortion sliders - separate
        # from the section's own Reset button. Right-justified in stretch_row,
        # below - which inherits distortion_layout's own
        # _RESET_BUTTON_OPTICAL_INSET right margin, so it lands flush with
        # reset_distortion_button/the slider values without needing its own
        # alignment logic.
        self.reset_stretch_button = SvgToolButton(
            "Global/Reset.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.reset_stretch_button.clicked.connect(self.reset_stretch_requested.emit)

        # --- 3 peer collapsible sections (Light, Position, Distortion) --- A
        # colored left-edge accent (not a full box, which would double up with
        # the ChannelTabFrame's own colored border) - the way to visually split
        # each section, preferred over a plain 1px hairline. Each section's own
        # Reset button lives right-justified in its header row, beside its
        # title (not at the bottom), using the same "toggle_button +
        # addStretch(1) + button" pattern batch_window.py's own
        # Auto-Import-Rules/Sequential-Import- Rule "?" buttons already
        # established, rather than a trailing bottom row.

        # --- Light/tone section - placed first of the 3 ---
        self.tone_box = CollapsibleSection()
        self.tone_box.setStyleSheet(_section_style(self._color))
        self.reset_tone_button = SvgToolButton(
            "Global/Reset.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.reset_tone_button.clicked.connect(self.reset_tone_requested.emit)
        _add_header_reset_button(self.tone_box, self.reset_tone_button)
        tone_layout = self.tone_box.content_layout
        # Extra right margin - see _RESET_BUTTON_OPTICAL_INSET.
        tone_layout.setContentsMargins(14, 2, _RESET_BUTTON_OPTICAL_INSET, 0)
        # Extra air between the section's own disclosure header ("Light") and
        # its first content ("Exposure") - the header's own layout only left
        # 2px there by default.
        tone_layout.addSpacing(6)
        # Real unit (stops/EV), not percent_mode - like alignment's dx/dy/
        # scale/rotation, its unit already means something on its own. It
        # differs from Brightness (a plain additive offset, percent_mode)
        # despite both looking like "make it lighter": exposure is a
        # multiplicative gain applied first (see imaging.apply_tone_curve).
        self.exposure = SliderSpin(i18n.tr("exposure_label"), -5.0, 5.0, 0.0, decimals=2, percent_mode=False)
        self.brightness = SliderSpin(i18n.tr("brightness_label"), -0.5, 0.5, 0.0, decimals=3, percent_mode=True)
        self.contrast = SliderSpin(i18n.tr("contrast_label"), 0.0, 3.0, 1.0, decimals=2, percent_mode=True)
        self.highlights = SliderSpin(i18n.tr("highlights_label"), -1.0, 1.0, 0.0, decimals=2, percent_mode=True)
        self.shadows = SliderSpin(i18n.tr("shadows_label"), -1.0, 1.0, 0.0, decimals=2, percent_mode=True)
        self.white_point = SliderSpin(i18n.tr("white_point"), -0.5, 0.5, 0.0, decimals=3, percent_mode=True)
        self.black_point = SliderSpin(i18n.tr("black_point"), -0.5, 0.5, 0.0, decimals=3, percent_mode=True)
        self.gamma = SliderSpin(i18n.tr("gamma_label"), 0.1, 4.0, 1.0, decimals=2, percent_mode=True)
        for w in (self.exposure, self.brightness, self.contrast, self.highlights, self.shadows,
                  self.white_point, self.black_point, self.gamma):
            w.value_changed.connect(lambda _v: self.tone_changed.emit())
            tone_layout.addWidget(w)
        root.addWidget(self.tone_box)

        root.addSpacing(6)

        # --- Position section (dx/dy/scale/rotation - unchanged) ---
        self.position_box = CollapsibleSection()
        self.position_box.setStyleSheet(_section_style(self._color))
        self.reset_align_button = SvgToolButton(
            "Global/Reset.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.reset_align_button.clicked.connect(self.reset_align_requested.emit)
        _add_header_reset_button(self.position_box, self.reset_align_button)
        align_layout = self.position_box.content_layout
        # Extra right margin - see _RESET_BUTTON_OPTICAL_INSET.
        align_layout.setContentsMargins(14, 2, _RESET_BUTTON_OPTICAL_INSET, 0)
        align_layout.addSpacing(6)
        active_row = QHBoxLayout()
        active_row.addWidget(self.active_checkbox)
        active_row.addWidget(self.active_info_button)
        active_row.addStretch(1)
        align_layout.addLayout(active_row)
        self.dx = SliderSpin(i18n.tr("offset_x"), -500, 500, 0.0, decimals=1)
        self.dy = SliderSpin(i18n.tr("offset_y"), -500, 500, 0.0, decimals=1)
        self.scale = SliderSpin(i18n.tr("scale_label"), 0.5, 2.0, 1.0, decimals=4)
        self.rotation = SliderSpin(i18n.tr("rotation_label"), -45, 45, 0.0, decimals=2)
        for w in (self.dx, self.dy, self.scale, self.rotation):
            w.value_changed.connect(lambda _v: self.align_changed.emit())
            align_layout.addWidget(w)
        root.addWidget(self.position_box)

        root.addSpacing(6)

        # --- Distortion section - a real per-shot lens correction (radial
        # distortion, vertical/horizontal perspective, anamorphic squeeze),
        # split from Position into its own section and own Reset button, since
        # it's a fixed lens characteristic set once rather than fiddled with on
        # every drag-to-align the way Position is - see
        # ChannelLayer.distortion's own comment in model.py, and
        # imaging.apply_lens_correction for the actual warp math. Auto Align
        # never touches any of these 4 (MainWindow.on_auto_align_all only ever
        # estimates/writes dx/dy/scale/rotation).
        self.distortion_box = CollapsibleSection()
        self.distortion_box.setStyleSheet(_section_style(self._color))
        self.reset_distortion_button = SvgToolButton(
            "Global/Reset.svg", size=HEADER_COMPANION_BTN_SIZE, icon_size=HEADER_COMPANION_ICON_SIZE)
        self.reset_distortion_button.clicked.connect(self.reset_distortion_requested.emit)
        _add_header_reset_button(self.distortion_box, self.reset_distortion_button)
        distortion_layout = self.distortion_box.content_layout
        # Extra right margin - see _RESET_BUTTON_OPTICAL_INSET.
        distortion_layout.setContentsMargins(14, 2, _RESET_BUTTON_OPTICAL_INSET, 0)
        distortion_layout.addSpacing(6)
        stretch_row = QHBoxLayout()
        stretch_row.addWidget(self.stretch_checkbox)
        stretch_row.addWidget(self.stretch_info_button)
        stretch_row.addStretch(1)
        stretch_row.addWidget(self.reset_stretch_button)
        distortion_layout.addLayout(stretch_row)
        self.distortion = SliderSpin(i18n.tr("distortion_label"), -1.0, 1.0, 0.0, decimals=3, percent_mode=True)
        self.perspective_v = SliderSpin(i18n.tr("perspective_v_label"), -1.0, 1.0, 0.0, decimals=3, percent_mode=True)
        self.perspective_h = SliderSpin(i18n.tr("perspective_h_label"), -1.0, 1.0, 0.0, decimals=3, percent_mode=True)
        self.anamorphic = SliderSpin(i18n.tr("anamorphic_label"), -1.0, 1.0, 0.0, decimals=3, percent_mode=True)
        for w in (self.distortion, self.perspective_v, self.perspective_h, self.anamorphic):
            w.value_changed.connect(lambda _v: self.distortion_changed.emit())
            distortion_layout.addWidget(w)
        root.addWidget(self.distortion_box)

        # --- Solo preview toggle, below all 3 sections and styled discreetly
        # (the same muted "#888 / 11px" secondary-text convention already used
        # elsewhere in this app, e.g. import_panel.py's filename labels) - it's
        # a transient preview toggle, not on the same footing as the 3 real
        # edit sections above it.
        root.addSpacing(6)
        solo_row = QHBoxLayout()
        self.solo_checkbox = CheckBox()
        self.solo_checkbox.setStyleSheet("QCheckBox { color: #888; font-size: 11px; }")
        self.solo_checkbox.toggled.connect(self.solo_toggled.emit)
        solo_row.addWidget(self.solo_checkbox)
        solo_row.addStretch(1)
        root.addLayout(solo_row)

        self.retranslate_ui()

    # -- helpers -------------------------------------------------------
    def set_frame_disabled(self, disabled: bool) -> None:
        """Grays this panel's 3 nested CollapsibleSection accent borders to
        _DISABLED_BORDER_COLOR - restores the real channel color when
        re-enabled. Needed alongside setEnabled(False) (which
        MainWindow._sync_channels_panel_availability already applies to the
        whole Trichrome Process block, cascading down to this panel)
        because an explicit QSS color, unlike a plain unstyled border,
        doesn't automatically dim just because the widget (or an ancestor)
        is disabled."""
        color = _DISABLED_BORDER_COLOR if disabled else self._color
        self.tone_box.setStyleSheet(_section_style(color))
        self.position_box.setStyleSheet(_section_style(color))
        self.distortion_box.setStyleSheet(_section_style(color))

    def block_align_signals(self, block: bool) -> None:
        # Covers both Position and Distortion sliders - now 2 separate
        # sibling sections, but MainWindow._sync_panel_from_layer still sets
        # all 8 values in one blocked batch regardless of the 2 separate
        # change signals (align_changed/distortion_changed) each group fires.
        for w in (self.dx, self.dy, self.scale, self.rotation,
                  self.distortion, self.perspective_v, self.perspective_h, self.anamorphic):
            w.blockSignals(block)

    def block_tone_signals(self, block: bool) -> None:
        for w in (self.black_point, self.white_point, self.gamma, self.exposure, self.brightness,
                  self.contrast, self.highlights, self.shadows):
            w.blockSignals(block)

    def set_sliders_enabled(self, enabled: bool) -> None:
        for w in (self.dx, self.dy, self.scale, self.rotation,
                  self.distortion, self.perspective_v, self.perspective_h, self.anamorphic,
                  self.black_point, self.white_point, self.gamma, self.exposure, self.brightness,
                  self.contrast, self.highlights, self.shadows):
            w.setEnabled(enabled)

    def retranslate_ui(self) -> None:
        self.active_checkbox.setText(i18n.tr("active_checkbox"))
        self.stretch_checkbox.setText(i18n.tr("stretch_checkbox"))
        self.reset_stretch_button.setToolTip(i18n.tr("reset_stretch_tooltip"))
        self.solo_checkbox.setText(i18n.tr("solo_checkbox"))

        self.position_box.setTitle(i18n.tr("position_group"))
        self.dx.set_label_text(i18n.tr("offset_x"))
        self.dy.set_label_text(i18n.tr("offset_y"))
        self.scale.set_label_text(i18n.tr("scale_label"))
        self.rotation.set_label_text(i18n.tr("rotation_label"))
        self.reset_align_button.setToolTip(i18n.tr("reset_position_tooltip"))

        self.distortion_box.setTitle(i18n.tr("distortion_group"))
        self.distortion.set_label_text(i18n.tr("distortion_label"))
        self.perspective_v.set_label_text(i18n.tr("perspective_v_label"))
        self.perspective_h.set_label_text(i18n.tr("perspective_h_label"))
        self.anamorphic.set_label_text(i18n.tr("anamorphic_label"))
        self.reset_distortion_button.setToolTip(i18n.tr("reset_distortion_tooltip"))

        self.tone_box.setTitle(i18n.tr("tone_group"))
        self.black_point.set_label_text(i18n.tr("black_point"))
        self.white_point.set_label_text(i18n.tr("white_point"))
        self.highlights.set_label_text(i18n.tr("highlights_label"))
        self.shadows.set_label_text(i18n.tr("shadows_label"))
        self.gamma.set_label_text(i18n.tr("gamma_label"))
        self.exposure.set_label_text(i18n.tr("exposure_label"))
        self.brightness.set_label_text(i18n.tr("brightness_label"))
        self.contrast.set_label_text(i18n.tr("contrast_label"))
        self.reset_tone_button.setToolTip(i18n.tr("reset_tone_tooltip"))

        for w in (self.dx, self.dy, self.scale, self.rotation,
                  self.distortion, self.perspective_v, self.perspective_h, self.anamorphic,
                  self.black_point, self.white_point, self.gamma, self.exposure, self.brightness,
                  self.contrast, self.highlights, self.shadows):
            w.retranslate_ui()
