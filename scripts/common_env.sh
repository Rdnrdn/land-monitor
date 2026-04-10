#!/usr/bin/env bash

resolve_land_monitor_env_file() {
  if [[ -n "${LAND_MONITOR_ENV_FILE:-}" && -f "${LAND_MONITOR_ENV_FILE}" ]]; then
    printf '%s\n' "${LAND_MONITOR_ENV_FILE}"
    return 0
  fi

  if [[ -f /etc/land-monitor/land-monitor.env ]]; then
    printf '%s\n' /etc/land-monitor/land-monitor.env
    return 0
  fi

  if [[ -f /opt/land-monitor/.env ]]; then
    printf '%s\n' /opt/land-monitor/.env
    return 0
  fi

  if [[ -f ./.env ]]; then
    printf '%s\n' ./.env
    return 0
  fi

  return 1
}

load_land_monitor_env() {
  local env_file
  env_file="$(resolve_land_monitor_env_file)" || {
    echo "land-monitor env file not found" >&2
    return 1
  }

  export LAND_MONITOR_ENV_FILE="${env_file}"
  set -a
  source "${env_file}"
  set +a
  printf '%s\n' "${env_file}"
}

require_land_monitor_db_env() {
  local missing=0
  local key
  for key in LAND_DB_HOST LAND_DB_PORT LAND_DB_NAME LAND_DB_USER LAND_DB_PASSWORD; do
    if [[ -z "${!key:-}" ]]; then
      echo "missing required env var: ${key}" >&2
      missing=1
    fi
  done
  return "${missing}"
}

land_monitor_db_target() {
  printf 'host=%s port=%s db=%s user=%s\n' \
    "${LAND_DB_HOST}" \
    "${LAND_DB_PORT}" \
    "${LAND_DB_NAME}" \
    "${LAND_DB_USER}"
}
