"""Per-subfolder scan_manifest.json - records each capture's mode/invert
alongside its filename, so a future "import this folder into a session" step
(not built yet - this tool doesn't touch sessions at all today) has
something to read instead of re-deriving the mode from the filename."""
from __future__ import annotations

import datetime
import json
import os

MANIFEST_NAME = "scan_manifest.json"


def append_entry(
    folder: str, filename: str, mode: str, invert: bool, channel: str | None = None,
) -> None:
    """``channel`` (``"R"``/``"G"``/``"B"``), when given, marks this file as
    one shot of an RGB-backlight triplet - a future import step can then map
    the 3 files sharing an index straight to a BatchItem's 3 ChannelLayers by
    channel identity instead of re-deriving it from the filename suffix."""
    path = os.path.join(folder, MANIFEST_NAME)
    entries = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, OSError):
            entries = []
    entry = {
        "filename": filename,
        "mode": mode,
        "invert": invert,
        "captured_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    if channel:
        entry["channel"] = channel
    entries.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
