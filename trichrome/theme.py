"""Appearance (Dark / Light / Same as System) and the colors that depend on it.

The app's own chrome (custom-painted sliders, histogram, curves, channel tabs,
the QSS of a few styled widgets) was originally written against a dark
window. Everything theme-dependent now reads it from here, at paint time or
through a registered callback, so switching the appearance applies instantly.

- macOS keeps its native style; ``QStyleHints.setColorScheme`` forces Dark or
  Light on the native controls (and on the window frames).
- Windows uses the Fusion style with an explicit palette taken from the macOS
  tones, so both platforms look the same. The native Windows style draws its
  own controls (group-box frames, radio indicators hidden through QSS) and its
  dark palette left some text black on dark surfaces.

Light is a light gray (LIGHT_*), not white: lists and text fields included.
"""
from __future__ import annotations

import weakref

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from . import os_integration

APPEARANCE_KEY = "appearance"
APPEARANCES = ("dark", "light", "system")
DEFAULT_APPEARANCE = "dark"

# Fusion is used wherever the native style isn't macOS's.
USES_FUSION = not os_integration.IS_MAC

# The light theme's tones, shared by both platforms: a light gray throughout,
# nothing close to white (lists and fields are only a step lighter than the
# window).
LIGHT_WINDOW = "#d9d9d9"
LIGHT_BASE = "#e6e6e6"
LIGHT_PANE = "#e3e3e5"
LIGHT_PLOT = "#e8e8e8"
LIGHT_POPUP = "#e2e2e2"

_current = DEFAULT_APPEARANCE
_callbacks: list = []  # weakref.WeakMethod / weakref.ref to plain callables


# --- Reading the current theme ------------------------------------------------

def is_dark() -> bool:
    app = QApplication.instance()
    if app is None:
        return True
    return app.palette().color(QPalette.Window).lightness() < 128


def pick(dark, light):
    """``dark`` in the dark theme, ``light`` otherwise (any value type)."""
    return dark if is_dark() else light


def qcolor(dark, light) -> QColor:
    return QColor(pick(dark, light))


def overlay(alpha: int) -> str:
    """A QSS rgba() that lightens a dark surface or darkens a light one by the
    same amount: the "subtle tint" every hover/frame overlay uses."""
    return f"rgba(255, 255, 255, {alpha})" if is_dark() else f"rgba(0, 0, 0, {alpha})"


def overlay_color(alpha: int) -> QColor:
    return QColor(255, 255, 255, alpha) if is_dark() else QColor(0, 0, 0, alpha)


def text_color() -> QColor:
    """Strong foreground (hovered icons, values): near-white or near-black."""
    return qcolor("#f0f0f0", "#1e1e1e")


def value_text_color(enabled: bool = True) -> str:
    if enabled:
        return pick("#d8d8dc", "#2a2a2e")
    return pick("#6a6a6e", "#a0a0a4")


def muted_text_color() -> str:
    """Secondary text (file names, captions, help lines)."""
    return pick("#8a8a8a", "#6a6a6a")


def luminance_channel_color() -> QColor:
    """The Y (luminance) channel's neutral color in the histogram and curves."""
    return qcolor("#dcdcdc", "#4a4a4a")


def hairline_color() -> str:
    """Separator between the side panels, the preview and the toolbar."""
    return pick("#101010", "#b4b4b4")


def plot_colors() -> dict:
    """Histogram and curve editor plot area."""
    if is_dark():
        return {"bg": QColor(24, 24, 24), "curve_bg": QColor(38, 38, 42),
                "border": QColor(80, 80, 86), "grid": QColor(255, 255, 255, 24),
                "diagonal": QColor(255, 255, 255, 40)}
    return {"bg": QColor(LIGHT_PLOT), "curve_bg": QColor(LIGHT_PLOT),
            "border": QColor(170, 170, 176), "grid": QColor(0, 0, 0, 22),
            "diagonal": QColor(0, 0, 0, 45)}


