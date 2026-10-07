"""Low level image processing: loading, geometric warp, tonal correction, compositing."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import numpy as np
import cv2
import rawpy
from PIL import Image

# The resolution every live edit (sliders, curves, crop, alignment) actually
# recomposes at - main_window.py's recompute_preview() only ever reads
# layer.image_preview/normal_layer.image_preview, never the full-res source (HQ
# Preview is the separate, idle-triggered pass that does go higher). This value
# trades off directly against live responsiveness, not just sharpness. **Tried
# and reverted**: raising it to 1920 measured at ~120ms -> ~220ms for a single
# synthetic compose_trichrome pass, and live slider/curve dragging felt
# noticeably less snappy in the built app - reverted back to 1400 the same day.
# Don't raise this again without first addressing the live-recompute cost
# itself (the HQ Preview idle-pass mechanism below is the sharpness fix that
# doesn't cost live responsiveness).
MAX_PREVIEW_DIM = 1400

_EXIF_DATETIME_ORIGINAL = 36867
_EXIF_DATETIME = 306

# Extensions load_grayscale/load_color decode via plain PIL.
RASTER_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")

# Extensions load_grayscale/load_color hand to rawpy (LibRaw) instead of
# PIL. Not exhaustive of everything LibRaw can open - just the common
# formats worth recognizing by extension; .raf (Fuji) is listed first
# since the X-T3 is the one camera actually confirmed working with this
# app's Scan tool so far.
RAW_EXTENSIONS = (
    ".raf",
    ".cr2", ".cr3",
    ".nef", ".nrw",
    ".arw", ".srf", ".sr2",
    ".dng",
    ".orf",
    ".rw2",
    ".pef",
    ".raw",
)

# Every extension load_grayscale/load_color can actually open - the one
# shared source of truth for every file picker / drag-and-drop filter /
# batch-import filename matcher in the app, instead of each keeping its
# own separately-typed-out copy (which is how RAW support ended up scoped
# to only the Scan tool at first - nothing else recognized these
# extensions at all). A plain tuple, not a set, so it also works directly
# with str.endswith(), which several call sites already rely on.
IMPORTABLE_EXTENSIONS = RASTER_EXTENSIONS + RAW_EXTENSIONS


def is_raw_path(path: str) -> bool:
    """True if ``path``'s extension is one load_grayscale/load_color will
    decode via rawpy/LibRaw instead of PIL."""
    return os.path.splitext(path)[1].lower() in RAW_EXTENSIONS


def qt_image_name_filter_patterns() -> str:
    """Space-joined ``*.ext`` glob patterns for every extension
    load_grayscale/load_color can open - for a QFileDialog name filter,
    e.g. ``f"Images ({qt_image_name_filter_patterns()})"``."""
    return " ".join(f"*{ext}" for ext in IMPORTABLE_EXTENSIONS)


def _load_raw_rgb_uint16(path: str) -> np.ndarray:
    """Decode a RAW file via LibRaw into a demosaiced RGB array (uint16,
    full 0..65535 range) - the RAW counterpart of PIL's decode step in
    load_grayscale/load_color below, converging into the same dtype-
    normalization/channel-collapse tail those functions already have.

    Deliberately requests sRGB output (LibRaw's own default output_color/
    gamma), not linear - so a RAW source behaves like every other
    supported file type as far as this app's tone-curve/color pipeline is
    concerned, rather than needing a separate linear-aware code path.
    use_camera_wb neutralizes the sensor's own color filter array bias
    (same neutral starting point a camera's own JPEG/TIFF rendering
    already gives the PIL-based path) without no_auto_bright's opposite -
    LibRaw's own auto-exposure guess is left off since it would fight with
    this app's own Exposure/tone-curve sliders. user_flip is left at its
    default (-1: honor the file's own embedded orientation), so unlike
    the PIL path there's no separate _apply_exif_orientation step needed.
    """
    with rawpy.imread(path) as raw:
        return raw.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=16)


def extract_capture_date(path: str) -> Optional[float]:
    """Best-effort capture date (epoch seconds) for ``path``: EXIF
    DateTimeOriginal/DateTime if present, else the file's mtime, else None
    (caller falls back to import order)."""
    try:
        with Image.open(path) as pil_img:
            exif = pil_img.getexif()
        raw = exif.get(_EXIF_DATETIME_ORIGINAL) or exif.get(_EXIF_DATETIME)
        if raw:
            return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S").timestamp()
    except Exception:
        pass
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


_CHANNEL_INDEX = {"R": 0, "G": 1, "B": 2}


def load_grayscale(path: str, channel: Optional[str] = None) -> np.ndarray:
    """Load an image file as float32 grayscale in [0, 1], any bit depth.

    With ``channel`` left as None (the normal path - real photos shot B&W
    through a color filter), a color source is flattened to standard
    luminance, same as a genuinely single-channel source always is.

    With ``channel`` set to "R"/"G"/"B" (Harris Shutter Effect mode - the 3
    "channels" are actually 3 different color photos), a color source
    instead contributes only that one real channel, letting each slot carry
    that photo's actual red/green/blue data instead of its luminance. A
    source that's already single-channel has no channels to pick from
    either way, so it's used as-is regardless of ``channel``.
    """
    if is_raw_path(path):
        arr = _load_raw_rgb_uint16(path)
    else:
        pil_img = Image.open(path)
        pil_img = _apply_exif_orientation(pil_img)
        is_single_channel = pil_img.mode in ("L", "I", "I;16", "F")
        if not is_single_channel:
            pil_img = pil_img.convert("RGB") if channel else pil_img.convert("L")
        arr = np.asarray(pil_img)

    if arr.dtype == np.uint8:
        arr = arr.astype(np.float32) / 255.0
    elif arr.dtype == np.uint16:
        arr = arr.astype(np.float32) / 65535.0
    elif arr.dtype in (np.int32, np.int64):
        # PIL "I" mode (32 bit int) - normalize using observed max
        max_val = float(arr.max()) or 1.0
        arr = arr.astype(np.float32) / max_val
    else:
        arr = arr.astype(np.float32)
        if arr.max() > 1.0:
            arr = arr / arr.max()

    if arr.ndim == 3:
        arr = arr[..., _CHANNEL_INDEX[channel]] if channel else cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    return np.clip(arr, 0.0, 1.0)


def load_color(path: str) -> np.ndarray:
    """Load an image file as float32 RGB in [0, 1], any bit depth - unlike
    load_grayscale, never collapses to a single channel. For a real color
    photo (as opposed to this app's core case of 3 separate B&W-through-
    filter exposures), e.g. the scan tool's single-shot Color/Color Reversal
    processing preview."""
    if is_raw_path(path):
        arr = _load_raw_rgb_uint16(path)
    else:
        pil_img = Image.open(path)
        pil_img = _apply_exif_orientation(pil_img)
        pil_img = pil_img.convert("RGB")
        arr = np.asarray(pil_img)

    if arr.dtype == np.uint8:
        arr = arr.astype(np.float32) / 255.0
    elif arr.dtype == np.uint16:
        arr = arr.astype(np.float32) / 65535.0
    else:
        arr = arr.astype(np.float32)
        if arr.max() > 1.0:
            arr = arr / arr.max()

    return np.clip(arr, 0.0, 1.0)


def _apply_exif_orientation(pil_img: Image.Image) -> Image.Image:
    try:
        from PIL import ImageOps
        return ImageOps.exif_transpose(pil_img)
    except Exception:
        return pil_img


def make_preview(image_full: np.ndarray, max_dim: int = MAX_PREVIEW_DIM) -> tuple[np.ndarray, float]:
    """Return a downsized copy of image_full (if needed) and the scale factor used."""
    h, w = image_full.shape[:2]
    longest = max(h, w)
    if longest <= max_dim:
        return image_full.copy(), 1.0
    scale = max_dim / float(longest)
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
    resized = cv2.resize(image_full, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return resized, scale


def build_similarity_matrix(
    dx: float, dy: float, scale: float, rotation_deg: float,
    src_center: tuple[float, float], dst_center: tuple[float, float],
) -> np.ndarray:
    """2x3 matrix mapping source image coordinates to canvas coordinates.

    The image is rotated/scaled about its own center, then that center is
    placed at ``dst_center + (dx, dy)``.
    """
    theta = np.radians(rotation_deg)
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    r = np.array([[scale * cos_t, -scale * sin_t],
                  [scale * sin_t, scale * cos_t]], dtype=np.float64)

    cx, cy = src_center
    tcx, tcy = dst_center
    target = np.array([tcx + dx, tcy + dy], dtype=np.float64)
    translation = target - r @ np.array([cx, cy], dtype=np.float64)

    m = np.zeros((2, 3), dtype=np.float64)
    m[:, :2] = r
    m[:, 2] = translation
    return m


def decompose_similarity_matrix(
    m: np.ndarray, src_center: tuple[float, float], dst_center: tuple[float, float],
) -> tuple[float, float, float, float]:
    """Inverse of build_similarity_matrix: returns (dx, dy, scale, rotation_deg)."""
    a, b = m[0, 0], m[0, 1]
    c, d = m[1, 0], m[1, 1]
    scale = float(np.hypot(a, c)) or 1e-6
    rotation_deg = float(np.degrees(np.arctan2(c, a)))

    r = np.array([[a, b], [c, d]], dtype=np.float64)
    cx, cy = src_center
    tcx, tcy = dst_center
    t = m[:, 2]
    center_vec = r @ np.array([cx, cy], dtype=np.float64)
    dx = float(t[0] + center_vec[0] - tcx)
    dy = float(t[1] + center_vec[1] - tcy)
    return dx, dy, scale, rotation_deg


def compose_affine(outer: np.ndarray, inner: np.ndarray) -> np.ndarray:
    """The 2x3 affine matrix equivalent to applying ``inner`` then ``outer``."""
    outer3 = np.vstack([outer, [0.0, 0.0, 1.0]])
    inner3 = np.vstack([inner, [0.0, 0.0, 1.0]])
    return (outer3 @ inner3)[:2, :]


# Tunable "feel" constants for apply_lens_correction's 3 warp components -
# how strong an effect the slider's [-1, 1] range actually produces. Chosen
# empirically for a fine-correction tool (matching real small lens/tripod-
# tilt errors), not a dramatic creative-distortion one; revisit if the built
# app's own feel needs adjusting.
_DISTORTION_STRENGTH = 0.6
_PERSPECTIVE_STRENGTH = 0.6
_ANAMORPHIC_STRENGTH = 0.5


def _lens_correction_source_coords(xn, yn, distortion, perspective_v, perspective_h, anamorphic):
    """apply_lens_correction's own per-pixel formula: corrected
    (destination) center-normalized coordinates -> original (source) ones,
    for scalars or arrays. Shared with lens_correction_forward_point (the
    guided-perspective solver's point mapping), so the solver can never
    drift from the warp actually applied - see apply_lens_correction's
    docstring for the 3 steps."""
    xd = xn / (1.0 + perspective_v * yn * _PERSPECTIVE_STRENGTH)
    yd = yn / (1.0 + perspective_h * xn * _PERSPECTIVE_STRENGTH)

    r2 = xd ** 2 + yd ** 2
    radial_factor = 1.0 + distortion * _DISTORTION_STRENGTH * r2
    xd = xd * radial_factor
    yd = yd * radial_factor

    aspect_factor = 1.0 + anamorphic * _ANAMORPHIC_STRENGTH
    xd = xd / aspect_factor
    return xd, yd


def lens_correction_forward_point(
    xn: float, yn: float, distortion: float, perspective_v: float, perspective_h: float, anamorphic: float,
) -> tuple[float, float] | None:
    """Where an original-image point (center-normalized, [-1, 1] spanning
    the frame) lands once apply_lens_correction is applied - the inverse
    of _lens_correction_source_coords, which has no closed form, so solved
    by a few Newton steps (finite-difference Jacobian) starting from the
    point itself (the correction is always close to identity). None if it
    doesn't converge (a pathological coefficient combination)."""
    params = (distortion, perspective_v, perspective_h, anamorphic)
    x, y = xn, yn
    eps = 1e-5
    for _ in range(30):
        fx, fy = _lens_correction_source_coords(x, y, *params)
        ex, ey = fx - xn, fy - yn
        if abs(ex) < 1e-9 and abs(ey) < 1e-9:
            return x, y
        fxx, fyx = _lens_correction_source_coords(x + eps, y, *params)
        fxy, fyy = _lens_correction_source_coords(x, y + eps, *params)
        a, c = (fxx - fx) / eps, (fyx - fy) / eps
        b, d = (fxy - fx) / eps, (fyy - fy) / eps
        det = a * d - b * c
        if abs(det) < 1e-12 or not np.isfinite(det):
            return None
        x -= (d * ex - b * ey) / det
        y -= (-c * ex + a * ey) / det
        if not (np.isfinite(x) and np.isfinite(y)) or abs(x) > 10 or abs(y) > 10:
            return None
    fx, fy = _lens_correction_source_coords(x, y, *params)
    return (x, y) if abs(fx - xn) < 1e-6 and abs(fy - yn) < 1e-6 else None


def _guide_is_vertical(line, width: int, height: int) -> bool:
    (u0, v0), (u1, v1) = line
    return abs((v1 - v0) * height) >= abs((u1 - u0) * width)


def _golden_minimize(cost, lo: float = -1.0, hi: float = 1.0) -> float:
    """Coarse scan of [lo, hi], then golden-section refinement around the
    best sample - the guided-Perspective costs are smooth in their
    coefficient, but not guaranteed unimodal over the whole range."""
    samples = np.linspace(lo, hi, 81)
    costs = [cost(c) for c in samples]
    best = int(np.argmin(costs))
    if not np.isfinite(costs[best]):
        return float("nan")
    a = samples[max(0, best - 1)]
    b = samples[min(len(samples) - 1, best + 1)]
    ratio = (np.sqrt(5.0) - 1.0) / 2.0
    for _ in range(40):
        c1 = b - ratio * (b - a)
        c2 = a + ratio * (b - a)
        if cost(c1) <= cost(c2):
            b = c2
        else:
            a = c1
    return float(np.clip((a + b) / 2.0, lo, hi))


def solve_guided_perspective(
    lines, width: int, height: int,
    distortion: float, perspective_v: float, perspective_h: float, anamorphic: float,
) -> dict | None:
    """The Framing tool's guided Perspective mode: given up to 4 guide
    lines the user drew along edges that should be straight - in the
    *uncorrected* image's own normalized [0, 1] coordinates (``lines`` =
    [((u0, v0), (u1, v1)), ...]; ``width``/``height`` = that image's pixel
    size, for real angles) - classifies each as roughly vertical or
    horizontal and uses every orientation that has exactly 2 guides (a
    lone guide is ignored): 2 vertical guides solve perspective_v, 2
    horizontal ones perspective_h (both together when both pairs exist,
    by alternating 1D searches since the 2 coefficients interact a little),
    each making its pair parallel once mapped through the real correction;
    every other coefficient is kept as-is. Then the straighten angle making
    them truly vertical/horizontal (the average of both pairs' own
    estimates when both exist).

    Returns {"perspective_v"?: float, "perspective_h"?: float, "rotation":
    degrees} (only the solved coefficient(s) present) or None when no
    orientation has a pair. Coefficients are bounded to the sliders' own
    [-1, 1] range and the angle to Straighten's [-45, 45] - a correction
    stronger than that only gets as close as it can.
    """
    vertical = [line for line in lines if _guide_is_vertical(line, width, height)]
    horizontal = [line for line in lines if not _guide_is_vertical(line, width, height)]
    pairs = {}
    if len(vertical) == 2:
        pairs["perspective_v"] = (vertical, True)
    if len(horizontal) == 2:
        pairs["perspective_h"] = (horizontal, False)
    if not pairs:
        return None
    params = {"distortion": distortion, "perspective_v": perspective_v,
              "perspective_h": perspective_h, "anamorphic": anamorphic}

    def angles(pair, is_vertical, p):
        result = []
        for (u0, v0), (u1, v1) in pair:
            p0 = lens_correction_forward_point(2 * u0 - 1, 2 * v0 - 1, **p)
            p1 = lens_correction_forward_point(2 * u1 - 1, 2 * v1 - 1, **p)
            if p0 is None or p1 is None:
                return None
            dx = (p1[0] - p0[0]) * width / 2.0
            dy = (p1[1] - p0[1]) * height / 2.0
            if is_vertical:
                if dy < 0:
                    dx, dy = -dx, -dy
                # Angle away from vertical; also the straighten angle that
                # makes this line vertical (build_similarity_matrix's own
                # rotation convention, y-down image coordinates).
                result.append(np.degrees(np.arctan2(dx, dy)))
            else:
                if dx < 0:
                    dx, dy = -dx, -dy
                result.append(-np.degrees(np.arctan2(dy, dx)))
        return result

    def solve_one(key):
        pair, is_vertical = pairs[key]

        def cost(coef):
            a = angles(pair, is_vertical, dict(params, **{key: coef}))
            return float("inf") if a is None else (a[0] - a[1]) ** 2

        coef = _golden_minimize(cost)
        if np.isfinite(coef):
            params[key] = coef

    for _ in range(3 if len(pairs) == 2 else 1):
        for key in pairs:
            solve_one(key)

    estimates = []
    for key, (pair, is_vertical) in pairs.items():
        a = angles(pair, is_vertical, params)
        if a is None:
            return None
        estimates.append((a[0] + a[1]) / 2.0)
    result = {key: float(params[key]) for key in pairs}
    result["rotation"] = float(np.clip(np.mean(estimates), -45.0, 45.0))
    return result


def frame_point_to_display(
    u: float, v: float, width: int, height: int, rotation_deg: float, mirror_h: bool, mirror_v: bool,
    distortion: float = 0.0, perspective_v: float = 0.0, perspective_h: float = 0.0, anamorphic: float = 0.0,
) -> tuple[float, float] | None:
    """Where an uncorrected-frame point (normalized [0, 1]) lands once
    apply_straighten_mirror (Geometry, then straighten, then mirror) is
    applied with these parameters - also normalized [0, 1]. Used to draw
    guided-Perspective guides (kept in uncorrected coordinates) on top of
    the live-corrected preview. None if the lens inverse doesn't converge."""
    p = lens_correction_forward_point(2 * u - 1, 2 * v - 1, distortion, perspective_v, perspective_h, anamorphic)
    if p is None:
        return None
    px, py = (p[0] + 1) * width / 2.0, (p[1] + 1) * height / 2.0
    m = build_similarity_matrix(0.0, 0.0, 1.0, rotation_deg, (width / 2, height / 2), (width / 2, height / 2))
    dx = m[0, 0] * px + m[0, 1] * py + m[0, 2]
    dy = m[1, 0] * px + m[1, 1] * py + m[1, 2]
    du, dv = dx / width, dy / height
    return (1.0 - du if mirror_h else du), (1.0 - dv if mirror_v else dv)


def display_point_to_frame(
    u: float, v: float, width: int, height: int, rotation_deg: float, mirror_h: bool, mirror_v: bool,
    distortion: float = 0.0, perspective_v: float = 0.0, perspective_h: float = 0.0, anamorphic: float = 0.0,
) -> tuple[float, float]:
    """Exact inverse of frame_point_to_display (closed form: undo mirror,
    undo the straighten rotation, then the lens correction's own
    destination->source formula)."""
    du = 1.0 - u if mirror_h else u
    dv = 1.0 - v if mirror_v else v
    m = build_similarity_matrix(0.0, 0.0, 1.0, rotation_deg, (width / 2, height / 2), (width / 2, height / 2))
    inv = cv2.invertAffineTransform(m)
    dx, dy = du * width, dv * height
    px = inv[0, 0] * dx + inv[0, 1] * dy + inv[0, 2]
    py = inv[1, 0] * dx + inv[1, 1] * dy + inv[1, 2]
    xs, ys = _lens_correction_source_coords(
        2 * px / width - 1, 2 * py / height - 1, distortion, perspective_v, perspective_h, anamorphic)
    return float((xs + 1) / 2), float((ys + 1) / 2)


def apply_lens_correction(
    image: np.ndarray, distortion: float, perspective_v: float, perspective_h: float, anamorphic: float,
) -> np.ndarray:
    """Per-channel lens correction - radial (round) distortion, vertical/
    horizontal perspective (keystone), and anamorphic squeeze/stretch - all
    4 plain [-1, 1] coefficients (0 = no effect either way), applied as one
    combined per-pixel remap so a channel with more than one of these set
    only gets resampled once, not once per effect.

    Order (destination/corrected coordinates -> source/original coordinates,
    since that's what cv2.remap needs):
    1. Perspective: divides one axis by a factor that varies linearly along
       the other - a first-order approximation of a true projective
       (keystone) transform. Good enough at the small correction magnitudes
       this tool is meant for (fine alignment, not architectural correction)
       and lets this stay one coherent per-pixel formula instead of a
       separate cv2.warpPerspective pass.
    2. Radial distortion: a single-coefficient (k1-style) Brown-Conrady-like
       model, `factor = 1 + k * r^2` about the image's own center - positive
       and negative push the image in opposite directions (which one reads
       as "barrel" vs "pincushion" is not load-bearing here, this is a
       generic correction slider, not a real lens-profile undistort).
    3. Anamorphic: a flat horizontal-axis scale, applied last since it's
       independent of position (unlike the other two, which vary by pixel).

    Returns ``image`` unchanged (same object) when all 4 are exactly 0 - the
    overwhelmingly common case (most photos need none of this), so it costs
    nothing when unused.
    """
    if distortion == 0.0 and perspective_v == 0.0 and perspective_h == 0.0 and anamorphic == 0.0:
        return image
    h, w = image.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    xn = (xs - (w - 1) / 2.0) / (w / 2.0)
    yn = (ys - (h - 1) / 2.0) / (h / 2.0)
    xd, yd = _lens_correction_source_coords(xn, yn, distortion, perspective_v, perspective_h, anamorphic)
    map_x = xd * (w / 2.0) + (w - 1) / 2.0
    map_y = yd * (h / 2.0) + (h - 1) / 2.0
    return cv2.remap(
        image, map_x, map_y, interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0.0,
    )


# How far one "Stretch on Canvas" pin's influence reaches, as a fraction of
# the *reference canvas*'s own [0, 1] normalized space (both axes treated
# the same way apply_lens_correction's own radial term already does, i.e.
# not corrected for a non-square aspect ratio - same "good enough, one
# coherent formula" tradeoff). Tunable "feel" constant, same convention as
# _DISTORTION_STRENGTH/_PERSPECTIVE_STRENGTH/_ANAMORPHIC_STRENGTH above.
_STRETCH_FALLOFF_RADIUS = 0.35


def _stretch_falloff(dist):
    """Smooth, compactly-supported falloff kernel (Wendland-C2-like): 1.0 at
    dist=0, decaying smoothly to exactly 0.0 at dist >= _STRETCH_FALLOFF_RADIUS.
    Shared by apply_stretch_warp (numpy arrays) and warp_stretch_point (a
    single float) so the 2 stay visually consistent with each other."""
    t = np.clip(1.0 - (dist / _STRETCH_FALLOFF_RADIUS) ** 2, 0.0, 1.0)
    return t * t


def apply_stretch_warp(image: np.ndarray, pins: list[tuple[float, float, float, float]]) -> np.ndarray:
    """"Stretch on Canvas" - a localized "pin and drag" deformation: each pin
    is (anchor_u, anchor_v, delta_u, delta_v), all normalized to this image's
    own [0, 1] width/height, recording one completed canvas drag - the point
    the user clicked (anchor) dragged to where they released (anchor + delta).
    Unlike apply_lens_correction's 4 uniform coefficients (one same correction
    everywhere), this is deliberately *local* - the stretch takes effect from
    the clicked point - so a precise small adjustment in one area doesn't
    disturb the rest of the image.

    Approximate inverse-distance-weighted (RBF-style) deformation, the same
    "one coherent per-pixel formula, not a true mesh/FEM solve" tradeoff
    apply_lens_correction's own perspective term already makes: for each
    OUTPUT pixel, every pin contributes _stretch_falloff(distance to that
    pin's own *destination*, anchor+delta) of that pin's delta, pulled
    *backward* (since this builds the inverse/source-sampling map cv2.remap
    needs) - multiple pins simply add, each one independent of the others,
    matching "drag a new point to refine, without needing to touch earlier
    ones."

    Applied *after* warp_to_canvas in both compose_rgb_from_channels and
    _warp_and_tone (main_window.py's own Solo-preview path) - i.e. already
    in the same reference/canvas coordinate space the pins themselves were
    recorded in, so no extra coordinate transform is needed here.

    Returns ``image`` unchanged (same object) when pins is empty - the
    overwhelmingly common case."""
    if not pins:
        return image
    h, w = image.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    xn = xs / max(1, w - 1)
    yn = ys / max(1, h - 1)

    offset_u = np.zeros((h, w), dtype=np.float32)
    offset_v = np.zeros((h, w), dtype=np.float32)
    for anchor_u, anchor_v, delta_u, delta_v in pins:
        dest_u, dest_v = anchor_u + delta_u, anchor_v + delta_v
        dist = np.hypot(xn - dest_u, yn - dest_v)
        weight = _stretch_falloff(dist)
        offset_u -= weight * delta_u
        offset_v -= weight * delta_v

    map_x = (xn + offset_u) * (w - 1)
    map_y = (yn + offset_v) * (h - 1)
    return cv2.remap(
        image, map_x, map_y, interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0.0,
    )


def warp_stretch_point(
    u: float, v: float, pins: list[tuple[float, float, float, float]],
) -> tuple[float, float]:
    """Forward counterpart to apply_stretch_warp, for a single point rather
    than a full image - used by CanvasWidget's own live reference-grid
    overlay (widgets/canvas_widget.py) to visualize the deformation as it's
    being dragged, not by the actual image pipeline. An approximate forward
    analogue of the inverse-weighted remap above (weighted by distance to
    each pin's own *anchor* instead of its destination, and added instead
    of subtracted) - good enough for a visual guide, not claimed to be the
    exact mathematical inverse of apply_stretch_warp."""
    du = dv = 0.0
    for anchor_u, anchor_v, delta_u, delta_v in pins:
        dist = ((u - anchor_u) ** 2 + (v - anchor_v) ** 2) ** 0.5
        t = max(0.0, min(1.0, 1.0 - (dist / _STRETCH_FALLOFF_RADIUS) ** 2))
        weight = t * t
        du += weight * delta_u
        dv += weight * delta_v
    return u + du, v + dv


def warp_to_canvas(image: np.ndarray, matrix: np.ndarray, canvas_size: tuple[int, int]) -> np.ndarray:
    """canvas_size is (width, height)."""
    return cv2.warpAffine(
        image, matrix, canvas_size,
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0.0,
    )


def apply_invert(image: np.ndarray, invert: bool) -> np.ndarray:
    """Invert tones for a raw negative scan, before the tone curve is applied."""
    return (1.0 - image) if invert else image


def apply_film_base_correction(
    image: np.ndarray, film_base: Optional[dict], channel: Optional[str] = None,
) -> np.ndarray:
    """Normalizes a raw scan against a sampled film-base reference, applied at
    load time - before invert, since invert (1 - x) does not preserve a
    multiplicative per-channel bias linearly (a fixed base/mask tint, like
    color negative's orange mask, becomes tone-dependent after inversion rather
    than a uniform cast). ``channel`` ("R"/"G"/"B") picks one key out of
    ``film_base`` to correct a single-channel grayscale ``image`` (one
    trichrome ChannelLayer's own raw density); leave it ``None`` to correct a
    full color ``image`` (Normal mode), where each of its 3 channels is
    normalized against its own matching key. A no-op whenever ``film_base`` is
    falsy or a needed key is missing/non-positive (an unaffected axis stays
    exactly as loaded, never zeroed out)."""
    if not film_base:
        return image
    if channel is not None:
        base_value = film_base.get(channel)
        if not base_value or base_value <= 1e-6:
            return image
        return np.clip(image / base_value, 0.0, 1.0)
    r, g, b = film_base.get("R"), film_base.get("G"), film_base.get("B")
    if not (r and g and b and r > 1e-6 and g > 1e-6 and b > 1e-6):
        return image
    out = image.copy()
    out[..., 0] = np.clip(out[..., 0] / r, 0.0, 1.0)
    out[..., 1] = np.clip(out[..., 1] / g, 0.0, 1.0)
    out[..., 2] = np.clip(out[..., 2] / b, 0.0, 1.0)
    return out


def apply_zone_adjustment(image: np.ndarray, shadows: float, highlights: float) -> np.ndarray:
    """Brighten/darken shadows and highlights independently, Lightroom-style.

    Positive ``shadows``/``highlights`` lighten that tonal region, negative
    darkens it; each fades out smoothly toward the opposite end of the range
    so the two controls stay mostly independent.
    """
    if abs(shadows) < 1e-6 and abs(highlights) < 1e-6:
        return image
    shadow_mask = np.clip(1.0 - 2.0 * image, 0.0, 1.0) ** 2
    highlight_mask = np.clip(2.0 * image - 1.0, 0.0, 1.0) ** 2
    return image + 0.4 * shadows * shadow_mask + 0.4 * highlights * highlight_mask


def apply_tone_curve(
    image: np.ndarray, black_point: float, white_point: float,
    gamma: float, exposure: float, brightness: float, contrast: float,
    shadows: float = 0.0, highlights: float = 0.0,
) -> np.ndarray:
    """Apply the tone curve.

    ``black_point``/``white_point`` follow the usual photo-editing convention
    (Lightroom's Blacks/Whites): positive values lighten (lift blacks / raise
    whites), negative values darken (crush blacks / reduce whites), 0 is a
    no-op. ``shadows``/``highlights`` behave the same way but act only on
    their respective tonal region (see ``apply_zone_adjustment``).

    ``exposure`` is in stops (EV) - a multiplicative gain (``2**exposure``)
    applied first, before anything else in this function, simulating a change
    in how much light was captured rather than an edit made to the result
    afterward (that's what ``brightness``, a simple additive offset applied at
    the very end, is for).
    """
    out = image.astype(np.float32)
    if exposure:
        out = out * (2.0 ** exposure)
    out = apply_zone_adjustment(out, shadows, highlights)

    threshold_black = -black_point
    threshold_white = 1.0 - white_point
    span = max(threshold_white - threshold_black, 1e-4)
    out = (out - threshold_black) / span
    out = np.clip(out, 0.0, 1.0)
    if gamma and gamma > 0:
        out = np.power(out, 1.0 / gamma)
    out = (out - 0.5) * contrast + 0.5 + brightness
    return np.clip(out, 0.0, 1.0)


def compose_rgb(r: np.ndarray, g: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.stack([r, g, b], axis=-1).astype(np.float32)


def apply_white_balance(rgb: np.ndarray, temperature: float, tint: float) -> np.ndarray:
    """Simple gain-based white balance. temperature/tint are in [-100, 100].

    Positive temperature warms the image (more red/yellow, less blue);
    positive tint pushes toward magenta, negative toward green.
    """
    if abs(temperature) < 1e-6 and abs(tint) < 1e-6:
        return rgb
    t = temperature / 100.0
    m = tint / 100.0
    r_gain = 1.0 + 0.35 * t + 0.15 * m
    g_gain = 1.0 - 0.15 * m
    b_gain = 1.0 - 0.35 * t + 0.15 * m
    out = rgb.copy()
    out[..., 0] *= r_gain
    out[..., 1] *= g_gain
    out[..., 2] *= b_gain
    return out


def solve_white_balance(r: float, g: float, b: float) -> Optional[tuple[float, float]]:
    """Inverse of apply_white_balance's gain model: given a pixel that
    should become neutral gray, solves for the (temperature, tint) that
    neutralizes it - the math behind the white balance eyedropper.

    r_gain = 1 + 0.35t + 0.15m, g_gain = 1 - 0.15m, b_gain = 1 - 0.35t + 0.15m
    (t, m being temperature/tint in [-1, 1]). Requiring R*r_gain = G*g_gain
    and B*b_gain = G*g_gain gives 2 linear equations in (t, m), solved here
    via Cramer's rule. Returns None if the pixel is too dark/degenerate
    (near-black, or a channel combination with no solution) to solve
    reliably - the caller should leave temperature/tint untouched then.
    """
    if r < 1e-3 and g < 1e-3 and b < 1e-3:
        return None
    a1, b1, c1 = 0.35 * r, 0.15 * (r + g), g - r
    a2, b2, c2 = -0.35 * b, 0.15 * (b + g), g - b
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-9:
        return None
    t = (c1 * b2 - b1 * c2) / det
    m = (a1 * c2 - a2 * c1) / det
    t = max(-1.0, min(1.0, t))
    m = max(-1.0, min(1.0, m))
    return t * 100.0, m * 100.0


_IDENTITY_CURVE = ((0.0, 0.0), (1.0, 1.0))


def evaluate_curve_lut(points, size: int = 256) -> np.ndarray:
    """Builds a `size`-entry lookup table (x sampled evenly over [0,1]) from
    a tone curve's sparse control points, via a monotone cubic Hermite
    spline (Fritsch-Carlson correction) - the same smooth, overshoot-free
    curve shape a classic Photoshop/Lightroom Curves tool produces, as
    opposed to a plain piecewise-linear join between points. `points` need
    not be pre-sorted; fewer than 2 points degenerates to the identity."""
    pts = sorted(points, key=lambda p: p[0])
    xs = np.array([p[0] for p in pts], dtype=np.float64)
    ys = np.array([p[1] for p in pts], dtype=np.float64)
    n = len(xs)
    sample_x = np.linspace(0.0, 1.0, size)
    if n < 2:
        return np.clip(sample_x, 0.0, 1.0).astype(np.float32)

    dx = np.diff(xs)
    dx = np.where(np.abs(dx) < 1e-9, 1e-9, dx)
    delta = np.diff(ys) / dx  # secant slope of each interval, length n-1

    m = np.empty(n, dtype=np.float64)
    if n == 2:
        m[0] = m[1] = delta[0]
    else:
        m[0] = delta[0]
        m[-1] = delta[-1]
        m[1:-1] = (delta[:-1] + delta[1:]) / 2.0
        # Flatten the tangent at any interior point where the two adjacent
        # secants disagree in sign (a local min/max at that control point) -
        # part of the standard Fritsch-Carlson monotonicity guarantee.
        flat = delta[:-1] * delta[1:] <= 0.0
        m[1:-1][flat] = 0.0
    for k in range(n - 1):
        if delta[k] == 0.0:
            m[k] = 0.0
            m[k + 1] = 0.0

    # Rescale each interval's pair of tangents so the interpolated segment
    # can't overshoot past its own endpoints - what actually prevents the
    # classic cubic-spline ringing near a sharply-dragged point.
    for k in range(n - 1):
        d = delta[k]
        if d == 0.0:
            continue
        alpha, beta = m[k] / d, m[k + 1] / d
        s = alpha * alpha + beta * beta
        if s > 9.0:
            tau = 3.0 / np.sqrt(s)
            m[k] = tau * alpha * d
            m[k + 1] = tau * beta * d

    idx = np.clip(np.searchsorted(xs, sample_x, side="right") - 1, 0, n - 2)
    x0, x1 = xs[idx], xs[idx + 1]
    y0, y1 = ys[idx], ys[idx + 1]
    m0, m1 = m[idx], m[idx + 1]
    seg = np.where(np.abs(x1 - x0) < 1e-9, 1e-9, x1 - x0)
    t = (sample_x - x0) / seg
    t2, t3 = t * t, t * t * t
    h00 = 2 * t3 - 3 * t2 + 1
    h10 = t3 - 2 * t2 + t
    h01 = -2 * t3 + 3 * t2
    h11 = t3 - t2
    sample_y = h00 * y0 + h10 * seg * m0 + h01 * y1 + h11 * seg * m1
    # Flat outside the control points' own x-range, not spline extrapolation -
    # the endpoints can be dragged inward, and a real Curves tool clips input
    # tones beyond a moved endpoint to a constant output (the classic "black
    # point"/"white point" behavior), rather than extending the curve's shape
    # unpredictably past its own defined range.
    sample_y = np.where(sample_x <= xs[0], ys[0], sample_y)
    sample_y = np.where(sample_x >= xs[-1], ys[-1], sample_y)
    return np.clip(sample_y, 0.0, 1.0).astype(np.float32)


def _is_identity_curve(points) -> bool:
    return len(points) == 2 and tuple(points[0]) == _IDENTITY_CURVE[0] and tuple(points[1]) == _IDENTITY_CURVE[1]


def apply_curve(image: np.ndarray, points) -> np.ndarray:
    """Remaps `image` (float array, any shape, values roughly in [0,1])
    through a single tone curve defined by sparse control points -
    identical mapping applied to every element, so for an RGB array this
    is a master/luminosity curve (see apply_curves for independent R/G/B
    curves). A no-op for the default identity curve (skipped entirely
    rather than running a LUT pass that would just return the input
    unchanged)."""
    if _is_identity_curve(points):
        return image
    lut = evaluate_curve_lut(points)
    lut_x = np.linspace(0.0, 1.0, len(lut))
    return np.interp(np.clip(image, 0.0, 1.0), lut_x, lut).astype(np.float32)


def apply_curves(rgb: np.ndarray, curves: dict) -> np.ndarray:
    """Applies a full Curves correction (the "Y" master curve, then each of
    "R"/"G"/"B"'s own independent curve on top) to a composed RGB image -
    the same channel-selector composition a classic Photoshop Curves
    dialog uses. `curves` maps a subset of "Y"/"R"/"G"/"B" to a points
    list; a missing key means identity for that channel. Never mutates
    `rgb` in place, and only rebuilds the array via np.stack if at least
    one channel curve actually did something (apply_curve's own identity
    fast path means an all-identity `curves` dict is nearly free)."""
    out = apply_curve(rgb, curves.get("Y", _IDENTITY_CURVE))
    channels = [out[..., i] for i in range(3)]
    changed = False
    for i, ch in enumerate(("R", "G", "B")):
        remapped = apply_curve(channels[i], curves.get(ch, _IDENTITY_CURVE))
        if remapped is not channels[i]:
            channels[i] = remapped
            changed = True
    return np.stack(channels, axis=-1) if changed else out


_LUMA_WEIGHTS = (0.299, 0.587, 0.114)


def apply_black_white(rgb: np.ndarray) -> np.ndarray:
    """Real luminance-weighted grayscale conversion (ITU-R BT.601 weights - the
    same _LUMA_WEIGHTS compute_channel_histograms' own Y channel, and PIL's
    .convert("L") in load_grayscale, already use elsewhere in this app),
    replacing every pixel with R=G=B=Y. This replaced the original
    implementation of ColorPanel's Black & White toggle, which only zeroed
    saturation in HSV space - that only grays a pixel to HSV's V (max(R,G,B)),
    not a perceptually-weighted brightness, so e.g. a saturated red and a
    saturated blue at the same V read as the same gray even though a real B&W
    conversion (and the human eye) would see the blue as noticeably darker. See
    ColorPanel.black_white_button / MainWindow.on_black_white_toggled."""
    luma = np.dot(rgb[..., :3], _LUMA_WEIGHTS).astype(np.float32)
    return np.stack([luma, luma, luma], axis=-1)


def apply_global_correction_before_curves(
    rgb: np.ndarray, black_point: float, white_point: float, gamma: float, exposure: float,
    brightness: float, contrast: float, shadows: float, highlights: float,
    saturation: float, temperature: float, tint: float,
) -> np.ndarray:
    """Everything apply_global_correction does except the final Curves step -
    factored out so a caller can get the exact "input" image the Curves tool's
    own reference-histogram overlay needs: the pipeline result right before
    curves apply, which by definition never changes while the user is only
    editing the curve. See MainWindow. recompute_preview's
    update_curve_reference parameter."""
    out = apply_tone_curve(
        rgb, black_point, white_point, gamma, exposure, brightness, contrast, shadows, highlights)
    out = apply_white_balance(out, temperature, tint)

    if abs(saturation - 1.0) > 1e-6:
        out = np.clip(out, 0.0, 1.0)
        hsv = cv2.cvtColor(out, cv2.COLOR_RGB2HSV)
        hsv[..., 1] = np.clip(hsv[..., 1] * saturation, 0.0, 1.0)
        out = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)

    return np.clip(out, 0.0, 1.0)


def apply_global_correction(
    rgb: np.ndarray, black_point: float, white_point: float, gamma: float, exposure: float,
    brightness: float, contrast: float, shadows: float, highlights: float,
    saturation: float, temperature: float, tint: float, curves: dict | None = None,
    black_white: bool = False,
) -> np.ndarray:
    out = apply_global_correction_before_curves(
        rgb, black_point, white_point, gamma, exposure, brightness, contrast, shadows, highlights,
        saturation, temperature, tint)
    # The tone curves are the final creative shaping step, applied last -
    # after saturation/white balance, on the fully color-corrected image.
    out = apply_curves(out, curves or {})
    # Black & White (ColorPanel's toggle) is the true final step - a real
    # grayscale conversion of the finished, fully-corrected image, not a
    # correction of its own.
    if black_white:
        out = apply_black_white(out)
    return np.clip(out, 0.0, 1.0)


def compute_channel_histograms(rgb_uint8: np.ndarray, valid_mask: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """256-bin histogram counts (float64) for Y (luma-weighted)/R/G/B from
    an already-composited uint8 RGB image - shared by HistogramWidget and
    the Curves tool's own reference-histogram overlay so both compute
    channel data identically. ``valid_mask`` (same H×W, truthy where a
    pixel is real photographed content) excludes anything False, same
    convention as warp_coverage_mask/compose_coverage_mask - a pixel a
    misaligned channel or Straighten padded with a constant border fill
    shouldn't read as real clipping."""
    # round(), not a plain truncating cast: 0.299+0.587+0.114 isn't exactly
    # 1.0 in floating point, so for R=G=B (e.g. a Solo preview) a plain
    # astype(uint8) truncates ~25% of gray levels down by one, smearing the
    # Y curve a bin off from R/G/B where they should exactly coincide.
    luma = np.round(np.dot(rgb_uint8[..., :3], _LUMA_WEIGHTS)).astype(np.uint8)
    channel_data = {"Y": luma, "R": rgb_uint8[:, :, 0], "G": rgb_uint8[:, :, 1], "B": rgb_uint8[:, :, 2]}
    if valid_mask is not None:
        valid_mask = valid_mask.astype(bool)
        channel_data = {ch: data[valid_mask] for ch, data in channel_data.items()}
    return {
        ch: np.histogram(data, bins=256, range=(0, 255))[0].astype(np.float64)
        for ch, data in channel_data.items()
    }


def compose_rgb_from_channels(
    images, geo_params, tone_params, ref_index: int, visible: tuple[bool, bool, bool] = (True, True, True),
) -> np.ndarray:
    """Warp + per-channel tone curve + stack into RGB - everything
    compose_trichrome does before the *global* correction stage. Factored
    out so the white-balance eyedropper can sample a pixel from the same
    intermediate compose_trichrome itself builds (see
    compose_pre_white_balance_rgb), instead of duplicating this loop.

    ``visible`` is "Display Layer" (main_window.py) - a view-only toggle,
    separate from Solo: a hidden channel contributes pure black to the
    stack (so 2 can be shown together, in color) rather than the whole
    preview collapsing to one channel in grayscale. Still fully warped/
    toned before being zeroed, so canvas_size/ref_index's own shape
    requirement is unaffected regardless of which channel is hidden."""
    ref_h, ref_w = images[ref_index].shape[:2]
    canvas_size = (ref_w, ref_h)

    channel_arrays = [None, None, None]
    for i in range(3):
        img = images[i]
        if img is None:
            channel_arrays[i] = np.zeros((ref_h, ref_w), dtype=np.float32)
            continue
        h, w = img.shape[:2]
        (dx, dy, scale, rotation, distortion, perspective_v, perspective_h, anamorphic,
         stretch_pins) = geo_params[i]
        img = apply_lens_correction(img, distortion, perspective_v, perspective_h, anamorphic)
        matrix = build_similarity_matrix(
            dx, dy, scale, rotation, src_center=(w / 2, h / 2), dst_center=(ref_w / 2, ref_h / 2))
        warped = warp_to_canvas(img, matrix, canvas_size)
        warped = apply_stretch_warp(warped, stretch_pins)
        black, white, gamma, exposure, brightness, contrast, shadows, highlights, invert = tone_params[i]
        warped = apply_invert(warped, invert)
        channel_arrays[i] = apply_tone_curve(
            warped, black, white, gamma, exposure, brightness, contrast, shadows, highlights)

    for i in range(3):
        if not visible[i]:
            channel_arrays[i] = np.zeros_like(channel_arrays[i])

    return compose_rgb(*channel_arrays)


def warp_coverage_mask(
    shape: tuple[int, int], geo_params: tuple, ref_size: tuple[int, int],
) -> np.ndarray:
    """1.0 where warping a channel of ``shape`` with ``geo_params`` onto a
    ``ref_size`` canvas actually sampled real source pixels, 0.0 where the
    transform (alignment offset, the Straighten rotation, a distortion/
    perspective/anamorphic correction, or Stretch-on-Canvas pins - all can
    pull in empty space at the edges/corners same as an alignment offset
    can) left only black border fill - so callers (the histogram) can
    exclude that fill from clipping stats instead of flagging a thin,
    often near-invisible misalignment border as real over/underexposure."""
    h, w = shape
    ref_w, ref_h = ref_size
    dx, dy, scale, rotation, distortion, perspective_v, perspective_h, anamorphic, stretch_pins = geo_params
    ones = apply_lens_correction(
        np.ones((h, w), dtype=np.float32), distortion, perspective_v, perspective_h, anamorphic)
    matrix = build_similarity_matrix(
        dx, dy, scale, rotation, src_center=(w / 2, h / 2), dst_center=(ref_w / 2, ref_h / 2))
    warped = warp_to_canvas(ones, matrix, (ref_w, ref_h))
    warped = apply_stretch_warp(warped, stretch_pins)
    return (warped > 0.999).astype(np.float32)


def compose_coverage_mask(images, geo_params, ref_index: int) -> np.ndarray:
    """AND of every loaded channel's warp_coverage_mask, matching the shape
    compose_rgb_from_channels produces (before straighten/crop). A channel
    with no image doesn't exclude anything - it's genuinely absent, not a
    warp artifact, and compose_rgb_from_channels already renders it as real
    black, which the histogram should still flag as such."""
    ref_h, ref_w = images[ref_index].shape[:2]
    mask = np.ones((ref_h, ref_w), dtype=np.float32)
    for i in range(3):
        img = images[i]
        if img is None:
            continue
        mask *= warp_coverage_mask(img.shape[:2], geo_params[i], (ref_w, ref_h))
    return mask


def compose_pre_white_balance_rgb(images, geo_params, tone_params, ref_index: int, global_params) -> np.ndarray:
    """Everything compose_trichrome does up to (but not including) white
    balance/saturation - the color space apply_white_balance itself
    operates on, and so what the white-balance eyedropper needs to sample
    a pixel from for solve_white_balance to give a correct result. Takes
    the same ``global_params`` tuple as compose_trichrome for a matching
    call signature; the saturation/temperature/tint entries are unused."""
    rgb = compose_rgb_from_channels(images, geo_params, tone_params, ref_index)
    (gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
     _gsat, _gtemp, _gtint, _gcurves, _gbw) = global_params
    return apply_tone_curve(rgb, gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights)


def compose_trichrome(
    images, geo_params, tone_params, ref_index: int, global_params,
    visible: tuple[bool, bool, bool] = (True, True, True),
) -> np.ndarray:
    """Full pipeline shared by the live preview, single export and batch export.

    images: list of 3 grayscale float32 arrays (or None), ordered R, G, B.
    geo_params: list of 3 (dx, dy, scale, rotation_deg, distortion,
        perspective_v, perspective_h, anamorphic) tuples - the first 4 in
        the same pixel scale as ``images`` and relative to
        ``images[ref_index]``; the last 4 are plain [-1, 1] lens-correction
        coefficients, see apply_lens_correction.
    tone_params: list of 3 (black, white, gamma, exposure, brightness,
        contrast, shadows, highlights, invert) tuples.
    global_params: (black, white, gamma, exposure, brightness, contrast,
        shadows, highlights, saturation, temperature, tint, curves,
        black_white) tuple - curves is a {"Y"/"R"/"G"/"B": points} dict,
        see apply_curves; black_white is ColorPanel's B&W toggle, see
        apply_black_white.
    visible: "Display Layer" per-channel show/hide (default all-visible,
        the only value export/thumbnail callers ever pass) - see
        compose_rgb_from_channels's own docstring.
    """
    rgb = compose_rgb_from_channels(images, geo_params, tone_params, ref_index, visible)
    (gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
     gsat, gtemp, gtint, gcurves, gbw) = global_params
    return apply_global_correction(
        rgb, gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
        gsat, gtemp, gtint, gcurves, gbw)


def compose_normal(image: np.ndarray, global_params) -> np.ndarray:
    """Full pipeline for a Normal-mode single photo (see MainWindow's Files
    block Normal/Trichrome toggle) - the loaded color image already IS the
    final composite, so unlike compose_trichrome there's no warp/recompose
    stage first; just the same global-correction stage applied on top,
    taking the identical global_params tuple shape."""
    (gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
     gsat, gtemp, gtint, gcurves, gbw) = global_params
    return apply_global_correction(
        image, gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
        gsat, gtemp, gtint, gcurves, gbw)


def apply_straighten_mirror(
    rgb: np.ndarray, rotation_deg: float, mirror_h: bool, mirror_v: bool,
    distortion: float = 0.0, perspective_v: float = 0.0,
    perspective_h: float = 0.0, anamorphic: float = 0.0,
) -> np.ndarray:
    """Geometry (the Crop block's own whole-image lens correction, see
    CropSettings.distortion), then rotate about center ("straighten"),
    then flip left/right and/or top/bottom - the part of the crop pipeline
    that's always visible (including while the Crop tool itself is open),
    as opposed to the final crop rect (see apply_crop_rect)."""
    img = rgb
    img = apply_lens_correction(img, distortion, perspective_v, perspective_h, anamorphic)
    if rotation_deg:
        h, w = img.shape[:2]
        matrix = build_similarity_matrix(
            0.0, 0.0, 1.0, rotation_deg, src_center=(w / 2, h / 2), dst_center=(w / 2, h / 2))
        img = warp_to_canvas(img, matrix, (w, h))
    if mirror_h:
        img = img[:, ::-1]
    if mirror_v:
        img = img[::-1, :]
    return np.ascontiguousarray(img)


def apply_crop_rect(img: np.ndarray, x: float, y: float, width: float, height: float) -> np.ndarray:
    """Crops to the (x, y, width, height) rect - normalized [0,1]. Kept
    separate from apply_straighten_mirror so the Crop tool's own preview can
    show straighten/mirror live while still showing the *full* frame to
    crop against, instead of a shrinking crop-of-a-crop."""
    if (x, y, width, height) == (0.0, 0.0, 1.0, 1.0):
        return img
    h, w = img.shape[:2]
    x0 = max(0, min(w, round(x * w)))
    y0 = max(0, min(h, round(y * h)))
    x1 = max(x0, min(w, round((x + width) * w)))
    y1 = max(y0, min(h, round((y + height) * h)))
    if x1 > x0 and y1 > y0:
        img = img[y0:y1, x0:x1]
    return img


def apply_crop(
    rgb: np.ndarray, rotation_deg: float, mirror_h: bool, mirror_v: bool,
    x: float, y: float, width: float, height: float, **geometry,
) -> np.ndarray:
    """Straighten, mirror, then crop - the full pipeline, in the same order
    the Crop panel's controls list them in. Shared by export (which always
    wants the final result) and the live preview outside the Crop tool
    itself (see apply_straighten_mirror/apply_crop_rect for why the preview
    splits this in two while the Crop tool is open)."""
    img = apply_straighten_mirror(rgb, rotation_deg, mirror_h, mirror_v, **geometry)
    return apply_crop_rect(img, x, y, width, height)


def to_uint8(image: np.ndarray) -> np.ndarray:
    return np.clip(np.round(image * 255.0), 0, 255).astype(np.uint8)


def to_uint16(image: np.ndarray) -> np.ndarray:
    return np.clip(np.round(image * 65535.0), 0, 65535).astype(np.uint16)


def save_image(path: str, rgb_float: np.ndarray, bit_depth: int = 8) -> None:
    if bit_depth == 16:
        arr16 = to_uint16(rgb_float)
        bgr = cv2.cvtColor(arr16, cv2.COLOR_RGB2BGR)
        cv2.imwrite(path, bgr)
    else:
        arr8 = to_uint8(rgb_float)
        Image.fromarray(arr8, mode="RGB").save(path)
