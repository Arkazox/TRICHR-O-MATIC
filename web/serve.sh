#!/bin/sh
# Serves the repository root locally, so the page can read the desktop app's
# trichrome/ modules and icons, and opens http://localhost:8000/web/ in the
# default browser (a page opened as a file:// URL can't start its worker).
# Usage: ./web/serve.sh [port]. Ctrl+C stops the server.
cd "$(dirname "$0")/.." || exit 1
PORT="${1:-8000}"
URL="http://localhost:$PORT/web/"

open_page() {
  if command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
  else echo "Open $URL in your browser."
  fi
}

# Already running (from another terminal): just open the page.
if curl -s -o /dev/null "$URL"; then
  echo "Trichr-o-matic Web is already served at $URL"
  open_page
  exit 0
fi

# Like `python3 -m http.server`, but tells the browser not to cache: a
# reload must always pick up edited files, the worker's engine.py included.
python3 - "$PORT" >/dev/null 2>&1 <<'PY' &
import http.server, sys

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

NoCacheHandler.extensions_map[".mjs"] = "text/javascript"
NoCacheHandler.extensions_map[".wasm"] = "application/wasm"
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), NoCacheHandler).serve_forever()
PY
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null' EXIT INT TERM

# Wait for the server to answer before opening the page (about 5 s at most).
tries=0
until curl -s -o /dev/null "$URL"; do
  tries=$((tries + 1))
  if [ "$tries" -gt 50 ] || ! kill -0 "$SERVER" 2>/dev/null; then
    echo "The server didn't start on port $PORT (already in use?)."
    exit 1
  fi
  sleep 0.1
done

echo "Trichr-o-matic Web: $URL (Ctrl+C to stop)"
open_page
wait "$SERVER"
