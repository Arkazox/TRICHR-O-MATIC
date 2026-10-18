// Runs Pyodide off the main thread, so the page stays responsive while
// Python composes a preview, aligns or exports. app.js talks to it with
// {id, cmd, args} messages and gets {id, ok, result | error} back.
// A module worker: Pyodide no longer supports classic workers.

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v314.0.5/full/";

// Destination in Pyodide's file system -> source, relative to this script.
// The processing modules are read straight from the desktop app's package.
const PYTHON_FILES = {
  "/app/trichrome/__init__.py": null,
  "/app/trichrome/imaging.py": "../trichrome/imaging.py",
  "/app/trichrome/alignment.py": "../trichrome/alignment.py",
  "/app/engine.py": "engine.py",
};

let pyodide = null;
let engine = null;
const channelFiles = [null, null, null];

function status(text) {
  self.postMessage({ type: "status", text });
}

const ready = (async () => {
  const start = performance.now();
  status("Loading Python…");
  const { loadPyodide } = await import(PYODIDE_URL + "pyodide.mjs");
  pyodide = await loadPyodide({ indexURL: PYODIDE_URL });
  status("Loading numpy, OpenCV and Pillow…");
  await pyodide.loadPackage(["numpy", "opencv-python", "pillow"]);
  status("Loading the Trichr-o-matic engine…");
  pyodide.FS.mkdirTree("/app/trichrome");
  pyodide.FS.mkdirTree("/data");
  for (const [dest, src] of Object.entries(PYTHON_FILES)) {
    let text = "";
    if (src) {
      // Revalidated on every load, so an updated engine is never skipped.
      const response = await fetch(new URL(src, self.location.href), { cache: "no-cache" });
      if (!response.ok) throw new Error(`Couldn't load ${src} (${response.status})`);
      text = await response.text();
    }
    pyodide.FS.writeFile(dest, text);
  }
  // imaging.py imports rawpy (LibRaw) at module level. It has no browser
  // build, and only RAW files reach it, which app.js refuses, so an empty
  // module is enough for the import to succeed.
  pyodide.runPython(
    "import sys, types\n" +
    "sys.path.insert(0, '/app')\n" +
    "sys.modules.setdefault('rawpy', types.ModuleType('rawpy'))\n");
  engine = pyodide.pyimport("engine");
  // Every file this load used (Pyodide and its packages among them), for
  // app.js to hand to the service worker: see sw.js.
  const urls = performance.getEntriesByType("resource").map((entry) => entry.name);
  self.postMessage({ type: "ready", ms: Math.round(performance.now() - start), urls });
})();

ready.catch((err) => self.postMessage({ type: "fatal", error: String(err && err.message || err) }));

function toJs(value) {
  if (value === null || value === undefined) return null;
  if (!(value instanceof pyodide.ffi.PyProxy)) return value;
  const converted = value.toJs({ dict_converter: Object.fromEntries });
  value.destroy();
  return converted;
}

function removeFile(index) {
  const path = channelFiles[index];
  if (path) {
    try { pyodide.FS.unlink(path); } catch (_) { /* already gone */ }
  }
  channelFiles[index] = null;
}

// The last line of a Python traceback is the useful part for the user.
function errorText(err) {
  const text = String(err && err.message || err).trim();
  const lines = text.split("\n").filter((l) => l.trim());
  return lines.length ? lines[lines.length - 1] : text;
}

self.onmessage = async (event) => {
  const { id, cmd, args } = event.data;
  try {
    await ready;
    let result = null;
    let transfer = [];
    switch (cmd) {
      case "load": {
        removeFile(args.index);
        // Keep the extension: imaging.py picks the decoder from it.
        const ext = (args.name.match(/\.[A-Za-z0-9]+$/) || [""])[0].toLowerCase();
        const path = `/data/channel${args.index}${ext}`;
        pyodide.FS.writeFile(path, new Uint8Array(args.buffer));
        channelFiles[args.index] = path;
        result = toJs(engine.load_channel(args.index, path, args.color));
        break;
      }
      case "clear":
        engine.clear_channel(args.index);
        removeFile(args.index);
        break;
      case "swap": {
        const { a, b } = args;
        [channelFiles[a], channelFiles[b]] = [channelFiles[b], channelFiles[a]];
        result = toJs(engine.swap_channels(a, b, args.color));
        break;
      }
      case "reload":
        result = toJs(engine.reload_all(args.color));
        break;
      case "render":
        result = toJs(engine.render(args.state));
        if (result) transfer = [result.rgba.buffer];
        break;
      case "autoAlign":
        result = toJs(engine.auto_align(args.state, args.applyDistortion));
        break;
      case "export":
        result = toJs(engine.export_image(args.state, args.format));
        transfer = [result.data.buffer];
        break;
      default:
        throw new Error(`Unknown command ${cmd}`);
    }
    self.postMessage({ id, ok: true, result }, transfer);
  } catch (err) {
    self.postMessage({ id, ok: false, error: errorText(err) });
  }
};
