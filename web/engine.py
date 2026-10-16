"""Bridge between the web page and Trichr-o-matic's processing code.

Runs inside Pyodide (see worker.js). All image processing is done by
trichrome.imaging and trichrome.alignment, the same modules the desktop app
uses, unchanged. This module only keeps the loaded channels in memory and
turns the page's JSON state into the parameter tuples main_window.py builds
for the same calls.
"""
from __future__ import annotations

import gc
import io
import json
import time

import cv2
import numpy as np
from PIL import Image

from trichrome import alignment, imaging

CHANNEL_NAMES = ("R", "G", "B")

# Longest side of the arrays the live preview is composed from. Larger than
# the desktop's imaging.MAX_PREVIEW_DIM (1400), since the web version has no
# HQ Preview; Auto Align still works at MAX_PREVIEW_DIM (see auto_align).
PREVIEW_MAX_DIM = 1920

# The web version has no Light/Color panels: the global stage of
# compose_trichrome runs with GlobalCorrection's neutral values, except for
# the Curves, which come from the page.
_NEUTRAL_GLOBAL = (0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, {}, False)
_IDENTITY_CURVE = ((0.0, 0.0), (1.0, 1.0))

# One entry per channel: {"path", "preview", "scale"}. Full-resolution
# arrays are never kept: export reloads them from the file, like
# MainWindow._full_res_image does for batch-imported photos.
_channels: list[dict | None] = [None, None, None]
# Bumped whenever _channels changes, so _curve_base can tell a cached
# pre-curve image is still the current one.
_generation = 0

# The last full render's image right before the curves (framed and cropped),
# for a render where only the curves changed: see render. Keys: "key" (the
# state without its curves, plus _generation), "pre_curve" (float RGB, dropped
# once "index" is built), "index" (imaging.curves_preview_index), "valid",
# "solo", "frame_w", "frame_h", "hist_pre".
_curve_base: dict | None = None


def _turned(image: np.ndarray, quarter_turns: int) -> np.ndarray:
    """The rotate-left/right buttons: the source pixels turned by 90° steps
    (np.rot90's direction, counterclockwise), as ChannelLayer.rotate_quarter
    does on the desktop."""
    if quarter_turns % 4 == 0:
        return image
    return np.ascontiguousarray(np.rot90(image, quarter_turns))


def _previews(state: dict) -> list:
    k = state.get("quarter_turns", 0)
    return [_turned(entry["preview"], k) if entry else None for entry in _channels]


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def _load_full(index: int, path: str, color_trichrome: bool) -> np.ndarray:
    channel = CHANNEL_NAMES[index] if color_trichrome else None
    return imaging.load_grayscale(path, channel=channel)


def load_channel(index: int, path: str, color_trichrome: bool) -> dict:
    start = time.perf_counter()
    full = _load_full(index, path, color_trichrome)
    height, width = full.shape[:2]
    preview, scale = imaging.make_preview(full, PREVIEW_MAX_DIM)
    del full
    gc.collect()
    global _generation
    _channels[index] = {"path": path, "preview": preview, "scale": scale}
    _generation += 1
    return {"width": width, "height": height, "ms": _ms(start)}


def reload_all(color_trichrome: bool) -> dict:
    """Classic and Color Trichrome decode the files differently, so a mode
    change reloads every channel (same as the desktop's Mode combo)."""
    start = time.perf_counter()
    for index, entry in enumerate(_channels):
        if entry is not None:
            load_channel(index, entry["path"], color_trichrome)
    return {"ms": _ms(start)}


def swap_channels(a: int, b: int, color_trichrome: bool) -> dict:
    """Moves photo ``a`` to slot ``b`` and back (the desktop's channel swap).
    In Color Trichrome each file gives the plane of the slot it sits in, so
    both are decoded again for their new slot."""
    start = time.perf_counter()
    global _generation
    _channels[a], _channels[b] = _channels[b], _channels[a]
    _generation += 1
    if color_trichrome:
        for index in (a, b):
            if _channels[index] is not None:
                load_channel(index, _channels[index]["path"], True)
    return {"ms": _ms(start)}


def clear_channel(index: int) -> None:
    global _generation
    _channels[index] = None
    _generation += 1
    gc.collect()


def _canvas_ref(ref: int) -> int | None:
    """The reference channel, or the first loaded one while the reference
    has no file yet (compose needs a loaded channel to size the canvas)."""
    if _channels[ref] is not None:
        return ref
    return next((i for i in range(3) if _channels[i] is not None), None)


