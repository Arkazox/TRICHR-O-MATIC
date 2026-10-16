"use strict";

// The page: UI state, controls and the canvas. All image processing happens
// in worker.js (Pyodide running trichrome/imaging.py and alignment.py).

const $ = (selector) => document.querySelector(selector);

const CHANNELS = [
  { key: "R", name: "Red", color: "#e05555" },
  { key: "G", name: "Green", color: "#3fae4a" },
  { key: "B", name: "Blue", color: "#4a7fe0" },
];

const ACCEPTED_FILE = /\.(png|jpe?g|tiff?|bmp)$/i;

// [field, label, min, max, default, decimals, percent display, unit]
// Same ranges as the desktop's ChannelPanel and CropPanel.
// Light leaves out Brightness and Contrast (an offset and a linear stretch
// that Exposure, Blacks and Whites cover); they stay at neutral in the state
// sent to the engine.
const SLIDER_GROUPS = {
  position: [
    ["dx", "Offset X", -500, 500, 0, 1, false, ""],
    ["dy", "Offset Y", -500, 500, 0, 1, false, ""],
    ["scale", "Scale", 0.5, 2, 1, 4, false, ""],
    ["rotation", "Rotation", -45, 45, 0, 2, false, "°"],
  ],
  transform: [
    ["distortion", "Distortion", -1, 1, 0, 3, true, ""],
    ["perspective_v", "Vertical", -1, 1, 0, 3, true, ""],
    ["perspective_h", "Horizontal", -1, 1, 0, 3, true, ""],
    ["anamorphic", "Aspect", -1, 1, 0, 3, true, ""],
  ],
  light: [
    ["exposure", "Exposure", -5, 5, 0, 2, false, " EV"],
    ["gamma", "Gamma", 0.1, 4, 1, 2, true, ""],
    ["black_point", "Blacks", -0.5, 0.5, 0, 3, true, ""],
    ["white_point", "Whites", -0.5, 0.5, 0, 3, true, ""],
    ["shadows", "Shadows", -1, 1, 0, 2, true, ""],
    ["highlights", "Highlights", -1, 1, 0, 2, true, ""],
  ],
  straighten: [["rotation", "Straighten", -45, 45, 0, 2, false, "°"]],
};

const RESET_FIELDS = {
  position: ["dx", "dy", "scale", "rotation"],
  transform: ["distortion", "perspective_v", "perspective_h", "anamorphic", "stretch_pins"],
  light: ["exposure", "black_point", "white_point", "gamma", "brightness", "contrast", "shadows", "highlights"],
  // Header of the Trichrome Process block: every per-channel field, applied
  // to all 3 channels.
  process: ["dx", "dy", "scale", "rotation", "distortion", "perspective_v", "perspective_h", "anamorphic",
    "stretch_pins", "exposure", "black_point", "white_point", "gamma", "brightness", "contrast", "shadows",
    "highlights"],
  crop: ["rotation", "mirror_h", "mirror_v", "x", "y", "width", "height", "ratio", "portrait",
    "custom_w", "custom_h"],
};

const DEFAULT_LAYER = Object.freeze({
  dx: 0, dy: 0, scale: 1, rotation: 0,
  distortion: 0, perspective_v: 0, perspective_h: 0, anamorphic: 0,
  // Stretch on Canvas: [anchor_u, anchor_v, delta_u, delta_v] per drag,
  // normalized to the canvas. Always replaced, never mutated in place.
  stretch_pins: Object.freeze([]),
  exposure: 0, black_point: 0, white_point: 0, gamma: 1, brightness: 0, contrast: 1, shadows: 0, highlights: 0,
});

const DEFAULT_CROP = Object.freeze({
  rotation: 0, mirror_h: false, mirror_v: false,
  x: 0, y: 0, width: 1, height: 1, ratio: "original", portrait: false,
  custom_w: 1, custom_h: 1,
  // The Crop block's whole-image Geometry isn't offered here; the engine
  // still takes these, always neutral.
  distortion: 0, perspective_v: 0, perspective_h: 0, anamorphic: 0,
});

const CURVE_CHANNELS = ["Y", "R", "G", "B"];
const IDENTITY_CURVE = Object.freeze([Object.freeze([0, 0]), Object.freeze([1, 1])]);

function newCurves() {
  return Object.fromEntries(CURVE_CHANNELS.map((ch) => [ch, IDENTITY_CURVE]));
}

function newDoc() {
  return {
    layers: CHANNELS.map(() => ({ ...DEFAULT_LAYER })),
    crop: { ...DEFAULT_CROP },
    ref: 1, // green is the default reference, as on the desktop
    curves: newCurves(),
    negative: false, // inverts all 3 channels (raw negative scans)
    quarterTurns: 0, // rotate left/right, in np.rot90 steps (counterclockwise)
  };
}

const app = {
  doc: newDoc(),
  colorTrichrome: false,
  files: [null, null, null],      // {name, width, height}
  visible: [true, true, true],    // Show Layer (view state, not undoable)
  tab: 0,
  moveOnCanvas: false,
  stretch: false,                 // Stretch on Canvas, on the current tab's channel
  solo: null,                     // Solo Layer Preview: channel shown alone in B&W
  draggingChannel: null,          // file row being dragged to swap channels
  compare: false,                 // A|B: show the photo without its Light settings
  cropActive: false,
  cropDraft: null,                // {x, y, width, height} while crop mode is on
  zoom: null,                     // null = Fit, otherwise CSS px per preview px
  image: null,                    // {w, h} of the last rendered preview
  frame: null,                    // {w, h} of the frame before cropping
  undo: [],
  redo: [],
  pendingSnapshot: null,
  engineReady: false,
  pickIndex: 0,
};

// ---------------------------------------------------------------------------
// Worker
// ---------------------------------------------------------------------------

const worker = new Worker("worker.js", { type: "module" });
const pendingCalls = new Map();
let nextCallId = 1;

worker.onmessage = (event) => {
  const message = event.data;
  if (message.type === "status") {
    setActivity("engine", message.text, true);
  } else if (message.type === "ready") {
    app.engineReady = true;
    setActivity("engine", null);
    syncAll();
  } else if (message.type === "fatal") {
    // Stays in the status bar: nothing works until the page is reloaded.
    setActivity("engine", `The engine couldn't start: ${message.error}`);
  } else {
    const call = pendingCalls.get(message.id);
    pendingCalls.delete(message.id);
    if (message.ok) call.resolve(message.result);
    else call.reject(new Error(message.error));
  }
};

// A worker script that fails before it can post anything (Pyodide not
// reachable, for instance) only shows up here.
worker.onerror = (event) => {
  event.preventDefault();
  const reason = event.message || "the engine script didn't load";
  setActivity("engine",
    `The engine couldn't start (${reason}). Check your connection and reload the page.`);
};

function callWorker(cmd, args = {}, transfer = []) {
  return new Promise((resolve, reject) => {
    const id = nextCallId++;
    pendingCalls.set(id, { resolve, reject });
    worker.postMessage({ id, cmd, args }, transfer);
  });
}

// Compare shows the original: each channel's Light section back to neutral,
// while its position and geometry stay, as on the desktop.
function previewLayers() {
  if (!app.compare) return app.doc.layers;
  return app.doc.layers.map((layer) => {
    const neutral = { ...layer };
    for (const field of RESET_FIELDS.light) neutral[field] = DEFAULT_LAYER[field];
    return neutral;
  });
}

function engineState(fullFrame, forExport = false) {
  return JSON.stringify({
    ref: app.doc.ref,
    visible: forExport ? [true, true, true] : app.visible,
    full_frame: fullFrame,
    color_trichrome: app.colorTrichrome,
    layers: forExport ? app.doc.layers : previewLayers(),
    solo: forExport ? null : app.solo,
    // Compare shows the original: no curves, but the Negative stays, as on
    // the desktop.
    curves: app.compare && !forExport ? newCurves() : app.doc.curves,
    negative: !!app.doc.negative,
    crop: app.doc.crop,
    quarter_turns: app.doc.quarterTurns || 0,
  });
}

// ---------------------------------------------------------------------------
// Status bar
// ---------------------------------------------------------------------------

const activities = new Map();
let flashTimer = null;

function setActivity(key, text, spinning = false) {
  if (text) activities.set(key, { text, spinning });
  else activities.delete(key);
  renderActivity();
}

function flashMessage(text) {
  setActivity("flash", text);
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => setActivity("flash", null), 6000);
}

function renderActivity() {
  const el = $("#activity");
  el.textContent = "";
  const entries = [...activities.values()];
  if (entries.some((a) => a.spinning)) {
    const spinner = document.createElement("span");
    spinner.className = "spinner";
    el.append(spinner);
  }
  el.append(entries.map((a) => a.text).join(" · "));
}


// ---------------------------------------------------------------------------
// Undo / redo: snapshots of app.doc, taken around each edit
// ---------------------------------------------------------------------------

function beginEdit() {
  if (app.pendingSnapshot === null) app.pendingSnapshot = JSON.stringify(app.doc);
}

function endEdit() {
  if (app.pendingSnapshot === null) return;
  const before = app.pendingSnapshot;
  app.pendingSnapshot = null;
  if (before !== JSON.stringify(app.doc)) {
    app.undo.push(before);
    if (app.undo.length > 200) app.undo.shift();
    app.redo = [];
  }
}

function edit(change) {
  beginEdit();
  change();
  endEdit();
  syncAll();
  requestRender();
}

function restoreFrom(from, to) {
  if (!from.length) return;
  to.push(JSON.stringify(app.doc));
  app.doc = JSON.parse(from.pop());
  if (app.cropActive) app.cropDraft = cropRectOf(app.doc.crop);
  syncAll();
  requestRender();
}

// ---------------------------------------------------------------------------
// Sliders: the default sits at the middle of the track whatever the range
// ---------------------------------------------------------------------------

const sliders = [];

function makeSlider(container, spec, group, target) {
  const [field, label, min, max, def, decimals, percent, unit] = spec;
  const toPos = (v) => (v >= def
    ? (max === def ? 0 : ((v - def) / (max - def)) * 1000)
    : -((def - v) / (def - min)) * 1000);
  const fromPos = (p) => (p >= 0 ? def + (p / 1000) * (max - def) : def + (p / 1000) * (def - min));
  const round = (v) => Number(v.toFixed(decimals));

  const root = document.createElement("div");
  root.className = "slider";
  root.title = "Double-click to reset";
  const head = document.createElement("div");
  head.className = "slider-head";
  const name = document.createElement("span");
  name.textContent = label;
  const value = document.createElement("span");
  value.className = "value";
  head.append(name, value);
  const input = document.createElement("input");
  input.type = "range";
  input.min = -1000;
  input.max = 1000;
  input.step = 1;
  root.append(head, input);
  container.append(root);

  function look() {
    const v = target()[field];
    const pos = toPos(v);
    value.textContent = percent
      ? `${Math.round(pos / 10) > 0 ? "+" : ""}${Math.round(pos / 10)}`
      : `${v.toFixed(decimals)}${unit}`;
    const p = 50 + pos / 20;
    const lo = Math.min(50, p), hi = Math.max(50, p);
    input.style.setProperty("--track",
      `linear-gradient(to right, #555 ${lo}%, var(--accent) ${lo}%, var(--accent) ${hi}%, #555 ${hi}%)`);
  }

  input.addEventListener("input", () => {
    beginEdit();
    target()[field] = round(fromPos(Number(input.value)));
    look();
    requestRender();
  });
  input.addEventListener("change", () => { endEdit(); syncResetButtons(); });
  root.addEventListener("dblclick", () => {
    beginEdit();
    target()[field] = def;
    sync();
    requestRender();
    endEdit();
    syncResetButtons();
  });

  function sync() {
    input.value = toPos(target()[field]);
    look();
  }

  const slider = {
    group, sync,
    setDisabled(disabled) {
      root.classList.toggle("disabled", disabled);
      input.disabled = disabled;
    },
  };
  sliders.push(slider);
  return slider;
}

