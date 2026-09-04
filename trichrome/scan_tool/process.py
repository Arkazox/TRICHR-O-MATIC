"""Post-capture processing: an automatic JPG preview copy in a "processed"
subfolder next to the raw captures. No Qt here - reuses trichrome.imaging/
trichrome.alignment, the exact same pure functions the main app's own
export pipeline is built on, so this preview matches what a real import
would eventually produce.

Single-shot modes (B&W/Color/Color Reversal) just invert (or not) per the
mode's own convention - the same True/False already carried by
scan_window.MODES. An RGB-backlight triplet instead gets a full recompose:
auto-align the 2 non-reference channels onto the reference (same algorithm
and reference-channel convention - index 1, "G" - as the main app), then
imaging.compose_trichrome with neutral tone/global params, invert coming
from whichever capture mode is currently selected (Light and Mode are
independent settings; this respects Mode's own polarity either way).
"""
from __future__ import annotations

import os

import numpy as np

from .. import imaging
from ..alignment import AlignmentError, auto_align_layer

PROCESSED_SUBFOLDER = "processed"

_NEUTRAL_TONE = (0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
# 12th element is the Curves tool's per-channel curves dict (added to
# imaging.compose_trichrome's global_params shape 2026-09-04, after this
# module was originally written) - {} here means identity on every
# channel, same as _IDENTITY_CURVES in main_window.py. Without this,
# compose_trichrome's positional unpack would raise
# "not enough values to unpack" on every RGB-triplet recompose - a real
# latent bug this integration pass caught, since nothing had exercised
# process_rgb_triplet since curves were added.
_NEUTRAL_GLOBAL = (0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, {})
_REF_INDEX = 1  # "G" - matches the main app's default reference channel.


def processed_folder(dest_folder: str) -> str:
    folder = os.path.join(dest_folder, PROCESSED_SUBFOLDER)
    os.makedirs(folder, exist_ok=True)
    return folder


def process_single(path: str, invert: bool, is_color: bool, dest_folder: str) -> str:
    """Copies ``path`` into the processed subfolder as a JPG, grayscale for
    a B&W-mode capture or full color otherwise, inverted per ``invert``.
    Returns the saved path."""
    folder = processed_folder(dest_folder)
    out_path = os.path.join(folder, _jpg_name(path))
    if is_color:
        rgb = imaging.load_color(path)
        rgb = imaging.apply_invert(rgb, invert)
    else:
        gray = imaging.load_grayscale(path)
        gray = imaging.apply_invert(gray, invert)
        rgb = np.stack([gray, gray, gray], axis=-1)
    imaging.save_image(out_path, rgb)
    return out_path


def process_rgb_triplet(
    paths_by_channel: dict[str, str], invert: bool, dest_folder: str, out_basename: str,
) -> str:
    """Recomposes the 3 R/G/B-backlight shots into one trichrome JPG using
    the same auto-align + compose pipeline as the main app. ``out_basename``
    is the combined output's filename (no per-channel suffix, no
    extension) - e.g. the roll+index shared by all 3 source shots. Returns
    the saved path."""
    folder = processed_folder(dest_folder)
    out_path = os.path.join(folder, f"{out_basename}.jpg")

    images = [imaging.load_grayscale(paths_by_channel[ch]) for ch in ("R", "G", "B")]
    reference = images[_REF_INDEX]

    geo_params = []
    for i in range(3):
        if i == _REF_INDEX:
            geo_params.append((0.0, 0.0, 1.0, 0.0))
            continue
        try:
            geo_params.append(auto_align_layer(reference, images[i]))
        except AlignmentError:
            # Best-effort preview - fall back to no alignment for this
            # channel rather than failing the whole recompose over it.
            geo_params.append((0.0, 0.0, 1.0, 0.0))

    tone_params = [(*_NEUTRAL_TONE, invert) for _ in range(3)]
    rgb = imaging.compose_trichrome(images, geo_params, tone_params, _REF_INDEX, _NEUTRAL_GLOBAL)
    imaging.save_image(out_path, rgb)
    return out_path


def _jpg_name(path: str) -> str:
    base = os.path.splitext(os.path.basename(path))[0]
    return f"{base}.jpg"
