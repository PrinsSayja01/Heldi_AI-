#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 is required. Install it from python.org or Homebrew."
  exit 1
fi
PY_VER=$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if $PYTHON_BIN -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)'; then :; else
  echo "Python 3.10 or newer is required (found $PY_VER)."
  exit 1
fi

if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env

if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  if [ -d "/Applications/Ollama.app" ]; then
    echo "Starting Ollama…"
    open -a Ollama || true
    sleep 4
  fi
fi
if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Ollama is not running. You can start it in another terminal with: ollama serve"
  echo "The app will still start, but local AI enrichment will use its rules-based fallback until Ollama is available."
else
  echo "Ollama is reachable. Installed models:"
  ollama list || true
fi

echo "Starting Heidi Lead Intelligence Agent at http://127.0.0.1:8787"
exec uvicorn app.main:app --host 127.0.0.1 --port 8787
