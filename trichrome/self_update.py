"""In-app update: download the new release, check it, swap the .app and
relaunch, so updating doesn't mean opening GitHub and re-downloading by hand.

Flow (UpdateDownloadWorker, off the UI thread):
1. Download the release's SHA256SUMS and SHA256SUMS.sig and verify the
   signature against UPDATE_PUBLIC_KEY (Ed25519, see ed25519.py; the private
   key never leaves the release machine, see scripts/sign_update.py). HTTPS
   alone only proves the file came from GitHub; the signature proves it came
   from the release machine, even if the GitHub account were compromised.
2. Download this architecture's zip (the running binary's: an Intel build
   under Rosetta stays Intel) and compare its SHA-256 with the signed list.
3. Extract it with ditto into a staging folder, then check the new bundle:
   same bundle identifier, the expected version, contains this architecture,
   and its (ad-hoc) code signature verifies.

Then, once MainWindow has closed normally (unsaved-changes prompt
included), launch_installer() starts a detached shell script that waits for
this process to exit, moves the old .app aside, moves the new one into its
place, relaunches it and deletes the old one. If the swap fails, the old app
is put back and relaunched.

A file this app downloads doesn't get the quarantine flag (only browsers
and other apps that opt in set it), so the new version opens without the
first-launch Gatekeeper prompt. The flag is still stripped from the staged
bundle in case an extracted file carried it from the build machine.

can_self_update() says when this can't work, and the dialog then falls
back to opening the release page: running from source, not macOS, no
public key compiled in, the app running from a translocated (read-only)
copy because it was never moved out of Downloads, or a folder the user
can't write to."""
from __future__ import annotations

import hashlib
import os
import platform
import plistlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request

from PySide6.QtCore import QObject, Signal

from . import ed25519

# Hex Ed25519 public key matching the release machine's signing key
# (scripts/sign_update.py --public-key). Empty: self-update is off and
# Update opens the release page.
UPDATE_PUBLIC_KEY = "15e813aaa9882fd3a0ae2deff510b1a05f4e89d7ee0931d75525daebaa608f8f"

SUMS_ASSET = "SHA256SUMS"
SIGNATURE_ASSET = "SHA256SUMS.sig"
_USER_AGENT = "Trichr-o-matic"
_TIMEOUT_SECONDS = 30
_CHUNK_SIZE = 256 * 1024
_SYSTEM_CA_FILE = "/etc/ssl/cert.pem"


def ssl_context() -> ssl.SSLContext:
    """The python.org Python the app is built with ships no CA certificates
    of its own (its OpenSSL looks in an empty folder), so HTTPS would fail
    to verify every server. macOS keeps its root certificates as a PEM
    bundle at /etc/ssl/cert.pem; Windows' Python already loads the system
    store by itself."""
    context = ssl.create_default_context()
    if sys.platform == "darwin" and os.path.isfile(_SYSTEM_CA_FILE):
        context.load_verify_locations(cafile=_SYSTEM_CA_FILE)
    return context


def open_url(url: str, timeout: float = _TIMEOUT_SECONDS):
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    return urllib.request.urlopen(request, timeout=timeout, context=ssl_context())


def _architecture() -> str:
    return platform.machine()  # "arm64" or "x86_64" (also under Rosetta)


def asset_name(version: str) -> str:
    flavor = "AppleSilicon" if _architecture() == "arm64" else "Intel"
    return f"Trichr-o-matic-v{version}-{flavor}.zip"


def current_bundle_path() -> str | None:
    """The running .app, or None when not running from a built bundle."""
    if not getattr(sys, "frozen", False):
        return None
    # sys.executable is <bundle>/Contents/MacOS/<executable>.
    bundle = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(sys.executable))))
    return bundle if bundle.endswith(".app") else None


def can_self_update(assets: dict[str, str], version: str) -> bool:
    if sys.platform != "darwin" or not UPDATE_PUBLIC_KEY:
        return False
    if not all(name in assets for name in (SUMS_ASSET, SIGNATURE_ASSET, asset_name(version))):
        return False  # a release published before self-update existed
    bundle = current_bundle_path()
    if bundle is None or "/AppTranslocation/" in bundle:
        return False
    return os.access(os.path.dirname(bundle), os.W_OK) and os.access(bundle, os.W_OK)


def _bundle_info(bundle: str) -> dict:
    with open(os.path.join(bundle, "Contents", "Info.plist"), "rb") as f:
        return plistlib.load(f)


