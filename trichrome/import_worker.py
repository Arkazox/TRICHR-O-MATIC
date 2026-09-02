"""Background worker that turns matched R/G/B triplets into BatchItems.

Runs in a QThread so loading and auto-aligning many (possibly large) photos
doesn't freeze the UI. Each item starts from fresh, default color correction
and alignment - either auto-aligned individually or left at the default
(identity) position, never copied from any other photo or session.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from . import alignment, imaging
from .model import ChannelLayer, GlobalCorrection

CHANNEL_LETTERS = ("R", "G", "B")


class BatchImportWorker(QObject):
    progress = Signal(int, int)
    item_ready = Signal(int, object, str)  # index, BatchItem or None, warning/error message
    finished = Signal()

    def __init__(self, triplets, ref_letter: str, auto_align: bool, harris_shutter: bool = False):
        super().__init__()
        self.triplets = triplets
        self.ref_letter = ref_letter
        self.auto_align = auto_align
        self.harris_shutter = harris_shutter
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        total = len(self.triplets)
        for i, triplet in enumerate(self.triplets):
            if self._cancelled:
                break
            try:
                item, warning = self._build_item(triplet)
                self.item_ready.emit(i, item, warning)
            except Exception as exc:
                self.item_ready.emit(i, None, str(exc))
            self.progress.emit(i + 1, total)
        self.finished.emit()

    def _build_item(self, triplet):
        from .model import BatchItem  # local import: avoids a model -> worker -> model cycle at module load

        previews = {}
        scales = {}
        for letter in CHANNEL_LETTERS:
            full = imaging.load_grayscale(
                triplet.paths[letter], channel=letter if self.harris_shutter else None)
            preview, scale = imaging.make_preview(full)
            previews[letter] = preview
            scales[letter] = scale

        ref_preview = previews[self.ref_letter]
        ref_h, ref_w = ref_preview.shape[:2]

        warnings = []
        layers = []
        for ci, letter in enumerate(CHANNEL_LETTERS):
            layer = ChannelLayer(color_index=ci, label=letter)
            layer.path = triplet.paths[letter]
            layer.image_preview = previews[letter]
            layer.preview_scale = scales[letter]
            layer.is_reference = (letter == self.ref_letter)
            layer.harris_shutter = self.harris_shutter

            if letter != self.ref_letter and self.auto_align:
                try:
                    h, w = previews[letter].shape[:2]
                    matrix = alignment.auto_align(ref_preview, previews[letter])
                    dx, dy, sc, rot = imaging.decompose_similarity_matrix(
                        matrix, src_center=(w / 2, h / 2), dst_center=(ref_w / 2, ref_h / 2))
                    layer.dx, layer.dy, layer.scale, layer.rotation = dx, dy, sc, rot
                except alignment.AlignmentError as exc:
                    warnings.append(f"{letter}: {exc}")
            # else: leave at ChannelLayer's own default identity alignment.

            layers.append(layer)

        capture_date = imaging.extract_capture_date(triplet.paths[self.ref_letter])
        item = BatchItem(base=triplet.base, paths=dict(triplet.paths), layers=layers,
                          global_corr=GlobalCorrection(), capture_date=capture_date)
        return item, "; ".join(warnings)