function buildSliders() {
  const current = () => app.doc.layers[app.tab];
  const crop = () => app.doc.crop;
  for (const group of ["position", "transform", "light"]) {
    SLIDER_GROUPS[group].forEach((spec) => makeSlider($(`#sliders-${group}`), spec, group, current));
  }
  SLIDER_GROUPS.straighten.forEach((spec) => makeSlider($("#sliders-straighten"), spec, "straighten", crop));
}

// ---------------------------------------------------------------------------
// Files block
// ---------------------------------------------------------------------------

function buildFileRows() {
  const container = $("#channel-files");
  CHANNELS.forEach((channel, index) => {
    // The colored dot is the slot and stays outside the box; the box is the
    // photo, which is what a drag moves.
    const slot = document.createElement("div");
    slot.className = "channel-slot";
    slot.innerHTML = `<span class="channel-dot" title="${channel.name}" style="background:${channel.color}"></span>`;
    const row = document.createElement("div");
    row.className = "channel-file";
    row.dataset.index = index;
    row.innerHTML = `
      <span class="icon grip" title="Drag onto another channel to swap the photos"
        style="--icon: url(../resources/icons/Global/grip-vertical.svg)"></span>
      <span class="file-name"></span>
      <span class="file-size"></span>
      <button class="icon-button remove" title="Remove">
        <span class="icon" style="--icon: url(../resources/icons/Global/close.svg)"></span>
      </button>`;
    row.addEventListener("click", (event) => {
      if (event.target.closest(".remove")) return;
      app.pickIndex = index;
      $("#file-input").click();
    });
    row.querySelector(".remove").addEventListener("click", () => removeChannel(index));
    // Dragging a loaded row onto another swaps the two photos, each with
    // its own settings; the slot's color and the reference stay put.
    row.addEventListener("dragstart", (event) => {
      app.draggingChannel = index;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", CHANNELS[index].name);
      row.classList.add("dragging");
    });
    row.addEventListener("dragend", () => {
      app.draggingChannel = null;
      document.querySelectorAll(".channel-file").forEach((r) => r.classList.remove("dragging", "swap-target"));
    });
    row.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (app.draggingChannel === null) row.classList.add("drag-over");
      else if (app.draggingChannel !== index) row.classList.add("swap-target");
    });
    row.addEventListener("dragleave", () => row.classList.remove("drag-over", "swap-target"));
    row.addEventListener("drop", (event) => {
      event.preventDefault();
      event.stopPropagation();
      row.classList.remove("drag-over", "swap-target");
      if (app.draggingChannel !== null) {
        const from = app.draggingChannel;
        app.draggingChannel = null;
        swapChannels(from, index);
        return;
      }
      const file = event.dataTransfer.files[0];
      if (file) loadChannel(index, file);
    });
    slot.append(row);
    container.append(slot);
  });

  $("#file-input").addEventListener("change", (event) => {
    const file = event.target.files[0];
    event.target.value = "";
    if (file) loadChannel(app.pickIndex, file);
  });
}

function syncFileRows() {
  document.querySelectorAll(".channel-file").forEach((row) => {
    const index = Number(row.dataset.index);
    const file = app.files[index];
    const name = row.querySelector(".file-name");
    row.classList.toggle("loaded", !!file);
    name.classList.toggle("empty", !file);
    name.textContent = file ? file.name : `${CHANNELS[index].name}: choose or drop a file`;
    name.title = file ? file.name : "";
    row.querySelector(".file-size").textContent = file ? `${file.width}×${file.height}` : "";
    row.querySelector(".remove").hidden = !file;
    row.draggable = !!file;
  });
}

// Auto align on import: once a round of loads ends (3 dropped files load
// at the same time) with all 3 channels present, align them, as the
// desktop's Batch Import does with its Auto align option. Always on: the
// web version keeps its options to a minimum.
let pendingLoads = 0;
let loadedSinceAlign = false;

async function loadChannel(index, file) {
  if (!ACCEPTED_FILE.test(file.name)) {
    flashMessage(`${file.name}: the web version opens PNG, JPEG, TIFF and BMP. ` +
      "RAW files need the full app.");
    return;
  }
  const wasEmpty = !anyLoaded();
  const key = `load${index}`;
  setActivity(key, `Loading ${file.name}…`, true);
  pendingLoads++;
  try {
    const buffer = await file.arrayBuffer();
    const result = await callWorker("load",
      { index, name: file.name, buffer, color: app.colorTrichrome }, [buffer]);
    app.files[index] = { name: file.name, width: result.width, height: result.height };
    loadedSinceAlign = true;
    if (wasEmpty) app.zoom = null;
  } catch (err) {
    flashMessage(`${file.name} couldn't be opened: ${err.message}`);
  } finally {
    setActivity(key, null);
    pendingLoads--;
  }
  syncAll();
  requestRender();
  syncPhoneCrop();
  if (pendingLoads === 0 && loadedSinceAlign && app.files.every(Boolean)) {
    loadedSinceAlign = false;
    autoAlign();
  }
}

async function swapChannels(a, b) {
  if (a === b || !(app.files[a] || app.files[b])) return;
  setActivity("swap", "Swapping channels…", true);
  try {
    await callWorker("swap", { a, b, color: app.colorTrichrome });
  } catch (err) {
    flashMessage(`The channels couldn't be swapped: ${err.message}`);
    return;
  } finally {
    setActivity("swap", null);
  }
  [app.files[a], app.files[b]] = [app.files[b], app.files[a]];
  const swapLayers = (doc) => { [doc.layers[a], doc.layers[b]] = [doc.layers[b], doc.layers[a]]; };
  swapLayers(app.doc);
  // The history follows the photos too, so an undo never puts one photo's
  // settings on the other.
  const swapSnapshot = (snapshot) => {
    const doc = JSON.parse(snapshot);
    swapLayers(doc);
    return JSON.stringify(doc);
  };
  app.undo = app.undo.map(swapSnapshot);
  app.redo = app.redo.map(swapSnapshot);
  flashMessage(`${CHANNELS[a].name} and ${CHANNELS[b].name} swapped.`);
  syncAll();
  requestRender();
}

async function removeChannel(index) {
  await callWorker("clear", { index });
  app.files[index] = null;
  syncAll();
  requestRender();
}

// Same tokens and order of tries as the desktop's Batch Import
// (trichrome/filters.py, batch.detect_filter): a trailing separated token,
// then a leading one, then a bare 2- or 1-letter one at either end.
const CHANNEL_TOKENS = [["r", "red", "rouge"], ["g", "v", "green", "vert"], ["b", "blue", "bleu"]];
const NAME_SEPARATORS = ["_", "-", " ", "."];

function channelForToken(token) {
  const index = CHANNEL_TOKENS.findIndex((tokens) => tokens.includes(token.toLowerCase()));
  return index < 0 ? null : index;
}

function channelFromFileName(name) {
  const stem = name.replace(/\.[^.]+$/, "");
  for (const sep of NAME_SEPARATORS) {
    const at = stem.lastIndexOf(sep);
    if (at > 0) {
      const index = channelForToken(stem.slice(at + 1));
      if (index !== null) return index;
    }
  }
  for (const sep of NAME_SEPARATORS) {
    const at = stem.indexOf(sep);
    if (at > 0 && at < stem.length - 1) {
      const index = channelForToken(stem.slice(0, at));
      if (index !== null) return index;
    }
  }
  for (const n of [2, 1]) {
    if (stem.length > n) {
      const index = channelForToken(stem.slice(-n)) ?? channelForToken(stem.slice(0, n));
      if (index !== null) return index;
    }
  }
  return null;
}

function loadDroppedFiles(fileList) {
  const files = [...fileList].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
  if (files.length >= 3) {
    const picked = files.slice(0, 3);
    const detected = picked.map((file) => channelFromFileName(file.name));
    const recognized = new Set(detected).size === 3 && !detected.includes(null);
    picked.forEach((file, n) => loadChannel(recognized ? detected[n] : n, file));
    return;
  }
  // Fewer than 3: fill the empty channels first, in R, G, B order.
  const empty = [0, 1, 2].filter((i) => !app.files[i]);
  const slots = empty.length >= files.length ? empty : [0, 1, 2];
  files.forEach((file, n) => loadChannel(slots[n], file));
}

async function startOver() {
  if (anyLoaded() && !confirm("Remove the 3 photos and reset every setting?")) return;
  if (app.cropActive) exitCrop();
  await Promise.all([0, 1, 2].map((index) => callWorker("clear", { index })));
  app.files = [null, null, null];
  app.doc = newDoc();
  app.undo = [];
  app.redo = [];
  app.visible = [true, true, true];
  app.moveOnCanvas = false;
  app.compare = false;
  app.solo = null;
  syncAll();
  requestRender();
}

async function changeMode(color) {
  app.colorTrichrome = color;
  if (!anyLoaded()) return;
  setActivity("mode", "Reloading the photos…", true);
  try {
    await callWorker("reload", { color });
  } catch (err) {
    flashMessage(`The photos couldn't be reloaded: ${err.message}`);
  } finally {
    setActivity("mode", null);
  }
  requestRender();
}

function anyLoaded() {
  return app.files.some(Boolean);
}

// ---------------------------------------------------------------------------
// Trichrome Process block
// ---------------------------------------------------------------------------

function buildChannelControls() {
  const toggles = $("#show-layer");
  const tabs = $("#channel-tabs");
  const lockButtons = $("#reference-buttons");
  CHANNELS.forEach((channel, index) => {
    const toggle = document.createElement("button");
    toggle.className = "layer-toggle";
    toggle.style.color = channel.color;
    toggle.innerHTML = '<span class="icon"></span>';
    toggle.title = `Show the ${channel.name.toLowerCase()} layer`;
    toggle.addEventListener("click", () => {
      const next = [...app.visible];
      next[index] = !next[index];
      if (!next.some(Boolean)) return; // at least one layer stays on
      app.visible = next;
      syncAll();
      requestRender();
    });
    toggles.append(toggle);

    const tab = document.createElement("button");
    tab.className = "tab";
    tab.textContent = channel.name;
    tab.style.color = channel.color;
    tab.addEventListener("click", () => {
      app.tab = index;
      // Solo follows the tab, like Stretch on Canvas.
      if (app.solo !== null) app.solo = app.files[index] ? index : null;
      requestRender();
      if (app.moveOnCanvas && index === app.doc.ref) app.moveOnCanvas = false;
      syncAll();
    });
    tabs.append(tab);

    const lock = document.createElement("button");
    lock.className = "lock-toggle";
    lock.style.color = channel.color;
    lock.setAttribute("role", "radio");
    lock.title = `Lock the ${channel.name.toLowerCase()} layer`;
    lock.innerHTML = '<span class="dot"></span>';
    lock.addEventListener("click", () => {
      if (app.doc.ref === index) return;
      edit(() => {
        app.doc.ref = index;
        // The new reference is locked at the identity.
        for (const field of RESET_FIELDS.position) app.doc.layers[index][field] = DEFAULT_LAYER[field];
        if (app.tab === index) app.moveOnCanvas = false;
      });
    });
    lockButtons.append(lock);
  });

  // Move and Stretch on Canvas are one drag mode at a time.
  $("#move-on-canvas").addEventListener("change", (event) => {
    app.moveOnCanvas = event.target.checked;
    if (app.moveOnCanvas) app.stretch = false;
    syncAll();
  });
  $("#stretch-on-canvas").addEventListener("change", (event) => {
    app.stretch = event.target.checked;
    if (app.stretch) {
      app.moveOnCanvas = false;
      if (app.cropActive) exitCrop();
    }
    syncAll();
  });
  $("#solo").addEventListener("change", (event) => {
    app.solo = event.target.checked ? app.tab : null;
    syncAll();
    requestRender();
  });
  $("#reset-stretch").addEventListener("click", () => edit(() => {
    app.doc.layers[app.tab].stretch_pins = [];
  }));

  $("#auto-align").addEventListener("click", autoAlign);
}

