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
