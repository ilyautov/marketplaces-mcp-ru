#!/bin/bash
# macOS double-click installer. Finder runs this in Terminal.
cd "$(dirname "$0")" || exit 1
PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then
  echo "Python 3.10+ not found. Install it from https://python.org, then run this again."
  read -r -p "Press Enter to close…"
  exit 1
fi
"$PY" install.py
echo
read -r -p "Done. Press Enter to close…"
