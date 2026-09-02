"""Thin subprocess wrapper around the ``gphoto2`` CLI (libgphoto2).

Shells out to the ``gphoto2`` command rather than binding against
python-gphoto2 - the CLI is a straightforward Homebrew install
(``brew install gphoto2``) with no compiled-extension/build-toolchain
dependency, and its text output is stable enough to parse when the
subprocess locale is pinned to C (gphoto2 otherwise localizes its output to
the system locale, which would make parsing unreliable).

Camera config (image quality/RAW, etc.) is intentionally *not* hardcoded to
Fuji-specific paths here: the exact config tree depends on the connected
camera and libgphoto2 version, and can only really be introspected against
real hardware. ``list_config``/``get_config``/``set_config`` are generic;
``find_quality_config`` does a best-effort search over ``list_config`` for a
config that looks like it controls image quality/format, so a RAW option can
be offered when the camera exposes one without assuming its exact path.
"""
from __future__ import annotations

import dataclasses
import re
import subprocess
import sys

_ENV = {"LC_ALL": "C", "LANG": "C"}


class GPhotoError(RuntimeError):
    """Raised when the ``gphoto2`` CLI is missing, times out, or exits non-zero."""


@dataclasses.dataclass
class DetectedCamera:
    model: str
    port: str


@dataclasses.dataclass
class ConfigInfo:
    name: str
    label: str
    type: str
    current: str
    choices: list[str]


