"""Quick Tour (Help ▸ Quick Tour, the toolbar's "?" menu, and the welcome
window shown at launch) - a guided walk through the app's main areas.

Shape:
- ``WelcomeDialog`` (widgets/welcome_dialog.py) first - logo, version, a
  short description, "Open at startup", Close / Start the Tour.
- Then ``QuickTour`` runs the steps: ``TourOverlay``, one transparent child
  widget covering the whole MainWindow, dims everything except one or more
  "holes" cut around the real widgets each step points at (accent-blue
  border + glow), with ``TourCallout`` (Step X/N, title, text, a clickable
  timeline, Back/Next/Skip) beside them. Holes and callout ease toward
  their target every frame, so they follow scrolling/resizing for free.

A **child** widget, never a separate top-level window - a top-level overlay
window broke native drag hit-testing elsewhere in this app (the block system's
drag-and-drop).

The tour never touches photos, the session, or the undo stack. It does change
the *layout* (every block shown and expanded, except Scan; the Scan step
switches to the built-in Scan layout) and puts it back exactly as it was on
Finish/Skip/Esc: ``_capture_layout_state()``/``_apply_layout_state()`` in
Advanced mode, only the 4 blocks' own collapse state in Light mode (whose
layout is a fixed render override, see _apply_light_mode_block_layout). Every
menu action (except Quit) is disabled while it runs, and the overlay swallows
all mouse/keyboard input including shortcuts (ShortcutOverride), so nothing
underneath can be edited mid-tour.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import (
    QAbstractAnimation, QEasingCurve, QEvent, QObject, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, Qt, QTimer, Signal,
)
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractScrollArea, QApplication, QFrame, QGraphicsOpacityEffect,
    QHBoxLayout, QLabel, QPushButton, QToolTip, QVBoxLayout, QWidget,
)

from . import i18n
from .paths import resource_path
from .widgets.block_header_bar import BlockDragHandle, set_block_collapsed
from .widgets.button_style import style_primary_button, style_secondary_button

ACCENT = QColor("#5b9bd5")
_WIP_COLOR = "#f2c40c"
_DIM = QColor(8, 8, 12, 165)
_HOLE_PAD = 6
# Minimum distance between a hole and the window edge - wide enough for
# the 2px border plus most of its glow.
_HOLE_INSET = 4
_HOLE_RADIUS = 9.0
_CALLOUT_GAP = 18
_EDGE_MARGIN = 12
# Fraction of the remaining distance covered per frame - an exponential
# ease that also naturally follows a target that keeps moving (scroll).
_EASE = 0.24
_FRAME_MS = 16
_IDLE_POLL_MS = 120
_SCROLL_MS = 380
_FADE_MS = 220
_SETUP_FALLBACK_MS = 1500  # _finish_setup if the opening animation never settles
# A hole from the previous step keeps morphing into a new one only when it
# is this close to the new targets; a farther one is left behind and fades.
# Without this, a step change across the window (Scan block -> workspace
# buttons) swept a hole over everything in between.
_CARRY_GAP = 40
_LEAVE_STEP = 0.08


# ----------------------------------------------------------------------
# Steps
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class TourStep:
    key: str  # i18n: quick_tour_{key}_title / quick_tour_{key}_body
    # Hole groups: each inner list is unioned into one highlighted hole.
    # Hidden widgets are skipped; a step with no visible target shows a
    # centered callout over a fully dimmed window.
    targets: Callable | None = None
    place: str = "right"  # preferred callout side: right/left/top/bottom/inside/center
    layout: str = "tour"  # Advanced mode only: "tour" or "scan"
    kind: str = ""  # "batch" (Batch Import window card) / "light_diagram"
    wip: bool = False
    modes: tuple = ("advanced",)
    light_body_key: str | None = None  # body override while in Light mode
    scan_off_body_key: str | None = None  # body override while the Scan tool is disabled


def _block(key):
    return lambda mw: [[mw.block_widgets[key]]]


STEPS = (
    TourStep("sessions", lambda mw: [
        [mw.new_session_toolbar_btn, mw.open_session_toolbar_btn, mw.save_session_toolbar_btn]],
        place="bottom"),
    TourStep("toolbar", lambda mw: [[mw.import_toolbar_btn], [mw.export_toolbar_btn]], place="bottom"),
    TourStep("batch", kind="batch"),
    TourStep("preview", lambda mw: [[mw.canvas]], place="inside", modes=("advanced", "light")),
    TourStep("filmstrip", lambda mw: [[mw.carousel, mw.bottom_bar]], place="top"),
    TourStep("files", _block("files"), modes=("advanced", "light")),
    TourStep("channels", _block("channels"), modes=("advanced", "light")),
    TourStep("histogram", _block("histogram"), place="left", modes=("advanced", "light")),
    TourStep("crop", _block("crop"), place="left", modes=("advanced", "light")),
    TourStep("light", _block("light"), place="left"),
    TourStep("color", _block("color"), place="left"),
    TourStep("curves", _block("curves"), place="left"),
    TourStep("scan", lambda mw: [[mw.block_widgets["scan"]], [mw.scan_toolbar_btn]],
             layout="scan", wip=True),
    TourStep("workspaces", lambda mw: [
        [mw.trichrome_toolbar_btn, mw.settings_toolbar_btn, mw.crop_toolbar_btn, mw.scan_toolbar_btn]],
        place="bottom", scan_off_body_key="quick_tour_workspaces_body_no_scan"),
    TourStep("arrange", lambda mw: [
        [mw.light_panel.findChild(BlockDragHandle), mw.block_close_buttons["light"]],
        [mw.left_panel_toggle_btn, mw.right_panel_toggle_btn]], place="left"),
    TourStep("light_mode", place="center", kind="light_diagram", modes=("advanced", "light"),
             light_body_key="quick_tour_light_mode_body_light"),
    TourStep("ready", lambda mw: [[mw.help_toolbar_btn]], place="bottom", modes=("advanced", "light"),
             light_body_key="quick_tour_ready_body_light"),
)


# The tour's own Advanced-mode layout: every block visible and expanded
# (Scan excepted - it gets its own step under the built-in Scan layout),
# in the default sides, right panel in the same order as the built-in
# Trichrome layout (Histogram, Framing, Light, Color, Curves).
def _tour_layout_state(mwmod) -> dict:
    return {
        "left_panel_visible": True,
        "right_panel_visible": True,
        "carousel_visible": True,
        "block_side": dict(mwmod._DEFAULT_BLOCK_SIDE),
        "block_visible": {k: k != "scan" for k in mwmod._ALL_BLOCK_KEYS},
        "block_collapsed": {k: False for k in mwmod._ALL_BLOCK_KEYS},
        "left_block_order": list(mwmod._DEFAULT_LEFT_BLOCK_ORDER),
        "right_block_order": ["histogram", "crop", "light", "color", "curves"],
    }


def _visible_rect(widget: QWidget, root: QWidget) -> QRect:
    """widget's rect in root's coordinates, clipped to every scroll-area
    viewport above it - so a block half scrolled out of a side panel only
    gets a hole around its visible part."""
    rect = QRect(widget.mapTo(root, QPoint(0, 0)), widget.size())
    parent = widget.parentWidget()
    while parent is not None and parent is not root:
        if isinstance(parent, QAbstractScrollArea):
            viewport = parent.viewport()
            rect = rect.intersected(QRect(viewport.mapTo(root, QPoint(0, 0)), viewport.size()))
        parent = parent.parentWidget()
    return rect


def _highlight_rect(widget: QWidget, root: QWidget) -> QRect:
    """The rect to actually highlight for one target widget - usually its full
    _visible_rect, but for an icon-only button (SvgToolButton and its
    checkable/toggle subclasses, which all store their own drawn icon size as
    _icon_size) just the icon's own centered square - the button's own
    hit-target box can be taller/wider than the glyph it draws (e.g. the top
    toolbar's 40px-tall buttons around a 24px icon, both centered on purpose -
    see MainWindow._TOP_TOOLBAR_ HEIGHT), and a hole around the full box reads
    as loosely floating around the icon rather than hugging it."""
    rect = _visible_rect(widget, root)
    icon_size = getattr(widget, "_icon_size", None)
    if not icon_size:
        return rect
    center = rect.center()
    half = icon_size // 2
    return QRect(center.x() - half, center.y() - half, icon_size, icon_size)


def _blend(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t))


# ----------------------------------------------------------------------
# Controller
# ----------------------------------------------------------------------
class QuickTour(QObject):
    finished = Signal()

    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        mode = "light" if mw.light_mode_active else "advanced"
        self.steps = [s for s in STEPS if mode in s.modes
                      and (s.key != "scan" or mw.scan_tool_enabled)]
        self.index = 0
        self.overlay: TourOverlay | None = None
        self._current_layout: str | None = None
        self._saved: dict = {}
        self._disabled_actions: list[QAction] = []
        self._batch_pixmap = None
        self._batch_title = ""
        self._batch_probe = None
        self._scroll_anims: list[QPropertyAnimation] = []
        self._scroll_pending = False  # go() has queued _scroll_to_step
        self._setting_up = False  # start() -> _finish_setup()
        self._running = False

    # -- lifecycle -------------------------------------------------------
    def start(self) -> None:
        mw = self.mw
        self._running = True
        self._save_state()
        self._quiet_app()
        self.overlay = TourOverlay(mw, self)
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.setFocus()
        # The first step shows and animates at once; the slow part (loading
        # the sample photo, about 0.6s, and the tour layout) runs once the
        # overlay's opening animation has settled (TourOverlay._tick), with
        # a fallback timer. Done first, it left the window frozen and blank
        # for about a second; done mid-animation, it froze the animation.
        self._setting_up = True
        self.go(0)
        QTimer.singleShot(_SETUP_FALLBACK_MS, self._finish_setup)

    def _finish_setup(self) -> None:
        if not self._running or not self._setting_up:
            return
        self._setting_up = False
        self._install_sample_if_empty()
        self._apply_step_layout(self.current_step().layout)
        self.overlay.kick()
        if any(s.kind == "batch" for s in self.steps):
            QTimer.singleShot(0, self._prepare_batch_pixmap)

    def finish(self) -> None:
        if not self._running:
            return
        self._running = False
        for anim in self._scroll_anims:
            anim.stop()
        if self._batch_probe is not None:
            self._batch_probe.close()
            self._batch_probe.deleteLater()
            self._batch_probe = None
        if self.overlay is not None:
            self.overlay.shutdown()
            self.overlay.hide()
            self.overlay.deleteLater()
            self.overlay = None
        self._remove_sample()
        self._restore_state()
        self.finished.emit()

    # -- sample photo ------------------------------------------------------
    def _install_sample_if_empty(self) -> None:
        """When the session has no real photo yet (e.g. the first launch),
        swaps in the sample trichrome (resources/sample/, generated by
        scripts/generate_tour_sample.py) for the tour's duration, so the
        preview, thumbnails, histogram and curves show something real. The
        original batch_items list is kept as-is and reinstalled by
        _remove_sample() - same _apply_restored_items() path session
        restore uses, which touches neither the undo stack nor the
        unsaved-changes counter. A session holding real photos is left
        alone: the tour then simply shows the user's own photo."""
        mw = self.mw
        self._saved_session = None
        if not all(mw._is_batch_item_empty(it) for it in mw.batch_items):
            return
        paths = {c: resource_path("resources", "sample", f"Trichrome_Sample_{c}.jpg") for c in "RGB"}
        try:
            item = mw._build_trichrome_batch_item_from_paths(paths, invert=False)
        except Exception:
            return  # no sample available - the tour still works on an empty session
        item.base = "Sample Trichrome"
        # Light mode is single-photo (no filmstrip): only the sample itself.
        # 2+ items would make _update_carousel_visibility show a thumbnail
        # bar Light mode never has.
        items = [item] if mw.light_mode_active else [item] + self._sample_variations(item)
        self._saved_session = (mw.batch_items, mw.sort_mode, mw.sort_reversed, mw.batch_current_index)
        mw._apply_restored_items(items, mw.sort_mode, mw.sort_reversed, 0)
        mw.recompute_preview()
        mw.canvas.zoom_fit()

    @staticmethod
    def _sample_variations(src) -> list:
        """4 extra filmstrip entries so the thumbnail bar looks like a real
        session - the same loaded sample (layers copied shallowly - the image
        arrays themselves are shared, nothing is decoded again) with
        different edits: each channel on its own (Red/Green/Blue - the
        other 2 layers darkened to black through their own tone settings,
        at their sliders' limits), then black and white (Monochrome)."""
        import copy

        from .model import BatchItem, GlobalCorrection

        def variant(suffix: str, corr: GlobalCorrection, keep: int | None = None):
            layers = [copy.copy(l) for l in src.layers]
            if keep is not None:
                for i, layer in enumerate(layers):
                    if i != keep:
                        layer.exposure, layer.brightness = -5.0, -0.5
            return BatchItem(
                base=f"Sample {suffix}", paths=dict(src.paths), layers=layers, global_corr=corr,
                mode=src.mode, capture_date=src.capture_date, selected=False)

        monochrome = GlobalCorrection(contrast=1.25)
        monochrome.black_white_active = True
        return [
            variant("Red", GlobalCorrection(), keep=0),
            variant("Green", GlobalCorrection(), keep=1),
            variant("Blue", GlobalCorrection(), keep=2),
            variant("Monochrome", monochrome),
        ]

    def _remove_sample(self) -> None:
        saved = getattr(self, "_saved_session", None)
        if saved is None:
            return
        self._saved_session = None
        items, sort_mode, sort_reversed, current_index = saved
        self.mw._apply_restored_items(items, sort_mode, sort_reversed, current_index)
        self.mw.recompute_preview()

    def _force_thumbnails_visible(self) -> None:
        """The thumbnail bar normally only shows with 2+ photos; the tour
        shows it regardless (Advanced mode only - Light mode has no
        filmstrip at all), so its step has something to point at.
        _restore_state() hands visibility back to
        _update_carousel_visibility()."""
        if not self.mw.light_mode_active:
            self.mw.carousel.setVisible(True)

    # -- navigation --------------------------------------------------------
    def go(self, index: int) -> None:
        if not self._running:
            return
        self.index = max(0, min(len(self.steps) - 1, index))
        step = self.steps[self.index]
        if not self._setting_up:
            self._apply_step_layout(step.layout)
        self.overlay.set_card(
            (self._batch_pixmap, self._batch_title) if step.kind == "batch" and self._batch_pixmap else None)
        body_key = step.light_body_key if (self.mw.light_mode_active and step.light_body_key) else \
            f"quick_tour_{step.key}_body"
        if step.scan_off_body_key and not self.mw.scan_tool_enabled:
            body_key = step.scan_off_body_key
        self.overlay.callout.set_step(
            self.index, len(self.steps), i18n.tr(f"quick_tour_{step.key}_title"), i18n.tr(body_key),
            [i18n.tr(f"quick_tour_{s.key}_title") for s in self.steps],
            wip=step.wip, diagram=step.kind == "light_diagram")
        # A newer animation on the same scroll bar stops the older one
        # without its finished signal, so drop them here, or a skipped
        # step's animation would be counted as scrolling forever.
        for anim in self._scroll_anims:
            anim.stop()
        self._scroll_anims = []
        self._scroll_pending = True
        self.overlay.kick()
        # Let the (possibly just changed) layout settle before measuring
        # where the target sits inside its scroll area.
        QTimer.singleShot(40, lambda i=self.index: self._scroll_to_step(i))

    def next(self) -> None:
        if self.index >= len(self.steps) - 1:
            self.finish()
        else:
            self.go(self.index + 1)

    def back(self) -> None:
        if self.index > 0:
            self.go(self.index - 1)

    # -- targets -------------------------------------------------------------
    @property
    def scrolling(self) -> bool:
        """True while a step's block is still being scrolled into view (or
        about to be): the overlay holds back a hole that has no previous one
        to slide from until then, so it appears where its block ends up."""
        return self._scroll_pending or any(
            a.state() == QAbstractAnimation.Running for a in self._scroll_anims)

    def current_step(self) -> TourStep:
        return self.steps[self.index]

    def target_rects(self) -> list[QRectF]:
        step = self.current_step()
        rects = []
        if step.kind == "batch":
            card = self.overlay.card_rect() if self.overlay is not None else None
            if card:
                rects.append(QRectF(card).adjusted(-_HOLE_PAD, -_HOLE_PAD, _HOLE_PAD, _HOLE_PAD))
        if step.targets is None:
            return [r.intersected(QRectF(self.mw.rect()).adjusted(
                _HOLE_INSET, _HOLE_INSET, -_HOLE_INSET, -_HOLE_INSET)) for r in rects]
        for group in step.targets(self.mw):
            parts = [_highlight_rect(w, self.mw) for w in group if w is not None and w.isVisible()]
            parts = [r for r in parts if r.width() > 0 and r.height() > 0]
            if not parts:
                continue
            union = parts[0]
            for r in parts[1:]:
                union = union.united(r)
            rects.append(QRectF(union).adjusted(-_HOLE_PAD, -_HOLE_PAD, _HOLE_PAD, _HOLE_PAD))
        # Keep the whole frame (border + glow) inside the window: on macOS
        # the menu bar is outside the window, so the toolbar sits flush
        # against the window's top edge and a padded hole would be clipped.
        bounds = QRectF(self.mw.rect()).adjusted(_HOLE_INSET, _HOLE_INSET, -_HOLE_INSET, -_HOLE_INSET)
        return [r.intersected(bounds) for r in rects]

    def _scroll_to_step(self, index: int) -> None:
        if not self._running or index != self.index:
            return
        self._scroll_pending = False
        step = self.current_step()
        if step.targets is None:
            return
        groups = step.targets(self.mw)
        widget = groups[0][0] if groups and groups[0] else None
        if widget is None:
            return
        for scroll in (self.mw.left_scroll, self.mw.right_scroll):
            content = scroll.widget()
            if content is None or not content.isAncestorOf(widget):
                continue
            bar = scroll.verticalScrollBar()
            y = widget.mapTo(content, QPoint(0, 0)).y() - 8
            target = max(bar.minimum(), min(bar.maximum(), y))
            if target == bar.value():
                return
            anim = QPropertyAnimation(bar, b"value", self)
            anim.setDuration(_SCROLL_MS)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.setStartValue(bar.value())
            anim.setEndValue(target)
            anim.finished.connect(lambda a=anim: self._scroll_anims.remove(a) if a in self._scroll_anims else None)
            self._scroll_anims.append(anim)
            anim.start()
            return

    # -- app state -------------------------------------------------------------
    def _save_state(self) -> None:
        mw = self.mw
        self._saved = {
            "layout": None if mw.light_mode_active else mw._capture_layout_state(),
            "collapsed": dict(mw.block_collapsed),
            "layout_button": mw.default_layout_group.checkedButton(),
            "grid": mw.grid_view_toggle_btn.isChecked(),
            "scroll": (mw.left_scroll.verticalScrollBar().value(),
                       mw.right_scroll.verticalScrollBar().value()),
        }

    def _quiet_app(self) -> None:
        """Turns off every transient mode that would otherwise react to the
        tour's own layout changes or hold keyboard input, and disables the
        menus - a hidden/disabled menu is the only reliable way to stop a
        QAction shortcut (and macOS menu key equivalents) from firing."""
        mw = self.mw
        if mw._is_focus_mode:
            mw.toggle_focus_mode()
        if mw.grid_view_toggle_btn.isChecked():
            mw.grid_view_toggle_btn.setChecked(False)
        mw._set_crop_active(False)
        mw._set_perspective_active(False)
        mw._deactivate_canvas_drag_modes()
        mw.histogram.pick_button.setChecked(False)
        if mw.color_panel.pick_white_balance_btn.isChecked():
            mw.color_panel.pick_white_balance_btn.setChecked(False)
        self._disabled_actions = []

        def walk(actions):
            for action in actions:
                if action.menu() is not None:
                    walk(action.menu().actions())
                    continue
                if action.isSeparator() or action.menuRole() == QAction.QuitRole:
                    continue
                if action.isEnabled():
                    action.setEnabled(False)
                    self._disabled_actions.append(action)

        walk(mw.menuBar().actions())

    def _restore_state(self) -> None:
        mw = self.mw
        for action in self._disabled_actions:
            action.setEnabled(True)
        self._disabled_actions = []
        if mw.light_mode_active:
            self._set_light_blocks_collapsed(self._saved.get("collapsed", {}))
        elif self._saved.get("layout") is not None:
            mw._apply_layout_state(self._saved["layout"])
            button = self._saved.get("layout_button")
            if button is not None:
                button.setChecked(True)
        if self._saved.get("grid"):
            mw.grid_view_toggle_btn.setChecked(True)
        mw._update_carousel_visibility()
        left, right = self._saved.get("scroll", (0, 0))
        # After the restored layout has settled, so the scroll ranges match.
        QTimer.singleShot(0, lambda: (mw.left_scroll.verticalScrollBar().setValue(left),
                                      mw.right_scroll.verticalScrollBar().setValue(right)))

    def _set_light_blocks_collapsed(self, collapsed: dict) -> None:
        from . import main_window as mwmod
        mw = self.mw
        for key in mwmod._LIGHT_MODE_BLOCK_KEYS:
            widget = mw.block_widgets.get(key)
            if widget is not None:
                set_block_collapsed(widget.body, mw.block_collapse_buttons[key], collapsed.get(key, False))

    def _apply_step_layout(self, name: str) -> None:
        if name == self._current_layout:
            return
        self._current_layout = name
        mw = self.mw
        if mw.light_mode_active:
            # Light mode's layout is a fixed override - only expand its 4
            # blocks visually, without writing block_collapsed itself.
            self._set_light_blocks_collapsed({})
            return
        from . import main_window as mwmod
        if name == "scan":
            mw._apply_layout_state(mwmod._BUILT_IN_LAYOUT_STATES["Scan"])
            mw.scan_toolbar_btn.setChecked(True)
        else:
            mw._apply_layout_state(_tour_layout_state(mwmod))
            button = self._saved.get("layout_button")
            if button is not None:
                button.setChecked(True)
        # Applying a layout re-runs _update_carousel_visibility (via the
        # thumbnails toggle), which hides a 1-photo filmstrip again.
        self._force_thumbnails_visible()

    # -- Batch Import window snapshot ------------------------------------------
    def _prepare_batch_pixmap(self) -> None:
        """Builds a real BatchWindow off-screen and grabs it, so the Batch
        Import step shows the genuine window (current language, current
        theme, last-used settings) as a picture inside the overlay - a real,
        clickable window would sit above the overlay, take keyboard focus,
        and could start an actual import mid-tour."""
        if not self._running:
            return
        from .batch_window import BatchWindow
        probe = BatchWindow(self.mw)
        probe.setAttribute(Qt.WA_DontShowOnScreen, True)
        probe.show()
        self._batch_probe = probe
        # BatchWindow sizes itself over several event-loop passes (see
        # _fit_window_to_active_mode's own bounded retry chain).
        QTimer.singleShot(400, self._grab_batch_pixmap)

    def _grab_batch_pixmap(self) -> None:
        probe = self._batch_probe
        self._batch_probe = None
        if probe is None:
            return
        self._batch_pixmap = probe.grab()
        self._batch_title = probe.windowTitle()
        probe.close()
        probe.deleteLater()
        if self._running and self.current_step().kind == "batch":
            self.overlay.set_card((self._batch_pixmap, self._batch_title))
            self.overlay.kick()


