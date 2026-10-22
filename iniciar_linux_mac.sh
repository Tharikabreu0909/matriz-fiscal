#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Prefer Python 3.13, then 3.12 or 3.11; do not silently use 3.14+.
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11; do
  if command -v "$candidate" >/dev/null 2>&1; then PYTHON_BIN="$candidate"; break; fi
done
if [ -z "$PYTHON_BIN" ]; then
  echo "CheckFiscal 1.45 precisa de Python 3.11, 3.12 ou 3.13."
  exit 1
fi

if [ -x .venv/bin/python ]; then
  if ! .venv/bin/python -c 'import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)'; then
    rm -rf .venv
  fi
fi
"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate

if [ ! -f .venv/.checkfiscal-deps-1.45 ]; then
  python -m pip install --upgrade pip
  python -m pip install --disable-pip-version-check -r requirements.txt
  touch .venv/.checkfiscal-deps-1.45
fi

export CHECKFISCAL_DATA_DIR="${CHECKFISCAL_DATA_DIR:-$HOME/.checkfiscal}"
mkdir -p "$CHECKFISCAL_DATA_DIR"
python -m uvicorn app:app --host 127.0.0.1 --port 8145 --no-access-log
