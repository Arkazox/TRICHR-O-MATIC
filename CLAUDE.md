# Trichr-o-matic

macOS PySide6 app that recomposes a color image from three B&W photos shot
through R/G/B (or IR/Aerochrome/custom) filters. Packaged as a standalone
`.app` with PyInstaller. See `README.md` for user-facing features/usage,
`CHANGELOG_EN.md` for the user-facing release history.
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
  batch import/export so the UI doesn't block. `hq_preview_worker.py` is
  the same pattern for HQ Preview's single-photo native-resolution
  recompute — see "Preview resolution & HQ Preview" below.
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
    Device/Camera Settings/Film/Scan Light/Save Location, Batch Import's
    Import Rules).
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
  (bare shortcuts I/O/P); the 4 built-in default-layout entries, each a
  single plain **Load** action (no Update/Delete — see below); **Layout
  Preset** submenu (Save as Preset…, then Load/Update/Delete per custom
  preset); **Reset Layout** at the very bottom.
- **Layout Presets**: `_capture_layout_state()`/`_apply_layout_state()`
  capture/restore panel visibility + all 5 block fields, as a named
  QSettings-only snapshot (`self._layout_preset_names`,
  `layout_preset_data_{name}`). The toolbar's fixed **Trichrome / Color
  Correction / Crop / Scan** quick-switch slots (`_BUILT_IN_LAYOUT_PRESETS`,
  4 tuples of `(display name, i18n key, shortcut letter)`) each apply a
  **fixed dict literal** (`_BUILT_IN_LAYOUT_STATES`), not a QSettings
  preset — reworked 2026-09-11 after an earlier design where they loaded
  ordinary user-editable presets (`NewTrichrome`/`NewColorCorrection`/
  `NewCrop`/`NewScan`) turned out fragile: those presets cluttered the
  Layout Preset submenu as ordinary-looking entries, and silently broke
  the toolbar buttons whenever cleared (which `build_mac.sh` now does to
  *every* custom preset on every build — see below). The display names
  (`"Trichrome"` etc.) are still reserved (can't be overwritten via "Save
  as Preset…" or appear in the Layout Preset submenu), but there is no
  longer any live preset backing them to edit — changing one of these 4
  default layouts means editing `_BUILT_IN_LAYOUT_STATES` directly.
  `self.default_layout_group` (one exclusive `QButtonGroup` of the 4
  toolbar buttons) + `_activate_default_layout(name)` is the one entry
  point for toolbar click / bare shortcut (T/E/C/S) / Window-menu item —
  wired via `clicked` (not `toggled`) so re-pressing an already-active one
  still reapplies it. Activating the "Crop" slot also arms Crop's active
  mode (see "Crop tool" below); every other slot (and a plain preset
  load) turns it off. **Every custom Layout Preset is deleted on every
  build** (`layout_preset_names` + every `layout_preset_data_*` key, in
  `build_mac.sh`, alongside the existing session-state reset) so a freshly
  built `.app`'s first launch always shows only the app's own defaults,
  never leftover presets from previous dev-machine testing.

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
- **Classic Trichrome** (`mode == "trichrome"`, `ChannelLayer.harris_shutter
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

**Switching a multi-channel Trichrome photo back to Solo** shows
`widgets/mode_switch_dialog.py`'s `ModeSwitchDialog` (title "Mode Change"/
"Changement de mode", renamed 2026-09-09 from "Trichrome Photo" —
generic-menus-safe now that this warning theme is what the title
communicates, not which mode you're leaving) asking which loaded channel
to keep editing, since the other 1-2 would otherwise become invisible.
Each R/G/B choice button carries the same solid circle-letter glyph
Histogram/Curves' channel toggles and Lock Layer Position use
(`SvgLetterToggleButton`'s own `Global/circle-letter-{r,g,b}.svg`, applied
here as a static `tinted_svg_icon` on an ordinary `QPushButton` rather
than a full checkable `SvgLetterToggleButton`, since each row is a
one-shot choice, not a toggle), styled with the same rounded/translucent
look as the Files block's own Mode combo (`_CHANNEL_BUTTON_STYLE` mirrors
`import_panel.py`'s `_MODE_COMBO_STYLE` rgba values/radius/hover
treatment) instead of the plain flat rectangle + colored left-border
strip it used before.

**`ModeSwitchDialog`'s size is fully content-driven, never dependent on
whatever size Qt/the parent window would otherwise hand it** (2026-09-10,
per the user's own ask - the body text must always display in full,
regardless of any external sizing influence). Two parts, both needed:
`detail_label.setFixedWidth(300)` (not `setMaximumWidth` - a word-wrapped
`QLabel`'s own `sizeHint()` reports its *unwrapped*, single-line width
whenever nothing has constrained it yet, so a mere maximum doesn't feed
into the size the layout computes, only how far it's allowed to grow
afterward; a genuinely fixed width is what makes `sizeHint()` report the
real multi-line wrapped height for that width), then
`root.setSizeConstraint(QLayout.SetFixedSize)` on the dialog's top-level
layout - this pins the dialog's actual size to that layout's `sizeHint()`
on every relayout, which is also what makes it immune to being resized
away from that afterward (confirmed empirically: forcing `dlg.resize()`
to a bogus size, before or after `.show()`, snaps straight back). Don't
reach for a plain `setFixedWidth()` on the dialog itself for this instead
- `SetFixedSize` overrides any width previously set directly on the
widget, computing its own from the layout's content, so width control has
to happen at the *content* level (the label's own fixed width above), not
the dialog's.

**The reverse direction — switching a Solo photo to either Trichrome
variant — shows the same `ModeSwitchDialog`** (2026-09-09, same title,
same R/G/B button look), asking which channel the active Solo image
should become, whenever that Solo photo actually has an image
(`self.normal_layer.has_image()` — skipped entirely for an empty photo,
nothing to assign). Body text is direction-specific
(`mode_switch_to_trichrome_dialog_text`, naming the actual target -
"Classic Trichrome" or "Color Trichrome" - via `import_panel.MODE_LABEL_KEYS`
read against `import_panel.is_harris_shutter_active()`, since the combo's
selection has already changed by the time this fires but
`harris_shutter_toggled` hasn't yet - same "read the combo directly"
convention `_load_image_from_path` already relies on); `ModeSwitchDialog`
itself takes the already-translated `text` as a parameter now rather than
hardcoding `mode_switch_dialog_text`, precisely so both directions can
share one dialog class. All 3 buttons always show here (`[True, True,
True]`), unlike the Trichrome-to-Solo direction which only offers already-
loaded channels - any of the 3 can receive the image, including one that
already has its own.
`MainWindow._assign_normal_photo_to_channel()` is the reverse of
`_switch_to_normal_mode()`: reloads the Solo photo's own file via
`imaging.load_grayscale(path, channel=... if harris_shutter else None)`
(the same decode call `_load_image_from_path` uses for a real per-channel
load) into the chosen `ChannelLayer`, resets that channel's own alignment/
tone (a fresh assignment, not an edit-preserving move), carries over
`quarter_turns`, and propagates `invert` to **all 3** channels (not just
the chosen one) to preserve the existing "trichrome channels share one
invert state" invariant (`on_invert_toggled`). The other 2 channels are
left completely untouched, same as `_switch_to_normal_mode`'s own
principle of never silently clobbering channels the user didn't touch.
Also explicitly calls `import_panel.set_filename(index, ...)` and
`_sync_panel_from_layer(index)` itself (fixed 2026-09-10, a real bug: it
only called the shared `_sync_import_and_channels_ui()` tail, which
refreshes the Mode combo and the Solo File Path row but never touches the
3 channel filename labels or their alignment/tone panel controls — every
*other* call site that changes a channel's `layer.path` does this
explicitly, e.g. `activate_batch_item`/`on_channel_swap_requested` — so
the very first Solo → Trichrome assignment for a freshly-imported item
kept showing "No image loaded" in the newly-assigned channel's row
despite the photo actually being loaded).

**Loading photos and Auto Align/Lock Layer Position live in the
Trichrome Process block** (Trichrome modes only); Solo mode instead shows
a read-only **File Path:** row in Files (`ImportPanel.normal_path_label`/
`normal_filename_label`) — no load/change button (removed 2026-09-09, per
the user's own ask, once it became clear drag-and-drop already covers
adding Solo photos; there is currently no way to replace an *already-
loaded* Solo photo's source file in place — deleting it and dropping a
new one is the only option — `MainWindow.load_normal_image`/
`_load_normal_image_from_path`, the button's old handlers, were deleted
outright as fully dead code once that button was their only caller).
The read-only **File Path:** label and the actual filename beside it
(`ImportPanel.normal_path_label`/`normal_filename_label`) share the exact
same `font-size` (2026-09-10, per a user report of the two looking
vertically "décalé"/offset) — mixing font sizes in one row means each
label's own line-height gets centered around the row's cross-axis
independently, so their text baselines land a couple pixels apart even
though both widgets sit in the same `QHBoxLayout`; this was far more
visible with real macOS font metrics than in headless testing (see the
font-metrics gotcha under "Testing & environment gotchas"). Both are also
given an explicit `Qt.AlignVCenter` on `addWidget()` to pin them to the
row's exact vertical center regardless of platform font quirks.

Dragging image files from Finder onto the filmstrip, onto the grid view,
or (2026-09-08) onto the preview canvas itself while it's showing its
empty-project placeholder, or a Batch Import in Solo Processing Mode, all
add new photos as Solo — the canvas drop reuses the exact same
`MainWindow.on_carousel_files_dropped` handler as the filmstrip/grid, via
`CanvasWidget.files_dropped` (`widgets/canvas_widget.py`'s `_ImageLabel`
only accepts file drops while `CanvasWidget.clear_image()` has armed
`set_accept_file_drops(True)` — disarmed again the instant a real image
is shown via `set_image_rgb`/`set_image_gray`, since that same canvas
area is already used for align-drag/crop-drag/eyedropper interactions
once there's something to display). The placeholder text itself
(`canvas_placeholder` i18n key) invites both actions: "Load an image via
the "Import" button, or drag an image file here."

**Swapping which photo is loaded into which channel** (2026-09-09,
Trichrome modes only): each of the Files block's 3 channel rows has a
`_ChannelFileBlock` (`widgets/import_panel.py`) — the channel's filename
label and its drag handle (`_ChannelSwapHandle`, reusing the same
`Global/grip-vertical.svg` glyph as a block's own drag handle,
`widgets/block_header_bar.py`'s `BlockDragHandle` — a different mechanism
and mime type, not a channel dragged into the block-reorder system)
grouped into one visual/interactive unit, sitting between the channel
label and the Load/Change Image button. Only the block itself calls
`setAcceptDrops(True)` — the label and handle inside it don't — so Qt
routes a drag hovering over either child straight to the block's own
dragEnterEvent/dragLeaveEvent/dropEvent (Qt walks up from the widget
under the cursor to the nearest ancestor with drops enabled); this is
what makes "drop on the filename" and "drop on the handle" behave
identically without duplicating the handling. Dropping one channel's
handle onto another channel's block swaps which photo — and that photo's
own alignment/tone edits — is loaded into each of the two channels;
`color_index`/`label` (slot identity), `is_reference` (the Lock Layer
Position anchor choice) and `solo` (a per-panel preview toggle) stay
pinned to their slot rather than following the photo.
`MainWindow._swap_channel_layers()` does this generically via
`dataclasses.fields(ChannelLayer)` minus those 4 pinned names, so any
future `ChannelLayer` field is swapped automatically without needing this
list updated — `on_channel_swap_requested()` is the one entry point (push
undo, swap, resync both channels' filename/alignment/tone panels,
recompute).

Two pieces of drag feedback, both explicit user asks (2026-09-09) rather
than just a functional drop target — and each iterated once already, per
further user feedback, before landing on this shape:
- The drag pixmap is a `_translucent_grab()` of the whole
  `_ChannelFileBlock` (filename text + grip icon together, grabbed in its
  normal, not-yet-highlighted appearance so the highlight is left behind
  at the block's original position instead) redrawn at 55% opacity with no
  border, rather than the bare grip icon trailing the cursor with nothing
  to show what's being moved. An earlier pass synthesized a small text-only
  tag (`_filename_drag_pixmap`, since removed) showing just the filename;
  replaced once the user asked for the filename+handle pair to visually
  travel together as what's actually being picked up, Finder-style.
- While the drag is in progress, `ImportPanel._set_filename_drag_state()`
  highlights the **whole `_ChannelFileBlock`** (`channel_file_blocks[i]`,
  not just the label inside it) of both sides of the prospective swap — a
  dashed outline on the channel being dragged (set once at drag start,
  cleared via `_clear_filename_drag_states()` once `drag.exec()` returns,
  drop or cancel either way) and a solid accent-blue outline+fill on
  whichever channel's block is currently under the cursor (set/cleared
  from `_ChannelFileBlock`'s own dragEnterEvent/dragLeaveEvent/dropEvent)
  — so which two channels would swap is visible *before* the drop commits
  to anything. Two earlier passes framed narrower/wider scopes instead:
  first the *whole row* (channel_label+filename+handle+Load/Change
  button) via an extra per-row container QWidget, dropped once nesting
  that frame around the filename label's own already-distinct look read
  as "des cadres dans des cadres"; then *only the filename label*, which
  the user found too narrow once the drag pixmap itself grew to show the
  handle too — "le bouton et le chemin d'accès ne forme qu'un bloc" is
  what settled it on exactly the label+handle pairing, no more/less.
  `_FILE_BLOCK_BASE_STYLE`/`_FILE_BLOCK_SOURCE_STYLE`/
  `_FILE_BLOCK_TARGET_STYLE` share the same border width/radius so
  toggling the highlight never changes the block's own size.

**`_ChannelFileBlock` needs `WA_StyledBackground` to paint its own
highlight at all** — a real gotcha, confirmed by grabbing the widget and
inspecting rendered pixels (2026-09-09): a bare `QWidget` doesn't paint
its own stylesheet border/background by default (only specific widget
types QStyleSheetStyle special-cases, e.g. `QLabel`/`QPushButton`, do)
— without `setAttribute(Qt.WA_StyledBackground, True)`, the container
painted nothing of its own, and Qt's stylesheet cascade instead let the
border/background leak onto whichever child would actually render it:
`filename_label` (a `QLabel`, no competing border of its own) ended up
drawing the highlight across only *its own* rect, while `swap_handle`'s
own explicit `border: none; background: transparent` (`SvgToolButton`'s
base style) opted it out entirely — the user's "inclure l'icône dans le
cadre bleu" report was exactly this: the highlight visibly stopped at the
label's edge, never reaching the handle. Fixed by setting
`WA_StyledBackground` on the block (so it paints its own border/background
across its full rect, itself) *and* giving `filename_label` an explicit
`border: none; background: transparent` of its own (so it stops
independently inheriting the block's border via the cascade now that the
block paints it) — without that second half, the fix would have
regressed straight back into two nested frames (the block's real one plus
the label's inherited one), the same "des cadres dans des cadres" problem
from before.

**Mode combo width** (`ImportPanel.mode_combo`): `AdjustToContents` alone
isn't reliable once a stylesheet is applied — confirmed empirically
(2026-09-09) once "Classic Trichrome"/"Trichromie Classique" became the
widest item and started getting clipped, Qt's `QStyleSheetStyle` doesn't
reliably fold the QSS's own padding/arrow-box width back into the
size-hint computation it feeds `AdjustToContents`. `retranslate_ui()` now
also computes the needed width directly from font metrics plus the QSS's
own known padding/icon/arrow dimensions and enforces it via
`setMinimumWidth()`, sidestepping whatever `AdjustToContents` comes up
with — recomputed on every `retranslate_ui()` call so a language switch
(different widest string) or wording change stays correct automatically.

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

**Only one Batch Import window at a time** - `MainWindow.open_batch_window()`
(bound to Cmd+I and the toolbar's Import button) checks
`self.batch_window is not None and not self.batch_window.isHidden()` and,
if so, just raises/activates the existing one instead of constructing a
new `BatchWindow` (a real bug, fixed 2026-09-12: repeated Cmd+I presses
used to stack up a new window on every press, unbounded).
`BatchWindow` has no `WA_DeleteOnClose`, so closing it only hides it -
`self.batch_window` and the underlying object both survive a close,
which is what makes `isHidden()` a safe, cheap check here (no
deleted-wrapper `RuntimeError` risk) and is also why a *closed* window
still gets a genuinely fresh instance on the next Cmd+I - only a
still-open one gets reused.

The same 3-way choice (`processing_mode_radios`, a **Processing Mode**
block at the top of the window, framed/card-style radio buttons matching
the Mode combo's icons) picks Solo/Classic Trichrome/Color Trichrome for a
whole batch:
- **Trichrome** modes show the existing **File Selection** section
  (renamed from "Input folder"), one of **Automatic** (files matched by a
  filter keyword in the filename), **Sequential** (renamed from
  "Semi-automatic" — files already in R,G,B order, one flat list, now
  also accepting Finder drag-and-drop like Manual's columns), or
  **Manual** (pick each column yourself). All 3 sit directly below the
  Auto/Sequential/Manual radio row, in this fixed shape (2026-09-10/11,
  reworked for visual/positional consistency across the 3 modes):
  - **Automatic** and **Manual** both show 3 distinct per-channel lists
    side by side, each headed by a colored "Rouge"/"Vert"/"Bleu" bar
    rather than a plain floating label — Automatic's are read-only and
    auto-populated from the matched triplets (`_populate_auto_lists`),
    Manual's are user-editable. Automatic's own folder-path/Browse/Rescan
    row sits *below* its 3 lists, not above (so the table itself is
    always the first thing under the mode radios, like the other 2
    modes). Automatic's header is a plain `QLabel` styled directly
    (`_CHANNEL_COLUMN_HEADER_STYLE`, background+border+text baked into
    one stylesheet) since it has no controls of its own; Manual's and
    Sequential's headers (below) need to also host buttons, so they use a
    different split styling instead.
  - **Manual's per-column header bar and Sequential's own header bar**
    (2026-09-11) each combine the channel label (Manual only - Sequential
    has none, just an empty frame, "prend la taille du tableau") with
    that column/list's own Add/Remove/Clear icon buttons, all one visual
    frame directly above the list - not a separate button row below it.
    `_CHANNEL_HEADER_BAR_STYLE` (background/border, applied to a plain
    `QWidget` wrapping label+buttons) + `_CHANNEL_HEADER_LABEL_STYLE`
    (transparent/borderless label meant to sit inside that frame) replace
    `_CHANNEL_COLUMN_HEADER_STYLE` for these two. **Needs
    `Qt.WA_StyledBackground`** on the wrapping `QWidget` to actually paint
    its own background/border at all, and the label inside it needs its
    own explicit `border: none; background: transparent` - otherwise Qt's
    stylesheet cascade lets the frame leak onto whichever child paints it
    first instead (the exact same gotcha as `_ChannelFileBlock` in the
    Files block's own channel-swap rows, main_window.py). Sequential
    wraps its header bar + list in one `semi_table_widget` container so
    `semi_layout` still has exactly one "table" item at index 0, keeping
    `_move_triplets_info_into`'s "index 1, right after the table"
    convention valid without special-casing it.
  - The 3 icon buttons (`SvgToolButton`, icon-only, tooltip carrying what
    a plain-text label used to say) are shared by Sequential and every
    Manual column: `Global/photo-plus.svg` (Add), `Global/photo-minus.svg`
    (Remove selected), `Global/Reset.svg` (Clear) — both `photo-*.svg`
    moved from `Unused/Scan/`. The main toolbar's own Import button uses
    a different, similarly-named `Toolbar/image-plus.svg` - a separate
    icon for a separate action (importing into the whole session, not
    adding to one Batch Import list), don't conflate the two or move
    `image-plus.svg` into `Global/` on the assumption they're the same
    button reused.
  - Sequential's list stamps each item with the colored circle-letter
    glyph (`Global/circle-letter-{r,g,b}.svg`, the same icon family
    ModeSwitchDialog/Histogram/Curves use) for whichever channel that
    position maps to (`_channel_icon_for_index`: `index % 3`, matching
    `batch.build_semiauto_triplets`'s own fixed R,G,B,R,G,B... consumption
    order regardless of the reference-channel choice) - re-stamped in
    full (`_refresh_semi_icons`, called from `_refresh_semi_triplets`) on
    every add/remove/drag-reorder, since a reorder changes which channel
    every subsequent item maps to.
  - Every mode's list gets a genuinely **fixed** (not minimum) height
    (`_apply_list_fixed_height`, `_LIST_ROWS = 5`) so they always show the
    same number of rows, and every header bar ("un encart") gets an
    explicit `setFixedHeight(_HEADER_BAR_HEIGHT)` too - Manual's and
    Sequential's also share one exact set of margins
    (`_CHANNEL_HEADER_BAR_MARGINS`) so the two render at the identical
    height, and `semi_table_layout` deliberately leaves its own spacing at
    Qt's default (not `0`) to match the gap `col_layout`'s own default
    spacing puts between Manual's header bar and its list.
  - **What must *not* be fixed: each mode's own container.** An earlier
    version (2026-09-11/12) forced auto_container/semi_container/
    manual_container to one shared identical size, computed generously
    enough (Import Rules force-measured expanded) to fit whichever mode
    needed the most room. That did stop the window from resizing, but the
    user rightly called the result "disgracieux": Manual and Sequential
    (neither has anything like Import Rules) ended up padded out to
    Automatic's own, much taller footprint - a large dead blank area under
    their real content just to keep all 3 artificially identical.
  - **Current design**: fix only the tables/header bars (above) - genuinely
    deterministic given fixed-width, fixed/translated content - and leave
    each container's own *height* to size itself naturally.
    `_fit_window_to_active_mode()` is what makes the window's *height*
    adapt: it resizes *the window itself* (via `setFixedSize`, so the user
    can't drag it to a size the fixed-size content inside can't use) to
    fit whichever single container is genuinely active, every time that
    could change - a mode switch (`_on_mode_changed`), Import Rules
    expanding/collapsing (connected to its own `toggled`), a Processing
    Mode switch (`_on_processing_mode_changed`, Solo vs. Trichrome), or a
    retranslate. Each mode now gets its own honestly-sized height instead
    of one padded shape stretched to fit the tallest.
  - **The window's own *width*, unlike its height, must stay constant
    across every mode** (2026-09-12, per the user's own explicit "en bref"
    clarification, once the height-adapts design above was in place) -
    `_fix_mode_container_widths()` measures input_group's own natural
    width while Manual is its visible child (the widest natural
    requirement: 3 fixed-width columns) and fixes **input_group and
    solo_group themselves** - the 2 actual top-level siblings whose own
    width drives the window's rendered width - to that value, rather than
    the nested auto/semi/manual containers individually. Whichever of
    those 3 is the visible child then simply stretches to fill
    input_group's now-fixed width on its own (a `QVBoxLayout`'s normal
    behavior for an otherwise-unconstrained child) - which is also *why*
    Sequential's own single list now visibly spans the same width as
    Automatic's/Manual's 3 columns combined, with no width-specific code
    needed for Sequential at all. **A real, confirmed mismatch caught
    while building this**: fixing the nested containers' own widths
    instead (the first attempt) used Manual's measured *content* width,
    which excludes input_group's own QGroupBox border/padding - applying
    that same raw number directly to solo_group (itself a QGroupBox,
    whose own `setFixedWidth` *does* include its own border/padding)
    produced a visibly narrower Solo window than the other 3 modes
    (798px vs. 822px, confirmed directly) - fixed by measuring and fixing
    at the *outer, top-level-sibling* level instead.
  - **Getting `_fit_window_to_active_mode()` itself right took several
    real, confirmed Qt gotchas to work through** (2026-09-11/12, worth the
    full chain here since any one regressing reopens the resize bug):
    - `self.adjustSize()` (tried first) is itself unreliable for this:
      the exact same unchanged content, measured twice with nothing but a
      hide()/show() cycle in between, gave two different results. Uses
      `centralWidget().sizeHint()` instead - a pure bottom-up widget
      computation, confirmed stable under the same test.
    - `sizeHint()` for a complex nested widget (Import Rules'
      `CollapsibleSection`, holding a real `QTableWidget`/`QComboBox`es)
      measures *smaller* before the window has ever been shown/polished
      once than afterward - so this must run again from `showEvent()`
      once actually on screen, not only from `retranslate_ui()` inside
      `__init__` (necessarily pre-`.show()`).
    - Reading `sizeHint()` immediately after a `setVisible()`/
      `setFixedSize()` change (the mode switch itself) can still reflect
      stale, pre-update geometry, since such a change posts a deferred
      `QEvent.LayoutRequest` rather than propagating synchronously - an
      explicit `layout.invalidate()`/`.activate()`/
      `QApplication.processEvents()` sequence forces it to run first.
    - Clears this window's own prior min/max before remeasuring:
      whenever the active container's content changes, Qt's own automatic
      top-level sizing re-imposes a *new minimum* on the window but
      leaves whatever *maximum* an earlier `setFixedSize()` call here had
      set untouched - confirmed directly, `minimumSize() > maximumSize()`
      after a mode switch, an invalid state Qt resolves by growing the
      window.
    - **Import Rules' own `toggled` needed one more fix on top of all the
      above**: calling `_fit_window_to_active_mode()` directly from that
      signal (`CollapsibleSection._on_clicked`, several layout levels
      deeper than a mode-switch radio's own `toggled`) still read a stale,
      *expanded* sizeHint() on collapse even with the full invalidate/
      activate/processEvents sequence - confirmed the identical
      processEvents() call, made instead from *outside* any signal
      handler (after the toggle had already returned), read the correct
      value. Fixed by deferring it via `QTimer.singleShot(0, ...)` instead
      of a direct connection, so it runs on the next event-loop turn
      rather than inline mid-signal. Mode switches don't need this same
      deferral - their own container-visibility change is shallower in
      the layout tree and settles within the immediate, synchronous call.
    Confirmed stable end-to-end: each mode keeps its own distinct,
    unchanging size across repeated mode switches, a real rescan, a real
    mismatch/unmatched-files state, an Import Rules expand-then-collapse
    round trip (returns to the exact pre-expand size, not a residual
    larger one), a language switch, and a hide()/show() cycle - checked
    both the size numbers and (a real regression caught along the way,
    from a container-visibility fix in the earlier, now-reverted padded
    design) that the correct single container stays visible throughout.
  - The matched-triplets count + unmatched-files summary
    (`triplets_info_widget`, now holding only `triplets_row` -
    `triplets_label` + `unmatched_summary_label`) is one shared widget
    reparented via `_move_triplets_info_into()` to sit right below
    whichever mode's table is currently active (index 1 of that mode's
    own layout - see above for why every mode's own layout still has
    exactly one "table" item at index 0) — not fixed below all 3
    (mutually-exclusive) containers, which used to put it below whatever
    extra mode-specific controls happened to be in the active container
    too. **Real gotcha, cost real debugging time (2026-09-11)**: moving a
    widget from one container's layout to another reparents it to a
    different parent *widget* under the hood, and `QWidget.setParent()`
    implicitly hides a widget as a side effect of reparenting even if it
    was visible a moment ago — without an explicit `.show()` right after
    every such move (both in `_move_triplets_info_into` and in
    `_equalize_mode_container_sizes`, which does its own temporary
    remove/reinsert to measure around the widget), the whole summary
    silently went invisible on every single mode switch away from
    Automatic — not merely mispositioned, genuinely gone.
    `triplets_info_widget` used to also hold a separate `unmatched_label`
    (a more detailed plain-text warning below `triplets_row`, e.g.
    mismatched column counts) - **removed entirely 2026-09-12**, per the
    user's own ask to show only the one compact "N unmatched files"
    indicator in every mode, same as Automatic already did (Manual's and
    Sequential's own detailed wording is kept only in `start_import()`'s
    blocking validation alert for an actual Import click with an invalid
    Sequential count - a genuinely different, one-shot context). Losing
    this second, conditionally-visible row also incidentally made
    `triplets_info_widget`'s own height genuinely constant regardless of
    content state - a real, if secondary, contributor to the resize bug
    above, fixed as a side effect.
  - **Import Rules** (renamed from "Advanced Options": which filter-to-
    channel mapping — RGB Trichrome, IR Trichrome, Aerochrome, or a fully
    custom one — Automatic matching uses) lives *inside* auto_container
    itself, not as a sibling in the shared area — so it only ever shows
    in Automatic mode, hidden for free whenever auto_container itself is
    hidden. Both its "?" info buttons live in its own collapsible
    header's blue-tinted frame, pushed flush right by the header
    toggle-button's own Expanding size policy: the general explanation
    (`batch_auto_import_rules_info`, accent-blue "more important" ring)
    and, next to it (moved back into the header 2026-09-11, after a stint
    living inline next to the 4 mode radios), the per-rule explanation
    (`batch_advanced_options_info`, the app's plain default "?" style).
  - Every mode's unmatched-file indicator is the same compact count with
    the full filename list shown in a popup on hover (`ListBubble`), never
    an always-expanded block of text: Automatic's own unmatched files;
    Manual's leftover, unpaired files (2026-09-11, a row past the shortest
    column has fewer than 3 photos and never became a triplet); and
    Sequential's own trailing files past the last full triplet
    (2026-09-12). All 3 flow into the same `unmatched_summary_label`/
    hover-list - see `unmatched_label`'s removal, above.
- **Solo** mode shows a much simpler `solo_group`: Select Image(s)… /
  Select Folder… / Clear, reusing `MainWindow.on_carousel_files_dropped`
  for the actual import (the same path Finder drag-and-drop uses).
  `solo_group`'s own title reuses `batch_input_group` ("File Selection") -
  the same title the other 3 modes' shared group already uses - rather
  than its own separate `batch_solo_group` string (2026-09-12, per the
  user's own ask; the old, now-unused key was removed from `i18n.py`).
  `solo_list` gets the same `_apply_list_fixed_height` fixed height as
  every other mode's own table.

**Last-used settings persist across sessions** (2026-09-11, QSettings,
`ORG_NAME`/`APP_NAME`, independent of the remembered input folder which
already did): Processing Mode (`batch_last_processing_mode`), File
Selection mode (`batch_last_file_selection_mode`: "auto"/"semi"/
"manual"), and the Auto Align checkbox (`batch_auto_align`) - restored by
`_restore_last_settings()`, called once in `__init__` after `_build_ui()`
(every widget it touches must already exist) and before `retranslate_ui()`.
**A real ordering bug caught only by testing an actual restore round-trip
across 2 window instances, not by checking each write in isolation**: the
Processing Mode save was originally folded directly into
`_on_processing_mode_changed()` - which is *also* called once,
unconditionally, at the end of `_build_ui()` to apply the hardcoded
default radio's visibility before restoration ever runs. That call
clobbered a genuinely-restored non-default value (e.g. "solo" from a
previous session) back to the "bw_trichrome" default the moment the
*next* `BatchWindow` was constructed - restoring a value only for the
save that happens moments later, still inside the same `_build_ui()`
call, to immediately overwrite it. Fixed by splitting the save into its
own `_save_processing_mode_setting()`, wired directly to each radio's own
`toggled` signal (which only fires on a genuine state change) instead of
living inside the visibility-update method that `_build_ui()` also calls
directly. File Selection mode's own save (inside `_on_mode_changed`)
never had this problem since nothing calls that method directly during
setup - only the real `toggled` signal ever does.

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
`MAX_PREVIEW_DIM`-capped (1400px) arrays, never the full-resolution source
- `recompute_preview()`/`_recompute_preview_normal()` only ever read
`layer.image_preview`/`normal_layer.image_preview`. This keeps every
slider/curve/crop edit fast regardless of source resolution, but reads
visibly soft once zoomed in or in fullscreen - zoom/fullscreen just scale
up the same capped `QImage` (`canvas_widget.py`'s `_refresh_pixmap`), they
don't bypass the cap. **Tried and reverted (2026-09-09)**: raising this to
1920 for a MacBook Retina display measured at ~120ms → ~220ms for a
single synthetic `compose_trichrome` pass, and live slider/curve dragging
felt noticeably less snappy in the built app - see `MAX_PREVIEW_DIM`'s own
comment in `imaging.py` before retrying. **HQ Preview** below is the
sharpness fix that doesn't cost live responsiveness, since it only ever
runs once editing has actually stopped.

**HQ Preview** (the "HQ" toggle button next to Zoom 100%, also bound to
the bare **H** key like Z/F/G/etc. - see `MainWindow.keyPressEvent`,
2026-09-08/09) is an opt-in, idle-triggered pass that recomposes the
active photo at its **true native resolution** and swaps it into the
canvas in place of the ~1400px preview frame - not a replacement for the
live preview, which keeps running as normal on every edit.
`_arm_hq_preview_if_enabled()`, called from every `recompute_preview()`/
`_recompute_preview_normal()` exit, (re)starts the single-shot
`_hq_idle_timer` (`_HQ_PREVIEW_IDLE_MS`, 500ms) - `QTimer.start()` on an
already-running single-shot timer restarts its countdown, so calling this
on every edit turns it into a settle-delay (fires N ms after the *last*
edit) rather than a throttle like the Curves tool's own
`_CURVE_RECOMPUTE_THROTTLE_MS`, which fires at most once per burst. Once
idle, `_start_hq_preview()` dispatches the actual recompute. This delay
can stay short (raised from an initial, more conservative 4s down to
500ms, 2026-09-09) specifically *because* the recompute is backgrounded
and any now-stale result gets silently discarded (see below) - firing it
eagerly during a fast-moving edit just costs some wasted background CPU
on an abandoned computation, not a frozen UI, unlike the earlier
synchronous design where firing too eagerly meant an unnecessary freeze.

**Tried and reverted (2026-09-09)**: an intermediate step - a fast
~3200px-capped pass at 400ms idle, then upgrading to native resolution at
4s idle, run synchronously on the UI thread - was tried first and dropped
at the user's request in favor of the single native-resolution step
below, once that moved off the UI thread anyway (making the intermediate
stage's whole reason to exist - staying cheap enough to run synchronously
- moot).

**Runs in a background `QThread`** (`HQPreviewWorker`, `hq_preview_worker.py`
- mirrors the `QObject` + `moveToThread` pattern `import_worker.py`/
`export_worker.py` already use), not on the UI thread - a single native-
resolution pass measured empirically (2026-09-09) at ~2.9s for a realistic
24MP (6000x4000) trichrome triplet, all in `compose_trichrome`'s own
warp/tone/color math, not I/O, which would otherwise freeze every slider/
menu/etc. for that whole time. `_start_hq_preview()` snapshots everything
the worker needs as plain values *on the main thread* at dispatch time
(`geo_params` via `_full_res_params`, `tone_params`/`global_params` via
`_current_tone_params()`/`_current_global_params()`, the crop fields) -
only the actual full-res image *pixel data* (which doesn't change from
editing sliders) is fetched by the worker itself, via the plain, uncached
`_full_res_image`/`_full_res_color_image` callables (the same ones
`export_worker.py` takes) passed into its constructor; reading a layer's
`path`/`image_full` cross-thread this way is safe since editing never
touches those specific fields. The result (`result_ready` signal: a
`rgb_uint8` array + a list of `(layer, newly-decoded full-res array)`
pairs for any layer that needed a disk reload) is applied on the main
thread in `_on_hq_preview_result()`, which is also where the decode gets
cached onto `layer.image_full` - the worker itself never mutates a layer
object, only reads from it, so there's no cross-thread write race. Caching
here (not in `_full_res_image`/`_full_res_color_image` themselves) matters
because those are shared with `export_worker.py`, which deliberately must
*not* retain every processed batch item's full-res array in memory just
because it was touched. This does mean a session where you HQ-preview
many different large (especially RAW) photos in a row will accumulate
their full-res arrays in memory for the rest of the session - no eviction
exists yet if that becomes a real problem in practice. Swapping the result
into the canvas reuses the same `set_image_rgb`/`set_image_gray` the
low-res path uses (swapping in a bigger array "just works":
`_refresh_pixmap` always recomputes the on-screen size from `zoom *
source width`, so this doesn't disturb zoom/scroll position).

**Stale results are discarded, not applied**: `self._hq_result_stale`
(set `True` by `_arm_hq_preview_if_enabled` on *every* edit - including
one that arrives while a worker is already mid-compute - and by
`_disable_hq_preview`/`on_hq_preview_toggled(False)`; set `False` only
right when `_start_hq_preview()` actually dispatches a worker) is checked
in `_on_hq_preview_result`/`_on_hq_preview_failed` before touching the
canvas. A worker can't be cancelled mid-`compose_trichrome` call, so a
now-stale one is simply left to finish computing in the background and
its result silently dropped - wasted CPU work in that specific case, but
simple and correct, and `_start_hq_preview()` itself refuses to dispatch a
second worker while one is already running (`self._hq_thread is not
None`), so this can't pile up into multiple concurrent workers: an edit
during an in-flight compute just means *this* settle period doesn't
produce a refresh, the next one will.

**A spinning `Global/refresh.svg` icon** (`self.hq_loading_icon`, an
`SvgToolButton` - originally a `QProgressBar`, replaced 2026-09-09 to
match the Scan block's own "refresh"/device-poll button, which uses the
same glyph) shows while a `HQPreviewWorker` is running, hidden once its
thread reports `finished` (success, failure, or a discarded stale result
all hide it the same way). `refresh.svg` moved from `Tools/Scan/` to
`Global/` accordingly (now used by 2+ areas - see the icon-folder
convention above). The spin itself is a continuous version of
`ScanPanel`'s own `_on_refresh_spin_tick` pattern (`self._hq_spin_timer`,
same `_HQ_SPIN_TICK_MS`/16ms tick and `_HQ_SPIN_DEGREES_PER_SEC`/360°-per-
second rate as that button's fixed 1-second one-shot spin) but looped
indefinitely between `_show_hq_loading_indicator()`/
`_hide_hq_loading_indicator()` instead of a fixed duration, since a HQ
compute's length isn't known up front - `_on_hq_spin_tick` wraps the angle
modulo 360 so it never grows unbounded over a long-running compute. Left
enabled (not `setEnabled(False)`, which would dim it via
`SvgToolButton`'s own disabled-state color) so it matches the Scan
button's full-brightness look while spinning; `setFocusPolicy(Qt.NoFocus)`
+ an arrow cursor keep it from reading as a clickable control despite
being a real `QToolButton`. It's wrapped in its own
`self.hq_loading_bar_container` (a plain `QWidget` with a small
`QHBoxLayout`/margins) rather than added to the status bar directly - a
bare small fixed-size control, added straight into `QStatusBar`'s own
layout, rendered outside the window's left edge (2026-09-09, a
native-macOS-style-control-in-a-cramped-layout glitch, first hit with the
`QProgressBar`) - visibility is toggled on the *container* via the two
`_show_hq_loading_indicator`/`_hide_hq_loading_indicator` methods (which
also start/stop the spin timer), never the icon or container's own
`setVisible` directly. Placed via `self.statusBar().insertWidget(0, ...)`,
not `addWidget` (which just appends after whatever's already there) -
index 0 is the exact slot `showMessage()`'s own temporary text (e.g.
`"status_saving_session"`) occupies, and a hidden widget takes no layout
space, so the container sits flush at the status bar's own left margin -
the same starting point that text uses - rather than wherever it happened
to land otherwise.

If native resolution ever turns out too slow in practice even backgrounded
(e.g. a very large batch of huge RAW files edited in quick succession),
the next step would be viewport-only rendering (only compute HQ pixels for
the visible region of the canvas, bounding cost by screen size instead of
source resolution, like a real "1:1 preview" in Lightroom/Capture One) -
real added complexity (viewport tracking, recompute-on-pan/zoom, mapping
screen coordinates back through each channel's own alignment matrix), not
attempted yet.

`_current_tone_params()`/`_current_global_params()` are the shared tuple-
builders both the low-res preview and every HQ pass call, so they can't
drift apart - don't reintroduce a separate inline copy of that
tuple-building anywhere.

**HQ Preview stays on while you browse between photos** (changed
2026-09-09, once the compute moved to a background thread): switching the
active photo (`activate_batch_item`, `_restore_state` for undo/redo) does
*not* turn HQ Preview off - it just calls the normal `recompute_preview()`
tail like any other edit, which runs `_arm_hq_preview_if_enabled()` and so
marks any in-flight/just-finished result for the *previous* photo stale
and re-arms the idle timer for the newly active one. Before backgrounding
the compute, switching photos explicitly disabled HQ Preview
(`_disable_hq_preview`, since then removed) so a slow idle-triggered pass
firing while you were just clicking through the filmstrip wouldn't cost
anything for a photo you'd already moved past - now that a stale result
is silently discarded rather than shown (and never blocks the UI while
computing), there's no cost left to guard against, so the toggle can
simply reflect "on" or "off" the way any other persistent-feeling toggle
would. `on_hq_preview_toggled` (the button/shortcut path) is still the
one place that forces an immediate `recompute_preview()` call when turning
it *off*, so the display reverts to the low-res frame right away rather
than leaving a stale HQ frame on screen. `_invalidate_hq_preview()` is a
narrower variant - stops the timer and marks results stale without
touching `hq_preview_enabled`/the button's checked state - used at
`recompute_preview()` exits that clear the canvas entirely (no image
loaded), where there's nothing for a HQ pass to apply to.

**Confirmed working end-to-end (2026-09-09)**, both by headless test
coverage (background-thread dispatch/result/staleness/concurrency-guard,
both Trichrome and Normal mode, the zoom-stability fix below) and by the
user's own pass in the built app - described as "seamless."

**No full-res path exists for Solo preview** (a preview-only view state,
never handled by `export_worker.py` either) - `_arm_hq_preview_if_enabled`/
`_start_hq_preview` both no-op while any layer's `solo` is set, same for
Compare mode (a transient before/after view, not worth a full-res pass).
The toggle itself stays enabled in both cases; it just has nothing to do
until you leave that state.

Not persisted across launches (same as Compare/Crop-active) - resets to
off on every relaunch.

### Canvas zoom is a percentage of a stable reference size, not of whatever's loaded

`CanvasWidget.zoom` is **not** a multiplier on `self._qimage`'s own pixel
size - it's relative to `self._ref_width`/`_ref_height`
(`set_reference_size()`), a separate, deliberately stable pair of
dimensions. **Why this split exists (2026-09-09)**: before it, `zoom`
scaled directly off `self._qimage.width()/height()`, so swapping in an HQ
Preview native-resolution array for the *same* photo (e.g. 1400px ->
6000px) made the on-screen image balloon/shrink at a fixed zoom value,
and the same thing happened in miniature on every ordinary edit too,
since even the live low-res path's own array shrinks after a crop is
applied. None of that is a real zoom change from the user's point of
view - only the pixel *density* changed, not "how much of the photo, how
big, from what part."

- `MainWindow.recompute_preview()`/`_recompute_preview_normal()` call
  `self.canvas.set_reference_size(w, h, native_zoom)` right after
  `set_image_rgb`/`set_image_gray`, using the low-res result's own
  (already straightened/mirrored/cropped) shape for `w, h`, and
  `1.0 / ref.preview_scale` (or the solo/Normal-mode layer's own
  `preview_scale`) for `native_zoom` - "how many reference-space pixels
  make up one native pixel."
- `MainWindow._on_hq_preview_result()` calls `self.canvas.set_hq_image_rgb()`
  instead of `set_image_rgb()` - swaps `self._qimage` to the sharper
  native array *without* calling `set_reference_size`, so the zoom
  reference (and therefore the on-screen box size at any given zoom
  level) doesn't move. `_refresh_pixmap()` computes the target on-screen
  size from `_ref_width/_ref_height * zoom`, then `.scaled()`s whatever
  `self._qimage` currently holds into that fixed box - a higher-res
  source there just reads sharper, same box.
- **`zoom_100()` ("Real Size", the Z key/button) is one deliberate
  exception**: it targets `self._native_zoom`, i.e. true 1:1 native-
  pixel-to-screen-pixel, not "100% of the reference/preview size" (which
  was never real size to begin with - just the sharpest the live
  preview could show before HQ Preview existed).
- **`zoom_fit()` is the other one, and it's a persistent *mode*
  (`self._fit_mode`), not a one-time zoom value** (2026-09-09 fix, right
  after the reference-size split above first shipped): `set_reference_size()`
  re-applies the fit calculation on every new photo/crop state whenever
  `_fit_mode` is set, instead of leaving whatever zoom number the
  *previous* photo's own fit happened to compute. Without this, switching
  from e.g. a landscape photo to a portrait one while "Fit" was active
  reused the landscape photo's fit zoom on the portrait one's own (very
  different) reference dimensions, showing it too small or spilling past
  the viewport - a real regression the reference-size split introduced,
  since before it `zoom` was implicitly "self-correcting" (always relative
  to whatever was currently loaded, so any stale zoom number still landed
  on that same photo's own true dimensions). `_set_zoom_raw()` is the
  shared apply-and-repaint tail both a manual `set_zoom()` (which clears
  `_fit_mode`) and the internal `_apply_fit_zoom()` (which must not) call,
  keeping "did this zoom change come from the user or from Fit's own
  upkeep" unambiguous. An HQ Preview swap (`set_hq_image_rgb`, which never
  calls `set_reference_size`) still doesn't move the Fit target, same as
  any other zoom level - only a genuinely new photo/crop does.
- `_ImageLabel.display_scale` (screen pixels per unit, divided out of
  align-drag mouse deltas to land in `ChannelLayer.dx`/`dy`'s own unit)
  is likewise `pix.width() / self._ref_width`, not `/ self._qimage.width()`
  - it has to be, since `dx`/`dy` are always in preview-space units
  regardless of which resolution tier happens to be on screen; before
  this fix, dragging to align while a HQ frame was showing would have
  computed the wrong delta by whatever factor separated the two tiers
  (a latent bug HQ Preview introduced, never actually observed/reported,
  fixed as part of this same change).

### Filmstrip & grid view

Grid view (the "Grid" toolbar button, or the bare **G** key) is the
filmstrip's own "fullscreen" mode — not a separate widget, but the exact
same `CarouselWidget` instance (`self.carousel`) reparented and switched
into a different internal layout, so every filmstrip feature (drag-to-
reorder, right-click menu, click/Cmd-click/Shift-arrow selection, Finder
file drops) keeps working unchanged with nothing to duplicate or keep in
sync:

- **`CarouselWidget.set_grid_mode(bool)`** moves every `_CarouselCard`
  between the strip's `QHBoxLayout` (`self.strip_layout`, fixed
  `THUMB_W`/`THUMB_H` size) and a second internal `QGridLayout`
  (`self.grid_layout`, on `self.grid_strip`/`self.grid_scroll`) — same
  cards, same selection state, same thumbnails, just a different
  container/size. `MainWindow.on_grid_view_toggled` is what actually
  moves the *widget* itself: `self.carousel` is removed from
  `canvas_layout` (its normal "bande" spot, below `bottom_bar`) and
  reparented into `self.preview_stack` (replacing `self.canvas`) while
  active, then moved back — `insertWidget(canvas_layout.indexOf(bottom_bar),
  ...)`, never a plain `addWidget`, so it lands *before* `bottom_bar`, not
  after.
- **`bottom_bar` (the zoom/rotate/compare/fullscreen/sort/grid/thumbnails-
  toggle row) is always the last item in `canvas_layout`**, with
  `self.carousel` inserted *above* it — this is what pins the toolbar to
  the true bottom edge of the preview window regardless of whether the
  filmstrip strip is shown/hidden below it or grid mode is active
  (previously `bottom_bar` sat *above* `self.carousel`, so the toolbar's
  own position visibly shifted depending on filmstrip visibility — fixed
  by swapping the order).
- **Grid cell sizing always fills the available width** — `_reflow_grid()`
  derives each cell's size from `available_width / columns` (recomputed on
  every resize), and `grid_layout.setAlignment(Qt.AlignHCenter |
  Qt.AlignTop)` centers the block, so margins stay equal on both sides
  regardless of the side panels' width/visibility. Zoom In/Out (routed to
  `carousel.zoom_in()`/`zoom_out()` while grid mode is active, to
  `canvas.zoom_in()`/`zoom_out()` otherwise — see
  `MainWindow.on_zoom_in_clicked`/`on_zoom_out_clicked`) only change the
  column count (`MIN_GRID_COLUMNS`/`MAX_GRID_COLUMNS`), never the cell
  size directly.
- **Thumbnail source resolution is 480px** (`MainWindow._THUMBNAIL_MAX_DIM`,
  `_update_carousel_thumbnail`'s `imaging.make_preview(..., max_dim=...)`)
  — well above the filmstrip's own ~96px on-screen size, specifically
  because the same pixmap is reused, scaled up, for grid cells (which can
  display much larger). The old value (110px) read as visibly pixelated
  once enlarged there. Zooming to very few columns in a wide window can
  still exceed this and look soft — an accepted tradeoff rather than
  recomputing a full-resolution thumbnail per cell.
- **Up/Down arrow keys move a row at a time while grid mode is active**
  (`CarouselWidget.go_up()`/`go_down()`, moving the current index by
  `self._grid_columns`, a no-op in strip mode since a single row has no
  "row above/below") — wired in `MainWindow.keyPressEvent` next to the
  existing Left/Right handling, gated on
  `self.grid_view_toggle_btn.isChecked()`, Shift held extends the
  selection via the same `_extend_selection_to` anchor logic Left/Right
  already use. **Escape deactivates grid mode** (checked in
  `keyPressEvent` at the same priority tier as fullscreen/crop).
- **Two real focus-routing gotchas hit while building Up/Down navigation,
  both confirmed via `QTest.mouseClick`/`QTest.keyClick` (a direct
  `mw.keyPressEvent(event)` call bypasses Qt's real focus dispatch
  entirely and will not catch either of these):**
  1. `ArrowKeyScrollArea` (`widgets/controls.py`) only special-cased
     Left/Right — after a real click, keyboard focus lands on the scroll
     area itself, and `QScrollArea`'s own native key handling silently
     consumes Up/Down/PageUp/etc. to scroll its viewport before
     `MainWindow.keyPressEvent` ever sees them. Fixed with an
     `ignore_keys` constructor parameter (default `(Left, Right)`,
     unchanged everywhere else); `CarouselWidget.grid_scroll` passes
     `(Left, Right, Up, Down)`.
  2. Activating grid mode via the toolbar button or the **G** shortcut
     doesn't itself move keyboard focus — if a side tool panel
     (`left_scroll`/`right_scroll`, also `ArrowKeyScrollArea` instances)
     still had focus from before, Up/Down kept scrolling *that* panel
     instead of navigating photos, even with fix #1 in place. Fixed by
     `on_grid_view_toggled` calling `self.carousel.grid_scroll.setFocus()`
     right when entering grid mode, so it becomes the active panel for
     Up/Down immediately on activation, not only after a click inside it.

### Filmstrip context menu — "Convert to Trichrome"

Right-clicking 1-3 selected Solo photos (2026-09-10) offers "Convert to
Trichrome Image" — hidden whenever more than 3 are selected (nowhere to
put a 4th channel) or any selected photo is already Trichrome (ambiguous
which of its own 3 channels would be used).
`MainWindow.convert_items_to_trichrome(indices)` builds one *new* Classic
Trichrome `BatchItem` from them, in filmstrip order — the first selected
photo becomes Red, the second (if any) Green, the third (if any) Blue,
each flattened to luminance the same way a real classic-trichrome shot
would be (`imaging.load_grayscale` with no `channel` argument — always
Classic, never Color Trichrome, since a Solo photo has no per-channel
decode of its own worth preserving). Named with the same "(N)" version
suffix `duplicate_batch_item`'s own `_duplicate_base_name` uses, inserted
right after the first source photo. The source photo(s) are left
completely untouched, same "this creates something new, it doesn't
consume its inputs" principle `duplicate_batch_item` follows — selecting
just 1 photo produces a Trichrome item with only its Red channel filled
(Green/Blue stay empty, no different from starting a fresh Trichrome
project and loading one channel manually).

**`CarouselWidget` needed a way to know each item's mode without ever
holding `BatchItem` data itself** — the eligibility check above needs it,
but the carousel otherwise only ever sees `base` strings and thumbnails.
`set_items(bases, modes)` now takes a parallel `modes` list (every one of
its ~7 call sites in `main_window.py` updated to pass
`[it.mode for it in self.batch_items]` alongside the existing bases list,
so the two can never drift out of index-alignment at any full rebuild),
cached as `CarouselWidget._item_modes`. Two things update it *without* a
full rebuild, since neither goes through `set_items()`:
`CarouselWidget._reorder()` (a drag-and-drop filmstrip reorder moves
`_cards` around directly, `on_carousel_reordered` in `main_window.py`
just re-syncs `batch_items` to match rather than calling `set_items()`
again — `_item_modes` needs the identical `list.insert(target,
list.pop(from_index))` treatment or it silently goes stale, showing the
*previous* occupant's mode at that filmstrip position) and
`CarouselWidget.set_item_mode(index, mode)`, called from the one shared
tail every Mode-switch handler already funnels through
(`_sync_import_and_channels_ui`, right after it computes the active
item's own `mode`) rather than adding a call at each of
`on_import_mode_change_requested`/`_switch_to_normal_mode`/
`_switch_to_trichrome_mode`/`_assign_normal_photo_to_channel`
individually.

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
- **Camera Settings** (2026-09-09, below Device): RAW/JPEG Format, White
  Balance, Shutter Speed — each is a `gphoto2` config node found
  generically on the connected camera by leaf-name hint
  (`gphoto_backend.find_quality_config`/`find_white_balance_config`/
  `find_shutter_speed_config`, all thin wrappers over one shared
  `_find_config_by_hints`; no path is ever hardcoded, since the exact
  config tree depends on the camera/libgphoto2 version — see the module's
  own docstring). `ScanPanel._on_camera_selected` re-detects all 3 via the
  shared `_populate_config_combo()` helper every time the selected camera
  changes; each label+combo pair only appears once that camera actually
  exposes the node **with real choices** — hidden entirely otherwise
  (**a real per-camera gotcha**: Shutter Speed in particular is often
  only settable over PTP when the camera's own physical mode dial is in
  Manual — a dial in Auto/Program can make libgphoto2 report the node as
  present but with an empty choice list, which reads here as "not
  exposed", not a bug). Not threaded through `settings_snapshot()`/
  `apply_settings_snapshot()` (`.trirgb`) — like the camera/quality
  selection above it, this is live hardware state tied to whichever
  camera is currently connected, not project content.
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
- The panel's own sections (Device/Camera Settings/Film/Scan Light/Save
  Location) are independently collapsible (`CollapsibleSection`),
  persisted in the Scan tool's own QSettings domain.
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
- **A top-level window's own `.size()` is unreliable under
  `QT_QPA_PLATFORM=offscreen`** once anything triggers a resize after
  `.show()` (e.g. toggling which of several sibling widgets is visible) -
  confirmed 2026-09-11 while fixing a real bug where switching Batch
  Import's Auto/Sequential/Manual radio grew the window and never shrank
  it back. The offscreen platform itself warns `This plugin does not
  support propagateSizeHints()` on every resize - after that, `.size()`
  can report values wildly larger than the central widget's own
  `sizeHint()` (residual/stale geometry from a prior resize pass, not a
  real computed size). The reliable, platform-independent signal for "did
  I actually equalize these widgets' footprints" is each widget's own
  `minimumSize()`/`sizeHint()` (confirmed equal across every mode in this
  fix) - not the window's outer `.size()`, which needs the user's own
  pass in the real app to confirm.

## Roadmap

A running todo list, not tied to version numbers — update it as items are
picked up/finished rather than reorganizing it per release.

**Major features:**

- **Metadata panel** — planned for later. Not yet specified: what fields
  (presumably EXIF from the source photos and/or the composite's own
  derived info), where it lives in the UI, whether it's per-channel or
  per-composite, read-only or editable. Don't start without a real
  functional spec.
- ✅ **RAW file support** — decode landed 2026-09-08 and confirmed working
  by the user against real captures from the Scan tool; general Import/
  Files/drag-and-drop widened the same day. A real end-to-end batch
  import of `.RAF` triplets through the Batch Import window itself has
  since been tested and confirmed working too — the whole feature is
  done, not just the decode/wiring.
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

**Pre-beta checklist** (2026-09-11, before opening the app to outside
testers) — a v0.5.1 test build is being made specifically to work through
this list, not a feature pass on top of the app's current state:

- Verify every tool still works end-to-end in the built app (a manual
  regression pass, not a new feature).
- Polish the Shortcuts menu.
- Polish the Quick Start menu.
- A first-launch "quick tour" — not yet specified (which steps, how many,
  skippable, shown once vs. re-openable from a menu). Needs a real spec
  before starting, same as Metadata panel above.
- A "Light" mode that restricts the app to the trichromy tools only — not
  yet specified (which tools/blocks it hides, how it's toggled, whether
  it's a separate default layout or a real feature-gating mode). Needs a
  real spec before starting.
- Finish the Scan tool's remaining options — not yet specified which ones
  are still missing beyond what's documented under "Scan tool" above.

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

`CHANGELOG_EN.md` is the **user-facing** release history — what changed
and why it matters to someone using the app, in plain language, as
opposed to this file's implementation-level detail for development.

**2026-09-11**: the French changelog (`CHANGELOG_FR.md`) and the PDF
copies of both (`CHANGELOG_EN.pdf`/`CHANGELOG_FR.pdf`, regenerated by
`scripts/generate_changelog_pdf.py`) were dropped per the user's own
request — not worth the upkeep. `CHANGELOG_EN.md` (English, Markdown
only) is now the single changelog; `build_mac.sh` no longer regenerates
anything changelog-related as part of a build.

The **Unreleased** section at the top always lists what's changed since
the last version was actually built, plus a running list of what's
planned next.

**Workflow — do this whenever the user asks to bump the version and
build**, *before* touching `trichrome.spec`:
1. In `CHANGELOG_EN.md`, turn `## Unreleased` into a new dated version
   entry (`## vX.Y.Z — YYYY-MM-DD`, today's actual date) —
   rewrite/tighten the wording into a single coherent release note rather
   than a raw per-feature diary. Keep the "Remaining tasks for future
   versions" framing for anything still open.
2. Leave a fresh, empty `## Unreleased` section at the top of the file.
3. Bump `trichrome.spec` and run `./build_mac.sh`.
4. Commit the changes (git repo at the project root, GitHub remote
   `origin`) — a version-bump/build request implicitly includes
   committing afterward. Message convention: `"vX.Y.Z"` as the summary
   line.
5. **Push to `origin` right after committing** — this auto-push
   authorization is scoped to version-bump/release commits specifically,
   not a blanket standing push authorization for any other commit. If
   `git push` fails with an HTTPS credential error, run
   `gh auth setup-git` first and retry.

**Unlike this file** (updated after nearly every substantial change), do
**not** touch the changelog incrementally after each feature/fix — leave
`## Unreleased` alone between bumps and reconstruct it from the
conversation/git history in one pass, only when the user actually asks to
bump the version and build. Don't let a version release with an empty or
stale changelog, but "stale" only starts to matter right before a bump.

## Language

The user writes in French; reply in English regardless of the language they use.
