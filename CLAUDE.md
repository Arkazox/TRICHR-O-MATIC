# Trichr-o-matic

macOS PySide6 app that recomposes a color image from three B&W photos shot
through R/G/B (or IR/Aerochrome/custom) filters. Packaged as a standalone
`.app` with PyInstaller. See `README.md` for user-facing features/usage,
`CHANGELOG_EN.md`/`CHANGELOG_FR.md` for the user-facing release history.
Display name is "Trichr-o-matic" (window title, Finder/.app name); the
Python package (`trichrome/`), class names, and the `ORG_NAME`/`APP_NAME`
QSettings domain (`"TrichromeMaker"`) are unrelated internal identifiers —
left as-is so renaming the app doesn't reset users' saved sessions.

> **Note on this file**: it used to be a strict chronological development
> log (every pass, every revert, dated). It was reorganized (2026-09-08)
> into a reference describing the **current** app - by feature area, not by
> date - since the chronological form had accumulated a lot of narrative
> about options/mechanisms that were later renamed, superseded, or removed
> outright, making it easy to act on stale information. Only genuinely
> load-bearing "why" reasoning and hard-won gotchas are kept; a handful of
> abandoned approaches are flagged briefly so they aren't retried blindly.
> Keep updating it after substantial changes, but prefer editing the
> relevant feature section over appending a new dated paragraph - if a
> change makes a paragraph wrong, fix that paragraph.

## Running & building

```bash
source venv/bin/activate        # venv already exists at repo root
python3 main.py                 # run from source, no rebuild needed
./build_mac.sh                  # -> dist/Trichr-o-matic.app (bumps nothing itself)
```

Version string and icon live in `trichrome.spec` (`CFBundleShortVersionString`,
`icon="resources/icon.icns"`). Bump the version there before a release build;
don't touch the icon path unless the user explicitly asks for a new icon.

**`build_mac.sh` resets the developer machine's remembered session on every
build**, right after the PyInstaller build and changelog PDF regen: a small
inline Python snippet clears `last_session_file_path` and the legacy
`session_items` QSettings array/`session_current_index` (the exact keys
`_restore_session`/`_legacy_restore_session` read at launch — see the
session-persistence note below) in the real `TrichromeMaker`/`TrichromeMaker`
domain. This is deliberately narrow — only session/photo-import state is
cleared; layout presets, language, and window/block layout (all in the same
QSettings domain) are untouched. **Why**: so testing a freshly built version
always starts from a genuine empty state (must explicitly Open/New Session)
instead of silently reopening whatever session/photos happened to be open on
this Mac from the previous build.

## Terminology (user's vocabulary)

The user refers to UI regions with specific French terms — use this mapping
when parsing their requests, since it doesn't always line up 1:1 with code
identifiers:

- **Barre d'outil** = the top toolbar (`self.top_toolbar`), conceptually
  split into left/middle/right zones by `toolbar_spacer_left`/
  `toolbar_spacer_right`.
- **Panneau outil de gauche** / **panneau outil de droite** = `left_container`/
  `right_container` (both `BlockReorderZone` instances — see "The block
  system" below). **Fenêtre Preview** (center) = `canvas_container`.
- **Barre des vignettes** (below the preview) = the carousel/filmstrip.
- **Barre de preview** (above the preview, display + sort controls) = the
  zoom/fit/fullscreen/sort row above the canvas.
- Inside a tool panel, each **"bloc"** is one independently movable/
  hideable/collapsible block (`_ALL_BLOCK_KEYS` in `main_window.py`):
  - **Fichiers** = `import_panel` (key `"files"`)
  - **Traitement Trichrome** = `independent_channels_group` (key
    `"channels"` — the 3 `ChannelPanel` R/G/B blocks, plus Auto Align and
    Lock Layer Position; named "Independent Channels", then "RGB Channels",
    now "Trichrome Process" — only the display title changed, the
    identifier is still `channels`/`independent_channels_group`)
  - **Histogramme** = `histogram_box` (key `"histogram"`)
  - **Light** = `light_panel` (key `"light"` — brightness/contrast/
    exposure/highlights/shadows/gamma/black&white points, plus Negative)
  - **Color** = `color_panel` (key `"color"` — temperature/tint/
    saturation, white balance eyedropper, plus a Black & White toggle)
  - **Recadrage** = `crop_panel` (key `"crop"`)
  - **Courbes** = `curves_panel` (key `"curves"`)
  - **Scan** = `scan_panel` (key `"scan"`)

## Code map

- `main.py` — entry point.
- `trichrome/model.py` — data model: `ChannelLayer` (one R/G/B shot: image
  arrays, alignment dx/dy/scale/rotation, tone curve, `quarter_turns`),
  `GlobalCorrection` (Light/Color/Curves/Black&White fields for the
  composed image), `CropSettings`, and `BatchItem` (one imported photo:
  its 3 `layers` + `normal_layer` (Solo-mode image) + `mode`
  (`"trichrome"`/`"normal"`) + `global_corr` + `crop` +
  `uid`/`capture_date`/`custom_order` used for filmstrip sorting).
- `trichrome/imaging.py` — pure image-processing functions (load, warp,
  tone curve, curves, compose, EXIF capture-date extraction). No Qt here.
- `trichrome/main_window.py` — the big one: UI construction, all signal
  wiring, undo/redo, session persistence, batch import orchestration,
  filmstrip sorting, the block/layout system. Most feature work touches
  this file.
- `trichrome/import_worker.py` / `export_worker.py` — QThread workers for
  batch import/export so the UI doesn't block.
- `trichrome/batch_window.py`, `batch.py`, `filters.py` — the separate
  batch-import window and filename/filter-matching logic.
- `trichrome/alignment.py` — ORB/ECC auto-alignment.
- `trichrome/i18n.py` — flat dict-based `i18n.tr("key", **kwargs)`, EN and
  FR blocks kept in parallel; add a key to both when adding UI text.
- `trichrome/scan_tool/` — the Scan feature's implementation (camera I/O,
  naming, manifest, capture worker) — see "Scan tool" below. Also runnable
  standalone via `python3 -m trichrome.scan_tool`, kept alive deliberately
  for separate beta testing even though the app's own **Scan** block
  (`trichrome/widgets/scan_panel.py`) is the integrated, actively-developed
  surface.
