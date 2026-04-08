#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
source .venv/bin/activate
export PYTHONPATH="$(pwd)/src"
python scripts/run_torgi_gov.py
