#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/claw/projects/land-monitor"

cd "$PROJECT_ROOT"
exec .venv/bin/python scripts/bot_router.py "$@"
