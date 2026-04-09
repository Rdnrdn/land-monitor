#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
REQ_FILE="$ROOT_DIR/requirements.txt"

find_python() {
  local candidate

  for candidate in python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

if ! PYTHON_BIN="$(find_python)"; then
  echo "Python 3.10+ is required for this project (Django 5.2)."
  echo "Install Python 3.10+ locally, then rerun: ./scripts/bootstrap_local.sh"
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$REQ_FILE"

if [ ! -f "$ROOT_DIR/.env" ]; then
  echo
  echo "Missing $ROOT_DIR/.env"
  echo "Create it from the example:"
  echo "  cp .env.example .env"
fi

echo
echo "Local environment is ready."
echo "Python: $(python --version 2>&1)"
echo "Venv: $VENV_DIR"
