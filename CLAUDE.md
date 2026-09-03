# Trichr-o-matic

macOS PySide6 app that recomposes a color image from three B&W photos shot
through R/G/B (or IR/Aerochrome/custom) filters. Packaged as a standalone
`.app` with PyInstaller. See `README.md` for user-facing features/usage.
Display name is "Trichr-o-matic" (window title, Finder/.app name); the
Python package (`trichrome/`), class names, and the `ORG_NAME`/`APP_NAME`
QSettings domain (`"TrichromeMaker"`) are unrelated internal identifiers —
left as-is so renaming the app doesn't reset users' saved sessions.

## Running & building

```bash
source venv/bin/activate        # venv already exists at repo root
python3 main.py                 # run from source, no rebuild needed
./build_mac.sh                  # -> dist/Trichr-o-matic.app (bumps nothing itself)
```

Version string and icon live in `trichrome.spec` (`CFBundleShortVersionString`,
`icon="resources/icon.icns"`). Bump the version there before a release build;
don't touch the icon path unless the user explicitly asks for a new icon.

## Terminology (user's vocabulary, agreed 2026-09-03)

The user refers to UI regions with specific French terms - use this mapping
when parsing their requests, since it doesn't always line up 1:1 with code
identifiers:

- **Barre d'outil** = the top toolbar (`self.top_toolbar`), conceptually
  split into left/middle/right zones by `toolbar_spacer_left`/
  `toolbar_spacer_right`.
- **Panneau outil de gauche** / **panneau outil de droite** = `left_container`/
  `right_container` (both `BlockReorderZone` instances - see the block
  system in the Key Patterns section below). **Fenêtre Preview** (center) =
  `canvas_container`.
- Inside a tool panel, each **"bloc"** is one independently movable/
  hideable/collapsible block (`_ALL_BLOCK_KEYS` in `main_window.py`) -
  since 2026-09-04 there's no longer a shared wrapper container per pair,
  each of the 7 is its own top-level widget in `left_layout`/`right_layout`:
  - **Fichiers** = `import_panel` (key `"files"`)
  - **Trichromie** = `independent_channels_group` (key `"channels"` - the
    3 `ChannelPanel` R/G/B blocks)
  - **Histogramme** = `histogram_box` (key `"histogram"`)
  - **Light** (part of what used to be "Global Color Correction") =
    `light_panel` (key `"light"`)
  - **Color** (the other half) = `color_panel` (key `"color"`)
  - **Recadrage** = `crop_panel` (key `"crop"`)
  - **Scan** = `scan_panel` (key `"scan"`)
- **Barre des vignettes** (below the preview) = the carousel/filmstrip.
- **Barre de preview** (above the preview, display + sort controls) = the
  zoom/fit/fullscreen/sort row above the canvas.

## Code map

- `main.py` — entry point.
- `trichrome/model.py` — data model: `ChannelLayer` (one R/G/B shot: image
  arrays, alignment dx/dy/scale/rotation, tone curve, `quarter_turns`) and
  `BatchItem` (one imported photo: its 3 layers + global correction +
  `uid`/`capture_date`/`custom_order` used for filmstrip sorting).
- `trichrome/imaging.py` — pure image-processing functions (load, warp,
  tone curve, compose, EXIF capture-date extraction). No Qt here.
- `trichrome/main_window.py` — the big one: UI construction, all signal
  wiring, undo/redo, session persistence, batch import orchestration,
  filmstrip sorting. Most feature work touches this file.
- `trichrome/import_worker.py` / `export_worker.py` — QThread workers for
  batch import/export so the UI doesn't block.
- `trichrome/batch_window.py`, `batch.py`, `filters.py` — the separate
  batch-import window and filename/filter-matching logic.
- `trichrome/alignment.py` — ORB/ECC auto-alignment.
- `trichrome/i18n.py` — flat dict-based `i18n.tr("key", **kwargs)`, EN and
  FR blocks kept in parallel; add a key to both when adding UI text.
- `trichrome/widgets/` — custom widgets. Toolbar icon buttons
  (`rotate_toggle_button.py`, `fullscreen_toggle_button.py`,
  `filmstrip_toggle_button.py`, `sort_button.py`, `compare_button.py`, and
  the top-toolbar buttons built inline in `main_window.py`) are all
  `resources/icons/**/*.svg` files rendered and tinted at paint time by
  `trichrome/widgets/svg_icons.py` (`SvgToolButton` for a single icon,
  `SvgTwoStateToggleButton` for a checkable button that swaps between two
  icons by state, `SvgCheckableToolButton` for a same-icon checkable button
  that dims while unchecked but stays clickable, `SvgLetterToggleButton` for
  the R/G/B/Y channel-letter buttons). `resources/icons/` is organized into
  subfolders by usage area (`Color Correction/`, `Crop/`, `General/`,
  `Letters/`, `Preview/`, `Scan/`, `Toolbar/`) - **pass the subfolder as
  part of the name**, e.g. `SvgToolButton("Crop/crop.svg")`; several
  subfolders (`Scan/` in particular, and a few per-aspect-ratio crop icons)
  hold assets staged ahead of features that don't use them yet - don't
  delete them as "unused." `trichrome/paths.py` resolves the icons folder
  both from source and inside the frozen `.app` (`sys._MEIPASS`);
  `trichrome.spec` bundles `resources/icons` via `datas` (recursively, so
  new subfolders need no spec change). When adding a new icon button, reuse
  an existing SVG (duplicating and rotating/recoloring one via a plain SVG
  `transform` is fine - e.g. `Crop/mirror_line_vertical.svg` is `Crop/
  mirror_line.svg` rotated 90°) or ask the user for one rather than
  hand-drawing a new one from scratch - this project stopped hand-drawing
  icons in QPainter once SVG assets became available. Match existing
  sizing/spacing for buttons in the same toolbar row.

## Key patterns

- **Session persistence — two mechanisms, one now primary at launch**:
  1. Explicit, portable `.trirgb` project files (`_collect_session_data`/
     `_build_restored_items_from_data`/`save_session_to_path`/
     `load_session_from_path`) — plain JSON, opened via File ▸ Open Session
     (⌘O) / Save Session (⌘S) / Save Session As (⌘⇧S) or the toolbar's save
     button. No mtime staleness check (unlike the QSettings path below)
     since opening a named file is an explicit user action. Every time
     `_session_file_path` changes (save/save-as/open/new session), go
     through `_set_session_file_path()` — it also mirrors the path into
     `QSettings` as `"last_session_file_path"`, which `_restore_session`
     reads on next launch to just reopen that same file (full fidelity, the
     same code path as File ▸ Open Session), instead of reconstructing
     state field-by-field.
  2. Implicit, OS-scoped autosave-on-close via `QSettings(ORG_NAME, APP_NAME)`
     (`_save_session_state`/`_legacy_restore_session` in `main_window.py`,
     `ORG_NAME = APP_NAME = "TrichromeMaker"`) — now only a **fallback**,
     used by `_restore_session` at launch when there's no remembered
     `.trirgb` (fresh install, or a session that was never saved to a file)
     or reopening it failed.

  Every `BatchItem`/`ChannelLayer` field that should survive either path
  needs a matching read/write pair in **both** mechanisms — `_save_session_state`/
  `_legacy_restore_session` (QSettings) *and* `_collect_session_data`/
  `_build_restored_items_from_data` (`.trirgb`). Both share the same tail via
  `_apply_restored_items` for installing a reconstructed `batch_items` list
  and refreshing the UI — extend that instead of duplicating it a third time.
  Window-level state that isn't part of `batch_items` (currently just panel
  visibility: `left_panel_visible`/`right_panel_visible`/`carousel_visible`,
  read from the toggle buttons' checked state) goes through a second, parallel
  shared tail, `_apply_restored_layout()`, called right after
  `_apply_restored_items()` in both mechanisms - add future window-level
  fields there rather than growing `_apply_restored_items`'s signature.
  When testing, monkeypatch the **module-level** `trichrome.main_window.ORG_NAME`/
  `.APP_NAME` to an isolated string first — never run tests against the real
  `"TrichromeMaker"` domain, that's the user's actual saved session.
  **`mw.ORG_NAME`/`mw.APP_NAME` do NOT work for this** - `ORG_NAME`/`APP_NAME`
  are plain module globals (`main_window.py` line ~141), and every method
  that builds a `QSettings(ORG_NAME, APP_NAME)` reads the bare name via
  normal Python scoping (module globals), never `self.ORG_NAME` - so
  setting a class or instance attribute of the same name is silently a
  no-op that leaves every `QSettings` call still pointed at the real
  domain. **This bug actually happened** (2026-09-04): a test script
  patched `MainWindow.ORG_NAME` (a class attribute) instead of the module
  global, and every `_save_layout_preset`/`_delete_layout_preset` call in
  that "isolated" test session silently wrote to the user's real
  `com.trichromemaker.TrichromeMaker` plist instead - overwriting their
  real `"Trichrome"`/`"Color Correction"` Layout Presets with synthetic
  test data in one pass, then their real `"NewTrichrome"`/
  `"NewColorCorrection"`/`"NewCrop"`/`"NewScan"` presets (recreated after
  the first corruption) in the very next pass, before the root cause was
  found. Correct pattern:
  `import trichrome.main_window as mwmod; mwmod.ORG_NAME = mwmod.APP_NAME
  = "SomeIsolatedName"` **before** constructing `MainWindow()` - confirm
  isolation actually held by reading back
  `QSettings(mwmod.ORG_NAME, mwmod.APP_NAME)` after the test, not by
  trusting the patch was applied to the right target.
  `.trirgb` files are registered as a document type in `trichrome.spec`'s
  `CFBundleDocumentTypes`; `main.py`'s `TrichromaticApp` catches the macOS
  `QEvent.FileOpen` this generates (double-click in Finder, or an app
  already running) and routes it to `load_session_from_path` - note the
  event can arrive before `MainWindow` exists (buffered via
  `pending_open_path`), so don't assume `window` is ready when handling it.
- **Unsaved-changes tracking**: `MainWindow._edit_counter` piggybacks on the
  undo/redo stack instead of a separate dirty flag - `push_undo`: +1,
  `undo`: -1, `redo`: +1. `_saved_edit_counter` records its value at the
  last `.trirgb` save; they differ ⇒ dirty. This correctly treats "undid
  back to exactly the saved state" as clean, which a simple bool flag
  wouldn't. `_confirm_discard_unsaved_changes()` is the shared prompt for
  any action that would discard the session (New Session, Open Session,
  quit via `closeEvent`) - deliberately NOT gated on `_session_file_path`
  being set: the first time you do real work and haven't saved yet still
  prompts. If the user picks Save with no `_session_file_path` yet, it
  falls through to `action_save_session_as()`, and cancelling *that* is
  treated as cancelling the whole thing (nothing got saved). Reuse this
  helper for any future action that discards the current session rather
  than re-deriving it. It shows `widgets/unsaved_changes_dialog.py`'s
  `UnsavedChangesDialog` — a plain `QDialog` styled to match the rest of the
  app (tinted `warning.svg` via `svg_icons.tinted_svg_pixmap`, plain
  `QPushButton`s) instead of the native `QMessageBox` chrome.
- **Every alert/warning dialog uses the app's own look, never native
  `QMessageBox` chrome (policy from 2026-09-01 on)** — `widgets/
  alert_dialog.py`'s `show_alert(parent, title, text)` is a drop-in
  replacement for `QMessageBox.warning`/`.critical(parent, title, text)`:
  same call shape, but renders as an `AlertDialog` (`UnsavedChangesDialog`'s
  same recipe - tinted `warning.svg`, plain `QPushButton`, no native
  chrome), with a single "Close" button (`close_button` i18n key, already
  shared with `export_dialog.py`). Currently used by the Locate-failure
  message (`on_locate_missing_files`, see below) - reach for `show_alert`
  instead of `QMessageBox` for any new alert; the handful of pre-existing
  `QMessageBox.critical`/`.warning` calls elsewhere (`_load_image_from_path`'s
  load error, auto-align failure, session-load errors) predate this policy
  and haven't been retrofitted yet, not an exception to it.
  - **Optional scrollable table (added 2026-09-02):** `show_alert`/
    `AlertDialog` also take `table_headers`/`table_rows` - a read-only,
    non-editable `QTableWidget` (`Qt.ItemIsEditable` stripped per-item)
    capped at `_TABLE_MAX_HEIGHT = 160` px, appended below the body text.
    The point: `text` itself must stay a **fixed** paragraph that never
    grows (no more folding a variable-length list into it with string
    interpolation, which is what the Locate-failure message used to do) -
    a long, variable-length list goes in the table instead, which scrolls
    internally via its own bounded height instead of stretching the dialog
    to fit however many rows there are.
  - **Per-row tooltip + row action (added 2026-09-02):** `table_tooltips`
    (one string per row, set on every cell in that row so hovering
    anywhere in it works) and `row_action_label`/`row_action`/`row_targets`
    - a button next to the table, disabled until a row is selected
    (`QAbstractItemView.SelectRows`/`SingleSelection`, wired via
    `itemSelectionChanged`), calling `row_action(row_targets[selected_row])`
    on click *or* double-click. `row_targets` holds an opaque per-row
    payload for the callback - not the display strings themselves.
    `row_action` returning `True` removes that row (and its paired
    `row_targets` entry, kept in sync by index) from the table - `False`
    leaves it for another attempt. **Bug fixed 2026-09-02:**
    `_trigger_row_action` used to hardcode the button back to disabled
    right after a successful `removeRow()`, even when rows (and a newly
    auto-selected one) remained - `QTableWidget.removeRow()` auto-selects
    the next row and fires `itemSelectionChanged` itself when rows are
    left (confirmed empirically), so that signal already re-enables the
    button correctly; the explicit `setEnabled(False)` right after was
    stomping that back to wrong. Fixed by calling
    `self._update_row_action_enabled()` instead of hardcoding, which
    re-derives the state from the table's actual current selection - this
    is what let a 3-row Locate-failure dialog resolve every row instead of
    getting stuck disabled after the first one. `on_locate_missing_files`
    uses all of this: `unresolved` now carries `(item_index, ci, base, label, path)`
    per entry (channel index and last-known path added specifically for
    this), split into `table_rows=[(base, label), ...]`,
    `table_tooltips=[path, ...]` (so hovering a row shows its original
    file location), and `row_targets=[(item_index, ci), ...]` feeding
    `row_action=lambda target: self._relink_one_channel_interactively(*target)`
    - letting the user select a still-unresolved row (e.g. a renamed file
    basename-matching couldn't find) and pick its exact replacement file
    directly from the dialog, instead of having to close it and go
    manually reload that channel from the left panel.
    `_relink_one_channel_interactively(item_index, ci)` opens
    `QFileDialog.getOpenFileName` (starting in the missing file's own
    last-known directory), then does a **pre-flight
    `imaging.load_grayscale` call before `push_undo()`** - same ordering
    as `_load_image_from_path` - so a bad/unreadable pick doesn't push a
    no-op undo entry; `_relink_channel` then repeats that same load once
    confirmed (an accepted extra decode - this is a one-off interactive
    click, not a hot path). Only touches `import_panel`/`recompute_preview`/
    `canvas.zoom_fit()` when `item_index` is the *currently active* item
    (same guard as the batch Locate path), but always refreshes that one
    item's carousel thumbnail via `_refresh_carousel_thumbnail_for_item`
    regardless of whether it's active.
- **Undo/redo**: snapshot-based (`_snapshot_state`/`_restore_state` in
  `main_window.py`), deep-copies `batch_items`. Any new `BatchItem` field
  must be threaded through `_snapshot_state`'s `BatchItem(...)` call or it
  silently resets on undo.
- **BatchItem identity**: `uid` is assigned once (monotonic, never reused)
  and used both as a stable identity for tracking "this same photo" across
  reordering, and as the import-order sort key. After restoring a session,
  `ensure_batch_item_uid_above(...)` must be called so new items in the new
  process can't collide with restored uids.
- **Missing/moved source files (added 2026-09-01)**: both session-restore
  paths (`_legacy_restore_session`/`_build_restored_items_from_data`) now
  keep `ChannelLayer.path` set to the last-known path even when
  `imaging.load_grayscale` can't be called (file gone/moved) - previously
  `path` was only ever set alongside a successful load, so a moved file
  silently reverted the layer to "never imported." `ChannelLayer.is_missing()`
  (`path` set but `has_image()` false) is the derived check used everywhere.
  A `BatchItem` is now only dropped on restore if literally no channel ever
  had a path (a genuinely empty item) — previously any item where all 3
  channels failed to load vanished from the session entirely, which is the
  bug this fixes (thumbnails "disappearing" after files moved/were deleted).
  `MainWindow.recompute_preview()` feeds every missing channel of the
  *active* item to `missing_files_banner` (`widgets/missing_files_banner.py`,
  `MissingFilesBanner` — a `QFrame` above `self.canvas` in
  `canvas_container`, styled like the app's other warning affordances
  rather than a native dialog) so the preview area shows which channel(s)
  and last-known path(s) are missing instead of just going blank; the
  filmstrip thumbnail itself is unaffected by this fix beyond simply still
  existing (it was already a plain placeholder box when `has_image()` is
  false — the bug was the item vanishing, not the thumbnail rendering).
  `MainWindow.on_locate_missing_files()` (wired to the banner's Locate
  button) opens a folder picker and relinks missing channels across
  **every selected photo** (`self.carousel.selected_indices()`, falling
  back to just the active photo if the selection is empty) in one action -
  not just the active item shown in the preview, since the whole point is
  fixing many photos whose shared source folder moved, in one pick. For
  each missing channel it looks for a file with the same basename as its
  last-known path (`_find_file_in_folder` — direct child first, then
  `os.walk` for a nested subfolder) inside the chosen folder, then reloads
  it via `_relink_channel(item, ci, path)` - a lower-level sibling of
  `_load_image_from_path` that works on an arbitrary (possibly non-active)
  `BatchItem`/channel index, never touches per-active-item UI, and never
  resets alignment/tone (those are already sitting correctly on the layer
  from restore - only image data/`path` change) - unlike a fresh manual
  "Load image", which is a *reset*, not a relink. One `push_undo()` covers
  the whole batch of relinked channels, same convention as
  `paste_settings_to`/`reset_batch_items`/`delete_batch_items`. Any channel
  basename-matching couldn't find (e.g. the file was *renamed*, not just
  moved - basename matching can't help there) is collected into
  `unresolved` and surfaced via a `QMessageBox.warning` (`dialog_locate_failed_title`/
  `_text`), listing each unresolved `(photo base, channel letter)` pair and
  explaining the two ways out didactically: retry Locate with a different
  folder, or reimport that channel manually via the Independent Channels
  panel. `original_base` snapshots every targeted item's `base` *before*
  the relink loop runs, specifically so the dialog's photo name can't drift
  mid-loop if that same item's reference channel gets relinked (which
  renames `item.base`, same as a manual reload) right before one of its
  other channels fails - a real bug caught by testing this exact sequence.
- **Filmstrip sort**: `MainWindow.sort_mode`/`sort_reversed` +
  `BatchItem.custom_order`. Dragging a card always writes a fresh
  `custom_order` sequence — remember it must be assigned so that re-applying
  `_apply_current_sort()` (which honors `sort_reversed`) reproduces the same
  on-screen order (see `on_carousel_reordered`), not the naive 0..N-1 in
  display order.
- **Top toolbar** (`MainWindow._build_top_toolbar`): a plain `QToolBar`
  below the native title bar, NOT merged into it via
  `setUnifiedTitleAndToolBarOnMac` — that was tried and reverted (bridged
  into Cocoa's native unified title bar, AppKit decides the real layout and
  ignores every Qt-side lever; confirmed via screenshots from the user).
  Getting pixel-perfect placement next to the traffic lights would need
  native PyObjC/Cocoa code bypassing Qt's toolbar system entirely, which the
  user has declined twice as disproportionate for the payoff.
  Separately, **`QToolBar.setContentsMargins()` doesn't apply per-edge to
  its children even in plain (non-unified) mode** — confirmed empirically:
  it folds into the toolbar's size hint but the internal layout still
  top/leading-anchors children, dumping all the leftover space at the
  trailing end (this is what caused the same vertical-centering and
  left/right-symmetry bugs even after dropping unified mode). The working
  pattern used here: give buttons the toolbar's full height directly (so
  there's no leftover vertical space to mis-place, and each `SvgToolButton`
  centers its own icon in its own box via `paintEvent`) and use real fixed-
  width spacer `QWidget`s as the first/last toolbar items for edge margins,
  instead of trusting `contentsMargins` for either axis.