- `trichrome/widgets/` — custom widgets:
  - `block_header_bar.py` — the shared chrome every block is built from:
    `start_block_chrome()`/`finish_block_chrome()` (title, drag handle,
    collapse/close buttons), `BlockDragHandle` (the grip that starts a
    drag), `BlockReorderZone` (the drop target — see "The block system"),
    `make_disabled_message_label()`/`set_block_disabled()` (the yellow
    "Tool Disabled" banner + full-block gray-out).
    `CollapsibleSection` (in `controls.py`) is the smaller, per-panel
    collapsible sub-section (`ChannelPanel`'s Alignment/Light, Scan's own
    Device/Film/Scan Light/Save Location, Batch Import's Import Rules).
  - `curve_editor.py`/`curves_panel.py` — the Curves tool.
  - `crop_panel.py`, `global_panel.py` (Light/Color), `import_panel.py`
    (Files), `channel_panel.py`, `histogram_widget.py`, `scan_panel.py` —
    one file per block.
  - `info_bubble.py` — `InfoButton` (the shared "?" button class) and the
    two bubble shapes it opens, `InfoBubble` (rich text) and `ListBubble`
    (a scrollable list, used by Batch Import's unmatched-files hover).
  - `carousel_widget.py` — the filmstrip/grid view.
  - `svg_icons.py` — icon rendering (see "Icons" below).
  - Toolbar icon buttons (`rotate_toggle_button.py`,
    `fullscreen_toggle_button.py`, `filmstrip_toggle_button.py`,
    `sort_button.py`, `compare_button.py`, and the top-toolbar buttons
    built inline in `main_window.py`) are all `resources/icons/**/*.svg`
    files rendered/tinted at paint time by `svg_icons.py`.
- `resources/icons/` is organized by **where an icon is actually used**,
  reorganized 2026-09-08 from an earlier by-icon-family layout (which had
  drifted — e.g. `Preview/invert.svg` was actually a Light-panel icon) —
  pass the subfolder as part of the name, e.g.
  `SvgToolButton("Global/crop.svg")`. Top-level folders:
  - `Toolbar/` — icons used only in the top toolbar.
  - `Filmstrip/` — icons used only in the carousel/filmstrip and the
    preview bar above the canvas (zoom, fit, rotate, compare, sort,
    fullscreen, grid-view toggle).
  - `Tools/<block name>/` — icons used only within one specific tool
    block's own panel: `Tools/Crop/`, `Tools/Color Correction/` (Light +
    Color panels), `Tools/Trichrome Process/`, `Tools/Scan/`. A tool
    without its own subfolder (Files, Histogram, Curves) has no
    icons that are exclusively its own — everything it uses lives in
    `Global/`.
  - `Global/` — icons used across **more than one** of the areas above,
    or by shared infrastructure that isn't tied to one tool/one bar (the
    block system's own chrome — grip handle, collapse chevron, close
    button; the shared alert-dialog warning icon; the reset icon reused
    by several blocks' own headers; the R/G/B/Y channel-letter icons,
    shared by Trichrome Process, Histogram and Curves; the Mode-selector
    icons, shared by the Files block and the Batch Import window).
  - `Unused/<original folder name>/` — icons not referenced anywhere in
    `trichrome/` (confirmed via grep before moving each one, checking
    both real code and dynamic/f-string construction, not just a literal
    string match) — nested by whichever category they used to belong to,
    purely to avoid filename collisions and keep some provenance. This
    folder is the one place in the app where "unreferenced" is the
    **expected, documented** state, not something to clean up on sight —
    several of these are staged ahead of features that don't use them
    yet (a lot of the Scan-tool camera/photo-status icon set), and others
    are superseded assets kept in case they're wanted again. Don't delete
    anything from here without checking with the user first; when a new
    icon stops being referenced by any code, move it into the matching
    `Unused/` subfolder (or create one) instead of deleting it outright.

  `trichrome/paths.py` resolves the icons folder both from source and
  inside the frozen `.app`; `trichrome.spec` bundles `resources/icons`
  recursively, so new subfolders need no spec change. When adding a new
  icon reference, categorize it the same way: exclusive to one bar/tool →
  that folder; used in 2+ of them → `Global/`.

## Architecture & key patterns

### Session persistence — two mechanisms, one primary at launch

1. Explicit, portable `.trirgb` project files (`_collect_session_data`/
   `_build_restored_items_from_data`/`save_session_to_path`/
   `load_session_from_path`) — plain JSON, opened via File ▸ Open Session
   (⌘O) / Save Session (⌘S) / Save Session As (⌘⇧S) or the toolbar's save
   button. Every time `_session_file_path` changes (save/save-as/open/new
   session), go through `_set_session_file_path()` — it also mirrors the
   path into `QSettings` as `"last_session_file_path"`, which
   `_restore_session` reads on next launch to reopen that same file (full
   fidelity, the same code path as File ▸ Open Session).
2. Implicit, OS-scoped autosave-on-close via `QSettings(ORG_NAME, APP_NAME)`
   (`_save_session_state`/`_legacy_restore_session`, `ORG_NAME = APP_NAME =
   "TrichromeMaker"`) — a **fallback**, used by `_restore_session` at
   launch when there's no remembered `.trirgb` or reopening it failed.
   Note: `build_mac.sh` clears this state on every build (see above), so a
   freshly built `.app`'s first launch is always empty, not "fallback".

Every `BatchItem`/`ChannelLayer`/`GlobalCorrection` field that should
survive either path needs a matching read/write pair in **both**
mechanisms — `_save_session_state`/`_legacy_restore_session` (QSettings)
*and* `_collect_session_data`/`_build_restored_items_from_data` (`.trirgb`).
Both share the same tail via `_apply_restored_items()` for installing a
reconstructed `batch_items` list, and `_apply_restored_layout()` for
window-level state (panel/block layout, tool_side history is gone — see
"The block system" below) — extend those instead of duplicating them a
third time. `Layout Presets` are QSettings-only, deliberately **not**
part of `.trirgb` (a personal cross-session arrangement library, not
project content) — see "The block system".

`.trirgb` files are registered as a document type in `trichrome.spec`'s
`CFBundleDocumentTypes`; `main.py`'s `TrichromaticApp` catches the macOS
`QEvent.FileOpen` this generates and routes it to `load_session_from_path`
— note the event can arrive before `MainWindow` exists (buffered via
`pending_open_path`).

**Critical testing rule — read this before writing any test that touches
QSettings**: when testing, monkeypatch the **module-level**
`trichrome.main_window.ORG_NAME`/`.APP_NAME` to an isolated string first —
never run tests against the real `"TrichromeMaker"` domain, that's the
user's actual saved session. `mw.ORG_NAME`/`MainWindow.ORG_NAME` do **not**
work for this: `ORG_NAME`/`APP_NAME` are plain module globals, and every
method that builds a `QSettings(ORG_NAME, APP_NAME)` reads the bare name
via normal Python scoping (module globals), never `self.ORG_NAME` — so
setting a class or instance attribute of the same name is silently a
no-op that leaves every `QSettings` call still pointed at the real domain.
**This bug actually happened**: a test script patched a class attribute
instead of the module global, and every "isolated" test session in that
run silently overwrote the user's real saved Layout Presets. Correct
pattern:
```python
import trichrome.main_window as mwmod
mwmod.ORG_NAME = mwmod.APP_NAME = "SomeIsolatedName"   # before constructing MainWindow()
```
Confirm isolation actually held by reading back
`QSettings(mwmod.ORG_NAME, mwmod.APP_NAME)` afterward, not by trusting the
patch was applied to the right target.

