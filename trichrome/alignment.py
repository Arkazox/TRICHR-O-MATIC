"""Automatic alignment of a moving grayscale image onto a reference one.

Returns a 2x3 similarity matrix (translation + rotation + uniform scale,
no shear) mapping moving-image pixel coordinates to reference-image pixel
coordinates, both expressed in "as-loaded" (unwarped) coordinates.
"""
from __future__ import annotations

import numpy as np
import cv2

from . import imaging


class AlignmentError(RuntimeError):
    pass


def _to_uint8(img: np.ndarray) -> np.ndarray:
    return np.clip(np.round(img * 255.0), 0, 255).astype(np.uint8)


def auto_align_layer(
    reference_full: np.ndarray, moving_full: np.ndarray, max_dim: int | None = None,
) -> tuple[float, float, float, float]:
    """Auto-align a full-resolution moving image onto a full-resolution reference.

    Downscales both for speed, then converts the result back to full-resolution
    pixel units. Returns (dx, dy, scale, rotation_deg) usable directly as a
    geo_params tuple for imaging.compose_trichrome.
    """
    max_dim = max_dim or imaging.MAX_PREVIEW_DIM
    ref_preview, ref_scale = imaging.make_preview(reference_full, max_dim)
    mov_preview, mov_scale = imaging.make_preview(moving_full, max_dim)

    matrix = auto_align(ref_preview, mov_preview)

    h, w = mov_preview.shape[:2]
    ref_h, ref_w = ref_preview.shape[:2]
    dx, dy, scale, rotation = imaging.decompose_similarity_matrix(
        matrix, src_center=(w / 2, h / 2), dst_center=(ref_w / 2, ref_h / 2),
    )
    dx_full = dx / ref_scale
    dy_full = dy / ref_scale
    scale_full = scale * (mov_scale / ref_scale)
    return dx_full, dy_full, scale_full, rotation


def auto_align(reference: np.ndarray, moving: np.ndarray) -> np.ndarray:
    """Try feature-based alignment first, fall back to ECC intensity-based."""
    try:
        return _align_orb(reference, moving)
    except AlignmentError:
        return _align_ecc(reference, moving)