def _geo_params(layer: dict, index: int, ref: int, full_res: bool) -> tuple:
    # The reference channel is locked: its position is always the identity,
    # as in MainWindow._full_res_params. The 4 lens coefficients are its own.
    if index == ref:
        dx, dy, scale, rotation = 0.0, 0.0, 1.0, 0.0
    elif full_res:
        ref_scale = _channels[ref]["scale"]
        dx = layer["dx"] / ref_scale
        dy = layer["dy"] / ref_scale
        scale = layer["scale"] * (_channels[index]["scale"] / ref_scale)
        rotation = layer["rotation"]
    else:
        dx, dy, scale, rotation = layer["dx"], layer["dy"], layer["scale"], layer["rotation"]
    # Stretch pins are normalized to the canvas, so they need no conversion
    # between preview and full resolution.
    pins = [tuple(pin) for pin in layer.get("stretch_pins", [])]
    return (dx, dy, scale, rotation, layer["distortion"], layer["perspective_v"],
            layer["perspective_h"], layer["anamorphic"], pins)


def _tone_params(layer: dict, negative: bool) -> tuple:
    # Negative inverts all 3 channels, as the desktop's toggle does.
    return (layer["black_point"], layer["white_point"], layer["gamma"], layer["exposure"],
            layer["brightness"], layer["contrast"], layer["shadows"], layer["highlights"], negative)


def _global_params(state: dict) -> tuple:
    curves = {ch: [tuple(p) for p in points] for ch, points in (state.get("curves") or {}).items()}
    return _NEUTRAL_GLOBAL[:11] + (curves, False)


def _geometry(crop: dict) -> dict:
    return {key: crop[key] for key in ("distortion", "perspective_v", "perspective_h", "anamorphic")}


def _frame_transform(img: np.ndarray, crop: dict) -> np.ndarray:
    return imaging.apply_straighten_mirror(
        img, crop["rotation"], crop["mirror_h"], crop["mirror_v"], **_geometry(crop))


def _curve_base_key(state: dict) -> str:
    rest = {key: value for key, value in state.items() if key != "curves"}
    return json.dumps(rest, sort_keys=True) + f"#{_generation}"


def _preview_result(rgb_u8: np.ndarray, valid: np.ndarray, base: dict, start: float) -> dict:
    hist = imaging.compute_channel_histograms(rgb_u8, valid)
    height, width = rgb_u8.shape[:2]
    rgba = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2RGBA)
    return {
        "rgba": rgba.tobytes(), "width": width, "height": height,
        "frame_w": base["frame_w"], "frame_h": base["frame_h"],
        "hist": {key: values.tolist() for key, values in hist.items()},
        "hist_pre": base["hist_pre"],
        "ms": _ms(start),
    }


def _render_curves_only(state: dict, start: float) -> dict:
    """A render where only the curves changed since the last full one (a
    curve drag): the cached pre-curve image mapped through lookup tables
    (imaging.curves_preview_luts, within one 8-bit level of apply_curves),
    as MainWindow._on_curve_recompute_tick does. Skips the warp, compose and
    framing that a full render repeats."""
    base = _curve_base
    if base["index"] is None:
        base["index"] = imaging.curves_preview_index(base.pop("pre_curve"))
    curves = _global_params(state)[11]
    if base["solo"]:
        # Solo Layer Preview takes only the master curve.
        curves = {"Y": curves.get("Y", _IDENTITY_CURVE)}
    rgb_u8 = imaging.apply_curves_preview(base["index"], imaging.curves_preview_luts(curves))
    return _preview_result(rgb_u8, base["valid"], base, start)


def render(state_json: str) -> dict | None:
    """The live preview: the 1400px arrays composed exactly like
    MainWindow.recompute_preview, plus the histogram and the frame size
    before cropping (the crop overlay works in that frame)."""
    global _curve_base
    start = time.perf_counter()
    state = json.loads(state_json)
    key = _curve_base_key(state)
    if _curve_base is not None and _curve_base["key"] == key:
        return _render_curves_only(state, start)
    ref = _canvas_ref(state["ref"])
    if ref is None:
        return None
    images = _previews(state)
    geo = [_geo_params(state["layers"][i], i, ref, False) for i in range(3)]
    negative = bool(state.get("negative"))
    tone = [_tone_params(state["layers"][i], negative) for i in range(3)]
    visible = tuple(bool(v) for v in state["visible"])
    crop = state["crop"]
    (gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
     gsat, gtemp, gtint, gcurves, _gbw) = _global_params(state)

    # compose_trichrome split in two, as MainWindow.recompute_preview does,
    # so the image right before the curves is available for the Curves
    # editor's background histogram.
    solo = state.get("solo")
    if solo is not None and _channels[solo] is not None:
        # Solo Layer Preview: that one channel, aligned and toned, in B&W,
        # with only the master (Y) curve, as on the desktop.
        only = tuple(i == solo for i in range(3))
        gray = imaging.compose_rgb_from_channels(images, geo, tone, ref, only)[..., solo]
        gray = imaging.apply_tone_curve(
            gray, gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights)
        pre_curve = np.repeat(gray[..., None], 3, axis=2)
        curved = imaging.apply_curve(gray, gcurves.get("Y", _IDENTITY_CURVE))
        rgb = np.repeat(curved[..., None], 3, axis=2)
    else:
        rgb0 = imaging.compose_rgb_from_channels(images, geo, tone, ref, visible)
        pre_curve = imaging.apply_global_correction_before_curves(
            rgb0, gblack, gwhite, ggamma, gexposure, gbrightness, gcontrast, gshadows, ghighlights,
            gsat, gtemp, gtint)
        rgb = imaging.apply_curves(pre_curve, gcurves)
    rgb = np.clip(rgb, 0.0, 1.0)
    mask = imaging.compose_coverage_mask(images, geo, ref)
    rgb = _frame_transform(rgb, crop)
    pre_curve = _frame_transform(pre_curve, crop)
    mask = _frame_transform(mask, crop)
    frame_h, frame_w = rgb.shape[:2]
    if not state["full_frame"]:
        rect = (crop["x"], crop["y"], crop["width"], crop["height"])
        rgb = imaging.apply_crop_rect(rgb, *rect)
        pre_curve = imaging.apply_crop_rect(pre_curve, *rect)
        mask = imaging.apply_crop_rect(mask, *rect)

    rgb_u8 = imaging.to_uint8(rgb)
    valid = mask > 0.5
    hist_pre = imaging.compute_channel_histograms(imaging.to_uint8(pre_curve), valid)
    _curve_base = {
        "key": key, "pre_curve": pre_curve, "index": None, "valid": valid,
        "solo": solo is not None and _channels[solo] is not None,
        "frame_w": frame_w, "frame_h": frame_h,
        "hist_pre": {k: values.tolist() for k, values in hist_pre.items()},
    }
    return _preview_result(rgb_u8, valid, _curve_base, start)


