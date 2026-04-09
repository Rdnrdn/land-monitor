#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.local/django.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "No local Django PID file found."
  echo "If the server was started manually, stop it with Ctrl-C in that terminal."
  exit 0
fi

pid="$(cat "$PID_FILE")"

if kill -0 "$pid" >/dev/null 2>&1; then
  kill "$pid"
  echo "Stopped local Django server (PID $pid)."
else
  echo "Process $pid is not running."
fi

rm -f "$PID_FILE"