async function autoAlign() {
  if (activities.has("align")) return; // already running
  const button = $("#auto-align");
  button.disabled = true;
  setActivity("align", "Auto Align…", true);
  try {
    const result = await callWorker("autoAlign", {
      state: engineState(false, true),
      applyDistortion: false, // position only: the lens search isn't offered here
    });
    edit(() => {
      for (const [index, values] of Object.entries(result.results)) {
        const layer = app.doc.layers[Number(index)];
        for (const [field, value] of Object.entries(values)) layer[field] = Number(value.toFixed(4));
      }
    });
    if (result.failed.length) {
      flashMessage(`Auto Align couldn't align: ${result.failed.map((i) => CHANNELS[i].name).join(", ")}`);
    } else {
      flashMessage("Auto Align done.");
    }
  } catch (err) {
    flashMessage(`Auto Align failed: ${err.message}`);
  } finally {
    setActivity("align", null);
    syncAll();
  }
}

// ---------------------------------------------------------------------------
// Reset buttons
// ---------------------------------------------------------------------------

// The objects a section's Reset applies to.
function resetTargets(section) {
  if (section === "crop") return [app.doc.crop];
  if (section === "process") return app.doc.layers;
  return [app.doc.layers[app.tab]];
}

function resetDefaults(section) {
  return section === "crop" ? DEFAULT_CROP : DEFAULT_LAYER;
}

function sameValue(a, b) {
  return Array.isArray(a) ? JSON.stringify(a) === JSON.stringify(b) : a === b;
}

function canReset(section) {
  const defaults = resetDefaults(section);
  if (section === "position" && app.tab === app.doc.ref) return false;
  return resetTargets(section).some((target) =>
    RESET_FIELDS[section].some((field) => !sameValue(target[field], defaults[field])));
}

function buildResetButtons() {
  document.querySelectorAll("[data-reset]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault(); // inside a <summary>: don't fold the section
      event.stopPropagation();
      const section = button.dataset.reset;
      edit(() => {
        const defaults = resetDefaults(section);
        for (const target of resetTargets(section)) {
          for (const field of RESET_FIELDS[section]) target[field] = defaults[field];
        }
      });
      if (section === "crop" && app.cropActive) app.cropDraft = cropRectOf(app.doc.crop);
    });
  });
}

function syncResetButtons() {
  document.querySelectorAll("[data-reset]").forEach((button) => {
    button.disabled = !canReset(button.dataset.reset);
  });
}

// ---------------------------------------------------------------------------
// Framing: crop mode, ratio, straighten, mirror
// ---------------------------------------------------------------------------

function cropRectOf(crop) {
  return { x: crop.x, y: crop.y, width: crop.width, height: crop.height };
}

// Width / height in frame pixels, or null for Free.
function cropRatio() {
  const { ratio, portrait } = app.doc.crop;
  if (ratio === "free" || !app.frame) return null;
  if (ratio === "original") return app.frame.w / app.frame.h;
  if (ratio === "custom") {
    const { custom_w: w, custom_h: h } = app.doc.crop;
    const r = w > 0 && h > 0 ? w / h : 1;
    return portrait ? 1 / r : r;
  }
  const [a, b] = ratio.split(":").map(Number);
  // A preset follows the frame's orientation unless inverted.
  const r = app.frame.w >= app.frame.h ? a / b : b / a;
  return portrait ? 1 / r : r;
}

// The largest centered rectangle of the current ratio, normalized.
function centeredRatioRect() {
  const r = cropRatio();
  if (!r) return { x: 0, y: 0, width: 1, height: 1 };
  const { w, h } = app.frame;
  let width = 1, height = 1;
  if (w / h > r) width = (r * h) / w;
  else height = w / (r * h);
  return { x: (1 - width) / 2, y: (1 - height) / 2, width, height };
}

function enterCrop() {
  if (!anyLoaded() || app.cropActive) return;
  app.cropActive = true;
  app.moveOnCanvas = false;
  app.stretch = false;
  app.cropDraft = cropRectOf(app.doc.crop);
  syncAll();
  requestRender();
}

function commitCrop() {
  const draft = app.cropDraft;
  edit(() => Object.assign(app.doc.crop, draft));
  exitCrop();
}

function exitCrop() {
  app.cropActive = false;
  app.cropDraft = null;
  syncAll();
  requestRender();
}

function buildFramingControls() {
  $("#crop-toggle").addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (app.cropActive) commitCrop();
    else enterCrop();
  });
  $("#ratio").addEventListener("change", (event) => {
    edit(() => { app.doc.crop.ratio = event.target.value; });
    applyRatioToDraft();
  });
  for (const [id, field] of [["#custom-w", "custom_w"], ["#custom-h", "custom_h"]]) {
    $(id).addEventListener("change", (event) => {
      const value = Math.min(100, Math.max(0.1, Number(event.target.value) || 1));
      edit(() => { app.doc.crop[field] = Number(value.toFixed(1)); });
      applyRatioToDraft();
    });
  }
  $("#orientation").addEventListener("click", () => {
    edit(() => { app.doc.crop.portrait = !app.doc.crop.portrait; });
    applyRatioToDraft();
  });
  $("#mirror-h").addEventListener("click", () => edit(() => { app.doc.crop.mirror_h = !app.doc.crop.mirror_h; }));
  $("#mirror-v").addEventListener("click", () => edit(() => { app.doc.crop.mirror_v = !app.doc.crop.mirror_v; }));
}

function applyRatioToDraft() {
  if (!anyLoaded()) return;
  if (!app.cropActive) enterCrop();
  if (app.doc.crop.ratio !== "free") app.cropDraft = centeredRatioRect();
  drawOverlay();
}

// ---------------------------------------------------------------------------
// Preview canvas
// ---------------------------------------------------------------------------

let renderBusy = false;
let renderDirty = false;

function requestRender() {
  renderDirty = true;
  if (!renderBusy) pumpRender();
}

// One render in flight at a time; edits made meanwhile are coalesced into
// the next one, so slider drags never queue up stale frames.
async function pumpRender() {
  while (renderDirty) {
    renderDirty = false;
    if (!anyLoaded()) {
      showPlaceholder(true);
      drawHistogram(null);
      return;
    }
    renderBusy = true;
    try {
      const result = await callWorker("render", { state: engineState(app.cropActive) });
      if (result) {
        drawPreview(result);
      }
    } catch (err) {
      flashMessage(`Preview failed: ${err.message}`);
    } finally {
      renderBusy = false;
    }
  }
}

function showPlaceholder(show) {
  $("#placeholder").hidden = !show;
  $("#stage").hidden = show;
  if (show) app.image = null;
}

function drawPreview(result) {
  const canvas = $("#preview");
  canvas.width = result.width;
  canvas.height = result.height;
  const pixels = new Uint8ClampedArray(result.rgba.buffer, result.rgba.byteOffset, result.rgba.byteLength);
  canvas.getContext("2d").putImageData(new ImageData(pixels, result.width, result.height), 0, 0);
  app.image = { w: result.width, h: result.height };
  app.frame = { w: result.frame_w, h: result.frame_h };
  showPlaceholder(false);
  drawHistogram(result.hist);
  curveUI.histograms = result.hist_pre;
  drawCurveEditor();
  layoutStage();
}

function fitScale() {
  const viewport = $("#viewport");
  const pad = 24;
  return Math.max(0.02, Math.min(
    (viewport.clientWidth - pad) / app.image.w,
    (viewport.clientHeight - pad) / app.image.h));
}

function displayScale() {
  return app.zoom ?? fitScale();
}

function layoutStage() {
  if (!app.image) return;
  const scale = displayScale();
  const width = Math.round(app.image.w * scale);
  const height = Math.round(app.image.h * scale);
  const stage = $("#stage");
  stage.style.width = `${width}px`;
  stage.style.height = `${height}px`;
  for (const canvas of [$("#preview"), $("#overlay")]) {
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
  }
  $("#zoom-fit").title = `Fit to window (F) · zoom ${Math.round(scale * 100)}%`;
  $("#zoom-fit").classList.toggle("on", app.zoom === null);
  $("#zoom-100").classList.toggle("on", app.zoom === 1);
  drawOverlay();
}

function setZoom(zoom) {
  app.zoom = zoom === null ? null : Math.min(8, Math.max(0.05, zoom));
  layoutStage();
}

// Rotate what's on screen by 90°. The source pixels turn (np.rot90), so
// with a single mirror on, the source turns the other way for the picture
// to turn the way the button says. Each channel's offset turns with it
// (ChannelLayer.rotate_quarter), and the crop rectangle turns with the frame.
function rotatePhoto(clockwise) {
  if (!anyLoaded()) return;
  const crop = app.doc.crop;
  const sourceClockwise = (crop.mirror_h !== crop.mirror_v) ? !clockwise : clockwise;
  edit(() => {
    app.doc.quarterTurns = (((app.doc.quarterTurns || 0) + (sourceClockwise ? -1 : 1)) % 4 + 4) % 4;
    for (const layer of app.doc.layers) {
      const { dx, dy } = layer;
      [layer.dx, layer.dy] = sourceClockwise ? [-dy || 0, dx] : [dy, -dx || 0];
      layer.stretch_pins = (layer.stretch_pins || []).map(([u, v, du, dv]) => (sourceClockwise
        ? [1 - v, u, -dv, du]
        : [v, 1 - u, dv, -du]));
    }
    const { x, y, width, height } = crop;
    Object.assign(crop, clockwise
      ? { x: 1 - (y + height), y: x, width: height, height: width }
      : { x: y, y: 1 - (x + width), width: height, height: width });
  });
  if (app.cropActive) app.cropDraft = cropRectOf(app.doc.crop);
  app.zoom = null;
}

function setCompare(on) {
  if (on && !anyLoaded()) return;
  app.compare = on;
  syncAll();
  requestRender();
}

function toggleFullscreen() {
  const entering = !document.body.classList.contains("focus");
  document.body.classList.toggle("focus", entering);
  if (entering) document.documentElement.requestFullscreen?.().catch(() => {});
  else if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  syncFullscreenButton();
  requestAnimationFrame(() => { if (app.zoom === null) layoutStage(); });
}

function syncFullscreenButton() {
  const on = document.body.classList.contains("focus");
  $("#fullscreen").classList.toggle("on", on);
  $("#fullscreen .icon").style.setProperty("--icon",
    `url(../resources/icons/Filmstrip/${on ? "fullscreen_exit" : "fullscreen"}.svg)`);
  $("#fullscreen").title = on ? "Exit full screen (Esc)" : "Full screen (⌘F)";
}

function buildViewControls() {
  $("#rotate-left").addEventListener("click", () => rotatePhoto(false));
  $("#rotate-right").addEventListener("click", () => rotatePhoto(true));
  $("#crop-rotate-left").addEventListener("click", () => rotatePhoto(false));
  $("#crop-rotate-right").addEventListener("click", () => rotatePhoto(true));
  $("#compare").addEventListener("click", () => setCompare(!app.compare));
  $("#fullscreen").addEventListener("click", toggleFullscreen);
  // Leaving the browser's full screen (Esc) also leaves the panel-less view.
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement && document.body.classList.contains("focus")) {
      document.body.classList.remove("focus");
      syncFullscreenButton();
      requestAnimationFrame(() => { if (app.zoom === null) layoutStage(); });
    }
  });
}

// Zoom the preview keeping the image point under (clientX, clientY) in place.
function zoomAt(zoom, clientX, clientY) {
  if (!app.image) return;
  const viewport = $("#viewport");
  const stage = $("#stage");
  const before = stage.getBoundingClientRect();
  const oldScale = displayScale();
  const ix = (clientX - before.left) / oldScale;
  const iy = (clientY - before.top) / oldScale;
  setZoom(zoom);
  const after = stage.getBoundingClientRect();
  const newScale = displayScale();
  viewport.scrollLeft += after.left + ix * newScale - clientX;
  viewport.scrollTop += after.top + iy * newScale - clientY;
}

