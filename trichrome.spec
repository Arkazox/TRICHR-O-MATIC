# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas = [("resources/icons", "resources/icons")]
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
        "CFBundleShortVersionString": "0.5.0",
        "CFBundleName": "Trichr-o-matic",
        "NSHumanReadableCopyright": "© 2026",
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