### Unsaved-changes tracking

`MainWindow._edit_counter` piggybacks on the undo/redo stack instead of a
separate dirty flag — `push_undo`: +1, `undo`: -1, `redo`: +1.
`_saved_edit_counter` records its value at the last `.trirgb` save; they
differ ⇒ dirty (this correctly treats "undid back to exactly the saved
state" as clean). `_confirm_discard_unsaved_changes()` is the shared
prompt for any action that would discard the session (New Session, Open
Session, quit via `closeEvent`) — reuse it for any future
session-discarding action. It shows `widgets/unsaved_changes_dialog.py`'s
`UnsavedChangesDialog`, the app's own dialog look, not native
`QMessageBox` chrome.

### Alert dialogs — never native `QMessageBox` chrome

`widgets/alert_dialog.py`'s `show_alert(parent, title, text)` is a drop-in
replacement for `QMessageBox.warning`/`.critical` — renders as an
`AlertDialog` (tinted `warning.svg`, plain `QPushButton`, no native
chrome) with a single "Close" button. **Every** alert in the app goes
through it — `QMessageBox` is not imported anywhere in `trichrome/`
anymore; always reach for `show_alert` for any new one, never
`QMessageBox`.

`show_alert`/`AlertDialog` also take:
- `table_headers`/`table_rows` — a read-only `QTableWidget` (capped at
  160px) appended below the body text, for a variable-length list. `text`
  itself must stay a **fixed** paragraph that never grows.
- `table_tooltips` (one per row) and `row_action_label`/`row_action`/
  `row_targets` — a button next to the table, disabled until a row is
  selected, calling `row_action(row_targets[selected_row])` on click or
  double-click; returning `True` removes that row. Used by the missing-
  files relink flow (`on_locate_missing_files`) so a still-unresolved row
  can be relinked directly from the dialog.

### Undo/redo

Snapshot-based (`_snapshot_state`/`_restore_state`), deep-copies
`batch_items`. Any new `BatchItem`/`ChannelLayer`/`GlobalCorrection` field
must be threaded through `_snapshot_state`'s `BatchItem(...)` call or it
silently resets on undo — **unless** it's already a field of an object
that gets `copy.copy()`'d whole (e.g. any new `GlobalCorrection` or
`ChannelLayer` field is automatically included; only `BatchItem`'s own
top-level fields need explicit threading since it's reconstructed
field-by-field).

**Mutable-field aliasing trap**: a shallow `copy.copy()` shares mutable
sub-objects (e.g. `GlobalCorrection.curves`, a `dict[str, list[tuple]]`)
between the live model and a pushed undo snapshot. The fix isn't a
deep-copy but a discipline: every write site must **replace** such a
field with a freshly-built object, never mutate one in place.

### BatchItem identity & sorting

`uid` is assigned once (monotonic, never reused), used as a stable
identity for reordering and as the import-order sort key. After restoring
a session, `ensure_batch_item_uid_above(...)` must be called so new items
in the new process can't collide with restored uids. Filmstrip sort:
`MainWindow.sort_mode`/`sort_reversed` + `BatchItem.custom_order` — a
drag always writes a fresh `custom_order` sequence so re-applying
`_apply_current_sort()` reproduces the same on-screen order.

### Missing/moved source files