function zoomAtCenter(zoom) {
  const bounds = $("#viewport").getBoundingClientRect();
  zoomAt(zoom, bounds.left + bounds.width / 2, bounds.top + bounds.height / 2);
}

function overViewport(event) {
  return $("#viewport").contains(event.target);
}

function buildPinchZoom() {
  // A trackpad pinch (and Ctrl/⌘ + wheel) arrives as a wheel event with
  // ctrlKey set; the browser would zoom the whole page with it.
  window.addEventListener("wheel", (event) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    if (!overViewport(event) || !app.image) return;
    const delta = Math.max(-50, Math.min(50, event.deltaY));
    zoomAt(displayScale() * Math.exp(-delta * 0.01), event.clientX, event.clientY);
  }, { passive: false });

  // Safari reports a pinch as gesture events instead. On a touch screen the
  // touch handlers below zoom (every browser sends those); the gesture events
  // are only cancelled there, or iOS would zoom the whole page.
  let gestureStart = null;
  const onGesture = (event) => {
    event.preventDefault();
    if (touchPinch) return;
    if (event.type === "gesturestart") {
      gestureStart = overViewport(event) && app.image ? displayScale() : null;
    } else if (event.type === "gesturechange" && gestureStart !== null) {
      zoomAt(gestureStart * event.scale, event.clientX, event.clientY);
    } else if (event.type === "gestureend") {
      gestureStart = null;
    }
  };
  for (const type of ["gesturestart", "gesturechange", "gestureend"]) {
    window.addEventListener(type, onGesture, { passive: false });
  }

  // Touch: two fingers pinch around their midpoint; a double tap switches
  // between fit and 1:1 (at the tapped point); a long press shows the
  // original (Compare) until the finger lifts.
  const viewport = $("#viewport");
  const spread = (touches) => Math.hypot(
    touches[0].clientX - touches[1].clientX, touches[0].clientY - touches[1].clientY);
  const midpoint = (touches) => [
    (touches[0].clientX + touches[1].clientX) / 2, (touches[0].clientY + touches[1].clientY) / 2];
  let tap = null;
  let lastTap = null;
  let holdTimer = null;
  let holdCompare = false;
  const cancelHold = () => { clearTimeout(holdTimer); holdTimer = null; };
  const endHold = () => {
    cancelHold();
    if (holdCompare) { holdCompare = false; setCompare(false); }
  };
  viewport.addEventListener("touchstart", (event) => {
    cancelHold();
    if (event.touches.length === 2 && app.image) {
      touchPinch = { distance: spread(event.touches), scale: displayScale() };
      tap = null;
      endHold();
    } else if (event.touches.length === 1) {
      const t = event.touches[0];
      tap = { x: t.clientX, y: t.clientY, time: event.timeStamp };
      // Not while cropping (the press may start a frame drag), nor when
      // Compare is already on from its button.
      if (app.image && !app.cropActive && !app.compare) {
        holdTimer = setTimeout(() => {
          holdTimer = null;
          holdCompare = true;
          tap = null; // a hold isn't a tap
          setCompare(true);
        }, LONG_PRESS_MS);
      }
    } else {
      tap = null;
    }
  }, { passive: true });
  viewport.addEventListener("touchmove", (event) => {
    if (tap || holdTimer) {
      const t = event.touches[0];
      const start = tap || { x: t.clientX, y: t.clientY };
      if (Math.hypot(t.clientX - start.x, t.clientY - start.y) > DOUBLE_TAP_DIST / 2) {
        tap = null;
        cancelHold();
      }
    }
    if (!touchPinch || event.touches.length !== 2) return;
    event.preventDefault();
    const [x, y] = midpoint(event.touches);
    zoomAt(touchPinch.scale * spread(event.touches) / touchPinch.distance, x, y);
  }, { passive: false });
  viewport.addEventListener("touchend", (event) => {
    if (event.touches.length < 2) touchPinch = null;
    if (!event.touches.length) endHold();
    if (!tap || event.touches.length) return;
    const isDouble = lastTap && tap.time - lastTap.time < DOUBLE_TAP_MS
      && Math.hypot(tap.x - lastTap.x, tap.y - lastTap.y) < DOUBLE_TAP_DIST;
    lastTap = isDouble ? null : tap;
    if (isDouble && app.image) {
      event.preventDefault();
      if (app.zoom === null) zoomAt(1, tap.x, tap.y);
      else setZoom(null);
    }
    tap = null;
  });
  viewport.addEventListener("touchcancel", () => { touchPinch = null; tap = null; endHold(); });
  // No text-selection loupe or image menu on a long press.
  viewport.addEventListener("contextmenu", (event) => {
    if (holdCompare || holdTimer) event.preventDefault();
  });
}

let touchPinch = null;
const LONG_PRESS_MS = 450;

function buildZoomControls() {
  $("#zoom-in").addEventListener("click", () => zoomAtCenter(displayScale() * 1.25));
  $("#zoom-out").addEventListener("click", () => zoomAtCenter(displayScale() / 1.25));
  $("#zoom-fit").addEventListener("click", () => setZoom(null));
  $("#zoom-100").addEventListener("click", () => setZoom(1));
  window.addEventListener("resize", () => { if (app.zoom === null) layoutStage(); drawHistogram(lastHistogram); });
}

// ---------------------------------------------------------------------------
// Crop overlay
// ---------------------------------------------------------------------------

const HANDLE = 12; // CSS px hit radius around a corner
let cropDrag = null;

function draftRectPx() {
  const d = app.cropDraft;
  const { w, h } = app.frame;
  return { x: d.x * w, y: d.y * h, w: d.width * w, h: d.height * h };
}

function setDraftFromPx(rect) {
  const { w, h } = app.frame;
  app.cropDraft = { x: rect.x / w, y: rect.y / h, width: rect.w / w, height: rect.h / h };
}

function drawOverlay() {
  const overlay = $("#overlay");
  const ctx = overlay.getContext("2d");
  const active = app.cropActive && app.cropDraft && app.image
    && app.frame && app.image.w === app.frame.w && app.image.h === app.frame.h;
  const scale = app.image ? displayScale() : 1;
  const dpr = window.devicePixelRatio || 1;
  const cssW = app.image ? Math.round(app.image.w * scale) : 0;
  const cssH = app.image ? Math.round(app.image.h * scale) : 0;
  overlay.width = Math.max(1, Math.round(cssW * dpr));
  overlay.height = Math.max(1, Math.round(cssH * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);
  if (app.stretch && app.image && !app.cropActive) drawStretchGrid(ctx, cssW, cssH);
  if (!active) return;

  const r = draftRectPx();
  const x = r.x * scale, y = r.y * scale, w = r.w * scale, h = r.h * scale;
  ctx.fillStyle = "rgba(0, 0, 0, 0.55)";
  ctx.beginPath();
  ctx.rect(0, 0, cssW, cssH);
  ctx.rect(x, y, w, h);
  ctx.fill("evenodd");

  ctx.strokeStyle = "rgba(255, 255, 255, 0.35)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (const t of [1 / 3, 2 / 3]) {
    ctx.moveTo(x + w * t, y); ctx.lineTo(x + w * t, y + h);
    ctx.moveTo(x, y + h * t); ctx.lineTo(x + w, y + h * t);
  }
  ctx.stroke();

  ctx.strokeStyle = "#fff";
  ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
  ctx.lineWidth = 3;
  const l = Math.min(16, w / 3, h / 3);
  ctx.beginPath();
  for (const [cx, cy, sx, sy] of [[x, y, 1, 1], [x + w, y, -1, 1], [x, y + h, 1, -1], [x + w, y + h, -1, -1]]) {
    ctx.moveTo(cx + sx * l, cy + sy * 1.5);
    ctx.lineTo(cx + sx * 1.5, cy + sy * 1.5);
    ctx.lineTo(cx + sx * 1.5, cy + sy * l);
  }
  ctx.stroke();
}

// The reference grid shown while Stretch on Canvas is on: square cells over
// the displayed image, each vertex pulled by the current channel's pins.
const STRETCH_GRID_CELL_PX = 36;

function drawStretchGrid(ctx, width, height) {
  const cols = Math.max(1, Math.round(width / STRETCH_GRID_CELL_PX));
  const rows = Math.max(1, Math.round(height / STRETCH_GRID_CELL_PX));
  const pins = app.doc.layers[app.tab].stretch_pins;
  const vertex = (col, row) => {
    const c = displayToCanvas(col / cols, row / rows);
    const w = pins.length ? warpStretchPoint(c.u, c.v, pins) : c;
    const d = canvasToDisplay(w.u, w.v);
    return [d.fx * width, d.fy * height];
  };
  const grid = [];
  for (let row = 0; row <= rows; row++) {
    grid.push([]);
    for (let col = 0; col <= cols; col++) grid[row].push(vertex(col, row));
  }
  ctx.strokeStyle = "rgba(255, 255, 255, 0.43)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let row = 0; row <= rows; row++) {
    ctx.moveTo(...grid[row][0]);
    for (let col = 1; col <= cols; col++) ctx.lineTo(...grid[row][col]);
  }
  for (let col = 0; col <= cols; col++) {
    ctx.moveTo(...grid[0][col]);
    for (let row = 1; row <= rows; row++) ctx.lineTo(...grid[row][col]);
  }
  ctx.stroke();
}

function framePoint(event) {
  const bounds = $("#overlay").getBoundingClientRect();
  const scale = displayScale();
  return {
    x: Math.min(app.frame.w, Math.max(0, (event.clientX - bounds.left) / scale)),
    y: Math.min(app.frame.h, Math.max(0, (event.clientY - bounds.top) / scale)),
  };
}

function cropHit(p) {
  const r = draftRectPx();
  const tolerance = HANDLE / displayScale();
  const corners = {
    nw: [r.x, r.y], ne: [r.x + r.w, r.y], sw: [r.x, r.y + r.h], se: [r.x + r.w, r.y + r.h],
  };
  for (const [name, [cx, cy]] of Object.entries(corners)) {
    if (Math.abs(p.x - cx) <= tolerance && Math.abs(p.y - cy) <= tolerance) return name;
  }
  if (p.x > r.x && p.x < r.x + r.w && p.y > r.y && p.y < r.y + r.h) return "move";
  return null;
}

const CURSORS = { nw: "nwse-resize", se: "nwse-resize", ne: "nesw-resize", sw: "nesw-resize", move: "move" };

function resizeFromAnchor(anchor, p) {
  const minSize = 16;
  let w = Math.max(minSize, Math.abs(p.x - anchor.x));
  let h = Math.max(minSize, Math.abs(p.y - anchor.y));
  const ratio = cropRatio();
  if (ratio) {
    if (w / h > ratio) w = h * ratio;
    else h = w / ratio;
  }
  // Keep the rectangle inside the frame on the side it grows toward.
  const left = p.x < anchor.x;
  const up = p.y < anchor.y;
  const maxW = left ? anchor.x : app.frame.w - anchor.x;
  const maxH = up ? anchor.y : app.frame.h - anchor.y;
  const shrink = Math.min(1, maxW / w, maxH / h);
  w *= shrink;
  h *= shrink;
  return { x: left ? anchor.x - w : anchor.x, y: up ? anchor.y - h : anchor.y, w, h };
}