- **Top toolbar reshuffled + left-panel tool switcher added (2026-09-02),
  ahead of wiring the standalone scan tool into the main app.** Final
  left-to-right order: **New Session, Open Session, Save, Import** |
  *(stretch)* | **Trichrome, Global Correction, Crop, Scan** | *(stretch)*
  | **Export, show/hide Left Panel, show/hide Right Panel, Help**.
  `left_panel_toggle_btn` moved out of the left cluster into the right one
  (now sits between Export and the right-panel toggle) - same button
  object/wiring, just relocated in `top_toolbar.addWidget(...)` order.
  `new_session_toolbar_btn`/`open_session_toolbar_btn` are plain
  `SvgToolButton`s wired straight to the existing `action_new_session`/
  `action_open_session` (already used by the File menu's ⌘N/⌘O) - no new
  logic, just a toolbar shortcut to actions that already existed.
  `import_toolbar_btn` kept its existing behavior (`open_batch_window`),
  only its icon changed (`Toolbar/Import.svg` → `Toolbar/image-plus.svg`) -
  the old download-tray glyph didn't read as "add photos" the way an
  image+plus does; `Toolbar/Import.svg` itself was left on disk unreferenced
  rather than deleted, in case it's wanted elsewhere later.
  - **New left-panel tool switcher (`left_tool_group`: `trichrome_toolbar_btn`/
    `scan_toolbar_btn`), independent of the existing right-panel one
    (`right_tool_group`: `settings_toolbar_btn`/`crop_toolbar_btn`)** - two
    separate `QButtonGroup`s, each exclusive within itself but not with each
    other, so e.g. Trichrome (left) + Crop (right) can both be checked at
    once; this is why the toolbar visually interleaves them
    (Trichrome, Global Correction, Crop, Scan) rather than grouping each
    pair together - that interleaved order was requested explicitly, not
    an oversight. Same wiring pattern as the right pair: buttons constructed
    in `_build_top_toolbar` (`trichrome_panel`/`scan_panel` don't exist yet
    at that point), `toggled` connected to `trichrome_panel.setVisible`/
    `scan_panel.setVisible` in `_connect_signals()` once both panels exist -
    mirrors `settings_toolbar_btn.toggled.connect(self.global_panel.setVisible)`
    exactly, no extra state machine needed since neither has Crop's
    escape/apply complexity. Bare keyboard shortcuts **T**/**S** added
    alongside the existing **E**/**C** in `keyPressEvent` (same
    `not text_editing` guard).
  - **`trichrome_panel`**: a new plain `QWidget` wrapping exactly what the
    left panel already always showed - `import_panel` +
    `independent_channels_group` - moved inside it verbatim, no behavior
    change. **`scan_panel`**: a new, currently-empty placeholder `QWidget`
    (`scan_panel_placeholder` i18n text, "Scan tool integration is coming
    soon") - both live side by side inside `left_container`, exactly
    mirroring `right_container`'s existing `global_panel`/`crop_panel`
    sibling pattern, with `scan_panel.setVisible(False)` initially so
    Trichrome (matching prior default behavior) shows on launch.
    Wiring the real `scan_tool/` UI into `scan_panel` is future work -
    this pass only prepares the panel-switching shell per the user's own
    framing ("faisons des petites modifications visuelles" before the
    real integration).
  - **New icons, sourced from the real Lucide repo** (same family
    `file.svg`/`file-settings.svg` already came from) **rather than
    approximated by hand** - fetched via
    `raw.githubusercontent.com/lucide-icons/lucide/main/icons/<name>.svg`
    and re-wrapped in this project's own SVG attribute convention
    (`preserveAspectRatio`, `class="lucide lucide-<name>"`, `stroke="#ffffff"`,
    `stroke-width="1.5"` in place of Lucide's own default `currentColor`/`2`):
    `Toolbar/file-new.svg` (Lucide `file-plus`), `Toolbar/file-open.svg`
    (Lucide `file-symlink` - Lucide has no icon literally named "open a
    file"; this was the closest real glyph matching the same single-badge-
    cut-into-the-outline construction `file-settings.svg`/`file-cog`
    already uses, picked over `file-input`'s alternative arrow-into-file
    motif since it stays self-contained within the file silhouette instead
    of extending a shaft outside it). `Toolbar/image-plus.svg` is Lucide's
    real `image-plus`, verbatim. **`Toolbar/trichrome.svg`** (3 overlapping
    circles) and **`Toolbar/scan.svg`** (camera + a small "+" badge) were
    initially hand-composed here (no Lucide `camera-plus` upstream),
    verified by rendering each to a PNG before finalizing - **both since
    superseded**: the user sourced real replacements from Supericons
    (Tabler icons) the same day - `trichrome_toolbar_btn` still points at
    `Toolbar/trichrome.svg` (the user overwrote that file in place with
    their own version, so no code change was needed), while
    `scan_toolbar_btn` was repointed to the user's **`Scan/camera-plus.svg`**
    (a real `icon-tabler-camera-plus`, dropped alongside several other
    real `Scan/camera-*.svg` icons - question/check/search/cancel/cog/
    pause/minus - staged for later scan-tool UI work, not all wired up
    yet). The old hand-composed `Toolbar/scan.svg` was left on disk
    unreferenced rather than deleted, same conservative call as the
    superseded `Toolbar/Import.svg` above.
- **"Session Options" toolbar button, added 2026-09-03** -
  `session_options_toolbar_btn` (`Toolbar/file-settings.svg`, the existing
  file-cog icon - not a new asset), sitting between Open Session and Save.
  Opens `show_session_options_dialog()`, a placeholder window (currently
  just "Session options are coming soon.", `session_options_placeholder`)
  built with the exact same recipe as the existing `_show_help_dialog`
  (plain `QDialog`, `QShortcut(QKeySequence.Close, ...)`, a single Close
  button) rather than a bespoke layout - reusing that convention is what
  makes it look consistent with the app's other secondary windows without
  a separate styling pass. No session-options functionality actually
  exists yet - this is purely the entry point + empty shell, same
  "shell first, spec later" pattern as `scan_panel`.
- **Reassignable tool layout (Window ▸ Layout), added 2026-09-03.** Until
  now, `left_tool_group` (Trichrome/Scan) and `right_tool_group` (Global
  Correction/Crop) were fixed pairs, each hardcoded to its own sidebar. The
  user asked to be able to move any of the 4 tools to either side, with a
  layout control living in the Window menu - implemented as:
  - **`self.tool_side: dict[str, str]`** (`"trichrome"`/`"scan"`/
    `"global_correction"`/`"crop"` → `"left"`/`"right"`), initialized from
    `_DEFAULT_TOOL_SIDES` in `__init__`. **`self._tool_registry`** (built at
    the end of `_build_ui`, right before the first `retranslate_ui()` call,
    since every tool's button+panel exists by then) maps each tool key to
    its `(toolbar_button, panel_widget)` pair - the one lookup table
    everything else in this feature is built on.
  - **`_move_tool_to_side(tool_key, new_side)`** is the actual mechanic:
    moves the button between `left_tool_group`/`right_tool_group`
    (`QButtonGroup.removeButton`/`addButton`), reparents the panel widget
    between `self.left_layout`/`self.right_layout` (both now stored as
    `self.` attributes, not local variables, specifically so this method
    can reach them - `insertWidget(layout.count() - 1, panel)` to land
    right before the trailing `addStretch(1)`, which `addStretch` always
    leaves as the layout's last item), and updates `tool_side`. Reparenting
    a widget into a different layout automatically reparents it to that
    layout's owning widget too - no manual `setParent()` needed.
    **Active-tool bookkeeping on move**: if the moved tool was the active
    (checked) one, whichever tool remains on its old side (if any) becomes
    active there instead, so that side doesn't go blank, and the moved
    tool stays checked on arrival so its new side doesn't go blank either.
    If the moved tool *wasn't* active, it only gets force-checked on
    arrival if its new side had literally nothing active already (an empty
    side) - otherwise whatever was already active there is left alone.
    `histogram_box` is not part of any of this - it stays a fixed sibling
    at the top of `right_container` regardless of which tools move through
    it, exactly as before (per the Crop-tool section above).
  - **Window menu originally had a "Layout" submenu with 4 per-tool "Move
    X to Left/Right Panel" actions** (`move_trichrome_action` etc.,
    `_toggle_tool_side()`, `_update_layout_menu_labels()`) - **removed
    2026-09-03** once drag-and-drop block reordering (below) and Layout
    Presets made them redundant; the user's own framing was "maintenant
    qu'on peut tout réorganiser à la main, plus besoin de ces options."
    `_move_tool_to_side`/`self.tool_side`/`self._tool_registry` themselves
    are unchanged and still very much used (by `reset_layout()` and by
    Layout Preset load) - only the direct interactive menu triggers for
    moving one tool at a time were deleted. **Reset Layout**
    (`reset_layout()`) is now a direct `Window` menu action (no longer
    nested in a submenu), restoring the one default configuration stated
    when this feature was first built: Trichrome+Scan left, Global
    Correction+Crop right, Trichrome and Global Correction active, both
    side panels visible, thumbnail strip visible, zoomed to fit, plus (as
    of the drag-reorder feature below) both panels' block order reset to
    default too.
  - **Persisted through both session mechanisms**, following the existing
    `_apply_restored_layout()` shared-tail convention exactly (see the
    session-persistence architecture note up top) - it gained 3 new
    optional, None-safe parameters (`tool_side`, `active_left_tool`,
    `active_right_tool`) so an old saved session/`.trirgb` from before this
    feature just keeps `__init__`'s `_DEFAULT_TOOL_SIDES` default rather
    than needing every caller to know that default itself.
    `_collect_session_data()`/`_save_session_state()` gained matching
    writes, via a new small helper `_active_tool_for_side(side)` (which of
    the tools currently on that side is checked, or `None` if a side was
    left with nothing active - a real if unlikely reachable state once
    tools can be freely reshuffled). QSettings keys: `tool_side_<key>` ×4,
    `active_left_tool`, `active_right_tool`; `.trirgb` JSON: `tool_side`
    (one nested dict), `active_left_tool`, `active_right_tool`.
  - Verified headlessly: moving both the active and an inactive tool
    (checking the other-side/same-side active-tool bookkeeping above in
    both directions), button-group membership and panel reparenting after
    a move, menu label text tracking current side, `reset_layout()`
    restoring the full default state, the Window-menu actions' own click
    wiring, and a full round-trip through *both* persistence mechanisms
    (QSettings autosave and `.trirgb` save/open) confirming a custom
    layout survives a relaunch. **A real testing trap hit while writing
    these tests**: `_legacy_restore_session()` silently drops a session
    with zero real photo content entirely (its own pre-existing "genuinely
    empty item" filter - see the missing/moved-source-files note above)
    *before* ever reaching `_apply_restored_layout()` - the QSettings
    round-trip test only started working once a fake `layer.path` string
    was set so the item would survive that filter; this isn't a bug in the
    layout feature, just a precondition for testing session persistence at
    all that's easy to trip over.
- **Drag-and-drop block reordering within a side panel, added 2026-09-03.**
  The user's own vocabulary (see Terminology above) treats each side panel
  as a stack of "blocs" - Fichiers/Trichromie on the left,
  Histogramme/Global Correction/Recadrage on the right. Because the tool
  switcher only ever shows one of Trichrome/Scan on the left and one of
  Global Correction/Crop on the right, at most **2 blocks are ever visible
  in a panel at once** (Fichiers+Trichromie on the left; Histogramme plus
  whichever of Global Correction/Recadrage is active on the right) - so
  the whole feature reduces to "swap the order of these 2 blocks," not a
  general N-item reorder like the carousel's.
  - **`trichrome/widgets/block_header_bar.py`** - **revised same day** after
    the user tried the first version and gave 3 pieces of feedback: use a
    small dedicated drag handle instead of the whole title bar being
    draggable (the two options were both offered up front, the user picked
    the other one once they saw it in practice); `import_panel`/
    `histogram_box` shouldn't have gained title text at all ("ces fenêtres
    sont claires sans le texte") - reverted, no `import_panel_title`/
    `histogram_panel_title` i18n keys anymore, `import_panel`/`histogram_box`
    no longer have a `title_label` attribute; and the block headers overall
    "prennent beaucoup de place" - every panel with a header row
    (`independent_channels_group`, `GlobalPanel`, `CropPanel`) had its outer
    `QVBoxLayout`'s top content margin halved (`max(2, top // 2)`, reading
    the existing margin via `getContentsMargins()` rather than guessing a
    fixed value, so it stays proportional to whatever the style's default
    actually is).
    - **`BlockDragHandle(SvgToolButton)`**: a small grip icon
      (`General/grip-vertical.svg` - no matching icon existed in
      `resources/icons/`, sourced from the real Lucide `grip-vertical` via
      `raw.githubusercontent.com` and re-wrapped in this project's own SVG
      convention, same precedent as `file-new.svg`/`image-plus.svg`), the
      **only** part of a header row that starts a drag -
      `mousePressEvent`/`mouseMoveEvent` past
      `QApplication.startDragDistance()`, same threshold-based gesture
      detection as the carousel's own drag. Takes `drag_source` (the whole
      block widget, e.g. `self` for `GlobalPanel`/`CropPanel`/`ImportPanel`,
      or `self.histogram_box`/`self.independent_channels_group` from
      `main_window.py`) - `_ghost_pixmap()` grabs and paints that whole
      widget at 0.85 opacity as the `QDrag`'s pixmap, and the hotspot is
      computed via `self.mapTo(drag_source, event.pos())` so the ghost
      tracks the cursor at the same relative position the grip was grabbed
      from - **this is what makes the block visibly "move" under the
      cursor while dragging**, not just show a generic drag icon. Since
      only the grip widget itself handles mouse events now, no
      `WA_TransparentForMouseEvents` trick is needed on title labels or
      buttons anymore - they're untouched, ordinary interactive children
      again, `header_row` went back to a plain `QHBoxLayout` added via
      `layout.addLayout(header_row)` (the `BlockHeaderBar` QWidget wrapper
      from the first version is gone entirely). `import_panel`/
      `histogram_box`'s header rows are now just the grip + a trailing
      stretch, no label at all.
    - **`BlockReorderZone(QWidget)`** is still the drop target
      (`self.trichrome_panel` on the left, `self.right_container` on the
      right) - `setAcceptDrops(True)` + `dragEnterEvent`/`dragMoveEvent`/
      `dropEvent`, emitting `block_dropped(dragged_key)` on any valid drop,
      same as before. No drop-position math (unlike the carousel's
      `_insert_index_for_x`) since with only 2 blocks "the other one" is
      unambiguous - **any** valid drop just toggles which block is first,
      regardless of which one was actually dragged.
    - **New: live drop-target highlight**, addressing "j'aimerais que le
      déplacement soit plus visuel... une zone indique les emplacements
      possibles." `set_block_widgets({key: widget})` (called once per zone
      right after construction in `main_window.py`) is what lets the zone
      resolve "the other visible block" itself instead of needing
      `main_window.py` to tell it. `dragEnterEvent` decodes the dragged
      block's key from the mime data, finds its sibling via
      `_target_widget()` (the other mapped widget that `isVisible()` -
      real interactive-drag-only code path, so unlike
      `_apply_right_block_order()` above, `isVisible()` is fine here; there
      is no pre-`show()` call site for an actual mouse drag), and calls
      `_set_highlight(widget)`, which toggles a `dragReorderTarget`
      dynamic property (`setProperty` + `style().unpolish()`/`.polish()`
      to force Qt to re-evaluate the stylesheet) - cleared again on
      `dragLeaveEvent`/`dropEvent`. `DRAG_TARGET_QSS` (a
      `QGroupBox[dragReorderTarget="true"] { border: 2px solid #5b9bd5;
      border-radius: 6px; }` rule) is applied once via `self.setStyleSheet(...)`
      on `MainWindow` itself near the end of `_build_ui` - QSS cascades to
      every descendant regardless of nesting, and every draggable block is
      a `QGroupBox`, so one rule covers all 5.
  - **State: `self.left_files_block_first`/`self.right_histogram_first`**
    (bools, default `True` - today's default order). `_apply_left_block_order()`/
    `_apply_right_block_order()` reposition the blocks in
    `self.trichrome_panel_layout`/`self.right_layout` from scratch each
    time (remove all, reinsert in the right order) rather than doing an
    incremental swap - simpler and idempotent, safe to call after every
    tool switch, restore, or preset load without tracking prior state.
    `_apply_right_block_order()` determines the active right tool via
    `self.crop_toolbar_btn.isChecked()`, **not** `self.crop_panel.isVisible()`
    - a real bug hit while testing headlessly: `isVisible()` depends on the
    whole ancestor chain including the top-level window actually being
    shown (`.show()`), which isn't true at every call site (session
    restore happens before `main()` calls `show()`) - `isChecked()` reflects
    logical state regardless, the same reason `_apply_restored_items`
    already checks `crop_toolbar_btn.isChecked()` rather than the panel's
    own visibility elsewhere in this file. `_apply_right_block_order()`
    also no-ops if either `global_correction`/`crop` isn't currently on the
    right side (`self.tool_side`), since a loaded layout preset or a stale
    `.trirgb` could in principle put them elsewhere.
    `settings_toolbar_btn.toggled`/`crop_toolbar_btn.toggled` both also
    call `_apply_right_block_order()` (in addition to their existing
    `global_panel.setVisible`/`_on_crop_tool_toggled` connections) so
    switching tools preserves whichever histogram-vs-tool order was set.
  - **Persisted through both session mechanisms**, same
    `_apply_restored_layout()` shared tail as `tool_side` above - 2 more
    optional, None-safe parameters (`left_files_block_first`,
    `right_histogram_first`). QSettings keys of the same name; `.trirgb`
    JSON keys of the same name. `reset_layout()` also resets both to
    `True` and reapplies.
  - Verified headlessly (both the original pass and again after the
    grip-handle revision): swapping on the left and right, that a tool
    switch (Global Correction ↔ Crop) preserves the histogram-relative
    order instead of resetting it, `reset_layout()` restoring default
    order, `_target_widget()` correctly resolving the sibling block both
    before and after a tool switch, the `dragReorderTarget` property
    correctly toggling on/off via `_set_highlight()`, `import_panel` no
    longer having a `title_label` attribute at all post-revert, and full
    round-trips through both QSettings autosave and `.trirgb` save/open.
    **Not, and can't be, verified here**: the actual drag gesture's feel -
    the ghost pixmap's opacity/positioning, whether the highlight border
    reads clearly at real size, general "does this feel good" - all need
    the user's own manual pass, same as any other visual/interactive
    change per the Testing section below.
  - **Third pass, 2026-09-04, after the user tried it for real**: two
    things fixed. (1) "Le drag visuel fonctionne mais la prévisualisation
    n'est pas très intuitive" - the ghost pixmap at full block size
    visually blanketed the highlighted drop target while hovering over it,
    defeating the point of the highlight. `_GHOST_SCALE = 0.42` now scales
    the ghost down (keeping aspect ratio) and draws a 1.5px white outline
    around it so it reads as a distinct floating preview rather than a raw
    screenshot fragment; the hotspot is scaled by the same factor so it
    still tracks the cursor at the same relative grabbed point instead of
    jumping. `DRAG_TARGET_QSS` also got stronger - a dashed border (was
    solid) plus a light `rgba(91, 155, 213, 40)` fill, a more standard
    "active drop zone" look than a thin selection-style outline; QSS on a
    native `QGroupBox` was already confirmed to render reliably in this
    app (`ChannelPanel`'s per-channel `QGroupBox::title` color rules
    predate this and work fine), so the fill wasn't a risk. (2) "pareil
    pour le glissé qui ne fonctionne pas parfaitement" - a real Qt
    gotcha: `QDrag.exec()`'s own internal event loop consumes the mouse
    release that ends the drag, so `BlockDragHandle` (a `QToolButton`
    subclass) never gets a normal `mouseReleaseEvent` for that press -
    `QAbstractButton`'s internal "down" state could stay stuck `true`
    afterward. Fixed with an explicit `self.setDown(False)` right after
    `drag.exec(...)` returns.
  - **Also 2026-09-04, separately: "tu peux encore réduire le header des
    blocs."** Two real gaps from the first margin-reduction pass: `import_panel`
    and `histogram_box` had **no** top-margin reduction applied at all (their
    own `QVBoxLayout`s were missed since they didn't have a header row yet
    when that pass was written) - both now get the same treatment as the
    other 3. All 5 blocks' top margin is now a flat `4` (was `max(2, top //
    2)`, i.e. ~5 from an 11px default - not enough per the user's follow-up)
    - a fixed value now instead of proportional, and `BlockDragHandle`'s own
    size shrank again, `(18, 22)`/`14` → `(16, 16)`/`12`, so the grip itself
    contributes less to the header row's height too.
- **Full block system overhaul, 2026-09-04 - superseded the exclusive
  tool-switcher entirely.** Requested in one pass: split "Global
  Correction" into two peer blocks (Light, keeping Negative; Color);
  restore Files' title (only `histogram_box` stays title-less); per-block
  collapse (header-only) and close (fully hidden, restorable); the Tools
  menu repurposed to list every block with independent show/hide
  checkboxes; and - raised right as this was being built - **cross-panel
  drag**, not just reordering within one side. That last point is what
  forced the real architectural question: the old exclusive pairs
  (`left_tool_group`: Trichrome vs Scan; `right_tool_group`: Global
  Correction vs Crop) can't coexist with blocks freely moving between
  panels and being hidden independently - two mechanisms fighting over the
  same widgets. Asked the user directly; their answer: **keep the 4
  toolbar buttons in their toolbar position but disable them
  (`setEnabled(False)`) - what becomes of them is a follow-up
  conversation, not decided here.** Every block is now independently
  positioned/visible/collapsed; nothing about `trichrome_toolbar_btn`/
  `scan_toolbar_btn`/`settings_toolbar_btn`/`crop_toolbar_btn` is wired to
  anything anymore beyond the two `QButtonGroup`s they still nominally sit
  in (harmless, since disabled). **Superseded 2026-09-04** - that "follow-up
  conversation" happened: the 4 buttons are re-enabled and repurposed into
  built-in default-layout quick-switches, see the "4 old tool-switcher
  toolbar buttons repurposed" entry under Layout Presets below (this
  paragraph is kept as history of why they went inert in the first place).
  - **State (all in `main_window.py`)**: `_ALL_BLOCK_KEYS = ("files",
    "channels", "histogram", "light", "color", "crop", "scan")`.
    `self.block_side: dict[str, str]` ("left"/"right"),
    `self.block_visible: dict[str, bool]`, `self.block_collapsed: dict[str, bool]`,
    `self.left_block_order`/`self.right_block_order: list[str]` (every
    block assigned to that side, in order - **hidden blocks keep their
    slot**, never removed from the list, so re-showing one via the Tools
    menu restores it at the same position, per the user's explicit "le
    réactiver... le fait réapparaître... à sa dernière position").
    `_DEFAULT_BLOCK_SIDE`/`_DEFAULT_BLOCK_VISIBLE`/`_DEFAULT_LEFT_BLOCK_ORDER`/
    `_DEFAULT_RIGHT_BLOCK_ORDER` reproduce exactly what the old exclusive
    switcher showed by default (Files+Channels left; Histogram+Light+Color
    right; Crop and Scan hidden) - `reset_layout()`'s new job.
  - **`_apply_block_layout()`** is the single place block-system state
    becomes actual on-screen layout: for each side, clears
    `left_layout`/`right_layout` and reinserts every block in that side's
    order list, `setVisible()` per `block_visible AND block_side == side`.
    Also refreshes both `BlockReorderZone`'s `set_block_widgets()` mapping
    (since a block's side can change) and re-syncs every Tools-menu
    action's checked state. Called after every drag-drop, visibility
    toggle, `reset_layout()`, and layout restore - deliberately a full
    rebuild each time rather than an incremental patch, so it's trivially
    correct regardless of how many things changed at once.
  - **`trichrome/widgets/block_header_bar.py` gained `start_block_chrome()`/
    `finish_block_chrome()`** - the shared construction helper every block
    now goes through (`ImportPanel`, `LightPanel`, `ColorPanel`,
    `CropPanel`, and the 3 still built inline in `main_window.py`:
    `independent_channels_group`, `histogram_box`, `scan_panel`).
    `start_block_chrome(block, key, title_i18n_key_or_None)` sets the tight
    top margin, starts `header_row` with the drag handle + optional title;
    the caller adds its own buttons (Reset, Copy, Invert, etc.) to
    `header_row` next; `finish_block_chrome(outer, header_row)` appends the
    collapse toggle (`General/chevron-down.svg`) and close button
    (`General/close.svg` - both real Lucide icons, same
    fetch-and-rewrap precedent as the grip icon) at the end, adds
    `header_row` to `outer`, and builds a `body` `QWidget`/`QVBoxLayout` for
    the real content - returns `(body, body_layout, collapse_button,
    close_button)`. **Every block widget exposes `.body`** (the contract
    `set_block_collapsed()`/`reset_layout()`/`_apply_restored_layout()` all
    rely on) - the class-based panels set `self.body = body` themselves;
    the 3 inline-built ones needed it set explicitly right after
    construction (`self.histogram_box.body = self.histogram_body`, etc.) -
    a real bug caught by testing: `reset_layout()` crashed with
    `AttributeError: 'QGroupBox' object has no attribute 'body'` on
    exactly those 3 before this was added.
  - **`BlockReorderZone` generalized from a 2-block swap to real N-item,
    cross-panel reordering.** `set_block_widgets({key: widget})` still
    seeds which blocks *can* live in a zone; `_visible_widgets(exclude_key)`
    walks the zone's own layout and returns currently-visible children
    (skipping the dragged block, which stays in place/visible during its
    own drag - only a ghost pixmap follows the cursor). `dragEnterEvent`/
    `dragMoveEvent` now accept a drag **regardless of whether the dragged
    key belongs to this zone** - that's what makes cross-panel drops work,
    both zones just accept any valid `BLOCK_REORDER_MIME`. On hover,
    `_nearest_widget()` (closest visible block to the cursor's Y, by
    vertical-center distance) drives the highlight - simpler than a full
    insertion-line indicator, and still clearly reads as "drop near here."
    On drop, `_insert_index_for_y()` computes a real insertion index (first
    visible widget whose midpoint is below the drop Y) and emits
    `block_dropped(dragged_key, insert_index)`.
  - **`MainWindow._on_block_dropped(target_side, dragged_key, insert_index)`**
    is the one handler for both same-panel reorder and cross-panel move
    (they're the same operation once you don't special-case "same side"):
    removes `dragged_key` from wherever it currently sits (its old side's
    order list), sets `block_side[dragged_key] = target_side`, then
    translates `insert_index` (a position among the target zone's visible
    blocks, excluding the dragged one) into a real position in the target's
    *full* order list by finding which visible key currently sits there
    and inserting right before it (or appending, past the last visible
    one) - this is what lets hidden blocks keep sane relative positions
    even as visible ones get reordered around them.
  - **Light/Color split (`trichrome/widgets/global_panel.py`, rewritten)**:
    `GlobalPanel` (one `QGroupBox`, two subheaders) became `LightPanel`/
    `ColorPanel` (two peer `QGroupBox`es, each going through
    `start_block_chrome`/`finish_block_chrome` like every other block).
    `LightPanel` keeps `invert_button` (Negative) in its header, per the
    user's explicit "garde le bouton Négatif dans le bloc light", plus its
    own full-size header `reset_button` (`HEADER_RESET_BTN_SIZE`, matching
    every other block - not the old smaller companion-sized
    `reset_light_btn`). `ColorPanel` keeps `pick_white_balance_btn` (the
    eyedropper) plus its own full-size `reset_button` - the old separate
    companion-sized `reset_white_balance_btn` next to the eyedropper was
    dropped as redundant once Color got its own proper header Reset
    covering the exact same fields (`on_reset_white_balance` already
    reset temperature/tint/saturation together). `main_window.py`'s
    `on_global_changed`/`_sync_global_panel_from_model` now read/write
    both panels instead of one; `on_global_reset` (the old "reset
    everything" handler, tied to a button that no longer exists once
    Light/Color are separate peer blocks) was removed outright - dead code,
    confirmed via grep before deleting.
  - **A real functional gap caught by testing, not just a naming one**:
    `crop_toolbar_btn.isChecked()` was used in ~10 places across
    `main_window.py` as "is the Crop tool currently active" (gating the
    Crop-tool-only full-vs-cropped preview frame, Enter-to-apply, Escape-
    to-cancel, etc.) - with the button now permanently disabled/inert, all
    10 were mechanically replaced with `self.block_visible.get("crop",
    False)`, the new equivalent. Two of those call sites needed more than
    a mechanical swap: the Escape handler used to call
    `self.settings_toolbar_btn.setChecked(True)` to "switch back" -
    replaced with `self.set_block_visible("crop", False)` (hide the block
    outright, since there's no longer a single other tool to switch back
    *to* - Light/Color are usually already visible alongside Crop, not
    exclusive with it). `on_crop_apply()` similarly now hides the Crop
    block after committing, instead of checking a dead button.
    `_on_crop_tool_toggled` (the old handler wired to
    `crop_toolbar_btn.toggled`, which armed/disarmed the canvas crop
    overlay and disarmed the white-balance eyedropper) was renamed
    `_on_crop_block_visibility_changed` and is now called explicitly from
    `set_block_visible()` whenever `key == "crop"` - **and also explicitly
    from `reset_layout()` and `_apply_restored_layout()`**, since those two
    set `block_visible` directly through `_apply_block_layout()` rather
    than through `set_block_visible()` (which handles every block
    uniformly and can't special-case one key's side effects) - without
    this, a restored session with Crop visible would show the panel but
    leave the canvas crop-drag overlay disarmed, a real gap caught by
    testing the restore path specifically, not just construction.
  - **Verified headlessly**: default block layout matches the old
    switcher's default appearance exactly; all 4 toolbar buttons disabled;
    Negative lives on `LightPanel` only; Tools-menu checkbox toggling a
    block's visibility and vice versa (close button → menu unchecks);
    collapse hides/shows just a block's `body`; a full cross-panel drag
    (`_on_block_dropped("left", "light", 0)`) actually moves the widget
    between `left_layout`/`right_layout`; `reset_layout()` restores
    everything including re-arming/disarming the crop canvas overlay;
    slider → model (`on_global_changed`) and reset (`on_reset_light`/
    `on_reset_white_balance`) scoping stays correct now that they read
    from two separate panel objects; undo/redo unaffected (block-system
    state was already outside the undo stack, same as panel visibility
    always was); full round-trips through QSettings autosave, `.trirgb`,
    and Layout Presets. **A real test-harness trap hit while verifying
    this, not a code bug**: calling `mw.close()` after making genuine
    edits in a test script hangs forever under
    `QT_QPA_PLATFORM=offscreen`, because `closeEvent` correctly shows the
    app's real "unsaved changes" confirmation dialog (modal, waiting for
    input that never comes headlessly) - any future headless test that
    calls `.close()` needs either no real edits beforehand, or to not call
    `.close()` at all.
  - **Fourth pass, 2026-09-04, 3 more pieces of feedback after trying the
    block system for real:**
    1. **"Je veux éviter d'avoir de barre de scroll latérale... il faut
       adapter la largeur des blocs outils au side panels et non
       l'inverse."** Root cause, found by measuring `minimumSizeHint()`
       headlessly rather than guessing: `left_scroll` never got
       `setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)` -
       `right_scroll` already had it (see the 2026-09-02 note on the
       right sidebar), the left one was simply missed when
       `left_container` became a `BlockReorderZone` holding blocks
       directly. Added. But the real fix per the user's own framing
       ("adapt block width to the panel, not the other way around") is
       that `independent_channels_group` ("Trichromie") measured **364px**
       against `left_scroll`'s 360px minimum - shrinking the collapse/
       close buttons (next point) brought every block back under its
       panel's own minimum width with margin (verified by measuring all 7
       against both panels' minimums headlessly).
    2. **"Les bouton hide et close peuvent être plus petits et plus
       discrets... la croix doit visuellement être de la même hauteur que
       le bouton collapse."** `finish_block_chrome()`'s collapse/close
       buttons moved off the shared `HEADER_COMPANION_BTN_SIZE`/
       `HEADER_COMPANION_ICON_SIZE` (34×30/20, meant for a panel's own
       primary actions like Reset/Copy) onto new dedicated, smaller
       constants: `_UTILITY_BTN_SIZE = (22, 22)` for both boxes (same
       size for both, so click targets stay identical), but **different
       icon sizes** - `_COLLAPSE_ICON_SIZE = 13` vs `_CLOSE_ICON_SIZE = 9`.
       The asymmetry is deliberate: Lucide's `x` glyph spans corner-to-
       corner (~50% of its 24-unit viewBox height) while `chevron-down` is
       a shallow centered dip (~25%) - at equal `icon_size` the X reads as
       visibly taller/heavier than the chevron even though the button
       boxes are pixel-identical, which is what the user was flagging.
       Sizing the X's `icon_size` down (roughly proportional to the ratio
       of those two path-height fractions) is what makes the two read as
       a matched pair.
    3. **"J'aime la couleur bleu et les pointillés... mais dans l'état on
       a l'impression que le déplacement d'outil vient remplacer les
       autres blocs et non s'intégrer au dessus / en dessous."** The
       `dragReorderTarget` dynamic-property + QSS whole-widget highlight
       (border+fill over one entire target block) is gone - replaced with
       a **thin dashed insertion line** drawn between blocks, at the exact
       gap the drop would land in. `BlockReorderZone._insert_position(y,
       exclude_key)` now returns `(insert_index, indicator_y)` together
       (previously two separate methods, `_insert_index_for_y`/
       `_nearest_widget`, computed similar-but-not-identical things) so
       the drawn indicator and the actual drop logic can never disagree.
       `paintEvent` draws it directly on the zone widget itself (a plain
       dashed `QPen(QColor("#5b9bd5"), 2.5, Qt.DashLine)` line with small
       filled end-caps) - same blue the user said they liked, kept
       unchanged; `DRAG_TARGET_QSS` and the old `_set_highlight()`
       mechanism were removed outright (dead code once nothing sets the
       property anymore).
    - **Verified headlessly**: `left_scroll`'s scrollbar policy; every
      block's `minimumSizeHint()` against its own panel's minimum width;
      collapse/close button box sizes match while icon sizes differ;
      `_insert_position()` returns index 0 near the top, the correct
      mid-gap index between two visible blocks, and `len(visible)` past
      the last one, with a real end-to-end drop still landing at the
      expected order position. **Not verified here** (needs the running
      app): whether the insertion line actually reads clearly at real
      screen size/DPI, and whether the resized collapse/close buttons are
      still comfortably clickable at 22×22.
    - **One known residual edge case, not chased further**: block minimum
      widths were only checked against each block's *own current* side.
      Since blocks can now be dragged to the *other* panel too, dragging
      "Trichromie" (340px) to the right column, while that column is
      squeezed all the way down to its own 300px minimum, would still
      overflow - only reachable by combining a cross-panel drag with the
      splitter pulled to its tightest width, not the default/common case
      this pass fixed. Worth another pass if the user hits it in practice.
  - **Fifth pass, 2026-09-04, after trying it again:** the width fix above
    "seemed to work on the left panel but not the right," plus two more
    asks - tighter collapsed-block spacing, and matching every block's
    Reset/eyedropper/Negative icon size to the histogram block's (which
    the user liked).
    - **`HEADER_RESET_BTN_SIZE`/`HEADER_RESET_ICON_SIZE` (41×36/24) removed
      from `svg_icons.py` entirely** - `LightPanel.reset_button`/
      `invert_button`, `ColorPanel.reset_button`, `CropPanel.reset_button`,
      and `independent_channels_group`'s `reset_all_alignment_button`/
      `reset_all_color_button` (previously hardcoded `(41, 36)`/`24`
      inline, not even via the constant) all moved onto
      `HEADER_COMPANION_BTN_SIZE`/`HEADER_COMPANION_ICON_SIZE` (34×30/20) -
      which is exactly what `HistogramPanel.pick_button`/`reset_button`
      already used, confirmed by reading `histogram_widget.py` before
      assuming. This is very likely what actually explains the "right
      panel only" scrollbar report: the right panel's 3 always-crowded
      headers (Light/Color/Crop, each with 2-3 action buttons plus the new
      collapse/close pair) were the ones still using the larger size,
      while the left panel's only comparably-crowded header (Trichromie)
      got fixed by the previous pass's collapse/close shrink alone.
    - **`start_block_chrome()`'s bottom margin is now tight (4) too, not
      just top.** When a block is collapsed, its hidden `body` contributes
      no height, so the *bottom* margin ends up sitting directly under the
      header row - left at the ~11px style default (only top had been
      reduced in the third pass), a collapsed block still looked padded
      at the bottom while looking tight at the top. Both margins now match.
    - **Real bug, not just a numbers/sizing issue: `_apply_block_layout()`
      didn't force the scroll areas to re-evaluate their content width
      after a drag.** `QLayout.removeWidget()`/`insertWidget()` (how a
      drag reorders blocks) don't reliably prompt `QScrollArea`'s own
      `widgetResizable` machinery to recompute against the *current*
      layout state on their own - `_apply_block_layout()` now ends with
      `layout.invalidate()`/`layout.activate()` on both
      `left_layout`/`right_layout` plus `left_container.updateGeometry()`/
      `right_container.updateGeometry()`, forcing both scroll areas to
      re-check. Matches the user's own diagnosis exactly: "lorsque l'on
      déplace les blocs, cette adaptation n'est plus prise en compte."
    - **Verified headlessly**: both scroll areas' policy is
      `ScrollBarAlwaysOff` and stays that way after a drag; every block's
      `minimumSizeHint()` stays under its panel's minimum width even in a
      deliberately worst-case state (Crop shown, every `ChannelPanel`'s
      `align_box`/`tone_box` collapsible sections force-expanded via
      `.setChecked(True)`) - `channels` (Trichromie) dropped from 364px
      (over the 360px left-panel minimum) before this pass to 330px now,
      comfortably under; every header-row action button now measures
      34px wide uniformly, confirmed on one button from each of Light,
      Color, Crop, Trichromie's "reset all", and Histogram itself; the
      "channels" block's collapse toggle actually shrinks
      `independent_channels_group`'s height and hides `.body` correctly
      (it's the one block whose chrome is inline in `main_window.py`
      rather than a class's own `__init__`, so this wasn't a given).
      **Not verified here**: whatever specifically was meant by
      "l'outil individual channels ne semble pas s'adapter correctement" -
      no reproducible width/collapse defect was found for it once the
      general fixes above were in place; if it's still off after this
      pass, needs a more specific description (a screenshot, or exactly
      what looks wrong and when) to chase further.
  - **Sixth pass, 2026-09-04: the user pinpointed the actual cause of the
    "individual channels" overflow** - the block's own title text was too
    wide (plausible: the offscreen/headless test environment's font
    substitution doesn't reproduce real macOS font metrics, so the
    previous pass's width measurements weren't wrong exactly, just not
    representative of the real rendering the user was seeing). 4 changes:
    - **`independent_channels_group_title` renamed "Independent Channels"
      → "RGB Channels"** ("Canaux RVB" in French) - shorter, and also
      updated the one other place the old name was hardcoded into a help
      string (`dialog_locate_failed_text`, "reimport them one by one...
      using the Independent/RGB Channels panel on the left") so it stays
      consistent with the renamed block.
    - **Collapse button is now a real 2-state indicator, not a static
      icon**: `SvgToolButton` gained `set_rotation(degrees)` (rotates the
      drawn icon around its own center in `paintEvent`, generic - reusable
      anywhere a rotating icon is needed, same idea `SvgIconLabel` already
      had for the Crop ratio icon). `set_block_collapsed()` in
      `block_header_bar.py` now takes the `collapse_button` too and
      rotates it 90° when collapsed (chevron pointing right) vs. 0° when
      expanded (pointing down) - all 3 call sites in `main_window.py`
      (`_toggle_block_collapsed`, `reset_layout`,
      `_apply_restored_layout`) updated to pass it.
    - **`histogram_box` gained a title back** (`"menu_tools_histogram"`,
      already existed with correct EN/FR text) - a direct reversal of the
      third pass's "only histogram stays title-less" call; the user
      changed their mind after seeing it in practice. `start_block_chrome`
      already supported an optional title from the start, so this was a
      one-argument change plus wiring `self.histogram_title_label` into
      `retranslate_ui()`.
    - Verified headlessly: both renamed strings appear correctly in EN and
      FR; `SvgToolButton._rotation` flips 0↔90 on each collapse/expand
      click; `histogram_title_label.text()` reads "Histogram"/"Histogramme"
      correctly per language.
  - **Drop-to-remove, added 2026-09-04.** Two options were proposed for
    "remove a block by dragging it out of the panels" (a dedicated
    drop-to-delete target vs. any drop outside both panels counting as
    removal); the user picked the simpler one - **any drop outside both
    `BlockReorderZone`s removes the block**, same as clicking its own
    close button. `BlockDragHandle` gained `drag_rejected = Signal(str)`,
    emitted from `_start_drag()` when `drag.exec(...)` returns
    `Qt.IgnoreAction` (Qt's own signal that no drop target accepted the
    drag). `MainWindow` connects each block's handle via
    `widget.findChild(BlockDragHandle)` (the handle isn't in its own
    dict, so this avoids threading a 4th return value through every
    `start_block_chrome()` call site) to `_on_block_drag_rejected(key)`,
    which calls `set_block_visible(key, False)` (a no-op if already
    hidden - checked explicitly, so this can't double-fire a status
    message) and shows a status-bar message ("'X' removed - re-enable it
    from the Tools menu", `status_block_removed` i18n key) for 4 seconds,
    since a block silently disappearing from a drop-outside gesture isn't
    otherwise obvious the way clicking a dedicated × button is.
    **Known, accepted tradeoff**: `QDrag.exec()` reports a drag cancelled
    via Escape identically to one rejected by every drop target
    (`Qt.IgnoreAction` either way) - Qt gives no way to tell them apart
    from the source side. So pressing Escape mid-drag also removes the
    block, not just a genuine drop-outside. Left as-is rather than
    engineering a workaround, since removal is non-destructive (one Tools
    menu click restores it) and the user chose the simpler option
    knowing removal isn't a big/scary action here.
    - Verified headlessly: every block's handle is discoverable via
      `findChild` and wired; emitting `drag_rejected` end-to-end hides the
      block, unchecks its Tools-menu action, and shows the expected status
      message; emitting it again on an already-hidden block is a correct
      no-op (no duplicate/spurious status message); re-showing via the
      Tools menu afterward still works normally. **Not verified here**:
      the real drag-and-drop gesture itself (an actual mouse-driven
      `QDrag.exec()` call can't be driven headlessly) - only the
      `Qt.IgnoreAction` handling logic once that returns.
  - **Seventh pass, 2026-09-04 - the important find: a real, high-impact
    bug in the drag system itself, plus 6 more requests.**
    - **`import_panel.py` used block key `"import"`, but every other
      reference in `main_window.py` (`_ALL_BLOCK_KEYS`, `block_side`,
      `block_widgets`, etc.) uses `"files"` for this exact block.** The
      user reported "I can't move the files block to the right panel" -
      in fact it couldn't be moved *anywhere*, same-panel reorder
      included: `_on_block_dropped` looks up `self.block_side.get(dragged_key)`,
      which returned `None` for `"import"` and hit the early-return
      guard, silently doing nothing. This had been invisible to every
      previous round of headless testing because those tests all called
      `_on_block_dropped("left"/"right", "files", ...)` directly with the
      *correct* canonical key, never through the real
      `BlockDragHandle`-emitted MIME data that only `import_panel.py` got
      wrong. Fixed by changing the key passed to `start_block_chrome()`
      from `"import"` to `"files"`; verified this time via
      `import_panel.findChild(BlockDragHandle).block_key` (the actual
      value that would flow through a real drag) rather than calling
      `_on_block_dropped` with an assumed-correct key.
    - **Collapse chevron rotation direction was backwards.** The sixth
      pass's `+90°` for "collapsed" actually points the chevron *left*,
      not right - confirmed by hand-tracing the rotated SVG path's
      coordinates, then independently confirmed empirically (rendered
      both rotations to a `QImage` and checked which edge the V-shape's
      single-point vertex landed on: `+90` puts it on the left edge,
      `-90` on the right). Fixed to `-90.0`. `rotated_tinted_svg_pixmap()`
      is a new shared helper in `svg_icons.py` (factored out of
      `SvgIconLabel.set_icon`'s existing rotation logic) used by both
      that label and the new use below.
    - **`CollapsibleSection` (`controls.py`, used by each `ChannelPanel`'s
      Alignment/Light sub-sections) now uses the same SVG chevron instead
      of `QToolButton.setArrowType()`'s native arrow** - visual
      consistency with the block-level collapse buttons, per the user's
      explicit ask. Its `toggle_button` keeps native text+icon layout
      (`Qt.ToolButtonTextBesideIcon`); only the icon source changed, via
      `setIcon(QIcon(rotated_tinted_svg_pixmap(...)))` swapped in
      `_update_chevron_icon()`, called from both `__init__` and
      `_on_clicked()`. Same `-90°`-when-collapsed convention.
    - **`tone_group` i18n key renamed "Color correction"/"Étalonnage" →
      "Light"/"Lumière"** (matching `global_light_subheader`'s existing
      French wording) - this is the label on each `ChannelPanel`'s second
      `CollapsibleSection`, not `LightPanel`'s own title; the two are
      different i18n keys for two different (if now same-named) UI
      elements, both changed for the same reason (the split of Global
      Correction into Light/Color).
    - **Both side panels now share one width range** (`_SIDE_PANEL_MIN_WIDTH`/
      `_SIDE_PANEL_MAX_WIDTH` = 360/420, both new module constants) -
      they used to differ (left 360-420, right 300-360), backwards now
      that any block can be dragged to either side: a block that fit the
      wider left panel could still overflow the narrower right one. This
      is very likely what actually explained the right-panel scrollbar
      persisting across two previous "fix" attempts that only ever
      touched button/margin sizing, never the asymmetric bounds
      themselves - and directly satisfies the user's own new requirement
      that "les 2 panneaux latéraux doivent réagir exactement de la même
      manière, peu importe l'organisation des outils."
    - **Drag-delete is now visually obvious mid-drag, not just after the
      fact.** `BlockDragHandle._start_drag()` connects `QDrag.targetChanged`
      (Qt's own documented hook for updating a drag's visual feedback
      based on the current potential drop target) to swap the ghost
      pixmap's outline red the moment the cursor leaves both
      `BlockReorderZone`s, back to the normal white/blue outline the
      moment it re-enters one - `_is_over_reorder_zone()` walks up from
      whatever widget `targetChanged` reports to check whether any
      ancestor `isinstance(w, BlockReorderZone)` (handles both "target is
      the zone itself" and "target is some non-drop-accepting child
      widget Qt bubbled the drag event up from," which is what
      `BlockReorderZone` already relied on for normal drops to work when
      hovering over a child block). `_scaled_source_pixmap()`/
      `_ghost_pixmap()` were split apart so the expensive grab-and-scale
      only happens once per drag, not on every `targetChanged` firing -
      only the cheap outline-color repaint happens live.
    - **`QApplication.beep()` on drag-delete** (`_on_block_drag_rejected`)
      - the OS's own system alert sound, not a bundled audio asset, so
      nothing new to package or risk going missing in the frozen `.app`.
    - **"The dragged block's preview should disappear the instant it's
      dropped in a delete zone"** - not additional code: this is already
      how native `QDrag` rendering works on every platform (the
      OS-managed drag image is torn down synchronously the moment the
      mouse button releases, regardless of whether the drop was accepted
      or rejected) - nothing in this codebase controls that image's
      teardown timing to begin with, so there was nothing to fix. Worth
      confirming in the real app since it can't be verified headlessly,
      but there's no known reason it wouldn't already hold.
    - Verified headlessly: the fixed `"files"` key via the real handle's
      own `.block_key`, and that a drop with that real key now actually
      moves the block; collapse rotation is `-90` on click; each
      `ChannelPanel`'s `align_box.toggle_button.icon()` is non-null (SVG,
      not native arrow) and `tone_box.toggle_button.text()` reads
      "Light"; both scroll areas report identical min/max width;
      `_ghost_pixmap(danger=True/False)` both render without error;
      `_is_over_reorder_zone()` returns correctly for the zone itself, a
      child block within it, an unrelated widget (canvas), and `None`.
      **Not verified here**: the real drag gesture's live visual feel
      (red outline swap timing, whether it reads clearly) and the beep's
      actual audible/appropriate character - both need the real app.
  - **Eighth pass, 2026-09-04 - the seventh pass's red-outline drag
    feedback didn't actually appear in the real app; a header-layout bug
    caught along the way affected 3 more blocks.**
    - **`QDrag.targetChanged` + live `drag.setPixmap()` (the seventh
      pass's approach) turned out not to work** - the user reported no
      visible change at all. This matches a known Qt/macOS limitation:
      once a native drag session starts, the OS caches its own drag
      image, and `QDrag.setPixmap()` calls after that point aren't
      reliably honored on every platform - `targetChanged` firing and the
      callback running (both already verified headlessly last pass) don't
      guarantee the *visual* actually updates. **Replaced entirely** with
      a fully custom `_DragPreviewOverlay` (`block_header_bar.py`) - a
      frameless, click-through, always-on-top `QWidget` that
      `BlockDragHandle._start_drag()` creates, positions, and repaints
      itself via a 16ms `QTimer` (polling `QCursor.pos()` and
      `QApplication.widgetAt(QCursor.pos())` directly, not relying on any
      QDrag signal). `QDrag` itself now only ever carries a 1×1
      fully-transparent placeholder pixmap - the overlay is the only
      thing actually visible, so its red/white border swap is guaranteed
      to render regardless of platform-specific native drag-image
      caching. This also incidentally fixed a second complaint in the
      same message ("cette image revient à la position initiale avec une
      animation... est-ce possible de ne pas afficher cette animation") -
      that "snap back to origin" animation is the OS animating the
      *native* drag pixmap back on rejection, and since that pixmap is
      now just a transparent 1×1 placeholder, there's nothing visible to
      animate; the overlay itself is just `.close()`d immediately with no
      transition.
    - **Deletion sound now reuses `_play_delete_sound()`** (macOS's
      `Pop.aiff` via `afplay`, already used for deleting a photo) instead
      of `QApplication.beep()`, per "je préfère que tu utilise le même
      son qu'à la suppression d'une photo."
    - **Real bug: `start_block_chrome()` added `header_row.addStretch(1)`
      internally, right after the title**, which silently pushed
      anything a caller added afterward (a "?" scope-info button, in
      `LightPanel`/`ColorPanel`'s case) all the way to the header's right
      edge instead of leaving it next to the title - caught by the user
      ("colle les indicateurs '?' à la droite des titres"). The stretch
      is now the **caller's own responsibility** - `start_block_chrome()`
      no longer adds one at all, so every one of its 7 call sites
      (`ImportPanel`, `CropPanel`, `LightPanel`, `ColorPanel`,
      `independent_channels_group`, `histogram_box`, `scan_panel`) had to
      add their own `header_row.addStretch(1)` at the point that's
      actually correct for that block - immediately after the "?" button
      for Light/Color/the new RGB Channels one, immediately after the
      title for the other 4 (which have nothing that belongs right next
      to it). Verified headlessly by walking each header row's actual
      layout item order and confirming grip → title → "?" (where
      present) → stretch → trailing buttons.
    - **`independent_channels_group` ("RGB Channels") gained the same "?"
      scope-info button** as Light/Color, per the user's explicit ask,
      wired the same way (`show_info_bubble`, same 18×18 rounded style).
    - **New/changed info-bubble text, exact wording given by the user**:
      `channels_scope_info` (new) - "Modifie séparément les images Noir
      et Blanc des canaux RVB. Ces changements s'appliquent avant les
      réglages de lumière et de couleur." (2 small typos in the user's
      own draft silently corrected when writing it down: "séparement" →
      "séparément", "changement" → "changements" for plural agreement).
      `global_scope_info` (Light/Color's existing button) replaced with
      "Dans le cas d'une image trichrome, ces changements s'appliquent
      sur l'image couleur recomposée."
    - **Real bug: the "Scan" block's title was never actually displayed.**
      `self.scan_title_label` was created (via `start_block_chrome(...,
      "menu_tools_scan")`) back in the sixth pass, but no
      `retranslate_ui()` call ever set its text - unlike
      `histogram_title_label`, which got the equivalent line at the same
      time. The label existed in the layout the whole time, just empty.
      One missing line, now added.
    - Verified headlessly: `scan_title_label.text() == "Scan"`; each of
      Light/Color/Channels' header layouts, walked item-by-item, show
      grip → title → "?" → stretch → trailing buttons in that exact
      order; `_DragPreviewOverlay` constructs, resizes to a given
      pixmap, repositions via `move_for_cursor()`, swaps between the
      normal/danger pixmap, and closes cleanly; `_on_block_drag_rejected`
      calls the real `_play_delete_sound` (mocked and asserted called)
      instead of `QApplication.beep()`. **Not verified here** (needs the
      real app): whether the overlay-based drag preview actually renders
      and follows the cursor smoothly during a genuine native drag
      session - this is precisely the class of behavior that silently
      failed last pass despite passing every headless check available,
      so this result should be treated as "logic is sound," not "visual
      confirmed."
  - **Ninth pass, 2026-09-04 - the eighth pass's overlay broke drag-and-
    drop entirely: every block got deleted on drop, regardless of
    target.** Root cause: `_DragPreviewOverlay` was a real top-level
    window (`Qt.WindowStaysOnTopHint`) kept positioned exactly under the
    cursor for the whole drag. OS-level native drag-and-drop hit-testing
    (which `QDrag` relies on to resolve `dragEnterEvent`/`dropEvent`
    against the widget under the cursor) operates at the window-manager
    level, checking which real *window* currently sits topmost at that
    screen position - `Qt.WA_TransparentForMouseEvents` only affects
    ordinary in-app mouse-event routing through Qt's own event system, it
    has no bearing on that separate OS-level mechanism. So the overlay
    itself was very likely what every drop was landing on, from the
    native drag session's point of view - explaining "les outils sont
    supprimés dès qu'ils sont déplacés, peu importe le panneau" exactly:
    with the real `BlockReorderZone` widgets unreachable by native
    hit-testing, *every* drop resolved to `Qt.IgnoreAction`, and
    `_on_block_drag_rejected` fired for all of them, not just genuine
    drops outside both panels.
    - **Reverted outright** rather than attempting a third live-drag-
      visual technique: `_DragPreviewOverlay` deleted; `_start_drag()`
      back to a single static `QDrag.setPixmap()` call (no danger/normal
      variants, no live updates) set once before `exec()`, matching
      exactly the shape verified working through the sixth/seventh
      passes. `_ghost_pixmap()` is a plain method again (no `danger`
      param), `_is_over_reorder_zone()`/`_scaled_source_pixmap()` removed
      (only ever used by the reverted overlay code). Drag-delete itself
      (`drag_rejected` on `Qt.IgnoreAction`, the sound, the status
      message, the Tools-menu sync) is untouched and still correct - only
      the mid-drag red-border visual polish is gone.
    - **Deliberately not re-attempted this pass.** Two different
      techniques for one purely cosmetic detail (a live red/white border
      swap during drag) both caused real regressions - the first was
      silently inert, the second broke core drag-and-drop - and neither
      could be verified without a real interactive session. Restoring
      correct behavior took priority over the visual polish; if the red-
      border cue is wanted again, it needs a technique that doesn't
      involve a second real window competing for OS-level drag
      hit-testing (e.g. `QDrag.setDragCursor(pixmap, action)`, which is
      part of the *same* native drag session Qt already manages rather
      than a separate window - untried here, and its exact interaction
      with `setPixmap()` wasn't confirmed before this pass ran out of
      appetite for another unverified live-drag experiment).
    - Verified headlessly: `BlockDragHandle` no longer has
      `_is_over_reorder_zone`/`_scaled_source_pixmap`; `_ghost_pixmap()`
      takes no arguments and returns a valid pixmap; same-panel reorder
      and cross-panel move via `_on_block_dropped` (the actual drop
      handler, unaffected by any of this - it was always the *native
      hit-testing reaching it* that broke, not the handler itself) still
      work; `drag_rejected` still correctly triggers removal + sound.
      **Not verified here** (needs the real app, and is the whole reason
      this reverted rather than iterating further blind): that a real
      drag now actually reaches `BlockReorderZone` again.
  - **Tenth pass, 2026-09-04 - the user confirmed the ninth pass's revert
    fixed dragging, then asked to drop drag-to-delete entirely**: "cette
    option de supprimer l'outil en drag and drop n'est pas necessaire
    (disponible avec la croix et dans le menu tools), supprime là et
    reviens au comportement de base (changer l'ordre seulement lorsqu'on
    le drag and drop dans une zone active indiqué par le trait bleu)".
    The "Drop-to-remove" feature from the sixth-pass-adjacent entry above
    (and its `drag_rejected` signal from the seventh pass) is now removed
    outright, not just made safer - `BlockDragHandle` no longer emits
    anything on a rejected/cancelled drag, `_on_block_drag_rejected`/
    `status_block_removed` (i18n, both languages) are deleted, and a drop
    outside both `BlockReorderZone`s (Escape included) is a plain no-op -
    the block simply stays where it was, exactly like the drag never
    happened. Removing a block is now, once again, only ever done via its
    own close button or the Tools menu. Verified headlessly: pyflakes
    clean on the 3 touched files; EN/FR i18n parity still holds; a real
    app boot; `BlockDragHandle` has no `drag_rejected` attribute; a
    same-panel reorder via `_on_block_dropped` (the same handler the blue
    insertion-line indicator drives) still works correctly.
- **Layout Presets (Window ▸ Layout Preset), added 2026-09-03.** Named,
  saveable full-layout snapshots - requested by the user in the same pass
  as the block-reorder feature above and the removal of the per-tool move
  actions, specifically so a user could still jump between a small number
  of deliberately different arrangements without the fine-grained
  drag-and-drop alone being the only way to change layout.
  - **`_capture_layout_state()`**/**`_apply_layout_state(data)`**: the one
    place the full set of layout-only fields is listed - panel visibility
    plus, since the 2026-09-04 block-system overhaul above, the 5 block
    fields (`block_side`/`block_visible`/`block_collapsed`/
    `left_block_order`/`right_block_order`). `_apply_layout_state` is just
    a thin wrapper over `_apply_restored_layout(...)` with fields pulled
    from a dict instead of positional args - both
    `_build_restored_items_from_data` (the `.trirgb` path) and Layout
    Preset load go through it now, so the field list only has to be kept
    in sync in one place instead of two.
  - **Storage: QSettings only, not part of `.trirgb`** - presets are a
    personal, cross-session arrangement library (like a keyboard shortcut
    set), not project-file content, so they deliberately don't travel with
    a saved session/`.trirgb` the way `block_side` itself does.
    `self._layout_preset_names: list[str]` (QSettings key
    `layout_preset_names`) is the ordered name list, loaded eagerly in
    `__init__` since `_build_ui()` needs it immediately to populate the
    menu; each preset's actual data is `json.dumps(_capture_layout_state())`
    under its own key, `layout_preset_data_{name}`.
  - **Menu**: `Window ▸ Layout Preset` - **Save Layout as Preset…**
    (`on_save_layout_preset`, a plain `QInputDialog.getText` asking only
    for a name, per the user's explicit "demande juste un nom" - not a
    custom dialog, since this is a simple one-field text prompt with no
    existing app-specific equivalent to reuse, unlike the alert-dialog
    policy which is specifically about warning/error dialogs), then a
    separator, then one submenu per saved preset with 3 actions each:
    **Load**, **Update**, **Delete Preset**. `_save_layout_preset(name)`
    doubles as both "Save" (new name) and "Update" (existing name) - saving
    under a name that already exists just overwrites its data, so Update's
    handler is literally the same call with the existing name, no separate
    code path. `_rebuild_layout_preset_menu()` tears down and rebuilds
    every per-preset submenu (keeping only the Save action + separator) -
    called after every save/update/delete, and from `retranslate_ui()` too
    so a language switch also re-translates the Load/Update/Delete Preset
    labels (they're plain `QAction`s built with `i18n.tr()` at construction
    time, not synced any other way).
  - Verified headlessly: save/load/update/delete all mutating
    `self._layout_preset_names` and the menu structure correctly, a loaded
    preset actually restoring `block_side` (moving a block back across
    panels) and the reordered widget positions that follow from it, the
    preset submenu surviving a simulated language switch with correctly
    re-translated labels, and the Window menu's action list no longer
    containing the old move-to-side actions.
  - **The 4 old tool-switcher toolbar buttons repurposed into built-in
    default-layout quick-switches, 2026-09-04.** Since the full block
    system (drag/collapse/close/Tools-menu) superseded what
    `trichrome_toolbar_btn`/`settings_toolbar_btn`/`crop_toolbar_btn`/
    `scan_toolbar_btn` used to do, they'd been sitting disabled/greyed in
    their toolbar slots (see the "full block system overhaul" entry
    above) pending a follow-up decision. The user's follow-up: re-enable
    them, but as **layout-preset shortcuts**, not tool-visibility
    toggles - each applies one of 4 specific named Layout Presets the
    user had already saved through the regular mechanism above
    (`"Trichrome"`, `"Color Correction"`, `"Crop"`, `"Scan"` - confirmed
    to exist, read-only, from the real QSettings domain
    `com.trichromemaker.TrichromeMaker` before writing any code). The
    bare-letter keyboard shortcuts (T/E/C/S) are unchanged in binding,
    only in what they now do.
    - **`_BUILT_IN_LAYOUT_PRESETS`** (module-level, `main_window.py`) is
      the one ordered list of `(preset name, Window-menu i18n key, bare
      shortcut letter)` tuples - `_BUILT_IN_LAYOUT_PRESET_NAMES` is the
      derived name-only tuple used everywhere a plain membership check is
      needed (guards below).
    - **Single exclusive group, not two independent pairs.** The old
      `left_tool_group`/`right_tool_group` (2 separate `QButtonGroup`s,
      each exclusive within its own pair) are gone, replaced by one
      `self.default_layout_group` holding all 4 buttons - per the user's
      explicit "un seul layout peut être actif à la fois (icone en blanc
      et les autres grisée)", only one of the 4 reads as active
      (full-color) at any time now, not one-per-side. Buttons are
      re-enabled (`setEnabled(False)` calls removed); only
      `trichrome_toolbar_btn` starts checked (was previously both
      `trichrome_toolbar_btn` *and* `settings_toolbar_btn`, back when
      they were 2 independent exclusive pairs - keeping both `True` now
      would conflict with a single exclusive group).
    - **`_activate_default_layout(name)`** is the one entry point all 3
      trigger paths (a toolbar button's `clicked`, a bare keyboard
      shortcut, a Window-menu click) funnel through - syncs the matching
      button's checked state via `self._default_layout_buttons[name]`
      (built once, alongside the buttons, in `_build_ui`) and then always
      calls `_load_layout_preset(name)` regardless of whether the checked
      state actually changed. **Deliberately wired via each button's
      `clicked` signal, not `toggled`** - `clicked` fires on every real
      click including a re-click of the already-checked button (an
      exclusive-group radio button doesn't uncheck itself on a second
      click, so `toggled` wouldn't fire again), which is exactly the
      wanted behavior: re-pressing "T" after having dragged blocks around
      resets back to the actual Trichrome layout instead of being a
      no-op. Keyboard shortcuts call `_activate_default_layout(name)`
      directly (replacing the old bare `.setChecked(True)` calls in
      `keyPressEvent`) rather than synthesizing a `.click()`, for the
      same reload-even-if-already-checked reason.
    - **Built-in presets are Load-only - not Update/Delete-able, and
      listed directly in the Window menu, not nested in the Layout Preset
      submenu**, both per explicit user request. `_rebuild_layout_preset_menu()`
      now skips any name in `_BUILT_IN_LAYOUT_PRESET_NAMES` when building
      the Layout Preset submenu's per-preset Load/Update/Delete entries -
      they simply never appear there. Instead, `self.builtin_layout_actions`
      (built in `_build_ui`, right after Reset Layout, its own separator
      on each side) holds one plain non-checkable `QAction` per built-in
      preset, translated in `retranslate_ui()` with the same `"\t<letter>"`
      shortcut-hint suffix convention every other Window-menu item already
      uses, triggering `_activate_default_layout` exactly like the
      toolbar buttons.
    - **Guard against silently overwriting a built-in via "Save Layout as
      Preset…".** The Layout Preset submenu no longer offers Update/Delete
      for a built-in name, but the free-text "Save as Preset…" dialog
      could still type one of the 4 reserved names verbatim -
      `on_save_layout_preset()` now checks the entered name against
      `_BUILT_IN_LAYOUT_PRESET_NAMES` first and shows `show_alert(...)`
      (`layout_preset_builtin_name_title`/`_text`, the text taking the
      typed name via `{name}`) instead of saving, rather than silently
      clobbering the built-in's data. `_delete_layout_preset()` also
      gained the same guard as defense-in-depth, even though the UI can
      no longer reach it for a built-in name.
    - **Tooltip wording**: `settings_toolbar_tooltip` ("Global Correction
      (E)" / "Correction Globale (E)") renamed to "Color Correction (E)" /
      "Correction Couleur (E)" to match the preset name it now actually
      applies - the other 3 tooltips already matched their preset names
      exactly, so only this one needed changing.
    - **Custom presets are untouched** - `on_save_layout_preset`/
      `_save_layout_preset`/`_load_layout_preset`/`_delete_layout_preset`
      and the Layout Preset submenu's Load/Update/Delete-per-preset
      pattern all still work exactly as before for any name that isn't
      one of the 4 reserved ones, per the user's explicit "garde la
      possibilité de créer et modifier des layouts personnalisés."
    - Verified headlessly: all 4 buttons enabled and in one 4-member
      exclusive group; saving presets under `"Trichrome"`/`"Color
      Correction"` plus a custom `"MyCustom"` name, then confirming the
      Layout Preset submenu lists only `MyCustom`; `builtin_layout_actions`
      text/shortcut-hint correctness in both EN and FR;
      `_activate_default_layout("Color Correction")` correctly flipping
      the exclusive checked state (trichrome→unchecked, settings→checked)
      and actually applying that preset's captured `block_visible` data;
      re-clicking an already-checked button still re-triggers a reload;
      the builtin-name-collision alert firing (mocked) instead of
      overwriting; `_delete_layout_preset("Trichrome")` being a correct
      no-op; and (follow-up check, same day) a real bare-letter "C"
      keypress driven through an actual `QKeyEvent`/`keyPressEvent`
      call, confirmed to reach `_activate_default_layout` and check the
      right button. **Not verified here**: the toolbar buttons' real
      dim/full-color visual at each checked state - needs the real app.
  - **Second pass, 2026-09-04, after the user tried it for real - 3 more
    changes**, all in `main_window.py`/`i18n.py`:
    1. **Reset Layout moved to the very bottom of the Window menu**,
       below the Layout Preset submenu (was previously above the 4
       built-in layout entries, near the top) - the construction order in
       `_build_ui` was rearranged so `reset_layout_action` is built and
       added last, after `layout_preset_menu`/`_rebuild_layout_preset_menu()`,
       with its own separator; `retranslate_ui()`'s corresponding
       `setText()` call moved to match (order there doesn't affect the
       menu, but kept it next to the construction order for readability).
    2. **Built-in layout entries now read "Layout - Trichrome"/"Layout -
       Color Correction"/"Layout - Crop"/"Layout - Scan"** (French:
       "Disposition - " - reusing this codebase's already-established
       "layout" → "disposition" translation, the same word
       `menu_window_reset_layout`/`menu_window_layout_preset` already
       use, rather than leaving "Layout" untranslated as a loanword) - a
       new `menu_window_layout_prefix` i18n key, prepended in
       `retranslate_ui()` ahead of each entry's existing label key.
    3. **Display name decoupled from the actual preset loaded.** The user
       found the layouts saved under the reserved names themselves
       ("Trichrome"/"Color Correction"/"Crop"/"Scan", from the first
       pass) didn't match what they'd actually set up, and recreated
       correct versions as ordinary custom presets named
       `"NewTrichrome"`/`"NewColorCorrection"`/`"NewCrop"`/`"NewScan"`.
       Rather than asking the user to keep re-saving under the exact
       reserved names (which would then be un-updatable per the first
       pass's own guard - a contradiction with "garde la possibilité de
       créer et modifier des layouts personnalisés"), `_BUILT_IN_LAYOUT_PRESETS`
       gained a 4th tuple element - the *source* preset name each display
       slot actually loads - and a derived `_BUILT_IN_LAYOUT_SOURCE`
       dict (display name → source name).
       `_activate_default_layout(name)` now resolves through it before
       calling `_load_layout_preset()`: `name` (e.g. `"Color Correction"`,
       the fixed identifier used everywhere else - button lookup, Window
       menu action, keyboard shortcut) is never itself a real saved
       preset any more; what actually gets loaded is `NewColorCorrection`.
       The reserved display names stay reserved (`_BUILT_IN_LAYOUT_PRESET_NAMES`,
       still guards `on_save_layout_preset`/skips the Layout Preset
       submenu, unchanged), but the 4 `New*` presets are **ordinary,
       fully editable custom presets** - they show up normally in the
       Layout Preset submenu with working Load/Update/Delete, so editing
       `NewCrop` there and re-pressing "C" picks up the change immediately,
       which is exactly the live-linking behavior the user's "modifier des
       layouts personnalisés" ask implies.
    - Verified headlessly: Window menu's action list ends with
      `reset_layout_action` as the literal last entry; the 4 built-in
      entries render as "Layout - Trichrome\tT" etc. in EN and
      "Disposition - Trichromie\tT" etc. in FR; saving `NewTrichrome`/
      `NewColorCorrection`/`NewCrop`/`NewScan` as regular presets makes
      them appear in the Layout Preset submenu (the old reserved-name
      entries `Trichrome`/`Color Correction`/`Crop`/`Scan` stay hidden,
      now orphaned data from the first pass, harmless); activating
      `"Color Correction"` and `"Crop"` each actually applies its
      *source* preset's distinct `block_visible` data (not the reserved
      name's own, confirming the decoupling actually works end-to-end,
      not just that the mapping dict is correct).