class UpdateDownloadWorker(QObject):
    progress = Signal(int, int)   # bytes received, total (0 if unknown)
    ready = Signal(str)           # path of the checked, staged .app
    failed = Signal(str)
    finished = Signal()

    def __init__(self, version: str, assets: dict[str, str]):
        super().__init__()
        self._version = version
        self._assets = assets
        self._cancelled = False
        self.staging_dir: str | None = None

    def cancel(self) -> None:
        # Read between chunks on the worker thread; a plain bool is enough.
        self._cancelled = True

    def run(self) -> None:
        try:
            self.ready.emit(self._download_and_stage())
        except Exception as exc:
            discard_staging(self.staging_dir)
            self.staging_dir = None
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def _read_small(self, name: str) -> bytes:
        with open_url(self._assets[name]) as response:
            return response.read(1024 * 1024)

    def _download_and_stage(self) -> str:
        sums = self._read_small(SUMS_ASSET)
        signature = bytes.fromhex(self._read_small(SIGNATURE_ASSET).decode("ascii").strip())
        if not ed25519.verify(bytes.fromhex(UPDATE_PUBLIC_KEY), sums, signature):
            raise ValueError("the update's signature doesn't match")
        zip_name = asset_name(self._version)
        expected_hash = None
        for line in sums.decode("utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == zip_name:
                expected_hash = parts[0].lower()
        if expected_hash is None:
            raise ValueError(f"{zip_name} isn't in the signed list")

        bundle = current_bundle_path()
        self.staging_dir = tempfile.mkdtemp(prefix="Trichr-o-matic-update-")
        zip_path = os.path.join(self.staging_dir, zip_name)
        digest = hashlib.sha256()
        with open_url(self._assets[zip_name]) as response, open(zip_path, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            received = 0
            while True:
                if self._cancelled:
                    raise RuntimeError("cancelled")
                chunk = response.read(_CHUNK_SIZE)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                self.progress.emit(received, total)
        if digest.hexdigest() != expected_hash:
            raise ValueError("the download is corrupted (checksum mismatch)")

        extract_dir = os.path.join(self.staging_dir, "extracted")
        subprocess.run(["ditto", "-x", "-k", zip_path, extract_dir], check=True, capture_output=True)
        os.remove(zip_path)
        # The zip's own bundle name, not the running one's: the user may have
        # renamed their copy, and the swap keeps their name and location.
        apps = [name for name in os.listdir(extract_dir) if name.endswith(".app")]
        if len(apps) != 1:
            raise ValueError("the download doesn't contain the app")
        new_app = os.path.join(extract_dir, apps[0])

        new_info, old_info = _bundle_info(new_app), _bundle_info(bundle)
        if new_info.get("CFBundleIdentifier") != old_info.get("CFBundleIdentifier"):
            raise ValueError("the downloaded app has a different identifier")
        if new_info.get("CFBundleShortVersionString") != self._version:
            raise ValueError("the downloaded app has an unexpected version")
        executable = os.path.join(new_app, "Contents", "MacOS", new_info.get("CFBundleExecutable", ""))
        archs = subprocess.run(["lipo", "-archs", executable], capture_output=True, text=True).stdout.split()
        if _architecture() not in archs:
            raise ValueError("the downloaded app is for another processor")
        subprocess.run(["codesign", "--verify", "--deep", new_app], check=True, capture_output=True)
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", new_app], capture_output=True)
        return new_app


def discard_staging(staging_dir: str | None) -> None:
    if staging_dir and os.path.basename(staging_dir).startswith("Trichr-o-matic-update-"):
        shutil.rmtree(staging_dir, ignore_errors=True)


def discard_staged_update(new_app: str) -> None:
    """Drops a staged update that won't be installed (quit cancelled)."""
    discard_staging(os.path.dirname(os.path.dirname(new_app)))


_INSTALLER_SCRIPT = """#!/bin/sh
# Waits for the old app to quit, swaps the bundles, relaunches.
pid="$1"; old_app="$2"; new_app="$3"; staging="$4"
while kill -0 "$pid" 2>/dev/null; do sleep 0.2; done
backup="$staging/previous.app"
if mv "$old_app" "$backup"; then
    if mv "$new_app" "$old_app"; then
        open "$old_app"
        rm -rf "$staging"
        exit 0
    fi
    mv "$backup" "$old_app"
fi
open "$old_app"
"""


def launch_installer(new_app: str) -> None:
    """Starts the detached swap script. Call right before quitting."""
    bundle = current_bundle_path()
    staging = os.path.dirname(os.path.dirname(new_app))
    script = os.path.join(staging, "install.sh")
    with open(script, "w") as f:
        f.write(_INSTALLER_SCRIPT)
    subprocess.Popen(
        ["/bin/sh", script, str(os.getpid()), bundle, new_app, staging],
        start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