function buildCropOverlay() {
  const overlay = $("#overlay");
  overlay.addEventListener("pointerdown", (event) => {
    if (!app.cropActive || !app.frame) return;
    const p = framePoint(event);
    const r = draftRectPx();
    const hit = cropHit(p);
    const opposite = {
      nw: { x: r.x + r.w, y: r.y + r.h }, ne: { x: r.x, y: r.y + r.h },
      sw: { x: r.x + r.w, y: r.y }, se: { x: r.x, y: r.y },
    };
    cropDrag = hit === "move"
      ? { mode: "move", start: p, rect: r }
      : { mode: "resize", anchor: hit ? opposite[hit] : p };
    overlay.setPointerCapture(event.pointerId);
  });
  overlay.addEventListener("pointermove", (event) => {
    if (!app.cropActive || !app.frame) return;
    const p = framePoint(event);
    if (!cropDrag) {
      overlay.style.cursor = CURSORS[cropHit(p)] || "crosshair";
      return;
    }
    if (cropDrag.mode === "move") {
      const { rect, start } = cropDrag;
      setDraftFromPx({
        x: Math.min(app.frame.w - rect.w, Math.max(0, rect.x + p.x - start.x)),
        y: Math.min(app.frame.h - rect.h, Math.max(0, rect.y + p.y - start.y)),
        w: rect.w, h: rect.h,
      });
    } else {
      setDraftFromPx(resizeFromAnchor(cropDrag.anchor, p));
    }
    drawOverlay();
  });
  const end = () => { cropDrag = null; };
  overlay.addEventListener("pointerup", end);
  overlay.addEventListener("pointercancel", end);
}

// ---------------------------------------------------------------------------
// Move on Canvas
// ---------------------------------------------------------------------------

// A drag on screen, in preview pixels, converted to the channel's dx/dy:
// undo the mirror, then the straighten rotation (both are applied to the
// composed frame, after the channel is placed). Geometry is ignored, which
// is close enough for small corrections.
function screenDeltaToChannel(dx, dy) {
  const crop = app.doc.crop;
  if (crop.mirror_h) dx = -dx;
  if (crop.mirror_v) dy = -dy;
  const theta = (crop.rotation * Math.PI) / 180;
  const c = Math.cos(theta), s = Math.sin(theta);
  return { dx: c * dx + s * dy, dy: -s * dx + c * dy };
}

function moveActiveChannel(dx, dy) {
  const layer = app.doc.layers[app.tab];
  const delta = screenDeltaToChannel(dx, dy);
  layer.dx = Number((layer.dx + delta.dx).toFixed(1));
  layer.dy = Number((layer.dy + delta.dy).toFixed(1));
}

// Stretch pins live in the canvas's own [0, 1] space (before the mirror
// and the crop). These convert from and to a fraction of the displayed
// image. Straighten and Geometry are ignored, as on the desktop.
function displayToCanvas(fx, fy) {
  const crop = app.doc.crop;
  let u = fx, v = fy;
  if (!app.cropActive) {
    u = crop.x + fx * crop.width;
    v = crop.y + fy * crop.height;
  }
  if (crop.mirror_h) u = 1 - u;
  if (crop.mirror_v) v = 1 - v;
  return { u, v };
}

function canvasToDisplay(u, v) {
  const crop = app.doc.crop;
  if (crop.mirror_h) u = 1 - u;
  if (crop.mirror_v) v = 1 - v;
  if (!app.cropActive) {
    u = (u - crop.x) / crop.width;
    v = (v - crop.y) / crop.height;
  }
  return { fx: u, fy: v };
}

function canvasPointAt(event) {
  const bounds = $("#preview").getBoundingClientRect();
  const fx = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
  const fy = Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height));
  return displayToCanvas(fx, fy);
}

// imaging.warp_stretch_point: where a point lands once the pins pull it
// (the live grid's approximation of the image warp).
const STRETCH_FALLOFF_RADIUS = 0.35;

function warpStretchPoint(u, v, pins) {
  let du = 0, dv = 0;
  for (const [au, av, pu, pv] of pins) {
    const dist = Math.hypot(u - au, v - av);
    const t = Math.max(0, Math.min(1, 1 - (dist / STRETCH_FALLOFF_RADIUS) ** 2));
    du += t * t * pu;
    dv += t * t * pv;
  }
  return { u: u + du, v: v + dv };
}

function buildMoveOnCanvas() {
  const canvas = $("#preview");
  let drag = null;
  canvas.addEventListener("pointerdown", (event) => {
    if (app.cropActive) return;
    const layer = app.doc.layers[app.tab];
    if (app.stretch) {
      const anchor = canvasPointAt(event);
      beginEdit();
      layer.stretch_pins = [...layer.stretch_pins, [anchor.u, anchor.v, 0, 0]];
      drag = { mode: "stretch", anchor };
    } else if (app.moveOnCanvas && app.tab !== app.doc.ref) {
      beginEdit();
      drag = { mode: "move", x: event.clientX, y: event.clientY, dx: layer.dx, dy: layer.dy };
      canvas.style.cursor = "grabbing";
    } else {
      return;
    }
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const layer = app.doc.layers[app.tab];
    if (drag.mode === "stretch") {
      const p = canvasPointAt(event);
      const pins = layer.stretch_pins.slice(0, -1);
      layer.stretch_pins = [...pins, [drag.anchor.u, drag.anchor.v, p.u - drag.anchor.u, p.v - drag.anchor.v]];
      drawOverlay();
    } else {
      const scale = displayScale();
      layer.dx = drag.dx;
      layer.dy = drag.dy;
      moveActiveChannel((event.clientX - drag.x) / scale, (event.clientY - drag.y) / scale);
      sliders.filter((s) => s.group === "position").forEach((s) => s.sync());
    }
    requestRender();
  });
  const end = () => {
    if (!drag) return;
    if (drag.mode === "stretch") {
      // A plain click (no movement) leaves no pin behind.
      const layer = app.doc.layers[app.tab];
      const last = layer.stretch_pins[layer.stretch_pins.length - 1];
      if (last && Math.abs(last[2]) < 1e-4 && Math.abs(last[3]) < 1e-4) {
        layer.stretch_pins = layer.stretch_pins.slice(0, -1);
      }
    }
    drag = null;
    canvas.style.cursor = "";
    endEdit();
    syncAll();
    requestRender();
  };
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
}

// ---------------------------------------------------------------------------
// Curves: Y (master) then R, G, B, as imaging.apply_curves. The editor is a
// port of the desktop's CurveEditor: click to add a point, drag it (between
// its neighbors), double-click an inner point to remove it; the endpoints
// move on both axes (a black or white point), and double-clicking one puts
// it back in its corner.
// ---------------------------------------------------------------------------

const CURVE_COLORS = { Y: "#dcdcdc", R: CHANNELS[0].color, G: CHANNELS[1].color, B: CHANNELS[2].color };
const CURVE_MARGIN = 10;
const CURVE_HANDLE_RADIUS = 5.5;
const CURVE_HIT_RADIUS = 11;
// A fingertip covers more than a cursor tip.
const CURVE_TOUCH_HIT_RADIUS = 22;
// Two taps this close in time and space make a double tap.
const DOUBLE_TAP_MS = 350;
const DOUBLE_TAP_DIST = 24;
const CURVE_MIN_X_GAP = 0.015;

const curveUI = { channel: "Y", drag: null, histograms: null };

// imaging.evaluate_curve_lut: monotone cubic Hermite (Fritsch-Carlson),
// flat outside the endpoints. Used to draw the curve the engine applies.
function evaluateCurveLut(points, size = 128) {
  const pts = [...points].sort((a, b) => a[0] - b[0]);
  const n = pts.length;
  const out = new Float32Array(size);
  if (n < 2) {
    for (let i = 0; i < size; i++) out[i] = i / (size - 1);
    return out;
  }
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const delta = [];
  for (let k = 0; k < n - 1; k++) {
    const dx = Math.abs(xs[k + 1] - xs[k]) < 1e-9 ? 1e-9 : xs[k + 1] - xs[k];
    delta.push((ys[k + 1] - ys[k]) / dx);
  }
  const m = new Array(n);
  if (n === 2) {
    m[0] = m[1] = delta[0];
  } else {
    m[0] = delta[0];
    m[n - 1] = delta[n - 2];
    for (let k = 1; k < n - 1; k++) {
      m[k] = delta[k - 1] * delta[k] <= 0 ? 0 : (delta[k - 1] + delta[k]) / 2;
    }
  }
  for (let k = 0; k < n - 1; k++) {
    if (delta[k] === 0) { m[k] = 0; m[k + 1] = 0; }
  }
  for (let k = 0; k < n - 1; k++) {
    const d = delta[k];
    if (d === 0) continue;
    const alpha = m[k] / d, beta = m[k + 1] / d;
    const sum = alpha * alpha + beta * beta;
    if (sum > 9) {
      const tau = 3 / Math.sqrt(sum);
      m[k] = tau * alpha * d;
      m[k + 1] = tau * beta * d;
    }
  }
  for (let i = 0; i < size; i++) {
    const x = i / (size - 1);
    let y;
    if (x <= xs[0]) y = ys[0];
    else if (x >= xs[n - 1]) y = ys[n - 1];
    else {
      let k = 0;
      while (k < n - 2 && x >= xs[k + 1]) k++;
      const seg = Math.abs(xs[k + 1] - xs[k]) < 1e-9 ? 1e-9 : xs[k + 1] - xs[k];
      const t = (x - xs[k]) / seg, t2 = t * t, t3 = t2 * t;
      y = (2 * t3 - 3 * t2 + 1) * ys[k] + (t3 - 2 * t2 + t) * seg * m[k]
        + (-2 * t3 + 3 * t2) * ys[k + 1] + (t3 - t2) * seg * m[k + 1];
    }
    out[i] = Math.min(1, Math.max(0, y));
  }
  return out;
}

function isIdentityCurve(points) {
  return points.length === 2 && points[0][0] === 0 && points[0][1] === 0
    && points[1][0] === 1 && points[1][1] === 1;
}

function curvesAreIdentity() {
  return CURVE_CHANNELS.every((ch) => isIdentityCurve(app.doc.curves[ch]));
}

function curvePlot() {
  const canvas = $("#curve-editor");
  const size = canvas.clientWidth;
  return { x: CURVE_MARGIN, y: CURVE_MARGIN, w: Math.max(1, size - 2 * CURVE_MARGIN), h: Math.max(1, size - 2 * CURVE_MARGIN) };
}

function curveToCanvas(x, y) {
  const r = curvePlot();
  return [r.x + x * r.w, r.y + (1 - y) * r.h];
}

function canvasToCurve(event) {
  const bounds = $("#curve-editor").getBoundingClientRect();
  const r = curvePlot();
  const x = (event.clientX - bounds.left - r.x) / r.w;
  const y = 1 - (event.clientY - bounds.top - r.y) / r.h;
  return [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))];
}

function nearestCurvePoint(event) {
  const bounds = $("#curve-editor").getBoundingClientRect();
  const px = event.clientX - bounds.left, py = event.clientY - bounds.top;
  let best = null;
  let bestDist = event.pointerType && event.pointerType !== "mouse" ? CURVE_TOUCH_HIT_RADIUS : CURVE_HIT_RADIUS;
  app.doc.curves[curveUI.channel].forEach(([x, y], i) => {
    const [cx, cy] = curveToCanvas(x, y);
    const dist = Math.abs(cx - px) + Math.abs(cy - py);
    if (dist < bestDist) { best = i; bestDist = dist; }
  });
  return best;
}

function setCurvePoints(points) {
  // Replaced, never mutated: undo snapshots share the old arrays.
  app.doc.curves = { ...app.doc.curves, [curveUI.channel]: points };
}

