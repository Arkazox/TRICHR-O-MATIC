# -*- mode: python ; coding: utf-8 -*-
# Windows build: pyinstaller --noconfirm --clean trichrome_win.spec
# (run on Windows; PyInstaller doesn't cross-compile). Produces the folder
# dist/Trichr-o-matic/ with Trichr-o-matic.exe inside. Same data files as
# trichrome.spec; only the packaging (no .app bundle, .ico, version
# resource) differs.
import os
from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo,
    VarStruct, VSVersionInfo,
)

block_cipher = None

# Single source of truth for the version string - see trichrome/version.py.
_version_ns = {}
exec(open("trichrome/version.py").read(), _version_ns)
APP_VERSION = _version_ns["__version__"]
_version_tuple = tuple(int(p) for p in APP_VERSION.split(".")[:3]) + (0,)

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
    ("resources/icon.ico", "resources"),  # window icon (main.py)
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

# Shown in the .exe's Properties ▸ Details tab.
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_version_tuple, prodvers=_version_tuple),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "Simon Jayet"),
            StringStruct("FileDescription", "Trichr-o-matic"),
            StringStruct("FileVersion", APP_VERSION),
            StringStruct("InternalName", "Trichr-o-matic"),
            StringStruct("LegalCopyright", "© 2026 Simon Jayet. MIT License."),
            StringStruct("OriginalFilename", "Trichr-o-matic.exe"),
            StringStruct("ProductName", "Trichr-o-matic"),
            StringStruct("ProductVersion", APP_VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

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
    icon="resources/icon.ico",
    version=version_info,
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