def _run(args: list[str], timeout: float) -> str:
    import os
    env = dict(os.environ)
    env.update(_ENV)
    try:
        result = subprocess.run(
            ["gphoto2", *args], capture_output=True, text=True, timeout=timeout, env=env,
        )
    except FileNotFoundError as exc:
        raise GPhotoError(
            "gphoto2 is not installed - run `brew install gphoto2`."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GPhotoError(f"gphoto2 timed out after {timeout:.0f}s") from exc
    if result.returncode != 0:
        raise GPhotoError((result.stderr or result.stdout or "gphoto2 failed").strip())
    return result.stdout


def is_available() -> bool:
    import shutil
    return shutil.which("gphoto2") is not None


def _release_macos_ptp_camera() -> None:
    """macOS holds any connected camera's USB interface claimed via its own
    background daemon the moment it's plugged in, which then makes any
    libgphoto2 call that needs to actually *open* the camera (as opposed to
    ``--auto-detect``'s plain USB enumeration, which doesn't need the claim)
    fail with gphoto2 error -53 ("Could not claim the USB device"). Killing
    that daemon right before is the standard workaround - macOS relaunches it
    on its own whenever it's next needed, so this is harmless and doesn't
    need to be undone. **Confirmed against a real Fuji X-T3 (2026-09-02) that
    the daemon's name has changed across macOS versions** - the classic
    advice online is to kill ``PTPCamera`` (the old Image Capture helper
    app), but on current macOS (Sequoia) the actual process is
    ``/usr/libexec/ptpcamerad`` (lowercase, no `.app`) - ``PTPCamera`` wasn't
    even running when this was debugged, so killing only the old name was a
    silent no-op. Both names are killed here for safety across OS versions;
    it's a plain ``killall`` on each, so one missing process is not an
    error.

    **This alone is not always enough.** On the same real hardware, a
    third-party camera-as-webcam driver (here: FUJIFILM X Webcam's own
    ``com.fujifilm.XWebcam.CameraExtension`` System Extension - confirmed
    active via ``systemextensionsctl list`` showing
    ``[activated enabled]``) continuously holds its own PTP session with the
    camera for webcam streaming, and unlike the daemons above it's a
    DriverKit-level extension that doesn't respond to ``killall`` at all -
    it has to be disabled by the user in System Settings ▸ General ▸ Login
    Items & Extensions ▸ Driver Extensions before gphoto2 can get exclusive
    access. If capture still fails with -53 (or -110 "PTP Device Busy")
    after this function runs, that's the next thing to check - any
    camera-as-webcam software (Fuji's, or an equivalent for another brand)
    installed and enabled is the likely culprit, not a bug in this file."""
    if sys.platform != "darwin":
        return
    for name in ("ptpcamerad", "PTPCamera"):
        try:
            subprocess.run(["killall", "-9", name], capture_output=True, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            pass
    import time
    time.sleep(0.4)


def auto_detect(timeout: float = 5.0) -> list[DetectedCamera]:
    """Returns every camera gphoto2 currently sees over USB, parsed from
    ``--auto-detect``'s two-column ``Model``/``Port`` table."""
    out = _run(["--auto-detect"], timeout=timeout)
    cameras: list[DetectedCamera] = []
    lines = out.splitlines()
    for line in lines:
        if not line.strip() or line.strip().startswith("---") or line.strip().startswith("Model"):
            continue
        # Columns are fixed-width and right-padded; the port is always the
        # last whitespace-separated token (e.g. "usb:001,004").
        parts = line.rstrip().rsplit(None, 1)
        if len(parts) != 2:
            continue
        model, port = parts
        model = model.strip()
        if not model or not port.strip():
            continue
        cameras.append(DetectedCamera(model=model, port=port.strip()))
    return cameras


def list_config(port: str, timeout: float = 10.0) -> list[str]:
    _release_macos_ptp_camera()
    out = _run(["--port", port, "--list-config"], timeout=timeout)
    return [line.strip() for line in out.splitlines() if line.strip().startswith("/")]


def get_config(port: str, name: str, timeout: float = 10.0) -> ConfigInfo:
    _release_macos_ptp_camera()
    out = _run(["--port", port, "--get-config", name], timeout=timeout)
    label = ""
    ctype = ""
    current = ""
    choices: list[str] = []
    for line in out.splitlines():
        line = line.rstrip()
        if line.startswith("Label:"):
            label = line[len("Label:"):].strip()
        elif line.startswith("Type:"):
            ctype = line[len("Type:"):].strip()
        elif line.startswith("Current:"):
            current = line[len("Current:"):].strip()
        elif line.startswith("Choice:"):
            m = re.match(r"Choice:\s*\d+\s+(.*)", line)
            if m:
                choices.append(m.group(1).strip())
    return ConfigInfo(name=name, label=label or name, type=ctype, current=current, choices=choices)


def set_config(port: str, name: str, value: str, timeout: float = 10.0) -> None:
    _release_macos_ptp_camera()
    _run(["--port", port, "--set-config", f"{name}={value}"], timeout=timeout)


# Candidate leaf-name substrings (checked case-insensitively) for whichever
# config actually controls RAW vs. JPEG on the connected camera - the first
# match in --list-config's output wins.
_QUALITY_LEAF_HINTS = ("imagequality", "imageformat", "quality")


def find_quality_config(port: str, timeout: float = 10.0) -> str | None:
    for path in list_config(port, timeout=timeout):
        leaf = path.rsplit("/", 1)[-1].lower()
        if any(hint in leaf for hint in _QUALITY_LEAF_HINTS):
            return path
    return None


_SAVED_FILE_RE = re.compile(r"^Saving file as (.+)$")


def capture_and_download(
    port: str, dest_pattern: str, keep_on_camera: bool = True, timeout: float = 90.0,
) -> list[str]:
    """Triggers a shutter release, downloads the resulting file(s) to
    ``dest_pattern`` (a gphoto2 filename pattern - e.g. ending in ``.%C`` to
    let gphoto2 substitute the real extension, since RAW/JPEG/RAW+JPEG all
    produce a different one), and returns the actual saved path(s) - a
    camera set to "RAW + JPEG" produces two files for one shutter release.
    ``keep_on_camera`` leaves the original on the camera's card either way -
    this tool downloads a copy, it never deletes the only copy of a scan.
    """
    _release_macos_ptp_camera()
    args = ["--port", port, "--filename", dest_pattern, "--force-overwrite"]
    if keep_on_camera:
        args.append("--keep")
    args.append("--capture-image-and-download")
    out = _run(args, timeout=timeout)
    saved: list[str] = []
    for line in out.splitlines():
        m = _SAVED_FILE_RE.match(line.strip())
        if m:
            saved.append(m.group(1).strip())
    if not saved:
        raise GPhotoError("Capture succeeded but gphoto2 did not report a saved file path:\n" + out)
    return saved
