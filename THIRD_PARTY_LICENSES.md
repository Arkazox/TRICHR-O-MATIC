# Third-party licenses

Trichr-o-matic itself is released under the MIT License (see `LICENSE`).
The macOS app bundles the following open-source software, each under its
own license. Their source code is available from the links below.

## Libraries

| Component | License | Source |
|---|---|---|
| Python | PSF License | https://www.python.org |
| Qt 6 / PySide6 / Shiboken6 | LGPL v3 | https://code.qt.io, https://download.qt.io/official_releases/QtForPython/ |
| NumPy | BSD 3-Clause | https://github.com/numpy/numpy |
| OpenCV (opencv-python-headless) | Apache 2.0 | https://github.com/opencv/opencv, https://github.com/opencv/opencv-python |
| Pillow | MIT-CMU (HPND) | https://github.com/python-pillow/Pillow |
| rawpy | MIT | https://github.com/letmaik/rawpy |
| LibRaw (used by rawpy) | LGPL v2.1 or CDDL v1.0 | https://github.com/LibRaw/LibRaw |
| PyInstaller bootloader | GPL v2 with a bootloader exception | https://github.com/pyinstaller/pyinstaller |

Some of these packages ship further libraries (image codecs, compression,
video I/O). Their notices are listed in each package's own license files,
for example OpenCV's `LICENSE-3RD-PARTY.txt`.

### Qt (LGPL v3)

Qt is dynamically linked: its libraries are stored as separate files inside
`Trichr-o-matic.app/Contents/Frameworks`. You may replace them with your own
build of the same Qt version. The full LGPL v3 text is at
https://www.gnu.org/licenses/lgpl-3.0.html.

## Optional external tool

Scan (an experimental feature, off by default) uses
[gphoto2](http://www.gphoto.org) (LGPL v2.1). It is **not** bundled: you
install it separately, and the app runs it as an external program.
