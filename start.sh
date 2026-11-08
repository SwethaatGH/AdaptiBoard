#!/usr/bin/env bash
# AdaptiBoard - one-command start for the BOARD laptop (macOS / Linux).
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Creating Python environment..."
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r server/requirements.txt
if [ ! -f web/dist/index.html ]; then
  echo "Building the web app (first run only)..."
  (cd web && npm install --no-audit --no-fund && npm run build)
fi
exec .venv/bin/python -u server/main.py "$@"
