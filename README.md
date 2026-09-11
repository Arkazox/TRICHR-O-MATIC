# Trichr-o-matic

A macOS app that recomposes a color image from three black & white photos shot
through Red, Green and Blue (or IR/Aerochrome/custom) filters — and, more
generally, a photo-editing app built around that trichromy workflow.

## Features

### Modes
- **Solo** — a single, already-composed photo (color or B&W), loaded and
  edited as-is, no channel recomposition.
- **Classic Trichrome** — the classic case: 3 black & white shots taken through
  R/G/B (or IR/Aerochrome/custom) filters, recomposed into one color image.
- **Color Trichrome** — 3 real color photos, each keeping its own R, G or B
  channel instead of being flattened to grayscale, for a genuine
  "Harris Shutter" look.

### Import
- Load photos individually (**Trichrome Process** block), or drag image files
  from Finder straight onto the thumbnail strip (added as Solo photos).
- **Import Images…** (batch import window): pick a Processing Mode (Solo /
  Classic Trichrome / Color Trichrome), then match R/G/B triplets **Automatic**ally
  by filename (RGB Trichrome, IR Trichrome, Aerochrome or a fully custom
  filter-to-channel mapping), **Sequential**ly (files already in R, G, B
  order), or **Manual**ly (pick each column yourself) — or just select
  individual images/a whole folder for Solo mode.
- TIFF/PNG/JPEG, 8 or 16 bit. **Negative** option per channel for raw,
  uninverted negative scans.

### Editing tools — every one its own movable, collapsible, closable block
- **Trichrome Process** — per-channel alignment (drag on the canvas,
  Shift+scroll to scale, Alt/Option+scroll to rotate, or sliders) and tone
  (exposure, black/white point, gamma, brightness, contrast, highlights/
  shadows), plus automatic alignment (ORB feature matching + RANSAC, falling
  back to ECC) and a lockable reference channel.
- **Light** / **Color** — the composed image's overall look: exposure,
  brightness, contrast, highlights/shadows/whites/blacks, gamma, negative
  (Light); temperature, tint, saturation, a white-balance eyedropper, and a
  true luminance-weighted **Black & White** conversion (Color).
- **Crop** — aspect ratio presets (or custom/original/free), straighten,
  horizontal/vertical mirror, 4 grid overlay styles, interactive drag/resize
  rectangle.
- **Curves** — independent Y (master), R, G and B tone curves with a live,
  channel-matched histogram overlay showing the image *before* your edits.
- **Scan** — tethered capture from a connected camera (via `gphoto2`): live
  connect/disconnect status, 3 film types (Black & White / Color / Color
  Reversal), an optional on-screen RGB backlight (with an automatic
  red/green/blue 3-shot sequence for scanning straight into a trichrome
  triplet), film-base color correction for color negatives, and automatic
  import of finished captures into the current session.
- **Histogram** — live Y/R/G/B curves with clipping indicators and a pixel
  eyedropper.

### Layout
- Drag any block by its grip to reorder it, move it between the two side
  panels, collapse it to just its header, or close it — bring closed blocks
  back from the **Tools** menu.
- Save named **Layout Presets**; the toolbar's Trichrome / Color Correction /
  Crop / Scan buttons (and their T/E/C/S shortcuts) jump straight to your own
  saved layout for each task. **Reset Layout** restores the defaults.

### Everything else
- Undo/redo for nearly every action, filmstrip with drag-to-reorder,
  multi-select, copy/paste settings, Reset All and Duplicate per photo, and a
  thumbnail grid view.
- Export as 8-bit PNG, 8-bit JPEG or 16-bit TIFF — current photo, a selection,
  or the whole session at once.
- Sessions: portable `.trirgb` project files (File ▸ Save/Open Session), plus
  an OS-level autosave fallback.
- Recovery for missing/moved source photos, with a folder-based relink flow.
- English / French interface, switchable from the Help menu (defaults to
  English).
- Distraction-free fullscreen preview, trackpad pinch-to-zoom and two-finger
  pan.
- Built-in help (Help menu, or F1) with shortcuts and a quick-start guide.

## Development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Iterate this way while developing — no need to rebuild the `.app` bundle until
you want a standalone, double-clickable copy.

## Building the macOS app

```bash
./build_mac.sh
```

The app is generated at `dist/Trichr-o-matic.app`. Bump the version string in
`trichrome.spec` (`CFBundleShortVersionString`) before a release build — see
`CHANGELOG_EN.md` for the user-facing history of each version.

## Usage notes

1. Pick a **Mode** for your photo in the Files block: **Solo** for a single
   already-composed image, or a Trichrome mode to combine 3 R/G/B shots.
2. In a Trichrome mode, load the reference channel first (Green by default),
   then the other two — they're auto-aligned against it automatically (redo
   anytime with **Auto Align** in the Trichrome Process block). Switch the
   locked/reference channel anytime if needed.
3. Adjust each channel's alignment/tone (Trichrome Process), then the overall
   Light/Color correction, Crop and Curves as needed — every block can be
   rearranged, collapsed or hidden to fit how you work.
4. Click **Export…** to choose an output folder/format and save the result.

## Batch import

Open it from the sidebar's **Import Images…** button (⌘I). It processes many
photos in one run:

1. Choose a **Processing Mode** for the whole batch — Solo, Classic Trichrome, or
   Color Trichrome.
2. In a Trichrome mode, point it at a folder of R/G/B files (matched
   automatically by a filter keyword in the filename, or manually), pick the
   **Import Rules** (which filter feeds which channel — RGB Trichrome, IR,
   Aerochrome, or a custom mapping), and optionally auto-align each triplet
   on import. In Solo mode, just select the individual images or a folder.
3. Click **Import** — the new photos are added to the filmstrip, ready to
   edit and export like any other photo in the session.
