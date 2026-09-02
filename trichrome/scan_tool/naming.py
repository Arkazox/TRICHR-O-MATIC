"""Filename generation for scan captures: <roll name>_<index>.<ext>."""
from __future__ import annotations

import re

_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|]')
_PAD = 3


def sanitize_roll_name(name: str) -> str:
    name = _UNSAFE_CHARS.sub("_", name).strip()
    return name or "roll"


def base_name(roll_name: str, index: int) -> str:
    """``<sanitized roll name>_<index>``, no extension - the stem shared by
    a single capture's filename and (for an RGB-backlight triplet) its
    recomposed processed output, which drops the per-channel suffix."""
    return f"{sanitize_roll_name(roll_name)}_{index:0{_PAD}d}"


def build_filename_pattern(roll_name: str, index: int, channel: str | None = None) -> str:
    """A gphoto2 filename pattern (no directory) - ``%C`` lets gphoto2 fill
    in the real extension (RAF/JPG/...), which depends on the camera's
    current quality setting and isn't known ahead of the capture.
    ``channel`` (``"R"``/``"G"``/``"B"``), when given, appends a suffix so
    the 3 shots of an RGB-backlight triplet share the same index and sort
    together while staying distinguishable - e.g. ``Roll01_004_R.%C``."""
    base = base_name(roll_name, index)
    if channel:
        base += f"_{channel}"
    return f"{base}.%C"
