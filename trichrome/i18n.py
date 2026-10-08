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

    "load_image_button": "Load an image…",
    "change_image_button": "Change Image",
    "no_image_loaded": "No image loaded",
    "channel_swap_handle_tooltip": "Drag onto another channel's filename to swap their images",
    "active_checkbox": "Move on Canvas",
    "active_layer_info": (
        "<b>Move on Canvas</b><br>"
        "<span style=\"color:#9a9a9a;\">The channel that reacts to dragging, scrolling and "
        "the arrow keys directly on the preview canvas. Only one channel can be active at "
        "a time - check Move on Canvas on a different channel to switch, or just switch the "
        "R/G/B tab: while it's checked, it automatically follows whichever tab you're "
        "viewing</span>"
        "<br><br>"
        "<b>Drag</b><br>"
        "<span style=\"color:#9a9a9a;\">Moves the active channel</span>"
        "<br><br>"
        "<b>Shift + scroll</b><br>"
        "<span style=\"color:#9a9a9a;\">Scales the active channel</span>"
        "<br><br>"
        "<b>Alt/Option + scroll</b><br>"
        "<span style=\"color:#9a9a9a;\">Rotates the active channel</span>"
        "<br><br>"
        "<b>Arrow keys</b><br>"
        "<span style=\"color:#9a9a9a;\">Nudge the active channel by a small step (hold "
        "Shift for a bigger step). While Move on Canvas is checked, all 4 arrow keys "
        "control alignment instead of their usual navigation</span>"
        "<br><br>"
        "<b>Locked channel</b><br>"
        "<span style=\"color:#9a9a9a;\">Excluded from Auto Align only - it can still be "
        "made active and repositioned manually (see Lock layer position)</span>"
    ),
    "stretch_checkbox": "Stretch on Canvas",
    "stretch_layer_info": (
        "<b>Stretch on Canvas</b><br>"
        "<span style=\"color:#9a9a9a;\">Click and drag directly on the preview canvas to "
        "locally stretch the active channel, starting from the exact point you click - lets "
        "you refine one area precisely without disturbing the rest of the image. Only one "
        "channel can be active at a time - check Stretch on Canvas on a different channel to "
        "switch, or just switch the R/G/B tab: while it's checked, it automatically follows "
        "whichever tab you're viewing. Checking this unchecks Move on Canvas (and vice versa) "
        "- a canvas drag can only do one or the other</span>"
        "<br><br>"
        "<b>Drag</b><br>"
        "<span style=\"color:#9a9a9a;\">Pulls the image from the clicked point towards the "
        "cursor - a reference grid shows the deformation live. Drag again elsewhere to refine "
        "further, without undoing the previous drag</span>"
        "<br><br>"
        "<b>Reset</b><br>"
        "<span style=\"color:#9a9a9a;\">The Geometry section's own Reset button clears "
        "every stretch drag along with the 4 sliders above</span>"
    ),
    "stretch_on_canvas_indicator_label": "Drag on the canvas to stretch the {channel} layer, starting from where you click",
    "solo_checkbox": "Solo Layer Preview (B&&W)",
    "invert_checkbox_tooltip": "Negative (invert scan) — inverts the tones of all 3 channels, for raw, uninverted negative scans.",
    "alignment_group": "Alignment",
    "position_group": "Position",
    "offset_x": "Offset X",
    "offset_y": "Offset Y",
    "scale_label": "Scale",
    "rotation_label": "Rotation (°)",
    "distortion_group": "Geometry",
    "distortion_label": "Distortion",
    "perspective_v_label": "Vertical",
    "perspective_h_label": "Horizontal",
    "anamorphic_label": "Aspect",
    "auto_align_button": "Auto align",
    "auto_align_apply_distortion_checkbox": "Apply geometry to auto align",
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
    "crop_group_title": "Framing",
    "crop_aspect_ratio_label": "Aspect",
    "crop_ratio_original": "Original",
    "crop_ratio_free": "Free",
    "crop_ratio_custom": "Custom",
    "crop_invert_orientation_button": "Invert Orientation",
    "crop_straighten_label": "Straighten",
    "crop_mirror_label": "Mirror",
    "crop_section_title": "Crop",
    "crop_geometry_section_title": "Geometry",
    "reset_crop_geometry_tooltip": "Reset Geometry (Distortion, Vertical, Horizontal, Aspect)",
    "crop_perspective_tooltip": "Perspective correction",
    "perspective_indicator_label": "Perspective: draw up to 2 vertical and 2 horizontal guides along edges that should be straight - double-click a guide to delete it - Enter to apply, Esc to cancel",
    "status_perspective_need_two_guides": "Draw 2 vertical or 2 horizontal guides",
    "status_perspective_applied": "Perspective corrected",
    "crop_mirror_h_button": "Mirror Left/Right",
    "crop_mirror_v_button": "Mirror Top/Bottom",
    "crop_grid_label": "Grid:",
    "crop_grid_off": "Off",
    "crop_grid_3x3": "3 × 3",
    "crop_grid_2x2": "2 × 2",
    "crop_grid_golden": "Golden Ratio",
    "crop_grid_squares": "Grid",
    "crop_reset_tooltip": "Reset crop",
    "crop_activate_tooltip": "Toggle crop mode",
    "curves_group_title": "Curves",
    "curves_reset_tooltip": "Reset curve",
    "saturation_label": "Saturation",
    "temperature_label": "Temperature",
    "tint_label": "Tint",
    "export_button": "Export…",

    "zoom_in": "Zoom In",
    "zoom_out": "Zoom Out",
    "zoom_fit_tooltip": "Fit to window (F)",
    "zoom_100": "100% (Real Size) (Z)",
    "hq_preview_tooltip": "HQ Preview (H): show the photo at full resolution shortly after you stop editing, computed in the background",
    "hq_preview_failed": "HQ Preview couldn't be computed: {error}",
    "rotate_left_tooltip": "Rotate left (⌘L)",
    "rotate_right_tooltip": "Rotate right (⌘R)",
    "fullscreen_button": "Fullscreen (⌘F)",
    "exit_fullscreen_button": "Exit fullscreen (⌘F)",
    "compare_tooltip": "Compare (:)",
    "compare_indicator_label": "Displaying original",
    "move_on_canvas_indicator_label": "Drag the {channel} layer on the canvas to reposition it",
    "menu_view": "View",
    "menu_view_zoom_in": "Zoom In",
    "menu_view_zoom_out": "Zoom Out",
    "menu_view_zoom_fit": "Zoom to Fit",
    "menu_view_zoom_100": "Zoom 100%",
    "menu_view_hq_preview": "Preview HQ",
    "menu_view_compare": "Compare",
    "menu_view_fullscreen": "Full Screen",
    "menu_view_exit_fullscreen": "Exit Full Screen",
    "menu_view_thumbnails": "Show/Hide Thumbnails",
    "menu_view_grid": "Grid View",
    "status_saving_session": "Saving session…",
    "status_loading_session": "Loading session…",
    "status_session_loaded": "Session loaded",
    "status_exporting": "Exporting {i} / {n}…",
    "menu_settings": "Preferences…",
    "settings_title": "Preferences",
    "settings_section_general": "General",
    "settings_language": "Language",
    "settings_reopen_last_session": "Reopen the last session at launch",
    "settings_quick_tour_at_startup": "Show the Quick Tour at startup",
    "settings_check_updates_at_startup": "Check for updates at startup",
    "settings_play_sounds": "Play sounds when saving, deleting and exporting",
    "settings_section_sessions": "Sessions",
    "settings_session_preview_cache": "Store previews in session files",
    "settings_session_preview_cache_help": "Sessions open much faster. Adds about 350 KB per photo to the .trirgb file. Exports and HQ Preview always use your original files.",
    "settings_section_export": "Export",
    "settings_export_help": "Used by the Export window, which also remembers the last values you chose there.",
    "settings_done_button": "Done",
    "settings_section_experimental": "Experimental",
    "settings_experimental_info": "Features still in development. They may be incomplete, change, or not work with every setup. Turn one on only if you want to try it early.",
    "settings_scan_tool_enabled": "Enable the Scan tool",
    "settings_scan_tool_enabled_help": "Tethered film scanning with a camera over USB. Adds the Scan button to the toolbar, the S shortcut and its entries in the Tools and Window menus.",
    "settings_scan_tool_busy_title": "Capture in Progress",
    "settings_scan_tool_busy_text": "The Scan tool can't be turned off while a capture is running. Wait for it to finish, then try again.",
    "settings_export_format": "Default Format",
    "settings_export_suffix": "Filename suffix",
    "status_updating_previews": "Updating previews {i} / {n}…",
    "status_export_finished": "Export: {status}",
    "status_hq_preview_loading": "Loading HQ preview…",
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
    "crop_toolbar_tooltip": "Framing (C)",
    "scan_toolbar_tooltip": "Scan (S)",
    "right_panel_toggle_tooltip": "Show/hide right panel",
    "help_toolbar_tooltip": "Help (F1)",
    "canvas_placeholder": 'Load an image via the "Import" button, or drag an image file here',
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
        "affected photo(s) using the Trichrome Process panel on the left."
    ),
    "dialog_locate_failed_column_photo": "Photo",
    "dialog_locate_failed_column_channel": "Channel",

    "black_white_button_tooltip": "Black & White",
    "pick_white_balance_tooltip": "Pick White Balance (W) - click a point in the preview that should be neutral gray",
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
    "menu_convert_to_trichrome": "Convert to Trichrome Image",
    "menu_tools": "Tools",
    "menu_tools_crop": "Framing",
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
    "menu_window_layout_crop": "Framing",
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
    "menu_quickstart_action": "Guide",
    "menu_shortcuts_action": "Keyboard Shortcuts",
    "menu_check_updates_action": "Check for Updates…",
    # Check for Updates (widgets/update_dialog.py, update_checker.py).
    "update_check_window_title": "Check for Updates",
    "update_check_current_version": "Version {version}",
    "update_check_checking": "Checking for updates…",
    "update_check_up_to_date": "You're up to date.",
    "update_check_available": "Version {version} is available.",
    "update_check_failed": "Couldn't check for updates. Check your internet connection and try again.",
    "update_check_update_button": "Update…",
    "update_check_close": "Close",
    # Quick Tour (trichrome/quick_tour.py, widgets/welcome_dialog.py). Step
    # bodies: "\n\n" separates paragraphs, <kbd>X</kbd> renders as a key.
    "menu_quick_tour_action": "Quick Tour",
    "quick_tour_welcome_window_title": "Welcome",
    "quick_tour_welcome_title": "Welcome to Trichr-o-matic",
    "quick_tour_version": "Version {version}",
    "quick_tour_welcome_text": (
        "Trichr-o-matic is an app built for processing trichrome photography. Importing the Red, Green and Blue layers, aligning them and color-grading your photos: all of this is possible with Trichr-o-matic, and much more.\n\nStart the tour to learn more."
    ),
    "quick_tour_open_at_startup": "Open at startup",
    "quick_tour_close": "Close",
    "quick_tour_start": "Start the Tour",
    "quick_tour_step": "Step {n} / {total}",
    "quick_tour_in_progress": "In progress",
    "quick_tour_skip": "Skip tour",
    "quick_tour_back": "Back",
    "quick_tour_next": "Next",
    "quick_tour_finish": "Finish",
    "quick_tour_light_diagram_caption": "Light Mode layout: one panel, one photo.",
    "quick_tour_sessions_title": "Sessions",
    "quick_tour_sessions_body": (
        "Trichr-o-matic works from sessions, saved as .trirgb files.\n\nIn the toolbar, the icons on the left let you create a new session (<kbd>⌘N</kbd>), open an existing one (<kbd>⌘O</kbd>) or save the current session (<kbd>⌘S</kbd>)."
    ),
    "quick_tour_toolbar_title": "Import and export",
    "quick_tour_toolbar_body": (
        "The Import button is on the left of the toolbar, Export on the right."
    ),
    "quick_tour_workspaces_title": "Workspaces",
    "quick_tour_workspaces_body": (
        "Four workspaces arrange the tools into a predefined layout: Trichrome, Color Correction, Framing and Scan (shortcuts <kbd>T</kbd> <kbd>E</kbd> <kbd>C</kbd> <kbd>S</kbd>).\n\nBy default, each one shows the panels useful for its task.\n\nTo create your own layout, rearrange the panels, then save it from Window ▸ Layout Preset."
    ),
    "quick_tour_workspaces_body_no_scan": (
        "Three workspaces arrange the tools into a predefined layout: Trichrome, Color Correction and Framing (shortcuts <kbd>T</kbd> <kbd>E</kbd> <kbd>C</kbd>).\n\nBy default, each one shows the panels useful for its task."
    ),
    "quick_tour_preview_title": "Preview",
    "quick_tour_preview_body": (
        "The main window shows the result, and updates as you adjust.\n\n<kbd>F</kbd> fits the image to the window, <kbd>Z</kbd> shows it at actual size, and <kbd>⌘F</kbd> goes full screen.\n\nSome tools work directly on the image: moving or stretching a layer in Trichrome Process, cropping the photo, or picking a white balance reference."
    ),
    "quick_tour_filmstrip_title": "Photos and view controls",
    "quick_tour_filmstrip_body": (
        "Every photo in your session gets a thumbnail here: click to switch, drag to reorder, right-click for more.\n\nThe bar below handles zoom, HQ preview, rotation, before/after comparison, full screen, sorting and grid view (<kbd>G</kbd>)."
    ),
    "quick_tour_files_title": "Files",
    "quick_tour_files_body": (
        "Choose the processing mode:<br><b>Solo</b>: a standard photo, already composed<br><b>Classic Trichrome</b>: 3 black and white photos<br><b>Color Trichrome</b>: one channel from each of 3 color photos\n\nIn trichrome modes, import or replace the files for each R/G/B layer. Drag a file's handle onto another channel to swap the two."
    ),
    "quick_tour_channels_title": "Trichrome Process",
    "quick_tour_channels_body": (
        "The app's main tool.\n\nFor each layer, you can adjust the color, reposition it or change its geometry to get a perfect alignment.\n\n<b>Auto Align</b> aligns the layers automatically for you. Manual adjustments may be required.\n\nUse <b>Lock Layer Position</b> to fix the reference channel, so it won't move.\n\nShow each layer on its own with the buttons at the top of the tool."
    ),
    "quick_tour_histogram_title": "Histogram",
    "quick_tour_histogram_body": (
        "Shows the image tones live.\n\nClick the Y/R/G/B button to isolate one channel.\n\nUse the eyedropper to read a specific value on the preview."
    ),
    "quick_tour_crop_title": "Framing",
    "quick_tour_crop_body": (
        "Crop: click the crop icon, or turn on crop mode with <kbd>C</kbd>. Crop in the preview, then confirm with <kbd>Enter</kbd>.\n\nGeometry: distortion, vertical and horizontal perspective, and aspect correction for the whole composed image."
    ),
    "quick_tour_light_title": "Light",
    "quick_tour_light_body": (
        "Exposure, brightness, contrast, highlights, shadows, whites, blacks and gamma adjustment applied to the composed image.\n\nThe Negative button in the header turns the image into a negative."
    ),
    "quick_tour_color_title": "Color",
    "quick_tour_color_body": (
        "Temperature, tint and saturation adjustment applied to the composed image.\n\nUse the white balance picker to click something neutral in the image.\n\nThe button in the header converts to black and white."
    ),
    "quick_tour_curves_title": "Curves",
    "quick_tour_curves_body": (
        "Fine tonal control on the master curve (Y) or on each R, G and B channel.\n\nClick the line to add a point, drag to shape it, double-click a point to remove it."
    ),
    "quick_tour_scan_title": "Scan",
    "quick_tour_scan_body": (
        "Digitize film with a camera tethered over USB. Pick the film type and the backlight; with "
        "the RGB light, each capture takes the three exposures of a trichrome automatically. "
        "Captures go straight into your session.\n\n"
        "The Scan workspace (<kbd>S</kbd>) shows it next to Histogram and Framing. This tool is "
        "still being built: some options are missing and may change."
    ),
    "quick_tour_arrange_title": "Arrange your workspace",
    "quick_tour_arrange_body": (
        "Rearrange your workspace by dragging a block by its grip. Drop it where you want, in the panel of your choice.\n\nCollapse a block with the arrow, or close it with the X.\n\nReopen a closed block from the Tools menu.\n\nTo save your own workspace layout, go to Window ▸ Layout Preset.\n\nThe two buttons at the top right hide the side panels (<kbd>I</kbd> for the left panel, <kbd>O</kbd> for the right)."
    ),
    "quick_tour_batch_title": "Import Window",
    "quick_tour_batch_body": (
        "Open the import window with Cmd+I or using the top left button.\n\nChoose the processing mode:<br><b>Solo</b>: a standard photo, already composed<br><b>Classic Trichrome</b>: 3 black and white photos<br><b>Color Trichrome</b>: one channel from each of 3 color photos\n\nFor trichrome modes, choose how the triplets are grouped into trichromes:<br>Automatic (by filter name in the filename)<br>Sequential (files already in order)<br>Manual\n\nTick <b>Auto align</b> to align every photo as it comes in."
    ),
    "quick_tour_light_mode_title": "Light Mode",
    "quick_tour_light_mode_body": (
        "Switch to it from <kbd>Window</kbd> ▸ <kbd>Switch to Light Mode</kbd>, and back the same way with <kbd>Window</kbd> ▸ <kbd>Switch to Advanced Mode</kbd>.\n\nLight Mode is a simpler version of the app for working on one trichrome image at a time: the four blocks that matter and the preview.\n\nSessions, thumbnails and Batch Import are hidden, and your Advanced session stays as it was."
    ),
    "quick_tour_light_mode_body_light": (
        "Switch back to the full app from <kbd>Window</kbd> ▸ <kbd>Switch to Advanced Mode</kbd>.\n\n"
        "You're in Light Mode, a simpler version of the app for one trichrome at a time: the four "
        "blocks that matter and the preview. Advanced Mode adds sessions, thumbnails, Batch Import "
        "and every tool."
    ),
    "quick_tour_ready_title": "You're ready",
    "quick_tour_ready_body": (
        "Reopen this tour anytime from <b>Help ▸ Quick Tour</b> or this button.\n\nThe Guide and the full list of keyboard shortcuts are here too."
    ),
    "quick_tour_ready_body_light": (
        "Reopen this tour anytime from <b>Help ▸ Quick Tour</b>. The Guide and the full list of "
        "keyboard shortcuts are in the Help menu too."
    ),
    "menu_batch": "Import Images…",
    "menu_switch_to_light_mode": "Switch to Light Mode",
    "menu_switch_to_advanced_mode": "Switch to Advanced Mode",
    "light_mode_exit_confirm_title": "Switch to Advanced Mode",
    "light_mode_exit_confirm_text": (
        "Start a new session with the current photo, or open your last session instead?"
    ),
    "light_mode_exit_new_session_button": "New Session with This Photo",
    "light_mode_exit_open_last_button": "Open Last Session",
    "light_mode_reset_channels_tooltip": "Clear the Red, Green and Blue images",
    "double_click_reset_hint": "Double-click to reset",

    "independent_channels_group_title": "Trichrome Process",
    "import_panel_title": "Files",
    "mode_solo_option": "Solo",
    "mode_bw_trichrome_option": "Classic Trichrome",
    "mode_color_trichrome_option": "Color Trichrome",
    "mode_select_info": (
        "<b>Solo</b><br>"
        "<span style=\"color:#9a9a9a;\">A single already-composed photo, loaded and edited "
        "as-is - no channel recomposition</span>"
        "<br><br>"
        "<b>Classic Trichrome</b><br>"
        "<span style=\"color:#9a9a9a;\">Combines 3 black &amp; white photos taken with colored "
        "filters to recompose a color image</span>"
        "<br><br>"
        "<b>Color Trichrome</b><br>"
        "<span style=\"color:#9a9a9a;\">Simulates RGB filters from 3 color photos, each keeping "
        "its own real channel, to create a &quot;Harris Shutter Effect&quot;</span>"
    ),
    "normal_file_path_label": "File Path:",
    "status_photo_added": "Photo added",
    "status_photos_added": "{n} photo(s) added",
    "dialog_drop_photos_failed_text": "Could not load the following file(s):\n{files}",
    "normal_photo_label": "Photo",
    "channels_disabled_normal_mode": "This tool is only available for trichrome photographs",
    "mode_switch_dialog_title": "Mode Change",
    "mode_switch_dialog_text": (
        "Are you sure you want to switch back to Solo mode? Choose which "
        "layer you want to continue editing:"
    ),
    "mode_switch_to_trichrome_dialog_text": (
        "Are you sure you want to switch to {mode} mode? Which layer would "
        "you like to assign this image to?"
    ),
    "mode_switch_channel_button": "{channel} Layer",
    "mode_switch_cancel_button": "Cancel",
    "block_collapse_tooltip": "Collapse/Expand",
    "block_close_tooltip": "Remove from view",
    "menu_tools_histogram": "Histogram",
    "reset_all_alignment_tooltip": "Reset alignment for all channels",
    "reset_all_color_tooltip": "Reset color for all channels",
    "reset_position_tooltip": "Reset Position (Offset X, Offset Y, Scale, Rotation)",
    "reset_distortion_tooltip": "Reset Distortion (Distortion, Vertical, Horizontal, Aspect)",
    "reset_stretch_tooltip": "Reset Stretch on Canvas only",
    "reset_tone_tooltip": "Reset Light (Exposure, Brightness, Contrast, Highlights, Shadows, Whites, Blacks, Gamma)",
    "lock_layer_position_label": "Lock layer position:",
    "lock_layer_position_info": "Auto Align never moves the locked channel - it aligns the other "
                                 "two onto it instead, keeping whatever manual position you've set. "
                                 "You can still edit the locked channel's own alignment by hand. "
                                 "Exactly one channel is always locked; pick a different one anytime.",
    "display_layer_label": "Show Layer:",

    "batch_window_title": "Import",
    "batch_import_button": "Import",
    "batch_import_status_running": "Importing {i} / {n}…",
    "batch_import_status_done": "{n} photo(s) imported.",
    "carousel_empty_hint": "No photos imported yet — use the “Import…” button at the top of the sidebar.",
    "carousel_toggle_tooltip": "Show/hide thumbnails",
    "grid_view_toggle_tooltip": "Grid view (G)",
    "sort_button_tooltip": "Sort thumbnails",
    "sort_by_filename": "By Filename",
    "sort_by_capture_date": "By Capture Date",
    "sort_by_import_order": "By Import Order",
    "sort_by_custom": "Custom Order",
    "sort_reverse_order": "Reverse Order",
    "export_scope_current": "Export current photo",
    "export_scope_selected": "Export selected ({n})",
    "export_scope_all": "Export all ({n})",
    "export_confirm_button": "Export",
    "export_no_items": "No photo to export.",
    "export_already_running": "An export is already in progress. Wait for it to finish (see the status bar) before starting another one.",
    "export_failures_text": "{failed} of {n} photo(s) could not be exported.",
    "export_failures_photo_header": "Photo",
    "export_failures_error_header": "Error",
    "export_quit_confirm_title": "Export in Progress",
    "export_quit_confirm_text": "An export is still running. Quitting now will stop it after the photo currently being saved.",
    "export_quit_confirm_button": "Stop Export and Quit",
    "close_button": "Close",
    "batch_mode_auto_radio": "Automatic",
    "batch_mode_semi_radio": "Sequential",
    "batch_mode_manual_radio": "Manual",
    "batch_mode_info": (
        "<b>Automatic</b> — files are grouped by a filter marker found in their name (Red, Green, "
        "Blue, Yellow or Infrared - any position, case-insensitive). Which filter fills which R/G/B "
        "channel depends on the mode picked in <b>Import Rules</b> below (Classic, IR Trichrome, "
        "Aerochrome…). Files sharing an identical name once that marker is removed form one triplet; "
        "otherwise, a plain numbered sequence (Image1, Image2, Image3…) is grouped 3 relevant files "
        "at a time, in order.<br><br>"
        "<b>Sequential</b> — select a batch of images at once, already in R, G, B, R, G, B… "
        "order (drag to reorder if needed): the first 3 form one triplet, the next 3 the next one, "
        "and so on.<br><br>"
        "<b>Manual</b> — pick the files for the R, G and B columns independently, useful when "
        "filenames don't follow any pattern at all. Row N of each column forms one triplet."
    ),
    "batch_advanced_options_title": "Auto-Import Rules",
    "batch_auto_import_rules_info": (
        "<b>Auto-Import Rules</b><br>"
        "<span style=\"color:#9a9a9a;\">Define the automatic file-detection settings and how they "
        "get assigned to the R/G/B Channels</span>"
    ),
    "batch_semi_import_rule_title": "Sequential Import Rule",
    "batch_semi_import_rule_info": (
        "<b>Sequential Import Rule</b><br>"
        "<span style=\"color:#9a9a9a;\">Choose the order in which each group of 3 files is assigned "
        "to the R/G/B Channels</span>"
    ),
    "batch_advanced_options_info": (
        "<b>RGB Trichrome</b><br>"
        "<span style=\"color:#9a9a9a;\">Standard mapping - the R, G and B filtered photos fill "
        "the R, G and B channels directly</span>"
        "<br><br>"
        "<b>IR Trichrome</b><br>"
        "<span style=\"color:#9a9a9a;\">The Red channel is filled by an infrared-filtered photo "
        "instead - Green and Blue stay standard</span>"
        "<br><br>"
        "<b>Aerochrome</b><br>"
        "<span style=\"color:#9a9a9a;\">Simulates Kodak Aerochrome's shifted mapping - Red channel "
        "from Infrared, Green channel from Red, Blue channel from Green</span>"
        "<br><br>"
        "<b>Custom</b><br>"
        "<span style=\"color:#9a9a9a;\">Freely assign which filter feeds each channel, using the "
        "filters defined below</span>"
    ),
    "batch_advanced_mode_classic": "RGB Trichrome",
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
    "batch_semi_hint": ("Files are grouped 3 at a time, in the order shown — drag to reorder. Set "
                         "the channel order in Sequential Import Rule below."),
    "batch_semi_invalid_count": "{n} files selected — not a multiple of 3 ({remainder} extra file(s) will be ignored).",
    "batch_semi_select_title": "Select images",
    "batch_manual_add_button": "Add files…",
    "batch_manual_remove_button": "Remove selected",
    "batch_manual_clear_button": "Clear",
    "batch_manual_hint": ("Drop image files onto a column to add them, or drag items within a column "
                           "to reorder them."),
    "batch_select_files_title": "Select the {channel} images",
    "batch_processing_mode_group": "Processing Mode",
    "batch_solo_select_images_title": "Select photos to import",
    "batch_solo_count": "{n} photo(s) queued",
    "batch_solo_no_photos": "No photos selected to import.",
    "batch_input_group": "File Selection",
    "batch_browse_button": "Browse…",
    "batch_rescan_button": "Rescan",
    "batch_no_folder": "No folder selected",
    "batch_select_input_title": "Select the input folder",
    "batch_select_output_title": "Select the output folder",
    "batch_triplets_found": "{n} matched triplets",
    "batch_unmatched_label": "{n} unmatched files (ignored)",
    "batch_align_auto_checkbox": "Auto-align each image individually",
    "batch_output_folder_label": "Output folder:",
    "export_same_as_source": "Source folder",
    "export_same_as_source_tooltip": ("Save each exported photo next to its own source file, instead of "
                                       "one shared folder — useful when the photos being exported come "
                                       "from different folders."),
    "export_reveal_in_finder": "Show in Finder after export",
    "batch_suffix_label": "Filename suffix:",
    "batch_format_label": "Format:",
    "batch_status_no_triplets": "No matched triplets found in this folder.",
    "batch_status_running": "Processing {i} / {n}…",
    "batch_status_done": "Done — {ok} succeeded, {failed} failed",
    "batch_status_cancelled": "Cancelled after {i} / {n}",
    "batch_error_no_input": "Select an input folder first.",
    "batch_error_no_output": "Select an output folder.",

    "status_auto_align_running": "Auto Align…",
    "status_locating_files": "Searching for missing files {i} / {n}…",
    "status_scan_capturing": "Scan: capturing…",
    "status_scan_capturing_channel": "Scan: capturing {channel} ({i} / {n})…",
    "status_scan_sampling_base": "Scan: sampling film base, {channel} ({i} / {n})…",
    "status_auto_align_all_done": "Auto-alignment complete.",
    "status_auto_align_failed": "Automatic alignment failed.",
    "status_exported": "Image exported: {path}",
    "status_settings_copied": "Settings copied",
    "status_settings_pasted": "Settings pasted to {n} photo(s)",
    "status_crop_pasted": "Crop pasted to {n} photo(s)",
    "status_photos_deleted": "{n} photo(s) deleted",
    "status_photos_reset": "{n} photo(s) reset",
    "status_photo_duplicated": "Photo duplicated",
    "status_photo_converted_to_trichrome": "Trichrome photo created",
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
    "export_dialog_title": "Export",
    "export_filter_png": "8-bit PNG (*.png)",
    "export_filter_jpg": "8-bit JPEG (*.jpg)",
    "export_filter_tiff": "16-bit TIFF (*.tiff)",

    "help_quickstart_title": "Guide",
    "help_search_placeholder": "Search the guide",
    "help_search_no_results": "No results",
    "help_search_result_count_one": "1 result",
    "help_search_result_count": "{n} results",
    "help_quickstart_content": """
<h3>Overview</h3>
<p>Trichr-o-matic is built first for <b>trichrome</b> recomposition: combining 3 separate R/G/B (or custom-filtered) shots into one color photo.</p>
<p>Its tools also work on any single photo. In <b>Solo</b> mode, the same Light, Color, Curves and Framing editing applies to an already-composed photo, film-scanned or digital.</p>
<h3>Light Mode &amp; Advanced Mode</h3>
<ul>
<li><b>Advanced mode</b> is the full app: every tool, multi-photo sessions, Batch Import and Scan.</li>
<li><b>Light mode</b> is a simplified, single-photo interface for a fast, distraction-free trichrome workflow. It shows only <b>Histogram</b>, <b>Files</b>, <b>Trichrome Process</b> and <b>Framing</b>, with no filmstrip, no extra panels and no session file to manage.</li>
</ul>
<p>Switch with <b>Window ▸ Switch to Light Mode</b> or <b>Switch to Advanced Mode</b>. Each mode keeps its own state: the Light mode photo stays separate from your Advanced session. Going back to Advanced mode offers to start a new session with that photo, or to reopen your last session.</p>
<h3>Processing Types</h3>
<p>The <b>Mode</b> selector in the <b>Files</b> block decides how each photo is processed:</p>
<ul>
<li><b>Solo</b>: a single, already-composed photo (color or B&amp;W), loaded and edited as-is. No channel recomposition.</li>
<li><b>Classic Trichrome</b>: 3 black &amp; white shots taken through Red, Green and Blue (or IR or custom) filters, recomposed into one color image.</li>
<li><b>Color Trichrome</b>: 3 real color photos, each keeping its own R, G or B channel (a "Harris Shutter" look), instead of being flattened to grayscale.</li>
</ul>
<p>Changing an existing photo's mode asks what to do with its image(s):</p>
<ul>
<li>From a Trichrome mode to Solo: pick which loaded channel to keep.</li>
<li>From Solo to a Trichrome mode: pick which channel the photo becomes.</li>
</ul>
<p>To build a Trichrome photo from existing Solo photos, select 1 to 3 of them in the filmstrip and choose <b>Convert to Trichrome Image</b> from the right-click menu. They are combined in filmstrip order (first → Red, second → Green, third → Blue). The originals stay unchanged.</p>
<h3>Sessions</h3>
<p>A <b>session</b> is everything you're working on: every imported photo, its settings and your current layout.</p>
<ul>
<li><b>File ▸ Save Session</b> (Cmd+S) writes it to a portable <b>.trirgb</b> file you can reopen later or move to another machine. <b>Save Session As…</b> (Cmd+Shift+S) saves a copy under a new name.</li>
<li><b>File ▸ Open Session…</b> (Cmd+O) loads one back. <b>New Session</b> (Cmd+N) starts over with a single blank photo.</li>
<li>The session name appears at the bottom right of the status bar. With unsaved changes, closing the app, opening another session or starting a new one asks whether to save first.</li>
<li>Almost every edit can be undone with <b>Cmd+Z</b>, and redone with <b>Cmd+Shift+Z</b>.</li>
</ul>
<h3>Export</h3>
<p>Click <b>Export…</b> at the top of the sidebar, or press <b>Cmd+E</b>.</p>
<ul>
<li><b>What</b>: the <i>current</i> photo, your <i>selection</i> (build it with Cmd+click or Cmd+A in the filmstrip), or <i>all</i> photos.</li>
<li><b>Format</b>: 8-bit PNG, 8-bit JPEG or 16-bit TIFF. The last format you chose is kept as the default.</li>
<li><b>Where</b>: a folder you choose, or next to each photo's own source file.</li>
</ul>
<p>Press <b>Enter</b> in the Export window to start. Progress shows in the status bar, and a sound plays when the export finishes.</p>
<h3>Import</h3>
<ul>
<li><b>Drag and drop</b>: drag image files from Finder onto the filmstrip, the grid view or the empty preview canvas to add them as Solo photos, one at a time.</li>
<li><b>Import Images…</b> (Cmd+I) opens the Batch Import window, for many photos at once, including whole Trichrome triplets.</li>
</ul>
<h4>Batch Import window</h4>
<p>Choose a <b>Processing Mode</b> (Solo, Classic Trichrome or Color Trichrome) for the whole batch. In Solo mode, select individual images or a folder. In Trichrome mode, pick how files are matched into R/G/B triplets:</p>
<ul>
<li><b>Automatic</b>: files are matched by filename, using <b>Auto-Import Rules</b> to decide which filter feeds which channel.</li>
<li><b>Sequential</b>: select files already grouped in triplets, in the order set by <b>Sequential Import Rule</b>.</li>
<li><b>Manual</b>: pick each of the 3 columns yourself.</li>
</ul>
<p>Click the <b>?</b> buttons next to each option for details, then <b>Import</b>. The new photos are added to the filmstrip after the current selection.</p>
<h4>Auto-Import Rules</h4>
<p>Decides which filter keyword in a filename feeds which channel for Automatic matching. Choose a built-in mapping (<b>RGB Trichrome</b>, <b>IR Trichrome</b>, <b>Aerochrome</b>) or define your own.</p>
<h4>Sequential Import Rule</h4>
<p>Decides which channel each file in a group of 3 goes to, for Sequential matching. R/G/B by default, or any of the other 5 orders.</p>
<p>If a session's source photos have been moved or renamed, the preview lists the missing files. Use <b>Locate…</b> to relink them.</p>
<h3>Layouts</h3>
<ul>
<li><b>Blocks</b>: every tool lives in its own movable block, in the left or right panel. Drag a block by its grip handle to reorder it, or move it to the other panel. A blue dashed line shows where it will land.</li>
<li>A block can be <b>collapsed</b> to its header, or <b>closed</b>. Use the <b>Tools</b> menu to bring a closed block back.</li>
<li>The toolbar buttons <b>Trichrome / Color Correction / Framing / Scan</b> (shortcuts <b>T / E / C / S</b>) jump to a saved layout for that task. Save your own arrangement under one of those names with <b>Window ▸ Layout Preset ▸ Save Layout as Preset…</b>. You can also save any number of named layouts.</li>
<li><b>Window ▸ Reset Layout</b> restores the default arrangement.</li>
</ul>
<h3>Tools</h3>
<p>Each tool below is in its own block (see Layouts above). A small icon button at the bottom of each block or section resets just that part. Hover over it for details. It greys out when there is nothing to reset.</p>
<h4>Trichrome Process</h4>
<p>The most detailed tool, where trichrome recomposition happens.</p>
<ul>
<li><b>Show Layer</b>, at the top of the block, toggles any combination of the 3 channels in the preview. At least one stays on. Unlike Solo Layer Preview, the result stays in full color.</li>
<li><b>R/G/B tabs</b>: pick the channel to edit. Each tab has 3 collapsible sections, and their open or closed state is shared across the tabs.</li>
</ul>
<p>The 3 sections of each tab:</p>
<ul>
<li><b>Light</b>: exposure, brightness, contrast, highlights, shadows, whites, blacks and gamma for that channel's black &amp; white image, applied before the composed image's own Light and Color.</li>
<li><b>Position</b>: offset X/Y, scale and rotation. Check <b>Move on Canvas</b> to control them on the preview: drag to move, Shift+scroll to scale, Alt/Option+scroll to rotate, or nudge with the arrow keys (hold Shift for a bigger step). While it's checked, arrow keys adjust alignment instead of navigating, and Move on Canvas follows the R/G/B tab you're viewing.</li>
<li><b>Geometry</b>: per-shot lens correction: Distortion (barrel or pincushion), Vertical and Horizontal perspective, and Aspect. Check <b>Stretch on Canvas</b> to click-drag on the preview and refine one area of this channel, starting from where you click. Each drag refines the result further. Only one of Move on Canvas or Stretch on Canvas can be active at a time.</li>
</ul>
<p>Below the tabs:</p>
<ul>
<li><b>Auto Align</b> aligns all 3 channels. With <b>Apply geometry to auto align</b> checked, it also solves Geometry.</li>
<li><b>Lock Layer Position</b> picks the channel that stays fixed as the anchor. Auto Align never moves it, but you can still reposition it by hand.</li>
<li>Each tab has its own <b>Solo Layer Preview</b> toggle, which shows just that channel in black &amp; white.</li>
</ul>
<h4>Histogram</h4>
<p>Live Y/R/G/B levels for the composed image, with clipping indicators and a per-pixel eyedropper. Each channel can also be viewed on its own.</p>
<h4>Light</h4>
<p>Exposure, brightness, contrast, highlights, shadows, whites, blacks and gamma for the composed image. A <b>Negative</b> toggle is in the header.</p>
<h4>Color</h4>
<p>Temperature, tint, saturation and a white balance eyedropper. A <b>Black &amp; White</b> toggle in the header makes a true luminance-based grayscale conversion.</p>
<h4>Framing</h4>
<p>Two sections:</p>
<ul>
<li><b>Crop</b>: pick an aspect ratio, straighten, mirror, and choose a grid overlay. Click <b>Activate</b> to drag and resize the crop rectangle on the canvas. <b>Enter</b> applies it, <b>Esc</b> cancels.</li>
<li><b>Geometry</b>: distortion, vertical and horizontal perspective, and aspect correction for the whole composed image. Works in every mode, including Solo. Click <b>Perspective correction</b> and draw up to 2 vertical and 2 horizontal guides along edges that should be straight. Drag an endpoint to adjust a guide, or double-click it to delete it. <b>Enter</b> solves and applies the correction, <b>Esc</b> cancels.</li>
</ul>
<h4>Curves</h4>
<p>A classic tone curve editor with independent Y (master), R, G and B curves. Click the diagonal to add a point and drag to reshape the curve, including its two endpoints for a true black or white point. Double-click a point to remove it.</p>
<h4>Scan</h4>
<p>Tethered capture from a camera connected over USB.</p>
<ul>
<li><b>Device</b> shows the live connection status. Once connected, <b>Camera Settings</b> shows whichever of Format, White Balance and Shutter Speed the camera supports.</li>
<li><b>Film</b> sets how each capture is processed on import: <b>Black &amp; White</b> (invert and a true grayscale conversion), <b>Color</b> (invert only), or <b>Color Reversal</b> (already positive, no change).</li>
<li><b>Scan Light</b> sets an optional on-screen backlight: <b>External</b>, a plain <b>White</b> light, or <b>RGB</b>, which runs an automatic red, green, blue 3-shot sequence into one trichrome triplet.</li>
<li><b>Film base</b> (color negatives): sample the film's clear base once, with a calibration sequence or by picking a point on an imported photo. <b>Correct for film base color on import</b> removes it from every later capture.</li>
</ul>
<p>Set the save folder, roll name and starting number under <b>Files Settings</b>, then click <b>Capture</b>. Captures are added to the current session automatically.</p>
<h3>Navigation &amp; Preview</h3>
<ul>
<li><b>Filmstrip</b>: imported photos appear under the preview. It shows automatically once there's more than one photo. Click a thumbnail (or use <b>←/→</b>) to edit that photo's own settings. Press <b>G</b> for a grid of every thumbnail (use <b>↑/↓</b> to move a row, <b>Esc</b> to leave).</li>
<li><b>Thumbnail menu</b>: right-click for <b>Copy</b>, <b>Paste</b>, <b>Paste Crop</b>, <b>Reset All</b>, <b>Duplicate</b> and <b>Delete</b>. Copy, Paste and Delete also have Cmd+C, Cmd+V and Cmd+Delete. <b>Reset All</b> clears a photo's alignment, color and crop. <b>Duplicate</b> makes a numbered copy, e.g. "(2)", to compare another edit side by side.</li>
<li><b>Zoom</b>: the preview opens at fit-to-window on launch and after each import. Use the zoom controls, or <b>Z</b> and <b>F</b>, to switch between Real Size and Fit.</li>
<li><b>HQ Preview</b> (<b>H</b>, or the toolbar button next to Zoom 100%) recomposes the photo at full resolution a moment after you stop editing, for a sharper preview.</li>
<li><b>Fullscreen</b> (Cmd+F) hides the side panels; press Esc to leave. <b>Compare</b> (the <b>:</b> key, or the toolbar button) temporarily shows the original, unedited image, to judge your changes.</li>
</ul>
""",

    "help_shortcuts_title": "Keyboard Shortcuts",
    # The "Files & Edit" section below is only half of this file's content -
    # the rest (New/Open/Save/Save As Session, Import, Export, Undo/Redo,
    # Copy/Paste, Rotate) is generated live from each real QAction's own
    # shortcut() by MainWindow._general_shortcuts_html() and spliced in at
    # %%GENERAL_SHORTCUTS_ITEMS%% - see show_shortcuts_dialog. Only bindings
    # with no derivable QAction shortcut() (Delete Selection/Close Window
    # have none at all; Quit's is empty by design, see
    # _general_shortcuts_html's own docstring) are still authored directly
    # here.
    "help_shortcuts_files_edit_static": (
        "<li><kbd>Cmd+Delete</kbd> — remove the selected photo(s)</li>"
        "<li><kbd>Cmd+W</kbd> — close the active window</li>"
        "<li><kbd>F1</kbd> — Guide</li>"
        "<li><kbd>Cmd+Q</kbd> — quit</li>"
    ),
    "shortcut_key_shift": "Shift",
    "shortcut_export_hint": "Enter/Return in that window starts the export",
    "shortcut_copy_paste_hint": "copy the current photo's settings, paste them onto the selected photos",
    "help_shortcuts_content": """
<h3>Files &amp; Edit</h3>
<ul>
%%GENERAL_SHORTCUTS_ITEMS%%
</ul>
<h3>View</h3>
<ul>
<li><kbd>T</kbd> / <kbd>E</kbd> / <kbd>C</kbd> / <kbd>S</kbd> — jump to your saved Trichrome /
Color Correction / Framing / Scan layout (see Window ▸ Layout Preset)</li>
<li><kbd>I</kbd> / <kbd>O</kbd> — show/hide the left/right side panel</li>
<li><kbd>P</kbd> — show/hide the thumbnail filmstrip</li>
<li><kbd>G</kbd> — toggle the thumbnail grid view</li>
<li><kbd>Cmd+F</kbd> — toggle fullscreen</li>
<li><kbd>Esc</kbd> — exit fullscreen or the grid view (whichever applies)</li>
<li><b>Drag</b> a block's grip handle — reorders it or moves it to the other side panel</li>
</ul>
<h3>Navigation</h3>
<ul>
<li><kbd>←</kbd> / <kbd>→</kbd> — go to the previous/next photo (hold <kbd>Shift</kbd> to extend
the export selection instead)</li>
<li><kbd>↑</kbd> / <kbd>↓</kbd> — move a row up/down while the grid view is active (hold
<kbd>Shift</kbd> to extend the export selection)</li>
<li><b>Drag</b> a thumbnail — reorders photos (switches to Custom sort order)</li>
<li><b>Drag</b> image files from Finder onto the filmstrip — adds them as new Solo
photos</li>
<li><b>Cmd+click</b> a thumbnail — add/remove it from the export selection</li>
<li><kbd>Cmd+A</kbd> — select all photos, or deselect all if every photo is already
selected</li>
</ul>
<h3>Preview</h3>
<ul>
<li><b>Ctrl + scroll</b>, or a trackpad <b>pinch</b> — zooms the preview</li>
<li><b>Two-finger scroll</b> on the trackpad — pans the preview once zoomed in</li>
<li><kbd>Cmd+Plus</kbd> / <kbd>Cmd+Minus</kbd> — zoom in/out (or use the toolbar buttons)</li>
<li><kbd>F</kbd> / <kbd>Z</kbd> — jump to Fit / 100% zoom (or use the toolbar buttons)</li>
<li><kbd>H</kbd> — toggle HQ Preview</li>
<li><kbd>:</kbd> — toggle Compare, showing the unedited original</li>
</ul>
<h3>Tools</h3>
<p><b>Double-click</b> any slider — resets it to its default value, in every tool below.</p>
<h4>Trichrome Process</h4>
<p>Pick the channel to work on from the R/G/B tabs.</p>
<ul>
<li><b>Drag</b> — moves the channel while <b>Move on Canvas</b> is checked, or locally
stretches it while <b>Stretch on Canvas</b> is checked</li>
<li><b>Arrow keys</b> — nudge the channel's position by a small step (hold <kbd>Shift</kbd>
for a bigger step), while <b>Move on Canvas</b> is checked</li>
<li><b>Shift + scroll</b> — scales the channel marked Move on Canvas</li>
<li><b>Alt/Option + scroll</b> — rotates the channel marked Move on Canvas</li>
</ul>
<h4>Framing</h4>
<ul>
<li><b>Drag</b> — resizes the crop rectangle, or draws/edits a perspective guide line</li>
<li><kbd>Enter</kbd> — apply the crop rectangle or the perspective correction, whichever
is active</li>
<li><kbd>Esc</kbd> — cancel the active crop or perspective correction, without changing
anything</li>
</ul>
<h4>Color</h4>
<ul>
<li><kbd>W</kbd> — toggle the White Balance eyedropper</li>
</ul>
""",

    # --- Scan tool (standalone test window) ---
    "scan_window_title": "Scan Tool (test)",
    "scan_wip_notice": "This tool is still under development — some errors or unexpected behavior may occur.",
    "scan_device_group": "Device",
    "scan_device_not_connected": "Not connected",
    "scan_device_connected": "Connected: {model}",
    "scan_device_refresh": "Refresh",
    "scan_camera_settings_group": "Camera Settings",
    "scan_white_balance_label": "White Balance",
    "scan_shutter_speed_label": "Shutter Speed",
    "scan_mode_group": "Film",
    "scan_mode_bw": "B&W",
    "scan_mode_color": "Color",
    "scan_mode_color_reversal": "Color Reversal",
    "scan_mode_invert_note": "Invert will be applied automatically on import for this mode.",
    "scan_mode_no_invert_note": "No invert needed on import for this mode (already positive).",
    "scan_mode_note_bw": "Invert and Black & White will be applied automatically on import.",
    "scan_mode_note_color": "Invert will be applied automatically on import.",
    "scan_mode_note_color_reversal": "Photo will be imported without changes.",
    "scan_light_group": "Scan Light",
    "scan_light_external": "External",
    "scan_light_white": "White",
    "scan_light_rgb": "RGB",
    "scan_light_rgb_note": "Capture will automatically take 3 shots in sequence - red, green, then blue light - and return to white light afterward. All 3 share the same number, suffixed _R/_G/_B.",
    "scan_light_window_title": "Scan Backlight",
    "scan_sample_base_button": "Sample Film Base",
    "scan_sample_base_tooltip": (
        "Place the film's clear, unexposed base (the rebate/leader) under "
        "the light, then click - captures a quick 3-shot RGB reference used "
        "to correct the base/mask color (e.g. color negative's orange mask) "
        "on later RGB Light imports."
    ),
    "scan_sample_base_requires_rgb_light": (
        "Select RGB Light first, then place the film's clear/unexposed base "
        "under the light and click again."
    ),
    "scan_film_base_status_not_set": "Film base: not sampled yet",
    "scan_film_base_status_set": "Film base sampled — R {r} · G {g} · B {b}",
    "scan_apply_film_base_checkbox": "Correct for film base color on import",
    "scan_apply_film_base_tooltip": (
        "Removes the sampled film base's color bias (e.g. the orange mask "
        "on color negative film) from each RGB Light channel before "
        "inverting, using the sampled reference above. Applied to every "
        "RGB Light photo added to the session while checked."
    ),
    "scan_capturing_channel_status": "Capturing {channel}…",
    "scan_process_checkbox": "Also save a processed JPG preview",
    "scan_process_tooltip": "Saves an extra JPG copy in a \"processed\" subfolder: grayscale + inverted for Black & White, inverted for Color, as-is for Color Reversal. For an RGB Light triplet, recomposes the 3 shots into one trichrome image using the app's own auto-align + compose algorithm.",
    "scan_processing_status": "Processing…",
    "scan_processed_label": "Processed",
    "scan_location_group": "Files Settings",
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
    "scan_select_folder_prompt_title": "Select a folder to save your scans",
    "scan_pick_film_base_tooltip": (
        "Alternative to Sample Film Base: click here, then click a clear/"
        "unexposed point on a Trichrome photo already in the session "
        "(instead of taking 3 new calibration shots). Applies to the next "
        "capture, same as a dedicated sample."
    ),
    "scan_pick_film_base_requires_trichrome": (
        "Select a Trichrome photo with all 3 R/G/B channels loaded first."
    ),
    "status_film_base_picked": "Film base sampled from photo.",
}

