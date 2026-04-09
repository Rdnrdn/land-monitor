#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PID_DIR="$ROOT_DIR/.local"
PID_FILE="$PID_DIR/django.pid"
LOG_FILE="$PID_DIR/django.log"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

mkdir -p "$PID_DIR"

if [ ! -d "$VENV_DIR" ]; then
  echo "Virtualenv not found. Run ./scripts/bootstrap_local.sh first."
  exit 1
fi

if [ ! -f "$ROOT_DIR/.env" ]; then
  echo "Missing $ROOT_DIR/.env"
  echo "Create it from the example:"
  echo "  cp .env.example .env"
  echo "Then make sure PostgreSQL is available with the LAND_DB_* settings."
  exit 1
fi

if [ -f "$PID_FILE" ]; then
  existing_pid="$(cat "$PID_FILE")"
  if kill -0 "$existing_pid" >/dev/null 2>&1; then
    echo "Local Django server is already running with PID $existing_pid"
    echo "Stop it first: ./scripts/stop_local.sh"
    exit 1
  fi
  rm -f "$PID_FILE"
fi

source "$VENV_DIR/bin/activate"

(
  cd "$ROOT_DIR/web"
  nohup python manage.py runserver "$HOST:$PORT" >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
)

sleep 2

server_pid="$(cat "$PID_FILE")"
if ! kill -0 "$server_pid" >/dev/null 2>&1; then
  echo "Django failed to start. Last log lines:"
  tail -n 20 "$LOG_FILE" || true
  rm -f "$PID_FILE"
  exit 1
fi

echo "Local Django server started."
echo "URL: http://$HOST:$PORT/"
echo "PID: $server_pid"
echo "Log: $LOG_FILE"
echo "Stop: ./scripts/stop_local.sh"