function drawCurveEditor() {
  const canvas = $("#curve-editor");
  const size = canvas.clientWidth;
  if (!size) return;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(size * dpr);
  canvas.height = Math.round(size * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, size, size);
  const r = curvePlot();
  const color = CURVE_COLORS[curveUI.channel];

  ctx.fillStyle = "rgb(38, 38, 42)";
  ctx.fillRect(r.x, r.y, r.w, r.h);
  ctx.strokeStyle = "rgb(80, 80, 86)";
  ctx.lineWidth = 1;
  ctx.strokeRect(r.x + 0.5, r.y + 0.5, r.w - 1, r.h - 1);
  ctx.strokeStyle = "rgba(255, 255, 255, 0.094)";
  ctx.beginPath();
  for (const f of [0.25, 0.5, 0.75]) {
    ctx.moveTo(r.x + f * r.w, r.y); ctx.lineTo(r.x + f * r.w, r.y + r.h);
    ctx.moveTo(r.x, r.y + f * r.h); ctx.lineTo(r.x + r.w, r.y + f * r.h);
  }
  ctx.stroke();
  ctx.strokeStyle = "rgba(255, 255, 255, 0.157)";
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(...curveToCanvas(0, 0));
  ctx.lineTo(...curveToCanvas(1, 1));
  ctx.stroke();
  ctx.setLineDash([]);

  // The image before the curves, in the edited channel's color.
  const hist = curveUI.histograms && anyLoaded() ? curveUI.histograms[curveUI.channel] : null;
  if (hist) {
    const peak = Math.max(...hist) || 1;
    ctx.beginPath();
    ctx.moveTo(...curveToCanvas(0, 0));
    hist.forEach((v, i) => ctx.lineTo(...curveToCanvas(i / (hist.length - 1), Math.min(1, v / peak))));
    ctx.lineTo(...curveToCanvas(1, 0));
    ctx.closePath();
    ctx.globalAlpha = 70 / 255;
    ctx.fillStyle = color;
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  const points = app.doc.curves[curveUI.channel];
  const lut = evaluateCurveLut(points, 128);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.8;
  ctx.beginPath();
  lut.forEach((y, i) => {
    const [cx, cy] = curveToCanvas(i / (lut.length - 1), y);
    if (i === 0) ctx.moveTo(cx, cy); else ctx.lineTo(cx, cy);
  });
  ctx.stroke();

  points.forEach(([x, y], i) => {
    const [cx, cy] = curveToCanvas(x, y);
    ctx.beginPath();
    if (curveUI.drag === i) {
      ctx.arc(cx, cy, CURVE_HANDLE_RADIUS, 0, Math.PI * 2);
      ctx.fillStyle = "#e8e8e8";
      ctx.fill();
    } else {
      ctx.arc(cx, cy, CURVE_HANDLE_RADIUS - 1, 0, Math.PI * 2);
      ctx.fillStyle = "rgb(38, 38, 42)";
      ctx.fill();
      ctx.strokeStyle = "#e8e8e8";
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  });
}

function buildCurves() {
  const canvas = $("#curve-editor");
  const row = $("#curve-channels");
  for (const ch of CURVE_CHANNELS) {
    const button = document.createElement("button");
    button.className = "layer-toggle";
    button.dataset.channel = ch;
    button.style.color = CURVE_COLORS[ch];
    button.title = ch === "Y" ? "Master curve" : `${CHANNELS.find((c) => c.key === ch).name} curve`;
    button.innerHTML = '<span class="icon"></span>';
    button.addEventListener("click", () => {
      curveUI.channel = ch;
      syncCurveControls();
      drawCurveEditor();
    });
    row.append(button);
  }

  // Double-click (or double tap) on a point: an interior point is removed, an
  // endpoint goes back to its corner, (0, 0) or (1, 1), which always keeps the
  // points in order.
  const removeCurvePoint = (index) => {
    const points = app.doc.curves[curveUI.channel];
    const last = points.length - 1;
    if (index > 0 && index < last) {
      edit(() => setCurvePoints(points.filter((_, k) => k !== index)));
      return;
    }
    const corner = index === 0 ? [0, 0] : [1, 1];
    if (points[index][0] === corner[0] && points[index][1] === corner[1]) return;
    edit(() => setCurvePoints(points.map((p, k) => (k === index ? corner : p))));
  };
  // touch-action: none (needed to drag points) stops the browser from making
  // a dblclick out of two taps, so touch detects its own double tap.
  let lastTap = null;
  let lastPointerType = "mouse";

  canvas.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    lastPointerType = event.pointerType;
    let index = nearestCurvePoint(event);
    if (event.pointerType !== "mouse") {
      const now = event.timeStamp;
      const isDouble = lastTap && now - lastTap.time < DOUBLE_TAP_MS
        && Math.hypot(event.clientX - lastTap.x, event.clientY - lastTap.y) < DOUBLE_TAP_DIST;
      lastTap = isDouble ? null : { time: now, x: event.clientX, y: event.clientY };
      if (isDouble && index !== null) {
        removeCurvePoint(index);
        return;
      }
    }
    beginEdit();
    if (index === null) {
      const points = app.doc.curves[curveUI.channel];
      let [x, y] = canvasToCurve(event);
      for (const [px] of points) {
        if (px - CURVE_MIN_X_GAP < x && x < px + CURVE_MIN_X_GAP) {
          x = x >= px ? px + CURVE_MIN_X_GAP : px - CURVE_MIN_X_GAP;
        }
      }
      x = Math.min(1 - CURVE_MIN_X_GAP, Math.max(CURVE_MIN_X_GAP, x));
      const next = [...points, [x, y]].sort((a, b) => a[0] - b[0]);
      index = next.findIndex((p) => p[0] === x && p[1] === y);
      setCurvePoints(next);
      requestRender();
    }
    curveUI.drag = index;
    canvas.classList.add("dragging");
    canvas.setPointerCapture(event.pointerId);
    drawCurveEditor();
  });
  canvas.addEventListener("pointermove", (event) => {
    if (curveUI.drag === null) {
      canvas.classList.toggle("over-point", nearestCurvePoint(event) !== null);
      return;
    }
    const points = app.doc.curves[curveUI.channel];
    const i = curveUI.drag;
    let [x, y] = canvasToCurve(event);
    const lo = i > 0 ? points[i - 1][0] + CURVE_MIN_X_GAP : 0;
    const hi = i < points.length - 1 ? points[i + 1][0] - CURVE_MIN_X_GAP : 1;
    x = lo <= hi ? Math.min(hi, Math.max(lo, x)) : points[i][0];
    setCurvePoints(points.map((p, k) => (k === i ? [x, y] : p)));
    drawCurveEditor();
    requestRender();
  });
  const end = () => {
    if (curveUI.drag === null) return;
    curveUI.drag = null;
    canvas.classList.remove("dragging");
    endEdit();
    syncAll();
  };
  canvas.addEventListener("pointerleave", () => canvas.classList.remove("over-point"));
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
  canvas.addEventListener("dblclick", (event) => {
    // Touch handles its own double tap in pointerdown.
    if (lastPointerType !== "mouse") return;
    const index = nearestCurvePoint(event);
    if (index !== null) removeCurvePoint(index);
  });

  $("#negative").addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!anyLoaded()) return;
    edit(() => { app.doc.negative = !app.doc.negative; });
  });
  $("#reset-curves").addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    edit(() => { app.doc.curves = newCurves(); });
  });
  window.addEventListener("resize", drawCurveEditor);
}

function syncCurveControls() {
  document.querySelectorAll("#curve-channels .layer-toggle").forEach((button) => {
    const ch = button.dataset.channel;
    const active = ch === curveUI.channel;
    button.classList.toggle("on", active);
    button.querySelector(".icon").style.setProperty("--icon",
      `url(../resources/icons/Global/${active ? "circle-letter" : "circle-dotted-letter"}-${ch.toLowerCase()}.svg)`);
  });
  $("#negative").classList.toggle("on", !!app.doc.negative);
  $("#negative").disabled = !anyLoaded();
  $("#reset-curves").disabled = curvesAreIdentity();
}

// ---------------------------------------------------------------------------
// Histogram
// ---------------------------------------------------------------------------

let lastHistogram = null;