def _align_orb(reference: np.ndarray, moving: np.ndarray, min_matches: int = 12) -> np.ndarray:
    ref8 = _to_uint8(reference)
    mov8 = _to_uint8(moving)

    orb = cv2.ORB_create(nfeatures=4000)
    kp_ref, des_ref = orb.detectAndCompute(ref8, None)
    kp_mov, des_mov = orb.detectAndCompute(mov8, None)

    if des_ref is None or des_mov is None or len(kp_ref) < min_matches or len(kp_mov) < min_matches:
        raise AlignmentError("Pas assez de points d'intérêt détectés")

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    raw_matches = matcher.knnMatch(des_mov, des_ref, k=2)

    good = []
    for pair in raw_matches:
        if len(pair) != 2:
            continue
        m, n = pair
        if m.distance < 0.75 * n.distance:
            good.append(m)

    if len(good) < min_matches:
        raise AlignmentError("Pas assez de correspondances fiables")

    src_pts = np.float32([kp_mov[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_ref[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    matrix, inliers = cv2.estimateAffinePartial2D(
        src_pts, dst_pts, method=cv2.RANSAC, ransacReprojThreshold=3.0,
    )
    if matrix is None or inliers is None or int(inliers.sum()) < min_matches // 2:
        raise AlignmentError("Estimation de transformation échouée")

    return matrix.astype(np.float64)


# How strongly optimize_distortion is pulled back toward "no correction" - a
# candidate (distortion, perspective_v, perspective_h, anamorphic) is only kept
# over the identity (0,0,0,0) baseline when it improves the ECC registration
# cost by more than this penalty, weighted by the squared magnitude of the 4
# params - the goal is an optimal alignment with as little distortion applied
# as possible. Tune if the built app's own results feel too eager/too timid to
# apply a correction.
_DISTORTION_REG_WEIGHT = 0.02
_DISTORTION_SEARCH_STEP0 = 0.25
_DISTORTION_SEARCH_MIN_STEP = 0.01


def optimize_distortion(
    reference: np.ndarray, moving: np.ndarray,
    dx: float, dy: float, scale: float, rotation: float,
) -> tuple[float, float, float, float]:
    """Given a channel's already-estimated similarity alignment (dx/dy/
    scale/rotation, from auto_align/auto_align_layer), searches for small
    per-channel lens-correction coefficients
    (imaging.apply_lens_correction's own 4 parameters - distortion,
    perspective_v, perspective_h, anamorphic) that further improve
    registration against ``reference`` - the "Apply distortion to auto
    align" option.

    A plain, dependency-free coordinate-descent pattern search (Hooke-
    Jeeves style) - this app has no numerical-optimization dependency
    today (no scipy in requirements.txt), and adding one just for this
    single call site would also need new PyInstaller bundling
    (trichrome.spec's collect_all() loop), untested here. Each candidate
    is scored via cv2.computeECC (the same Enhanced Correlation
    Coefficient metric alignment.py's own ECC fallback path already uses
    to *find* a transform - here it only *scores* one), regularized by
    _DISTORTION_REG_WEIGHT so a larger correction is only kept when it
    meaningfully improves registration, not merely matched by it.

    Returns (0.0, 0.0, 0.0, 0.0) if the search never beats the no-
    correction baseline (a channel with too little texture to score
    reliably, or genuinely no lens mismatch, both resolve to "don't
    bother")."""
    ref_h, ref_w = reference.shape[:2]
    mh, mw = moving.shape[:2]
    ref_f32 = reference.astype(np.float32)
    matrix = imaging.build_similarity_matrix(
        dx, dy, scale, rotation, src_center=(mw / 2, mh / 2), dst_center=(ref_w / 2, ref_h / 2))

    def cost(params: np.ndarray) -> float:
        d, pv, ph, a = (float(v) for v in params)
        corrected = imaging.apply_lens_correction(moving, d, pv, ph, a)
        warped = imaging.warp_to_canvas(corrected, matrix, (ref_w, ref_h))
        try:
            score = float(cv2.computeECC(ref_f32, warped.astype(np.float32)))
        except cv2.error:
            score = -1.0
        reg = _DISTORTION_REG_WEIGHT * float(np.sum(np.square(params)))
        return (1.0 - score) + reg

    bounds = ((-1.0, 1.0),) * 4
    x = np.zeros(4, dtype=np.float64)
    initial_cost = cost(x)
    best_cost = initial_cost
    step = _DISTORTION_SEARCH_STEP0
    while step > _DISTORTION_SEARCH_MIN_STEP:
        improved = False
        for i in range(4):
            for sign in (1.0, -1.0):
                candidate = x.copy()
                candidate[i] = np.clip(candidate[i] + sign * step, *bounds[i])
                c = cost(candidate)
                if c < best_cost - 1e-6:
                    x, best_cost, improved = candidate, c, True
        if not improved:
            step *= 0.5

    if best_cost >= initial_cost:
        return 0.0, 0.0, 0.0, 0.0
    return float(x[0]), float(x[1]), float(x[2]), float(x[3])


def _align_ecc(reference: np.ndarray, moving: np.ndarray) -> np.ndarray:
    ref_f = reference.astype(np.float32)
    mov_f = moving.astype(np.float32)

    if mov_f.shape != ref_f.shape:
        mov_f = cv2.resize(mov_f, (ref_f.shape[1], ref_f.shape[0]), interpolation=cv2.INTER_AREA)
        scale_x = moving.shape[1] / ref_f.shape[1]
        scale_y = moving.shape[0] / ref_f.shape[0]
    else:
        scale_x = scale_y = 1.0

    warp_matrix = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)

    try:
        _, warp_matrix = cv2.findTransformECC(
            ref_f, mov_f, warp_matrix, cv2.MOTION_EUCLIDEAN, criteria, None, 5,
        )
    except cv2.error as exc:
        raise AlignmentError("L'algorithme ECC n'a pas convergé") from exc

    matrix = warp_matrix.astype(np.float64)
    if scale_x != 1.0 or scale_y != 1.0:
        # Rescale translation back to the moving image's original pixel size.
        matrix[0, 2] *= scale_x
        matrix[1, 2] *= scale_y
    return matrix
