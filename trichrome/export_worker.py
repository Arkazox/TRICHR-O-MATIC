"""Background worker that exports multiple batch items, each with its own
independent alignment/color correction, at full resolution."""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, Signal

from . import imaging


class BatchExportWorker(QObject):
    progress = Signal(int, int)
    item_result = Signal(int, bool, str)
    finished = Signal()

    def __init__(
        self, items, full_res_loader, full_res_params, output_dir, suffix, ext, bit_depth,
        full_res_color_loader=None,
    ):
        """``items``: list of BatchItem. ``full_res_loader(layer)`` returns a
        full-resolution grayscale array for a layer (loading from disk if
        needed). ``full_res_params(layer, ref)`` returns the full-resolution
        (dx, dy, scale, rotation) tuple for a layer relative to ``ref``.
        ``full_res_color_loader(layer)`` is the Normal-mode counterpart -
        full-resolution *color* for item.normal_layer, never collapsed to
        grayscale (optional/None-safe so a caller that never exports a
        Normal-mode item doesn't need to pass it).
        ``output_dir`` of None means "same folder as each item's own source
        file" instead of one fixed folder for every item.
        """
        super().__init__()
        self.items = items
        self.full_res_loader = full_res_loader
        self.full_res_params = full_res_params
        self.full_res_color_loader = full_res_color_loader
        self.output_dir = output_dir
        self.suffix = suffix
        self.ext = ext
        self.bit_depth = bit_depth
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        total = len(self.items)
        for i, item in enumerate(self.items):
            if self._cancelled:
                break
            try:
                if item.mode == "normal":
                    nl = item.normal_layer
                    image = imaging.apply_invert(self.full_res_color_loader(nl), nl.invert)
                    gc = item.global_corr
                    global_params = (
                        gc.black_point, gc.white_point, gc.gamma, gc.exposure, gc.brightness, gc.contrast,
                        gc.shadows, gc.highlights, gc.saturation, gc.temperature, gc.tint,
                        {ch: tuple(pts) for ch, pts in gc.curves.items()})
                    rgb = imaging.compose_normal(image, global_params)
                    ref_path = nl.path
                else:
                    ref = next(l for l in item.layers if l.is_reference)
                    images = [self.full_res_loader(l) for l in item.layers]
                    geo_params = [self.full_res_params(l, ref) for l in item.layers]
                    tone_params = [(l.black_point, l.white_point, l.gamma, l.exposure, l.brightness, l.contrast,
                                    l.shadows, l.highlights, l.invert) for l in item.layers]
                    gc = item.global_corr
                    global_params = (
                        gc.black_point, gc.white_point, gc.gamma, gc.exposure, gc.brightness, gc.contrast,
                        gc.shadows, gc.highlights, gc.saturation, gc.temperature, gc.tint,
                        {ch: tuple(pts) for ch, pts in gc.curves.items()})
                    rgb = imaging.compose_trichrome(images, geo_params, tone_params, ref.color_index, global_params)
                    ref_path = ref.path

                cr = item.crop
                rgb = imaging.apply_crop(
                    rgb, cr.rotation, cr.mirror_h, cr.mirror_v, cr.x, cr.y, cr.width, cr.height)

                out_dir = self.output_dir if self.output_dir is not None else os.path.dirname(ref_path)
                out_name = f"{item.base}{self.suffix}{self.ext}"
                out_path = os.path.join(out_dir, out_name)
                imaging.save_image(out_path, rgb, bit_depth=self.bit_depth)
                self.item_result.emit(i, True, out_name)
            except Exception as exc:
                self.item_result.emit(i, False, str(exc))
            self.progress.emit(i + 1, total)
        self.finished.emit()
