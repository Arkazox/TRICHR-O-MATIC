"""Background worker for HQ Preview's native-resolution recompute (see
CLAUDE.md's "Preview resolution & HQ Preview") - keeps the multi-second
full-resolution compose_trichrome/compose_normal pass off the UI thread so
sliders/menus/etc. stay responsive while it runs. Mirrors the QObject +
moveToThread pattern import_worker.py/export_worker.py already use."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from . import imaging


class HQPreviewWorker(QObject):
    # rgb_uint8, {layer: newly-decoded full-res array} - the caller applies
    # the cache dict onto layer.image_full itself, back on the main thread
    # (see MainWindow._on_hq_preview_result) - this worker never mutates
    # the layer objects it reads from.
    result_ready = Signal(object, object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self, is_normal_mode: bool, layers, normal_layer, full_res_loader, full_res_color_loader,
        geo_params, tone_params, global_params, ref_color_index,
        crop_active: bool, crop_rotation: float, crop_mirror_h: bool, crop_mirror_v: bool,
        crop_x: float, crop_y: float, crop_width: float, crop_height: float,
    ):
        """``full_res_loader(layer)``/``full_res_color_loader(layer)`` are
        MainWindow's own plain, uncached ``_full_res_image``/
        ``_full_res_color_image`` (the same callables BatchExportWorker
        takes) - read-only, so calling them from this thread is safe.
        ``geo_params``/``tone_params``/``global_params``/``ref_color_index``
        are a plain snapshot taken on the main thread at dispatch time, not
        re-read live during run() - only the image *pixel data* (which
        doesn't change from editing sliders) is fetched here."""
        super().__init__()
        self.is_normal_mode = is_normal_mode
        self.layers = layers
        self.normal_layer = normal_layer
        self.full_res_loader = full_res_loader
        self.full_res_color_loader = full_res_color_loader
        self.geo_params = geo_params
        self.tone_params = tone_params
        self.global_params = global_params
        self.ref_color_index = ref_color_index
        self.crop_active = crop_active
        self.crop_rotation = crop_rotation
        self.crop_mirror_h = crop_mirror_h
        self.crop_mirror_v = crop_mirror_v
        self.crop_x = crop_x
        self.crop_y = crop_y
        self.crop_width = crop_width
        self.crop_height = crop_height

    def run(self) -> None:
        try:
            # A list of (layer, array) pairs, not a dict keyed by layer -
            # ChannelLayer is a plain (unhashable, eq=True) dataclass.
            newly_loaded = []
            if self.is_normal_mode:
                layer = self.normal_layer
                full = self.full_res_color_loader(layer)
                if layer.image_full is None:
                    newly_loaded.append((layer, full))
                image = imaging.apply_invert(full, layer.invert)
                rgb = imaging.compose_normal(image, self.global_params)
            else:
                images = []
                for l in self.layers:
                    if not l.has_image():
                        images.append(None)
                        continue
                    full = self.full_res_loader(l)
                    if l.image_full is None:
                        newly_loaded.append((l, full))
                    images.append(full)
                rgb = imaging.compose_trichrome(
                    images, self.geo_params, self.tone_params, self.ref_color_index, self.global_params)
            if self.crop_active:
                # Same "show the full frame while cropping" exception as the
                # live preview - see the matching comment in recompute_preview.
                rgb = imaging.apply_straighten_mirror(
                    rgb, self.crop_rotation, self.crop_mirror_h, self.crop_mirror_v)
            else:
                rgb = imaging.apply_crop(
                    rgb, self.crop_rotation, self.crop_mirror_h, self.crop_mirror_v,
                    self.crop_x, self.crop_y, self.crop_width, self.crop_height)
            self.result_ready.emit(imaging.to_uint8(rgb), newly_loaded)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
