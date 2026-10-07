"""Background worker for Help > Check for Updates - a single GET to
GitHub's Releases API, off the UI thread so opening the dialog never
blocks waiting on the network. Mirrors the QObject + moveToThread pattern
the other workers use (see hq_preview_worker.py)."""
from __future__ import annotations

import json
import urllib.request

from PySide6.QtCore import QObject, Signal

REPO = "Arkazox/Trichr-o-matic"
_API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
_TIMEOUT_SECONDS = 8


def parse_version(text: str) -> tuple[int, ...]:
    """"v0.6.3" / "0.6.3" -> (0, 6, 3), for a plain tuple comparison
    against trichrome.version.__version__. Falls back to (0,) for
    anything that doesn't parse, so a malformed tag can never look newer
    than the running version."""
    text = text.strip()
    if text[:1] in ("v", "V"):
        text = text[1:]
    parts = []
    for chunk in text.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


class UpdateCheckWorker(QObject):
    # latest_version ("0.6.4", no leading "v"), release_html_url
    result_ready = Signal(str, str)
    failed = Signal(str)
    finished = Signal()

    def run(self) -> None:
        try:
            request = urllib.request.Request(
                _API_URL,
                headers={"Accept": "application/vnd.github+json", "User-Agent": "Trichr-o-matic"},
            )
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
            tag = str(data.get("tag_name", "")).strip()
            url = str(data.get("html_url", "")).strip()
            if not tag:
                raise ValueError("release has no tag_name")
            self.result_ready.emit(tag[1:] if tag[:1] in ("v", "V") else tag, url)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