Both session-restore paths keep `ChannelLayer.path` set to the
last-known path even when the file can't be loaded (moved/deleted) —
`ChannelLayer.is_missing()` (`path` set but `has_image()` false) is the
derived check used everywhere. A `BatchItem` is only dropped on restore if
*no* channel/normal_layer ever had a path at all.
`MainWindow.recompute_preview()` feeds every missing channel of the
*active* item to `missing_files_banner` (a `QFrame` above the canvas)
showing which channel(s) and last-known path(s) are missing.
`on_locate_missing_files()` (the banner's Locate button) relinks missing
channels across every selected photo by searching a chosen folder for a
matching basename; anything it can't find is listed in a `show_alert`
table with a per-row **Relink…** action to pick the exact replacement
file directly.

### The block system

Every tool (`files`, `channels`, `histogram`, `light`, `color`, `curves`,
`crop`, `scan`) is its own independently positioned/visible/collapsed
**block** — this superseded an earlier exclusive left/right tool-switcher
design entirely (that mechanism, `tool_side`/`_tool_registry`, no longer
exists in the code).

- **State**: `self.block_side: dict[str, str]` ("left"/"right"),
  `self.block_visible`, `self.block_collapsed`, `self.left_block_order`/
  `self.right_block_order: list[str]` — every block assigned to that side,
  in order; **hidden blocks keep their slot** so re-showing one restores
  its last position. `_DEFAULT_BLOCK_SIDE`/`_DEFAULT_BLOCK_VISIBLE`/
  `_DEFAULT_LEFT_BLOCK_ORDER`/`_DEFAULT_RIGHT_BLOCK_ORDER` (near the top
  of `main_window.py`) are what `reset_layout()` restores: Files +
  Trichrome Process + Scan (hidden) on the left; Histogram + Light + Color
  + Crop (hidden) + Curves (hidden) on the right.
- **`_apply_block_layout()`** is the single place block state becomes
  real layout: clears and reinserts every block per its side's order
  list, sets visibility, refreshes each `BlockReorderZone`'s widget map,
  re-syncs the Tools-menu checkboxes, and forces both scroll areas to
  re-evaluate their width (`layout.invalidate()`/`.activate()` +
  `updateGeometry()` — needed because `removeWidget`/`insertWidget` don't
  reliably trigger `QScrollArea`'s own resize logic on their own).
- **Drag-and-drop**: `BlockDragHandle` (the small grip, the *only* part of
  a header that starts a drag) computes a scaled-down ghost pixmap with a
  white outline and starts a `QDrag` carrying a 1×1 transparent
  placeholder pixmap set via `drag.setPixmap()` once (not live-updated —
  see the gotcha below). `BlockReorderZone` (both side panels) is the drop
  target: it accepts a drag from *either* zone (that's what makes
  cross-panel moves work), computes an insertion point via
  `_insert_position()`, and draws a thin dashed blue line at the exact gap
  the drop would land in (`paintEvent`, not a whole-widget highlight — a
  full-block highlight was tried first and read as "replacing" the target
  block rather than inserting near it). `MainWindow._on_block_dropped(side,
  key, insert_index)` is the one handler for both same-panel reorder and
  cross-panel move.
  - **Abandoned approach, don't retry blindly**: a live drag-preview
    overlay (a second always-on-top `QWidget` following the cursor, with
    a red border once outside a drop zone) was tried twice and reverted
    both times — first because `QDrag.setPixmap()` calls after the drag
    starts aren't reliably honored on macOS, then because the overlay
    itself (a real top-level window) intercepted the OS-level native
    drag hit-testing, breaking every drop (everything resolved to
    "rejected"). The static single-pixmap approach above is what actually
    works. A "drop outside both panels removes the block" feature was
    also tried and removed at the user's request — a block is now only
    ever removed via its own close button or the Tools menu.
- Both side panels share **one** width range (`_SIDE_PANEL_MIN_WIDTH`/
  `_SIDE_PANEL_MAX_WIDTH`, `main_window.py`) — they used to differ, which
  is wrong once any block can be dragged to either side. Any block whose
  `minimumSizeHint()` doesn't comfortably fit that width will force a
  horizontal scrollbar on the whole panel — when adding buttons to a
  header row, check the panel's own `minimumSizeHint()` against this
  bound, not just how the row looks in isolation.
- **Tools menu** (`self.tools_menu`) lists all 8 blocks with independent
  checkable actions, synced to `block_visible`.
- **Window menu**: Close Window; Left/Right Panel + Thumbnails toggles
  (bare shortcuts I/O/P); the 4 built-in default-layout entries, each its
  own small submenu with **Load** + **Update** (no Delete); **Layout
  Preset** submenu (Save as Preset…, then Load/Update/Delete per custom
  preset); **Reset Layout** at the very bottom.
- **Layout Presets**: `_capture_layout_state()`/`_apply_layout_state()`
  capture/restore panel visibility + all 5 block fields, as a named
  QSettings-only snapshot (`self._layout_preset_names`,
  `layout_preset_data_{name}`). `_BUILT_IN_LAYOUT_PRESETS` (4 tuples of
  `(display name, i18n key, shortcut letter, source preset name)`) maps
  the toolbar's fixed **Trichrome / Color Correction / Crop / Scan**
  quick-switch slots onto real, user-editable custom presets
  (`NewTrichrome`/`NewColorCorrection`/`NewCrop`/`NewScan`) — the display
  names themselves are reserved (can't be overwritten via "Save as
  Preset…") but their underlying source presets are ordinary presets, so
  editing e.g. `NewCrop` and re-pressing **C** picks up the change
  immediately. `self.default_layout_group` (one exclusive `QButtonGroup`
  of the 4 toolbar buttons) + `_activate_default_layout(name)` is the one
  entry point for toolbar click / bare shortcut (T/E/C/S) / Window-menu
  item — wired via `clicked` (not `toggled`) so re-pressing an
  already-active one still reloads it. Activating the "Crop" slot also
  arms Crop's active mode (see "Crop tool" below); every other slot (and
  a plain preset load) turns it off.

### Sliders

`SliderSpin`/`_ResettableSlider` (`widgets/controls.py`) — the app's one
slider primitive. The default always sits at its own exact midpoint step
(`_value_to_fraction`/`_fraction_to_value` stretch `[min, default)` and
`(default, max]` to fill their own half of the track independently, so
this holds even when the default isn't the arithmetic midpoint — e.g.
gamma 0.1..4.0, default 1.0). The fill is drawn from that center point
out to the handle, plus a small center tick, so every slider reads "which
side of default, how far" at a glance. Handle is fully custom-painted
(hollow ring at rest, filled while dragging).

`ClickToEditValue` — a bare right-aligned number, click to edit inline
(no native spin-box arrows). `percent_mode=True` additionally remaps the
*displayed* number to -100..100 with 0 at the default (Lightroom
convention) — used for every Light/Color slider, since their real unit
(a multiplier, an exponent, an additive shift) isn't independently
meaningful on its own. Left `False` for a slider whose unit already means
something (alignment dx/dy/scale/rotation, Crop's Straighten degrees,
Exposure in EV). The **stored/exported value is always the real unit**
either way — only the displayed number changes.

`CollapsibleSection` (also in `controls.py`) is the smaller per-panel
collapsible sub-section, reused by `ChannelPanel`, Scan's own sections,
and Batch Import's Import Rules — its collapse chevron uses the same
rotating-SVG convention as a block's own collapse button
(`SvgToolButton.set_rotation(degrees)`, `-90°` when collapsed).

### Info buttons

`widgets/info_bubble.py`'s `InfoButton(info_key, color=None)` is the one
shared "?" button class used everywhere in the app (block headers, the
Mode selector, Batch Import's Import Rules, etc.) — looks up
`i18n.tr(info_key)` fresh every time it's shown (so a language switch is
picked up automatically), and opens on **click** (stays open until an
outside click, like a normal popup) or after **hovering statically for
~0.5s** (closes as soon as the cursor leaves — the two triggers
deliberately behave differently). Pass `color="#5b9bd5"` (this app's one
accent blue) for a visually "more important" callout ring instead of the
default plain style. `ListBubble` (built on the same `_PopupBubble` base
as `InfoBubble`) shows a scrollable list instead of rich text — used by
Batch Import's unmatched-files-on-hover summary.

### Icons

Prefer reusing/adapting an existing SVG (duplicating + rotating via a
plain `transform`, or recoloring) over hand-drawing a new one — this
project stopped hand-drawing icons in `QPainter` once SVG assets became
available. When a real matching Lucide/Tabler icon exists upstream, fetch
and re-wrap it in this project's own SVG attribute convention rather than
approximating it by hand. `svg_icons.py` provides:
- `SvgToolButton`/`SvgCheckableToolButton`/`SvgTwoStateToggleButton`/
  `SvgLetterToggleButton`/`SvgColorCheckableToolButton` — the button
  family, all tinted at paint time from a single-color glyph.
- `tinted_svg_pixmap`/`tinted_svg_icon` — flat single-color tint.
- `raw_svg_pixmap`/`raw_svg_icon` — renders an SVG's own embedded colors
  verbatim (for a genuinely multi-color icon, e.g. the Mode selector's
  layered-stack icons).
- `gradient_tinted_svg_pixmap`/`gradient_tinted_svg_icon` — a
  `QLinearGradient` tint (used by the Scan tool's RGB Light icon).
- `rotated_tinted_svg_pixmap`/`SvgToolButton.set_rotation()` — a rotated
  variant, used by every collapse chevron.
- **When an icon renders smaller or oddly cropped next to sibling icons**,
  check its `viewBox` for extra padding, or a stroke extending past the
  path's own bounding box — both have caused real, hard-to-spot sizing
  mismatches here. Fix the `viewBox` crop, don't fight it with app-side
  scaling.

## Modes & film type

Every photo (`BatchItem`) is one of two **modes**, chosen via the Files
block's **Mode** combo (`ImportPanel.mode_combo`, icons + text, styled to
blend into the block rather than look like a native control):

- **Solo** (`BatchItem.mode == "normal"`) — a single, already-composed
  photo (color or B&W), loaded via `imaging.load_color()` into
  `BatchItem.normal_layer` and edited as-is. No channel recomposition;
  Trichrome Process (the RGB-channel block) is unavailable and grays out.
- **B&W Trichrome** (`mode == "trichrome"`, `ChannelLayer.harris_shutter
  == False`) — the classic case: 3 B&W shots through R/G/B filters,
  flattened to luminance on load (`imaging.load_grayscale`) and
  recomposed.
- **Color Trichrome** (`mode == "trichrome"`, `harris_shutter == True`) —
  3 real color photos, each contributing its own real R, G, or B channel
  (`imaging.load_grayscale(path, channel="R"/"G"/"B")`) instead of being
  flattened — a genuine "Harris Shutter" look.

`ChannelLayer.harris_shutter` is the one field that means "how to decode
this Trichrome channel" — it's a real per-channel field (mirrors
`invert`'s architecture) so undo/redo and cross-photo consistency work
for free. `BatchItem.normal_layer.harris_shutter` is a **vestigial**
field on the same dataclass (always `True`, set at every fresh-Solo-photo
creation site) — a retired mechanism used to read it for a Solo-only
"Black & White" concept; nothing reads it for a live decision anymore
(see below), but it's still threaded through both persistence mechanisms
since removing the field would touch the session-file schema.

**Loading photos and Auto Align/Lock Layer Position live in the
Trichrome Process block** (Trichrome modes only); Solo mode instead shows
a single "Load Image" button in Files. Dragging image files from Finder
onto the filmstrip, onto the grid view, or (2026-09-08) onto the preview
canvas itself while it's showing its empty-project placeholder, or a
Batch Import in Solo Processing Mode, all add new photos as Solo — the
canvas drop reuses the exact same `MainWindow.on_carousel_files_dropped`
handler as the filmstrip/grid, via `CanvasWidget.files_dropped`
(`widgets/canvas_widget.py`'s `_ImageLabel` only accepts file drops while
`CanvasWidget.clear_image()` has armed `set_accept_file_drops(True)` —
disarmed again the instant a real image is shown via `set_image_rgb`/
`set_image_gray`, since that same canvas area is already used for align-
drag/crop-drag/eyedropper interactions once there's something to display).
The placeholder text itself (`canvas_placeholder` i18n key) invites both
actions: "Load an image via the "Import" button, or drag an image file
here."

**Dropping the very first photo(s) into a project no longer leaves a
stray empty thumbnail (fixed 2026-09-08).** A fresh session/New Session
always starts with one untouched, genuinely-empty `BatchItem` (no image
in any of its 3 channels or its `normal_layer`) - `MainWindow.
_append_new_batch_items()` (the shared tail behind
`on_carousel_files_dropped` and Scan tool add-to-session) now drops the
existing batch first when *every* item in it is empty
(`_is_batch_item_empty()`, the same "genuinely empty" criterion the
session-restore paths already use) before appending the new photo(s) -
so importing the first real photo(s) into an empty project replaces that
placeholder instead of leaving it behind as a dangling first thumbnail.
Only fires when the *entire* existing batch is empty - a real photo
already in the project is never removed.

### Black & White and Negative — mode-agnostic, live in Light/Color

- **Negative** (`ChannelLayer.invert` / `normal_layer.invert`) lives in
  the **Light** panel's header (an icon button, dims when off) and
  applies uniformly in every mode — `_active_invert_state()` reads
  whichever of `normal_layer.invert`/`layers[0].invert` the active mode
  actually uses.
- **Black & White** (`ColorPanel.black_white_button`, in the **Color**
  panel's header) is a genuine luminance-weighted grayscale conversion
  (`imaging.apply_black_white`, BT.601 weights — the same weights used
  everywhere else luma is computed in this app) applied as the **very
  last** step of the pipeline, after curves. `GlobalCorrection
  .black_white_active: bool` drives it, threaded through
  `apply_global_correction`'s trailing `black_white` parameter — checking
  it disables Color's sliders/white-balance/Reset (but not the toggle
  itself). Available in every mode, unlike the old Files-block "B&W Film /
  Color Film" buttons this replaced (see below).

**Retired mechanism, don't resurrect without checking with the user
first**: an earlier "Film type" concept lived directly in the Files block
as `bw_film_button`/`color_film_button`, and a separate Solo-only
mechanism (`BatchItem.saturation_before_bw`, `MainWindow._solo_bw_active()`,
`ColorPanel.set_disabled_message`) forced `saturation = 0.0` to fake
black & white on a Solo photo. Both were removed once the real
`black_white_active` mechanism above shipped — the *only* controls left
for film type today are the Mode combo (Trichrome B&W vs. Color) and the
Color panel's own Black & White toggle (any mode, a real conversion, not
a saturation hack).

### Batch Import window

The same 3-way choice (`processing_mode_radios`, a **Processing Mode**
block at the top of the window, framed/card-style radio buttons matching
the Mode combo's icons) picks Solo/B&W Trichrome/Color Trichrome for a
whole batch:
- **Trichrome** modes show the existing **File Selection** section
  (renamed from "Input folder") — **Automatic** (files matched by a
  filter keyword in the filename; the exact filter-to-channel mapping —
  Classic, IR Trichrome, Aerochrome, or a fully custom one — is chosen in
  the **Import Rules** section, renamed from "Advanced Options", with its
  own accent-blue "?" info button explaining automatic matching and a
  second "?" next to the radio row explaining each of the 4 mapping
  modes), **Sequential** (renamed from "Semi-automatic" — files already
  in R,G,B order), or **Manual** (pick each column yourself). The
  Automatic mode's unmatched-file list is a compact count with the full
  filename list shown in a popup on hover (`ListBubble`), not an
  always-expanded block of text.
- **Solo** mode shows a much simpler `solo_group`: Select Image(s)… /
  Select Folder… / Clear, reusing `MainWindow.on_carousel_files_dropped`
  for the actual import (the same path Finder drag-and-drop uses).

`MainWindow.start_batch_import(..., harris_shutter)` takes the decode
strategy as an explicit parameter from the Batch window's own Processing
Mode choice — it does **not** read the main window's currently-active
photo's own Harris Shutter state (a real bug, fixed).

## Editing tools

### Trichrome Process (per-channel)

Per-channel alignment (drag on canvas / Shift+scroll scale / Alt+scroll
rotate / sliders — dx/dy/scale/rotation, real units, not percent-mapped)
and tone (exposure → black/white point → gamma → brightness → contrast →
shadows/highlights, in that pipeline order — see `imaging.apply_tone_curve`).
**Auto Align** (ORB + RANSAC, falling back to ECC) and **Lock Layer
Position** (which channel is the reference/anchor — geometric anchor for
canvas size/orientation) live at the top of this block, above the 3
`ChannelPanel`s. The whole block, including its header buttons, grays out
with a yellow "Tool Disabled" message (`set_block_disabled`) whenever the
active photo is in Solo mode.

### Light & Color

Two peer blocks (split from an earlier single "Global Correction" panel):
- **Light**: Exposure (EV, multiplicative, applied first — a real
  photographic-stops control, distinct from Brightness's flat additive
  offset applied last), Brightness, Contrast, Highlights, Shadows,
  Whites, Blacks, Gamma, plus **Negative** in the header (see above).
- **Color**: Temperature, Tint, Saturation, a white-balance eyedropper
  (`pick_white_balance_btn` — solves the pre-white-balance pixel
  algebraically so it doesn't double-count the old correction), plus
  **Black & White** in the header (see above).

Every Reset button in the app (both of these, per-channel resets, Crop's,
Curves') greys out whenever there's nothing to reset — recomputed on
every edit in `recompute_preview()`.

**Solo (B&W) preview** of a Trichrome channel (`ChannelLayer.solo`) also
applies Global's own Light fields on top of that channel's own tone
curve (not Color fields — temperature/tint/saturation are meaningless on
a single grayscale channel), so toggling Solo doesn't make Light sliders
look like a no-op.

### Crop

`CropPanel`: aspect ratio (presets + custom + "original" default + "free"
+ invert-orientation), straighten, mirror (independent H/V), a grid
overlay (3×3 / 2×2 / Golden Ratio / fixed-size squares / off), and a
header row of **Activate** + **Reset**. The interactive drag/resize
rectangle is drawn directly on the canvas.

**Active crop mode is decoupled from block visibility** — `self._crop_active`
is the one source of truth (not `block_visible["crop"]`), since the block
can now be shown in any custom layout without necessarily meaning "start
cropping". `_set_crop_active(active)` is the single place that changes
it: arms/disarms the canvas overlay, disarms the white-balance eyedropper,
and force-shows the block when activating (but deactivating never hides
it). Straighten/mirror/aspect-ratio/grid apply **live**; the rectangle
itself is a canvas-side-only proposal until **Enter** commits it into
`item.crop` (also deactivates); **Escape** discards the in-progress drag
and deactivates without touching layout. Activating the toolbar's "Crop"
default-layout slot also arms active mode; every other layout switch
(including Escape, and switching to another saved layout) turns it off.
The Crop tool's own preview always shows the full straightened/mirrored
frame (never the previously-applied crop) — every other view shows the
fully-cropped result.

### Curves

`CurvesPanel`/`CurveEditor` — 4 **independent** Y (master)/R/G/B curves
(`GlobalCorrection.curves: dict[str, list[tuple[float,float]]]`), composed
Y first then each of R/G/B on top (`imaging.apply_curves`), applied as
the pipeline's last step before Black & White. A channel-selector row
(`CURVE_CHANNEL_COLORS`) picks which curve you're editing; the curve line
and a translucent histogram behind it are both tinted to match, and that
background histogram always shows the image **before** curve edits (a
separate "reference histogram" path, frozen during a drag — see
`recompute_preview(update_curve_reference=...)`) so it never moves while
you're editing, unlike the main Histogram block which always shows the
final result.

- Click the diagonal line to add a point; drag reshapes it (both
  endpoints can move on both axes now — moving one past a neighbor is
  clamped, and a sampled `x` beyond the outermost points is flattened,
  not extrapolated, for a real black/white-point clip); double-click a
  non-endpoint point to remove it.
- The curve itself is a **monotone cubic Hermite spline**
  (Fritsch-Carlson correction) — smooth, no overshoot/ringing near a
  sharply-dragged point, unlike a naive cubic spline.
- Dragging is throttled to at most one full `recompute_preview()` per
  ~16ms (a `QTimer`, `_CURVE_RECOMPUTE_THROTTLE_MS`) — the model itself
  updates synchronously on every mouse-move, only the expensive
  recompute/repaint is coalesced, so nothing is ever lost, just
  visually a frame or two behind a very fast drag.
- The plot is kept square (`resizeEvent` pins height to width).

Handles use the exact same paint recipe as `_ResettableSlider`'s own
handle, per an explicit ask to keep one consistent "round handle" visual
language across the app.

### Histogram

Live Y/R/G/B curves (`compute_channel_histograms`, shared with the
Curves tool's reference overlay), drawn on a **linear** scale (tried
log1p, then sqrt, settled on plain linear — a single very dominant spike
can still dwarf the rest of the chart, which is what the clip-indicator
bars at the edges are for). Clipping indicators are computed against a
**coverage mask** (`imaging.compose_coverage_mask`) that excludes pixels
only present due to warp padding (a channel-alignment offset or
Straighten introduces real black/white border pixels that aren't genuine
over/underexposure) and scale their height/opacity with how much is
actually clipped rather than jumping straight to a fixed size. A pixel
eyedropper (`pick_button`) shows a live per-channel marker on hover,
independent of the Solo-channel isolation (`isolate_channel`/
`show_all_channels`, also linked to each channel panel's own Solo
checkbox).

### Preview resolution & HQ Preview

The live preview always composites from `imaging.make_preview()`'s
`~MAX_PREVIEW_DIM`-capped (1400px) arrays, never the full-resolution
source - `recompute_preview()`/`_recompute_preview_normal()` only ever
read `layer.image_preview`/`normal_layer.image_preview`. This keeps every
slider/curve/crop edit fast regardless of source resolution, but reads
visibly soft once zoomed in or in fullscreen - zoom/fullscreen just scale
up the same capped `QImage` (`canvas_widget.py`'s `_refresh_pixmap`), they
don't bypass the cap.

**HQ Preview** (the "HQ" toggle button next to Zoom 100%, 2026-09-08) is
an opt-in, idle-triggered full-resolution pass on top of that, not a
replacement for it: `on_hq_preview_toggled` sets `self.hq_preview_enabled`;
`_arm_hq_preview_if_enabled()` (re)starts `self._hq_idle_timer`, a
single-shot `QTimer` restarted on every `recompute_preview()`/
`_recompute_preview_normal()` exit - since `QTimer.start()` on an
already-running single-shot timer restarts its countdown, calling this on
every edit turns it into a settle-delay (fires `_HQ_PREVIEW_IDLE_MS` after
the *last* edit) rather than a throttle (contrast with the Curves tool's
own `_CURVE_RECOMPUTE_THROTTLE_MS`, which fires at most once per burst).
Once idle, `_recompute_hq_preview()` reuses `imaging.compose_trichrome`/
`compose_normal` - the same resolution-agnostic entry points
`export_worker.py` calls for a real export - on full-res source arrays,
then swaps the result into the canvas via the same `set_image_rgb`/
`set_image_gray` the low-res path uses (swapping in a bigger array "just
works": `_refresh_pixmap` always recomputes the on-screen size from
`zoom * source width`, so this doesn't disturb zoom/scroll position). The
next edit's own low-res `recompute_preview()` call overwrites it
immediately, so HQ only ever shows once things are still.

`_current_tone_params()`/`_current_global_params()` are the shared tuple-
builders both the low-res preview and this HQ pass call, so they can't
drift apart - don't reintroduce a separate inline copy of that
tuple-building in either place.

**No full-res path exists for Solo preview** (a preview-only view state,
never handled by `export_worker.py` either) - `_arm_hq_preview_if_enabled`/
`_recompute_hq_preview` both no-op while any layer's `solo` is set, same
for Compare mode (a transient before/after view, not worth a full-res
pass). The toggle itself stays enabled in both cases; it just has nothing
to do until you leave that state.

**Caching, and why it's split from the export path**: `_full_res_image`/
`_full_res_color_image` (used by `export_worker.py`) deliberately do
*not* cache their result onto `layer.image_full` - a big batch export
processes many items in sequence and must not retain every one's full-res
array in memory just because it was touched. HQ Preview's own
`_full_res_image_cached`/`_full_res_color_image_cached` wrap those same
loaders but *do* stash the result onto `layer.image_full`, so repeated
edits to the *same* photo don't re-read/re-decode from disk on every
single idle tick - only the first HQ pass on a given photo pays that cost
(a RAW source's `rawpy` decode in particular can take a second or more
per channel); every further tweak just re-runs the cheap numpy compose/
crop step. This does mean a session where you HQ-preview many different
large (especially RAW) photos in a row will accumulate their full-res
arrays in memory for the rest of the session - no eviction exists yet if
that becomes a real problem in practice.

**Runs synchronously** (with `QApplication.setOverrideCursor(Qt.WaitCursor)`),
not in a background `QThread` - simpler, and acceptable since it only
fires once after editing stops, never on every tick; a first-time RAW
decode can still cause a noticeable pause. Not persisted across launches
(same as Compare/Crop-active) - resets to off on every relaunch.

## Scan tool

The **Scan** block (`widgets/scan_panel.py`) is the integrated,
actively-developed surface; `trichrome/scan_tool/` also runs standalone
(`python3 -m trichrome.scan_tool`), kept alive deliberately for separate
beta testing — the two share the same underlying `gphoto_backend`/
`naming`/`manifest`/`process` modules and the same QSettings domain
(`ORG_NAME`/`"ScanTool"`, distinct from the main app's session domain),
so scan configuration (roll name, counter, save folder, film/light
choice) is shared between them.

- **Device**: tethered capture over USB via the `gphoto2` CLI (not the
  Python bindings — no build toolchain needed). Confirmed working on a
  Fujifilm X-T3. **A real per-machine gotcha**: any camera-as-webcam
  driver (e.g. Fuji's own webcam System Extension) can hold its own PTP
  session and block tethered capture with error -53/-110 — check for that
  before assuming a code regression if capture stops working.
- **Film** (3 framed/icon radio buttons, styled like the Mode selector):
  **Black & White** (invert + a real Black & White conversion applied
  automatically on import), **Color** (invert only), **Color Reversal**
  (no changes — already positive).
- **Scan Light**: External / White / RGB, a `BacklightWindow` (a plain
  solid-color top-level widget you drag onto the display behind your
  rig). **RGB** triggers an automatic red→green→blue 3-shot sequence per
  Capture (a ~400ms settle delay between color swap and shutter),
  producing one Standard (non-Harris-Shutter) Trichrome triplet sharing
  one filename index with `_R`/`_G`/`_B` suffixes; a partial failure
  logs what succeeded but doesn't advance the counter.
- **Film-base color correction** (color negative's orange mask):
  **Sample Film Base** runs a dedicated 3-shot RGB-Light calibration
  sequence against the film's own clear/unexposed base; the eyedropper-
  style **pick from photo** alternative instead reads 3 already-warped
  channel arrays at a clicked point on an already-imported Trichrome
  photo (needed because the click position must be resolved through each
  channel's own alignment matrix, not just sampled naively). The stored
  reference is applied by dividing each channel's raw density by the
  sampled base **before** invert — session-scoped in-memory state, not
  persisted across relaunch.
- **Captures are added to the current session automatically** (no manual
  "Add to Session" step) — `_finish_capture()` builds and emits the
  finished `BatchItem` request straight to `MainWindow`, applying invert/
  Black-&-White/harris_shutter/film-base correction per the Film/Light
  choice active at capture time.
- The panel's own sections (Device/Film/Scan Light/Save Location) are
  independently collapsible (`CollapsibleSection`), persisted in the Scan
  tool's own QSettings domain.
- **Per-session scan settings**: `ScanPanel.settings_snapshot()`/
  `apply_settings_snapshot()` thread the panel's current configuration
  (folder, roll name, counter, film/light choice, etc.) through
  `.trirgb` only (`"scan_settings"` key) — deliberately not through the
  main app's QSettings-autosave fallback, since the Scan tool already has
  its own always-on cross-session persistence and mirroring it a second
  way would create two competing sources of truth.

## Testing & environment gotchas

The user runs the built app manually after each change and does their
own testing pass — **don't write throwaway verification test scripts by
default**. Reach for a quick headless script only when a change is
genuinely non-visual/hard-to-eyeball (a coordinate transform, a
persistence round-trip, a numeric claim), and keep it minimal:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -c "..."
```

Always isolate `QSettings` per the module-level `ORG_NAME`/`APP_NAME`
rule above. A handful of environment-specific traps have bitten real
testing sessions here — worth checking before assuming a genuine bug:

- **`isVisible()` vs `isHidden()`**: `isVisible()` requires the *whole*
  ancestor chain to have been `.show()`n, including the top-level window
  — a headless test that never calls `.show()` on `MainWindow` will see
  `isVisible() == False` even for a widget that's genuinely, explicitly
  shown. Use `not widget.isHidden()` in headless tests/checks instead.
- **`mw.close()` hangs forever headlessly** if there are real unsaved
  edits — `closeEvent` correctly shows the app's own modal "unsaved
  changes" confirmation, which waits for input that never comes under
  `QT_QPA_PLATFORM=offscreen`. Either don't make real edits before
  closing, or don't call `.close()` at all.
- **A second `MainWindow()` in the same process does not reliably pick up
  QSettings a first instance wrote** (reproduces even for old, unrelated
  fields — not a caching issue `settings.sync()` fixes). To simulate "the
  app restarted", call `_legacy_restore_session()`/
  `_build_restored_items_from_data()` directly on the **same** instance
  that saved, not a second constructed window.
- **A fake, nonexistent file path** for a `ChannelLayer.path` can hang
  `PIL.Image.open()` indefinitely under this environment's sandboxed
  `/tmp` access (confirmed via `faulthandler`, not a bug in the app —
  `FileNotFoundError` should raise near-instantly on a normal
  filesystem). Write a real tiny file into the scratchpad directory
  instead of pointing a test at a path that was never created.
- **`QDrag.exec()`'s own event loop consumes the mouse release** that
  ends a drag, so a `QAbstractButton`-based drag source (e.g.
  `BlockDragHandle`) never gets a normal `mouseReleaseEvent` for that
  press and can get stuck visually "down" — call `self.setDown(False)`
  explicitly right after `drag.exec(...)` returns.
- **A real interactive drag-and-drop gesture, a genuine mouse hover held
  motionless for N seconds, or real camera hardware** can't be driven
  headlessly at all — only the resulting event-handling logic (once Qt
  delivers a synthetic `QEvent`, or a mocked backend call returns) can be
  exercised this way. Always say so explicitly rather than claiming a
  visual/tactile/hardware behavior is "verified" when only its downstream
  logic was.
- **Offscreen font-metrics don't match real macOS rendering** — a width
  measured via `minimumSizeHint()` under `QT_QPA_PLATFORM=offscreen` is a
  useful *relative* signal (did this change get smaller/bigger) but not a
  reliable *absolute* one; a real "does this actually fit" claim needs
  the user's own pass in the running app.

## Roadmap

A running todo list, not tied to version numbers — update it as items are
picked up/finished rather than reorganizing it per release.

**Major features:**

- **Metadata panel** — planned for later. Not yet specified: what fields
  (presumably EXIF from the source photos and/or the composite's own
  derived info), where it lives in the UI, whether it's per-channel or
  per-composite, read-only or editable. Don't start without a real
  functional spec.
- **RAW file support** — core decode landed 2026-09-08 and confirmed
  working by the user against real captures from the Scan tool; general
  Import/Files/drag-and-drop widened the same day. Still not verified:
  a real end-to-end batch import of `.RAF` triplets through the Batch
  Import window itself (only its filename-matching logic was checked
  with empty stub files, not a real decode).
  - **Decode** (`imaging.py`): `load_grayscale`/`load_color` (the sole
    choke points every caller already goes through) branch on
    `is_raw_path()` and decode via `_load_raw_rgb_uint16()`
    (`rawpy.imread(...).postprocess(use_camera_wb=True,
    no_auto_bright=True, output_bps=16)` — sRGB output, not linear, so a
    RAW source converges into the exact same uint16-normalization/
    channel-collapse tail the PIL path already had) instead of
    `PIL.Image.open()`. `requirements.txt` gained `rawpy>=0.21`;
    `trichrome.spec`'s existing `collect_all()` loop (previously
    `cv2`-only) also bundles `rawpy` now — a prebuilt macOS arm64/cp312
    wheel bundles `libraw_r.dylib` + its own deps inside the wheel
    itself, same self-contained shape as `opencv-python-headless`, so no
    extra system dependency. `extract_capture_date()` needed no change —
    its existing PIL-open-with-fallback-to-mtime already degrades
    gracefully on a RAW file it can't parse, just without a real EXIF
    date.
  - **One shared extension list, not three.** `imaging.py` is now the
    single source of truth: `RASTER_EXTENSIONS` (the original PNG/JPEG/
    TIFF/BMP set) + `RAW_EXTENSIONS` (`.raf`/`.cr2`/`.cr3`/`.nef`/`.nrw`/
    `.arw`/`.srf`/`.sr2`/`.dng`/`.orf`/`.rw2`/`.pef`/`.raw`) =
    `IMPORTABLE_EXTENSIONS` (a tuple, not a set, so it also works
    directly with `str.endswith()`), plus `qt_image_name_filter_patterns()`
    for building a `QFileDialog` name filter. `batch.py`/
    `carousel_widget.py`/`batch_window.py` — previously 3 independent,
    hand-typed copies of the same PNG/JPEG/TIFF/BMP list — now all import
    `imaging.IMPORTABLE_EXTENSIONS` instead. Every RAW extension added to
    `imaging.py` in the future automatically reaches every consumer.
  - **Every file-selection surface now accepts RAW**: the Files block's
    per-channel Load and Solo-mode Load Image (`main_window.py`'s
    `load_image`/`load_normal_image`), the missing-file relink dialog
    (`_relink_one_channel_interactively`), the Batch Import window's Solo
    image/folder pickers and Manual/Semi-automatic per-file pickers (all
    6 `QFileDialog` name-filter sites now build their filter string from
    `imaging.qt_image_name_filter_patterns()` instead of a hardcoded
    `*.png *.jpg ...` literal), Finder drag-and-drop onto the carousel/
    grid view, and the Batch Import window's Automatic-mode filename-
    triplet matching (`batch.find_triplets`, confirmed headlessly that a
    `photo_R/G/B.RAF` set is now detected as one triplet).

**Smaller items:**

- ✅ Every remaining native `QMessageBox.warning`/`.critical` call (image
  load errors, mode-switch reload errors, session load/open errors, auto-
  align failures, batch import/export validation) now goes through
  `show_alert` — the app's own `AlertDialog` look is used everywhere;
  `QMessageBox` is no longer imported anywhere in `trichrome/`.
- Do a pass over how the different tools relate to each other in the
  processing pipeline — clarify their actual order (which one applies
  before/after which), both internally and for the user (the Curves
  section above documents the current order; consider surfacing it in
  the UI itself, not just this file).

## Changelog workflow

`CHANGELOG_EN.md`/`CHANGELOG_FR.md` are the **user-facing** release
history — what changed and why it matters to someone using the app, in
plain language, as opposed to this file's implementation-level detail for
development. Two parallel files, not one bilingual file — keep both in
sync (same sections, same version boundaries) but write each as natural
prose in its own language. `CHANGELOG_EN.pdf`/`CHANGELOG_FR.pdf` are PDF
copies regenerated automatically by `build_mac.sh` (via
`scripts/generate_changelog_pdf.py`) on every build.

The **Unreleased** section at the top always lists what's changed since
the last version was actually built, plus a running list of what's
planned next.

**Workflow — do this whenever the user asks to bump the version and
build**, *before* touching `trichrome.spec`:
1. In **both** changelog files, turn `## Unreleased` into a new dated
   version entry (`## vX.Y.Z — YYYY-MM-DD`, today's actual date) —
   rewrite/tighten the wording into a single coherent release note rather
   than a raw per-feature diary. Keep the "Remaining tasks for future
   versions" framing for anything still open.
2. Leave a fresh, empty `## Unreleased` section at the top of both files.
3. Bump `trichrome.spec` and run `./build_mac.sh` — the changelog PDF
   regen is the build script's own last step, don't run it separately.
4. Commit the changes (git repo at the project root, GitHub remote
   `origin`) — a version-bump/build request implicitly includes
   committing afterward. Message convention: `"vX.Y.Z"` as the summary
   line, plus a second commit for the PDFs the build regenerates.
5. **Push to `origin` right after committing** — this auto-push
   authorization is scoped to version-bump/release commits specifically,
   not a blanket standing push authorization for any other commit. If
   `git push` fails with an HTTPS credential error, run
   `gh auth setup-git` first and retry.

**Unlike this file** (updated after nearly every substantial change), do
**not** touch the changelogs incrementally after each feature/fix — leave
`## Unreleased` alone between bumps and reconstruct it from the
conversation/git history in one pass, only when the user actually asks to
bump the version and build. Don't let a version release with an empty or
stale changelog, but "stale" only starts to matter right before a bump.

## Language

The user writes in French; reply in English regardless of the language they use.
