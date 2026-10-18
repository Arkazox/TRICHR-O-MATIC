#!/bin/sh
# Double-click in Finder: opens Terminal and starts both servers, the local
# one (opened in the browser) and the --lan one for a phone on the same
# Wi-Fi (its address is printed below). Close the Terminal window (or
# Ctrl+C) to stop both; the --lan one also stops by itself after an hour.
DIR="$(dirname "$0")"
"$DIR/serve.sh" --lan &
LAN=$!
trap 'kill "$LAN" 2>/dev/null' EXIT INT TERM
"$DIR/serve.sh"
# The local server was already running (serve.sh only opened the page):
# keep the --lan one up until it stops.
wait "$LAN"
