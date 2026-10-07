"""Background worker that recomputes previews shown from a session's preview
cache with the exact, original-file pipeline (see preview_cache.py)."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QObject, Signal

from . import preview_cache


def preview_decode_workers() -> int:
    # Each in-flight decode of a 44MP photo peaks around 0.5GB (PIL image +
    # float32 copies), so parallelism is capped well below the core count.
    return max(1, min(4, os.cpu_count() or 1))


class PreviewUpgradeWorker(QObject):
    # cache key, exact preview (np.ndarray), preview_scale
    preview_ready = Signal(str, object, float)
    finished = Signal()

    def __init__(self, jobs: list[tuple[str, str, str, str, object, int]]):
        """``jobs``: (key, path, decode, slot, film_base, quarter_turns),
        plain values snapshotted on the main thread - nothing here touches a
        ChannelLayer."""
        super().__init__()
        self.jobs = jobs
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        with ThreadPoolExecutor(max_workers=preview_decode_workers()) as pool:
            futures = {
                pool.submit(preview_cache.compute_exact_preview, path, decode, slot, film_base, qt): key
                for key, path, decode, slot, film_base, qt in self.jobs
            }
            for future in as_completed(futures):
                if self._cancelled:
                    for f in futures:
                        f.cancel()
                    break
                try:
                    preview, scale = future.result()
                except Exception:
                    continue  # leave the cached preview in place
                self.preview_ready.emit(futures[future], preview, scale)
        self.finished.emit()
