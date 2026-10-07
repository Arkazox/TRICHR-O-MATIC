"""Resolve paths to bundled resource files (icons, etc.) - works both when
running from source and from the PyInstaller-frozen .app, where bundled data
lives under ``sys._MEIPASS`` instead of next to this file."""
from __future__ import annotations

import os
import sys


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts: str) -> str:
    base = getattr(sys, "_MEIPASS", None) or _repo_root()
    return os.path.join(base, *parts)


def icon_path(name: str) -> str:
    return resource_path("resources", "icons", name)
