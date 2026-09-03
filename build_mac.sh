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

python3 scripts/generate_changelog_pdf.py

# Reset the remembered session (last opened .trirgb path, and the legacy
# QSettings item-array fallback used when there's no remembered path) so
# the very first launch of a freshly built version starts from a clean
# slate - New/Open Session is then mandatory, rather than silently
# reopening whatever photos/session happened to be open the last time
# this Mac ran the app (2026-09-04, requested so each new build's first
# launch is a genuine "fresh install" test, not carrying over leftover
# test data from the previous build). Deliberately narrow: only clears
# the session/photo-import state (last_session_file_path, session_items,
# session_current_index) - everything else in the same QSettings domain
# (layout presets, language, panel/block layout, window geometry) is left
# completely untouched.
python3 - <<'PY'
from PySide6.QtCore import QSettings
from trichrome.main_window import ORG_NAME, APP_NAME
settings = QSettings(ORG_NAME, APP_NAME)
settings.remove("last_session_file_path")
settings.remove("session_items")
settings.remove("session_current_index")
PY

echo ""
echo "App créée : dist/Trichr-o-matic.app"
