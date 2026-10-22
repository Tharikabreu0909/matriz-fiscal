#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate

if [ ! -f .venv/.checkfiscal-deps-1.41 ]; then
  python -m pip install --disable-pip-version-check -q -r requirements.txt
  touch .venv/.checkfiscal-deps-1.41
fi

export CHECKFISCAL_DATA_DIR="${CHECKFISCAL_DATA_DIR:-$HOME/.checkfiscal}"
mkdir -p "$CHECKFISCAL_DATA_DIR"
python -m uvicorn app:app --host 127.0.0.1 --port 8141 --no-access-log
