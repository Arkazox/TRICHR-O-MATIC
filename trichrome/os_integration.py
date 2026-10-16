"""The few places where the app talks to the operating system directly:
feedback sounds, revealing exported files, and the wording of keyboard
shortcuts and the file manager's name in UI text.

Everything here keeps the exact macOS behavior on ``darwin`` and adds a
Windows counterpart on ``win32``; any other platform gets a silent no-op."""
from __future__ import annotations

import os
import subprocess
import sys

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

# Scan is off on every platform for now: no toolbar slot, S key, menu entries
# or Quick Tour step, and no Preferences switch. Its code stays in
# trichrome/scan_tool and widgets/scan_panel.py. Set this back to
# ``not IS_WINDOWS`` to restore it (gphoto2 has no practical Windows build:
# libgphoto2 needs its USB driver swapped through Zadig), along with a
# Preferences switch for SCAN_TOOL_ENABLED_KEY.
SCAN_TOOL_AVAILABLE = False


# --- Sounds -----------------------------------------------------------------

# One distinct system sound per event, so each is told apart by ear.
_MAC_SOUNDS = {
    "save": "/System/Library/Sounds/Glass.aiff",
    "delete": "/System/Library/Sounds/Pop.aiff",
    "export_done": "/System/Library/Sounds/Hero.aiff",
}
# Windows sound-scheme aliases (Control Panel ▸ Sound ▸ Sounds), so the
# user's own scheme applies and nothing needs to be bundled.
_WINDOWS_SOUNDS = {
    "save": "SystemAsterisk",
    "delete": "SystemExclamation",
    "export_done": "SystemNotification",
}


def play_sound(event: str) -> None:
    """Fire-and-forget; a missing sound or player is silently ignored."""
    try:
        if IS_MAC:
            subprocess.Popen(
                ["afplay", _MAC_SOUNDS[event]],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif IS_WINDOWS:
            import winsound
            # SND_NODEFAULT: an alias the scheme leaves empty plays nothing,
            # instead of falling back to the default beep.
            winsound.PlaySound(
                _WINDOWS_SOUNDS[event],
                winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
    except Exception:
        pass


# --- File manager ------------------------------------------------------------

def reveal_file(path: str) -> None:
    """Show the file selected in Finder / File Explorer."""
    if IS_MAC:
        subprocess.run(["open", "-R", path])
    elif IS_WINDOWS:
        # explorer.exe exits with 1 even on success, so its status isn't
        # checked; Popen also avoids waiting on it.
        subprocess.Popen(["explorer", f"/select,{os.path.normpath(path)}"])


def open_folder(path: str) -> None:
    if IS_MAC:
        subprocess.run(["open", path])
    elif IS_WINDOWS:
        os.startfile(os.path.normpath(path))


# --- UI text -----------------------------------------------------------------

# The strings in i18n.py are written for macOS (⌘, Cmd+, Finder). On Windows
# Qt maps the same ControlModifier to the Ctrl key, so only the wording needs
# translating. Applied in order: the longer forms first.
_WINDOWS_TEXT = (
    ("⌘⌫", "Ctrl+Del"),
    # Quit: Windows closes the app with Alt+F4 (no Ctrl+Q binding).
    ("Cmd+Q", "Alt+F4"),
    ("⌘", "Ctrl+"),
    ("Cmd+", "Ctrl+"),
    ("Alt/Option", "Alt"),
)
_WINDOWS_FILE_MANAGER = {
    "en": (("Finder", "File Explorer"),),
    "fr": (("le Finder", "l'Explorateur de fichiers"), ("Finder", "Explorateur de fichiers")),
}


# Key-cap badges (<kbd>) in rich text: Windows otherwise draws arrows such as
# ↑/↓ from its color emoji font, in red; Segoe UI Symbol keeps them plain.
KBD_FONT_CSS = "font-family:'Segoe UI Symbol','Segoe UI';" if IS_WINDOWS else ""


def platform_text(text: str, language: str = "en") -> str:
    """UI text as written in i18n.py, adapted to the running platform."""
    if not IS_WINDOWS:
        return text
    for old, new in _WINDOWS_TEXT:
        text = text.replace(old, new)
    for old, new in _WINDOWS_FILE_MANAGER.get(language, _WINDOWS_FILE_MANAGER["en"]):
        text = text.replace(old, new)
    return text