def slider_colors(enabled: bool) -> dict:
    if is_dark():
        if enabled:
            return {"groove": QColor(74, 74, 80), "fill": QColor(122, 144, 194),
                    "tick": QColor(200, 200, 206, 190), "handle": QColor(232, 232, 232)}
        return {"groove": QColor(58, 58, 62), "fill": QColor(90, 92, 98),
                "tick": QColor(120, 120, 126, 140), "handle": QColor(140, 140, 144)}
    if enabled:
        return {"groove": QColor(186, 186, 192), "fill": QColor(108, 140, 200),
                "tick": QColor(90, 90, 96, 200), "handle": QColor(70, 70, 76)}
    return {"groove": QColor(206, 206, 210), "fill": QColor(170, 176, 190),
            "tick": QColor(150, 150, 156, 140), "handle": QColor(160, 160, 164)}


def channel_pane_colors() -> dict:
    """Trichrome Process's channel editor (the folder-tab frame)."""
    if is_dark():
        return {"pane": QColor("#232227"), "shelf": QColor(255, 255, 255, 16),
                "divider": QColor(255, 255, 255, 40)}
    return {"pane": QColor(LIGHT_PANE), "shelf": QColor(0, 0, 0, 14),
            "divider": QColor(0, 0, 0, 40)}


def light_gray_for_icon(value: int) -> int:
    """Maps a light gray fill of a multi-color icon (designed for a dark
    surface) to a dark gray for the light theme, keeping the order: the
    lightest layer becomes the darkest."""
    return min(255, 0x30 + (255 - value))


# --- Changes --------------------------------------------------------------------

def on_change(callback) -> None:
    """Calls ``callback()`` after every appearance change. A bound method is
    held weakly, so a destroyed widget simply drops out."""
    try:
        ref = weakref.WeakMethod(callback)
    except TypeError:
        ref = weakref.ref(callback)
    _callbacks.append(ref)


def _repolish_styled_widgets(app) -> None:
    """A widget under a stylesheet keeps the palette it had when the sheet
    was applied: Qt doesn't pass it a later application palette change (the
    native combo's text stayed white on the new light field, slider rings
    kept a dark fill). Re-setting each sheet re-polishes its subtree with the
    current palette. QWidget.setStyleSheet explicitly: CheckBox/RadioButton
    override it to append their indicator rules again."""
    for widget in app.allWidgets():
        sheet = widget.styleSheet()
        if sheet:
            QWidget.setStyleSheet(widget, sheet)


def _notify() -> None:
    app = QApplication.instance()
    if app is not None:
        _repolish_styled_widgets(app)
    alive = []
    for ref in _callbacks:
        fn = ref()
        if fn is None:
            continue
        alive.append(ref)
        try:
            fn()
        except RuntimeError:
            # The underlying C++ widget is gone (Shiboken raises on access).
            alive.pop()
    _callbacks[:] = alive
    app = QApplication.instance()
    if app is not None:
        for widget in app.allWidgets():
            # QWidget.update explicitly: item views overload update(index).
            QWidget.update(widget)


def current_appearance() -> str:
    return _current


def _scheme_for(appearance: str):
    return {"dark": Qt.ColorScheme.Dark, "light": Qt.ColorScheme.Light}.get(
        appearance, Qt.ColorScheme.Unknown)


def _system_is_dark(app) -> bool:
    return app.styleHints().colorScheme() == Qt.ColorScheme.Dark


_installed = False
_notify_timer = None


def install(app, appearance: str) -> None:
    """Called once at startup, before the main window's widgets exist. A
    second call (another MainWindow, in tests) only re-applies."""
    global _installed
    if _installed:
        apply(appearance, notify=False)
        return
    _installed = True
    if USES_FUSION:
        app.setStyle("Fusion")
    app.styleHints().colorSchemeChanged.connect(lambda _scheme: _on_system_scheme_changed())
    # On macOS, a scheme change with windows on screen settles a moment
    # later than setColorScheme() returns, with further palette changes; the
    # refresh runs once they're all in (coalesced on the next event-loop turn).
    global _notify_timer
    _notify_timer = QTimer()
    _notify_timer.setSingleShot(True)
    _notify_timer.setInterval(0)
    _notify_timer.timeout.connect(_notify)
    app.paletteChanged.connect(lambda _palette: _notify_timer.start())
    apply(appearance, notify=False)
    _notify_timer.stop()  # nothing to refresh yet at startup


