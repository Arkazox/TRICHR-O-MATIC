# Trichr-o-matic — Changelog (English)

This file tracks what changed for users between builds, starting from
v0.4.0. It's the release-notes counterpart to `CLAUDE.md` (which covers
*how* things are implemented, for development) — this one covers *what
changed and why it matters to someone using the app*.

A French version lives in `CHANGELOG_FR.md`. A PDF copy of each
(`CHANGELOG_EN.pdf` / `CHANGELOG_FR.pdf`) is regenerated automatically by
`build_mac.sh` on every build (`scripts/generate_changelog_pdf.py`), so
they're always in sync with whatever `.app` you're holding.

The **Unreleased** section at the top always lists what's changed since
the last version was actually built, plus a running list of what's planned
next — so it doubles as a short roadmap snapshot, not just a history.

---

## Unreleased

### Remaining tasks for future versions
- **v0.5.0** (next): a **Curves tool**, plus integrating the standalone
  **Negative Scan tool** (tethered capture, already tested against a real
  camera) into the main app's toolbar.
- **v0.6.0**: a **metadata panel** - not yet specified.
- A handful of older error dialogs (image load errors, auto-align
  failure, session-load errors) still use the old system-dialog look and
  haven't been switched over to the app's own alert style yet.

---

## v0.4.5 — 2026-09-04

### Added
- **Fully customizable layout**: every panel - Files, RGB Channels,
  Histogram, Light, Color, Crop, and Scan - is now its own independent
  block. Drag a block by its grip to reorder it, move it to the other
  side panel, collapse it down to just its header, or close it entirely;
  a new **Tools** menu lists every block with a checkbox to bring closed
  ones back.
- **Layout Presets** (Window ▸ Layout Preset): save your own named panel
  arrangements, then load, update, or delete them anytime.
- **Quick layout switches**: the top toolbar's Trichrome / Color
  Correction / Crop / Scan buttons (and their T/E/C/S shortcuts) now jump
  straight to your own saved layout for that task - only one is active at
  a time. The same 4 shortcuts are also listed directly in the Window
  menu, with Update available right there too.
- **Reset Layout** (Window menu) restores the default panel arrangement
  in one click.
- Global Correction is now two separate panels, **Light** (exposure,
  brightness, contrast, highlights/shadows, black/white points, gamma,
  and Negative) and **Color** (temperature, tint, saturation, white
  balance eyedropper) - place each independently on either side of the
  screen.

### Changed
- The Crop tool's active drag mode is now a dedicated button in its own
  panel, separate from whether the panel is simply visible - it no longer
  turns on or off unexpectedly as you rearrange your layout. Escape now
  only exits crop mode without changing your layout; switching to a
  different saved layout automatically turns crop mode off, and switching
  to the Crop layout turns it back on.
- "Independent Channels" renamed to **RGB Channels**.
- Smaller, more consistent block headers throughout, with matching icon
  sizes.
- Language selection moved to the **Help** menu (Help ▸ Language).
- A newly installed or updated version no longer reopens whatever session
  was last open - the first launch always starts empty, so you'll need to
  open an existing session or start a new one.

### Removed
- The Crop panel's own Copy button (redundant with ⌘C / the filmstrip's
  Copy and Paste Crop).

---

## v0.4.4 — 2026-09-02

### Added
- **Window menu**: Close Window, and toggles for the Left Panel, Right
  Panel, and Thumbnails strip - each with its own keyboard shortcut
  (⌘W, I, O, P).
- **Exposure slider**, in both Independent Channels and Global Correction,
  sitting just above Brightness. Unlike Brightness (a simple lightening/
  darkening nudge), Exposure is a proper photographic stops (EV) control
  that behaves like a real exposure change - pushing it hard blows out
  highlights the way overexposing a shot would.
- **Histogram pixel picker**: a new eyedropper button next to the
  histogram's Reset. While it's active, hovering the preview draws a live
  marker showing exactly where that pixel falls on the Y/R/G/B curves.

### Changed
- Histogram redesign: subtle shadow/midtone/highlight guide lines in the
  background, and a softer, Lightroom-style look for the overlapping
  channel curves (a translucent fill with a crisp outline on top).
- The histogram's clipping indicators are more accurate: a thin, often
  invisible black/white border introduced by slightly misaligned channels
  (or the Straighten tool) is no longer mistaken for real over/
  underexposure, and the indicator now scales with how much is actually
  clipped instead of always jumping to the same size.
- Soloing a channel's B&W preview now automatically highlights that
  channel's scope in the histogram (the histogram's own Reset button
  turns Solo preview back off again), and now also reflects any Global
  Correction "Light" adjustments (Exposure, Brightness, Contrast,
  Highlights, Shadows, Whites, Blacks, Gamma) - it used to ignore Global
  Correction entirely while a channel was soloed. Color-only adjustments
  (Temperature, Tint, Saturation) are still skipped, since they don't mean
  anything on a black & white preview.