# ----------------------------------------------------------------------
# Overlay
# ----------------------------------------------------------------------
class TourOverlay(QWidget):
    _CARD_TITLE_H = 28

    def __init__(self, mw, tour: QuickTour):
        super().__init__(mw)
        self.mw = mw
        self.tour = tour
        self.setGeometry(mw.rect())
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self._holes: list[QRectF] = []
        # Holes of the previous step being dropped: [rect, alpha]. They
        # shrink toward their own center and fade out in place.
        self._leaving: list[list] = []
        self._holes_step: int | None = None  # the step self._holes were seeded for
        self._fresh: list[bool] = []  # per hole: grown from nothing, not carried
        self._fade = 0.0
        self._card = None  # (pixmap, title)
        self._card_alpha = 0.0
        self._callout_pos: QPointF | None = None
        self.callout = TourCallout(self, tour)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(_FRAME_MS)
        mw.installEventFilter(self)
        for scroll in (mw.left_scroll, mw.right_scroll):
            scroll.verticalScrollBar().valueChanged.connect(self.kick)

    def shutdown(self) -> None:
        self._timer.stop()
        self.mw.removeEventFilter(self)
        for scroll in (self.mw.left_scroll, self.mw.right_scroll):
            try:
                scroll.verticalScrollBar().valueChanged.disconnect(self.kick)
            except (RuntimeError, TypeError):
                pass

    def kick(self, *_args) -> None:
        if self._timer.interval() != _FRAME_MS:
            self._timer.setInterval(_FRAME_MS)

    # -- card (Batch Import snapshot) --------------------------------------
    def set_card(self, card) -> None:
        if card is None or self._card is None or card[0] is not self._card[0]:
            self._card_alpha = 0.0
        self._card = card

    def card_rect(self) -> QRect | None:
        if self._card is None:
            return None
        pixmap = self._card[0]
        dpr = pixmap.devicePixelRatio() or 1.0
        pw, ph = pixmap.width() / dpr, pixmap.height() / dpr + self._CARD_TITLE_H
        scale = min(1.0, (self.width() * 0.62) / pw, (self.height() - 80) / ph)
        w, h = round(pw * scale), round(ph * scale)
        x = max(_EDGE_MARGIN + _HOLE_PAD,
                (self.width() - (w + _CALLOUT_GAP + TourCallout.WIDTH)) // 2)
        y = max(_EDGE_MARGIN + _HOLE_PAD, (self.height() - h) // 2)
        return QRect(x, y, w, h)

    # -- animation ---------------------------------------------------------
    def _tick(self) -> None:
        targets = self.tour.target_rects()
        moving = False

        if self._holes_step != self.tour.index or len(self._holes) != len(targets):
            # On every step change (not only when the hole count changes):
            # each new target morphs from the closest previous hole within
            # _CARRY_GAP of it, or grows out of its own center when none is
            # that close. Previous holes no target picked fade out in place.
            # Matching per target matters: a bounding box of all the new
            # targets (Arrange: toolbar + Light block) also covered a far
            # hole (the workspace buttons) and swept it across the window.
            self._holes_step = self.tour.index
            seeded, used, self._fresh = [], set(), []
            for t in targets:
                near = t.adjusted(-_CARRY_GAP, -_CARRY_GAP, _CARRY_GAP, _CARRY_GAP)
                close = [i for i, r in enumerate(self._holes) if r.intersects(near)]
                if close:
                    best = min(close, key=lambda i: _rect_distance(self._holes[i], t))
                    used.add(best)
                    seeded.append(QRectF(self._holes[best]))
                    self._fresh.append(False)
                else:
                    seeded.append(QRectF(t.center(), t.center()))
                    self._fresh.append(True)
            self._leaving += [[QRectF(r), 1.0] for i, r in enumerate(self._holes)
                              if i not in used]
            self._holes = seeded
        scrolling = self.tour.scrolling
        for i, target in enumerate(targets):
            if self._fresh[i] and scrolling:
                # A hole with no previous one to slide from grows only once
                # its block has scrolled into place: grown at the block's
                # pre-scroll position, it slid along the whole panel with it
                # (Arrange: the Light block's header). Until then it stays an
                # invisible point riding the target's center.
                self._holes[i] = QRectF(target.center(), target.center())
                moving = True
                continue
            current = self._holes[i]
            if _rect_distance(current, target) > 0.6:
                moving = True
                self._holes[i] = _lerp_rect(current, target, _EASE)
            else:
                self._holes[i] = QRectF(target)

        for entry in self._leaving:
            rect, alpha = entry
            entry[0] = _lerp_rect(rect, QRectF(rect.center(), rect.center()), _EASE)
            entry[1], _ = _approach(alpha, 0.0, _LEAVE_STEP)
        self._leaving = [e for e in self._leaving if e[1] > 0.0]
        moving = moving or bool(self._leaving)

        self._fade, f_moving = _approach(self._fade, 1.0)
        target_card = 1.0 if self._card is not None else 0.0
        self._card_alpha, c_moving = _approach(self._card_alpha, target_card)
        moving = moving or f_moving or c_moving

        pos = self._callout_target(targets)
        if self._callout_pos is None:
            self._callout_pos = pos
        else:
            delta = pos - self._callout_pos
            if abs(delta.x()) + abs(delta.y()) > 0.6:
                moving = True
                self._callout_pos += delta * _EASE
            else:
                self._callout_pos = pos
        self.callout.move(round(self._callout_pos.x()), round(self._callout_pos.y()))

        self.update()
        self._timer.setInterval(_FRAME_MS if moving else _IDLE_POLL_MS)
        if not moving and self.tour._setting_up:
            QTimer.singleShot(0, self.tour._finish_setup)

    def _all_holes(self) -> list[QRectF]:
        return self._holes + [e[0] for e in self._leaving]

    def _callout_target(self, targets: list[QRectF]) -> QPointF:
        cw, ch = self.callout.width(), self.callout.height()
        W, H = self.width(), self.height()
        if not targets:
            return QPointF((W - cw) / 2, (H - ch) / 2)
        u = targets[0]
        for r in targets[1:]:
            u = u.united(r)
        g = _CALLOUT_GAP
        candidates = {
            "right": QPointF(u.right() + g, u.top()),
            "left": QPointF(u.left() - g - cw, u.top()),
            "bottom": QPointF(u.center().x() - cw / 2, u.bottom() + g),
            "top": QPointF(u.center().x() - cw / 2, u.top() - g - ch),
            "inside": QPointF(u.center().x() - cw / 2, u.bottom() - ch - 24),
            "center": QPointF((W - cw) / 2, (H - ch) / 2),
        }
        preferred = self.tour.current_step().place
        order = [preferred] + [k for k in ("right", "left", "bottom", "top") if k != preferred]

        def fits(p: QPointF, key: str) -> bool:
            if key in ("inside", "center"):
                return True
            # Only the axis facing away from the target must fit as-is;
            # the other one is clamped below anyway.
            if key in ("right", "left"):
                return _EDGE_MARGIN <= p.x() <= W - cw - _EDGE_MARGIN
            return _EDGE_MARGIN <= p.y() <= H - ch - _EDGE_MARGIN

        chosen = next((candidates[k] for k in order if fits(candidates[k], k)), candidates[preferred])
        x = max(_EDGE_MARGIN, min(W - cw - _EDGE_MARGIN, chosen.x()))
        y = max(_EDGE_MARGIN, min(H - ch - _EDGE_MARGIN, chosen.y()))
        return QPointF(x, y)

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        if self._card is not None and self._card_alpha > 0.01:
            self._paint_card(p)

        full = QPainterPath()
        full.addRect(QRectF(self.rect()))
        holes = QPainterPath()
        for r in self._all_holes():
            if r.width() > 1 and r.height() > 1:
                holes.addRoundedRect(r, _HOLE_RADIUS, _HOLE_RADIUS)
        dim = QColor(_DIM)
        dim.setAlpha(round(_DIM.alpha() * self._fade))
        p.fillPath(full.subtracted(holes), dim)

        for r, fade in [(r, self._fade) for r in self._holes] + [
                (e[0], self._fade * e[1]) for e in self._leaving]:
            if r.width() <= 1 or r.height() <= 1:
                continue
            for width, alpha in ((10, 28), (6, 55)):
                glow = QColor(ACCENT)
                glow.setAlpha(round(alpha * fade))
                p.setPen(QPen(glow, width))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r, _HOLE_RADIUS, _HOLE_RADIUS)
            border = QColor(ACCENT)
            border.setAlpha(round(255 * fade))
            p.setPen(QPen(border, 2))
            p.drawRoundedRect(r, _HOLE_RADIUS, _HOLE_RADIUS)

        # The callout's soft shadow (painted here rather than as a
        # QGraphicsDropShadowEffect on the callout - see TourCallout).
        p.setPen(Qt.NoPen)
        callout = QRectF(self.callout.geometry())
        for spread, alpha in ((14, 10), (9, 18), (5, 28), (2, 40)):
            p.setBrush(QColor(0, 0, 0, round(alpha * self._fade)))
            p.drawRoundedRect(callout.adjusted(-spread, -spread + 6, spread, spread + 6), 10 + spread, 10 + spread)

    def _paint_card(self, p: QPainter) -> None:
        rect = self.card_rect()
        if rect is None:
            return
        pixmap, title = self._card
        p.save()
        p.setOpacity(self._card_alpha)
        # Soft shadow
        for i, alpha in enumerate((40, 26, 14)):
            spread = 4 + i * 5
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawRoundedRect(QRectF(rect).adjusted(-spread, -spread + 6, spread, spread + 6), 12, 12)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(rect), 10, 10)
        p.setClipPath(clip)
        pal = self.palette()
        title_bg = _blend(pal.color(QPalette.Window), pal.color(QPalette.WindowText), 0.06)
        title_h = round(self._CARD_TITLE_H * rect.height() / (
            pixmap.height() / (pixmap.devicePixelRatio() or 1.0) + self._CARD_TITLE_H))
        title_rect = QRect(rect.left(), rect.top(), rect.width(), title_h)
        p.fillRect(title_rect, title_bg)
        for i, color in enumerate(("#e0625a", "#e0b53a", "#5bb04f")):
            p.setBrush(QColor(color))
            p.drawEllipse(QPointF(rect.left() + 14 + i * 18, title_rect.center().y() + 0.5), 5.5, 5.5)
        p.setPen(pal.color(QPalette.WindowText))
        font = QFont(self.font())
        font.setBold(True)
        p.setFont(font)
        p.drawText(title_rect, Qt.AlignCenter, title)
        p.drawPixmap(QRect(rect.left(), title_rect.bottom() + 1, rect.width(), rect.height() - title_h), pixmap)
        p.restore()

    # -- input: swallow everything ---------------------------------------
    def eventFilter(self, obj, event) -> bool:
        if obj is self.mw and event.type() == QEvent.Resize:
            self.setGeometry(self.mw.rect())
            self.kick()
        return False

    def event(self, event) -> bool:
        if event.type() == QEvent.ShortcutOverride:
            # Claims every key press for keyPressEvent below, so no
            # QShortcut/QAction shortcut (Cmd+Z, Cmd+W, ...) can fire
            # underneath the tour.
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key_Escape:
            self.tour.finish()
        elif key in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter):
            self.tour.next()
        elif key == Qt.Key_Left:
            self.tour.back()
        event.accept()

    def mousePressEvent(self, event) -> None:
        self.setFocus()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        event.accept()

    def wheelEvent(self, event) -> None:
        event.accept()