function drawHistogram(hist) {
  lastHistogram = hist;
  const canvas = $("#histogram");
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = 110;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#1c1c1c";
  ctx.fillRect(0, 0, width, height);
  if (!hist) return;

  // Linear scale; the two end bins are left out of the peak so clipping
  // doesn't flatten everything else.
  let peak = 1;
  for (const key of ["Y", "R", "G", "B"]) {
    for (let i = 1; i < 255; i++) peak = Math.max(peak, hist[key][i]);
  }
  const series = [
    ["R", "rgba(224, 86, 79, 0.9)"], ["G", "rgba(92, 191, 106, 0.9)"],
    ["B", "rgba(91, 143, 224, 0.9)"], ["Y", "rgba(240, 240, 240, 0.85)"],
  ];
  for (const [key, color] of series) {
    ctx.beginPath();
    ctx.moveTo(0, height);
    for (let i = 0; i < 256; i++) {
      const x = (i / 255) * width;
      const y = height - Math.min(1, hist[key][i] / peak) * (height - 6);
      ctx.lineTo(x, y);
    }
    ctx.lineTo(width, height);
    if (key !== "Y") {
      ctx.globalCompositeOperation = "lighter";
      ctx.fillStyle = color.replace(/[\d.]+\)$/, "0.16)");
      ctx.fill();
      ctx.globalCompositeOperation = "source-over";
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.stroke();
  }
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

const EXPORT_FORMATS = {
  png: { ext: ".png", type: "image/png" },
  jpeg: { ext: ".jpg", type: "image/jpeg" },
  tiff16: { ext: ".tif", type: "image/tiff" },
};

function buildExport() {
  const dialog = $("#export-dialog");
  const format = $("#export-format");
  const syncExt = () => { $("#export-ext").textContent = EXPORT_FORMATS[format.value].ext; };
  format.addEventListener("change", syncExt);
  $("#export-button").addEventListener("click", () => {
    if (app.cropActive) commitCrop();
    const source = app.files[app.doc.ref] || app.files.find(Boolean);
    $("#export-name").value = `${source.name.replace(/\.[^.]+$/, "")}_trichrome`;
    syncExt();
    syncDropdowns();
    dialog.showModal();
  });
  dialog.addEventListener("close", () => {
    syncPhoneCrop(); // opening the dialog committed the crop
    if (dialog.returnValue === "export") exportImage(format.value, $("#export-name").value.trim() || "trichrome");
  });
}

async function exportImage(format, name) {
  const button = $("#export-button");
  button.disabled = true;
  setActivity("export", "Exporting at full resolution…", true);
  try {
    const result = await callWorker("export", { state: engineState(false, true), format });
    const { ext, type } = EXPORT_FORMATS[format];
    const url = URL.createObjectURL(new Blob([result.data], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = name + ext;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    flashMessage(`Exported ${name}${ext} (${result.width}×${result.height}).`);
  } catch (err) {
    flashMessage(`Export failed: ${err.message}`);
  } finally {
    setActivity("export", null);
    syncAll();
  }
}

// ---------------------------------------------------------------------------
// "Download the full app" window
// ---------------------------------------------------------------------------

const RELEASES_API = "https://api.github.com/repos/Arkazox/TRICHR-O-MATIC/releases/latest";
let latestRelease = null; // fetched once per page load

function visitorPlatform() {
  const ua = navigator.userAgent;
  if (/Windows/.test(ua)) return "windows";
  if (/Macintosh|Mac OS X/.test(ua)) return "mac";
  return null;
}

// Whether this Mac is Apple Silicon: only Chromium browsers can tell
// (User-Agent Client Hints); Safari and Firefox report every Mac as Intel.
// null when unknown.
async function macIsAppleSilicon() {
  try {
    const hints = await navigator.userAgentData?.getHighEntropyValues(["architecture"]);
    if (hints?.architecture) return hints.architecture === "arm";
  } catch (_) {
    // Not available: unknown.
  }
  return null;
}

function formatSize(bytes) {
  return `${Math.round(bytes / 1e6)} MB`;
}

async function loadLatestRelease() {
  if (latestRelease) return latestRelease;
  const response = await fetch(RELEASES_API, { headers: { Accept: "application/vnd.github+json" } });
  if (!response.ok) throw new Error(`GitHub answered ${response.status}`);
  latestRelease = await response.json();
  return latestRelease;
}

const RELEASES_PAGE = "https://github.com/Arkazox/TRICHR-O-MATIC/releases/latest";
let selectedAsset = null;

// The Download button gets the chosen system's file once the latest
// release is known; until then (or offline) the release page, in a new tab.
function syncGetAppDownload() {
  const dialog = $("#get-app-dialog");
  const option = dialog.querySelector(`.get-app-option[data-asset="${selectedAsset}"]`);
  dialog.querySelectorAll(".get-app-option").forEach((o) => {
    o.classList.toggle("selected", o === option);
    o.setAttribute("aria-checked", o === option);
  });
  const button = $("#get-app-download");
  button.classList.toggle("disabled", !option);
  $("#get-app-download-label").textContent = option ? `Download for ${option.dataset.label}` : "Choose your system";
  const asset = option && latestRelease?.assets.find((a) => a.name.endsWith(selectedAsset));
  if (asset) {
    button.href = asset.browser_download_url;
    button.removeAttribute("target");
  } else {
    button.href = RELEASES_PAGE;
    button.target = "_blank";
    button.rel = "noopener";
  }
}

// A page can't follow a download's progress (the browser owns it), so
// this only says which file is on its way and where it lands. The button
// reads "Downloading…" for a few seconds, which also stops a double click
// from starting a second copy.
let getAppBusyTimer = null;

function showGetAppProgress() {
  const button = $("#get-app-download");
  const status = $("#get-app-status");
  const asset = latestRelease?.assets.find((a) => a.name.endsWith(selectedAsset));
  const check = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  check.setAttribute("class", "get-app-status-check");
  check.setAttribute("viewBox", "0 0 24 24");
  check.setAttribute("aria-hidden", "true");
  check.innerHTML = '<circle cx="12" cy="12" r="11" fill="currentColor" opacity=".18"/>'
    + '<circle cx="12" cy="12" r="10.25" fill="none" stroke="currentColor" stroke-width="1.5"/>'
    + '<path d="M7 12.4l3.2 3.2L17 8.8" fill="none" stroke="currentColor" stroke-width="2"'
    + ' stroke-linecap="round" stroke-linejoin="round"/>';
  const text = document.createElement("div");
  const title = document.createElement("span");
  title.className = "get-app-status-title";
  if (asset) {
    title.textContent = "Download started";
    const file = document.createElement("span");
    file.className = "file";
    file.textContent = asset.name;
    text.append(title, file, ` (${formatSize(asset.size)}). You'll find it in your browser's downloads.`);
  } else {
    title.textContent = "Opening the download page";
    text.append(title, "The files are on the GitHub release page, in a new tab.");
  }
  status.replaceChildren(check, text);
  status.hidden = false;
  if (!asset) return;
  clearTimeout(getAppBusyTimer);
  button.classList.add("busy");
  $("#get-app-download-label").textContent = "Downloading…";
  getAppBusyTimer = setTimeout(() => {
    button.classList.remove("busy");
    syncGetAppDownload();
  }, 4000);
}

function hideGetAppProgress() {
  clearTimeout(getAppBusyTimer);
  $("#get-app-download").classList.remove("busy");
  $("#get-app-status").hidden = true;
  for (const note of $("#get-app-dialog").querySelectorAll(".get-app-note")) note.hidden = true;
}

async function openGetAppDialog() {
  const dialog = $("#get-app-dialog");
  const platform = visitorPlatform();
  // On a Mac whose chip can't be known, Apple Silicon: every Mac sold
  // since late 2020. Another system: nothing preselected.
  const intelMac = platform === "mac" && (await macIsAppleSilicon()) === false;
  selectedAsset = platform === "windows" ? "Windows-Setup.exe"
    : platform === "mac" ? (intelMac ? "Intel.zip" : "AppleSilicon.zip") : null;
  hideGetAppProgress();
  syncGetAppDownload();
  dialog.showModal();
  try {
    const release = await loadLatestRelease();
    $("#get-app-version").textContent = `Version ${release.tag_name.replace(/^v/, "")}`;
    dialog.querySelectorAll(".get-app-option").forEach((option) => {
      const asset = release.assets.find((a) => a.name.endsWith(option.dataset.asset));
      if (asset) option.querySelector(".get-app-size").textContent = formatSize(asset.size);
    });
    syncGetAppDownload();
  } catch (_) {
    // Offline or rate-limited: Download opens the release page.
  }
}

function buildGetApp() {
  $("#get-app-button").addEventListener("click", openGetAppDialog);
  $("#get-app-dialog").querySelectorAll(".get-app-option").forEach((option) => {
    option.addEventListener("click", () => {
      selectedAsset = option.dataset.asset;
      hideGetAppProgress();
      syncGetAppDownload();
    });
  });
  // Once a download starts, how to get past the first-launch warning.
  $("#get-app-download").addEventListener("click", () => {
    if (!selectedAsset) return;
    showGetAppProgress();
    const windows = selectedAsset.startsWith("Windows");
    $("#get-app-note-mac").hidden = windows;
    $("#get-app-note-windows").hidden = !windows;
  });
  $("#get-app-copy").addEventListener("click", async () => {
    const button = $("#get-app-copy");
    try {
      await navigator.clipboard.writeText($("#get-app-xattr").textContent);
      button.textContent = "Copied";
    } catch (_) {
      // Clipboard refused: select the text so ⌘C works.
      getSelection().selectAllChildren($("#get-app-xattr"));
    }
    setTimeout(() => { button.textContent = "Copy"; }, 1500);
  });
  closeOnBackdropClick($("#get-app-dialog"));
}

// A click or tap on the backdrop (outside the card, not in its padding)
// closes it. Pointer events rather than click: iOS Safari doesn't always
// send a click for a tap on a dialog's backdrop. Both ends must be outside,
// so a drag that starts in the card (selecting text) doesn't close it.
function closeOnBackdropClick(dialog) {
  const outside = (event) => {
    if (event.target !== dialog) return false;
    const r = dialog.getBoundingClientRect();
    return event.clientX < r.left || event.clientX > r.right
      || event.clientY < r.top || event.clientY > r.bottom;
  };
  let pressedOutside = false;
  dialog.addEventListener("pointerdown", (event) => { pressedOutside = outside(event); });
  dialog.addEventListener("pointerup", (event) => {
    if (pressedOutside && outside(event)) dialog.close();
    pressedOutside = false;
  });
}

// ---------------------------------------------------------------------------
// Quick Tour
// ---------------------------------------------------------------------------

// Seen once in this browser: the tour then waits for the "?" button. Storage
// can be blocked (private windows, strict settings): the tour then stays
// closed rather than opening on every visit.
const TOUR_SEEN_KEY = "trichromatic-web-tour-seen";
let tourStep = 0;

function tourSeen() {
  try { return localStorage.getItem(TOUR_SEEN_KEY) === "1"; } catch (_) { return true; }
}

function showTourStep(index) {
  const steps = $("#tour-dialog").querySelectorAll(".tour-step");
  tourStep = Math.max(0, Math.min(steps.length - 1, index));
  steps.forEach((step, i) => step.classList.toggle("current", i === tourStep));
  $("#tour-dots").querySelectorAll("span").forEach((dot, i) => dot.classList.toggle("current", i === tourStep));
  const last = tourStep === steps.length - 1;
  $("#tour-back").hidden = tourStep === 0;
  $("#tour-next").textContent = last ? "Get started" : "Next";
}

function openTour() {
  showTourStep(0);
  $("#tour-dialog").showModal();
  $("#tour-next").focus();
}

function buildTour() {
  const dialog = $("#tour-dialog");
  const count = dialog.querySelectorAll(".tour-step").length;
  $("#tour-dots").replaceChildren(...Array.from({ length: count }, () => document.createElement("span")));
  $("#tour-button").addEventListener("click", openTour);
  $("#tour-back").addEventListener("click", () => showTourStep(tourStep - 1));
  $("#tour-next").addEventListener("click", () => {
    if (tourStep === count - 1) dialog.close();
    else showTourStep(tourStep + 1);
  });
  $("#tour-get-app").addEventListener("click", () => {
    dialog.close();
    openGetAppDialog();
  });
  dialog.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight") showTourStep(tourStep + 1);
    else if (event.key === "ArrowLeft") showTourStep(tourStep - 1);
  });
  // However it closes (Get started, Esc, the backdrop), it counts as seen.
  dialog.addEventListener("close", () => {
    try { localStorage.setItem(TOUR_SEEN_KEY, "1"); } catch (_) {}
  });
  closeOnBackdropClick(dialog);
  if (!tourSeen()) openTour();
}

// ---------------------------------------------------------------------------
// Keyboard and window-level drops
// ---------------------------------------------------------------------------

function isTyping(target) {
  return target.matches("input[type=text], input[type=number], select, textarea, .dropdown-button");
}

function buildKeyboard() {
  document.addEventListener("keydown", (event) => {
    if (document.querySelector("dialog[open]")) return;
    const mod = event.metaKey || event.ctrlKey;
    const key = event.key.toLowerCase();
    if (mod && key === "z") {
      event.preventDefault();
      if (event.shiftKey) restoreFrom(app.redo, app.undo);
      else restoreFrom(app.undo, app.redo);
      return;
    }
    if (mod && key === "y") {
      event.preventDefault();
      restoreFrom(app.redo, app.undo);
      return;
    }
    if (mod && (event.key === "+" || event.key === "=" || event.key === "-" || event.key === "0")) {
      event.preventDefault();
      if (!app.image) return;
      if (event.key === "0") setZoom(null);
      else zoomAtCenter(displayScale() * (event.key === "-" ? 1 / 1.25 : 1.25));
      return;
    }
    if (mod && key === "f") {
      event.preventDefault();
      toggleFullscreen();
      return;
    }
    if (isTyping(event.target) || mod) return;
    if (event.key === ":") {
      setCompare(!app.compare);
    } else if (key === "f" && !event.altKey) {
      setZoom(null);
    } else if (key === "z" && !event.altKey) {
      if (app.image) zoomAtCenter(1);
    } else if (key === "c") {
      if (app.cropActive) commitCrop();
      else enterCrop();
    } else if (event.key === "Enter" && app.cropActive) {
      event.preventDefault();
      commitCrop();
    } else if (event.key === "Enter" && app.stretch && !event.target.matches("button, input")) {
      app.stretch = false;
      syncAll();
    } else if (event.key === "Escape") {
      if (app.cropActive) exitCrop();
      else if (app.stretch) { app.stretch = false; syncAll(); }
      else if (app.moveOnCanvas) { app.moveOnCanvas = false; syncAll(); }
      else if (document.body.classList.contains("focus")) toggleFullscreen();
    } else if (event.key.startsWith("Arrow") && app.moveOnCanvas
               && !event.target.matches("input[type=range]")) {
      event.preventDefault();
      const step = event.shiftKey ? 5 : 0.5;
      const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[event.key];
      edit(() => moveActiveChannel(d[0], d[1]));
    }
  });
}

// ---------------------------------------------------------------------------
// Phones: one tool at a time behind icon tabs, and an import button in the
// preview, since a phone can't drag and drop. The CSS shows them only on a
// narrow screen; on a wide one every block shows, as before.
// ---------------------------------------------------------------------------

const PHONE_QUERY = matchMedia("(max-width: 760px)");
// Hidden by default; the preview bar's histogram button shows it under the
// tabs, whichever tool is shown (remembered per browser).
const HISTOGRAM_KEY = "phone-histogram-shown";
let phoneHistogram = false;

function showTool(tool) {
  const panel = $("#panel");
  panel.dataset.tool = tool;
  document.querySelectorAll(".tool-tab").forEach((tab) => {
    const active = tab.dataset.tool === tool;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active);
  });
  const shown = [...panel.querySelectorAll(":scope > .block")].filter((block) =>
    block.dataset.tool === tool
    || (block.dataset.tool === "histogram" && phoneHistogram));
  $("#histogram-toggle").classList.toggle("on", phoneHistogram);
  $("#histogram-toggle").title = phoneHistogram ? "Hide the histogram" : "Show the histogram";
  panel.querySelectorAll(":scope > .block").forEach((block) => {
    block.classList.toggle("tool-current", shown.includes(block));
    block.classList.toggle("tool-first", block === shown[0]);
    block.classList.toggle("tool-last", block === shown[shown.length - 1]);
  });
  if (PHONE_QUERY.matches) shown.forEach((block) => { block.open = true; });
  syncPhoneCrop();
  // Canvases measure their width when drawn: 0 while their block was hidden.
  drawHistogram(lastHistogram);
  drawCurveEditor();
}