### Fixed
- **Harris Shutter Effect** now correctly remembers each photo's own
  setting - previously, switching between photos could leave the checkbox
  showing the wrong state, and in rare cases a batch export could
  reinterpret a photo's channels under the wrong mode. Both Harris
  Shutter and Negative can now also be applied to several selected photos
  at once - toggling one always sets every selected photo to the same new
  state, rather than flipping each photo's own existing setting
  individually.
- The missing-files relink window's "Relink…" button no longer gets stuck
  disabled after resolving one photo when others in the list still need
  fixing.

---

## v0.4.3 — 2026-09-02

### Added
- **White balance eyedropper.** A "Pick White Balance" tool in the Color
  section: click it, then click any point in the preview that should be
  neutral gray, and Temperature/Tint are set automatically to neutralize
  it. A "Reset" button next to it clears Temperature, Tint, *and*
  Saturation back to default.
- **Reset Light button.** Resets all 7 "Light" sliders (Brightness,
  Contrast, Highlights, Shadows, Whites, Blacks, Gamma) at once, next to
  the "Light" section title.
- **Recovery for missing/moved source photos.** If a session is reopened
  and some original R/G/B files were moved or deleted, the affected
  photo(s) no longer silently disappear from the filmstrip. The preview
  instead shows exactly which file(s) are missing and their last-known
  location, with a **Locate** button that relinks them (across every
  selected photo at once) by searching a folder you pick.
  - If some files still can't be found this way (e.g. renamed rather than
    moved), a dialog lists them in a table - hover a row to see its
    original file path, or select a row and click **Relink…** to pick that
    exact replacement file directly, without needing to go find it via the
    left panel.
- **Reset buttons now grey out** whenever there's nothing to reset -
  across the whole app: Global Correction, Light, Color, each channel's
  own alignment/color reset, and the Crop panel.
- **This changelog**, in English and French, with an auto-generated PDF
  copy of each kept in sync with every build.

### Changed
- Negative/invert moved into the Global Correction panel's header, next
  to Reset, as an icon (dims when off, lights up when on) instead of a
  text checkbox further down the panel - it's significant enough in
  trichromy (wrong polarity ruins the whole image) to sit up top.
- The small warning-glyph info icon that used to sit next to Reset
  (hinting that per-channel corrections wouldn't be cleared by it) was
  removed from the Global Correction header; the "?" info button
  explaining the panel's own scope stays.
- Alert/warning dialogs now match the app's own look instead of macOS's
  generic system dialogs.

---

## v0.4.2 — 2026-09-01

### Added
- **Harris Shutter Effect.** An opt-in mode (checkbox below the channel
  panels) for people who load 3 *color* photos instead of black & white
  ones - it extracts the real R/G/B channel from each source instead of
  converting to grayscale, for a genuine Harris Shutter look. Off by
  default; regular black & white trichromy is unaffected either way.
- **Redesigned sliders** across the whole app: every slider now visually
  centers on its own default, filling left or right from that point so
  it's obvious at a glance whether a value is above or below normal.
  Numbers are now a clean, click-to-type value instead of a spinbox, and
  color-correction sliders display as -100…+100 (Lightroom-style) while
  sliders with a real physical unit (pixels, degrees, zoom) keep their own
  unit.
- Export window: "Show in Finder after export" option.
- **⌘W** now closes the active secondary window (Export, Import, Help)
  without quitting the app.
- New crop aspect ratio preset: 7:5.
- Crop grid overlay: 4 styles to choose from (3×3, 2×2, Golden Ratio,
  fixed-size squares), replacing the old 2-option picker.

### Changed
- "Global Color Correction" renamed to **Global Correction**, and split
  into two clearly labeled sections: **Light** and **Color** (Temperature,
  Tint, Saturation, in that order).
- Crop aspect ratio presets reordered (most-square to widest) and the
  orientation icon now visually rotates to match your selection.
- The Crop and Global Correction panels now match each other exactly in
  layout, so switching between them doesn't shift anything on screen.

### Fixed
- Cropping with a locked aspect ratio near the edge of a photo no longer
  distorts the ratio.

---

## v0.4.0 / v0.4.1 — 2026-08-31

*(v0.4.1 was a same-day follow-up bugfix/polish pass on v0.4.0; changes
below cover both.)*

### Added
- **New Session**, a proper multi-photo session system, and the photo
  filmstrip's right-click menu (Reset All, Duplicate).
- Help menu content rewritten to match everything above.

### Changed
- Shortcuts reference reorganized into General / Navigation / Preview /
  Sliders sections; the "active channel" explanation moved into a live
  "?" info button next to each channel's Active checkbox.
- Sidebar layout polish: cleaner section titles, histogram split into its
  own block, larger/repositioned reset buttons.
- The tool switcher (Global Correction ⇄ Crop) moved into the top toolbar
  as two buttons, with **E** / **C** shortcuts.

### Removed
- A handful of unused, dead translation strings cleaned out during an
  English/French text audit.