def auto_align(state_json: str, apply_distortion: bool) -> dict:
    """MainWindow._auto_align_all with a locked reference at the identity:
    ORB + RANSAC (ECC fallback) on MAX_PREVIEW_DIM reductions of the preview
    arrays, then optionally the lens-coefficient search."""
    start = time.perf_counter()
    state = json.loads(state_json)
    ref = state["ref"]
    previews = _previews(state)
    reference = previews[ref]
    results, failed = {}, []
    for index in range(3):
        if index == ref or _channels[index] is None:
            continue
        moving = previews[index]
        try:
            # Matched at the desktop's preview size, returned in this
            # preview's pixel units.
            dx, dy, scale, rotation = alignment.auto_align_layer(reference, moving, imaging.MAX_PREVIEW_DIM)
        except alignment.AlignmentError:
            failed.append(index)
            continue
        result = {"dx": dx, "dy": dy, "scale": scale, "rotation": rotation}
        if apply_distortion:
            d, pv, ph, an = alignment.optimize_distortion(reference, moving, dx, dy, scale, rotation)
            result.update(distortion=d, perspective_v=pv, perspective_h=ph, anamorphic=an)
        results[str(index)] = result
    return {"results": results, "failed": failed, "ms": _ms(start)}


def export_image(state_json: str, fmt: str) -> dict:
    """Full-resolution export: reload each file, compose, then
    Geometry + straighten + mirror + crop (imaging.apply_crop), and encode."""
    start = time.perf_counter()
    state = json.loads(state_json)
    ref = _canvas_ref(state["ref"])
    color = state["color_trichrome"]
    k = state.get("quarter_turns", 0)
    fulls = [
        _turned(_load_full(i, entry["path"], color), k) if entry else None
        for i, entry in enumerate(_channels)
    ]
    geo = [_geo_params(state["layers"][i], i, ref, True) for i in range(3)]
    negative = bool(state.get("negative"))
    tone = [_tone_params(state["layers"][i], negative) for i in range(3)]
    rgb = imaging.compose_trichrome(fulls, geo, tone, ref, _global_params(state))
    del fulls
    gc.collect()
    crop = state["crop"]
    rgb = imaging.apply_crop(
        rgb, crop["rotation"], crop["mirror_h"], crop["mirror_v"],
        crop["x"], crop["y"], crop["width"], crop["height"], **_geometry(crop))
    height, width = rgb.shape[:2]
    compose_ms = _ms(start)

    if fmt == "tiff16":
        bgr16 = cv2.cvtColor(imaging.to_uint16(rgb), cv2.COLOR_RGB2BGR)
        del rgb
        ok, encoded = cv2.imencode(".tif", bgr16)
        if not ok:
            raise RuntimeError("TIFF encoding failed")
        data = encoded.tobytes()
    else:
        image = Image.fromarray(imaging.to_uint8(rgb), mode="RGB")
        del rgb
        buffer = io.BytesIO()
        if fmt == "jpeg":
            image.save(buffer, format="JPEG", quality=95)
        else:
            image.save(buffer, format="PNG", compress_level=3)
        data = buffer.getvalue()
    gc.collect()
    return {"data": data, "width": width, "height": height,
            "compose_ms": compose_ms, "ms": _ms(start)}
