#!/bin/sh
# Serves the repository root locally, so the page can read the desktop app's
# trichrome/ modules and icons, and opens http://localhost:8000/web/ in the
# default browser (a page opened as a file:// URL can't start its worker).
#
# Usage: ./web/serve.sh [port]         this Mac only (localhost)
#        ./web/serve.sh --lan [port]   also phones on the same Wi-Fi
#
# --lan is for testing on a real phone. It serves only what the page needs
# (web/, the two trichrome/ modules the worker loads, resources/ without its
# private folders), never lists folders, and stops by itself after an hour.
# Port 8080 by default, so it can run next to the local server.
#
# It serves https, because iPhone keeps some features (the share sheet that
# saves to Photos) for secure pages. The certificate is made here, on first
# use, and kept in .lan-cert/ (gitignored, never served): self-signed, for
# this Mac's address only, not a certificate authority, valid 30 days. The
# phone warns once that the connection isn't private: accept it for this
# address ("visit this website"). Never install it on the phone.
# Ctrl+C stops the server.
cd "$(dirname "$0")/.." || exit 1

LAN=0
if [ "${1:-}" = "--lan" ]; then LAN=1; shift; fi
if [ "$LAN" = 1 ]; then PORT="${1:-8080}"; else PORT="${1:-8000}"; fi
URL="http://localhost:$PORT/web/"
LAN_MINUTES=60
CERT_DIR=".lan-cert"
CURL_OPTS=""

if [ "$LAN" = 1 ]; then
  # The Mac's address on the Wi-Fi (en0) or, failing that, Ethernet (en1).
  IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)"
  if [ -z "$IP" ]; then
    echo "This Mac has no network address: connect it to the Wi-Fi first."
    exit 1
  fi
  URL="https://localhost:$PORT/web/"
  CURL_OPTS="-k"
  # A new certificate when there's none, it expires within a day, or the
  # Mac's address changed.
  if [ ! -f "$CERT_DIR/cert.pem" ] \
     || ! openssl x509 -in "$CERT_DIR/cert.pem" -noout -checkend 86400 >/dev/null 2>&1 \
     || ! openssl x509 -in "$CERT_DIR/cert.pem" -noout -ext subjectAltName 2>/dev/null | grep -q "IP Address:$IP\$"; then
    mkdir -p "$CERT_DIR" && chmod 700 "$CERT_DIR"
    openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
      -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" \
      -subj "/CN=Trichr-o-matic dev server" \
      -addext "subjectAltName=IP:$IP,DNS:localhost" \
      -addext "basicConstraints=critical,CA:FALSE" \
      -addext "extendedKeyUsage=serverAuth" >/dev/null 2>&1 || {
        echo "Couldn't create the test certificate (openssl)."; exit 1; }
    chmod 600 "$CERT_DIR/key.pem"
  fi
fi

open_page() {
  if command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
  else echo "Open $URL in your browser."
  fi
}

# Already running (from another terminal): just open the page.
if [ "$LAN" = 0 ] && curl -s -o /dev/null "$URL"; then
  echo "Trichr-o-matic Web is already served at $URL"
  open_page
  exit 0
fi

# Like `python3 -m http.server`, but tells the browser not to cache: a
# reload must always pick up edited files, the worker's engine.py included.
python3 - "$PORT" "$LAN" "$LAN_MINUTES" "$CERT_DIR" >/dev/null 2>&1 <<'PY' &
import http.server, io, posixpath, ssl, sys, threading, urllib.parse

port, lan, minutes, cert_dir = int(sys.argv[1]), sys.argv[2] == "1", int(sys.argv[3]), sys.argv[4]

# --lan: the only paths a phone may read. Everything else is a 404, folder
# listings included: the rest of the repo (private notes among them) stays
# on this Mac.
ALLOWED_PREFIXES = ("web/", "resources/")
ALLOWED_FILES = {"trichrome/imaging.py", "trichrome/alignment.py"}
BLOCKED_PREFIXES = ("resources/icons/Unused/", "resources/TEST_FILES/")


# --lan: what the phone gets for the page's service worker. A worker stored
# on an earlier visit could keep serving old files (it can fail to reach a
# self-signed server); the browser fetches this script itself on each visit
# to check for updates, so it replaces the old worker, which then removes
# itself and its stored copies and reloads the page.
RETIRE_WORKER = b"""
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil((async () => {
  for (const key of await caches.keys()) await caches.delete(key);
  await self.registration.unregister();
  for (const client of await self.clients.matchAll({ type: "window" })) client.navigate(client.url);
})()));
"""


def lan_allowed(url_path):
    path = posixpath.normpath(urllib.parse.unquote(url_path.split("?", 1)[0])).lstrip("/")
    if path in ALLOWED_FILES:
        return True
    if any(part.startswith(".") or part == "__pycache__" for part in path.split("/")):
        return False
    # "web" alone is the page itself (index.html).
    in_allowed = path == "web" or path.startswith(ALLOWED_PREFIXES)
    return in_allowed and not path.startswith(BLOCKED_PREFIXES)


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    # A connection that goes quiet (a phone's unused preconnection) is
    # dropped instead of holding its thread.
    timeout = 30

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_head(self):
        if lan and not lan_allowed(self.path):
            self.send_error(404)
            return None
        if lan and self.path.split("?", 1)[0] == "/web/sw.js":
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript")
            self.send_header("Content-Length", str(len(RETIRE_WORKER)))
            self.end_headers()
            return io.BytesIO(RETIRE_WORKER)
        return super().send_head()

    def list_directory(self, path):
        if lan:
            self.send_error(404)
            return None
        return super().list_directory(path)


NoCacheHandler.extensions_map[".mjs"] = "text/javascript"
NoCacheHandler.extensions_map[".wasm"] = "application/wasm"
class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    context = None

    # https: each connection's handshake runs on its own thread (on first
    # read), not in accept(): wrapping the listening socket made one client
    # that never finished its handshake block the whole server.
    def get_request(self):
        sock, address = self.socket.accept()
        if self.context:
            sock.settimeout(30)
            sock = self.context.wrap_socket(sock, server_side=True, do_handshake_on_connect=False)
        return sock, address


server = Server(("0.0.0.0" if lan else "127.0.0.1", port), NoCacheHandler)
if lan:
    server.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.context.load_cert_chain(f"{cert_dir}/cert.pem", f"{cert_dir}/key.pem")
    threading.Timer(minutes * 60, server.shutdown).start()
server.serve_forever()
PY
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null' EXIT INT TERM

# Wait for the server to answer before opening the page (about 5 s at most).
tries=0
until curl -s $CURL_OPTS -o /dev/null "$URL"; do
  tries=$((tries + 1))
  if [ "$tries" -gt 50 ] || ! kill -0 "$SERVER" 2>/dev/null; then
    echo "The server didn't start on port $PORT (already in use?)."
    exit 1
  fi
  sleep 0.1
done

if [ "$LAN" = 1 ]; then
  echo "Trichr-o-matic Web, for phones on this Wi-Fi:"
  echo
  echo "    https://$IP:$PORT/web/"
  echo
  echo "The phone warns that the connection isn't private (a test certificate"
  echo "made on this Mac): accept it for this address. Don't install it."
  echo "Stops by itself in $LAN_MINUTES minutes. Ctrl+C stops it now."
else
  echo "Trichr-o-matic Web: $URL (Ctrl+C to stop)"
  open_page
fi
wait "$SERVER"
