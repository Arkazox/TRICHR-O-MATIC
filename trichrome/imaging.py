"""Low level image processing: loading, geometric warp, tonal correction, compositing."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import numpy as np
import cv2
from PIL import Image

MAX_PREVIEW_DIM = 1400

_EXIF_DATETIME_ORIGINAL = 36867
_EXIF_DATETIME = 306


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


def warp_to_canvas(image: np.ndarray, matrix: np.ndarray, canvas_size: tuple[int, int]) -> np.ndarray:
    """canvas_size is (width, height)."""
    return cv2.warpAffine(
        image, matrix, canvas_size,
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0.0,
    )


def apply_invert(image: np.ndarray, invert: bool) -> np.ndarray:
    """Invert tones for a raw negative scan, before the tone curve is applied."""
    return (1.0 - image) if invert else image


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
    applied first, before anything else in this function, simulating a
    change in how much light was captured rather than an edit made to the
    result afterward (that's what ``brightness``, a simple additive offset
    applied at the very end, is for - see the CLAUDE.md note on the
    difference this models).
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


def apply_global_correction(
    rgb: np.ndarray, black_point: float, white_point: float, gamma: float, exposure: float,
    brightness: float, contrast: float, shadows: float, highlights: float,
    saturation: float, temperature: float, tint: float,
) -> np.ndarray:
    out = apply_tone_curve(
        rgb, black_point, white_point, gamma, exposure, brightness, contrast, shadows, highlights)
    out = apply_white_balance(out, temperature, tint)

    if abs(saturation - 1.0) > 1e-6:
        out = np.clip(out, 0.0, 1.0)
        hsv = cv2.cvtColor(out, cv2.COLOR_RGB2HSV)
        hsv[..., 1] = np.clip(hsv[..., 1] * saturation, 0.0, 1.0)
        out = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)

    return np.clip(out, 0.0, 1.0)


def compose_rgb_from_channels(images, geo_params, tone_params, ref_index: int) -> np.ndarray:
    """Warp + per-channel tone curve + stack into RGB - everything
    compose_trichrome does before the *global* correction stage. Factored
    out so the white-balance eyedropper can sample a pixel from the same
    intermediate compose_trichrome itself builds (see
    compose_pre_white_balance_rgb), instead of duplicating this loop."""
    ref_h, ref_w = images[ref_index].shape[:2]
    canvas_size = (ref_w, ref_h)

    channel_arrays = [None, None, None]
    for i in range(3):
        img = images[i]
        if img is None:
            channel_arrays[i] = np.zeros((ref_h, ref_w), dtype=np.float32)
            continue
        h, w = img.shape[:2]
        dx, dy, scale, rotation = geo_params[i]
        matrix = build_similarity_matrix(
            dx, dy, scale, rotation, src_center=(w / 2, h / 2), dst_center=(ref_w / 2, ref_h / 2))
        warped = warp_to_canvas(img, matrix, canvas_size)
        black, white, gamma, exposure, brightness, contrast, shadows, highlights, invert = tone_params[i]
        warped = apply_invert(warped, invert)
        channel_arrays[i] = apply_tone_curve(
            warped, black, white, gamma, exposure, brightness, contrast, shadows, highlights)

    return compose_rgb(*channel_arrays)


def warp_coverage_mask(
    shape: tuple[int, int], geo_params: tuple[float, float, float, float], ref_size: tuple[int, int],
) -> np.ndarray:
    """1.0 where warping a channel of ``shape`` with ``geo_params`` onto a
    ``ref_size`` canvas actually sampled real source pixels, 0.0 where the
    transform (alignment offset, or the Straighten rotation) left only
    warpAffine's constant black border fill - so callers (the histogram)
    can exclude that fill from clipping stats instead of flagging a thin,
    often near-invisible misalignment border as real over/underexposure."""
    h, w = shape
    ref_w, ref_h = ref_size
    dx, dy, scale, rotation = geo_params
    matrix = build_similarity_matrix(
        dx, dy, scale, rotation, src_center=(w / 2, h / 2), dst_center=(ref_w / 2, ref_h / 2))
    ones = np.ones((h, w), dtype=np.float32)
    warped = warp_to_canvas(ones, matrix, (ref_w, ref_h))
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
     _gsat, _gtemp, _gtint) = global_params
    return apply_tone_curve(rgb, gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights)


def compose_trichrome(images, geo_params, tone_params, ref_index: int, global_params) -> np.ndarray:
    """Full pipeline shared by the live preview, single export and batch export.

    images: list of 3 grayscale float32 arrays (or None), ordered R, G, B.
    geo_params: list of 3 (dx, dy, scale, rotation_deg) tuples, in the same
        pixel scale as ``images`` and relative to ``images[ref_index]``.
    tone_params: list of 3 (black, white, gamma, exposure, brightness,
        contrast, shadows, highlights, invert) tuples.
    global_params: (black, white, gamma, exposure, brightness, contrast,
        shadows, highlights, saturation, temperature, tint) tuple.
    """
    rgb = compose_rgb_from_channels(images, geo_params, tone_params, ref_index)
    (gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
     gsat, gtemp, gtint) = global_params
    return apply_global_correction(
        rgb, gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights, gsat, gtemp, gtint)


def apply_straighten_mirror(rgb: np.ndarray, rotation_deg: float, mirror_h: bool, mirror_v: bool) -> np.ndarray:
    """Rotate about center ("straighten"), then flip left/right and/or
    top/bottom - the part of the crop pipeline that's always visible
    (including while the Crop tool itself is open), as opposed to the
    final crop rect (see apply_crop_rect)."""
    img = rgb
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
    x: float, y: float, width: float, height: float,
) -> np.ndarray:
    """Straighten, mirror, then crop - the full pipeline, in the same order
    the Crop panel's controls list them in. Shared by export (which always
    wants the final result) and the live preview outside the Crop tool
    itself (see apply_straighten_mirror/apply_crop_rect for why the preview
    splits this in two while the Crop tool is open)."""
    img = apply_straighten_mirror(rgb, rotation_deg, mirror_h, mirror_v)
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
