"""Generates the Quick Tour's sample trichrome: 3 black-and-white 1920x1280
(3:2) images that, composed as R/G/B channels, show the app logo's motif -
three overlapping red/green/blue discs on a dark background, mixing to
yellow/magenta/cyan/white where they overlap.

Writes resources/sample/Trichrome_Sample_{R,G,B}.jpg. Run from the repo root:
    ./venv/bin/python scripts/generate_tour_sample.py
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image

W, H = 1920, 1280
RADIUS = 330
# Logo layout: red top-left, green top-right, blue bottom-center.
CENTERS = {"R": (W / 2 - 165, H / 2 - 120), "G": (W / 2 + 165, H / 2 - 120), "B": (W / 2, H / 2 + 165)}
DISC_LEVEL = 0.93
EDGE_SOFTNESS = 2.0  # px of anti-aliasing at each disc's edge
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "sample")


def channel(letter: str, rng: np.random.Generator) -> np.ndarray:
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    # Dark background with a soft vignette, identical in all 3 channels so
    # it composes to a neutral charcoal.
    r_norm = np.hypot((x - W / 2) / (W / 2), (y - H / 2) / (H / 2))
    background = 0.085 - 0.05 * np.clip(r_norm, 0, 1.4) ** 2
    cx, cy = CENTERS[letter]
    dist = np.hypot(x - cx, y - cy)
    disc = np.clip((RADIUS - dist) / EDGE_SOFTNESS + 0.5, 0, 1)
    # A gentle falloff toward each disc's rim, so it reads as lit rather
    # than flat vector art.
    shade = 1.0 - 0.10 * np.clip(dist / RADIUS, 0, 1) ** 3
    value = background * (1 - disc) + DISC_LEVEL * shade * disc
    # Independent fine grain per channel, like a real film/sensor capture.
    value += rng.normal(0, 0.008, size=value.shape).astype(np.float32)
    return (np.clip(value, 0, 1) * 255 + 0.5).astype(np.uint8)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = np.random.default_rng(1802)  # 1802: Thomas Young's three-color theory
    for letter in "RGB":
        path = os.path.join(OUT_DIR, f"Trichrome_Sample_{letter}.jpg")
        Image.fromarray(channel(letter, rng), mode="L").save(path, quality=92, optimize=True)
        print(path, os.path.getsize(path) // 1024, "KB")


if __name__ == "__main__":
    main()
