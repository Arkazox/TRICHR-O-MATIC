# Trichr-o-matic

A macOS app that recomposes a color image from three black & white photos shot through Red, Green and Blue filters (trichromy).

## Features

- Import the 3 B&W shots (R, G, B) — TIFF/PNG/JPEG, 8 or 16 bit
- **Negative** option per channel, for raw uninverted negative scans
- Automatic alignment (ORB feature matching + RANSAC, falling back to ECC intensity-based alignment)
- Manual alignment: drag directly on the preview (offset), Shift+scroll (scale), Alt+scroll (rotate), or the sliders — double-click any slider to reset it
- Per-channel color correction: black/white point, gamma, brightness, contrast
- Global color correction on the composed image: black/white point, gamma, brightness, contrast, saturation, hue
- Export as 8-bit PNG, 8-bit JPEG or 16-bit TIFF
- **Batch mode** (separate window): point it at a folder of R/G/B triplets (matched by filename) and process them all at once, reusing the alignment and/or color correction dialed in on the Simple mode window
- English / French interface, switchable anytime from the Language menu (defaults to English)
- Distraction-free fullscreen preview, trackpad pinch-to-zoom and two-finger pan
- Built-in help (Help menu, or F1) with shortcuts and a quick-start guide
- Remembers the last folder used to load/export images

## Development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Iterate this way while developing — no need to rebuild the `.app` bundle until you want a standalone, double-clickable copy.

## Building the macOS app

```bash
./build_mac.sh
```

The app is generated at `dist/Trichr-o-matic.app`.

## Usage notes (Simple mode)

1. Load the reference image (Green by default), then the other two. If working from raw negative scans, check **Negative** on each channel first.
2. To align a layer: click **Auto align**, or check **Active** on that layer and drag it directly on the canvas (scroll to fine-tune scale/rotation).
3. Adjust each channel's color correction, then the global color correction if needed.
4. Export the final result.

The reference channel is the geometric anchor (canvas size and orientation) — its own alignment controls are disabled. Switch the reference via the **Reference** radio button if needed.

The **Alignment** and **Color correction** sections are collapsed by default to keep the import step uncluttered; click the arrow next to their title to expand them.

## Batch mode

Open it from **File → Batch Mode…**. It processes a whole folder of scans in one run:

1. Point it at a folder containing all your R/G/B files. Filenames just need a channel marker somewhere (suffix or prefix, with or without a separator) — e.g. `scene01_R.tif` / `scene01_G.tif` / `scene01_B.tif`, `R_scene01.tif`, `scene01R.tif`, or the French `rouge`/`vert`/`bleu`/`r`/`v`/`b`. Files sharing the same base name are grouped into a triplet; anything that doesn't match a complete R+G+B set is listed as unmatched and skipped.
2. Choose the alignment strategy:
   - **Reuse current alignment from Simple mode** — applies the exact fixed offset/scale/rotation currently set in the Simple mode window to every triplet. Ideal when a fixed scanning rig introduces the same geometric offset regardless of the scene: calibrate once on one representative shot in Simple mode, then batch the rest.
   - **Auto-align each image individually** — re-runs the automatic alignment per triplet, for scans whose framing shifts from shot to shot.
   - Color correction and negative settings are always taken from the current Simple mode window, whichever alignment strategy you pick.
3. Pick an output folder, filename suffix and format, then **Start batch**. Progress and a per-file log are shown live; **Cancel** stops after the current image.