- **Menu bar reworked to match (2026-09-02)**, same pass as the toolbar
  reshuffle above:
  - File menu's Import item reworded "Import…" → **"Import Images…"**
    (`menu_batch`) - same wording change applied to the toolbar's own
    `import_toolbar_tooltip` for consistency, since they're the same action.
  - **Language menu relocated into the native macOS Application menu**
    (the one always named after the app, leftmost in the bar) instead of
    staying its own top-level entry - `self.language_menu.menuAction()
    .setMenuRole(QAction.ApplicationSpecificRole)`, the same `menuRole`
    mechanism `quit_action` already used (`QAction.QuitRole`) to get pulled
    into that same native menu, just applied to a whole submenu's own
    `menuAction()` instead of one flat action - a standard, documented Qt/
    Cocoa pattern for this. **Only verifiable by running the real built
    `.app`** - the native Cocoa menu merge happens entirely outside Qt's own
    widget tree, so `self.menuBar().actions()` still lists Language as an
    ordinary top-level entry even after this change when inspected
    headlessly (confirmed: the role IS set correctly, `.text()`/child
    actions are all still intact - what can't be confirmed here is whether
    it actually *lands* inside the Cocoa Application menu on a real launch).
  - **New "Tools" menu** (`self.tools_menu`, positioned where Language used
    to sit in the bar), listing the same 4 tool-switcher buttons as the top
    toolbar's center cluster: Trichrome, Global Correction, Crop, Scan -
    `tools_trichrome_action`/`tools_global_correction_action`/
    `tools_crop_action`/`tools_scan_action`, each a checkable `QAction`
    with a `"\t<letter>"` display-hint suffix (T/E/C/S) added in
    `retranslate_ui()`, same convention as the Window menu's `\tI`/`\tO`/
    `\tP` hints. **Deliberately 4 independent checkable actions, not one
    `QActionGroup`** - Trichrome/Scan and Global Correction/Crop are 2
    separate exclusive pairs (left panel vs. right panel; see the toolbar
    section above), and a single `QActionGroup` across all 4 would wrongly
    force them into one 4-way exclusive choice. Each action is instead
    synced individually to its own toolbar button (`toggled ->
    action.setChecked`), and the toolbar buttons' own real
    `QButtonGroup` exclusivity is what correctly propagates the "uncheck
    the other one in this pair" behavior into the menu.
    - **Real bug caught and fixed by testing this headlessly**: the
      straightforward `triggered.connect(lambda checked:
      button.setChecked(True))` wiring (forcing the *button* checked
      regardless of the bool Qt passes, matching radio-button semantics)
      left the *menu checkmark itself* stuck unchecked after re-clicking an
      already-selected tool. Root cause: a checkable `QAction` not in a
      `QActionGroup` flips its own checked state internally as part of
      `trigger()`, *before* emitting `triggered` - so clicking an
      already-checked item flips it to unchecked first; the handler then
      calls `button.setChecked(True)`, but the button was *already*
      checked, so that's a no-op that fires no `toggled` signal, and
      nothing ever re-syncs the action back to checked. Fixed with a new
      `_select_tool_action(action, button)` helper that forces the action
      itself back to checked *and* the button, rather than trusting the
      button's own `toggled` echo to fix the action up - verified
      headlessly by re-triggering an already-checked action and confirming
      it stays checked (both for Trichrome/Scan and for Global
      Correction/Crop, the two independent pairs).
