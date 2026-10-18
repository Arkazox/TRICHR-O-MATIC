# Trichr-o-matic Web

A browser version of Trichr-o-matic, limited to Light mode, with a link to
download the full desktop app.

Everything runs in the visitor's browser: photos are never uploaded. The
image processing reuses `trichrome/imaging.py` and `trichrome/alignment.py`
through Pyodide (Python compiled to WebAssembly); only the interface is
written for the web.

Nothing in this folder is part of the desktop builds.

## Running it locally

```bash
./web/serve.sh          # serves the repo and opens http://localhost:8000/web/
./web/serve.sh --lan    # for a phone on the same Wi-Fi: prints https://<this Mac>:8080/web/
```

`--lan` serves only what the page needs (`web/`, `trichrome/imaging.py`
and `alignment.py`, `resources/` without its private folders), never lists
folders, and stops by itself after an hour. macOS may ask once to let
Python accept incoming connections: allow it.

It serves https, since iPhone keeps the share sheet (Save to Photos) for
secure pages. The certificate is self-signed, made on first use in
`.lan-cert/` (gitignored, never served), for this Mac's address only, not a
certificate authority, valid 30 days. The phone warns once that the
connection isn't private: accept it for that address, never install it.

The page reads `../trichrome/` and `../resources/icons/`, so it is served
from the repository root. Pyodide (about 20 MB with numpy, OpenCV and
Pillow) loads from the jsDelivr CDN and is cached by the browser after the
first visit.

## Files

- `index.html`, `style.css`, `app.js`: the page (controls, preview, crop
  overlay, histogram, export).
- `worker.js`: starts Pyodide in a Web Worker and runs the engine there.
- `manifest.webmanifest`, `sw.js`: installable app (Add to Home Screen).
  The service worker serves the page's files network first (a release shows
  up at once, the stored copy is the offline fallback) and Pyodide cache
  first (versioned URLs). It needs a trusted https page or localhost, so
  `serve.sh --lan` (self-signed certificate) runs without it.
- `engine.py`: the bridge to `trichrome/imaging.py` and `alignment.py`
  (same parameter tuples as `main_window.py`).
- `icons/`: icons used only by the web version (the others come from
  `resources/icons/`).
