"""Batch mode support: matching R/G/B files by filename inside one folder."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from . import filters as filters_module
from . import imaging

IMAGE_EXTENSIONS = imaging.IMPORTABLE_EXTENSIONS
_SEPARATORS = ("_", "-", " ", ".")

# For each fixed Advanced Options mode: which filter gets patched into each
# digital R/G/B channel. "custom" is user-defined (see filters.registry's
# get_custom_mapping/set_custom_mapping) and resolved dynamically.
_STATIC_MODE_CHANNEL_FILTERS = {
    "classic": {"R": "R", "G": "G", "B": "B"},
    "ir": {"R": "IR", "G": "G", "B": "B"},
    "aerochrome": {"R": "IR", "G": "R", "B": "G"},
}


def mode_channel_filters(mode: str) -> dict[str, str]:
    """Which filter feeds which digital R/G/B channel for the given mode."""
    if mode == "custom":
        return filters_module.registry.get_custom_mapping()
    return _STATIC_MODE_CHANNEL_FILTERS.get(mode, _STATIC_MODE_CHANNEL_FILTERS["classic"])


@dataclass
class Triplet:
    base: str
    paths: dict  # {"R": path, "G": path, "B": path}


def build_manual_triplets(r_paths: list[str], g_paths: list[str], b_paths: list[str],
                           ref_letter: str = "R") -> list[Triplet]:
    """Pair up manually-picked file lists by position: item i of each list forms one triplet.

    Extra items past the shortest list are ignored (the caller should warn about that).
    """
    lists = {"R": r_paths, "G": g_paths, "B": b_paths}
    n = min(len(r_paths), len(g_paths), len(b_paths))
    ref_list = lists.get(ref_letter, r_paths)
    triplets = []
    for i in range(n):
        paths = {"R": r_paths[i], "G": g_paths[i], "B": b_paths[i]}
        base = os.path.splitext(os.path.basename(ref_list[i]))[0]
        triplets.append(Triplet(base=base, paths=paths))
    return triplets


def build_semiauto_triplets(paths: list[str], ref_letter: str = "R") -> list[Triplet]:
    """Group a flat, ordered file list into R/G/B triplets, 3 files at a time.

    Files are assumed to already be in R, G, B, R, G, B... order. Any
    trailing files that don't complete a full triplet are ignored (the
    caller is expected to warn if ``len(paths)`` isn't a multiple of 3).
    """
    triplets = []
    for i in range(len(paths) // 3):
        r_path, g_path, b_path = paths[3 * i], paths[3 * i + 1], paths[3 * i + 2]
        by_channel = {"R": r_path, "G": g_path, "B": b_path}
        ref_path = by_channel.get(ref_letter, r_path)
        base = os.path.splitext(os.path.basename(ref_path))[0]
        triplets.append(Triplet(base=base, paths=by_channel))
    return triplets


def _filter_for_token(token: str) -> str | None:
    token_l = token.lower()
    for filt, tokens in filters_module.registry.tokens_map().items():
        if token_l in tokens:
            return filt
    return None


def detect_filter(stem: str) -> tuple[str | None, str]:
    """Return (filter, base_name) for a filename stem (no extension).

    Tries a trailing separated token, then a leading one, then a bare
    trailing/leading token with no separator at all (longest token first,
    e.g. "IR" before a single letter).
    """
    for sep in _SEPARATORS:
        if sep in stem:
            base, _, suffix = stem.rpartition(sep)
            filt = _filter_for_token(suffix)
            if filt and base:
                return filt, base

    for sep in _SEPARATORS:
        if sep in stem:
            prefix, _, rest = stem.partition(sep)
            filt = _filter_for_token(prefix)
            if filt and rest:
                return filt, rest

    for n in (2, 1):
        if len(stem) > n:
            filt = _filter_for_token(stem[-n:])
            if filt:
                return filt, stem[:-n]
            filt = _filter_for_token(stem[:n])
            if filt:
                return filt, stem[n:]

    return None, stem


def _natural_key(text: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def find_triplets(folder: str, mode: str = "classic") -> tuple[list[Triplet], list[str]]:
    """Scan a folder for image files and group them into R/G/B triplets by name.

    ``mode`` picks which filter gets patched into which digital channel (see
    mode_channel_filters) - e.g. under "ir" an infrared-filtered photo is what
    fills the digital Red channel, not a red-filtered one.

    Two matching passes run in order:
    1. Files that share an identical base name once their filter token is
       stripped (e.g. "shot1_R" / "shot1_G" / "shot1_B") are grouped by that
       base name - this is the common "shoot with a fixed rig" naming.
    2. Whatever is left (e.g. a plain scanned sequence "Image1_R",
       "Image2_G", "Image3_B", "Image4_IR", "Image5_R"... where every photo
       has its own unique name) is instead treated as one flat, ordered
       stream of filtered photos: relevant ones (whose filter this mode
       actually uses) are consumed 3 at a time in folder order, each landing
       on the channel its own filter maps to - so switching modes changes
       which files even count as "relevant" and thus how they group.

    Returns (triplets, unmatched_filenames), both usable even if incomplete;
    the caller decides how to report unmatched or incomplete groups.
    """
    channel_filters = mode_channel_filters(mode)
    filter_to_channel = {filt: channel for channel, filt in channel_filters.items()}

    try:
        entries = sorted(os.listdir(folder), key=_natural_key)
    except OSError:
        return [], []

    # Every relevant (filter used by this mode) file, in folder order.
    relevant: list[tuple[str, str, str, str]] = []  # (channel, base, name, path)
    unmatched: list[str] = []
    for name in entries:
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        stem, ext = os.path.splitext(name)
        if ext.lower() not in IMAGE_EXTENSIONS:
            continue
        filt, base = detect_filter(stem)
        channel = filter_to_channel.get(filt) if filt else None
        if channel is None:
            unmatched.append(name)
            continue
        relevant.append((channel, base, name, path))

    # Pass 1: identical-base-name grouping.
    groups: dict[str, dict] = {}
    for channel, base, name, path in relevant:
        groups.setdefault(base, {})[channel] = (name, path)

    triplets = []
    used_paths: set[str] = set()
    for base in sorted(groups.keys(), key=_natural_key):
        entry = groups[base]
        if all(c in entry for c in ("R", "G", "B")):
            triplets.append(Triplet(base=base, paths={c: entry[c][1] for c in ("R", "G", "B")}))
            used_paths.update(entry[c][1] for c in ("R", "G", "B"))

    # Pass 2: flat ordered-stream fallback, over whatever pass 1 left behind.
    leftover = [(channel, base, name, path) for channel, base, name, path in relevant
                if path not in used_paths]
    remainder = len(leftover) % 3
    clean_len = len(leftover) - remainder
    for i in range(0, clean_len, 3):
        chunk = leftover[i:i + 3]
        by_channel = {c: p for c, _, _, p in chunk}
        if len(by_channel) == 3:
            ref_base = next(b for c, b, _, _ in chunk if c == "R")
            triplets.append(Triplet(base=ref_base, paths=by_channel))
        else:
            unmatched.extend(n for _, _, n, _ in chunk)
    if remainder:
        unmatched.extend(n for _, _, n, _ in leftover[-remainder:])

    return triplets, sorted(unmatched, key=_natural_key)
