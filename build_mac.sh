#!/usr/bin/env bash
# Build "Trichr-o-matic.app" for macOS.
#
#   ./build_mac.sh          Apple Silicon -> dist-applesilicon/Trichr-o-matic.app
#   ./build_mac.sh intel    Intel         -> dist-intel/Trichr-o-matic.app
#
# The Intel build runs every step under Rosetta (`arch -x86_64`) with its own
# venv (venv-intel/), so pip installs x86_64 wheels and PyInstaller bundles
# x86_64 binaries. The python.org Python 3.12 is universal2, so the same
# interpreter serves both. The two builds never share a folder.
set -euo pipefail
cd "$(dirname "$0")"

case "${1:-arm64}" in
    arm64) ARCH=arm64; VENV=venv; DIST=dist-applesilicon; WORK=build ;;
    intel) ARCH=x86_64; VENV=venv-intel; DIST=dist-intel; WORK=build-intel ;;
    *) echo "Usage: $0 [intel]" >&2; exit 1 ;;
esac
run() { arch "-$ARCH" "$@"; }

if [ ! -d "$VENV" ]; then
    run python3 -m venv "$VENV"
fi
PY="$VENV/bin/python3"
if [ "$(run "$PY" -c 'import platform; print(platform.machine())')" != "$ARCH" ]; then
    echo "$PY doesn't run as $ARCH. Is Rosetta installed (softwareupdate --install-rosetta)?" >&2
    exit 1
fi
run "$PY" -m pip install --upgrade pip -q
run "$PY" -m pip install -r requirements.txt -q

rm -rf "$WORK" "$DIST"
run "$PY" -m PyInstaller trichrome.spec --noconfirm --distpath "$DIST" --workpath "$WORK"

# Every Mach-O file in the bundle must contain the target architecture and
# run on the macOS the app claims to support. A wheel's platform tag isn't
# proof (PySide6 6.10+ is tagged macOS 13 but built for 15), so read each
# binary's own minimum (minos, or LC_VERSION_MIN_MACOSX's version on older
# binaries) and fail the build on any that is newer than
# LSMinimumSystemVersion.
APP="$DIST/Trichr-o-matic.app"

# Some source files (icons downloaded from the web) carry the quarantine
# flag, which the bundle and its release zip would otherwise keep.
xattr -dr com.apple.quarantine "$APP"

MIN_MACOS=$(plutil -extract LSMinimumSystemVersion raw "$APP/Contents/Info.plist")
BAD=$(find "$APP" -type f -print0 | while IFS= read -r -d '' f; do
    archs=$(lipo -archs "$f" 2>/dev/null) || continue  # not a Mach-O file
    if [[ " $archs " != *" $ARCH "* ]]; then
        echo "  no $ARCH ($archs)  ${f#$APP/}"
        continue
    fi
    v=$(otool -arch "$ARCH" -l "$f" 2>/dev/null | awk '
        /LC_BUILD_VERSION|LC_VERSION_MIN_MACOSX/ { cmd = 1 }
        cmd && ($1 == "minos" || $1 == "version") { print $2; exit }')
    [ -z "$v" ] && continue
    if [ "$(printf '%s\n%s\n' "$MIN_MACOS" "$v" | sort -V | tail -1)" != "$MIN_MACOS" ]; then
        echo "  macOS $v  ${f#$APP/}"
    fi
done)
if [ -n "$BAD" ]; then
    echo ""
    echo "Build error: these binaries won't run on $ARCH Macs with macOS $MIN_MACOS (LSMinimumSystemVersion):"
    echo "$BAD"
    exit 1
fi
echo "Every bundled binary is $ARCH and runs on macOS $MIN_MACOS or later."

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
run "$PY" - <<'PY'
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
echo "App créée : $APP"
