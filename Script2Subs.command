#!/bin/bash
# Double-click in Finder to open the Script2Subs dashboard.
#
# From a terminal you can also pass normal CLI arguments through:
#   ./Script2Subs.command                                  -> dashboard
#   ./Script2Subs.command --audio narration.wav            -> align from audio
#   ./Script2Subs.command --timings narration.json --en english.txt --zh chinese.txt
#
# Needs only Python 3.10+ on PATH. Nothing is installed into the system;
# the app is run straight from this folder.
set -euo pipefail
cd "$(dirname "$0")"

# Override the interpreter with: PYTHON=/path/to/python3 ./Script2Subs.command
PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python 3 was not found on your PATH."
  echo "Install Python 3.10+ from https://www.python.org/downloads/ and try again."
  echo "Press Enter to close."
  read -r _
  exit 1
fi

# No arguments (a double-click) means: open the dashboard.
if [ "$#" -eq 0 ]; then
  exec "$PYTHON" -m script2subs ui
else
  exec "$PYTHON" -m script2subs "$@"
fi
