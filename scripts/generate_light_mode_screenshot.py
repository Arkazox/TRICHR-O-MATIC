"""Generates resources/quick_tour_light_mode.png - the screenshot of the
real Light mode window shown in the Quick Tour's "Light mode" step, with
the Quick Tour sample trichrome (resources/sample/) loaded.

Must run with the native macOS platform (NOT QT_QPA_PLATFORM=offscreen):
the offscreen platform has no macOS style or dark appearance, so it renders
a white, generic-looking UI that doesn't match the real app. The color
scheme is forced to Dark (the app's usual look). A window opens briefly
while it runs. Settings are isolated, the user's own session is untouched.

    ./venv/bin/python scripts/generate_light_mode_screenshot.py

Re-run it whenever Light mode's UI changes enough for the screenshot to
look stale.
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import trichrome.main_window as mwmod  # noqa: E402

WINDOW_SIZE = (1180, 760)
OUTPUT_WIDTH = 720  # px, the asset's final width (the callout shows it ~290pt wide on Retina)
OUT_PATH = os.path.join(ROOT, "resources", "quick_tour_light_mode.png")


def main() -> None:
    mwmod.ORG_NAME = mwmod.APP_NAME = "TrichromeLightModeScreenshot"
    settings = QSettings(mwmod.ORG_NAME, mwmod.APP_NAME)
    settings.clear()
    settings.setValue("light_mode_active", True)
    settings.sync()

    app = QApplication(sys.argv)
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    mw = mwmod.MainWindow()

    def pump(ms: int) -> None:
        end = time.time() + ms / 1000
        while time.time() < end:
            app.processEvents()
            time.sleep(0.01)

    paths = {c: os.path.join(ROOT, "resources", "sample", f"Trichrome_Sample_{c}.jpg") for c in "RGB"}
    item = mw._build_trichrome_batch_item_from_paths(paths, invert=False)
    item.base = "Sample Trichrome"
    mw._apply_restored_items([item], mw.sort_mode, mw.sort_reversed, 0)
    for key in mwmod._LIGHT_MODE_BLOCK_KEYS:
        widget = mw.block_widgets[key]
        mwmod.set_block_collapsed(widget.body, mw.block_collapse_buttons[key], False)

    mw.resize(*WINDOW_SIZE)
    mw.show()
    pump(600)
    mw.recompute_preview()
    mw.canvas.zoom_fit()
    pump(800)

    image = mw.grab().toImage()
    image = image.scaledToWidth(OUTPUT_WIDTH, Qt.SmoothTransformation)
    image.save(OUT_PATH)
    print(OUT_PATH, image.width(), "x", image.height())

    settings.clear()
    mw.hide()
    # Not mw.close(): no session to save, and closeEvent would write it to the
    # isolated domain just cleared above.


if __name__ == "__main__":
    main()