- **`SliderSpin` (`widgets/controls.py`), the app's one slider primitive**
  (used by `GlobalPanel`, every `ChannelPanel`'s alignment and tone
  sections, and `CropPanel`'s Straighten) - redesigned 2026-09-01 around one
  idea: **the slider's default always sits at its own exact midpoint step**,
  computed via a piecewise map (`_value_to_fraction`/`_fraction_to_value`,
  in `[-1, 1]` with `0` at the default) that stretches `[minimum, default)`
  and `(default, maximum]` to fill their own half of the track
  independently - so this holds even when the default isn't the arithmetic
  midpoint of the range (gamma: 0.1..4.0, default 1.0; contrast/saturation:
  0..3.0, default 1.0). `_ResettableSlider.paintEvent` then draws a fill
  from that fixed center point out to the handle (replacing Qt's native
  sub-page, which always fills from the left edge - the actual bug this
  fixes: a neutral value used to look "half full" the moment its default
  wasn't the minimum) plus a small tick marking the center, so every
  slider visually reads "which side of default, how far" at a glance.
  - **`percent_mode=True`** additionally remaps the *displayed/typed*
    number the same way, to -100..100 with `0` at the default - the
    Lightroom convention, used for every color-correction slider (all of
    `GlobalPanel`'s and each `ChannelPanel.tone_box`'s sliders) since their
    real unit (a multiplier, an exponent, an additive tonal shift) isn't
    independently meaningful on its own. Left `False` (the default) for any
    slider whose unit already means something by itself - `ChannelPanel`'s
    alignment sliders (`dx`/`dy` in pixels, `scale` a zoom ratio,
    `rotation` in degrees) and `CropPanel`'s Straighten (degrees) - turning
    a real angle into an abstract percentage would be a regression, not a
    cleanup. The stored/exported value is **always the real unit** either
    way - `value()`/`set_value()`/`value_changed` never speak percent, only
    `ClickToEditValue`'s own displayed number does - so nothing about
    persistence, undo, or the image-processing math in `imaging.py`
    changed; this was a presentation-layer-only refactor.
  - **`ClickToEditValue`** (also in `controls.py`) replaces the old
    `QDoubleSpinBox` (with its up/down-arrow box) with a bare right-aligned
    number - click it to swap in a line edit (focused, selected-all) until
    Enter/focus-out commits or Escape cancels. `signed=True` (set whenever
    `percent_mode` is on, or a real-mode slider's own default is exactly 0)
    prefixes a positive value with `+` and shows a bare `0` at exactly
    zero, echoing the slider's own center-relative fill in the number
    itself. Tracks its own `_editing` bool rather than trusting
    `QWidget.isVisible()`/`isHidden()` to guard against `editingFinished`
    firing twice (once for Enter, again on the subsequent focus-out) -
    `isVisible()` depends on the *whole* ancestor chain being shown, not
    just this widget's own hidden state, so it's unreliable as a re-entrancy
    guard in general (caught by a headless test here before it could reach
    a real user).
  - The old opt-in `set_show_center_mark()` flag is gone - centering is now
    unconditional and automatic for every slider, since every slider's
    default now always lands at the midpoint by construction.
  - **Handle (2026-09-01):** fully custom-painted now too, not native-then-
    overlay - `_ResettableSlider.paintEvent` no longer calls
    `super().paintEvent()` at all, and draws groove → fill → center tick →
    handle itself, in that order, every time. The QSS on `self.slider` only
    sets the handle's hit-testing box (`width`/`height`/`margin`,
    `background: transparent`) so `QStyle`/`QAbstractSlider`'s own mouse
    handling still computes drag geometry from it; nothing native actually
    renders. Painting the handle last is what guarantees it's fully opaque
    and never shows the groove/fill through it - the previous native-
    handle-then-overlay order could let the accent fill's antialiased edge
    peek past the native handle's own edge, which is what prompted this.
    Smaller now (`HANDLE_RADIUS = 5.5`, an 11px circle, down from 13px) and
    Lightroom-style stateful: a hollow ring (`HANDLE_BORDER = 2.0` px,
    interior painted in the live `QPalette.Window` color so it stays opaque
    without hardcoding a background) at rest, filling to a solid circle
    while `self.isSliderDown()` - `mousePressEvent`/`mouseReleaseEvent`
    both call `self.update()` after `super()` purely to repaint for that
    state change, they don't affect interaction otherwise.
- **`GlobalPanel` (`widgets/global_panel.py`), renamed and split
  (2026-09-01):** title is now "Global Correction" (`global_group_title`;
  was "Global color correction" / "Étalonnage global" - every other
  user-facing mention of the old name, the toolbar tooltip and both
  Quickstart/Shortcuts help texts, was updated to match). Its sliders are
  now grouped under two plain sub-headers (`_make_subheader()`, a small
  bold muted `QLabel` - not a collapsible section like `ChannelPanel`'s,
  since this is the primary always-visible panel, not per-channel detail
  meant to stay tucked away) - **Light**: Brightness, Contrast, Highlights,
  Shadows, Whites, Blacks, Gamma (unchanged order); **Color**: Temperature,
  Tint, Saturation, in that specific order (was Saturation, Temperature,
  Tint) - `self._light_sliders`/`self._color_sliders` split what used to be
  one `self._sliders` tuple, concatenated back into `self._sliders` for the
  existing `block_signals_all`/`set_sliders_enabled` loops so those didn't
  need to change. `invert_checkbox` stays where it was, above both
  subheaders - it's a toggle, not a slider, and doesn't belong to either
  group.
- **White balance eyedropper (added 2026-09-01, header rows reworked same
  day):** `pick_white_balance_btn` (`SvgCheckableToolButton`,
  `Color Correction/eyedropper.svg`) and `reset_white_balance_btn` (plain
  `SvgToolButton`, `Color Correction/reset_white_balance.svg`) sit on the
  **same row as the "Color" subheader text itself**, right-aligned next to
  it (`color_header_row`) - not on a separate row below it as first built.
  `light_header_row` mirrors this shape for **Light**: just one button,
  `reset_light_btn` (`Color Correction/reset_brightness.svg`), also
  right-aligned next to the "Light" text. Both reset buttons are at the
  shared `HEADER_COMPANION_BTN_SIZE`/`ICON_SIZE`. Checking the eyedropper
  button calls `MainWindow.on_pick_white_balance_toggled` →
  `CanvasWidget.set_wb_pick_enabled` → `_ImageLabel.set_wb_pick_enabled`,
  which swaps the canvas cursor for a white-tinted `eyedropper.svg`
  (`tinted_svg_pixmap`, hotspot near the glyph's own sampling tip, not its
  center) and arms `_ImageLabel.wb_pick_enabled`, checked first in
  `mousePressEvent` (ahead of crop/align) so an armed pick always wins over
  whatever other canvas mode happens to be active. A click emits
  `white_balance_pick_requested(u, v)` (normalized canvas position, the
  same convention as crop's normalized rect) straight to
  `MainWindow.on_white_balance_picked`, which is single-shot - it disarms
  the tool immediately (button + cursor) before doing anything else,
  Lightroom-style, rather than staying armed for repeated picks.
  - **Why a pixel needs recomposing, not just reading off the displayed
    preview:** `apply_white_balance` runs *before* saturation but *after*
    every other global adjustment (black/white/gamma/brightness/contrast/
    shadows/highlights) - see `apply_global_correction` in `imaging.py`.
    Solving from the pixel as *already displayed* (which has the *old*
    temperature/tint baked in) would double-count that old correction,
    since the new temperature/tint fully replaces the old one rather than
    stacking on top of it. `imaging.compose_rgb_from_channels` (per-channel
    warp/tone/stack, factored out of `compose_trichrome`) plus
    `imaging.compose_pre_white_balance_rgb` (that, plus the global tone
    curve stage only) reconstruct exactly the pre-white-balance pixel the
    real pipeline would produce; `on_white_balance_picked` samples `(u, v)`
    from that array - after also applying straighten/mirror/crop the same
    way `recompute_preview` does, since `(u, v)` are normalized against
    whatever's actually on screen, not the raw unstraightened frame.
    `compose_trichrome` itself is just `compose_rgb_from_channels` +
    `apply_global_correction` now (pure extraction, output unchanged).
  - **The solve** (`imaging.solve_white_balance(r, g, b)`) inverts
    `apply_white_balance`'s gain model algebraically (Cramer's rule on 2
    linear equations, `R*r_gain == G*g_gain == B*b_gain`) rather than
    iterating/searching - verified by a numeric round-trip test (apply a
    known temperature/tint to a neutral pixel, solve, reapply the solved
    values to the shifted pixel, confirm R≈G≈B again to float precision)
    for realistic magnitudes; only saturates against the ±100 clamp for a
    synthetic worst-case input whose swing is beyond what the linear model
    can invert exactly (two independent ±90 shifts compounded) - real
    photos sampled at a real gray/white patch stay well inside the accurate
    range. Returns `None` (pick left silently rejected, status bar message)
    for a black/near-black or otherwise degenerate sample.
  - **Scope/lifecycle**: picking is disarmed (button unchecked, cursor/canvas
    flag cleared) whenever the Crop tool is opened (`_on_crop_tool_toggled`)
    or the active photo changes (`activate_batch_item`) - both mirror how
    `align_enabled` is already reset in those same two places, so the
    eyedropper never stays silently armed against a context it no longer
    applies to.
  - **`on_reset_white_balance` resets all 3 Color sliders** (temperature,
    tint, *and* saturation - broadened from just the white-balance pair,
    since the button now sits at the Color subheader's own level, not
    tucked specifically next to Temperature/Tint) - checked via
    `GlobalCorrection.has_color_correction()`. `on_reset_light` is the
    matching Light-only reset, added the same day, via the new
    `GlobalCorrection.has_light_correction()` - `has_correction()` is now
    just `has_light_correction() or has_color_correction()`.
- **Histogram pixel pick (added 2026-09-02):** `HistogramPanel.pick_button`
  (`widgets/histogram_widget.py`, `SvgCheckableToolButton`, same
  `Color Correction/eyedropper.svg` as the white balance tool above) sits
  immediately left of the histogram's own Reset button. Unlike white
  balance's single-shot click-to-apply, this one is a **live, read-only
  readout**: while checked, hovering the preview draws a dashed vertical
  line per channel (`HistogramWidget.set_marker(r, g, b)`, Y derived with
  the same luma weights `set_image` uses so it lines up with the Y curve)
  at that pixel's tone on the chart, tracking the cursor continuously
  rather than sampling once. Nothing about the image or session changes -
  it's purely a display aid, so (unlike the white balance eyedropper) it
  does **not** disarm itself on Crop-tool toggle or photo switch; it stays
  armed until the user unchecks it.
  - **Hover plumbing**: `_ImageLabel` (`widgets/canvas_widget.py`) gained
    `histogram_pick_enabled`, `histogram_pixel_hovered(u, v)` (normalized,
    emitted from `mouseMoveEvent` on every move while armed) and
    `histogram_pixel_left()` (emitted on `leaveEvent`, and also whenever
    `set_histogram_pick_enabled(False)` disarms the tool directly - so the
    marker clears both when the mouse leaves the canvas *and* when the
    button itself is unchecked while the cursor is still sitting over the
    image). `setMouseTracking()` is toggled on/off together with the flag,
    since move events without a button held only arrive with tracking on -
    every other canvas gesture here only needs move events *during* a
    drag, which Qt already delivers regardless of tracking, so this is the
    one gesture that needed it turned on at all.
  - **Cursor**: `set_wb_pick_enabled`/`set_align_enabled`'s previous
    ad hoc cursor-swap logic was refactored into one shared
    `_refresh_cursor()` (eyedropper cursor if either `wb_pick_enabled` or
    `histogram_pick_enabled`, else open-hand if `align_enabled`, else the
    arrow) so the two eyedropper-style tools can't stomp on each other's
    cursor state - a real risk the old per-setter `if not
    self.wb_pick_enabled: ...` guard didn't account for once a second pick
    tool existed.
  - **Sampling**: `MainWindow._last_preview_rgb_u8` caches the exact array
    last handed to `canvas.set_image_rgb`/`set_image_gray` *and*
    `histogram.set_image` (both branches of `recompute_preview` - normal
    and Solo - now stash it, and clear it to `None` alongside the existing
    `canvas.clear_image()`/`histogram.clear()` calls when there's no
    image). `on_histogram_pixel_hovered` indexes straight into that cached
    array at the hovered normalized position - no recomposition, so it's
    exactly the same pixel the user sees on screen and in the histogram's
    own curves, straighten/crop included. A minor accepted staleness: if
    the image changes (slider drag, photo switch) while the cursor sits
    still, the marker doesn't refresh until the next actual mouse move -
    consistent with how a real eyedropper readout behaves elsewhere.
  - **Panel wiring** mirrors `GlobalPanel.pick_white_balance_btn` exactly:
    `HistogramPanel.pick_toggled` re-emits the button's own `toggled` (so
    MainWindow doesn't need to reach into the button directly), and
    `_on_pick_toggled` clears the chart's marker locally the moment the
    button is unchecked, without waiting on the canvas round-trip.
  - **Auto-disarm on click-elsewhere (added same day, 2026-09-02):** since
    this tool has no click semantics of its own (it's pure hover), leaving
    it armed indefinitely reads as a mode the user has to remember to turn
    off - so it now disarms itself the moment you click anything other
    than the preview canvas. `MainWindow.eventFilter` is installed
    app-wide (`QApplication.instance().installEventFilter(self)`, right
    after `_connect_signals()` in `__init__`; removed again in
    `closeEvent`) rather than only on this window, specifically so a click
    in another window - the Export dialog, the Batch window - disarms it
    too, not just clicks inside the main window. On `MouseButtonPress`,
    while `histogram.pick_button.isChecked()`, if the event's target
    widget is neither `self.canvas` nor a descendant of it
    (`self.canvas.isAncestorOf(obj)` - covers the scroll area's viewport
    and `image_label` both), the filter unchecks the button directly.
    **One deliberate exception: a click on the pick button itself is
    skipped by the filter.** Without it, the filter's forced
    `setChecked(False)` fires on the button's own `MouseButtonPress`
    (event filters run before the target widget's own handling), and then
    the same click's *release* would toggle the button back on via
    `QAbstractButton`'s normal checkable behavior - net effect, clicking
    the button to turn it off wouldn't work, it'd just flicker. The button
    already disarms itself correctly when clicked directly; the filter
    only needs to handle every other click. Verified headlessly: clicking
    inside the canvas (both the image label and the scroll area's
    viewport) leaves it armed, clicking the pick button itself leaves the
    filter's own logic a no-op, and clicking any other widget disarms it.
- **Reset buttons grey out when there's nothing to reset (added
  2026-09-01):** every Reset-shaped button in the app is disabled whenever
  its own scope is already at default, computed fresh in
  `MainWindow.recompute_preview()` (called on every edit) rather than only
  on load/undo, so the greyed state tracks live slider drags too:
  `global_panel.reset_button` (`has_correction()`, pre-existing),
  `reset_light_btn`/`reset_white_balance_btn` (the two new ones above),
  `reset_all_alignment_button`/`reset_all_color_button` (pre-existing, any
  channel), each `ChannelPanel`'s own per-channel `reset_align_button`/
  `reset_tone_button` (new - gates on that one layer's own
  `has_alignment_correction()`/`has_tone_correction()`, previously
  unwired), and `crop_panel.reset_button` (new - `CropSettings.has_crop()`,
  previously defined but never actually called anywhere; broadened at the
  same time to also check `aspect_ratio`/`aspect_portrait`/custom ratio,
  not just the rect/straighten/mirror fields it originally covered, since
  those are exactly what the Crop panel's own Reset button also clears).
- **`GlobalPanel` header row, reworked twice on 2026-09-02 - final shape:**
  `title_label`, the **"?" scope info button** (`scope_info_button` →
  `global_scope_info`, explaining "this panel applies to the whole image")
  right after it, a stretch, then `invert_button`, then `reset_button`.
  The header previously also had a warning-glyph "info" button next to
  Reset (`_ChannelCorrectionWarningButton`/`reset_scope_info_button`,
  lighting up white once any independent channel had its own color
  correction, as a hint that Reset here wouldn't touch those) - that one
  is now removed outright, along with its `global_reset_scope_info` i18n
  text and `MainWindow.recompute_preview()`'s
  `set_channels_have_correction(...)` call that fed it (dead code once the
  button was gone). **Do not confuse the two "?"/info-shaped buttons that
  used to live in this header** - an earlier pass removed the *wrong* one
  (the scope info "?") when asked to remove "the info button", then had to
  restore it once the user clarified they meant the warning-glyph one
  next to Reset; the "?" button is intentionally still here.
  Negative/invert lives in the header row itself as `invert_button`, an
  icon-only `SvgCheckableToolButton` (`Color Correction/invert_colors.svg`,
  dimmed while off, full color while on - the same pattern the top
  toolbar's tool switcher already used, not a one-off) at the same
  `HEADER_RESET_BTN_SIZE`/`ICON_SIZE` as `reset_button` right next to it -
  it used to be a separate `QCheckBox` with visible text ("Negative
  (invert scan)") on its own row below the header; that text is gone too,
  folded into `invert_checkbox_tooltip` instead since there's no label to
  read anymore. Reasoning: Negative is significant enough in trichromy
  (wrong polarity ruins the whole composite, not one slider's worth of
  correction) to live in the header next to Reset rather than buried below
  it - this was raised as an open question and the user picked "move it
  into the header" as the answer, so treat this as settled placement, not
  still up for debate. `reset_button`'s tooltip is now "Reset Global
  Correction" (`global_reset_tooltip`) instead of "Reset global color
  correction" - matches the panel's own title (`global_group_title`) more
  literally. Header row, final left-to-right order: title, "?", *(stretch)*,
  Negative, Reset.

## Roadmap (v0.4 log, shipped as v0.4.1 / v0.4.2 / v0.4.3)

Rough order of work the user laid out for v0.4, all done - kept as a log of
what changed and why, not an active punch list:

1. ✅ Update Help menu content (`show_quickstart_dialog`/`show_shortcuts_dialog`,
   `help_quickstart_content`/`help_shortcuts_content` in `i18n.py`) for
   everything shipped since it was last written: the session system, New
   Session, the filmstrip right-click menu (Reset All/Duplicate), and the
   split reset buttons. Done 2026-08-31.
2. ✅ Audited i18n terms/translations across `trichrome/i18n.py` - EN/FR key
   sets now match exactly (verified by diffing both blocks) and 4 dead keys
   with zero references anywhere (`batch_output_group`, `batch_status_idle`,
   `dialog_export_title`, `dialog_auto_align_failed` - note the very similar
   but actually-used `dialog_auto_align_failed_channels` survived) were
   removed. Done 2026-08-31.
3. ✅ Reorganized the shortcuts-reference dialog into "General" (app/session/
   window-level), "Navigation" (renamed from "Filmstrip" - the filmstrip
   itself keeps that name in the Quickstart guide, only this heading
   changed), "Preview" (active-channel + view controls merged into one
   section), and "Sliders". The "active channel" concept moved out of a
   static paragraph in the shortcuts text into a live **`?` info button**
   next to each channel panel's **Active** checkbox
   (`ChannelPanel.active_info_button` in `widgets/channel_panel.py`,
   `i18n.tr("active_layer_info")`) - same `show_info_bubble` pattern as
   `import_panel.py`'s `lock_info_button`. Done 2026-08-31.
4. ✅ Bumped `CFBundleShortVersionString` to 0.4.0 in `trichrome.spec` and
   built `dist/Trichr-o-matic.app` via `./build_mac.sh`. Done 2026-08-31;
   bumped again to 0.4.1 on 2026-09-01 after a follow-up bug/polish pass.
5. ✅ Sidebar layout polish: "Current Picture" title removed from
   `ImportPanel`; "Independent Channels" and "Global Color Correction"
   titles moved from the native `QGroupBox` title into a `title_label`
   inside the block (top-left), with their reset button(s) moved onto that
   same header row, right-aligned, and enlarged 120% (34×30/icon 20 →
   41×36/icon 24) - except the channel-correction warning glyph next to
   Global Color Correction's Reset, which stays at the original smaller
   size on purpose. Histogram and Global Color Correction were split into
   two separate blocks (`histogram_box` / `GlobalPanel`, both children of a
   new `right_container` in `_build_ui`) stacked in their old order; the
   histogram box has no title. `right_scroll` got
   `setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)` so content is
   never wider than the column. `SliderSpin`'s groove/handle were also
   thinned down (`widgets/controls.py`). Done 2026-09-01.
6. ✅ Tool switcher: landed as two checkable buttons in the **top toolbar**
   (centered, between the spacer widgets) rather than at the bottom of the
   right panel as first sketched - `settings_toolbar_btn`
   (`settings_sliders.svg`) and `crop_toolbar_btn` (`crop.svg`), grouped in
   a `QButtonGroup` (`right_tool_group`) for mutual exclusivity, shortcuts
   `E`/`C` (bare, no modifier - see `keyPressEvent`). Toggling shows/hides
   `global_panel`/`crop_panel` in `right_container`; the histogram box is
   unaffected either way. The inactive button must stay clickable (so you
   can switch to it), so dimming uses a new `SvgCheckableToolButton`
   (`widgets/svg_icons.py`) that tints via `isChecked()`, not
   `setEnabled(False)`. Done 2026-09-01.
7. A future **Scan tool** now has a stated direction (a negative-scanning
   tool with a trichromy mode, targeted at v0.5.0) - see its own section
   below (`## Negative scan tool (planned for v0.5.0)`) for what's actually
   decided vs. still open. Still don't start writing its feature code
   without a fuller functional spec than exists today (see that section).

Everything shipped in v0.4.2 and v0.4.3 (white balance eyedropper, missing/
moved source file recovery + relink, reset-button graying app-wide, the
custom `AlertDialog` convention, the Global Correction header reshuffle,
this changelog system) is logged in `CHANGELOG_EN.md`/`CHANGELOG_FR.md`
instead of being repeated here - the numbered list above is frozen as the
original v0.4 punch list, not still being appended to. See
`## v0.4.4 punch list (planned)` and `## Negative scan tool (planned for
v0.5.0)` below for what's next.

The Crop tool itself outgrew a single roadmap line - see its own section
below, which is **not** a closed checklist: the user has said its behavior
and display should keep improving, so treat it as a living area rather than
"done."

## v0.4.4 punch list (all items shipped and built as v0.4.4, 2026-09-02)

Laid out by the user right after v0.4.3 as "just minor bug fixes and
layout" for the next version - all 5 items below are done, and the
version was bumped/built as v0.4.4 the same day:

1. ✅ Fixed the Harris Shutter Effect checkbox's behavior - see the
   "Harris Shutter becomes per-channel state" entry in `## Harris Shutter
   Effect` below for the full writeup (root cause, fix, and the matching
   multi-select-apply behavior added for both Harris Shutter and Negative
   in the same pass).
2. ✅ Missing-files relink window - the 2026-09-02 pass (hover tooltip with
   the original path, per-row "Relink..." to pick an exact replacement
   file) had a real bug: the row-action button was wrongly hardcoded back
   to disabled after every successful relink, even with rows left, making
   the last unresolved row unreachable (see the `AlertDialog`/"Per-row
   tooltip + row action" entry above) - fixed by re-deriving its enabled
   state from the table's actual selection instead. User confirmed fixed.
   Still an area that may see further requests, just not currently
   tracked as open work.
3. ✅ Add a "Window" menu to the menu bar. `self.window_menu`, built in
   `_build_ui()` right after the Language menu (before Help) -
   `window_close_action` ("Close Window", display-only `\t⌘W` hint - no
   real `QAction.setShortcut()`, since Cmd+W is already handled per-window
   by the existing local `QShortcut(QKeySequence.Close, ...)` on each
   secondary window; a second menu-bar-level binding of the same key risks
   Qt shortcut ambiguity between the two. Its handler,
   `_close_active_window()`, calls `.close()` on `QApplication.activeWindow()`
   whenever that's not the main window itself - same "not the main window"
   policy, reachable by clicking the menu item as well as the existing
   per-window Cmd+W), plus three checkable actions mirroring the existing
   toolbar toggle buttons - `window_left_panel_action`/`_right_panel_action`/
   `_thumbnails_action`, bidirectionally synced with
   `left_panel_toggle_btn`/`right_panel_toggle_btn`/`carousel_toggle_btn`
   (`toggled` → `action.setChecked` one way, `action.triggered` → `btn.setChecked`
   the other - **the `triggered` direction must go through an explicit
   `lambda checked: btn.setChecked(checked)`, not a bare bound-method
   reference** - confirmed empirically that PySide6 doesn't reliably pass
   the checked bool through a raw `QAction.triggered.connect(some_widget.setChecked)`
   connection, raising `TypeError: takes exactly one argument (0 given)`
   on both `.trigger()` and the real `activate(QAction.Trigger)` path a
   menu click uses; the reverse `toggled → action.setChecked` direction has
   no such issue). The three toggle actions are constructed in `_build_ui()`
   (bare `QAction(self, checkable=True)`, no cross-wiring yet - the toolbar
   buttons don't exist at that point in `_build_ui`, same reason
   `settings_toolbar_btn`/`crop_toolbar_btn`'s panel-visibility wiring is
   deferred) and wired for real in `_connect_signals()`.
   `window_thumbnails_action`'s enabled state additionally tracks
   `carousel_toggle_btn`'s own (`_update_carousel_visibility()` now also
   sets `window_thumbnails_action.setEnabled(multi)`). New bare
   (no-modifier) keyboard shortcuts, added to `keyPressEvent` alongside the
   existing E/C/F/Z bare-letter ones (same `not text_editing` guard) rather
   than as real `QAction` shortcuts, for the same reason `delete_selection_action`
   already documents - a real global single-letter shortcut can hijack
   text input in a focused `QLineEdit`: **I** toggles the left panel, **O**
   the right panel, **P** the thumbnails (guarded by
   `carousel_toggle_btn.isEnabled()` too, so it's a no-op with <2 photos,
   matching the button's own disabled state). The menu actions' displayed
   text carries these as display-only hints (`"\tI"`/`"\tO"`/`"\tP"`),
   same convention as `window_close_action`. **`/` was the original choice
   for the thumbnails shortcut, changed to `P` on 2026-09-02** - the user
   flagged `/` as creating too many conflicts.
4. ✅ Link per-channel Solo (B&W preview) to the histogram's own Y/R/G/B
   scope isolation. `HistogramPanel` (`widgets/histogram_widget.py`) got a
   public API - `isolate_channel(ch)`/`show_all_channels()` (renamed from
   the private `_isolate_channel`/folded out of `_reset_channels`) - for
   callers outside the widget to use instead of reaching into `.chart`
   directly, plus a new `reset_requested` signal emitted only when the
   Reset **button** itself is clicked (not when `show_all_channels()` is
   called programmatically), so `MainWindow` can tell "the user asked to
   see everything again" apart from its own calls into the same method.
   `on_solo_toggled(index, checked)` now calls
   `self.histogram.isolate_channel(CHANNEL_NAMES[index])` when a channel
   is soloed and `self.histogram.show_all_channels()` when un-soloed
   (either directly via the checkbox, or via the new
   `on_histogram_reset()`, wired to `reset_requested`, which finds
   whichever layer has `solo=True` and unchecks its `solo_checkbox` -
   letting `on_solo_toggled`'s own `False` branch do the actual
   restoring). This resolved the "what does 'off' mean" ambiguity flagged
   originally in favor of the broader interpretation: histogram Reset also
   turns Solo preview off, not just the histogram's own display - the
   user's original phrasing ("le désactiver à l'effet du reset de
   l'histogramme") supported this reading directly. Verified headlessly:
   solo→isolate, reset-button→un-solos+shows all 4, and un-soloing
   directly (bypassing the reset button) still reverts the histogram too.
5. ✅ Rethink how the histogram works, more broadly - landed in two passes,
   both 2026-09-02, both in `widgets/histogram_widget.py` unless noted:
   - **Visual pass** (first ask - "plus précis et facile à appréhender"):
     two fine, low-alpha (`QColor(255,255,255,26)`) vertical divider lines
     at the shadow/midtone and midtone/highlight thirds, drawn behind the
     curves as a quiet always-on tonal reference. Curve rendering redone
     Lightroom-CC-style: the translucent additive fill under each channel
     dropped from alpha 150 to 60 (a much lighter wash so overlapping
     channels read as tinted glow rather than occlusion), plus a new
     second painting pass that traces a fully solid (~alpha 235), 1.3px
     outline along the curve itself with normal (not additive) blending -
     `HistogramWidget.paintEvent` now builds an open `curve_paths[ch]`
     (the outline) and a closed `fill_paths[ch]` (outline + baseline) per
     channel up front, fills all of them first under
     `CompositionMode_Plus`, then strokes all of them in a second loop
     under `CompositionMode_SourceOver` so the lines stay crisp on top of
     the wash instead of also brightening where they cross.
   - **Accuracy pass** (second ask, after the user noticed the clip
     indicators firing on blacks/whites that weren't visually obvious):
     traced to `imaging.warp_to_canvas`'s `cv2.warpAffine(...,
     borderMode=BORDER_CONSTANT, borderValue=0.0)` - any per-channel
     alignment offset, or the Straighten rotation, pads whatever the warp
     doesn't cover with **real pure-black (0) pixels** in the composite
     (pure-white if that channel also has Negative/invert on, since
     `apply_invert` runs after the warp) - confirmed numerically that a
     mere 2px channel shift alone puts 0.33% of that channel at 0, past
     the 0.1% clip threshold, on a thin border easy to miss at fit-zoom.
     The histogram was already reading the correct final composited/
     cropped array (same `rgb_u8` the canvas and export use) - this
     wasn't a "wrong data" bug, just genuine border-fill pixels reading as
     real clipping. Fixed two ways, both requested by the user together
     rather than picking one:
     - **Exclude the border from the stats entirely.**
       `imaging.warp_coverage_mask(shape, geo_params, ref_size)` warps an
       all-ones array through the exact same per-channel matrix used for
       the real warp, giving 1.0 wherever real source pixels landed and
       0.0 wherever only the constant fill did - exact (works for
       rotated/diagonal borders too, not a guessed rectangular margin).
       `imaging.compose_coverage_mask(images, geo_params, ref_index)` ANDs
       this across all three loaded channels (a channel that's simply not
       imported yet contributes no exclusion - that's real black from a
       missing channel, not a warp artifact, and should still be flagged).
       `MainWindow.recompute_preview()` computes this mask alongside `rgb`/
       `toned` in both the normal and Solo branches, threads it through
       the same `apply_straighten_mirror`/`apply_crop_rect` calls made on
       the image itself (both are plain array ops, so they apply
       correctly to a mask too), and passes `valid_mask=mask > 0.5` into
       `HistogramPanel.set_image`/`HistogramWidget.set_image` (new
       optional parameter, `None` = every pixel counts, unchanged
       behavior). Verified numerically: the 2px-shift case above drops to
       0% flagged once masked, while a real black patch painted into the
       source images (not a warp artifact) still reads 4%+ clipped with
       the same masking applied - the mask only removes warp padding, not
       real content.
     - **Scale the clip-bar's height *and* opacity with severity**,
       instead of a fixed floor. The bar used to jump straight to a
       6px-minimum height at the 0.1% threshold, making a barely-there
       sliver look as loud as a large blown-out region; now
       `severity = min(1.0, frac / 0.05)` (full height/opacity reached at
       5% clipped) drives both `bar_h = max(2.0, severity * h)` and
       `alpha = round(110 + severity * 125)`, so anything just over
       threshold reads as a faint 2px hint and only real, substantial
       clipping reads as a solid full-height bar. This was requested
       specifically as a second, independent fix alongside the masking
       above - not a replacement for it - since even after masking,
       genuine but small real clipping should still look small.

## Curves tool (planned for v0.4.5, added 2026-09-02)

Stated by the user right after v0.4.4 was built as their goal for the next
version: "ajouter un outil de courbes" - a curves tool. **Direction only,
not a functional spec** - don't start writing feature code from this
alone. Open questions to resolve with the user before implementation:
whether it's per-channel (alongside each `ChannelPanel`'s tone controls),
global (alongside `GlobalPanel`'s Light section), or both; whether it
replaces or sits alongside the existing black/white point + gamma +
shadows/highlights + exposure/brightness/contrast parametric tone
controls, or is purely an additional, more expressive alternative; and
where it lives in the UI (its own collapsible section, a dedicated tool
like Crop, etc.). `imaging.py`'s tone pipeline (`apply_tone_curve`) is the
natural integration point once scoped - it already takes a `tone_params`/
`global_params` tuple threaded through many call sites (see the Exposure
slider entry above for the full list of places a new tone parameter has
to be threaded through: model fields, `compose_trichrome`'s tuples,
session persistence ×2 mechanisms, undo, copy/paste, resets, i18n) - a
curves control would likely need the same treatment, but as an array/LUT
rather than a scalar, which is a different enough shape that it may not
reuse that exact tuple-based plumbing as-is.

## Negative scan tool (planned for v0.5.0; v1 capture harness built 2026-09-02)

Ships as its **own tool window** eventually, reachable via both a keyboard
shortcut and a button in the top toolbar - i.e. a peer of the Crop/Global
Correction tool switcher (`settings_toolbar_btn`/`crop_toolbar_btn` in
`main_window.py`), not a dialog buried in a menu - **not wired in yet**,
still developed and run standalone per the user's explicit request (it's
expected to be complex/heavy, so build+test it on its own first, integrate
once it works in isolation). "Trichromy mode" (mentioned as a planned mode
before this pass) turned out to mean the existing 3-mode capture selector
below (B&W/Couleur/Couleur Inversible), not a separate live-3-shot-through-
filters capture flow - no further open question there.

**What v1 actually does** (the user's own scope, given directly - "no image
processing in this tool" and no session-import yet, both deliberate): connect
to a tethered camera, show live connect/disconnect status, trigger a shutter
release, download the result to a configured folder with roll-name+increment
naming, and record which of the 3 capture modes it was shot in. Nothing about
image data is touched.

- **New top-level package `trichrome/scan_tool/`**, run standalone via
  `python3 -m trichrome.scan_tool` (`__main__.py`) - not imported by
  `main_window.py` at all yet, per the standalone-first requirement.
  - `gphoto_backend.py` - all camera I/O goes through the **`gphoto2` CLI**
    (Homebrew `libgphoto2`/`gphoto2`, not the `python-gphoto2` bindings -
    no build toolchain needed, and the CLI's config introspection is enough)
    via `subprocess`, always run with `LC_ALL=C`/`LANG=C` env overrides -
    gphoto2 otherwise localizes its own output to the system locale, which
    would silently break the text parsing below on a non-English Mac.
    `auto_detect()` parses `--auto-detect`'s two-column table;
    `list_config()`/`get_config()`/`set_config()` wrap `--list-config`/
    `--get-config`/`--set-config` generically (label/type/current/choices);
    `capture_and_download()` runs `--filename <pattern> --force-overwrite
    --keep --capture-image-and-download` and parses the actual saved path(s)
    from its "Saving file as ..." stdout lines (a RAW+JPEG quality setting
    downloads two files from one shutter release). **`--keep` is hardcoded
    on** - this tool downloads a copy and never deletes the only copy off the
    camera's card, on purpose, not something to make configurable without
    the user asking.
  - **RAW capture config is deliberately not hardcoded to a Fuji-specific
    path.** `find_quality_config()` searches `list_config()`'s output for a
    config whose leaf name looks quality/format-related
    (`_QUALITY_LEAF_HINTS`) rather than assuming an exact `/main/...` path -
    the real path depends on the camera and libgphoto2 version and can only
    be confirmed against real hardware, which this environment doesn't have.
    The UI's Format dropdown only appears when a matching config with real
    choices is actually found, defaulting to whichever choice contains
    "RAW" (falls back to the camera's own reported current value if none
    matches "RAW"); if nothing quality-shaped is found, the control simply
    stays hidden rather than guessing - matches the user's own "idéalement"
    (ideally) framing of the RAW request as best-effort, not a hard
    requirement. **Confirmed via `gphoto2 --list-cameras` (installed this
    session, `brew install gphoto2` → libgphoto2 2.5.34) that "Fuji
    Fujifilm X-T3" is a supported model** - real tethering/config behavior
    (exact config path, whether RAW capture-and-download actually works
    over USB for this body) is still unverified against real hardware,
    since none is available in this environment; the user has the camera
    and needs to be the one to actually test connect/capture/RAW-format
    end to end.
  - `naming.py` - `build_filename_pattern(roll_name, index)` →
    `"<sanitized roll name>_<index:03d>.%C"`; `%C` is gphoto2's own
    extension-substitution token, left unresolved until download since the
    real extension (RAF/JPG/...) depends on the camera's current quality
    setting.
  - `manifest.py` - `append_entry(folder, filename, mode, invert)` writes/
    appends to a `scan_manifest.json` in the destination folder (list of
    `{filename, mode, invert, captured_at}`). Not read by anything yet -
    exists so the mode/invert decision made at capture time isn't lost
    before a future "import this folder into a session" step can use it,
    since **this tool doesn't touch sessions or `BatchItem`/`ChannelLayer`
    at all** (explicitly out of scope for this pass, per the user).
  - `capture_worker.py` - `CaptureWorker(QObject)` + `run()`, moved to a
    `QThread` by `scan_window.py` exactly like `BatchImportWorker`/
    `export_worker.py`'s existing convention (`moveToThread` →
    `started.connect(run)` → `finished`/`error` → `thread.quit` →
    `deleteLater` ×2 → clear refs) - a RAW download over USB is a few
    seconds, long enough to need this off the GUI thread.
  - `scan_window.py` - the UI. `QSettings(ORG_NAME="TrichromeMaker",
    APP_NAME="ScanTool")` - a **distinct** `APP_NAME` from the main app's
    own `"TrichromeMaker"`/`"TrichromeMaker"` session-autosave domain, so
    this tool's settings can never collide with or corrupt a real saved
    session, tests included. Sections, top to bottom: **Device** (colored
    status dot + label, camera combo - always shown, only meaningfully
    interactive with 2+ cameras - Refresh button, Format dropdown per
    above), **Mode** (3 exclusive buttons + a live note stating whether
    invert will be applied on import for the selected mode - B&W and
    Couleur → invert, Couleur Inversible → no invert, matching the existing
    `invert_checkbox_tooltip` semantics for negative vs. reversal film),
    **Save Location** (base folder + Browse…, subfolder, roll name, next
    number), a big **Capture** button, a status line, and a scrollable
    capture history list for the current run. Device connection is polled
    every 3s via `QTimer` (skipped while a capture is in flight) rather
    than requiring a manual refresh, with manual Refresh still available.
    Reuses `trichrome.widgets.alert_dialog.show_alert` for errors (not a
    native `QMessageBox`) even though this window isn't part of the main
    app yet, so it doesn't need retrofitting later - matches the app-wide
    alert-dialog policy already in effect for everything else.
  - Icons: none yet by design - the user said they'll supply icons for this
    tool later, so v1 uses plain `QPushButton`s throughout (Capture,
    Browse…, Refresh, the 3 mode buttons) rather than guessing at SVG
    assets to hand-draw ahead of time - the existing `resources/icons/
    Scan/` assets (`aperture.svg`/`film.svg`/`iso.svg`/
    `reset_shutter_speed.svg`) are for capture-setting controls (ISO/
    aperture/shutter) this pass deliberately doesn't build, not filenames
    to press into service for Capture/Browse/Refresh.
  - i18n: `scan_*` keys added to the shared `trichrome/i18n.py` EN/FR blocks
    (not a separate local dict) since the tool is expected to fold into the
    main app's language system once integrated - parity verified the usual
    way (`set(EN.keys()) == set(FR.keys())`).
- **Real bug caught and fixed during headless testing**: `_load_settings()`
  originally called `setText()`/`setValue()` on each persisted field in
  sequence, and each one's own `textChanged`/`valueChanged` signal is wired
  straight to `_save_settings()` (which writes *every* field's current
  widget value, not just the one that changed) - so loading field N would
  fire a save that echoed field N+1's still-default value back into the
  settings store before field N+1 was ever read, permanently clobbering it.
  A persistence round-trip test (`next_number` set to 42, reloaded in a
  fresh `ScanToolWindow`) caught this reading back `1` instead. Fixed by
  wrapping the whole load sequence in `blockSignals(True/False)` on the
  affected widgets, the same technique already used throughout
  `main_window.py` for model→UI syncs that must not re-trigger the reverse
  UI→model path.
- Verified headlessly (`QT_QPA_PLATFORM=offscreen`, isolated `QSettings`
  domain per the project's testing convention, `gphoto_backend` functions
  monkeypatched since no camera is attached in this environment): all of
  `auto_detect`/`get_config`/`list_config`/`find_quality_config`/
  `capture_and_download`'s text-parsing against realistic sample gphoto2
  output; device-connected/disconnected/reconnected UI state transitions;
  the Format dropdown defaulting to a RAW choice; mode-switch invert-note
  text; the settings persistence round-trip (post-fix); and a full mocked
  capture → download → manifest-write → history-list → counter-increment
  wiring pass through the real `QThread`/`CaptureWorker` path with a fake
  `capture_and_download`. **Not, and can't be, verified here**: an actual
  shutter release, actual RAW download, or the real Fuji config path names -
  all need the user's real X-T3 over USB.
- **Real X-T3 tethering confirmed working, 2026-09-02.** `brew install
  gphoto2` (2.5.32, libgphoto2 2.5.34) run against the actual camera; a real
  shutter release + download through `gphoto_backend.capture_and_download`
  produced a genuine 6240×4160 JPEG with FUJIFILM X-T3 EXIF data. Getting
  there took real debugging, documented in full in
  `_release_macos_ptp_camera`'s own docstring in `gphoto_backend.py`
  (read it before touching this function again) - short version: gphoto2
  first failed with error -53 "Could not claim the USB device". The
  original fix here killed `PTPCamera` (the classic macOS/gphoto2 advice),
  which turned out to be a no-op - that process wasn't even running. The
  actual modern process is `/usr/libexec/ptpcamerad` (now killed alongside
  the old name, for both macOS-version cases). Killing the daemon alone
  *still* wasn't enough on this machine: **FUJIFILM X Webcam's own
  `com.fujifilm.XWebcam.CameraExtension` System Extension** (installed
  separately by the user for using the X-T3 as a video-call webcam) holds
  its own continuous PTP session with the camera, confirmed via
  `systemextensionsctl list` showing it `[activated enabled]` - a
  DriverKit-level claim that doesn't respond to `killall` at all. The user
  had to disable it manually (System Settings ▸ General ▸ Login Items &
  Extensions ▸ Driver Extensions) before a capture would go through -
  **this is a per-machine gotcha to remember, not something this codebase
  can fix**: any camera-as-webcam driver software (Fuji's specifically
  here, but the same class of conflict applies to similar tools for other
  brands) installed and left enabled will block tethered capture the same
  way, including after a reboot if it re-enables itself. If capture ever
  regresses again with -53/-110 after this point, check for that before
  assuming it's a code bug.
  - RAW format was not exercised in this pass (the test capture above was
    a plain JPEG, the camera's default quality setting) - `find_quality_config`/
    the Format dropdown's actual behavior against this camera's real config
    tree is still unverified. Worth confirming next time the user runs the
    tool for real.
  - Not yet done: wiring the tool into the main app's toolbar (still
    deliberately standalone-only, per the original ask).
- **"Use roll name as subfolder" + Scan Light (RGB backlight capture),
  added 2026-09-02** - both in `scan_window.py`:
  - `use_roll_subfolder_checkbox`: when on, `subfolder_edit` is disabled
    (greyed, not hidden) and `_destination_folder()` derives the subfolder
    from `naming.sanitize_roll_name(roll_name)` instead - a live
    `subfolder_preview_label` shows what that resolves to, since the
    sanitized name can differ from the raw roll-name text. Persisted like
    every other field here.
  - **Scan Light**: a 3-way exclusive mode (External/White/RGB,
    `light_mode_group`) for using the computer screen itself as a
    backlight behind the film - `BacklightWindow`, a plain solid-color
    top-level `QWidget` (not a `QDialog` - must stay open and independently
    movable/resizable while the tool window keeps working). White and RGB
    both show it plain white at rest (drag it onto whichever display sits
    behind the rig, then use macOS's own native fullscreen to fill that
    screen) - RGB mode's white-at-rest is deliberate, per the user
    ("pour une meilleure visualisation" - easier to frame/focus by than a
    single primary color).
  - **RGB mode's real point: Capture triggers an automatic 3-shot
    sequence**, not a single shot - pressing Capture while RGB is selected
    walks red → shoot → green → shoot → blue → shoot → back to white,
    entirely replacing a physical R/G/B filter with colored light itself.
    State machine: `_rgb_sequence_active`/`_step`/`_paths`/`_port` on
    `ScanToolWindow`; `_advance_rgb_sequence()` sets the window to the next
    `_RGB_CHANNEL_COLORS` entry, waits `_LIGHT_SETTLE_DELAY_MS` (400ms -
    lets the screen's color swap and any camera auto-metering settle
    before the shutter fires) via `QTimer.singleShot`, then calls
    `_start_capture(port, letter)`; `_on_capture_step_finished` is the
    shared completion handler for both a plain single shot and one step of
    a triplet - it re-enters `_advance_rgb_sequence()` for steps 0/1, and
    only calls `_finish_capture()` (write manifest + history + advance the
    counter) after step 2. **All 3 shots share one index number**, only
    distinguished by a `_R`/`_G`/`_B` filename suffix -
    `naming.build_filename_pattern(roll, index, channel=...)` and
    `manifest.append_entry(..., channel=...)` both grew an optional
    `channel` parameter for this (manifest field only written when given,
    so old-format entries/readers are unaffected). The counter
    (`next_number_spin`) advances by exactly **1** for the whole triplet,
    not 3.
  - **Partial-failure handling**: if channel 2 (or 3) fails mid-sequence,
    `_handle_capture_failure()` still logs whichever channel(s) already
    succeeded (never silently dropped) but does **not** advance the
    counter - the triplet is incomplete, so a retry should reuse the same
    index rather than skip ahead. The backlight always returns to white
    afterward, success or failure. `_on_capture_error` and a `makedirs()`
    failure inside `_start_capture` both funnel through this same helper.
  - **A real debugging trap hit while testing this headlessly, worth
    remembering**: `_selected_port()` reads `self.camera_combo`'s current
    item, not `self._cameras` directly - a test that sets
    `w._cameras = [...]` without also calling
    `w.camera_combo.addItem(...)` gets `_selected_port() -> None`, which
    silently routes into `show_alert(...)`'s **modal** `.exec()` - under
    `QT_QPA_PLATFORM=offscreen` with nothing able to click it, that hangs
    the test *forever* with zero further output, which looks exactly like
    a real deadlock in the capture/QThread code (confirmed it wasn't, via
    an isolated bare-QThread sanity test that completed instantly). Any
    future headless test of capture here must populate `camera_combo`
    (mirroring what `_poll_devices()` does), not just `_cameras`.
- **Cmd+Return capture shortcut, "Add to Current Session" placeholder, and
  a real Process pipeline, added 2026-09-02** - all in `scan_tool/`:
  - **Cmd+Return/Cmd+Enter triggers Capture** from either the main
    `ScanToolWindow` or the `BacklightWindow` (Qt maps Ctrl<->Cmd
    automatically on macOS, so `QShortcut(QKeySequence("Ctrl+Return"))`
    is the right binding) - useful since the backlight window is usually
    the one actually focused while positioning film on it.
    `BacklightWindow.__init__` takes an optional `on_capture` callback
    wired to both key sequences; both `_sync_backlight_window()` and
    `_advance_rgb_sequence()` now go through a shared
    `_ensure_backlight_window()` instead of each constructing
    `BacklightWindow()` separately, so the callback is only wired once.
    `_on_capture_clicked` gained an explicit `if self._capturing: return`
    guard at the top - the Capture *button* already disables itself
    mid-capture, but a keyboard shortcut bypasses button-enabled state
    entirely, so the guard has to live in the handler itself.
  - **`add_to_session_button`** ("Add to Current Session"), below the
    "Captured this session" list. `_on_add_to_session_clicked` is a
    deliberate no-op for now, exactly as asked - it'll import this
    session's captures into the main app's active session once the tool
    is wired in there (still standalone-only).
  - **`process_checkbox`** ("Also save a processed JPG preview"), in the
    Scan Light panel (placement per the user's own request, even though
    the feature applies regardless of which light mode is active - Light
    and Mode are independent settings, Process just happens to live in
    the Light panel). New pure-function module `scan_tool/process.py`
    (no Qt) reuses `trichrome.imaging`/`trichrome.alignment` directly -
    the exact same functions the main app's own export pipeline is built
    on, so this preview matches what a real import would eventually
    produce:
    - `process_single(path, invert, is_color, dest_folder)`: B&W mode
      loads via `imaging.load_grayscale` (collapses to luminance) and
      stacks the result into RGB for a valid JPG; Color/Color Reversal
      load via a **new** `imaging.load_color(path)` (added alongside
      `load_grayscale` - same normalization logic, but never collapses to
      one channel, since nothing existing preserved real color data for a
      single already-color photo). `invert` comes straight from
      `MODES`' own 3rd element (`True` for bw/color, `False` for
      color_reversal) - this is exactly the same True/False the tool
      already surfaced as an on-import hint (`scan_mode_invert_note`),
      just actually applied here instead of only described.
    - `process_rgb_triplet(paths_by_channel, invert, dest_folder,
      out_basename)`: the RGB-Light case - loads all 3 channel shots via
      `load_grayscale`, auto-aligns the 2 non-reference channels onto
      reference index 1 ("G", matching the main app's own default
      reference-channel convention) via `alignment.auto_align_layer`
      (falling back to identity/no-alignment for a channel if
      `AlignmentError` is raised, rather than failing the whole recompose
      - this is a best-effort preview, not a tunable export), then
      `imaging.compose_trichrome` with fully neutral tone/global params
      (`_NEUTRAL_TONE`/`_NEUTRAL_GLOBAL`, copied from the same constants
      in `main_window.py`) and `invert` from the *currently selected
      capture Mode* - Light and Mode are independent, so recompose still
      respects whichever polarity Mode says, exactly like the single-shot
      case. Output filename drops the per-channel suffix (`naming.py`
      gained a public `base_name(roll, index)`, factored out of
      `build_filename_pattern`, so this doesn't need to reach into the
      private `_PAD` constant) - one combined `<roll>_<index>.jpg`, not 3.
    - Runs in its own `QThread`/`ProcessWorker` (`process_worker.py`,
      same convention as `capture_worker.py`, but its `finished` signal
      carries `list[str]` since a batch of single-shot files each get
      tried independently - one unreadable file, e.g. a RAW format PIL
      can't decode, is skipped rather than failing the whole batch)
      **entirely separate `self._process_thread`/`_process_worker` state
      from the capture thread's own** - processing a slow RGB recompose
      must never block or get confused with the next capture starting.
      Triggered from `_finish_capture()` (only on a *successful* capture -
      `_handle_capture_failure`'s partial-RGB-triplet logging path passes
      `allow_process=False`, since `process_rgb_triplet` needs all 3
      channels and a partial triplet by definition doesn't have them).
      `closeEvent` now waits on `_process_thread` if one is still running
      rather than letting the window disappear out from under a live
      QThread. A successful process appends an extra history-list line
      (`"    ↳ Processed: <filename>"`) once done; a failure shows the
      same `show_alert` used elsewhere, without touching what capture
      already logged.
  - Verified headlessly with real synthetic PIL images (not just mocked
    return values, since `process.py` actually decodes pixel data):
    B&W inversion, Color inversion, Color Reversal passthrough, and a full
    RGB-triplet recompose all produce numerically correct output; both
    shortcuts are wired on both windows; the Add-to-Session button is a
    real no-op; and the full `ScanToolWindow` orchestration (capture →
    manifest/history → automatic process → second history line) works
    end-to-end for both a single shot and a full RGB triplet.

## v0.6.0 wishlist (added 2026-09-02)

- **Metadata panel** - add a panel showing metadata (presumably EXIF from
  the source photos and/or the trichrome composite's own derived info,
  exact scope not yet stated). No spec yet: what fields, where it lives in
  the UI, whether it's per-channel or per-composite, read-only or
  editable. Don't start on this without a real functional spec, same
  caveat as the Scan tool above.

## Crop tool (ongoing since 2026-09-01)

Built out from a placeholder into a real tool, then refined the same day and
again on 2026-09-02 - expect further functional and visual passes, this
section should stay current rather than becoming a historical log.

**Shape of the feature:**
- `CropPanel` (`widgets/crop_panel.py`): aspect ratio (presets + custom +
  "invert orientation", **`"original"` is the default**, ahead of `"free"`),
  straighten, mirror (see below), a grid-style picker, and a header row of
  Activate/Reset buttons (see "Active crop mode" below - the Copy button
  that used to sit here is gone, 2026-09-04).
- An interactive draggable crop rectangle drawn directly on `CanvasWidget`'s
  `_ImageLabel` (`widgets/canvas_widget.py`) - corner-handle resize +
  inside-drag move, aspect-ratio-locked when one is set, dimmed surroundings
  + grid overlay.
- `CropSettings` dataclass (`model.py`), one per `BatchItem` (`item.crop`),
  mirroring `GlobalCorrection`'s shape/conventions.
- Two tiers of "when it applies": straighten/mirror/aspect-ratio/grid apply
  **live**, like every other slider in the app - but the crop **rectangle**
  itself is only a live canvas-side proposal (`CanvasWidget.crop_rect()`)
  until **Enter** commits it into `item.crop.x/y/width/height`
  (`MainWindow.on_crop_apply`, wired in `keyPressEvent` only while active
  crop mode is on - see "Active crop mode decoupled from block visibility"
  below). Exiting without pressing Enter (Escape, or turning active mode
  off any other way) discards the in-progress drag, never touches the model.
- **The Crop tool's own preview always shows the full straightened/mirrored
  frame**, never the previously-applied crop - `imaging.apply_crop()`
  (straighten → mirror → crop) is a thin wrapper over two separately-callable
  steps, `apply_straighten_mirror()` and `apply_crop_rect()`;
  `recompute_preview` skips `apply_crop_rect` while `self._crop_active` is
  True. Every other view (Global Color Correction, the histogram, both
  export paths) shows the fully-cropped result via the combined
  `apply_crop()`, so cropping never shrinks against a previous crop.
- `mirror_h`/`mirror_v` (left/right vs. top/bottom, not a single `mirror`
  flag) - each its own `SvgCheckableToolButton` using `Crop/mirror_line.svg`
  and `Crop/mirror_line_vertical.svg` (the same icon,
  `transform="rotate(90 12 12)"` - duplicating and rotating an existing SVG
  like this is fine, distinct from hand-drawing a new one from scratch).
  `CropSettings.ratio_value()` can't resolve `"original"` alone (no
  image-size context), so callers go through
  `MainWindow._current_crop_ratio_value()` instead, which reads the actual
  reference layer's size. Grid defaults to `"3x3"`, not `"off"` (see the
  grid-overlay redesign below).
- `crop` is threaded through every place `BatchItem` fields must be (per the
  session-persistence and undo/redo notes above) plus the filmstrip's
  "Reset All" (`item.crop.reset()`, also exposed as the Crop panel's own
  Reset button, `General/Reset.svg`).
- **Copy/paste is deliberately asymmetric.** `_extract_settings()` (used by
  Cmd+C and the filmstrip's Copy - they all funnel through
  `copy_settings_from`) captures crop alongside color. The regular Paste
  (Cmd+V, filmstrip Paste) still only restores color, same as before -
  crop is only ever restored by the dedicated `paste_crop_to()`, reachable
  via the filmstrip's right-click **"Paste Crop"** entry (only shown once
  something with crop data has been copied -
  `CarouselWidget.set_paste_crop_available()`). The Crop panel itself has
  **neither a Copy nor a Paste button of its own** - it never had Paste
  (removed 2026-09-01, redundant with the filmstrip entry), and its own
  Copy button (which duplicated Cmd+C/filmstrip Copy) was removed
  2026-09-04 as part of decoupling active crop mode from block visibility
  (see below) - only Activate and Reset remain in its header row.

**Icons**: `resources/icons/` is organized into subfolders by usage area
(`Color Correction/`, `Crop/`, `General/`, `Letters/`, `Preview/`, `Scan/`,
`Toolbar/`) - every reference includes its subfolder, e.g.
`SvgToolButton("Crop/crop.svg")`. The Settings toolbar button uses
`Toolbar/horizontal_sliders.svg`; the Histogram and Global Color Correction
reset buttons and the Crop panel's own Reset use `General/Reset.svg`. The
Crop panel's aspect-ratio row shows an `SvgIconLabel` (reusable widget in
`svg_icons.py`, alongside `SvgToolButton` - a static, non-clickable
tinted-SVG label whose icon can change at runtime via `set_icon()`, which
also takes an optional `rotation` in degrees) that tracks the selected ratio
through a `_RATIO_ICONS` dict in `crop_panel.py`; Invert Orientation is an
`SvgToolButton("Crop/crop_rotate.svg")` on that same row, right of the
combo, and disables itself (`_ratio_invert_meaningful()`) whenever inverting
couldn't change anything - `"free"` (unconstrained) or `"1:1"` or a custom
ratio someone set to W==H. The Grid row's label is an
`SvgIconLabel` too, tracking the selected grid mode the same way (see
below). The Straighten slider (`SliderSpin`/`_ResettableSlider` in
`widgets/controls.py`) has `set_show_center_mark(True)`, drawing a small
tick at its horizontal midpoint in `paintEvent` - only meaningful for a
slider whose default sits exactly at the middle of its range, as
Straighten's -45..45/0 does.

**Ratio presets, ordering, and orientation icon (2026-09-01):**
`RATIO_KEYS` in `crop_panel.py` is `("original", "free", "1:1", "5:4",
"4:3", "7:5", "3:2", "16:9", "custom")` - the non-numeric entries
(`original`/`free`/`custom`) keep their original spots, and the numeric
presets are ordered most-square to widest (`1:1`=1.0 → `5:4`=1.25 →
`4:3`=1.33 → `7:5`=1.4 → `3:2`=1.5 → `16:9`=1.78), matching
`CropSettings._PRESET_RATIOS` in `model.py` (which needs the same set of
keys - add a new ratio to both places). `7:5` (`Crop/crop_7_5.svg`) and a
real `4:3` icon (`Crop/crop_4_3.svg`, once the user supplied it - `4:3`
used to fall back to the generic `aspect-ratio.svg`) were added this pass.
The ratio icon rotates 90° (`SvgIconLabel.set_icon(..., rotation=90.0)`)
whenever `crop.aspect_portrait` is set, so the glyph visually matches
whichever orientation is actually selected - `CropPanel` tracks this as
`self._portrait`, refreshed in `set_from_crop()`.

**Grid overlay redesign (2026-09-01):** replaced the old two-option
"Rule of Thirds"/"Grid" picker with four real overlay styles plus Off -
`_GRID_MODES = ("off", "3x3", "2x2", "golden", "grid")` in `crop_panel.py`,
each with its own icon in `_GRID_ICONS` (`Crop/grid_3x3.svg`,
`Crop/grid-2x2.svg`, `Crop/grid-golden-ratio.svg`, `Crop/grid.svg`
reused for both `"off"`'s fallback and `"grid"` itself - there's no
dedicated off/no-grid glyph). `3x3`/`2x2`/`golden` all draw lines as
**fractions of the crop rect** (adapting to its size/ratio as it's
resized) via `_ImageLabel.paintEvent` in `canvas_widget.py` - `golden`'s
two lines sit at `1/φ` and `1 - 1/φ` (≈0.618/0.382,
`_GOLDEN_FRACTION_HIGH`/`_GOLDEN_FRACTION_LOW`) instead of evenly-spaced
thirds. `"grid"` is different on purpose: fixed-size squares
(`_FIXED_GRID_SPACING_PX = 24.0`, constant screen pixels) tiled from the
rect's top-left corner, which do **not** adapt to the rect's size or ratio
- this was an explicit user requirement ("les carrés restent de même
taille peu importe le ratio et la fenêtre de crop").

**Locked-ratio edge-clamping bug (2026-09-01):** dragging a resize handle
with a fixed aspect ratio, when the drag pushed the rect past the image's
edge, used to clamp `x`/`y`/`w`/`h` against the `[0,1]` bounds
independently per axis (`_ImageLabel._resize_crop_rect` in
`canvas_widget.py`) - which silently distorted the locked ratio right at
the frame's edges (and `imaging.apply_crop_rect` would then clip
asymmetrically on top of that). Fixed by computing a single `scale` factor
from whichever axis is tighter (`max_w`/`max_h`, the available room from
the drag's fixed anchor corner to that edge) and shrinking **both**
dimensions by it together, so the ratio survives clamping exactly -
verified numerically (dragging a 16:9-locked rect out past the bottom-right
corner still lands on a rect whose real-pixel ratio is exactly 16/9).

**Header-row parity with Global Color Correction (2026-09-01):** the user
wants switching between the Crop and Global Color Correction panels to
never visibly shift anything, at any side-panel width. Both panels' header
rows follow the same shape - `title_label` (identical
`"font-weight: bold;"` stylesheet in both) → `addStretch(1)` → a Reset
button → one smaller "companion" icon button (the channel-correction
warning glyph on Global, Copy on Crop) - so the trailing button cluster is
the same total width in both and lands flush against the row's right edge
either way, regardless of panel width. This only holds because the Reset
and companion sizes are actually shared, not just visually similar:
`HEADER_RESET_BTN_SIZE`/`HEADER_RESET_ICON_SIZE` (41×36/24) and
`HEADER_COMPANION_BTN_SIZE`/`HEADER_COMPANION_ICON_SIZE` (34×30/20) live in
`svg_icons.py` and both `global_panel.py` and `crop_panel.py` import them
rather than redefining their own numbers - `crop_panel.py`'s Copy and
Invert Orientation buttons use the companion size, only its Reset uses the
larger one. Keep using these shared constants for any future header-row
icon button in either panel instead of hardcoding a size again, or the two
panels will drift out of sync the way they did here (Crop's Reset used to
be the smaller 34×30 size while Global's had already been enlarged to
41×36 in the v0.4 sidebar polish, roadmap item 5). The histogram box
(`histogram_box`) sits above both panels as a separate, always-visible
sibling in `right_container`'s `QVBoxLayout` (see `_build_ui`), so its own
position is already unaffected by which of Global/Crop is shown below it -
no change was needed there.

**Escape and per-photo behavior (2026-09-01; Escape's own effect superseded
2026-09-04, see "Active crop mode decoupled from block visibility" below):**
- Escape while active crop mode is on turns it off **without** committing
  the in-progress drag - mirrors "exiting mid-drag discards the proposal."
- In fullscreen, Escape's existing "leave fullscreen" branch is checked
  first and returns early - so leaving fullscreen and leaving Crop mode
  are two separate Escape presses, never both at once.
- `activate_batch_item` (ordinary filmstrip Left/Right/click navigation)
  was missing the `_sync_crop_panel_from_item()` call that the other
  restore paths (`_restore_state`, `_apply_restored_items`) already had -
  fixed, since without it every photo showed whichever crop settings
  happened to be in the panel from before, not its own.
- Fixed a real unit-mismatch bug in both places a target real-pixel aspect
  ratio gets applied to the crop rect: the rect's `x/y/width/height` are
  normalized **independently** as fractions of the image's own width and
  height, so they only equal real-world proportions when the image is
  square. Converting a target ratio into that normalized space now goes
  through a correction factor - `MainWindow._composed_image_ratio()`
  (from `image_preview.shape`) in `on_crop_settings_changed`'s
  ratio-change reshape, and the displayed label's own `width()/height()`
  (`label_ratio`, reliably equal to the image's true aspect ratio since
  the label is always sized to match the scaled pixmap) in
  `_ImageLabel._resize_crop_rect`'s drag-resize path in
  `canvas_widget.py`. Both previously did `new_h = new_w / ratio` /
  `h = min(w / ratio, ...)` directly in normalized space, which was wrong
  for any non-square photo.

**Active crop mode decoupled from block visibility (2026-09-04).** Since
the block system overhaul let the Crop block be shown in any custom
layout, alongside anything else, tying "is the interactive crop overlay
armed" directly to "is the Crop block visible" (`block_visible.get("crop")`,
via `_on_crop_block_visibility_changed` - the previous mechanism) meant the
draggable canvas overlay, Enter-to-apply, and full-vs-cropped preview frame
could pop on/off unexpectedly any time the block appeared/disappeared while
reorganizing layouts - not just when the user actually meant to start or
stop cropping. The user's own framing: "l'outil crop étant désormais
affichable sur plusieurs layout, cela créé des soucis quant à l'affichage
de la fenêtre de 'crop actif'."
- **`MainWindow._crop_active: bool`** (init `False` in `__init__`, next to
  `_compare_active`) is now the one source of truth for whether crop mode
  is armed - entirely independent of `block_visible["crop"]` (whether the
  panel/block happens to be shown). **`_set_crop_active(active)`**
  (renamed from `_on_crop_block_visibility_changed`) is the single place
  that changes it: syncs `crop_panel.activate_button`'s checked state
  (`CropPanel.set_active()`, blockSignals so it can't re-trigger),
  arms/disarms `canvas.set_crop_enabled()`, disarms the white-balance
  eyedropper and re-syncs the panel from the model when turning on, and
  calls `recompute_preview()` either way. **Activating also force-shows
  the block** (`set_block_visible("crop", True)` - no point arming an
  invisible tool) **but deactivating never touches visibility** - that
  would be a layout change, which Escape/apply deliberately are not.
- **`CropPanel` header, reworked**: the old Copy button is gone; a new
  checkable **`activate_button`** (`Crop/crop.svg` - the same icon as the
  top toolbar's "Layout - Crop" button, since it's the same concept) sits
  where Copy used to, immediately left of Reset - Reset itself moved to
  be the header's right-most action, matching every other block's own
  header order (title, [action buttons], Reset last). Toggling it emits
  `activate_toggled(bool)`, wired straight to `_set_crop_active`.
- **Every one of the ~10 places that used to read `block_visible.get("crop")`
  was individually re-examined** and split into two groups, not
  mechanically renamed as one: call sites that gate the *interactive*
  behavior (Escape/Enter handlers in `keyPressEvent`, `on_white_balance_picked`'s
  and `recompute_preview`'s "show full frame while cropping" branches) now
  check `self._crop_active`; call sites that only refresh the panel's own
  *displayed* controls when it happens to be on screen
  (`activate_batch_item`, `paste_crop_to`, `reset_batch_items`,
  `_restore_state`, `_apply_restored_items` - all "sync `crop_panel` from
  the model if visible, cheap display optimization, nothing to do with
  active mode") were deliberately left reading `block_visible.get("crop")`,
  unchanged.
- **The 4 explicit behaviors requested, all reachable through
  `_set_crop_active`/`set_block_visible`**:
  - Enter validates (`on_crop_apply`) - still commits `canvas.crop_rect()`
    into `item.crop`, then calls `_set_crop_active(False)` instead of the
    old `set_block_visible("crop", False)` - the block/layout is no longer
    touched by applying, only active mode.
  - Escape exits active mode without changing layout - `keyPressEvent`'s
    Escape branch now checks `self._crop_active` and calls
    `_set_crop_active(False)` only, never `set_block_visible`.
  - Activating the "Crop" layout (toolbar button, bare **C**, or the
    Window-menu entry - all funnel through `_activate_default_layout`)
    auto-activates crop mode: after loading its source preset, it calls
    `self._set_crop_active(name == "Crop")` unconditionally - `True` for
    the Crop slot, `False` for every other slot. This fires even if the
    underlying custom preset (e.g. `NewCrop`) hasn't been set up yet
    (`_load_layout_preset` no-ops silently on a missing preset) - pressing
    **C** still arms crop mode and shows the block either way, since
    `_set_crop_active(True)` force-shows it itself.
  - Changing layout auto-deactivates crop mode - `_apply_restored_layout()`
    (the shared tail for **every** layout load: session restore, `.trirgb`,
    and any Layout Preset - custom or built-in) unconditionally ends with
    `self._set_crop_active(False)`; `reset_layout()` does the same
    explicitly at its own end, since it doesn't route through
    `_apply_restored_layout`. `_activate_default_layout`'s own call
    (previous bullet) runs *after* the preset-load's deactivation, which
    is what lets it override back to `True` specifically for "Crop."
  - Not explicitly requested but a direct consequence of the same
    decoupling, added as a safety net: `set_block_visible("crop", False)`
    (the block's own close button, or unchecking it in the Tools menu)
    also calls `_set_crop_active(False)` if it was active - hiding the
    panel while the canvas overlay stayed armed with nothing to interact
    from it through wouldn't make sense. This is the one place
    `set_block_visible` still reaches into crop-active state at all;
    showing the block never arms it back.
- `crop_activate_tooltip` i18n key ("Activate Crop mode"/"Activer le mode
  Recadrage") replaces the removed `crop_copy_tooltip`.
- Verified headlessly (`QT_QPA_PLATFORM=offscreen`, isolated QSettings
  domain): header row order (grip → title → stretch → `activate_button` →
  `reset_button` → collapse → close, no Copy button); clicking
  `activate_button` arms `canvas.image_label.crop_enabled` and shows the
  block; Escape deactivates while leaving the block visible; Enter commits
  the dragged rect into `item.crop` *and* deactivates while leaving the
  block visible; closing the block while active deactivates it too;
  `_activate_default_layout("Crop")` activates and shows the block,
  `_activate_default_layout("Trichrome")` deactivates it;
  `reset_layout()` deactivates it; EN/FR tooltip text.

## Harris Shutter Effect (added 2026-09-01)

By default every R/G/B source is flattened to standard luminance before
anything else happens - `imaging.load_grayscale()`'s `.convert("L")` - which
is correct for the app's core case (real B&W photos shot through a color
filter) but throws away per-channel color data, so 3 *actually color* source
photos can never produce a true Harris Shutter effect (each channel slot
using that photo's own real R, G, or B plane, the way the classic effect
combines 3 video frames). A checkbox now offers that as an explicit,
opt-in alternative mode.

- **UI**: `harris_shutter_checkbox` sits at the **bottom** of the
  Independent Channels group (`main_window.py::_build_ui`, after the 3
  `ChannelPanel`s - below the Blue channel panel's blue border, on
  purpose), with a `"?"` info button to its right using the same
  `show_info_bubble` pattern as `ChannelPanel.active_info_button` /
  `ImportPanel.lock_info_button`. Its info bubble text
  (`harris_shutter_info` in `i18n.py`) is the one spot in the app that
  passes HTML to `show_info_bubble()` - `InfoBubble`'s `QLabel` auto-
  detects rich text (Qt's `mightBeRichText()`, triggered by the string
  starting with a `<b>` tag), so no change was needed in
  `widgets/info_bubble.py` itself. Format: `<b>` for the two bold
  white-ish mode names ("Off (default)"/"On" - inheriting the label's own
  `#f0f0f0`), `<span style="color:#9a9a9a;">` for the muted one-line
  description under each, `<br><br>` between the two blocks for a blank-
  line gap - mirrors the help dialogs' bold-heading/muted-body split
  (`_help_dialog_text_colors`) without needing that helper, since the
  bubble's background is always the same fixed dark color regardless of
  app theme.
- **`imaging.load_grayscale(path, channel=None)`**: `channel=None` (the
  default) is the original behavior, unchanged. `channel="R"/"G"/"B"`
  converts the source to `"RGB"` instead of `"L"` and slices out that one
  real channel *after* normalization. Critically, a source that's already
  single-channel (`L`/`I`/`I;16`/`F` - true monochrome files, no color data
  to extract) is completely unaffected by `channel` either way - both
  branches converge on the exact same array, verified numerically. This
  matters because extracting a fixed channel from a *not-quite-neutral*
  B&W scan (JPEG chroma-subsampling noise, sepia/toning, scanner drift)
  would otherwise measurably shift tone and add noise depending on which
  channel got picked - the classic "red-filter B&W conversion" effect,
  undesirable when it happens by accident. Real single-channel files never
  hit that path.
- **It's a global/session-level mode, not a per-photo field**: read
  directly off `harris_shutter_checkbox.isChecked()` everywhere a channel
  gets loaded, mirroring how panel visibility is read straight from its
  toggle button rather than a separate bool - no new `BatchItem`/
  `ChannelLayer` field. The checkbox's checked state is the only source of
  truth, threaded through **5 call sites**: `_load_image_from_path`
  (manual single-channel load), `_legacy_restore_session` and
  `_build_restored_items_from_data` (both session-restore paths - loop
  index `ci`/`color_index` maps directly to `CHANNEL_NAMES`), `_full_res_image`
  (export-time reload), and `BatchImportWorker._build_item` (batch import -
  `harris_shutter: bool` param threaded from `MainWindow.start_batch_import`
  through to `import_worker.py`, where the loop already iterates by letter).
- **Session persistence**: follows the same "window-level state, not part
  of `batch_items`" pattern as panel visibility (see the session-
  persistence note above) - `harris_shutter_enabled` in both
  `_save_session_state`/`_collect_session_data` and both restore paths,
  synced through `_apply_restored_layout`'s new 4th parameter. One wrinkle
  panel-visibility didn't have: the value has to be known **before** the
  per-channel `load_grayscale` calls inside the restore functions run (so
  images get reloaded with the right mode), not just applied afterward -
  `_legacy_restore_session` reads it into a local up front,
  `_build_restored_items_from_data` reads it straight off its `data` param
  at the top, and *then* it's also passed to `_apply_restored_layout` purely
  to sync the checkbox's own visual state (with `blockSignals`, since
  setting it there must not re-trigger a reload - the images were already
  loaded correctly by the loop above).
- **Toggling live**: `on_harris_shutter_toggled` reloads each of the 3
  *currently loaded* channels from disk under the new mode (pixel data
  only - alignment/tone-curve values are left untouched) and pushes one
  undo entry if anything actually reloaded. Future imports (single or
  batch) automatically pick up the new mode since they all read the same
  checkbox at load time.

## Exposure slider (added 2026-09-02)

A new tone control, `exposure`, added to both `ChannelLayer` (per-channel,
Independent Channels panel) and `GlobalCorrection` (Global Correction panel)
in `model.py` - sits **above Brightness** in both `ChannelPanel.tone_box`
and `GlobalPanel`'s Light group (`_light_sliders`/the tuple that also
drives layout order, so this is a real ordering dependency, not just visual
proximity).

- **Why it's a separate control from Brightness, not a rename** - asked by
  the user directly ("est-ce que exposure diffère de brightness ?") before
  requesting this: Exposure models a physical change in how much light was
  captured - a **multiplicative gain in stops (EV)**, `2**exposure`,
  applied **first**, before anything else in `imaging.apply_tone_curve`
  (before black/white point, gamma, shadows/highlights zone adjustment,
  contrast). Brightness stays what it always was - a simple **additive**
  offset applied at the very end of the same function, after
  contrast. Multiplicative-and-early vs. additive-and-late is the real
  difference: Exposure scales shadows/mid/highlights proportionally
  (pushing it hard blows out highlights first, the same way overexposing a
  shot would), Brightness shifts everything more evenly and doesn't have
  that same runaway-highlights behavior. Verified numerically: +1 EV
  exactly doubles a mid-gray value (0.5 → 1.0, clipped), -1 EV exactly
  halves it (0.5 → 0.25).
- **Range: -5.0 to +5.0 EV, `percent_mode=False`** (real units displayed
  directly, e.g. "+1.50"), not the ±100 percent-mapped scale most of this
  panel's other sliders use - explicitly requested ("peut être sur une
  autre échelle que +/-100 si c'est plus pertinent au concept"), matching
  the existing rule (see the `SliderSpin`/`ClickToEditValue` entry above)
  that `percent_mode` is for a value whose unit isn't independently
  meaningful (a multiplier, an additive shift) - EV already means something
  on its own, same reasoning as alignment's dx/dy/scale/rotation or Crop's
  Straighten degrees. Still centered/signed like every other slider here
  (`signed = percent_mode or default == 0` in `SliderSpin` already covers
  this since Exposure's default is exactly 0 - no special-casing needed).
- **Threaded through every place a tone value must be** (per the
  session-persistence/undo/copy-paste conventions elsewhere in this file):
  `imaging.apply_tone_curve`/`apply_global_correction`/
  `compose_rgb_from_channels`/`compose_pre_white_balance_rgb`/
  `compose_trichrome`'s `tone_params`/`global_params` tuples (both grew one
  field, inserted right after `gamma`/before `brightness` in every tuple
  - **position matters**, these are plain tuples unpacked positionally,
  not dicts, so every construction site and every unpacking site had to
  move in lockstep: `main_window.py` (4 tone_params/global_params
  construction sites, `_warp_and_tone`'s Solo-mode unpacking,
  `_NEUTRAL_TONE`/`_NEUTRAL_GLOBAL`), `export_worker.py`,
  `widgets/export_dialog.py`); `ChannelLayer.reset_tone()`/
  `has_tone_correction()` and `GlobalCorrection.reset()` (free, via
  dataclass `__init__`)/`has_light_correction()`; both session-persistence
  mechanisms (`_save_session_state`/`_legacy_restore_session` QSettings
  keys `{prefix}exposure`/`g_exposure`, and `_collect_session_data`/
  `_build_restored_items_from_data`'s `.trirgb` JSON key `"exposure"` -
  both read paths default to `0.0` when the key is missing, so old saved
  sessions/files load fine without it); `_extract_settings`/
  `paste_settings_to` (copy/paste); `_sync_global_panel_from_model`/
  `_sync_panel_from_layer` (model → slider) and `on_global_changed`/
  `on_tone_changed` (slider → model); `on_global_reset`/`on_reset_light`
  (explicit per-field resets, alongside the free ones via `reset()`/
  `reset_tone()`). `_snapshot_state`/`_restore_state` (undo/redo) needed
  **no changes** - both already deep-copy the whole `ChannelLayer`/
  `GlobalCorrection` object via `copy.copy()`, so a new dataclass field is
  automatically included. Verified end-to-end headlessly: slider move →
  recompute_preview brightens/darkens correctly, undo/redo, copy/paste,
  `.trirgb` round-trip, and legacy QSettings round-trip all preserve the
  value; reset buttons (`reset_light_btn`/per-channel `reset_tone_button`)
  correctly grey out/light up based on `exposure != 0.0` alongside the
  other fields.
- i18n: `exposure_label` ("Exposure"/"Exposition"), added to both EN/FR.

## Solo (B&W) preview now includes Global "Light" correction (added 2026-09-02)

Raised by the user right after the Exposure slider above: Solo mode
(`ChannelLayer.solo`, toggled via each channel panel's `solo_checkbox` -
isolates that one channel as a B&W preview) used to run **only** that
channel's own tone curve (`ChannelLayer.black_point`/`white_point`/`gamma`/`exposure`/
`brightness`/`contrast`/`shadows`/`highlights`) and completely ignored
`GlobalCorrection` - so toggling Solo made every Global Correction slider
look like a no-op, silently, since the composed-RGB preview (Global
applied) and the Solo preview (Global skipped) disagreed.

- **Fix, in `MainWindow._warp_and_tone`** (the only caller is
  `recompute_preview`'s Solo branch): after computing `toned` from the
  layer's own tone params exactly as before, a **second**
  `imaging.apply_tone_curve` pass now applies `GlobalCorrection`'s own
  black/white/gamma/exposure/brightness/contrast/shadows/highlights on
  top - the exact same "Light" field set `GlobalCorrection.
  has_light_correction()` already tracks, and the same second-tone-curve
  step `apply_global_correction` performs on the composed RGB (this reuses
  `apply_tone_curve` directly rather than `apply_global_correction`,
  specifically to skip its white-balance/saturation portion - deliberately
  excluded per the user's own framing ("les 'light' du moins puisque c'est
  affiché en noir et blanc"): temperature/tint/saturation are color-only
  and meaningless on a single-channel grayscale image, so applying them
  here would do nothing but waste a step, or worse, be misleading if a
  future change to `apply_white_balance` ever made it non-neutral on a
  gray pixel).
- **Compare mode**: mirrors the existing `_compare_active` handling - the
  global side now also substitutes `_NEUTRAL_TONE` in that branch, so
  Solo+Compare together still show the untouched original, same as before
  this fix.
- Verified numerically: Solo's preview mean shifts when Global exposure
  changes (previously it wouldn't have moved at all); cranking Global
  temperature/tint/saturation to extreme values while in Solo produces
  **zero** additional change (confirming the color portion really is
  skipped, not just visually negligible); per-channel exposure on the
  soloed layer itself still stacks on top correctly; Compare mode still
  shows the raw, untouched source.

## Harris Shutter becomes per-channel state (fixed 2026-09-02)

The Harris Shutter section above described it as deliberately **global/
session-level, not a per-photo field** - "read directly off
`harris_shutter_checkbox.isChecked()` everywhere a channel gets loaded."
The user found the real problem with that design: switching between
photos left the checkbox showing whichever state it was last set to,
never reflecting what mode the *currently displayed* photo's channels had
actually been loaded under - and worse, both the full-resolution export
reload (`_full_res_image`) and the relink flow (`_relink_channel`/
`_relink_one_channel_interactively`) read the same **shared, active-photo**
checkbox for *any* layer being processed, including ones from a
completely different, non-active photo (e.g. during a batch export) -
so a batch export could silently reinterpret other photos' channels
under the active photo's mode instead of their own.

- **Fix: `harris_shutter` is now a real `ChannelLayer` field** (`model.py`,
  next to `invert`, same invariant - kept identical across a photo's 3
  channels, toggled uniformly, not something that varies channel-to-channel
  within one photo). This mirrors `invert`'s existing architecture
  deliberately: undo/redo needed **zero changes** since `_snapshot_state`
  already deep-copies every `ChannelLayer` via `copy.copy()`, automatically
  picking up any new field - the same reason the Exposure slider above
  needed no undo-specific wiring either.
- **The shared checkbox now only reflects the *active* photo**, exactly
  like `GlobalPanel.invert_button`/`set_invert()`: a new
  `MainWindow._sync_harris_shutter_checkbox()` reads
  `self.layers[0].harris_shutter` (blockSignals, no re-trigger) and is
  called at the same 5 places `set_invert(self.layers[0].invert)` already
  is - `activate_batch_item`, `paste_settings_to`, `reset_batch_items`,
  `_restore_state` (undo/redo), `_apply_restored_items` (both session-
  restore paths) - so every place that already resyncs per-photo UI on a
  photo switch now resyncs this too, fixing the original bug directly.
- **Every load site now reads the *specific layer's own* field, not the
  shared checkbox**: `_relink_channel`/`_relink_one_channel_interactively`
  (preserves the channel's own existing mode when relinking, instead of
  reinterpreting it under whatever the active photo's checkbox shows) and
  `_full_res_image` (export reload - fixes the batch-export cross-photo
  bug described above) both switched from
  `self.harris_shutter_checkbox.isChecked()` to `layer.harris_shutter`.
  `_load_image_from_path` (a fresh manual single-channel load) still reads
  the live checkbox, but now also stamps `layer.harris_shutter` with it so
  the loaded channel remembers its own mode going forward.
  `import_worker.py`'s `BatchImportWorker._build_item` stamps
  `layer.harris_shutter = self.harris_shutter` on every newly-created
  `ChannelLayer` (the worker already threaded a `harris_shutter` bool
  through from `start_batch_import`'s snapshot of the checkbox at the
  moment Import was clicked - unchanged - it just wasn't being saved onto
  the layers themselves before).
- **Session persistence**: per-channel `{prefix}harris_shutter` in both
  QSettings (`_save_session_state`/`_legacy_restore_session`) and
  `.trirgb` (`_collect_session_data`/`_build_restored_items_from_data`),
  replacing the old single session-wide `harris_shutter_enabled` key/
  `_apply_restored_layout`'s 4th parameter (removed - `_apply_restored_items`
  now syncs the checkbox via `_sync_harris_shutter_checkbox()` instead,
  the same per-photo-scoped place `set_invert()` already lived). **Old
  files/sessions saved before this change still load correctly**: both
  restore paths fall back to the old top-level `harris_shutter_enabled`
  value as the default when a channel's own per-channel key is missing
  (`settings.value(prefix + "harris_shutter", legacy_harris_shutter_default, ...)`
  / `ch.get("harris_shutter", legacy_harris_shutter_default)`) - verified
  with a synthetic old-format `.trirgb` dict lacking the new key.
- **Multi-photo apply, requested in the same message**: "tout comme le
  mode négatif... appliquer à plusieurs photos en même temps" - both
  Harris Shutter and Negative now apply to every currently-selected
  carousel photo at once, falling back to just the active photo if
  nothing is selected. New shared helper `MainWindow._target_batch_indices()`
  (also now used by `on_locate_missing_files`, which had this exact
  selected-or-active-fallback logic inline already) returns that target
  list; `on_invert_toggled` and `on_harris_shutter_toggled` were both
  rewritten around it, replacing their old single-active-photo-only loops.
  **Critical requirement, explicit in the user's message**: a mixed
  selection must **converge on one explicit new state**, never invert
  each photo against its own prior value - i.e. `layer.invert = checked`/
  `layer.harris_shutter = checked` (the checkbox's own new value, applied
  uniformly), never `layer.invert = not layer.invert`. `on_invert_toggled`
  already did this correctly (just scoped to one photo before); the
  rewrite preserves that exact semantic while widening the scope. Both
  handlers finish by re-deriving the button/checkbox's own visual state
  from the *active* photo's actual value (`self.layers[0].invert`/
  `.harris_shutter`) rather than trusting the clicked `checked` value
  blindly - covers the edge case where the active photo isn't part of the
  selection being changed, so the control stays honest either way. One
  `push_undo()` covers the whole batch, same convention as
  `paste_settings_to`/`reset_batch_items`/`on_locate_missing_files`; each
  affected non-active photo's carousel thumbnail is refreshed
  individually, the active one via the usual `recompute_preview()`.
- **Not touched**: `paste_settings_to`'s clipboard (Cmd+C/V, "Paste") still
  excludes `harris_shutter`, same as alignment - both are "specific to
  this photo's own source data," not a portable "look," and copying
  `harris_shutter` would require a silent disk reload as a side effect of
  a paste, which the clipboard mechanism doesn't do for anything else.
  `reset_batch_items` ("Reset All") also doesn't touch it, for the same
  reason: it's the photo's own source-interpretation mode, not a
  "correction" with an obvious reset default, unlike `invert` (which
  *is* explicitly reset there to `False`).
- Verified end-to-end headlessly with real synthetic source images: the
  checkbox now correctly follows the active photo across `activate_batch_item`
  switches; a multi-select toggle with two photos in different starting
  states converges both to the exact new explicit state (checked
  numerically, not just visually) for both Harris Shutter and Negative;
  the pixel data actually changes on disk-reload (not just the flag);
  undo restores both the per-photo flag and the reloaded pixel data
  together; `.trirgb` and legacy QSettings round-trips preserve the
  per-channel value; the old-format-file fallback works; batch import
  stamps the field; and the export path's `_full_res_image` now uses a
  target layer's own mode instead of the active photo's checkbox.

## Changelog (added 2026-09-02, split into EN/FR the same day)

`CHANGELOG_EN.md`/`CHANGELOG_FR.md` are the **user-facing** release
history — what changed and why it matters to someone using the app, in
plain language, as opposed to `CLAUDE.md`'s implementation-level detail
for development. Two parallel files, not one bilingual file - keep both in
sync (same sections, same version boundaries) but write each as natural
prose in its own language rather than a mechanical translation.
`CHANGELOG_EN.pdf`/`CHANGELOG_FR.pdf` are PDF copies regenerated from them
by `scripts/generate_changelog_pdf.py` (`QTextDocument.setMarkdown()` +
`QPrinter` - both already part of PySide6, no new dependency; the script
loops over `LANGUAGES = ("EN", "FR")` so adding a third language later is
a one-line change) - verified visually via `qlmanage -t` (no PDF
text-extraction tool is installed in this environment) that headings/bold/
bullets/page numbers/accented French text all render correctly.

**Workflow - do this whenever the user asks to bump the version and
build** (e.g. "compile this as vX.Y.Z"), *before* touching
`trichrome.spec`:
1. In **both** `CHANGELOG_EN.md` and `CHANGELOG_FR.md`, turn the
   `## Unreleased` section into a new dated version entry
   (`## vX.Y.Z — YYYY-MM-DD`, using today's actual date) - rewrite/tighten
   the wording if needed (the Unreleased entries were written
   incrementally per-feature and may read less cleanly as a single release
   note), keep the "Remaining tasks for future versions" /
   "Tâches restantes pour les prochaines versions" framing for anything
   still open.
2. Leave a fresh, empty `## Unreleased` section at the top of both files
   for whatever comes next.
3. Bump `trichrome.spec` and run `./build_mac.sh` as usual -
   `generate_changelog_pdf.py` runs automatically as its last step now, so
   both PDFs are regenerated from the files you just edited, in sync with
   the `.app` they ship alongside. Don't run `generate_changelog_pdf.py`
   by hand as a separate step; it's part of the build now.
4. Commit the changes (git repo at the project root, GitHub remote
   `origin` since 2026-09-03) - a version-bump/build request implicitly
   includes committing afterward, no need to ask each time. Message
   convention: `"vX.Y.Z"` as the summary line. **Commit only - do not
   `git push` unless the user explicitly asks for that too** in the same
   or a later message; pushing is a separate, explicit action.

**Unlike `CLAUDE.md` (updated after nearly every substantial change), do
NOT touch these two files incrementally after each feature/fix - that was
tried and the user asked to stop (2026-09-02: "pour gagner de la
ressource" - it burns turns/tokens on every change for no benefit before a
release exists to read it). Leave `## Unreleased` alone between bumps and
reconstruct it from the conversation in one pass, only when the user
actually asks to bump the version and build** - i.e. do step 1 above by
looking back over what's shipped since the last version, not by having
kept a running tally. Both languages get written in that same single pass
(not just English incrementally with French deferred) - there's no
benefit to writing the English half early either, since neither is read
until a release happens. Don't let a version release with an empty or
stale changelog, but "stale" only starts to matter right before a bump,
not between them.

## Testing

The user runs the built app manually after each change and does their own
testing pass — **don't write throwaway verification test scripts by
default**. Reach for a quick headless script only when a change is genuinely
non-visual/hard-to-eyeball (e.g. verifying a coordinate-transform or
persistence round-trip), and keep it minimal. When you do:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -c "..."
```

Always isolate `QSettings` so tests never read/write the user's real saved
session - monkeypatch the **module-level** `trichrome.main_window.ORG_NAME`/
`.APP_NAME` (e.g. `mwmod.ORG_NAME = mwmod.APP_NAME = "SomeIsolatedName"`),
**not** `mw.ORG_NAME`/`MainWindow.ORG_NAME` - see the full incident writeup
under the session-persistence section above (a class/instance-attribute
patch is silently a no-op here and once actually corrupted the user's real
saved Layout Presets during testing). Verify isolation actually held by
reading back through `QSettings(mwmod.ORG_NAME, mwmod.APP_NAME)` rather
than assuming the patch landed on the right target.

## Language

The user writes in French; reply in English regardless of the language they use.
