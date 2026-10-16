#!/bin/sh
# Double-click in Finder: opens Terminal, serves the web version and opens it
# in the browser. Close the Terminal window (or Ctrl+C) to stop the server.
exec "$(dirname "$0")/serve.sh"
