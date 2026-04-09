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

if command -v pg_isready >/dev/null 2>&1; then
  if ! (
    set -a
    source "$ROOT_DIR/.env"
    set +a
    pg_isready \
      -h "${LAND_DB_HOST:-localhost}" \
      -p "${LAND_DB_PORT:-5432}" \
      -d "${LAND_DB_NAME:-land_monitor}" \
      -U "${LAND_DB_USER:-land_user}"
  ) >/dev/null 2>&1; then
    echo "PostgreSQL is not reachable with the settings from $ROOT_DIR/.env"
    echo "Check LAND_DB_* and make sure the local database is running."
    exit 1
  fi
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

# Keep local shell overrides from winning over repository .env.
unset DATABASE_URL LAND_DB_URL LAND_DB_NAME LAND_DB_HOST LAND_DB_PORT LAND_DB_USER LAND_DB_PASSWORD

cd "$ROOT_DIR/web"

if command -v setsid >/dev/null 2>&1; then
  nohup setsid python manage.py runserver "$HOST:$PORT" --noreload \
    >"$LOG_FILE" 2>&1 < /dev/null &
else
  nohup python manage.py runserver "$HOST:$PORT" --noreload \
    >"$LOG_FILE" 2>&1 < /dev/null &
fi

server_pid=$!
disown "$server_pid" 2>/dev/null || true
echo "$server_pid" >"$PID_FILE"

for _ in $(seq 1 10); do
  if ! kill -0 "$server_pid" >/dev/null 2>&1; then
    break
  fi

  if curl -fsS "http://$HOST:$PORT/" >/dev/null 2>&1; then
    echo "Local Django server started."
    echo "URL: http://$HOST:$PORT/"
    echo "PID: $server_pid"
    echo "Log: $LOG_FILE"
    echo "Stop: ./scripts/stop_local.sh"
    exit 0
  fi

  sleep 1
done

echo "Django failed to start. Last log lines:"
tail -n 40 "$LOG_FILE" || true
rm -f "$PID_FILE"
exit 1
