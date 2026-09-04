"""Data model for a trichrome channel layer and the overall project state."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

CHANNEL_NAMES = ("R", "G", "B")  # stable internal identifiers, independent of UI language

_next_batch_item_uid = 0


def _generate_batch_item_uid() -> int:
    global _next_batch_item_uid
    uid = _next_batch_item_uid
    _next_batch_item_uid += 1
    return uid


def ensure_batch_item_uid_above(n: int) -> None:
    """Advance the uid counter past ``n`` - called after restoring a session
    so freshly-created items (uid assigned fresh each process run) can't
    collide with, or sort ahead of, restored items that carry higher
    persisted uids from a previous run."""
    global _next_batch_item_uid
    _next_batch_item_uid = max(_next_batch_item_uid, n + 1)


@dataclass
class ChannelLayer:
    """One of the three black & white shots (R, G or B filter)."""

    color_index: int  # 0=R, 1=G, 2=B slot in the composed image
    label: str

    path: Optional[str] = None
    image_full: Optional[np.ndarray] = None      # float32 [0,1], full resolution grayscale
    image_preview: Optional[np.ndarray] = None    # float32 [0,1], downsampled for interactive editing
    preview_scale: float = 1.0                    # preview_size = full_size * preview_scale

    # Geometric alignment (similarity transform about the image's own center)
    dx: float = 0.0
    dy: float = 0.0
    scale: float = 1.0
    rotation: float = 0.0  # degrees

    # Per-channel tonal correction. black_point/white_point follow the usual
    # photo-editing convention (Lightroom's Blacks/Whites): positive lightens
    # (lifts blacks / raises whites), negative darkens, 0 is a no-op.
    black_point: float = 0.0
    white_point: float = 0.0
    gamma: float = 1.0
    exposure: float = 0.0  # stops (EV) - multiplicative, applied before black/white point
    brightness: float = 0.0
    contrast: float = 1.0
    shadows: float = 0.0
    highlights: float = 0.0
    invert: bool = False  # raw negative scan: invert tones before the tone curve
    # Harris Shutter mode: this channel's pixel data was extracted from its
    # own real R/G/B plane at load time (imaging.load_grayscale(channel=...))
    # instead of standard luminance - kept identical across all 3 channels
    # of a photo, same invariant as invert, and like invert not part of
    # has_tone_correction()/reset_tone() (see MainWindow.on_harris_shutter_toggled).
    # Unlike invert, changing it requires an actual reload from disk (it
    # changes what the pixel data *is*, not a live transform on top of it).
    harris_shutter: bool = False

    # Film base correction (2026-09-04, see the "Sample Film Base" section
    # in CLAUDE.md) - a per-channel reference {"R"/"G"/"B": float} sampled
    # from the film's own clear/unexposed base, normalized out of the raw
    # loaded pixel data *before* invert (imaging.apply_film_base_correction)
    # to remove a fixed base/mask tint (e.g. color negative's orange mask)
    # that a post-invert white-balance pick can't fully undo. Same
    # invariant as harris_shutter: changing it requires an actual reload
    # from disk, not a live transform layered on top - a trichrome
    # ChannelLayer only ever reads its own R/G/B key from this dict (the
    # other 2 keys are unused but harmless to carry), while normal_layer
    # (a full color image, not one channel) uses all 3. None means no
    # correction. Deliberately excluded from copy/paste and Reset All,
    # same reasoning as harris_shutter: it's the photo's own source-
    # interpretation of a specific roll's film base, not a general "look"
    # that makes sense on an unrelated photo or has an obvious reset
    # default. WARNING: like GlobalCorrection.curve_points, this is a
    # mutable dict - undo/redo's shallow copy.copy() means every write
    # site must *replace* this field with a fresh dict, never mutate one
    # in place, or a pushed undo snapshot can silently share state with
    # the live object.
    film_base: Optional[dict] = None

    is_reference: bool = False
    solo: bool = False

    # Net quarter turns (90 degree steps) applied since the file was loaded,
    # stored so a full-resolution reload from disk (export, session restore)
    # can reapply the same orientation via np.rot90(raw, quarter_turns).
    quarter_turns: int = 0

    def has_image(self) -> bool:
        # image_full may be left unloaded (lazily reloaded from ``path`` only
        # when actually needed, e.g. at export time) for batch-imported items
        # to avoid holding many full-resolution images in memory at once.
        return self.image_preview is not None

    def is_missing(self) -> bool:
        """True when a source path was recorded (import or session restore)
        but the file couldn't be loaded from it - moved or deleted on disk
        since. ``path`` is deliberately retained in that case (see the
        session-restore code in main_window.py) so the missing path can
        still be shown to the user and relinked via "Locate"."""
        return bool(self.path) and not self.has_image()

    def reset_alignment(self) -> None:
        self.dx = 0.0
        self.dy = 0.0
        self.scale = 1.0
        self.rotation = 0.0

    def has_alignment_correction(self) -> bool:
        return self.dx != 0.0 or self.dy != 0.0 or self.scale != 1.0 or self.rotation != 0.0

    def reset_tone(self) -> None:
        self.black_point = 0.0
        self.white_point = 0.0
        self.gamma = 1.0
        self.exposure = 0.0
        self.brightness = 0.0
        self.contrast = 1.0
        self.shadows = 0.0
        self.highlights = 0.0

    def has_tone_correction(self) -> bool:
        return (
            self.black_point != 0.0 or self.white_point != 0.0 or self.gamma != 1.0
            or self.exposure != 0.0
            or self.brightness != 0.0 or self.contrast != 1.0
            or self.shadows != 0.0 or self.highlights != 0.0
        )

    def rotate_quarter(self, clockwise: bool) -> None:
        """Rotate the source pixel data itself by 90 degrees (as opposed to
        ``rotation``, a small fine-alignment angle). The alignment offset is
        rotated along with it so existing manual alignment survives; the
        fine-alignment rotation/scale stay valid unchanged since a uniform
        turn of the raw image doesn't change its angle *relative to* the
        other channels.
        """
        k = -1 if clockwise else 1
        self.quarter_turns = (self.quarter_turns + k) % 4
        if self.image_full is not None:
            self.image_full = np.ascontiguousarray(np.rot90(self.image_full, k))
        if self.image_preview is not None:
            self.image_preview = np.ascontiguousarray(np.rot90(self.image_preview, k))
        dx, dy = self.dx, self.dy
        self.dx, self.dy = (-dy, dx) if clockwise else (dy, -dx)


@dataclass
class GlobalCorrection:
    black_point: float = 0.0
    white_point: float = 0.0
    gamma: float = 1.0
    exposure: float = 0.0  # stops (EV) - multiplicative, applied before black/white point
    brightness: float = 0.0
    contrast: float = 1.0
    shadows: float = 0.0
    highlights: float = 0.0
    saturation: float = 1.0
    temperature: float = 0.0
    tint: float = 0.0
    # Classic tone curves (Curves block) - 4 independent channel curves,
    # "Y" (master/luminosity, applied to R/G/B identically) plus "R"/"G"/"B"
    # (each applied only to its own channel, on top of "Y") - the same
    # channel-selector composition a classic Photoshop Curves dialog uses.
    # Added as one master curve 2026-09-04, split into per-channel the same
    # day once the user asked to edit them separately ("je veux pouvoir
    # modifier séparément les courbes YRGB"). Each value is a list of
    # (input, output) control points in [0,1], sorted by input - the
    # endpoints (input 0 and 1 in the *default* identity curve) can be
    # dragged inward too, which clips input tones beyond them to a flat
    # output (a black/white point), not just move vertically - see
    # imaging.evaluate_curve_lut/apply_curve/apply_curves. Always REPLACE a
    # channel's list wholesale rather than mutating it in place
    # (CurveEditor.points() already returns a fresh list each time) -
    # _snapshot_state's undo/redo copy is a shallow copy.copy() of the
    # whole GlobalCorrection, which would otherwise share list identity
    # between the live object and a saved snapshot.
    curves: dict[str, list[tuple[float, float]]] = field(
        default_factory=lambda: {ch: [(0.0, 0.0), (1.0, 1.0)] for ch in ("Y", "R", "G", "B")})

    _IDENTITY_CURVE = [(0.0, 0.0), (1.0, 1.0)]
    _CURVE_CHANNELS = ("Y", "R", "G", "B")

    def reset(self) -> None:
        self.__init__()

    def has_light_correction(self) -> bool:
        return (
            self.black_point != 0.0 or self.white_point != 0.0 or self.gamma != 1.0
            or self.exposure != 0.0
            or self.brightness != 0.0 or self.contrast != 1.0
            or self.shadows != 0.0 or self.highlights != 0.0
        )

    def has_color_correction(self) -> bool:
        return self.saturation != 1.0 or self.temperature != 0.0 or self.tint != 0.0

    def has_curve_correction(self) -> bool:
        return any(list(self.curves.get(ch, self._IDENTITY_CURVE)) != self._IDENTITY_CURVE
                   for ch in self._CURVE_CHANNELS)

    def has_correction(self) -> bool:
        return self.has_light_correction() or self.has_color_correction()


@dataclass
class CropSettings:
    """Crop applied to the whole recomposed image (not per-channel) -
    straighten/mirror/crop, in that order (see imaging.apply_crop)."""

    # Crop rect, normalized [0,1] relative to the (already straightened/
    # mirrored) composed image. (0,0,1,1) is "no crop" - the full frame.
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0
    rotation: float = 0.0  # "straighten", degrees, rotated about center
    mirror_h: bool = False  # left/right flip
    mirror_v: bool = False  # top/bottom flip

    # "original" (the photo's own composed aspect ratio) is the default -
    # "free" must be picked explicitly. ratio_value() can't resolve
    # "original" on its own (it needs the actual image size), so callers
    # special-case it - see MainWindow._current_crop_ratio_value().
    aspect_ratio: str = "original"  # "original"|"free"|"1:1"|"5:4"|"4:3"|"7:5"|"3:2"|"16:9"|"custom"
    aspect_portrait: bool = False  # swap W:H of the selected ratio ("invert orientation")
    custom_ratio_w: float = 1.0
    custom_ratio_h: float = 1.0

    _PRESET_RATIOS = {
        "1:1": 1.0, "5:4": 5 / 4, "4:3": 4 / 3, "7:5": 7 / 5, "3:2": 3 / 2, "16:9": 16 / 9,
    }

    def reset(self) -> None:
        self.__init__()

    def has_crop(self) -> bool:
        """True if any field differs from a fresh CropSettings() default -
        i.e. the Crop panel's own Reset button would actually change
        something. Includes aspect_ratio/portrait/custom ratio, unlike an
        earlier, narrower version of this check that only looked at the
        rect/straighten/mirror fields."""
        return (
            self.x != 0.0 or self.y != 0.0 or self.width != 1.0 or self.height != 1.0
            or self.rotation != 0.0 or self.mirror_h or self.mirror_v
            or self.aspect_ratio != "original" or self.aspect_portrait
            or self.custom_ratio_w != 1.0 or self.custom_ratio_h != 1.0
        )

    def ratio_value(self) -> Optional[float]:
        """Numeric width/height for the current aspect ratio setting, or
        None for "free" or "original" (unconstrained/context-dependent)."""
        if self.aspect_ratio in ("free", "original"):
            return None
        if self.aspect_ratio == "custom":
            ratio = (self.custom_ratio_w / self.custom_ratio_h) if self.custom_ratio_h else None
        else:
            ratio = self._PRESET_RATIOS.get(self.aspect_ratio)
        if ratio and self.aspect_portrait:
            ratio = 1.0 / ratio
        return ratio


def new_project_layers() -> list[ChannelLayer]:
    layers = [ChannelLayer(color_index=i, label=CHANNEL_NAMES[i]) for i in range(3)]
    layers[1].is_reference = True  # green channel as default reference
    return layers


@dataclass
class BatchItem:
    """One imported batch photo: its own independent alignment/color state.

    ``layers`` normally carry only a preview-resolution image (``image_full``
    left as None) - the full-resolution file is reloaded from ``path`` only
    when this item is actually exported, so importing many large scans at
    once doesn't hold them all in memory simultaneously.
    """

    base: str
    paths: dict  # {"R": path, "G": path, "B": path}
    layers: list  # 3 ChannelLayer
    global_corr: GlobalCorrection
    selected: bool = False  # by default only the active photo is selected
    crop: CropSettings = field(default_factory=CropSettings)

    # Normal/Trichrome mode (added 2026-09-04, first step of widening the
    # app beyond trichromy) - "trichrome" (default, preserves all existing
    # behavior) recomposes the image from ``layers`` (3 B&W-through-filter
    # shots); "normal" is a single already-color photo, loaded straight into
    # ``normal_layer`` and never warped/aligned/recomposed - Light/Color/
    # Crop/Curves still apply on top either way (see MainWindow.
    # recompute_preview's mode branch). ``layers`` still always exists (3
    # default ChannelLayers) even in "normal" mode, deliberately never
    # repurposed or left as None - every one of the many existing call sites
    # across this codebase that unconditionally reads `item.layers[i]` stays
    # correct without needing to know about mode at all; only the places
    # that actually compose/display/export the image, or gate the RGB
    # Channels tool, need to check it.
    mode: str = "trichrome"  # "trichrome" | "normal"
    # A plain ChannelLayer reused as a convenient single-image holder (gets
    # has_image()/is_missing() for free) - NOT one of the 3 trichrome
    # channels and never passed into compose_trichrome/compose_rgb_from_channels;
    # its own alignment/tone/harris_shutter fields are unused (Normal mode
    # has no per-channel controls, no UI exposes them), only
    # path/image_full/image_preview/preview_scale/quarter_turns/invert
    # matter here.
    normal_layer: ChannelLayer = field(
        default_factory=lambda: ChannelLayer(color_index=0, label="Normal"))

    # Stable identity, assigned once and never reassigned (even by undo/redo
    # or a resort) - lets the UI track "this same photo" across reordering,
    # and doubles as the "import order" sort key.
    uid: int = field(default_factory=_generate_batch_item_uid)
    # EXIF capture date (epoch seconds) if known; None falls back to uid
    # (import order) so sorting stays deterministic without it.
    capture_date: Optional[float] = None
    # Position in the user's manual (drag-and-drop) ordering; None falls
    # back to uid so a never-reordered item sorts as if by import order.
    custom_order: Optional[float] = None

    def effective_capture_date(self) -> float:
        return self.uid if self.capture_date is None else self.capture_date

    def effective_custom_order(self) -> float:
        return self.uid if self.custom_order is None else self.custom_order
