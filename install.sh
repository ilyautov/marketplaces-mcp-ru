#!/usr/bin/env bash
# Linux / macOS installer. Run: bash install.sh
cd "$(dirname "$0")" || exit 1
PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then
  echo "Python 3.10+ not found. Install python3 via your package manager and retry."
  exit 1
fi
exec "$PY" install.py "$@"
