#!/usr/bin/env bash
# Linux / macOS installer. Run: bash install.sh
cd "$(dirname "$0")" || exit 1
# Pick the first interpreter that is a real Python 3.10+ (a bare `python`
# may be Python 2, which would die with a SyntaxError before any friendly check).
PY=""
for CAND in python3 python; do
  if command -v "$CAND" >/dev/null 2>&1 \
     && "$CAND" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    PY="$CAND"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10+ not found (or your 'python' is too old)."
  echo "Install python3 via your package manager and retry."
  exit 1
fi
exec "$PY" install.py "$@"