def _approach(value: float, target: float, step: float = 0.12) -> tuple[float, bool]:
    if abs(target - value) <= step:
        return target, value != target
    return value + step * (1 if target > value else -1), True


def _lerp_rect(a: QRectF, b: QRectF, t: float) -> QRectF:
    return QRectF(
        a.left() + (b.left() - a.left()) * t,
        a.top() + (b.top() - a.top()) * t,
        a.width() + (b.width() - a.width()) * t,
        a.height() + (b.height() - a.height()) * t)


def _rect_distance(a: QRectF, b: QRectF) -> float:
    return (abs(a.left() - b.left()) + abs(a.top() - b.top())
            + abs(a.width() - b.width()) + abs(a.height() - b.height()))


# ----------------------------------------------------------------------
# Callout
# ----------------------------------------------------------------------
_KBD_RE = re.compile(r"<kbd>(.*?)</kbd>")


class TourCallout(QFrame):
    WIDTH = 320
    WIDE_WIDTH = 520  # steps showing the Light mode screenshot

    def __init__(self, overlay: TourOverlay, tour: QuickTour):
        super().__init__(overlay)
        self.tour = tour
        self.setObjectName("quickTourCallout")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(self.WIDTH)
        pal = self.palette()
        window, text = pal.color(QPalette.Window), pal.color(QPalette.WindowText)
        background = _blend(window, text, 0.04)
        border = _blend(window, text, 0.22)
        self._muted = _blend(window, text, 0.6).name()
        self._kbd_bg = _blend(window, text, 0.16).name()
        self.setStyleSheet(
            f"QFrame#quickTourCallout {{ background: {background.name()};"
            f" border: 1px solid {border.name()}; border-radius: 10px; }}")
        # One graphics effect only, and only while fading. A drop-shadow
        # effect on this frame plus an opacity effect on its content (the
        # first version) rendered the content offset from the frame on a
        # real Retina display - nested QGraphicsEffects are unreliable on
        # HiDPI. The shadow is painted by TourOverlay instead, and the
        # opacity effect is switched off once each fade-in completes.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.content = QWidget()
        outer.addWidget(self.content)
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self._opacity.setEnabled(False)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(_FADE_MS)
        self._fade.setStartValue(0.35)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.finished.connect(lambda: self._opacity.setEnabled(False))

        lay = QVBoxLayout(self.content)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.step_label = QLabel()
        self.step_label.setStyleSheet(
            f"color: {ACCENT.name()}; font-weight: 700; font-size: 10px; letter-spacing: 1px;")
        top.addWidget(self.step_label)
        self.wip_badge = QLabel(i18n.tr("quick_tour_in_progress"))
        self.wip_badge.setStyleSheet(
            f"background: {_WIP_COLOR}; color: #1e1d22; font-weight: 700; font-size: 10px;"
            " border-radius: 4px; padding: 1px 6px;")
        top.addWidget(self.wip_badge)
        top.addStretch(1)
        lay.addLayout(top)

        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size: 15px; font-weight: 700;")
        lay.addWidget(self.title_label)

        self.body_label = QLabel()
        self.body_label.setWordWrap(True)
        self.body_label.setTextFormat(Qt.RichText)
        self.body_label.setFixedWidth(self.WIDTH - 32)
        lay.addWidget(self.body_label)

        # A real screenshot of the Light mode window with the Quick Tour
        # sample loaded - resources/quick_tour_light_mode.png, generated by
        # scripts/generate_light_mode_screenshot.py with the native macOS
        # platform in dark appearance (the offscreen platform renders a
        # white, generic UI that doesn't match the app). Pre-scaled to the
        # box + the live DPR (same pattern as WelcomeDialog's logo, rather
        # than setScaledContents, which wouldn't apply a DPR correctly); the
        # box takes the image's own aspect ratio so it's never stretched.
        # The step showing it widens the whole callout (WIDE_WIDTH, via
        # _set_width) so the screenshot reads at a useful size.
        self._shot = QPixmap(resource_path("resources", "quick_tour_light_mode.png"))
        self.diagram = QLabel()
        self.diagram.setStyleSheet(f"border: 1px solid {border.name()}; border-radius: 4px;")
        lay.addWidget(self.diagram)
        self.diagram_caption = QLabel(i18n.tr("quick_tour_light_diagram_caption"))
        self.diagram_caption.setStyleSheet(f"color: {self._muted}; font-size: 11px;")
        lay.addWidget(self.diagram_caption)

        lay.addSpacing(4)
        self.timeline = TourTimeline()
        self.timeline.step_clicked.connect(tour.go)
        lay.addWidget(self.timeline)
        lay.addSpacing(2)

        foot = QHBoxLayout()
        foot.setSpacing(6)
        self.skip_button = QPushButton(i18n.tr("quick_tour_skip"))
        self.skip_button.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; color: {self._muted}; padding: 4px 0; }}"
            f" QPushButton:hover {{ color: {text.name()}; }}")
        self.skip_button.clicked.connect(tour.finish)
        foot.addWidget(self.skip_button)
        foot.addStretch(1)
        self.back_button = QPushButton(i18n.tr("quick_tour_back"))
        style_secondary_button(self.back_button)
        self.back_button.clicked.connect(tour.back)
        foot.addWidget(self.back_button)
        self.next_button = QPushButton()
        style_primary_button(self.next_button)
        self.next_button.clicked.connect(tour.next)
        foot.addWidget(self.next_button)
        lay.addLayout(foot)

        # The overlay keeps keyboard focus (arrows/Esc/Enter drive the tour).
        for button in (self.skip_button, self.back_button, self.next_button):
            button.setFocusPolicy(Qt.NoFocus)
            button.setCursor(Qt.PointingHandCursor)
        self._width = 0
        self._set_width(self.WIDTH)

    def _set_width(self, width: int) -> None:
        if width == self._width:
            return
        self._width = width
        self.setFixedWidth(width)
        self.body_label.setFixedWidth(width - 32)
        diagram_w = width - 32
        shot = self._shot
        diagram_h = round(diagram_w * shot.height() / shot.width()) if not shot.isNull() else 150
        self.diagram.setFixedSize(diagram_w, diagram_h)
        if not shot.isNull():
            dpr = self.devicePixelRatioF() or 1.0
            scaled = shot.scaled(
                int(diagram_w * dpr), int(diagram_h * dpr), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            scaled.setDevicePixelRatio(dpr)
            self.diagram.setPixmap(scaled)

    def _body_html(self, text: str) -> str:
        text = _KBD_RE.sub(
            lambda m: f'<span style="background-color:{self._kbd_bg}; font-weight:600;">'
                      f"&nbsp;{m.group(1)}&nbsp;</span>", text)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return "".join(f'<p style="margin:0 0 7px 0;">{p}</p>' for p in paragraphs)

    def set_step(self, index: int, total: int, title: str, body: str, titles: list[str],
                 wip: bool = False, diagram: bool = False) -> None:
        self.step_label.setText(i18n.tr("quick_tour_step", n=index + 1, total=total).upper())
        self.wip_badge.setVisible(wip)
        self.title_label.setText(title)
        self._set_width(self.WIDE_WIDTH if diagram else self.WIDTH)
        self.body_label.setText(self._body_html(body))
        self.diagram.setVisible(diagram)
        self.diagram_caption.setVisible(diagram)
        self.timeline.set_state(total, index, titles)
        self.back_button.setEnabled(index > 0)
        self.next_button.setText(i18n.tr("quick_tour_finish" if index == total - 1 else "quick_tour_next"))
        self.content.layout().activate()
        self.adjustSize()
        self._fade.stop()
        self._opacity.setEnabled(True)
        self._fade.start()


class TourTimeline(QWidget):
    """A row of dots, one per step: past steps tinted, the current one
    larger; click a dot to jump there (step title as tooltip)."""
    step_clicked = Signal(int)
    _PAD = 6

    def __init__(self):
        super().__init__()
        self.setFixedHeight(16)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._count = 1
        self._current = 0
        self._titles: list[str] = []
        self._hover = -1

    def set_state(self, count: int, current: int, titles: list[str]) -> None:
        self._count, self._current, self._titles = max(1, count), current, titles
        self.update()

    def _x(self, i: int) -> float:
        if self._count == 1:
            return self.width() / 2
        return self._PAD + i * (self.width() - 2 * self._PAD) / (self._count - 1)

    def _index_at(self, x: float) -> int:
        if self._count == 1:
            return 0
        spacing = (self.width() - 2 * self._PAD) / (self._count - 1)
        return max(0, min(self._count - 1, round((x - self._PAD) / spacing)))

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        idle = _blend(pal.color(QPalette.Window), pal.color(QPalette.WindowText), 0.28)
        done = QColor(ACCENT)
        done.setAlpha(150)
        cy = self.height() / 2
        for i in range(self._count - 1):
            p.setPen(QPen(done if i < self._current else idle, 2))
            p.drawLine(QPointF(self._x(i), cy), QPointF(self._x(i + 1), cy))
        p.setPen(Qt.NoPen)
        for i in range(self._count):
            if i == self._current:
                p.setBrush(pal.color(QPalette.Window))
                p.drawEllipse(QPointF(self._x(i), cy), 7, 7)
                p.setBrush(ACCENT)
                radius = 5.5
            else:
                p.setBrush(done if i < self._current else idle)
                radius = 4.5 if i == self._hover else 3.5
            p.drawEllipse(QPointF(self._x(i), cy), radius, radius)

    def mouseMoveEvent(self, event) -> None:
        i = self._index_at(event.position().x())
        if i != self._hover:
            self._hover = i
            self.update()
            if 0 <= i < len(self._titles):
                QToolTip.showText(event.globalPosition().toPoint(), f"{i + 1}. {self._titles[i]}", self)

    def leaveEvent(self, event) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, event) -> None:
        self.step_clicked.emit(self._index_at(event.position().x()))
        event.accept()


