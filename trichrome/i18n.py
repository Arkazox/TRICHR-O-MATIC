"""Minimal runtime i18n: a flat string table per language plus a tr() lookup.

The current language is a module-level variable so any widget can call
tr(key) at any time; widgets that must reflect a language change without an
app restart implement a retranslate_ui() method that main_window calls.
"""
from __future__ import annotations

DEFAULT_LANGUAGE = "en"

EN = {
    "channel_r": "Red",
    "channel_g": "Green",
    "channel_b": "Blue",

    "panel_title": "{channel} Layer",
    "load_image_button": "Load an image…",
    "no_image_loaded": "No image loaded",
    "active_checkbox": "Active (edit on canvas)",
    "active_layer_info": "The active channel is the one that reacts to dragging and "
                          "scrolling directly on the preview canvas. Only one channel can "
                          "be active at a time - check Active on a different channel to "
                          "switch. Locking a channel (see Lock layer position) only "
                          "excludes it from Auto Align; it can still be made active and "
                          "repositioned manually. Drag to move it, Shift+scroll to scale "
                          "it, Alt/Option+scroll to rotate it.",
    "solo_checkbox": "Solo (B&W preview)",
    "invert_checkbox_tooltip": "Negative (invert scan) — inverts the tones of all 3 channels, for raw, uninverted negative scans.",
    "alignment_group": "Alignment",
    "offset_x": "Offset X",
    "offset_y": "Offset Y",
    "scale_label": "Scale",
    "rotation_label": "Rotation (°)",
    "auto_align_button": "Auto align",
    "reset_button": "Reset",
    "tone_group": "Light",
    "black_point": "Blacks",
    "white_point": "Whites",
    "shadows_label": "Shadows",
    "highlights_label": "Highlights",
    "gamma_label": "Gamma",
    "exposure_label": "Exposure",
    "brightness_label": "Brightness",
    "contrast_label": "Contrast",

    "global_light_subheader": "Light",
    "global_color_subheader": "Color",
    "global_scope_info": "For a trichrome image, these changes apply to the recomposed color image.",
    "channels_scope_info": "Edits the Black & White images of the RGB channels separately. These changes apply before the Light and Color adjustments.",
    "crop_group_title": "Crop",
    "crop_aspect_ratio_label": "Aspect",
    "crop_ratio_original": "Original",
    "crop_ratio_free": "Free",
    "crop_ratio_custom": "Custom",
    "crop_invert_orientation_button": "Invert Orientation",
    "crop_straighten_label": "Straighten",
    "crop_mirror_h_button": "Mirror Left/Right",
    "crop_mirror_v_button": "Mirror Top/Bottom",
    "crop_grid_label": "Grid:",
    "crop_grid_off": "Off",
    "crop_grid_3x3": "3 × 3",
    "crop_grid_2x2": "2 × 2",
    "crop_grid_golden": "Golden Ratio",
    "crop_grid_squares": "Grid",
    "crop_apply_hint": "Press Enter to apply the crop",
    "crop_reset_tooltip": "Reset crop",
    "crop_activate_tooltip": "Activate Crop mode",
    "saturation_label": "Saturation",
    "temperature_label": "Temperature",
    "tint_label": "Tint",
    "export_button": "Export…",

    "zoom_in": "Zoom In",
    "zoom_out": "Zoom Out",
    "zoom_fit_tooltip": "Fit to window (F)",
    "zoom_100": "100% (Real Size) (Z)",
    "rotate_left_tooltip": "Rotate left (⌘L)",
    "rotate_right_tooltip": "Rotate right (⌘R)",
    "fullscreen_button": "Fullscreen (⌘F)",
    "exit_fullscreen_button": "Exit fullscreen (⌘F)",
    "compare_tooltip": "Compare (:)",
    "compare_indicator_label": "Displaying original",
    "session_saved_status": "Session Saved",
    "status_saving_session": "Saving session…",
    "status_loading_session": "Loading session…",
    "session_untitled_label": "Untitled Session",
    "session_open_prefix": "Session opened: ",
    "menu_new_session": "New Session",
    "dialog_quit_unsaved_title": "Unsaved Changes",
    "dialog_quit_unsaved_text": "This session has unsaved changes. Do you want to save them?",
    "dialog_quit_save_button": "Save",
    "dialog_quit_discard_button": "Don't Save",
    "dialog_quit_cancel_button": "Cancel",
    "import_toolbar_tooltip": "Import Images (⌘I)",
    "left_panel_toggle_tooltip": "Show/hide left panel",
    "save_session_toolbar_tooltip": "Save Session (⌘S)",
    "menu_open_session": "Open Session…",
    "menu_save_session": "Save Session",
    "menu_save_session_as": "Save Session As…",
    "export_toolbar_tooltip": "Export (⌘E)",
    "trichrome_toolbar_tooltip": "Trichrome (T)",
    "settings_toolbar_tooltip": "Color Correction (E)",
    "crop_toolbar_tooltip": "Crop (C)",
    "scan_toolbar_tooltip": "Scan (S)",
    "right_panel_toggle_tooltip": "Show/hide right panel",
    "help_toolbar_tooltip": "Help (F1)",
    "scan_panel_placeholder": "Scan tool integration is coming soon.",
    "canvas_placeholder": "Load the 3 images (R, G, B) to see the preview",
    "missing_files_banner_text": "The original source file(s) for this photo could not be found:",
    "missing_files_locate_button": "Locate…",
    "missing_files_locate_tooltip": "Pick the folder these files were moved to - Trichr-o-matic will look for files with the same name inside it, for every missing channel across the current selection.",
    "missing_files_locate_dialog_title": "Locate Moved Files",
    "missing_files_relink_dialog_title": "Select Replacement File",
    "missing_files_relink_button": "Relink…",
    "missing_files_locate_success": "Relinked {count} file(s)",
    "dialog_locate_failed_title": "Some files could not be relinked",
    "dialog_locate_failed_text": (
        "Trichr-o-matic couldn't find a matching file in that folder for the "
        "photo(s)/channel(s) listed below.\n\n"
        "Try again and pick a different folder - or, if these files were "
        "renamed rather than just moved, reimport them one by one for the "
        "affected photo(s) using the RGB Channels panel on the left."
    ),
    "dialog_locate_failed_column_photo": "Photo",
    "dialog_locate_failed_column_channel": "Channel",

    "pick_white_balance_tooltip": "Pick White Balance - click a point in the preview that should be neutral gray",
    "reset_white_balance_tooltip": "Reset Color (Temperature, Tint, Saturation)",
    "reset_light_tooltip": "Reset Light (Brightness, Contrast, Highlights, Shadows, Whites, Blacks, Gamma)",
    "white_balance_picked": "White balance set from the picked point",
    "histogram_pick_tooltip": "Pick Pixel Value - hover the preview to mark that pixel's tone on the histogram",
    "white_balance_pick_failed": "Couldn't set white balance from that point (too dark)",

    "menu_file": "File",
    "menu_load_channel": "Load the {channel} image…",
    "menu_quit": "Quit",
    "menu_edit": "Edit",
    "menu_undo": "Undo",
    "menu_redo": "Redo",
    "menu_edit_copy": "Copy",
    "menu_edit_paste": "Paste",
    "menu_paste_crop": "Paste Crop",
    "menu_edit_rotate_right": "Rotate Right",
    "menu_edit_rotate_left": "Rotate Left",
    "menu_edit_delete": "Delete Selection",
    "menu_reset_all": "Reset All",
    "menu_duplicate": "Duplicate",
    "menu_language": "Language",
    "menu_tools": "Tools",
    "menu_tools_crop": "Crop",
    "menu_tools_scan": "Scan",
    "menu_window": "Window",
    "menu_window_close": "Close Window",
    "menu_window_left_panel": "Left Panel",
    "menu_window_right_panel": "Right Panel",
    "menu_window_thumbnails": "Thumbnails",
    "menu_window_reset_layout": "Reset Layout",
    "menu_window_layout_prefix": "Layout - ",
    "menu_window_layout_trichrome": "Trichrome",
    "menu_window_layout_color_correction": "Color Correction",
    "menu_window_layout_crop": "Crop",
    "menu_window_layout_scan": "Scan",
    "menu_window_layout_preset": "Layout Preset",
    "menu_window_save_layout_preset": "Save Layout as Preset…",
    "layout_preset_save_dialog_title": "Save Layout as Preset",
    "layout_preset_name_prompt": "Preset name:",
    "layout_preset_load": "Load",
    "layout_preset_update": "Update",
    "layout_preset_delete": "Delete Preset",
    "layout_preset_builtin_name_title": "Reserved Preset Name",
    "layout_preset_builtin_name_text": "\"{name}\" is one of the 4 built-in default layouts and can't be overwritten. Choose a different name for your custom preset.",
    "menu_help": "Help",
    "menu_quickstart_action": "Quick Start",
    "menu_shortcuts_action": "Shortcuts",
    "menu_batch": "Import Images…",
    "double_click_reset_hint": "Double-click to reset",

    "independent_channels_group_title": "RGB Channels",
    "import_panel_title": "Files",
    "block_collapse_tooltip": "Collapse/Expand",
    "block_close_tooltip": "Remove from view",
    "menu_tools_histogram": "Histogram",
    "reset_all_alignment_tooltip": "Reset alignment for all channels",
    "reset_all_color_tooltip": "Reset color for all channels",
    "harris_shutter_checkbox": "Harris Shutter Effect (Color Source Image)",
    "harris_shutter_info": (
        "<b>Off (default)</b><br>"
        "<span style=\"color:#9a9a9a;\">Classic Trichrome Mode: combines 3 black &amp; white photos "
        "to recompose a color image</span>"
        "<br><br>"
        "<b>On</b><br>"
        "<span style=\"color:#9a9a9a;\">Color Mode: simulates RGB filters from 3 color photos to "
        "create a &quot;Harris Shutter Effect&quot;</span>"
    ),
    "lock_layer_position_label": "Lock layer position:",
    "lock_layer_position_info": "Auto Align never moves the locked channel - it aligns the other "
                                 "two onto it instead, keeping whatever manual position you've set. "
                                 "You can still edit the locked channel's own alignment by hand. "
                                 "Exactly one channel is always locked; pick a different one anytime.",

    "batch_window_title": "Import",
    "batch_import_button": "Import",
    "batch_import_status_running": "Importing {i} / {n}…",
    "batch_import_status_done": "{n} photo(s) imported.",
    "carousel_empty_hint": "No photos imported yet — use the “Import…” button at the top of the sidebar.",
    "carousel_toggle_tooltip": "Show/hide thumbnails",
    "sort_button_tooltip": "Sort thumbnails",
    "sort_by_filename": "By Filename",
    "sort_by_capture_date": "By Capture Date",
    "sort_by_import_order": "By Import Order",
    "sort_by_custom": "Custom Order",
    "sort_reverse_order": "Reverse Order",
    "export_scope_group": "What to export",
    "export_scope_current": "Export current photo",
    "export_scope_selected": "Export selected ({n})",
    "export_scope_all": "Export all ({n})",
    "export_confirm_button": "Export",
    "export_no_items": "No photo to export.",
    "close_button": "Close",
    "batch_mode_auto_radio": "Automatic",
    "batch_mode_semi_radio": "Semi-automatic",
    "batch_mode_manual_radio": "Manual",
    "batch_mode_info": (
        "<b>Automatic</b> — files are grouped by a filter marker found in their name (Red, Green, "
        "Blue, Yellow or Infrared - any position, case-insensitive). Which filter fills which R/G/B "
        "channel depends on the mode picked in <b>Advanced Options</b> below (Classic, IR Trichrome, "
        "Aerochrome…). Files sharing an identical name once that marker is removed form one triplet; "
        "otherwise, a plain numbered sequence (Image1, Image2, Image3…) is grouped 3 relevant files "
        "at a time, in order.<br><br>"
        "<b>Semi-automatic</b> — select a batch of images at once, already in R, G, B, R, G, B… "
        "order (drag to reorder if needed): the first 3 form one triplet, the next 3 the next one, "
        "and so on.<br><br>"
        "<b>Manual</b> — pick the files for the R, G and B columns independently, useful when "
        "filenames don't follow any pattern at all. Row N of each column forms one triplet."
    ),
    "batch_advanced_options_title": "Advanced Options",
    "batch_advanced_mode_classic": "Classic Trichrome",
    "batch_advanced_mode_ir": "IR Trichrome",
    "batch_advanced_mode_aerochrome": "Aerochrome",
    "batch_advanced_mode_custom": "Custom",
    "filter_yellow": "Yellow",
    "filter_infrared": "Infrared",
    "batch_channel_mapping_title": "Channel Mapping",
    "batch_filters_title": "Camera Filters",
    "batch_filters_name_header": "Name",
    "batch_filters_tokens_header": "Keywords",
    "batch_filters_hint": ("Keywords are comma-separated and case-insensitive. Built-in filters can't "
                            "be removed, but their name and keywords can be edited."),
    "batch_filters_add_button": "Add Custom Filter",
    "batch_filters_new_name_placeholder": "New Filter",
    "batch_filters_delete_tooltip": "Delete this filter",

    "batch_semi_select_button": "Select images…",
    "batch_semi_hint": ("Files are grouped 3 at a time, in the order shown, as R, G, B — drag to "
                         "reorder."),
    "batch_semi_invalid_count": "{n} files selected — not a multiple of 3 ({remainder} extra file(s) will be ignored).",
    "batch_semi_select_title": "Select images (in R, G, B order)",
    "batch_manual_add_button": "Add files…",
    "batch_manual_remove_button": "Remove selected",
    "batch_manual_clear_button": "Clear",
    "batch_manual_hint": ("Drop image files onto a column to add them, or drag items within a column "
                           "to reorder them — row N of each column forms one triplet."),
    "batch_manual_mismatch_warning": "Columns have different counts (R: {r}, G: {g}, B: {b}) — only the first {n} will be paired.",
    "batch_select_files_title": "Select the {channel} images",
    "batch_input_group": "Input folder",
    "batch_browse_button": "Browse…",
    "batch_rescan_button": "Rescan",
    "batch_no_folder": "No folder selected",
    "batch_select_input_title": "Select the input folder",
    "batch_select_output_title": "Select the output folder",
    "batch_triplets_found": "{n} matched triplets",
    "batch_unmatched_label": "{n} unmatched files (ignored):",
    "batch_align_auto_checkbox": ("Auto-align each image individually (otherwise, layers stay at "
                                   "their default position)"),
    "batch_output_folder_label": "Output folder:",
    "export_same_as_source": "Source folder",
    "export_same_as_source_tooltip": ("Save each exported photo next to its own source file, instead of "
                                       "one shared folder — useful when the photos being exported come "
                                       "from different folders."),
    "export_reveal_in_finder": "Show in Finder after export",
    "batch_suffix_label": "Filename suffix:",
    "batch_format_label": "Format:",
    "batch_cancel_button": "Cancel",
    "batch_status_no_triplets": "No matched triplets found in this folder.",
    "batch_status_running": "Processing {i} / {n}…",
    "batch_status_done": "Done — {ok} succeeded, {failed} failed",
    "batch_status_cancelled": "Cancelled after {i} / {n}",
    "batch_error_no_input": "Select an input folder first.",
    "batch_error_no_output": "Select an output folder.",

    "status_auto_align_running_all": "Auto-aligning all channels…",
    "status_auto_align_all_done": "Auto-alignment complete.",
    "status_auto_align_failed": "Automatic alignment failed.",
    "status_exported": "Image exported: {path}",
    "status_settings_copied": "Settings copied",
    "status_settings_pasted": "Settings pasted to {n} photo(s)",
    "status_crop_pasted": "Crop pasted to {n} photo(s)",
    "status_photos_deleted": "{n} photo(s) deleted",
    "status_photos_reset": "{n} photo(s) reset",
    "status_photo_duplicated": "Photo duplicated",
    "status_crop_applied": "Crop applied",

    "dialog_load_error_title": "Loading error",
    "dialog_load_error_text": "Could not load the image:\n{error}",
    "dialog_session_load_error_title": "Session error",
    "dialog_session_load_error_text": "Could not open the session file:\n{error}",
    "dialog_session_load_empty": "This session file doesn't contain any photo that could still be loaded.",
    "dialog_alignment_title": "Alignment",
    "dialog_alignment_missing_images": "Load the reference image and this channel first.",
    "dialog_auto_align_title": "Automatic alignment",
    "dialog_auto_align_failed_channels": "Automatic alignment failed for: {channels}.\nTry a manual alignment instead.",
    "dialog_export_missing": "Load all 3 images (Red, Green, Blue) before exporting.",
    "dialog_export_error_title": "Export error",
    "dialog_export_error_text": "Could not save the image:\n{error}",

    "file_filter_all": "All files (*.*)",
    "load_dialog_title": "Load the {channel} image",
    "export_dialog_title": "Export the trichrome image",
    "export_filter_png": "8-bit PNG (*.png)",
    "export_filter_jpg": "8-bit JPEG (*.jpg)",
    "export_filter_tiff": "16-bit TIFF (*.tiff)",

    "help_quickstart_title": "Quick Start",
    "help_quickstart_content": """
<h3>Simple mode (one photo)</h3>
<ol>
<li>Load the Red, Green and Blue shots from the <b>Current Picture</b> panel on the
left (or the File menu).</li>
<li>As soon as all three are loaded, the other two channels are <b>auto-aligned</b>
against the locked channel automatically (or click <b>Auto Align</b> in the
<b>Current Picture</b> panel to redo it anytime).</li>
<li>Pick a different locked channel anytime with the <b>R / G / B</b> buttons under
<b>Lock layer position</b>, in the <b>Current Picture</b> panel — it defines the canvas
size and orientation (Green by default).</li>
<li>Fine-tune alignment and color correction per channel (left), and the overall look —
including <b>Negative</b>, <b>Highlights/Shadows/Whites/Blacks</b> and
<b>Temperature/Tint</b> — in <b>Global Correction</b> (right). The small icon
buttons at the bottom of each panel reset just that part (hover them for details).</li>
<li>Click <b>Export…</b> to choose an output folder/format and save the result.</li>
</ol>
<h3>Batch mode (many photos)</h3>
<ol>
<li>Click the <b>Import…</b> button at the top of the sidebar (or press Cmd+I).</li>
<li>Pick how files are matched: <b>Automatic</b> (by filename), <b>Semi-automatic</b>
(select files already in R, G, B order), or <b>Manual</b> (pick each column yourself) —
click the <b>?</b> on the right for the difference between them.</li>
<li>Check <b>Auto-align each image</b> to have every photo aligned individually on import
(otherwise its layers stay at their default position), then click <b>Import</b> — the
new photos are added after the current selection (remove unwanted ones from the
Filmstrip anytime with Cmd+Delete).</li>
<li>The photos appear in a <b>Filmstrip</b> under the preview (it shows itself
automatically once there's more than one photo). Click a thumbnail (or use
<b>←/→</b>) to edit that photo's alignment and color independently of the others.</li>
<li>Build a selection with <b>Cmd+click</b> or <b>Cmd+A</b>, then use
<b>Export…</b> (Cmd+E) to export the <i>current</i>, <i>selected</i>, or
<i>all</i> photos at once.</li>
<li>Right-click a thumbnail for <b>Copy</b> / <b>Paste</b> / <b>Reset All</b> /
<b>Duplicate</b> / <b>Delete</b> (Copy/Paste/Delete are also Cmd+C / Cmd+V /
Cmd+Delete). <b>Reset All</b> clears that photo's alignment, color and negative back
to defaults; <b>Duplicate</b> makes a numbered copy — e.g. “(2)” — to try a
different edit side by side.</li>
</ol>
<h3>Sessions</h3>
<ul>
<li>Everything you're working on — every imported photo and its settings — is one
<b>session</b>. <b>File ▸ Save Session</b> (Cmd+S) writes it to a portable
<b>.trirgb</b> file you can reopen later or move to another machine;
<b>Save Session As…</b> (Cmd+Shift+S) saves a copy under a new name.</li>
<li><b>File ▸ Open Session…</b> (Cmd+O) loads one back; <b>New Session</b> (Cmd+N)
starts over with a single blank photo.</li>
<li>Relaunching the app automatically reopens whichever session file you had open
last, so you pick up right where you left off.</li>
<li>The current session's name is shown at the bottom-right of the status bar. With
unsaved changes, closing the app, opening another session, or starting a new one
will ask whether to save first.</li>
</ul>
<h3>Other</h3>
<ul>
<li>The preview opens at <b>fit-to-window</b> zoom automatically, on launch and after
every import.</li>
<li>The small arrow-and-squares button next to <b>Fullscreen</b> shows or hides the
Filmstrip.</li>
<li>The <b>Fullscreen</b> button (Cmd+F) hides the side panels for a distraction-free
preview (press Esc to leave).</li>
<li>Almost every change can be undone with <b>Cmd+Z</b> (<b>Cmd+Shift+Z</b> to redo).</li>
</ul>
""",

    "help_shortcuts_title": "Shortcuts",
    "help_shortcuts_content": """
<h3>General</h3>
<ul>
<li><b>Cmd+N</b> — New Session</li>
<li><b>Cmd+O</b> — Open Session</li>
<li><b>Cmd+S</b> — Save Session</li>
<li><b>Cmd+Shift+S</b> — Save Session As</li>
<li><b>Cmd+I</b> — Import menu</li>
<li><b>Cmd+E</b> — Export (Enter/Return in that window starts the export)</li>
<li><b>Cmd+Z</b> / <b>Cmd+Shift+Z</b> — Undo / Redo</li>
<li><b>Cmd+R</b> / <b>Cmd+L</b> — rotate the current photo 90° right/left</li>
<li><b>E</b> — show Global Correction</li>
<li><b>C</b> — show the Crop tool</li>
<li><b>Cmd+F</b> — toggle fullscreen (Esc to exit)</li>
<li><b>F1</b> — Quick Start</li>
<li><b>Cmd+Q</b> — quit</li>
</ul>
<h3>Navigation</h3>
<ul>
<li><b>←</b> / <b>→</b> — go to the previous/next photo (hold <b>Shift</b> to extend
the export selection instead)</li>
<li><b>Drag</b> a thumbnail — reorders photos (switches to Custom sort order)</li>
<li><b>Cmd+click</b> a thumbnail — add/remove it from the export selection</li>
<li><b>Cmd+A</b> — select all photos, or deselect all if every photo is already
selected</li>
<li><b>Cmd+C</b> / <b>Cmd+V</b> — copy the current photo's settings, paste them onto
the selected photos</li>
<li><b>Cmd+Delete</b> — remove the selected photo(s)</li>
</ul>
<h3>Preview</h3>
<p>The <i>active</i> channel is the one that reacts to dragging and scrolling
directly on the preview.</p>
<ul>
<li><b>Drag</b> — moves the active channel</li>
<li><b>Shift + scroll</b> — scales the active channel</li>
<li><b>Alt/Option + scroll</b> — rotates the active channel</li>
<li><b>Ctrl + scroll</b>, or a trackpad <b>pinch</b> — zooms the preview</li>
<li><b>Two-finger scroll</b> on the trackpad — pans the preview once zoomed in</li>
<li><b>F</b> / <b>Z</b> — jump to Fit / 100% zoom (or use the toolbar buttons)</li>
<li><b>:</b> — toggle Compare, showing the unedited original</li>
</ul>
<h3>Sliders</h3>
<ul>
<li><b>Double-click</b> any slider — resets it to its default value</li>
</ul>
""",

    # --- Scan tool (standalone test window, v0.5.0 direction) ---
    "scan_window_title": "Scan Tool (test)",
    "scan_device_group": "Device",
    "scan_device_not_connected": "Not connected",
    "scan_device_connected": "Connected: {model}",
    "scan_device_refresh": "Refresh",
    "scan_mode_group": "Mode",
    "scan_mode_bw": "Black & White",
    "scan_mode_color": "Color",
    "scan_mode_color_reversal": "Color Reversal",
    "scan_mode_invert_note": "Invert will be applied automatically on import for this mode.",
    "scan_mode_no_invert_note": "No invert needed on import for this mode (already positive).",
    "scan_light_group": "Scan Light",
    "scan_light_external": "External Light",
    "scan_light_white": "White Light",
    "scan_light_rgb": "RGB Light",
    "scan_light_rgb_note": "Capture will automatically take 3 shots in sequence - red, green, then blue light - and return to white light afterward. All 3 share the same number, suffixed _R/_G/_B.",
    "scan_light_window_title": "Scan Backlight",
    "scan_capturing_channel_status": "Capturing {channel}…",
    "scan_process_checkbox": "Also save a processed JPG preview",
    "scan_process_tooltip": "Saves an extra JPG copy in a \"processed\" subfolder: grayscale + inverted for Black & White, inverted for Color, as-is for Color Reversal. For an RGB Light triplet, recomposes the 3 shots into one trichrome image using the app's own auto-align + compose algorithm.",
    "scan_processing_status": "Processing…",
    "scan_processed_label": "Processed",
    "scan_location_group": "Save Location",
    "scan_base_folder_label": "Folder",
    "scan_base_folder_browse": "Browse…",
    "scan_subfolder_label": "Subfolder",
    "scan_use_roll_as_subfolder": "Use roll name as subfolder",
    "scan_subfolder_preview": "Will save to: {name}",
    "scan_roll_name_label": "Roll name",
    "scan_next_number_label": "Next number",
    "scan_quality_label": "Format",
    "scan_quality_unavailable": "Not exposed by this camera",
    "scan_capture_button": "Capture",
    "scan_capturing_status": "Capturing…",
    "scan_ready_status": "Ready.",
    "scan_history_group": "Captured this session",
    "scan_add_to_session_button": "Add to Current Session",
    "scan_error_title": "Scan Error",
    "scan_no_camera_error": "No camera selected or connected.",
}

