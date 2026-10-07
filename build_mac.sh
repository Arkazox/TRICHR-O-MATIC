#!/usr/bin/env bash
# Build "Trichr-o-matic.app" for macOS.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

rm -rf build dist
pyinstaller trichrome.spec --noconfirm

# Every Mach-O file in the bundle must run on the macOS the app claims to
# support. A wheel's platform tag isn't proof (PySide6 6.10+ is tagged
# macOS 13 but built for 15), so read each binary's own minimum (minos, or
# LC_VERSION_MIN_MACOSX's version on older binaries) and fail the build on
# any that is newer than LSMinimumSystemVersion.
APP="dist/Trichr-o-matic.app"
MIN_MACOS=$(plutil -extract LSMinimumSystemVersion raw "$APP/Contents/Info.plist")
TOO_NEW=$(find "$APP" -type f -print0 | while IFS= read -r -d '' f; do
    v=$(otool -arch arm64 -l "$f" 2>/dev/null | awk '
        /LC_BUILD_VERSION|LC_VERSION_MIN_MACOSX/ { cmd = 1 }
        cmd && ($1 == "minos" || $1 == "version") { print $2; exit }')
    [ -z "$v" ] && continue
    if [ "$(printf '%s\n%s\n' "$MIN_MACOS" "$v" | sort -V | tail -1)" != "$MIN_MACOS" ]; then
        echo "  macOS $v  ${f#$APP/}"
    fi
done)
if [ -n "$TOO_NEW" ]; then
    echo ""
    echo "Build error: these binaries need a newer macOS than LSMinimumSystemVersion ($MIN_MACOS):"
    echo "$TOO_NEW"
    exit 1
fi
echo "Every bundled binary runs on macOS $MIN_MACOS or later."

# Reset the remembered session (last opened .trirgb path, and the legacy
# QSettings item-array fallback used when there's no remembered path) so
# the very first launch of a freshly built version starts from a clean
# slate - New/Open Session is then mandatory, rather than silently
# reopening whatever photos/session happened to be open the last time
# this Mac ran the app (so each new build's first launch is a genuine
# "fresh install" test, not carrying over leftover test data from the
# previous build). Also clears every custom Layout Preset (same reasoning - a dev machine's own saved presets,
# including the 4 that used to back the toolbar's Trichrome/Color
# Correction/Crop/Scan buttons, should never leak into what a fresh build
# presents on first launch; those 4 buttons no longer depend on a preset
# existing at all, see _BUILT_IN_LAYOUT_STATES in main_window.py).
# Deliberately still narrow otherwise: language, panel/block layout,
# window geometry, and every other QSettings key in the same domain is
# left completely untouched.
python3 - <<'PY'
from PySide6.QtCore import QSettings
from trichrome.main_window import ORG_NAME, APP_NAME
settings = QSettings(ORG_NAME, APP_NAME)
settings.remove("last_session_file_path")
settings.remove("session_items")
settings.remove("session_current_index")
# Quick Tour: re-arm the welcome window so every fresh build shows it at
# first launch again (removing the key falls back to its default, True).
settings.remove("quick_tour_show_at_startup")
# Scan tool: opt-in while alpha. Removing the key falls back to its
# default, False, so a dev machine that turned it on for testing doesn't
# leak that into what a fresh build presents on first launch.
settings.remove("scan_tool_enabled")
# Batch Import: back to Auto Align on, "Apply transform to auto align" off
# (the keys' defaults), whatever the dev machine last used.
settings.remove("batch_auto_align")
settings.remove("batch_auto_align_apply_distortion")
for key in settings.allKeys():
    if key == "layout_preset_names" or key.startswith("layout_preset_data_"):
        settings.remove(key)
PY

echo ""
echo "App créée : dist/Trichr-o-matic.app"
