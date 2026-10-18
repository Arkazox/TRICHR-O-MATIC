// Service worker: makes the page installable (Add to Home Screen), start
// fast and work offline once it has been opened online.
//
// - The page's own files (web/, the trichrome/ modules, resources/) are
//   network first: online, a new release shows up right away; the stored
//   copy is only the offline fallback.
// - Pyodide and its packages (numpy, OpenCV, Pillow, about 20 MB) come from
//   the CDN under a versioned URL that never changes content: cache first,
//   so they load from the device after the first visit.
// - Everything else (the GitHub API for the download links) isn't touched.
//
// The first visit loads before this worker controls the page, so app.js
// sends it every URL that visit used (its own and the engine worker's) to
// store them too: offline works from the second launch on.

const APP_CACHE = "app";
const CDN_ORIGIN = "https://cdn.jsdelivr.net";
// One cache per Pyodide version ("cdn-v314.0.5"); older ones are dropped
// once a new version is stored.
const cdnCacheName = (url) => `cdn-${new URL(url).pathname.split("/")[2] || "x"}`;
// The two folders next to web/ that the page reads.
const ROOT = new URL("../", self.location.href).href;
const SHELL = ["./", "index.html", "style.css", "app.js", "worker.js", "engine.py",
  "manifest.webmanifest", "../trichrome/imaging.py", "../trichrome/alignment.py"];

function isAppFile(url) {
  return url.startsWith(new URL("./", self.location.href).href)
    || url.startsWith(ROOT + "trichrome/") || url.startsWith(ROOT + "resources/");
}

function isCdnFile(url) {
  return url.startsWith(CDN_ORIGIN + "/pyodide/");
}

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(APP_CACHE)
    .then((cache) => cache.addAll(SHELL))
    .catch(() => {}) // offline install: the next visit fills it
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

async function storeCdn(url, response) {
  const name = cdnCacheName(url);
  const cache = await caches.open(name);
  await cache.put(url, response);
  for (const key of await caches.keys()) {
    if (key.startsWith("cdn-") && key !== name) await caches.delete(key);
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const copy = response.clone();
      caches.open(APP_CACHE).then((cache) => cache.put(request.url, copy));
    }
    return response;
  } catch (err) {
    const cached = await caches.match(request.url, { ignoreSearch: true });
    if (cached) return cached;
    throw err;
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request.url);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) storeCdn(request.url, response.clone());
  return response;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET" || request.headers.has("range")) return;
  if (isCdnFile(request.url)) event.respondWith(cacheFirst(request));
  else if (isAppFile(request.url)) event.respondWith(networkFirst(request));
});

// From app.js: the URLs the first visit loaded before this worker took over.
self.addEventListener("message", (event) => {
  const urls = event.data && event.data.type === "store" ? event.data.urls : null;
  if (!urls) return;
  event.waitUntil((async () => {
    for (const url of urls) {
      try {
        if (isCdnFile(url)) {
          if (await caches.match(url)) continue;
          const response = await fetch(url, { mode: "cors" });
          if (response.ok) await storeCdn(url, response);
        } else if (isAppFile(url)) {
          if (await caches.match(url, { ignoreSearch: true })) continue;
          const response = await fetch(url);
          if (response.ok) await (await caches.open(APP_CACHE)).put(url, response);
        }
      } catch (_) {
        // Offline or refused: stored on a later visit instead.
      }
    }
  })());
});
