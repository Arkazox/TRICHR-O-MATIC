# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Single source of truth for the version string - see trichrome/version.py.
_version_ns = {}
exec(open("trichrome/version.py").read(), _version_ns)
APP_VERSION = _version_ns["__version__"]

# Every icon folder except Unused/ (icons no code references stay out of
# the shipped app).
datas = [
    (os.path.join("resources/icons", name), os.path.join("resources/icons", name))
    for name in sorted(os.listdir("resources/icons"))
    if name != "Unused" and os.path.isdir(os.path.join("resources/icons", name))
]
datas += [
    ("LICENSE", "."),
    ("THIRD_PARTY_LICENSES.md", "."),
    ("resources/app_logo.png", "resources"),
    ("resources/quick_tour_light_mode.png", "resources"),
    ("resources/sample", "resources/sample"),
]
binaries = []
hiddenimports = ["PySide6.QtSvg"]
for pkg in ("cv2", "rawpy"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Trichr-o-matic",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="resources/icon.icns",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Trichr-o-matic",
)

app = BUNDLE(
    coll,
    name="Trichr-o-matic.app",
    icon="resources/icon.icns",
    bundle_identifier="com.simonjayet.trichromemaker",
    info_plist={
        "NSHighResolutionCapable": "True",
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleName": "Trichr-o-matic",
        "NSHumanReadableCopyright": "© 2026 Simon Jayet. MIT License.",
        # Must not be lower than any bundled binary's own minimum: build_mac.sh
        # checks every Mach-O file in the bundle against it.
        "LSMinimumSystemVersion": "12.0",
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "Trichr-o-matic Session",
                "CFBundleTypeExtensions": ["trirgb"],
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner",
                "CFBundleTypeIconFile": "icon.icns",
            }
        ],
    },
)
