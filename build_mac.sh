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

# Reset the remembered session (last opened .trirgb path, and the legacy
# QSettings item-array fallback used when there's no remembered path) so
# the very first launch of a freshly built version starts from a clean
# slate - New/Open Session is then mandatory, rather than silently
# reopening whatever photos/session happened to be open the last time
# this Mac ran the app (2026-09-04, requested so each new build's first
# launch is a genuine "fresh install" test, not carrying over leftover
# test data from the previous build). Also clears every custom Layout
# Preset (2026-09-11, same reasoning - a dev machine's own saved presets,
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
for key in settings.allKeys():
    if key == "layout_preset_names" or key.startswith("layout_preset_data_"):
        settings.remove(key)
PY

echo ""
echo "App créée : dist/Trichr-o-matic.app"