# ----------------------------------------------------------------------
# Entry points used by MainWindow / main.py
# ----------------------------------------------------------------------
def open_quick_tour(mw) -> None:
    """Help ▸ Quick Tour / the toolbar "?" menu: the welcome window, then
    the tour itself if the user picks Start the Tour."""
    from . import main_window as mwmod
    from .widgets.welcome_dialog import WelcomeDialog
    if getattr(mw, "_quick_tour", None) is not None:
        return
    dialog = WelcomeDialog(mw, mwmod.ORG_NAME, mwmod.APP_NAME)
    dialog.exec()
    if dialog.result == "start":
        start_quick_tour(mw)


def start_quick_tour(mw) -> None:
    tour = QuickTour(mw)
    mw._quick_tour = tour
    tour.finished.connect(lambda: setattr(mw, "_quick_tour", None))
    tour.start()


def open_quick_tour_at_startup(mw) -> None:
    """Launch-time entry point - only while "Open at startup" is checked
    (main.py skips calling this when the app was launched by opening a
    .trirgb, on the assumption that user already knows the app)."""
    from . import main_window as mwmod
    from .widgets.welcome_dialog import show_at_startup_enabled
    if not mw.isVisible() or QApplication.activeModalWidget() is not None:
        return
    if show_at_startup_enabled(mwmod.ORG_NAME, mwmod.APP_NAME):
        open_quick_tour(mw)


def finish_quick_tour(mw) -> None:
    """Ends a running tour (restoring the user's layout) - closeEvent calls
    this first so the layout saved on quit is the user's own, never the
    tour's temporary one."""
    tour = getattr(mw, "_quick_tour", None)
    if tour is not None:
        tour.finish()