FR = {
    "channel_r": "Rouge",
    "channel_g": "Vert",
    "channel_b": "Bleu",

    "load_image_button": "Charger une image…",
    "change_image_button": "Changer l'image",
    "no_image_loaded": "Aucune image chargée",
    "channel_swap_handle_tooltip": "Glisser sur le nom de fichier d'un autre canal pour échanger leurs images",
    "active_checkbox": "Déplacer sur le canevas",
    "active_layer_info": (
        "<b>Déplacer sur le canevas</b><br>"
        "<span style=\"color:#9a9a9a;\">Le calque qui réagit quand on glisse, qu'on "
        "utilise la molette ou les flèches du clavier directement sur le canevas de "
        "l'aperçu. Un seul calque peut être actif à la fois - cochez Déplacer sur le "
        "canevas sur un autre calque pour changer, ou changez simplement d'onglet R/V/B : "
        "tant que c'est coché, ça suit automatiquement l'onglet affiché</span>"
        "<br><br>"
        "<b>Glisser</b><br>"
        "<span style=\"color:#9a9a9a;\">Déplace le calque actif</span>"
        "<br><br>"
        "<b>Maj + molette</b><br>"
        "<span style=\"color:#9a9a9a;\">Met le calque actif à l'échelle</span>"
        "<br><br>"
        "<b>Alt + molette</b><br>"
        "<span style=\"color:#9a9a9a;\">Fait pivoter le calque actif</span>"
        "<br><br>"
        "<b>Flèches du clavier</b><br>"
        "<span style=\"color:#9a9a9a;\">Micro-règlent la position du calque actif "
        "(maintenez Maj pour un pas plus grand). Quand Déplacer sur le canevas est coché, "
        "les 4 flèches contrôlent l'alignement au lieu de leur navigation habituelle</span>"
        "<br><br>"
        "<b>Calque verrouillé</b><br>"
        "<span style=\"color:#9a9a9a;\">Exclu uniquement de l'alignement automatique - il "
        "peut toujours être rendu actif et repositionné manuellement (voir Position "
        "verrouillée)</span>"
    ),
    "stretch_checkbox": "Étirer sur le canevas",
    "stretch_layer_info": (
        "<b>Étirer sur le canevas</b><br>"
        "<span style=\"color:#9a9a9a;\">Cliquez et glissez directement sur le canevas de "
        "l'aperçu pour étirer localement le calque actif, à partir du point exact cliqué - "
        "permet d'affiner précisément une zone sans perturber le reste de l'image. Un seul "
        "calque peut être actif à la fois - cochez Étirer sur le canevas sur un autre calque "
        "pour changer, ou changez simplement d'onglet R/V/B : tant que c'est coché, ça suit "
        "automatiquement l'onglet affiché. Cocher ceci décoche Déplacer sur le canevas (et "
        "inversement) - un glissement sur le canevas ne peut faire que l'un ou l'autre</span>"
        "<br><br>"
        "<b>Glisser</b><br>"
        "<span style=\"color:#9a9a9a;\">Tire l'image à partir du point cliqué vers le "
        "curseur - une grille de référence montre la déformation en direct. Glissez à nouveau "
        "ailleurs pour affiner davantage, sans annuler le glissement précédent</span>"
        "<br><br>"
        "<b>Réinitialiser</b><br>"
        "<span style=\"color:#9a9a9a;\">Le bouton Réinitialiser de la section Géométrie "
        "efface tous les glissements d'étirement en même temps que les 4 curseurs ci-dessus</span>"
    ),
    "stretch_on_canvas_indicator_label": "Glissez sur le canevas pour étirer le calque {channel}, à partir du point cliqué",
    "solo_checkbox": "Aperçu Solo du calque (N&&B)",
    "invert_checkbox_tooltip": "Négatif (inverser le scan) — inverse les tons des 3 calques, pour des scans de négatif brut, non inversés.",
    "alignment_group": "Alignement",
    "position_group": "Position",
    "offset_x": "Décalage X",
    "offset_y": "Décalage Y",
    "scale_label": "Échelle",
    "rotation_label": "Rotation (°)",
    "distortion_group": "Géométrie",
    "distortion_label": "Distorsion",
    "perspective_v_label": "Vertical",
    "perspective_h_label": "Horizontal",
    "anamorphic_label": "Aspect",
    "auto_align_button": "Alignement automatique",
    "auto_align_apply_distortion_checkbox": "Appliquer la géométrie à l'alignement auto",
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
    "crop_mirror_label": "Miroir",
    "crop_section_title": "Rognage",
    "crop_geometry_section_title": "Géométrie",
    "reset_crop_geometry_tooltip": "Réinitialiser la géométrie (Distorsion, Vertical, Horizontal, Aspect)",
    "crop_perspective_tooltip": "Correction de perspective",
    "perspective_indicator_label": "Perspective : tracez jusqu'à 2 guides verticaux et 2 horizontaux le long de lignes qui doivent être droites - double-clic sur un guide pour le supprimer - Entrée pour appliquer, Échap pour annuler",
    "status_perspective_need_two_guides": "Tracez 2 guides verticaux ou 2 guides horizontaux",
    "status_perspective_applied": "Perspective corrigée",
    "crop_mirror_h_button": "Miroir gauche/droite",
    "crop_mirror_v_button": "Miroir haut/bas",
    "crop_grid_label": "Grille :",
    "crop_grid_off": "Aucune",
    "crop_grid_3x3": "3 × 3",
    "crop_grid_2x2": "2 × 2",
    "crop_grid_golden": "Nombre d'or",
    "crop_grid_squares": "Grille",
    "crop_reset_tooltip": "Réinitialiser le recadrage",
    "crop_activate_tooltip": "Activer/désactiver le mode rognage",
    "curves_group_title": "Courbes",
    "curves_reset_tooltip": "Réinitialiser la courbe",
    "saturation_label": "Saturation",
    "temperature_label": "Température",
    "tint_label": "Teinte (magenta/vert)",
    "export_button": "Exporter…",

    "zoom_in": "Zoom avant",
    "zoom_out": "Zoom arrière",
    "zoom_fit_tooltip": "Ajuster à la fenêtre (F)",
    "zoom_100": "100 % (taille réelle) (Z)",
    "hq_preview_tooltip": "Aperçu HQ (H) : affiche la photo en pleine résolution peu après l'arrêt de l'édition, calculé en arrière-plan",
    "hq_preview_failed": "Impossible de calculer l'aperçu HQ : {error}",
    "rotate_left_tooltip": "Rotation à gauche (⌘L)",
    "rotate_right_tooltip": "Rotation à droite (⌘R)",
    "fullscreen_button": "Plein écran (⌘F)",
    "exit_fullscreen_button": "Quitter le plein écran (⌘F)",
    "compare_tooltip": "Comparer (:)",
    "compare_indicator_label": "Affichage de l'original",
    "move_on_canvas_indicator_label": "Faites glisser le calque {channel} sur le canevas pour le repositionner",
    "menu_view": "Affichage",
    "menu_view_zoom_in": "Zoom avant",
    "menu_view_zoom_out": "Zoom arrière",
    "menu_view_zoom_fit": "Ajuster à la fenêtre",
    "menu_view_zoom_100": "Zoom 100 %",
    "menu_view_hq_preview": "Aperçu HQ",
    "menu_view_compare": "Comparer",
    "menu_view_fullscreen": "Plein écran",
    "menu_view_exit_fullscreen": "Quitter le plein écran",
    "menu_view_thumbnails": "Afficher/masquer les vignettes",
    "menu_view_grid": "Vue en grille",
    "status_saving_session": "Sauvegarde de la session…",
    "status_loading_session": "Chargement de la session…",
    "status_session_loaded": "Session chargée",
    "status_exporting": "Export {i} / {n}…",
    "menu_settings": "Préférences…",
    "settings_title": "Préférences",
    "settings_section_general": "Général",
    "settings_language": "Langue",
    "settings_reopen_last_session": "Rouvrir la dernière session au lancement",
    "settings_quick_tour_at_startup": "Afficher la présentation au démarrage",
    "settings_check_updates_at_startup": "Rechercher les mises à jour au démarrage",
    "settings_play_sounds": "Jouer un son à l'enregistrement, à la suppression et à l'export",
    "settings_section_sessions": "Sessions",
    "settings_session_preview_cache": "Enregistrer les aperçus dans les fichiers de session",
    "settings_session_preview_cache_help": "Les sessions s'ouvrent beaucoup plus vite. Ajoute environ 350 Ko par photo au fichier .trirgb. Les exports et l'aperçu HQ utilisent toujours vos fichiers originaux.",
    "settings_section_export": "Export",
    "settings_export_help": "Utilisés par la fenêtre d'export, qui retient aussi les dernières valeurs que vous y avez choisies.",
    "settings_done_button": "Terminé",
    "settings_section_experimental": "Expérimental",
    "settings_experimental_info": "Fonctionnalités encore en développement. Elles peuvent être incomplètes, changer, ou ne pas fonctionner avec toutes les configurations. Activez-en une seulement si vous voulez l'essayer en avance.",
    "settings_scan_tool_enabled": "Activer l'outil Scan",
    "settings_scan_tool_enabled_help": "Numérisation de film avec un appareil photo relié en USB. Ajoute le bouton Scan dans la barre d'outils, le raccourci S et ses entrées dans les menus Outils et Fenêtre.",
    "settings_scan_tool_busy_title": "Capture en cours",
    "settings_scan_tool_busy_text": "L'outil Scan ne peut pas être désactivé pendant une capture. Attendez la fin de la capture, puis réessayez.",
    "settings_export_format": "Format par défaut",
    "settings_export_suffix": "Suffixe du fichier",
    "status_updating_previews": "Mise à jour des aperçus {i} / {n}…",
    "status_export_finished": "Export : {status}",
    "status_hq_preview_loading": "Chargement de l'aperçu HQ…",
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
    "crop_toolbar_tooltip": "Recadrage (C)",
    "scan_toolbar_tooltip": "Scan (S)",
    "right_panel_toggle_tooltip": "Afficher/masquer le panneau de droite",
    "help_toolbar_tooltip": "Aide (F1)",
    "canvas_placeholder": 'Charger une image via le bouton "importer" ou glisser ici un fichier image',
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
        "pour la ou les photos concernées, depuis le panneau Traitement "
        "Trichrome à gauche."
    ),
    "dialog_locate_failed_column_photo": "Photo",
    "dialog_locate_failed_column_channel": "Canal",

    "black_white_button_tooltip": "Noir et Blanc",
    "pick_white_balance_tooltip": "Balance des blancs à la pipette (W) - cliquez un point de l'aperçu qui devrait être gris neutre",
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
    "menu_convert_to_trichrome": "Convertir en image trichrome",
    "menu_tools": "Outils",
    "menu_tools_crop": "Recadrage",
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
    "menu_quickstart_action": "Guide",
    "menu_shortcuts_action": "Raccourcis clavier",
    "menu_check_updates_action": "Rechercher les mises à jour…",
    "update_check_window_title": "Rechercher les mises à jour",
    "update_check_current_version": "Version {version}",
    "update_check_checking": "Recherche de mises à jour…",
    "update_check_up_to_date": "Vous êtes à jour.",
    "update_check_available": "La version {version} est disponible.",
    "update_check_failed": "Impossible de vérifier les mises à jour. Vérifiez votre connexion internet et réessayez.",
    "update_check_update_button": "Mettre à jour…",
    "update_check_close": "Fermer",
    "menu_quick_tour_action": "Présentation",
    "quick_tour_welcome_window_title": "Bienvenue",
    "quick_tour_welcome_title": "Bienvenue dans Trichr-o-matic",
    "quick_tour_version": "Version {version}",
    "quick_tour_welcome_text": (
        "Trichr-o-matic est une application pensée pour le traitement de la photographie trichrome. Importer les couches R/V/B, les aligner et étalonner vos photos : tout cela est possible avec Trichr-o-matic, et bien plus encore.\n\nCommencez la présentation pour en savoir plus."
    ),
    "quick_tour_open_at_startup": "Ouvrir au démarrage",
    "quick_tour_close": "Fermer",
    "quick_tour_start": "Commencer la présentation",
    "quick_tour_step": "Étape {n} / {total}",
    "quick_tour_in_progress": "En cours de développement",
    "quick_tour_skip": "Passer la présentation",
    "quick_tour_back": "Retour",
    "quick_tour_next": "Suivant",
    "quick_tour_finish": "Terminer",
    "quick_tour_light_diagram_caption": "Disposition du mode Light : un panneau, une photo.",
    "quick_tour_sessions_title": "Sessions",
    "quick_tour_sessions_body": (
        "Trichr-o-matic fonctionne à partir de sessions, enregistrées dans des fichiers .trirgb.\n\nDans la barre d'outils, les icônes à gauche vous permettent de créer une nouvelle session (<kbd>⌘N</kbd>), d'ouvrir une session existante (<kbd>⌘O</kbd>) ou d'enregistrer la session en cours (<kbd>⌘S</kbd>)."
    ),
    "quick_tour_toolbar_title": "Import et export",
    "quick_tour_toolbar_body": (
        "Le bouton Importer est à gauche de la barre d'outils. Le bouton Exporter est à droite."
    ),
    "quick_tour_workspaces_title": "Espaces de travail",
    "quick_tour_workspaces_body": (
        "Quatre espaces de travail organisent les outils selon une disposition prédéfinie : Trichromie, Étalonnage, Recadrage et Scan (raccourcis <kbd>T</kbd> <kbd>E</kbd> <kbd>C</kbd> <kbd>S</kbd>).\n\nChacun affiche par défaut les panneaux utiles à sa tâche.\n\nPour créer votre propre disposition, réorganisez les panneaux, puis enregistrez-la depuis Fenêtre ▸ Préréglage de disposition."
    ),
    "quick_tour_workspaces_body_no_scan": (
        "Trois espaces de travail organisent les outils selon une disposition prédéfinie : Trichromie, Étalonnage et Recadrage (raccourcis <kbd>T</kbd> <kbd>E</kbd> <kbd>C</kbd>).\n\nChacun affiche par défaut les panneaux utiles à sa tâche.\n\nPour créer votre propre disposition, réorganisez les panneaux, puis enregistrez-la depuis Fenêtre ▸ Préréglage de disposition."
    ),
    "quick_tour_preview_title": "Aperçu",
    "quick_tour_preview_body": (
        "La fenêtre principale affiche le résultat et se met à jour au fil de vos réglages.\n\n<kbd>F</kbd> ajuste l'image à la fenêtre, <kbd>Z</kbd> l'affiche en taille réelle et <kbd>⌘F</kbd> passe en plein écran.\n\nCertains outils agissent directement sur l'image : déplacer ou étirer une couche dans le Traitement Trichrome, recadrer la photo, ou choisir une référence pour la balance des blancs."
    ),
    "quick_tour_filmstrip_title": "Photos et affichage",
    "quick_tour_filmstrip_body": (
        "Chaque photo de la session a sa vignette ici : cliquez pour changer de photo, glissez pour réordonner, clic droit pour plus d'options.\n\nLa barre du dessous gère le zoom, l'aperçu HQ, la rotation, la comparaison avant/après, le plein écran, le tri et la vue en grille (<kbd>G</kbd>)."
    ),
    "quick_tour_files_title": "Fichiers",
    "quick_tour_files_body": (
        "Choisissez le mode de traitement :<br><b>Solo</b> : une photo standard, déjà composée<br><b>Trichromie Classique</b> : 3 photos noir et blanc<br><b>Trichromie Couleur</b> : un canal de chacune de 3 photos couleur\n\nEn mode trichrome, importez ou remplacez les fichiers de chaque couche R/V/B. Glissez la poignée d'un fichier sur un autre canal pour échanger les deux."
    ),
    "quick_tour_channels_title": "Traitement Trichrome",
    "quick_tour_channels_body": (
        "L'outil principal de l'application.\n\nPour chaque couche, vous pouvez corriger l'étalonnage, la repositionner ou modifier sa géométrie afin d'obtenir un alignement parfait.\n\n<b>Alignement auto</b> aligne les couches automatiquement. Des ajustements manuels peuvent être requis.\n\n<b>Position verrouillée</b> fixe la couche de référence, qui ne bougera pas.\n\nAffichez chaque couche séparément grâce aux boutons en haut de l'outil."
    ),
    "quick_tour_histogram_title": "Histogramme",
    "quick_tour_histogram_body": (
        "Affiche les tons de l'image en direct.\n\nCliquez sur le bouton Y/R/V/B pour isoler une couche.\n\nUtilisez la pipette pour lire une valeur précise sur l'aperçu."
    ),
    "quick_tour_crop_title": "Recadrage",
    "quick_tour_crop_body": (
        "Recadrage : cliquez sur l'icône de recadrage, ou activez le mode recadrage avec la touche <kbd>C</kbd>. Recadrez dans l'aperçu, puis validez avec <kbd>Entrée</kbd>.\n\nGéométrie : distorsion, perspective verticale et horizontale, et correction d'aspect pour toute l'image composée."
    ),
    "quick_tour_light_title": "Lumière",
    "quick_tour_light_body": (
        "Ajustement d'exposition, de luminosité, de contraste, des hautes lumières, des ombres, des blancs, des noirs et du gamma pour l'image composée.\n\nLe bouton Négatif dans l'en-tête transforme l'image en négatif."
    ),
    "quick_tour_color_title": "Couleur",
    "quick_tour_color_body": (
        "Ajustement de température, teinte et saturation pour l'image composée.\n\nUtilisez la pipette de balance des blancs pour cliquer sur une zone neutre de l'image.\n\nLe bouton de l'en-tête convertit en noir et blanc."
    ),
    "quick_tour_curves_title": "Courbes",
    "quick_tour_curves_body": (
        "Réglage fin des tons sur la courbe principale (Y) ou sur chaque canal R, V et B.\n\nCliquez sur la ligne pour ajouter un point, glissez pour la modeler, double-cliquez un point pour le supprimer."
    ),
    "quick_tour_scan_title": "Scan",
    "quick_tour_scan_body": (
        "Numérisez vos films avec un appareil photo relié en USB. Choisissez le type de film et "
        "l'éclairage ; avec la lumière RVB, chaque capture prend automatiquement les trois vues "
        "d'une trichromie. Les captures arrivent directement dans votre session.\n\n"
        "L'espace de travail Scan (<kbd>S</kbd>) l'affiche à côté de l'Histogramme et du Recadrage. "
        "Cet outil est encore en construction : certaines options manquent et peuvent changer."
    ),
    "quick_tour_arrange_title": "Organisez votre espace de travail",
    "quick_tour_arrange_body": (
        "Réorganisez votre espace de travail en glissant un bloc par sa poignée. Déposez-le à l'endroit de votre choix, dans le panneau de votre choix.\n\nRéduisez un bloc avec la flèche, ou fermez-le avec la croix.\n\nRouvrez un bloc fermé depuis le menu Outils.\n\nPour enregistrer votre propre espace de travail, allez dans Fenêtre ▸ Préréglage de disposition.\n\nLes deux boutons en haut à droite masquent les panneaux latéraux (<kbd>I</kbd> pour le panneau gauche, <kbd>O</kbd> pour le droit)."
    ),
    "quick_tour_batch_title": "Fenêtre d'import",
    "quick_tour_batch_body": (
        "Ouvrez la fenêtre d'import avec <kbd>⌘I</kbd> ou le bouton en haut à gauche.\n\nChoisissez le mode de traitement :<br><b>Solo</b> : une photo standard, déjà composée<br><b>Trichromie Classique</b> : 3 photos noir et blanc<br><b>Trichromie Couleur</b> : un canal de chacune de 3 photos couleur\n\nPour les modes trichrome, choisissez la façon de regrouper les triplets en une photo trichrome :<br><b>Automatique</b> (selon le nom du filtre dans le nom de fichier)<br><b>Séquentiel</b> (fichiers déjà dans l'ordre)<br><b>Manuelle</b>\n\nCochez l'<b>alignement automatique</b> pour aligner chaque photo à l'import."
    ),
    "quick_tour_light_mode_title": "Mode Light",
    "quick_tour_light_mode_body": (
        "Activez-le depuis <kbd>Fenêtre</kbd> ▸ <kbd>Passer en mode Light</kbd>, et revenez de la même façon avec <kbd>Fenêtre</kbd> ▸ <kbd>Passer en mode Avancé</kbd>.\n\nLe mode Light est une version simplifiée de l'app pour travailler une image trichromie à la fois : les quatre blocs essentiels et l'aperçu.\n\nLes sessions, les vignettes et l'import par lot sont masqués, et votre session en mode Avancé reste intacte."
    ),
    "quick_tour_light_mode_body_light": (
        "Revenez à l'app complète depuis <kbd>Fenêtre</kbd> ▸ <kbd>Passer en mode Avancé</kbd>.\n\n"
        "Vous êtes en mode Light, une version simplifiée de l'app pour une trichromie à la fois : les "
        "quatre blocs essentiels et l'aperçu. Le mode Avancé ajoute les sessions, les vignettes, "
        "l'import par lot et tous les outils."
    ),
    "quick_tour_ready_title": "C'est parti",
    "quick_tour_ready_body": (
        "Relancez cette présentation à tout moment depuis <b>Aide ▸ Présentation</b> ou ce bouton.\n\nLe Guide et la liste complète des raccourcis clavier s'y trouvent aussi."
    ),
    "quick_tour_ready_body_light": (
        "Relancez cette présentation à tout moment depuis <b>Aide ▸ Présentation</b>. La Prise en "
        "main et la liste complète des raccourcis clavier sont aussi dans le menu Aide."
    ),
    "menu_batch": "Importer des images…",
    "menu_switch_to_light_mode": "Passer en mode Light",
    "menu_switch_to_advanced_mode": "Passer en mode Avancé",
    "light_mode_exit_confirm_title": "Passer en mode Avancé",
    "light_mode_exit_confirm_text": (
        "Commencer une nouvelle session avec la photo actuelle, ou ouvrir votre dernière session à la place ?"
    ),
    "light_mode_exit_new_session_button": "Nouvelle session avec cette photo",
    "light_mode_exit_open_last_button": "Ouvrir la dernière session",
    "light_mode_reset_channels_tooltip": "Effacer les images Rouge, Verte et Bleue",
    "double_click_reset_hint": "Double-cliquez pour réinitialiser",

    "independent_channels_group_title": "Traitement Trichrome",
    "import_panel_title": "Fichiers",
    "mode_solo_option": "Solo",
    "mode_bw_trichrome_option": "Trichromie Classique",
    "mode_color_trichrome_option": "Trichromie Couleur",
    "mode_select_info": (
        "<b>Solo</b><br>"
        "<span style=\"color:#9a9a9a;\">Une seule photo déjà composée, chargée et éditée "
        "telle quelle - aucune recomposition de canaux</span>"
        "<br><br>"
        "<b>Trichromie Classique</b><br>"
        "<span style=\"color:#9a9a9a;\">Combine 3 photos noir et blanc prises avec des filtres "
        "colorés pour recomposer une image couleur</span>"
        "<br><br>"
        "<b>Trichromie Couleur</b><br>"
        "<span style=\"color:#9a9a9a;\">Simule des filtres RGB à partir de 3 photos couleur, "
        "chacune gardant son propre canal réel, pour créer un &quot;Harris Shutter Effect&quot;</span>"
    ),
    "normal_file_path_label": "Chemin du fichier :",
    "status_photo_added": "Photo ajoutée",
    "status_photos_added": "{n} photo(s) ajoutée(s)",
    "dialog_drop_photos_failed_text": "Impossible de charger le(s) fichier(s) suivant(s) :\n{files}",
    "normal_photo_label": "Photo",
    "channels_disabled_normal_mode": "Cet outil est disponible uniquement pour les photographies trichrome",
    "mode_switch_dialog_title": "Changement de mode",
    "mode_switch_dialog_text": (
        "Êtes-vous sûr de vouloir repasser en mode Solo ? Choisissez le "
        "calque que vous souhaitez continuer d'éditer :"
    ),
    "mode_switch_to_trichrome_dialog_text": (
        "Êtes-vous sûr de vouloir basculer en mode {mode} ? À quelle "
        "couche souhaitez-vous attribuer cette image ?"
    ),
    "mode_switch_channel_button": "Calque {channel}",
    "mode_switch_cancel_button": "Annuler",
    "block_collapse_tooltip": "Réduire/Développer",
    "block_close_tooltip": "Retirer de l'affichage",
    "menu_tools_histogram": "Histogramme",
    "reset_all_alignment_tooltip": "Réinitialiser l'alignement de toutes les couches",
    "reset_all_color_tooltip": "Réinitialiser les couleurs de toutes les couches",
    "reset_position_tooltip": "Réinitialiser la position (Décalage X, Décalage Y, Échelle, Rotation)",
    "reset_distortion_tooltip": "Réinitialiser la distorsion (Distorsion, Vertical, Horizontal, Aspect)",
    "reset_stretch_tooltip": "Réinitialiser uniquement l'étirement sur le canevas",
    "reset_tone_tooltip": "Réinitialiser la lumière (Exposition, Luminosité, Contraste, Hautes lumières, "
                          "Ombres, Blancs, Noirs, Gamma)",
    "lock_layer_position_label": "Position verrouillée :",
    "lock_layer_position_info": "L'alignement automatique ne déplace jamais la couche verrouillée - "
                                 "il aligne les deux autres dessus, en conservant la position "
                                 "manuelle déjà réglée. Vous pouvez toujours modifier manuellement "
                                 "l'alignement de la couche verrouillée. Une seule couche est "
                                 "toujours verrouillée ; changez-la à tout moment.",
    "display_layer_label": "Afficher la couche :",

    "batch_window_title": "Import",
    "batch_import_button": "Importer",
    "batch_import_status_running": "Import {i} / {n}…",
    "batch_import_status_done": "{n} photo(s) importée(s).",
    "carousel_empty_hint": "Aucune photo importée — utilisez le bouton « Importer… » en haut de la barre latérale.",
    "carousel_toggle_tooltip": "Afficher/masquer les vignettes",
    "grid_view_toggle_tooltip": "Vue en grille (G)",
    "sort_button_tooltip": "Trier les vignettes",
    "sort_by_filename": "Par nom de fichier",
    "sort_by_capture_date": "Par date de capture",
    "sort_by_import_order": "Par ordre d'importation",
    "sort_by_custom": "Ordre personnalisé",
    "sort_reverse_order": "Ordre inversé",
    "export_scope_current": "Exporter la photo actuelle",
    "export_scope_selected": "Exporter la sélection ({n})",
    "export_scope_all": "Exporter tout ({n})",
    "export_confirm_button": "Exporter",
    "export_no_items": "Aucune photo à exporter.",
    "export_already_running": "Un export est déjà en cours. Attendez qu'il se termine (voir la barre d'état) avant d'en lancer un autre.",
    "export_failures_text": "{failed} photo(s) sur {n} n'ont pas pu être exportée(s).",
    "export_failures_photo_header": "Photo",
    "export_failures_error_header": "Erreur",
    "export_quit_confirm_title": "Export en cours",
    "export_quit_confirm_text": "Un export est toujours en cours. Quitter maintenant l'arrêtera après la photo en cours d'enregistrement.",
    "export_quit_confirm_button": "Arrêter l'export et quitter",
    "close_button": "Fermer",
    "batch_mode_auto_radio": "Automatique",
    "batch_mode_semi_radio": "Séquentiel",
    "batch_mode_manual_radio": "Manuelle",
    "batch_mode_info": (
        "<b>Automatique</b> — les fichiers sont regroupés grâce à un indicateur de filtre présent "
        "dans leur nom (Rouge, Vert, Bleu, Jaune ou Infrarouge - à n'importe quelle position, sans "
        "tenir compte de la casse). Le filtre qui remplit chaque canal R/V/B dépend du mode choisi "
        "dans <b>Règles d'Import</b> ci-dessous (Classique, Trichrome IR, Aerochrome…). Les fichiers "
        "partageant un nom identique une fois cet indicateur retiré forment un triplet ; sinon, une "
        "séquence numérotée simple (Image1, Image2, Image3…) est regroupée 3 fichiers pertinents à "
        "la fois, dans l'ordre.<br><br>"
        "<b>Séquentiel</b> — sélectionnez un lot d'images en une fois, déjà dans l'ordre R, V, "
        "B, R, V, B… (glissez pour réordonner si besoin) : les 3 premières forment un triplet, les 3 "
        "suivantes le triplet suivant, etc.<br><br>"
        "<b>Manuelle</b> — choisissez les fichiers des colonnes R, V et B indépendamment, utile quand "
        "les noms de fichiers ne suivent aucune convention. La ligne N de chaque colonne forme un "
        "triplet."
    ),
    "batch_advanced_options_title": "Règles d'Import Auto",
    "batch_auto_import_rules_info": (
        "<b>Règles d'Auto-Import</b><br>"
        "<span style=\"color:#9a9a9a;\">Permet de définir les paramètres de détection automatique "
        "des fichiers et leur attribution dans les Canaux RVB</span>"
    ),
    "batch_semi_import_rule_title": "Règle d'Import Séquentiel",
    "batch_semi_import_rule_info": (
        "<b>Règle d'Import Séquentiel</b><br>"
        "<span style=\"color:#9a9a9a;\">Permet de choisir l'ordre d'attribution de chaque groupe de "
        "3 fichiers dans les Canaux RVB</span>"
    ),
    "batch_advanced_options_info": (
        "<b>Trichrome RVB</b><br>"
        "<span style=\"color:#9a9a9a;\">Correspondance standard - les photos filtrées R, V et B "
        "remplissent directement les canaux R, V et B</span>"
        "<br><br>"
        "<b>Trichrome IR</b><br>"
        "<span style=\"color:#9a9a9a;\">Le canal Rouge est rempli par une photo filtrée infrarouge "
        "à la place - le Vert et le Bleu restent standards</span>"
        "<br><br>"
        "<b>Aerochrome</b><br>"
        "<span style=\"color:#9a9a9a;\">Simule la correspondance décalée du film Kodak Aerochrome - "
        "canal Rouge depuis l'Infrarouge, Vert depuis le Rouge, Bleu depuis le Vert</span>"
        "<br><br>"
        "<b>Personnalisé</b><br>"
        "<span style=\"color:#9a9a9a;\">Assignez librement quel filtre alimente chaque canal, à "
        "partir des filtres définis ci-dessous</span>"
    ),
    "batch_advanced_mode_classic": "Trichrome RVB",
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
    "batch_semi_hint": ("Les fichiers sont regroupés 3 par 3, dans l'ordre affiché — glissez pour "
                         "réordonner. Définissez l'ordre des canaux dans la Règle d'Import Séquentiel "
                         "ci-dessous."),
    "batch_semi_invalid_count": "{n} fichiers sélectionnés — ce n'est pas un multiple de 3 ({remainder} fichier(s) en trop seront ignorés).",
    "batch_semi_select_title": "Sélectionner des images",
    "batch_manual_add_button": "Ajouter des fichiers…",
    "batch_manual_remove_button": "Retirer la sélection",
    "batch_manual_clear_button": "Vider",
    "batch_manual_hint": ("Déposez des fichiers image sur une colonne pour les ajouter, ou glissez les "
                           "éléments dans une colonne pour les réordonner."),
    "batch_select_files_title": "Sélectionner les images {channel}",
    "batch_processing_mode_group": "Mode de traitement",
    "batch_solo_select_images_title": "Sélectionner les photos à importer",
    "batch_solo_count": "{n} photo(s) en attente",
    "batch_solo_no_photos": "Aucune photo sélectionnée à importer.",
    "batch_input_group": "Sélection des fichiers",
    "batch_browse_button": "Parcourir…",
    "batch_rescan_button": "Réanalyser",
    "batch_no_folder": "Aucun dossier sélectionné",
    "batch_select_input_title": "Sélectionner le dossier d'entrée",
    "batch_select_output_title": "Sélectionner le dossier de sortie",
    "batch_triplets_found": "{n} triplets appariés",
    "batch_unmatched_label": "{n} fichiers non appariés (ignorés)",
    "batch_align_auto_checkbox": "Aligner automatiquement chaque image",
    "batch_output_folder_label": "Dossier de sortie :",
    "export_same_as_source": "Dossier source",
    "export_same_as_source_tooltip": ("Enregistre chaque photo exportée à côté de son propre fichier "
                                       "source, plutôt que dans un dossier commun — utile quand les "
                                       "photos exportées proviennent de dossiers différents."),
    "export_reveal_in_finder": "Afficher dans le Finder après l'export",
    "batch_suffix_label": "Suffixe du nom de fichier :",
    "batch_format_label": "Format :",
    "batch_status_no_triplets": "Aucun triplet apparié trouvé dans ce dossier.",
    "batch_status_running": "Traitement {i} / {n}…",
    "batch_status_done": "Terminé — {ok} réussies, {failed} échouées",
    "batch_status_cancelled": "Annulé après {i} / {n}",
    "batch_error_no_input": "Sélectionnez d'abord un dossier d'entrée.",
    "batch_error_no_output": "Sélectionnez un dossier de sortie.",

    "status_auto_align_running": "Alignement automatique…",
    "status_locating_files": "Recherche des fichiers manquants {i} / {n}…",
    "status_scan_capturing": "Scan : prise de vue…",
    "status_scan_capturing_channel": "Scan : prise de vue {channel} ({i} / {n})…",
    "status_scan_sampling_base": "Scan : mesure de la base du film, {channel} ({i} / {n})…",
    "status_auto_align_all_done": "Alignement automatique terminé.",
    "status_auto_align_failed": "Alignement automatique échoué.",
    "status_exported": "Image exportée : {path}",
    "status_settings_copied": "Réglages copiés",
    "status_settings_pasted": "Réglages collés sur {n} photo(s)",
    "status_crop_pasted": "Recadrage collé sur {n} photo(s)",
    "status_photos_deleted": "{n} photo(s) supprimée(s)",
    "status_photos_reset": "{n} photo(s) réinitialisée(s)",
    "status_photo_duplicated": "Photo dupliquée",
    "status_photo_converted_to_trichrome": "Photo trichrome créée",
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
    "export_dialog_title": "Exporter",
    "export_filter_png": "PNG 8 bits (*.png)",
    "export_filter_jpg": "JPEG 8 bits (*.jpg)",
    "export_filter_tiff": "TIFF 16 bits (*.tiff)",

    "help_quickstart_title": "Guide",
    "help_search_placeholder": "Rechercher dans le guide",
    "help_search_no_results": "Aucun résultat",
    "help_search_result_count_one": "1 résultat",
    "help_search_result_count": "{n} résultats",
    "help_quickstart_content": """
<h3>Présentation</h3>
<p>Trichr-o-matic est d'abord conçu pour la recomposition <b>trichrome</b> : combiner 3 clichés distincts R/V/B (ou filtrés sur mesure) en une seule photo couleur.</p>
<p>Ses outils fonctionnent aussi sur une photo seule. En mode <b>Solo</b>, les mêmes réglages Lumière, Couleur, Courbes et Recadrage s'appliquent à une photo déjà composée, argentique numérisée ou numérique.</p>
<h3>Mode Light &amp; Mode Avancé</h3>
<ul>
<li><b>Mode Avancé</b> : l'application complète, avec tous les outils, les sessions multi-photos, l'Import par lot et le Scan.</li>
<li><b>Mode Light</b> : une interface simplifiée à une seule photo, pour un flux de travail trichrome rapide et sans distraction. Elle n'affiche que <b>Histogramme</b>, <b>Fichiers</b>, <b>Traitement Trichrome</b> et <b>Recadrage</b>, sans bandeau de vignettes, sans panneaux supplémentaires et sans fichier de session à gérer.</li>
</ul>
<p>Basculez depuis <b>Fenêtre ▸ Passer en mode Light</b> ou <b>Passer en mode Avancé</b>. Chaque mode garde son propre état : la photo du mode Light reste séparée de votre session Avancée. Revenir en mode Avancé propose de démarrer une nouvelle session avec cette photo, ou de rouvrir votre dernière session.</p>
<h3>Types de traitement</h3>
<p>Le sélecteur <b>Mode</b> du bloc <b>Fichiers</b> détermine comment chaque photo est traitée :</p>
<ul>
<li><b>Solo</b> : une seule photo déjà composée (couleur ou N&amp;B), chargée et éditée telle quelle. Aucune recomposition de canaux.</li>
<li><b>Trichromie Classique</b> : 3 clichés noir et blanc pris à travers des filtres Rouge, Vert et Bleu (ou IR, ou personnalisés), recomposés en une image couleur.</li>
<li><b>Trichromie Couleur</b> : 3 vraies photos couleur, chacune gardant son propre canal R, V ou B (effet « Harris Shutter »), au lieu d'être aplaties en niveaux de gris.</li>
</ul>
<p>Changer le mode d'une photo existante demande quoi faire de ses images :</p>
<ul>
<li>D'un mode Trichromie vers Solo : choisissez le canal chargé à conserver.</li>
<li>De Solo vers un mode Trichromie : choisissez le canal que devient la photo.</li>
</ul>
<p>Pour construire une photo Trichrome à partir de photos Solo existantes, sélectionnez-en 1 à 3 dans le bandeau et choisissez <b>Convertir en image Trichrome</b> dans le menu du clic droit. Elles sont combinées dans l'ordre du bandeau (1re → Rouge, 2e → Vert, 3e → Bleu). Les originales restent intactes.</p>
<h3>Sessions</h3>
<p>Une <b>session</b> regroupe tout ce sur quoi vous travaillez : chaque photo importée, ses réglages et votre disposition actuelle.</p>
<ul>
<li><b>Fichier ▸ Enregistrer la session</b> (Cmd+S) l'écrit dans un fichier portable <b>.trirgb</b> que vous pouvez rouvrir plus tard ou transférer sur une autre machine. <b>Enregistrer la session sous…</b> (Cmd+Maj+S) en enregistre une copie sous un nouveau nom.</li>
<li><b>Fichier ▸ Ouvrir une session…</b> (Cmd+O) en recharge une. <b>Nouvelle session</b> (Cmd+N) repart d'une seule photo vierge.</li>
<li>Le nom de la session s'affiche en bas à droite de la barre d'état. En cas de modifications non enregistrées, fermer l'application, ouvrir une autre session ou en créer une nouvelle demande d'abord s'il faut enregistrer.</li>
<li>Presque toutes les modifications peuvent être annulées avec <b>Cmd+Z</b>, et rétablies avec <b>Cmd+Maj+Z</b>.</li>
</ul>
<h3>Export</h3>
<p>Cliquez sur <b>Exporter…</b> en haut de la barre latérale, ou appuyez sur <b>Cmd+E</b>.</p>
<ul>
<li><b>Quoi</b> : la photo <i>actuelle</i>, votre <i>sélection</i> (à constituer avec Cmd+clic ou Cmd+A dans le bandeau), ou <i>toutes</i> les photos.</li>
<li><b>Format</b> : PNG 8 bits, JPEG 8 bits ou TIFF 16 bits. Le dernier format choisi reste le format par défaut.</li>
<li><b>Où</b> : un dossier de votre choix, ou à côté du fichier source de chaque photo.</li>
</ul>
<p>Appuyez sur <b>Entrée</b> dans la fenêtre d'export pour lancer. La progression s'affiche dans la barre d'état, et un son retentit à la fin de l'export.</p>
<h3>Import</h3>
<ul>
<li><b>Glisser-déposer</b> : glissez des fichiers image depuis le Finder sur le bandeau de vignettes, la vue en grille ou le canevas vide, pour les ajouter comme photos Solo, une à la fois.</li>
<li><b>Importer des images…</b> (Cmd+I) ouvre la fenêtre d'Import par lot, pour plusieurs photos à la fois, y compris des triplets Trichrome complets.</li>
</ul>
<h4>Fenêtre d'Import par lot</h4>
<p>Choisissez un <b>Mode de traitement</b> (Solo, Trichromie Classique ou Trichromie Couleur) pour tout le lot. En mode Solo, sélectionnez des images ou un dossier. En mode Trichromie, choisissez comment les fichiers sont appariés en triplets R/V/B :</p>
<ul>
<li><b>Automatique</b> : les fichiers sont appariés par nom, grâce aux <b>Règles d'Import Auto</b> qui déterminent quel filtre alimente quel canal.</li>
<li><b>Séquentiel</b> : sélectionnez des fichiers déjà regroupés en triplets, dans l'ordre défini par la <b>Règle d'Import Séquentiel</b>.</li>
<li><b>Manuel</b> : choisissez vous-même chacune des 3 colonnes.</li>
</ul>
<p>Cliquez sur les boutons <b>?</b> à côté de chaque option pour les détails, puis sur <b>Importer</b>. Les nouvelles photos sont ajoutées au bandeau après la sélection actuelle.</p>
<h4>Règles d'Import Auto</h4>
<p>Détermine quel mot-clé de filtre dans un nom de fichier alimente quel canal pour l'appariement Automatique. Choisissez une correspondance intégrée (<b>Trichrome RVB</b>, <b>Trichrome IR</b>, <b>Aerochrome</b>) ou définissez la vôtre.</p>
<h4>Règle d'Import Séquentiel</h4>
<p>Détermine à quel canal R/V/B va chaque fichier d'un groupe de 3, pour l'appariement Séquentiel. R/V/B par défaut, ou l'un des 5 autres ordres.</p>
<p>Si les photos source d'une session ont été déplacées ou renommées, l'aperçu liste les fichiers manquants. Utilisez <b>Localiser…</b> pour les relier à nouveau.</p>
<h3>Dispositions</h3>
<ul>
<li><b>Blocs</b> : chaque outil vit dans son propre bloc déplaçable, dans le panneau gauche ou droit. Glissez un bloc par sa poignée pour le réordonner ou le déplacer vers l'autre panneau. Un trait bleu en pointillés indique où il atterrira.</li>
<li>Un bloc peut être <b>réduit</b> à son en-tête, ou <b>fermé</b>. Le menu <b>Outils</b> permet de faire réapparaître un bloc fermé.</li>
<li>Les boutons <b>Trichrome / Correction Couleur / Recadrage / Scan</b> de la barre d'outils (raccourcis <b>T / E / C / S</b>) rejoignent une disposition enregistrée pour cette tâche. Enregistrez la vôtre sous l'un de ces noms avec <b>Fenêtre ▸ Préréglage de disposition ▸ Enregistrer la disposition comme préréglage…</b>. Vous pouvez aussi enregistrer autant de dispositions nommées que vous voulez.</li>
<li><b>Fenêtre ▸ Réinitialiser la disposition</b> restaure la disposition par défaut.</li>
</ul>
<h3>Outils</h3>
<p>Chaque outil ci-dessous est dans son propre bloc (voir Dispositions). Une petite icône en bas de chaque bloc ou section réinitialise uniquement cette partie. Survolez-la pour les détails ; elle se grise quand il n'y a rien à réinitialiser.</p>
<h4>Traitement Trichrome</h4>
<p>L'outil le plus détaillé, là où la recomposition trichrome se produit.</p>
<ul>
<li><b>Afficher la couche</b>, en haut du bloc, active ou désactive chaque combinaison des 3 canaux dans l'aperçu. Au moins un reste actif. Contrairement à l'Aperçu solo de couche, le résultat reste en couleur.</li>
<li><b>Onglets R/V/B</b> : choisissez le canal à éditer. Chaque onglet a 3 sections repliables, dont l'état ouvert ou fermé est partagé entre les onglets.</li>
</ul>
<p>Les 3 sections de chaque onglet :</p>
<ul>
<li><b>Lumière</b> : exposition, luminosité, contraste, hautes lumières, ombres, blancs, noirs et gamma pour l'image noir et blanc de ce canal, appliqués avant les réglages Lumière et Couleur de l'image composée.</li>
<li><b>Position</b> : décalage X/Y, échelle et rotation. Cochez <b>Déplacer sur le canevas</b> pour les régler sur l'aperçu : glisser pour déplacer, Maj+molette pour l'échelle, Alt+molette pour la rotation, ou les flèches pour un petit déplacement (Maj pour un plus grand). Tant que la case est cochée, les flèches règlent l'alignement au lieu de naviguer, et Déplacer sur le canevas suit l'onglet R/V/B affiché.</li>
<li><b>Géométrie</b> : correction optique propre à ce cliché : Distorsion (barillet ou coussinet), perspective Verticale et Horizontale, et Aspect. Cochez <b>Étirer sur le canevas</b> pour cliquer-glisser sur l'aperçu et affiner une zone de ce canal, à partir du point cliqué. Chaque glissement affine encore le résultat. Un seul des deux, Déplacer ou Étirer sur le canevas, peut être actif à la fois.</li>
</ul>
<p>Sous les onglets :</p>
<ul>
<li><b>Alignement automatique</b> aligne les 3 canaux. Avec <b>Appliquer la géométrie à l'alignement auto</b> cochée, il résout aussi la Géométrie.</li>
<li><b>Position verrouillée</b> choisit le canal qui reste fixe comme ancre. L'Alignement automatique ne le déplace jamais, mais vous pouvez le repositionner à la main.</li>
<li>Chaque onglet a son propre bouton <b>Aperçu solo de couche</b>, qui n'affiche que ce canal en noir et blanc.</li>
</ul>
<h4>Histogramme</h4>
<p>Niveaux Y/R/V/B en direct pour l'image composée, avec des indicateurs d'écrêtage et une pipette par pixel. Chaque canal peut aussi être affiché seul.</p>
<h4>Lumière</h4>
<p>Exposition, luminosité, contraste, hautes lumières, ombres, blancs, noirs et gamma de l'image composée. Un bouton <b>Négatif</b> est dans l'en-tête.</p>
<h4>Couleur</h4>
<p>Température, teinte, saturation et pipette de balance des blancs. Un bouton <b>Noir et Blanc</b> dans l'en-tête fait une vraie conversion en niveaux de gris pondérée par la luminance.</p>
<h4>Recadrage</h4>
<p>Deux sections :</p>
<ul>
<li><b>Rognage</b> : choisissez un ratio, redressez, mettez en miroir et choisissez une grille. Cliquez sur <b>Activer</b> pour glisser et redimensionner le rectangle sur le canevas. <b>Entrée</b> l'applique, <b>Échap</b> annule.</li>
<li><b>Géométrie</b> : distorsion, perspective verticale et horizontale, et correction d'aspect pour toute l'image composée, dans tous les modes, y compris Solo. Cliquez sur <b>Correction de perspective</b> et tracez jusqu'à 2 guides verticaux et 2 horizontaux le long de lignes qui devraient être droites. Glissez une extrémité pour ajuster un guide, ou double-cliquez pour le supprimer. <b>Entrée</b> calcule et applique la correction, <b>Échap</b> annule.</li>
</ul>
<h4>Courbes</h4>
<p>Un éditeur de courbes de ton classique, avec les courbes Y (globale), R, V et B indépendantes. Cliquez sur la diagonale pour ajouter un point, et glissez pour redessiner la courbe, y compris ses deux extrémités pour un vrai point noir ou blanc. Double-cliquez sur un point pour le supprimer.</p>
<h4>Scan</h4>
<p>Capture par câble USB, avec un appareil photo connecté.</p>
<ul>
<li><b>Appareil</b> affiche l'état de connexion en direct. Une fois connecté, <b>Réglages caméra</b> affiche ceux du Format, de la Balance des blancs et de la Vitesse d'obturation que l'appareil prend en charge.</li>
<li><b>Film</b> définit le traitement de chaque capture à l'import : <b>Noir et Blanc</b> (inversion et vraie conversion en niveaux de gris), <b>Couleur</b> (inversion seule) ou <b>Couleur Inversible</b> (déjà positive, aucun changement).</li>
<li><b>Lumière de scan</b> règle un rétroéclairage optionnel à l'écran : <b>Externe</b>, une lumière <b>Blanche</b> simple, ou <b>RVB</b>, qui enchaîne une séquence automatique de 3 prises rouge, verte et bleue en un triplet trichrome.</li>
<li><b>Base du film</b> (négatifs couleur) : échantillonnez la base claire du film une fois, par une séquence de calibration ou en cliquant sur un point d'une photo importée. <b>Corriger la couleur de base du film à l'import</b> la retire de toutes les captures suivantes.</li>
</ul>
<p>Réglez le dossier d'enregistrement, le nom de la pellicule et le numéro de départ dans <b>Réglages des fichiers</b>, puis cliquez sur <b>Capturer</b>. Les captures sont ajoutées automatiquement à la session en cours.</p>
<h3>Navigation &amp; Aperçu</h3>
<ul>
<li><b>Bandeau</b> : les photos importées apparaissent sous l'aperçu. Il s'affiche automatiquement dès qu'il y a plus d'une photo. Cliquez sur une vignette (ou utilisez <b>←/→</b>) pour éditer les réglages propres de cette photo. Appuyez sur <b>G</b> pour une grille de toutes les vignettes (<b>↑/↓</b> pour changer de ligne, <b>Échap</b> pour quitter).</li>
<li><b>Menu des vignettes</b> : clic droit pour <b>Copier</b>, <b>Coller</b>, <b>Coller le recadrage</b>, <b>Tout réinitialiser</b>, <b>Dupliquer</b> et <b>Supprimer</b>. Copier, Coller et Supprimer ont aussi Cmd+C, Cmd+V et Cmd+Suppr. <b>Tout réinitialiser</b> efface l'alignement, la couleur et le recadrage d'une photo. <b>Dupliquer</b> crée une copie numérotée, « (2) », pour comparer une autre retouche côte à côte.</li>
<li><b>Zoom</b> : l'aperçu s'ouvre en ajustement à la fenêtre au lancement et après chaque import. Utilisez les commandes de zoom, ou <b>Z</b> et <b>F</b>, pour passer entre Taille réelle et Ajustement.</li>
<li><b>Aperçu HQ</b> (<b>H</b>, ou le bouton de la barre d'outils à côté de Zoom 100 %) recompose la photo en pleine résolution un instant après votre dernière modification, pour un aperçu plus net.</li>
<li><b>Plein écran</b> (Cmd+F) masque les panneaux latéraux ; Échap pour quitter. <b>Comparer</b> (la touche <b>:</b>, ou le bouton de la barre d'outils) affiche temporairement l'image originale non retouchée, pour juger vos modifications.</li>
</ul>
""",

    "help_shortcuts_title": "Raccourcis clavier",
    # Only the static half of the "Files & Edit" section - see the same key in
    # the EN block for how the rest is generated.
    "help_shortcuts_files_edit_static": (
        "<li><kbd>Cmd+Suppr</kbd> — retire la ou les photo(s) sélectionnée(s)</li>"
        "<li><kbd>Cmd+W</kbd> — ferme la fenêtre active</li>"
        "<li><kbd>F1</kbd> — Guide</li>"
        "<li><kbd>Cmd+Q</kbd> — quitter</li>"
    ),
    "shortcut_key_shift": "Maj",
    "shortcut_export_hint": "Entrée dans cette fenêtre lance l'export",
    "shortcut_copy_paste_hint": "copie les réglages de la photo actuelle, les colle sur les photos sélectionnées",
    "help_shortcuts_content": """
<h3>Fichiers et Édition</h3>
<ul>
%%GENERAL_SHORTCUTS_ITEMS%%
</ul>
<h3>Affichage</h3>
<ul>
<li><kbd>T</kbd> / <kbd>E</kbd> / <kbd>C</kbd> / <kbd>S</kbd> — bascule vers votre disposition
enregistrée Trichrome / Correction Couleur / Recadrage / Scan (voir Window ▸ Préréglage de
disposition)</li>
<li><kbd>I</kbd> / <kbd>O</kbd> — affiche/masque le panneau latéral gauche/droit</li>
<li><kbd>P</kbd> — affiche/masque le bandeau de vignettes</li>
<li><kbd>G</kbd> — bascule la vue en grille des vignettes</li>
<li><kbd>Cmd+F</kbd> — bascule le plein écran</li>
<li><kbd>Échap</kbd> — quitte le plein écran ou la vue en grille (selon le cas)</li>
<li><b>Glisser</b> la poignée d'un bloc — le réordonne ou le déplace vers l'autre
panneau latéral</li>
</ul>
<h3>Navigation</h3>
<ul>
<li><kbd>←</kbd> / <kbd>→</kbd> — va à la photo précédente/suivante (maintenez <kbd>Maj</kbd>
pour étendre la sélection d'export au lieu de simplement naviguer)</li>
<li><kbd>↑</kbd> / <kbd>↓</kbd> — change de rangée quand la vue en grille est active (maintenez
<kbd>Maj</kbd> pour étendre la sélection d'export)</li>
<li><b>Glisser</b> une vignette — réorganise les photos (bascule sur l'ordre
personnalisé)</li>
<li><b>Glisser</b> des fichiers image depuis le Finder sur le bandeau — les ajoute comme
nouvelles photos Solo</li>
<li><b>Cmd+clic</b> sur une vignette — ajoute/retire de la sélection d'export</li>
<li><kbd>Cmd+A</kbd> — sélectionne toutes les photos, ou les désélectionne toutes si elles
le sont déjà</li>
</ul>
<h3>Aperçu</h3>
<ul>
<li><b>Ctrl + molette</b>, ou <b>pincer</b> sur le trackpad — zoome l'aperçu</li>
<li><b>Glisser à deux doigts</b> sur le trackpad — déplace la vue une fois zoomée</li>
<li><kbd>Cmd+Plus</kbd> / <kbd>Cmd+Moins</kbd> — zoom avant/arrière (ou utilisez les boutons de
la barre d'outils)</li>
<li><kbd>F</kbd> / <kbd>Z</kbd> — passe directement au zoom Ajuster / 100% (ou utilisez les
boutons de la barre d'outils)</li>
<li><kbd>H</kbd> — bascule HQ Preview</li>
<li><kbd>:</kbd> — bascule Comparer, affiche l'original non modifié</li>
</ul>
<h3>Outils</h3>
<p><b>Double-clic</b> sur un curseur — le réinitialise à sa valeur par défaut, dans
chaque outil ci-dessous.</p>
<h4>Traitement Trichrome</h4>
<p>Choisissez le canal sur lequel travailler via les onglets R/V/B.</p>
<ul>
<li><b>Glisser</b> — déplace le calque tant que <b>Déplacer sur le canevas</b> est coché,
ou l'étire localement tant que <b>Étirer sur le canevas</b> est coché</li>
<li><b>Flèches du clavier</b> — micro-règlent la position du calque (maintenez
<kbd>Maj</kbd> pour un pas plus grand), tant que <b>Déplacer sur le canevas</b> est coché</li>
<li><b>Maj + molette</b> — met à l'échelle le calque marqué Déplacer sur le canevas</li>
<li><b>Alt + molette</b> — fait pivoter le calque marqué Déplacer sur le canevas</li>
</ul>
<h4>Recadrage</h4>
<ul>
<li><b>Glisser</b> — redimensionne le rectangle de recadrage, ou trace/modifie un guide
de perspective</li>
<li><kbd>Entrée</kbd> — applique le rectangle de recadrage ou la correction de perspective,
selon celui qui est actif</li>
<li><kbd>Échap</kbd> — annule le recadrage ou la correction de perspective en cours, sans
rien changer</li>
</ul>
<h4>Couleur</h4>
<ul>
<li><kbd>W</kbd> — bascule la pipette de balance des blancs</li>
</ul>
""",

    # --- Scan tool (standalone test window) ---
    "scan_window_title": "Outil de scan (test)",
    "scan_wip_notice": "Cet outil est encore en cours de développement — des erreurs ou comportements inattendus peuvent survenir.",
    "scan_device_group": "Appareil",
    "scan_device_not_connected": "Non connecté",
    "scan_device_connected": "Connecté : {model}",
    "scan_device_refresh": "Actualiser",
    "scan_camera_settings_group": "Réglages caméra",
    "scan_white_balance_label": "Balance des blancs",
    "scan_shutter_speed_label": "Vitesse d'obturation",
    "scan_mode_group": "Film",
    "scan_mode_bw": "N&B",
    "scan_mode_color": "Couleur",
    "scan_mode_color_reversal": "Couleur Inversible",
    "scan_mode_invert_note": "L'inversion sera appliquée automatiquement à l'import pour ce mode.",
    "scan_mode_no_invert_note": "Aucune inversion nécessaire à l'import pour ce mode (déjà positif).",
    "scan_mode_note_bw": "Inversion et Noir et Blanc appliqués automatiquement à l'import.",
    "scan_mode_note_color": "Inversion appliquée automatiquement à l'import.",
    "scan_mode_note_color_reversal": "Photo importée sans changement.",
    "scan_light_group": "Lumière de scan",
    "scan_light_external": "Externe",
    "scan_light_white": "Blanche",
    "scan_light_rgb": "RVB",
    "scan_light_rgb_note": "La capture prendra automatiquement 3 photos en séquence - lumière rouge, verte, puis bleue - et reviendra à la lumière blanche ensuite. Les 3 partagent le même numéro, avec le suffixe _R/_G/_B.",
    "scan_light_window_title": "Rétroéclairage de scan",
    "scan_sample_base_button": "Échantillonner la base du film",
    "scan_sample_base_tooltip": (
        "Placez la base transparente et non exposée du film (l'amorce) sous "
        "la lumière, puis cliquez - capture 3 photos de référence RVB "
        "utilisées pour corriger la couleur de la base/du masque (par "
        "exemple le masque orange des négatifs couleur) sur les prochains "
        "imports RGB Light."
    ),
    "scan_sample_base_requires_rgb_light": (
        "Sélectionnez d'abord RGB Light, puis placez la base transparente/"
        "non exposée du film sous la lumière avant de cliquer à nouveau."
    ),
    "scan_film_base_status_not_set": "Base du film : non échantillonnée",
    "scan_film_base_status_set": "Base du film échantillonnée — R {r} · G {g} · B {b}",
    "scan_apply_film_base_checkbox": "Corriger la couleur de base du film à l'import",
    "scan_apply_film_base_tooltip": (
        "Retire le biais de couleur de la base du film échantillonnée (par "
        "exemple le masque orange des négatifs couleur) de chaque canal RGB "
        "Light avant l'inversion, en utilisant la référence échantillonnée "
        "ci-dessus. Appliqué à chaque photo RGB Light ajoutée à la session "
        "tant que la case est cochée."
    ),
    "scan_capturing_channel_status": "Prise de vue {channel}…",
    "scan_process_checkbox": "Enregistrer aussi un aperçu JPG traité",
    "scan_process_tooltip": "Enregistre une copie JPG supplémentaire dans un sous-dossier « processed » : noir et blanc + inversé pour Noir et Blanc, inversé pour Couleur, tel quel pour Couleur Inversible. Pour un triplet en Lumière RVB, recompose les 3 photos en une seule image trichrome avec l'algorithme d'auto-alignement et de composition de l'application.",
    "scan_processing_status": "Traitement…",
    "scan_processed_label": "Traité",
    "scan_location_group": "Paramètres des fichiers",
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
    "scan_select_folder_prompt_title": "Sélectionnez un dossier pour enregistrer vos scans",
    "scan_pick_film_base_tooltip": (
        "Alternative à Échantillonner la base du film : cliquez ici, puis "
        "cliquez un point transparent/non exposé sur une photo Trichrome "
        "déjà présente dans la session (plutôt que de prendre 3 nouvelles "
        "photos de calibration). S'applique à la prochaine prise de vue, "
        "comme un échantillonnage dédié."
    ),
    "scan_pick_film_base_requires_trichrome": (
        "Sélectionnez d'abord une photo Trichrome avec les 3 canaux R/V/B chargés."
    ),
    "status_film_base_picked": "Base du film échantillonnée depuis la photo.",
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
