# Trichr-o-matic

A macOS app that recomposes a color image from three black & white photos shot
through Red, Green and Blue (or IR/Aerochrome/custom) filters — and, more
generally, a photo-editing app built around that trichromy workflow.

<!-- TODO before publishing: add a screenshot, e.g. docs/screenshot.png -->

## Download

**[Download the latest version](https://github.com/Arkazox/Trichr-o-matic/releases/latest)**:
under *Assets*, pick the `.zip` for your Mac, unzip it, and move
`Trichr-o-matic.app` to your Applications folder.

- `Trichr-o-matic-vX.Y.Z-AppleSilicon.zip` for Macs with an M1 chip or later.
- `Trichr-o-matic-vX.Y.Z-Intel.zip` for Macs with an Intel processor.

Not sure which Mac you have? Open the Apple menu ▸ **About This Mac**: it shows either
**Chip** (Apple M1, M2, …) or **Processor** (Intel).

**Requirements:** macOS 12 Monterey or later.

### First launch

The app isn't signed with an Apple Developer certificate yet, so macOS blocks
it the first time:

1. Double-click `Trichr-o-matic.app`. macOS says it can't verify the app.
   Click **Done** (or **OK**).
2. Open **System Settings ▸ Privacy & Security**, scroll down, and click
   **Open Anyway** next to the message about Trichr-o-matic.
3. Confirm with **Open** (you may be asked for your password).

You only need to do this once. If macOS instead says the app "is damaged and
can't be opened", run this in Terminal, then open the app again:

```bash
xattr -cr /Applications/Trichr-o-matic.app
```

### Privacy

The app works entirely offline, with one exception: at launch (and from
Trichr-o-matic ▸ Check for Updates…) it asks GitHub whether a newer version
exists. You can turn the automatic check off in Preferences. Nothing about you or your
photos is sent.

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
  filter-to-channel mapping, with an **Auto-Import Rules** explainer for each),
  **Sequential**ly (files already in a row, in any of the 6 R/G/B orders, not
  just R, G, B), or **Manual**ly (pick each column yourself) — or just select
  individual images/a whole folder for Solo mode.
- TIFF/PNG/JPEG (8 or 16 bit) and camera **RAW** files (Fuji `.RAF`, Canon
  `.CR2`/`.CR3`, Nikon `.NEF`/`.NRW`, Sony `.ARW`/`.SRF`/`.SR2`, Adobe `.DNG`,
  Olympus `.ORF`, Panasonic `.RW2`, Pentax `.PEF`, and more). **Negative**
  option per channel for raw, uninverted negative scans.

### Editing tools — every one its own movable, collapsible, closable block
- **Trichrome Process** — per-channel alignment (drag on the canvas,
  Shift+scroll to scale, Alt/Option+scroll to rotate, sliders, or arrow keys
  for a fine nudge) and tone (exposure, black/white point, gamma, brightness,
  contrast, highlights/shadows), plus automatic alignment (ORB feature
  matching + RANSAC, falling back to ECC) and a lockable reference channel.
  Each channel also gets its own **Transform** correction (distortion,
  vertical/horizontal perspective, anamorphic stretch, for fixing lens
  quirks on that one shot) and **Stretch on Canvas**, a click-and-drag local
  warp for fine corrections a simple transform can't reach. **Show Layer**
  toggles any combination of the 3 channels' contribution to the composed
  preview, in color.
- **Light** / **Color** — the composed image's overall look: exposure,
  brightness, contrast, highlights/shadows/whites/blacks, gamma, negative
  (Light); temperature, tint, saturation, a white-balance eyedropper, and a
  true luminance-weighted **Black & White** conversion (Color).
- **Framing** — aspect ratio presets (or custom/original/free), straighten,
  horizontal/vertical mirror, 4 grid overlay styles, interactive drag/resize
  rectangle; a **Geometry** section with the same distortion/perspective/
  anamorphic correction as Trichrome Process, applied to the whole composed
  image (works for Solo photos too) — including **Guided Perspective**,
  where you draw a couple of guide lines on the canvas and the app solves
  the correction for you.
