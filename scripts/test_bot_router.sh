#!/usr/bin/env bash
set -euo pipefail

echo "=== status ==="
.venv/bin/python scripts/bot_router.py status
echo

echo "=== recent ==="
.venv/bin/python scripts/bot_router.py recent
echo

echo "=== cheapest ==="
.venv/bin/python scripts/bot_router.py cheapest
echo

echo "=== auction 1 ==="
.venv/bin/python scripts/bot_router.py auction 1
echo

echo "=== runs ==="
.venv/bin/python scripts/bot_router.py runs
