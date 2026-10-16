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
```

The page reads `../trichrome/` and `../resources/icons/`, so it is served
from the repository root. Pyodide (about 20 MB with numpy, OpenCV and
Pillow) loads from the jsDelivr CDN and is cached by the browser after the
first visit.

## Files

- `index.html`, `style.css`, `app.js`: the page (controls, preview, crop
  overlay, histogram, export).
- `worker.js`: starts Pyodide in a Web Worker and runs the engine there.
- `engine.py`: the bridge to `trichrome/imaging.py` and `alignment.py`
  (same parameter tuples as `main_window.py`).
- `icons/`: icons used only by the web version (the others come from
  `resources/icons/`).