- **Curves** — independent Y (master), R, G and B tone curves with a live,
  channel-matched histogram overlay showing the image *before* your edits.
- **Scan** *(experimental, off by default — turn it on in Preferences ▸
  Experimental; requires [gphoto2](http://www.gphoto.org), e.g.
  `brew install gphoto2`)* — tethered capture from a connected camera: live
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
- The toolbar's Trichrome / Color Correction / Crop / Scan buttons (and
  their T/E/C/S shortcuts) switch to a ready-made layout for each task. Save
  your own arrangements as named **Layout Presets**. **Reset Layout**
  restores the defaults.
- **Light Mode** (Window menu) — a hot-toggleable, restricted interface that
  recenters the app on single-photo trichrome editing (Files, Trichrome
  Process, Framing and Histogram only), for a simpler, kiosk-style workflow.

### Everything else
- Undo/redo for nearly every action, filmstrip with drag-to-reorder,
  multi-select, copy/paste settings, Reset All and Duplicate per photo, and a
  thumbnail grid view.
- Export as 8-bit PNG, 8-bit JPEG or 16-bit TIFF — current photo, a selection,
  or the whole session at once.
- Sessions: portable `.trirgb` project files (File ▸ Save/Open Session), plus
  an OS-level autosave fallback.
- Recovery for missing/moved source photos, with a folder-based relink flow.
- English / French interface, switchable in Preferences (defaults to
  English).
- Distraction-free fullscreen preview, trackpad pinch-to-zoom and two-finger
  pan, and an **HQ Preview** toggle for a sharper, full-resolution view once
  you stop editing.
- A guided **Quick Tour** (Help menu, or the toolbar's "?" dropdown) walks
  through the toolbar, every block and Batch Import on first launch —
  re-run it anytime, or turn off "show at startup" from the welcome window.
- Built-in help (Help menu, or F1) with a searchable table of contents,
  and a keyboard shortcuts sheet.

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
./build_mac.sh          # Apple Silicon -> dist-applesilicon/Trichr-o-matic.app
./build_mac.sh intel    # Intel (under Rosetta) -> dist-intel/Trichr-o-matic.app
```

Bump the version string in
`trichrome/version.py` (the single source of truth, read by both the app
itself and `trichrome.spec`'s `CFBundleShortVersionString`) before a
release build — see `CHANGELOG.md` for the history of each version.

## Usage notes

1. Pick a **Mode** for your photo in the Files block: **Solo** for a single
   already-composed image, or a Trichrome mode to combine 3 R/G/B shots.
2. In a Trichrome mode, load the reference channel first (Green by default),
   then the other two — they're auto-aligned against it automatically (redo
   anytime with **Auto Align** in the Trichrome Process block). Switch the
   locked/reference channel anytime if needed.
3. Adjust each channel's alignment/tone (Trichrome Process), then the overall
   Light/Color correction, Framing and Curves as needed — every block can be
   rearranged, collapsed or hidden to fit how you work.
4. Click **Export…** to choose an output folder/format and save the result.

## Batch import

Open it from the toolbar's **Import Images…** button (⌘I). It processes many
photos in one run:

1. Choose a **Processing Mode** for the whole batch — Solo, Classic Trichrome, or
   Color Trichrome.
2. In a Trichrome mode, point it at a folder of R/G/B files (matched
   automatically by a filter keyword in the filename, or manually), pick the
   **Auto-Import Rules** (which filter feeds which channel — RGB Trichrome, IR,
   Aerochrome, or a custom mapping), and optionally auto-align each triplet
   on import. In Solo mode, just select the individual images or a folder.
3. Click **Import** — the new photos are added to the filmstrip, ready to
   edit and export like any other photo in the session.

## License

MIT — see [LICENSE](LICENSE). The app bundles open-source libraries and
icons under their own licenses, listed in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
