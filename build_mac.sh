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

echo ""
echo "App créée : dist/Trichr-o-matic.app"