def _on_system_scheme_changed() -> None:
    if _current != "system":
        return
    # Deferred: on macOS the palette update follows the scheme signal.
    QTimer.singleShot(0, lambda: apply("system"))


def apply(appearance: str, notify: bool = True) -> None:
    global _current
    if appearance not in APPEARANCES:
        appearance = DEFAULT_APPEARANCE
    _current = appearance
    app = QApplication.instance()
    if app is None:
        return
    hints = app.styleHints()
    hints.setColorScheme(_scheme_for(appearance))
    dark = appearance == "dark" or (appearance == "system" and _system_is_dark(app))
    if USES_FUSION:
        app.setPalette(_fusion_palette(dark))
    else:
        # Native macOS palette, which follows the scheme set above; the light
        # theme's window and lists are taken down to the shared light gray.
        # Reset first, so a previous light override never sticks to dark.
        app.setPalette(QPalette())
        if not dark:
            palette = QPalette(app.palette())
            for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
                palette.setColor(group, QPalette.Window, QColor(LIGHT_WINDOW))
                palette.setColor(group, QPalette.Base, QColor(LIGHT_BASE))
                palette.setColor(group, QPalette.AlternateBase, QColor(LIGHT_PANE))
            app.setPalette(palette)
    if notify and _notify_timer is not None:
        _notify_timer.start()


def _fusion_palette(dark: bool) -> QPalette:
    """The macOS dark tones (window #323232, lists #1c1c1c…) for Dark; the
    shared light gray (LIGHT_WINDOW, LIGHT_BASE…) for Light."""
    if dark:
        c = {
            "window": "#323232", "text": "#f0f0f0", "base": "#1c1c1c", "alt": "#262626",
            "button": "#4a4a4a", "button_text": "#f0f0f0", "bright": "#ffffff",
            "light": "#5a5a5a", "midlight": "#474747", "mid": "#2a2a2a", "dark": "#1a1a1a",
            "shadow": "#0a0a0a", "tooltip": "#2b2b2b", "tooltip_text": "#f0f0f0",
            "placeholder": "#8a8a8a", "disabled": "#7a7a7a", "link": "#6fa9de",
        }
    else:
        c = {
            "window": LIGHT_WINDOW, "text": "#1e1e1e", "base": LIGHT_BASE, "alt": LIGHT_PANE,
            "button": "#e4e4e4", "button_text": "#1e1e1e", "bright": "#000000",
            "light": "#f0f0f0", "midlight": "#e6e6e6", "mid": "#b8b8b8", "dark": "#8e8e8e",
            "shadow": "#606060", "tooltip": LIGHT_POPUP, "tooltip_text": "#1e1e1e",
            "placeholder": "#8a8a8a", "disabled": "#9a9a9a", "link": "#3f7ec2",
        }
    p = QPalette()
    roles = {
        QPalette.Window: "window", QPalette.WindowText: "text", QPalette.Base: "base",
        QPalette.AlternateBase: "alt", QPalette.Text: "text", QPalette.Button: "button",
        QPalette.ButtonText: "button_text", QPalette.BrightText: "bright",
        QPalette.Light: "light", QPalette.Midlight: "midlight", QPalette.Mid: "mid",
        QPalette.Dark: "dark", QPalette.Shadow: "shadow", QPalette.ToolTipBase: "tooltip",
        QPalette.ToolTipText: "tooltip_text", QPalette.PlaceholderText: "placeholder",
        QPalette.Link: "link",
    }
    for role, key in roles.items():
        p.setColor(role, QColor(c[key]))
    p.setColor(QPalette.Highlight, QColor("#5b9bd5"))
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.Accent, QColor("#5b9bd5"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(c["disabled"]))
    p.setColor(QPalette.Disabled, QPalette.Highlight, QColor("#4a6a8a"))
    return p