FR = {
    "channel_r": "Rouge",
    "channel_g": "Vert",
    "channel_b": "Bleu",

    "panel_title": "Calque {channel}",
    "load_image_button": "Charger une image…",
    "no_image_loaded": "Aucune image chargée",
    "active_checkbox": "Actif (édition sur le canevas)",
    "active_layer_info": "Le calque actif est celui qui réagit quand on glisse ou "
                          "qu'on utilise la molette directement sur le canevas de "
                          "l'aperçu. Un seul calque peut être actif à la fois - cochez "
                          "Actif sur un autre calque pour changer. Verrouiller un "
                          "calque (voir Position verrouillée) l'exclut seulement de "
                          "l'alignement automatique ; il peut toujours être rendu actif "
                          "et repositionné manuellement. Glissez pour le déplacer, "
                          "Maj+molette pour le mettre à l'échelle, Alt+molette pour le "
                          "faire pivoter.",
    "solo_checkbox": "Solo (aperçu N&B)",
    "invert_checkbox_tooltip": "Négatif (inverser le scan) — inverse les tons des 3 calques, pour des scans de négatif brut, non inversés.",
    "alignment_group": "Alignement",
    "offset_x": "Décalage X",
    "offset_y": "Décalage Y",
    "scale_label": "Échelle",
    "rotation_label": "Rotation (°)",
    "auto_align_button": "Alignement automatique",
    "reset_button": "Réinitialiser",
    "tone_group": "Lumière",
    "black_point": "Noirs",
    "white_point": "Blancs",
    "shadows_label": "Ombres",
    "highlights_label": "Hautes lumières",
    "gamma_label": "Gamma",
    "exposure_label": "Exposition",
    "brightness_label": "Luminosité",
    "contrast_label": "Contraste",

    "global_light_subheader": "Lumière",
    "global_color_subheader": "Couleur",
    "global_scope_info": "Dans le cas d'une image trichrome, ces changements s'appliquent sur l'image couleur recomposée.",
    "channels_scope_info": "Modifie séparément les images Noir et Blanc des canaux RVB. Ces changements s'appliquent avant les réglages de lumière et de couleur.",
    "crop_group_title": "Recadrage",
    "crop_aspect_ratio_label": "Aspect",
    "crop_ratio_original": "Original",
    "crop_ratio_free": "Libre",
    "crop_ratio_custom": "Personnalisé",
    "crop_invert_orientation_button": "Inverser l'orientation",
    "crop_straighten_label": "Désincliner",
    "crop_mirror_h_button": "Miroir gauche/droite",
    "crop_mirror_v_button": "Miroir haut/bas",
    "crop_grid_label": "Grille :",
    "crop_grid_off": "Aucune",
    "crop_grid_3x3": "3 × 3",
    "crop_grid_2x2": "2 × 2",
    "crop_grid_golden": "Nombre d'or",
    "crop_grid_squares": "Grille",
    "crop_apply_hint": "Appuyez sur Entrée pour appliquer le recadrage",
    "crop_reset_tooltip": "Réinitialiser le recadrage",
    "crop_activate_tooltip": "Activer le mode Recadrage",
    "saturation_label": "Saturation",
    "temperature_label": "Température",
    "tint_label": "Teinte (magenta/vert)",
    "export_button": "Exporter…",

    "zoom_in": "Zoom avant",
    "zoom_out": "Zoom arrière",
    "zoom_fit_tooltip": "Ajuster à la fenêtre (F)",
    "zoom_100": "100 % (taille réelle) (Z)",
    "rotate_left_tooltip": "Rotation à gauche (⌘L)",
    "rotate_right_tooltip": "Rotation à droite (⌘R)",
    "fullscreen_button": "Plein écran (⌘F)",
    "exit_fullscreen_button": "Quitter le plein écran (⌘F)",
    "compare_tooltip": "Comparer (:)",
    "compare_indicator_label": "Affichage de l'original",
    "session_saved_status": "Session enregistrée",
    "status_saving_session": "Sauvegarde de la session en cours…",
    "status_loading_session": "Import de la session en cours…",
    "session_untitled_label": "Session sans titre",
    "session_open_prefix": "Session ouverte : ",
    "menu_new_session": "Nouvelle session",
    "dialog_quit_unsaved_title": "Modifications non enregistrées",
    "dialog_quit_unsaved_text": "Cette session contient des modifications non enregistrées. Voulez-vous les enregistrer ?",
    "dialog_quit_save_button": "Enregistrer",
    "dialog_quit_discard_button": "Ne pas enregistrer",
    "dialog_quit_cancel_button": "Annuler",
    "import_toolbar_tooltip": "Importer des images (⌘I)",
    "left_panel_toggle_tooltip": "Afficher/masquer le panneau de gauche",
    "save_session_toolbar_tooltip": "Enregistrer la session (⌘S)",
    "menu_open_session": "Ouvrir une session…",
    "menu_save_session": "Enregistrer la session",
    "menu_save_session_as": "Enregistrer la session sous…",
    "export_toolbar_tooltip": "Exporter (⌘E)",
    "trichrome_toolbar_tooltip": "Trichromie (T)",
    "settings_toolbar_tooltip": "Correction Couleur (E)",
    "crop_toolbar_tooltip": "Recadrer (C)",
    "scan_toolbar_tooltip": "Scan (S)",
    "right_panel_toggle_tooltip": "Afficher/masquer le panneau de droite",
    "help_toolbar_tooltip": "Aide (F1)",
    "scan_panel_placeholder": "L'intégration de l'outil de scan arrive bientôt.",
    "canvas_placeholder": "Chargez les 3 images (R, V, B) pour voir l'aperçu",
    "missing_files_banner_text": "Le(s) fichier(s) source d'origine de cette photo sont introuvables :",
    "missing_files_locate_button": "Localiser…",
    "missing_files_locate_tooltip": "Choisissez le dossier où ces fichiers ont été déplacés - Trichr-o-matic y recherchera les fichiers portant le même nom, pour chaque canal manquant de la sélection actuelle.",
    "missing_files_locate_dialog_title": "Localiser les fichiers déplacés",
    "missing_files_relink_dialog_title": "Sélectionner le fichier de remplacement",
    "missing_files_relink_button": "Relier…",
    "missing_files_locate_success": "{count} fichier(s) relié(s)",
    "dialog_locate_failed_title": "Certains fichiers n'ont pas pu être reliés",
    "dialog_locate_failed_text": (
        "Trichr-o-matic n'a trouvé aucun fichier correspondant dans ce dossier "
        "pour la ou les photos/canaux listés ci-dessous.\n\n"
        "Réessayez en choisissant un autre dossier - ou, si ces fichiers ont "
        "été renommés (et pas seulement déplacés), réimportez-les un par un "
        "pour la ou les photos concernées, depuis le panneau Canaux RVB "
        "à gauche."
    ),
    "dialog_locate_failed_column_photo": "Photo",
    "dialog_locate_failed_column_channel": "Canal",

    "pick_white_balance_tooltip": "Balance des blancs à la pipette - cliquez un point de l'aperçu qui devrait être gris neutre",
    "reset_white_balance_tooltip": "Réinitialiser la couleur (Température, Teinte, Saturation)",
    "reset_light_tooltip": "Réinitialiser la lumière (Luminosité, Contraste, Hautes lumières, Ombres, Blancs, Noirs, Gamma)",
    "white_balance_picked": "Balance des blancs réglée à partir du point sélectionné",
    "histogram_pick_tooltip": "Lire une valeur à la pipette - survolez l'aperçu pour repérer le ton de ce pixel sur l'histogramme",
    "white_balance_pick_failed": "Impossible de régler la balance des blancs à partir de ce point (trop sombre)",

    "menu_file": "Fichier",
    "menu_load_channel": "Charger l'image {channel}…",
    "menu_quit": "Quitter",
    "menu_edit": "Édition",
    "menu_undo": "Annuler",
    "menu_redo": "Rétablir",
    "menu_edit_copy": "Copier",
    "menu_edit_paste": "Coller",
    "menu_paste_crop": "Coller le recadrage",
    "menu_edit_rotate_right": "Rotation à droite",
    "menu_edit_rotate_left": "Rotation à gauche",
    "menu_edit_delete": "Supprimer la sélection",
    "menu_reset_all": "Tout réinitialiser",
    "menu_duplicate": "Dupliquer",
    "menu_language": "Langue",
    "menu_tools": "Outils",
    "menu_tools_crop": "Recadrer",
    "menu_tools_scan": "Scan",
    "menu_window": "Fenêtre",
    "menu_window_close": "Fermer la fenêtre",
    "menu_window_left_panel": "Panneau de gauche",
    "menu_window_right_panel": "Panneau de droite",
    "menu_window_thumbnails": "Vignettes",
    "menu_window_reset_layout": "Réinitialiser la disposition",
    "menu_window_layout_prefix": "Disposition - ",
    "menu_window_layout_trichrome": "Trichromie",
    "menu_window_layout_color_correction": "Correction Couleur",
    "menu_window_layout_crop": "Recadrage",
    "menu_window_layout_scan": "Scan",
    "menu_window_layout_preset": "Préréglage de disposition",
    "menu_window_save_layout_preset": "Enregistrer la disposition comme préréglage…",
    "layout_preset_save_dialog_title": "Enregistrer la disposition comme préréglage",
    "layout_preset_name_prompt": "Nom du préréglage :",
    "layout_preset_load": "Charger",
    "layout_preset_update": "Mettre à jour",
    "layout_preset_delete": "Supprimer le préréglage",
    "layout_preset_builtin_name_title": "Nom de préréglage réservé",
    "layout_preset_builtin_name_text": "« {name} » est l'une des 4 dispositions par défaut intégrées et ne peut pas être écrasée. Choisissez un autre nom pour votre préréglage personnalisé.",
    "menu_help": "Aide",
    "menu_quickstart_action": "Prise en main",
    "menu_shortcuts_action": "Raccourcis",
    "menu_batch": "Importer des images…",
    "double_click_reset_hint": "Double-cliquez pour réinitialiser",

    "independent_channels_group_title": "Canaux RVB",
    "import_panel_title": "Fichiers",
    "block_collapse_tooltip": "Réduire/Développer",
    "block_close_tooltip": "Retirer de l'affichage",
    "menu_tools_histogram": "Histogramme",
    "reset_all_alignment_tooltip": "Réinitialiser l'alignement de toutes les couches",
    "reset_all_color_tooltip": "Réinitialiser les couleurs de toutes les couches",
    "harris_shutter_checkbox": "Effet Harris Shutter (image source en couleur)",
    "harris_shutter_info": (
        "<b>Désactivé (par défaut)</b><br>"
        "<span style=\"color:#9a9a9a;\">Mode Trichromie Classique : Combine 3 photos noir et blanc "
        "pour recomposer une image couleur</span>"
        "<br><br>"
        "<b>Activé</b><br>"
        "<span style=\"color:#9a9a9a;\">Mode Couleur : Simule des filtres RGB à partir de 3 photos "
        "couleurs afin de créer un &quot;Harris Shutter Effect&quot;</span>"
    ),
    "lock_layer_position_label": "Position verrouillée :",
    "lock_layer_position_info": "L'alignement automatique ne déplace jamais la couche verrouillée - "
                                 "il aligne les deux autres dessus, en conservant la position "
                                 "manuelle déjà réglée. Vous pouvez toujours modifier manuellement "
                                 "l'alignement de la couche verrouillée. Une seule couche est "
                                 "toujours verrouillée ; changez-la à tout moment.",

    "batch_window_title": "Import",
    "batch_import_button": "Importer",
    "batch_import_status_running": "Import {i} / {n}…",
    "batch_import_status_done": "{n} photo(s) importée(s).",
    "carousel_empty_hint": "Aucune photo importée — utilisez le bouton « Importer… » en haut de la barre latérale.",
    "carousel_toggle_tooltip": "Afficher/masquer les vignettes",
    "sort_button_tooltip": "Trier les vignettes",
    "sort_by_filename": "Par nom de fichier",
    "sort_by_capture_date": "Par date de capture",
    "sort_by_import_order": "Par ordre d'importation",
    "sort_by_custom": "Ordre personnalisé",
    "sort_reverse_order": "Ordre inversé",
    "export_scope_group": "Quoi exporter",
    "export_scope_current": "Exporter la photo actuelle",
    "export_scope_selected": "Exporter la sélection ({n})",
    "export_scope_all": "Exporter tout ({n})",
    "export_confirm_button": "Exporter",
    "export_no_items": "Aucune photo à exporter.",
    "close_button": "Fermer",
    "batch_mode_auto_radio": "Automatique",
    "batch_mode_semi_radio": "Semi-automatique",
    "batch_mode_manual_radio": "Manuelle",
    "batch_mode_info": (
        "<b>Automatique</b> — les fichiers sont regroupés grâce à un indicateur de filtre présent "
        "dans leur nom (Rouge, Vert, Bleu, Jaune ou Infrarouge - à n'importe quelle position, sans "
        "tenir compte de la casse). Le filtre qui remplit chaque canal R/V/B dépend du mode choisi "
        "dans <b>Options avancées</b> ci-dessous (Classique, Trichrome IR, Aerochrome…). Les fichiers "
        "partageant un nom identique une fois cet indicateur retiré forment un triplet ; sinon, une "
        "séquence numérotée simple (Image1, Image2, Image3…) est regroupée 3 fichiers pertinents à "
        "la fois, dans l'ordre.<br><br>"
        "<b>Semi-automatique</b> — sélectionnez un lot d'images en une fois, déjà dans l'ordre R, V, "
        "B, R, V, B… (glissez pour réordonner si besoin) : les 3 premières forment un triplet, les 3 "
        "suivantes le triplet suivant, etc.<br><br>"
        "<b>Manuelle</b> — choisissez les fichiers des colonnes R, V et B indépendamment, utile quand "
        "les noms de fichiers ne suivent aucune convention. La ligne N de chaque colonne forme un "
        "triplet."
    ),
    "batch_advanced_options_title": "Options avancées",
    "batch_advanced_mode_classic": "Trichrome classique",
    "batch_advanced_mode_ir": "Trichrome IR",
    "batch_advanced_mode_aerochrome": "Aerochrome",
    "batch_advanced_mode_custom": "Personnalisé",
    "filter_yellow": "Jaune",
    "filter_infrared": "Infrarouge",
    "batch_channel_mapping_title": "Association des canaux",
    "batch_filters_title": "Filtres caméra",
    "batch_filters_name_header": "Nom",
    "batch_filters_tokens_header": "Mots-clés",
    "batch_filters_hint": ("Les mots-clés sont séparés par des virgules et insensibles à la casse. Les "
                            "filtres intégrés ne peuvent pas être supprimés, mais leur nom et leurs "
                            "mots-clés peuvent être modifiés."),
    "batch_filters_add_button": "Ajouter un filtre personnalisé",
    "batch_filters_new_name_placeholder": "Nouveau filtre",
    "batch_filters_delete_tooltip": "Supprimer ce filtre",

    "batch_semi_select_button": "Sélectionner des images…",
    "batch_semi_hint": ("Les fichiers sont regroupés 3 par 3, dans l'ordre affiché, en R, V, B — "
                         "glissez pour réordonner."),
    "batch_semi_invalid_count": "{n} fichiers sélectionnés — ce n'est pas un multiple de 3 ({remainder} fichier(s) en trop seront ignorés).",
    "batch_semi_select_title": "Sélectionner les images (dans l'ordre R, V, B)",
    "batch_manual_add_button": "Ajouter des fichiers…",
    "batch_manual_remove_button": "Retirer la sélection",
    "batch_manual_clear_button": "Vider",
    "batch_manual_hint": ("Déposez des fichiers image sur une colonne pour les ajouter, ou glissez les "
                           "éléments dans une colonne pour les réordonner — la ligne N de chaque "
                           "colonne forme un triplet."),
    "batch_manual_mismatch_warning": "Les colonnes ont des tailles différentes (R : {r}, V : {g}, B : {b}) — seules les {n} premières seront appariées.",
    "batch_select_files_title": "Sélectionner les images {channel}",
    "batch_input_group": "Dossier d'entrée",
    "batch_browse_button": "Parcourir…",
    "batch_rescan_button": "Réanalyser",
    "batch_no_folder": "Aucun dossier sélectionné",
    "batch_select_input_title": "Sélectionner le dossier d'entrée",
    "batch_select_output_title": "Sélectionner le dossier de sortie",
    "batch_triplets_found": "{n} triplets appariés",
    "batch_unmatched_label": "{n} fichiers non appariés (ignorés) :",
    "batch_align_auto_checkbox": ("Aligner automatiquement chaque image (sinon, les calques restent "
                                   "à leur position par défaut)"),
    "batch_output_folder_label": "Dossier de sortie :",
    "export_same_as_source": "Dossier source",
    "export_same_as_source_tooltip": ("Enregistre chaque photo exportée à côté de son propre fichier "
                                       "source, plutôt que dans un dossier commun — utile quand les "
                                       "photos exportées proviennent de dossiers différents."),
    "export_reveal_in_finder": "Afficher dans le Finder après l'export",
    "batch_suffix_label": "Suffixe du nom de fichier :",
    "batch_format_label": "Format :",
    "batch_cancel_button": "Annuler",
    "batch_status_no_triplets": "Aucun triplet apparié trouvé dans ce dossier.",
    "batch_status_running": "Traitement {i} / {n}…",
    "batch_status_done": "Terminé — {ok} réussies, {failed} échouées",
    "batch_status_cancelled": "Annulé après {i} / {n}",
    "batch_error_no_input": "Sélectionnez d'abord un dossier d'entrée.",
    "batch_error_no_output": "Sélectionnez un dossier de sortie.",

    "status_auto_align_running_all": "Alignement automatique de toutes les couches en cours…",
    "status_auto_align_all_done": "Alignement automatique terminé.",
    "status_auto_align_failed": "Alignement automatique échoué.",
    "status_exported": "Image exportée : {path}",
    "status_settings_copied": "Réglages copiés",
    "status_settings_pasted": "Réglages collés sur {n} photo(s)",
    "status_crop_pasted": "Recadrage collé sur {n} photo(s)",
    "status_photos_deleted": "{n} photo(s) supprimée(s)",
    "status_photos_reset": "{n} photo(s) réinitialisée(s)",
    "status_photo_duplicated": "Photo dupliquée",
    "status_crop_applied": "Recadrage appliqué",

    "dialog_load_error_title": "Erreur de chargement",
    "dialog_load_error_text": "Impossible de charger l'image :\n{error}",
    "dialog_session_load_error_title": "Erreur de session",
    "dialog_session_load_error_text": "Impossible d'ouvrir le fichier de session :\n{error}",
    "dialog_session_load_empty": "Ce fichier de session ne contient aucune photo encore chargeable.",
    "dialog_alignment_title": "Alignement",
    "dialog_alignment_missing_images": "Chargez d'abord l'image de référence et ce calque.",
    "dialog_auto_align_title": "Alignement automatique",
    "dialog_auto_align_failed_channels": "Échec de l'alignement automatique pour : {channels}.\nEssayez un alignement manuel.",
    "dialog_export_missing": "Chargez les 3 images (Rouge, Vert, Bleu) avant d'exporter.",
    "dialog_export_error_title": "Erreur d'export",
    "dialog_export_error_text": "Impossible d'enregistrer l'image :\n{error}",

    "file_filter_all": "Tous les fichiers (*.*)",
    "load_dialog_title": "Charger l'image {channel}",
    "export_dialog_title": "Exporter l'image trichrome",
    "export_filter_png": "PNG 8 bits (*.png)",
    "export_filter_jpg": "JPEG 8 bits (*.jpg)",
    "export_filter_tiff": "TIFF 16 bits (*.tiff)",

    "help_quickstart_title": "Prise en main",
    "help_quickstart_content": """
<h3>Mode simple (une seule photo)</h3>
<ol>
<li>Chargez les clichés Rouge, Vert et Bleu depuis le panneau <b>Photo actuelle</b> à
gauche (ou le menu Fichier).</li>
<li>Dès que les 3 sont chargés, les deux autres calques sont <b>alignés
automatiquement</b> sur la couche verrouillée (ou cliquez sur <b>Alignement
automatique</b> dans le panneau <b>Photo actuelle</b> pour le refaire à tout moment).</li>
<li>Changez de couche verrouillée à tout moment avec les boutons <b>R / V / B</b> sous
<b>Position verrouillée</b>, dans le panneau <b>Photo actuelle</b> — elle définit la
taille et l'orientation du canevas (Vert par défaut).</li>
<li>Affinez l'alignement et l'étalonnage de chaque calque (à gauche), et le rendu
global — dont <b>Négatif</b>, <b>Hautes lumières/Ombres/Blancs/Noirs</b> et
<b>Température/Teinte</b> — dans <b>Correction Globale</b> (à droite). Les petites
icônes en bas de chaque panneau réinitialisent uniquement cette partie (survolez-les
pour plus de détails).</li>
<li>Cliquez sur <b>Exporter…</b> pour choisir un dossier/format de sortie et
enregistrer le résultat.</li>
</ol>
<h3>Mode batch (plusieurs photos)</h3>
<ol>
<li>Cliquez sur le bouton <b>Importer…</b> en haut de la barre latérale (ou appuyez sur
Cmd+I).</li>
<li>Choisissez comment les fichiers sont appariés : <b>Automatique</b> (par nom de
fichier), <b>Semi-automatique</b> (fichiers déjà dans l'ordre R, V, B) ou <b>Manuelle</b>
(vous choisissez chaque colonne) — cliquez sur le <b>?</b> à droite pour connaître la
différence entre elles.</li>
<li>Cochez <b>Aligner automatiquement chaque image</b> pour que chaque photo soit alignée
individuellement à l'import (sinon ses calques restent à leur position par défaut), puis
cliquez sur <b>Importer</b> — les nouvelles photos sont ajoutées à la suite de la
sélection actuelle (retirez celles dont vous ne voulez pas du carrousel à tout moment
avec Cmd+Suppr).</li>
<li>Les photos apparaissent dans un <b>carrousel</b> sous l'aperçu (il s'affiche
automatiquement dès qu'il y a plus d'une photo). Cliquez sur une vignette (ou utilisez
<b>←/→</b>) pour modifier l'alignement et la couleur de cette photo indépendamment des
autres.</li>
<li>Constituez une sélection avec <b>Cmd+clic</b> ou <b>Cmd+A</b>, puis utilisez
<b>Exporter…</b> (Cmd+E) pour exporter la photo <i>actuelle</i>, la
<i>sélection</i>, ou <i>toutes</i> les photos en une fois.</li>
<li>Clic droit sur une vignette pour <b>Copier</b> / <b>Coller</b> / <b>Tout
réinitialiser</b> / <b>Dupliquer</b> / <b>Supprimer</b> (Copier/Coller/Supprimer sont
aussi Cmd+C / Cmd+V / Cmd+Suppr). <b>Tout réinitialiser</b> remet l'alignement, la
couleur et le négatif de cette photo à zéro ; <b>Dupliquer</b> en crée une copie
numérotée — par ex. « (2) » — pour essayer un autre réglage en parallèle.</li>
</ol>
<h3>Sessions</h3>
<ul>
<li>Tout votre travail en cours — chaque photo importée et ses réglages — forme une
<b>session</b>. <b>Fichier ▸ Enregistrer la session</b> (Cmd+S) l'écrit dans un
fichier portable <b>.trirgb</b> que vous pouvez rouvrir plus tard ou déplacer sur une
autre machine ; <b>Enregistrer la session sous…</b> (Cmd+Maj+S) en enregistre une
copie sous un nouveau nom.</li>
<li><b>Fichier ▸ Ouvrir une session…</b> (Cmd+O) en recharge une ;
<b>Nouvelle session</b> (Cmd+N) repart d'une seule photo vierge.</li>
<li>Relancer l'application rouvre automatiquement la dernière session ouverte, pour
reprendre exactement là où vous en étiez.</li>
<li>Le nom de la session en cours s'affiche en bas à droite de la barre d'état. En
cas de modifications non enregistrées, fermer l'application, ouvrir une autre
session ou en créer une nouvelle proposera d'abord de les enregistrer.</li>
</ul>
<h3>Autres</h3>
<ul>
<li>L'aperçu s'ouvre automatiquement en zoom <b>ajusté à la fenêtre</b>, au lancement et
après chaque import.</li>
<li>Le petit bouton flèche + carrés à côté de <b>Plein écran</b> affiche ou masque le
carrousel.</li>
<li>Le bouton <b>Plein écran</b> (Cmd+F) masque les panneaux latéraux pour un aperçu sans
distraction (Échap pour quitter).</li>
<li>Presque toutes les modifications peuvent être annulées avec <b>Cmd+Z</b>
(<b>Cmd+Maj+Z</b> pour rétablir).</li>
</ul>
""",

    "help_shortcuts_title": "Raccourcis",
    "help_shortcuts_content": """
<h3>Général</h3>
<ul>
<li><b>Cmd+N</b> — Nouvelle session</li>
<li><b>Cmd+O</b> — Ouvrir une session</li>
<li><b>Cmd+S</b> — Enregistrer la session</li>
<li><b>Cmd+Maj+S</b> — Enregistrer la session sous</li>
<li><b>Cmd+I</b> — Menu Import</li>
<li><b>Cmd+E</b> — Exporter (Entrée dans cette fenêtre lance l'export)</li>
<li><b>Cmd+Z</b> / <b>Cmd+Maj+Z</b> — Annuler / Rétablir</li>
<li><b>Cmd+R</b> / <b>Cmd+L</b> — fait pivoter la photo actuelle de 90° à droite/gauche</li>
<li><b>E</b> — affiche l'étalonnage global</li>
<li><b>C</b> — affiche l'outil de recadrage</li>
<li><b>Cmd+F</b> — bascule le plein écran (Échap pour quitter)</li>
<li><b>F1</b> — Prise en main</li>
<li><b>Cmd+Q</b> — quitter</li>
</ul>
<h3>Navigation</h3>
<ul>
<li><b>←</b> / <b>→</b> — va à la photo précédente/suivante (maintenez <b>Maj</b> pour
étendre la sélection d'export au lieu de simplement naviguer)</li>
<li><b>Glisser</b> une vignette — réorganise les photos (bascule sur l'ordre
personnalisé)</li>
<li><b>Cmd+clic</b> sur une vignette — ajoute/retire de la sélection d'export</li>
<li><b>Cmd+A</b> — sélectionne toutes les photos, ou les désélectionne toutes si elles
le sont déjà</li>
<li><b>Cmd+C</b> / <b>Cmd+V</b> — copie les réglages de la photo actuelle, les colle sur
les photos sélectionnées</li>
<li><b>Cmd+Suppr</b> — retire la ou les photo(s) sélectionnée(s)</li>
</ul>
<h3>Aperçu</h3>
<p>Le calque <i>actif</i> est celui qui réagit quand on glisse ou qu'on utilise la
molette directement sur l'aperçu.</p>
<ul>
<li><b>Glisser</b> — déplace le calque actif</li>
<li><b>Maj + molette</b> — met à l'échelle le calque actif</li>
<li><b>Alt + molette</b> — fait pivoter le calque actif</li>
<li><b>Ctrl + molette</b>, ou <b>pincer</b> sur le trackpad — zoome l'aperçu</li>
<li><b>Glisser à deux doigts</b> sur le trackpad — déplace la vue une fois zoomée</li>
<li><b>F</b> / <b>Z</b> — passe directement au zoom Ajuster / 100% (ou utilisez les
boutons de la barre d'outils)</li>
<li><b>:</b> — bascule Comparer, affiche l'original non modifié</li>
</ul>
<h3>Curseurs</h3>
<ul>
<li><b>Double-clic</b> sur un curseur — le réinitialise à sa valeur par défaut</li>
</ul>
""",

    # --- Outil de scan (fenêtre de test autonome, direction v0.5.0) ---
    "scan_window_title": "Outil de scan (test)",
    "scan_device_group": "Appareil",
    "scan_device_not_connected": "Non connecté",
    "scan_device_connected": "Connecté : {model}",
    "scan_device_refresh": "Actualiser",
    "scan_mode_group": "Mode",
    "scan_mode_bw": "Noir et Blanc",
    "scan_mode_color": "Couleur",
    "scan_mode_color_reversal": "Couleur Inversible",
    "scan_mode_invert_note": "L'inversion sera appliquée automatiquement à l'import pour ce mode.",
    "scan_mode_no_invert_note": "Aucune inversion nécessaire à l'import pour ce mode (déjà positif).",
    "scan_light_group": "Lumière de scan",
    "scan_light_external": "Lumière externe",
    "scan_light_white": "Lumière blanche",
    "scan_light_rgb": "Lumière RVB",
    "scan_light_rgb_note": "La capture prendra automatiquement 3 photos en séquence - lumière rouge, verte, puis bleue - et reviendra à la lumière blanche ensuite. Les 3 partagent le même numéro, avec le suffixe _R/_G/_B.",
    "scan_light_window_title": "Rétroéclairage de scan",
    "scan_capturing_channel_status": "Prise de vue {channel}…",
    "scan_process_checkbox": "Enregistrer aussi un aperçu JPG traité",
    "scan_process_tooltip": "Enregistre une copie JPG supplémentaire dans un sous-dossier « processed » : noir et blanc + inversé pour Noir et Blanc, inversé pour Couleur, tel quel pour Couleur Inversible. Pour un triplet en Lumière RVB, recompose les 3 photos en une seule image trichrome avec l'algorithme d'auto-alignement et de composition de l'application.",
    "scan_processing_status": "Traitement…",
    "scan_processed_label": "Traité",
    "scan_location_group": "Emplacement d'enregistrement",
    "scan_base_folder_label": "Dossier",
    "scan_base_folder_browse": "Parcourir…",
    "scan_subfolder_label": "Sous-dossier",
    "scan_use_roll_as_subfolder": "Utiliser le nom de la bobine comme sous-dossier",
    "scan_subfolder_preview": "Enregistrement dans : {name}",
    "scan_roll_name_label": "Nom de la bobine",
    "scan_next_number_label": "Prochain numéro",
    "scan_quality_label": "Format",
    "scan_quality_unavailable": "Non exposé par cet appareil",
    "scan_capture_button": "Prendre la photo",
    "scan_capturing_status": "Prise de vue…",
    "scan_ready_status": "Prêt.",
    "scan_history_group": "Capturé dans cette session",
    "scan_add_to_session_button": "Ajouter à la session actuelle",
    "scan_error_title": "Erreur de scan",
    "scan_no_camera_error": "Aucun appareil sélectionné ou connecté.",
}

STRINGS = {"en": EN, "fr": FR}

_current_language = DEFAULT_LANGUAGE


def set_language(lang: str) -> None:
    global _current_language
    if lang in STRINGS:
        _current_language = lang


def current_language() -> str:
    return _current_language


def tr(key: str, **kwargs) -> str:
    table = STRINGS.get(_current_language, EN)
    text = table.get(key, EN.get(key, key))
    return text.format(**kwargs) if kwargs else text


CHANNEL_KEYS = ("R", "G", "B")


def channel_name(color_index_or_key) -> str:
    key = color_index_or_key if isinstance(color_index_or_key, str) else CHANNEL_KEYS[color_index_or_key]
    return tr({"R": "channel_r", "G": "channel_g", "B": "channel_b"}[key])
