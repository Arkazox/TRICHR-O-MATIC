"""Preview cache stored inside .trirgb session files.

Decoding every full-resolution source photo just to build its ~1400px
editing preview is what makes reopening a big session slow (44MP JPEGs take
~0.4s each). A saved session therefore carries, in its own separate
top-level ``"preview_cache"`` block (never mixed into the settings), a small
JPEG of each preview, so the next open can show everything at once.

The cache is only ever a stand-in: after opening, MainWindow recomputes
every cache-sourced preview from the original file in the background
(compute_exact_preview, the exact same pipeline as a normal load), and
export / HQ Preview always read the originals - so quality never depends on
the cache. An entry is ignored when its source file's size or modification
time no longer matches.

No Qt here (same rule as imaging.py).
"""
from __future__ import annotations

import base64
import io
import json
import os
from typing import Optional

import numpy as np
from PIL import Image

from . import imaging

CACHE_FORMAT_VERSION = 1
_JPEG_QUALITY = 90


def layer_cache_key(path: str, decode: str, slot: str, film_base, quarter_turns: int) -> str:
    """Identifies one preview: same file decoded the same way with the same
    load-time corrections. ``decode`` is "L" (luminance), "R"/"G"/"B" (Color
    Trichrome's single real channel) or "RGB" (Solo photo); ``slot`` is the
    channel the film-base correction is read for ("R"/"G"/"B", "N" for Solo)."""
    fb = json.dumps(film_base, sort_keys=True) if film_base else ""
    return f"{decode}|{slot}|{int(quarter_turns) % 4}|{fb}|{path}"


def compute_exact_preview(
    path: str, decode: str, slot: str, film_base, quarter_turns: int,
) -> tuple[np.ndarray, float]:
    """The normal (non-cached) way a layer's preview is built at load time:
    full decode -> film-base correction -> quarter turns -> make_preview.
    Thread-safe (pure numpy/PIL/cv2, no shared state)."""
    if decode == "RGB":
        full = imaging.load_color(path)
        full = imaging.apply_film_base_correction(full, film_base)
    else:
        full = imaging.load_grayscale(path, channel=decode if decode in ("R", "G", "B") else None)
        full = imaging.apply_film_base_correction(full, film_base, channel=slot)
    if quarter_turns:
        full = np.ascontiguousarray(np.rot90(full, quarter_turns))
    return imaging.make_preview(full)


def _file_signature(path: str) -> Optional[tuple[int, int]]:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_size, st.st_mtime_ns


def encode_entry(preview: np.ndarray, preview_scale: float, path: str) -> Optional[dict]:
    """A cache entry for ``preview`` (float32 in [0, 1], 2D gray or HxWx3)."""
    sig = _file_signature(path)
    if sig is None:
        return None
    u8 = (np.clip(preview, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(u8).save(buf, "JPEG", quality=_JPEG_QUALITY)
    return {
        "file_size": sig[0],
        "file_mtime_ns": sig[1],
        "preview_scale": float(preview_scale),
        "shape": list(preview.shape),
        "jpeg": base64.b64encode(buf.getvalue()).decode("ascii"),
    }


def decode_entry(entry: dict, path: str) -> Optional[tuple[np.ndarray, float]]:
    """(preview, preview_scale), or None when the entry is unusable - the
    source file changed or vanished, or the entry is malformed."""
    try:
        if _file_signature(path) != (int(entry["file_size"]), int(entry["file_mtime_ns"])):
            return None
        img = Image.open(io.BytesIO(base64.b64decode(entry["jpeg"])))
        arr = np.asarray(img, dtype=np.float32) / 255.0
        if list(arr.shape) != list(entry["shape"]):
            return None
        return np.ascontiguousarray(arr), float(entry["preview_scale"])
    except Exception:
        return None


def build_cache_block(entries: dict[str, dict]) -> dict:
    return {"format_version": CACHE_FORMAT_VERSION, "entries": entries}


def read_cache_block(data: dict) -> dict[str, dict]:
    block = data.get("preview_cache")
    if not isinstance(block, dict) or block.get("format_version") != CACHE_FORMAT_VERSION:
        return {}
    entries = block.get("entries")
    return entries if isinstance(entries, dict) else {}