// On a phone the Crop tab is crop mode: showing it starts cropping, leaving
// it keeps the frame (as the desktop's crop button does).
function syncPhoneCrop() {
  if (!PHONE_QUERY.matches) return;
  const cropTab = $("#panel").dataset.tool === "crop";
  if (cropTab && !app.cropActive) enterCrop();
  else if (!cropTab && app.cropActive) commitCrop();
}

function buildPhoneLayout() {
  document.querySelectorAll(".tool-tab").forEach((tab) => {
    tab.addEventListener("click", () => showTool(tab.dataset.tool));
  });
  // A block can't be collapsed on a phone: its tab shows or hides it.
  document.querySelectorAll("#panel > .block > .block-title").forEach((title) => {
    title.addEventListener("click", (event) => {
      if (PHONE_QUERY.matches && !event.target.closest("button")) event.preventDefault();
    });
  });
  try { phoneHistogram = localStorage.getItem(HISTOGRAM_KEY) === "1"; } catch (_) { /* private mode */ }
  $("#histogram-toggle").addEventListener("click", () => {
    phoneHistogram = !phoneHistogram;
    try { localStorage.setItem(HISTOGRAM_KEY, phoneHistogram ? "1" : "0"); } catch (_) { /* private mode */ }
    showTool($("#panel").dataset.tool);
  });
  PHONE_QUERY.addEventListener("change", () => showTool($("#panel").dataset.tool));
  showTool($("#panel").dataset.tool);

  const input = $("#import-input");
  $("#import-button").addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    const files = [...input.files];
    input.value = "";
    if (files.length) loadDroppedFiles(files);
  });
}

function buildWindowDrop() {
  const viewport = $("#viewport");
  // Without this, a file dropped anywhere else would replace the page.
  window.addEventListener("dragover", (event) => event.preventDefault());
  window.addEventListener("drop", (event) => event.preventDefault());
  viewport.addEventListener("dragover", (event) => {
    event.preventDefault();
    viewport.classList.add("drag-over");
  });
  viewport.addEventListener("dragleave", (event) => {
    if (!viewport.contains(event.relatedTarget)) viewport.classList.remove("drag-over");
  });
  viewport.addEventListener("drop", (event) => {
    event.preventDefault();
    viewport.classList.remove("drag-over");
    if (event.dataTransfer.files.length) loadDroppedFiles(event.dataTransfer.files);
  });
}

// ---------------------------------------------------------------------------
// Dropdowns: a styled button and menu in front of each native <select>,
// which stays (hidden) as the value holder, so code reading select.value
// or listening to its "change" event is unchanged.
// ---------------------------------------------------------------------------

const dropdowns = [];
let openDropdown = null;

function enhanceSelect(select) {
  const wrap = document.createElement("div");
  wrap.className = "dropdown";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "dropdown-button";
  button.setAttribute("aria-haspopup", "listbox");
  if (select.getAttribute("aria-label")) button.setAttribute("aria-label", select.getAttribute("aria-label"));
  button.innerHTML = '<span class="dropdown-label"></span><span class="dropdown-arrow"><span class="icon"></span></span>';
  const menu = document.createElement("div");
  menu.className = "dropdown-menu";
  menu.setAttribute("role", "listbox");
  menu.hidden = true;
  wrap.append(button, menu);
  select.after(wrap);
  select.hidden = true;
  select.tabIndex = -1;

  let active = -1;
  const options = () => [...select.options];

  function refresh() {
    const option = select.options[select.selectedIndex];
    button.querySelector(".dropdown-label").textContent = option ? option.textContent : "";
    button.disabled = select.disabled;
  }

  function highlight(index) {
    active = index;
    menu.querySelectorAll(".dropdown-item").forEach((item, i) => item.classList.toggle("active", i === index));
    menu.children[index]?.scrollIntoView({ block: "nearest" });
  }

  function open() {
    if (select.disabled) return;
    closeOpenDropdown();
    menu.innerHTML = "";
    options().forEach((option, index) => {
      const item = document.createElement("div");
      item.className = "dropdown-item";
      item.setAttribute("role", "option");
      item.classList.toggle("selected", index === select.selectedIndex);
      item.setAttribute("aria-selected", index === select.selectedIndex);
      item.textContent = option.textContent;
      item.addEventListener("mousemove", () => { if (active !== index) highlight(index); });
      item.addEventListener("mousedown", (event) => event.preventDefault()); // keep focus on the button
      item.addEventListener("click", () => choose(index));
      menu.append(item);
    });
    menu.hidden = false;
    // Fixed, so the side panel's scrolling can't clip it; opens upward
    // when there isn't room below.
    const bounds = button.getBoundingClientRect();
    menu.style.minWidth = `${bounds.width}px`;
    menu.style.left = `${bounds.left}px`;
    const height = menu.offsetHeight;
    const below = window.innerHeight - bounds.bottom - 8;
    menu.style.top = height > below && bounds.top > below
      ? `${Math.max(8, bounds.top - height - 4)}px`
      : `${bounds.bottom + 4}px`;
    wrap.classList.add("open");
    button.setAttribute("aria-expanded", "true");
    highlight(Math.max(0, select.selectedIndex));
    openDropdown = close;
  }

  function close() {
    menu.hidden = true;
    wrap.classList.remove("open");
    button.setAttribute("aria-expanded", "false");
    if (openDropdown === close) openDropdown = null;
  }

  function choose(index) {
    close();
    if (index !== select.selectedIndex) {
      select.selectedIndex = index;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    refresh();
    button.focus();
  }

  button.addEventListener("click", () => (menu.hidden ? open() : close()));
  button.addEventListener("keydown", (event) => {
    const count = select.options.length;
    if (menu.hidden) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
        event.preventDefault();
        event.stopPropagation();
        open();
      }
      return;
    }
    event.stopPropagation();
    if (event.key === "ArrowDown") { event.preventDefault(); highlight(Math.min(count - 1, active + 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); highlight(Math.max(0, active - 1)); }
    else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(active); }
    else if (event.key === "Escape" || event.key === "Tab") { if (event.key === "Escape") event.preventDefault(); close(); }
    else if (event.key.length === 1) {
      // Type-ahead: the next item starting with that letter.
      const letter = event.key.toLowerCase();
      const items = options();
      for (let step = 1; step <= count; step++) {
        const i = (active + step) % count;
        if (items[i].textContent.trim().toLowerCase().startsWith(letter)) { highlight(i); break; }
      }
    }
  });

  dropdowns.push(refresh);
  refresh();
}

function closeOpenDropdown() {
  if (openDropdown) openDropdown();
}

function buildDropdowns() {
  document.querySelectorAll("select").forEach(enhanceSelect);
  document.addEventListener("mousedown", (event) => {
    if (openDropdown && !event.target.closest(".dropdown")) closeOpenDropdown();
  });
  // A fixed menu would float away from its button: close it instead.
  document.addEventListener("scroll", (event) => {
    if (openDropdown && !event.target.closest?.(".dropdown-menu")) closeOpenDropdown();
  }, true);
  window.addEventListener("resize", closeOpenDropdown);
}

function syncDropdowns() {
  for (const refresh of dropdowns) refresh();
}

// ---------------------------------------------------------------------------
// Sync every control from the state
// ---------------------------------------------------------------------------

function syncAll() {
  const isRef = app.tab === app.doc.ref;
  const loaded = anyLoaded();
  const allLoaded = app.files.every(Boolean);
  if (isRef && app.moveOnCanvas) app.moveOnCanvas = false;

  for (const slider of sliders) {
    slider.sync();
    slider.setDisabled((slider.group === "position" && isRef) || (slider.group === "light" && app.compare));
  }
  document.querySelectorAll("#show-layer .layer-toggle").forEach((toggle, index) => {
    const on = app.visible[index];
    const letter = CHANNELS[index].key.toLowerCase();
    toggle.classList.toggle("on", on);
    toggle.querySelector(".icon").style.setProperty("--icon",
      `url(../resources/icons/Global/${on ? "circle-letter" : "circle-dotted-letter"}-${letter}.svg)`);
  });
  document.querySelectorAll("#channel-tabs .tab").forEach((tab, index) => tab.classList.toggle("active", index === app.tab));
  const tabBody = $("#tab-body");
  tabBody.dataset.active = app.tab;
  tabBody.style.setProperty("--channel", CHANNELS[app.tab].color);
  if (app.solo !== null && !app.files[app.solo]) app.solo = null;
  const solo = $("#solo");
  solo.checked = app.solo === app.tab;
  solo.disabled = !app.files[app.tab];
  document.querySelectorAll("#reference-buttons .lock-toggle").forEach((button, index) => {
    const locked = index === app.doc.ref;
    button.classList.toggle("on", locked);
    button.setAttribute("aria-checked", locked);
  });
  $("#reference-note").hidden = !isRef;
  $("#mode").value = app.colorTrichrome ? "color" : "classic";

  const move = $("#move-on-canvas");
  move.checked = app.moveOnCanvas;
  move.disabled = isRef;
  if (!loaded) app.stretch = false;
  const stretch = $("#stretch-on-canvas");
  stretch.checked = app.stretch;
  stretch.disabled = !loaded;
  $("#reset-stretch").disabled = !app.doc.layers[app.tab].stretch_pins.length;
  $("#auto-align").disabled = !(allLoaded && app.engineReady);
  $("#export-button").disabled = !(loaded && app.engineReady) || activities.has("export");

  const crop = app.doc.crop;
  $("#compare").classList.toggle("on", app.compare);
  for (const id of ["#rotate-left", "#rotate-right", "#crop-rotate-left", "#crop-rotate-right", "#compare"]) {
    $(id).disabled = !loaded;
  }
  $("#crop-toggle").classList.toggle("on", app.cropActive);
  $("#crop-toggle").disabled = !loaded;
  $("#mirror-h").classList.toggle("on", crop.mirror_h);
  $("#mirror-v").classList.toggle("on", crop.mirror_v);
  $("#ratio").value = crop.ratio;
  $("#orientation").disabled = crop.ratio === "free" || crop.ratio === "original" || crop.ratio === "1:1";
  $("#orientation").classList.toggle("on", crop.portrait && !$("#orientation").disabled);
  $("#custom-ratio-row").hidden = crop.ratio !== "custom";
  $("#custom-w").value = crop.custom_w ?? 1;
  $("#custom-h").value = crop.custom_h ?? 1;

  const stage = $("#stage");
  stage.classList.toggle("crop-active", app.cropActive);
  stage.classList.toggle("move-active", app.moveOnCanvas);
  stage.classList.toggle("stretch-active", app.stretch);
  $("#indicator").textContent = [
    app.compare ? "Displaying original" : "",
    app.cropActive
      ? "Crop: drag the frame or its corners · Enter to apply · Esc to cancel"
      : app.stretch
        ? `Drag on the canvas to stretch the ${CHANNELS[app.tab].name.toLowerCase()} layer, starting from where you click`
        : app.moveOnCanvas
          ? `Drag the ${CHANNELS[app.tab].name.toLowerCase()} layer on the canvas to reposition it`
          : "",
  ].filter(Boolean).join(" · ");

  syncFileRows();
  syncResetButtons();
  syncDropdowns();
  syncCurveControls();
  drawCurveEditor();
  drawOverlay();
}

// ---------------------------------------------------------------------------

function init() {
  buildSliders();
  buildFileRows();
  buildChannelControls();
  buildResetButtons();
  buildFramingControls();
  buildCurves();
  buildZoomControls();
  buildPinchZoom();
  buildViewControls();
  buildCropOverlay();
  buildMoveOnCanvas();
  buildExport();
  buildGetApp();
  buildDropdowns();
  buildKeyboard();
  buildWindowDrop();
  buildPhoneLayout();
  $("#mode").addEventListener("change", (event) => changeMode(event.target.value === "color"));
  $("#reset-all").addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    startOver();
  });
  syncAll();
  drawHistogram(null);
  buildTour();
}

init();
