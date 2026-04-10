#!/usr/bin/env bash
set -euo pipefail

cd /opt/land-monitor
source "$(dirname "$0")/common_env.sh"
ENV_FILE="$(load_land_monitor_env)"
require_land_monitor_db_env

BACKUP_DIR="${LAND_MONITOR_BACKUP_DIR:-/var/backups/land-monitor}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/land_monitor_${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"

echo "env_file=${ENV_FILE}"
echo "backup_target=${BACKUP_FILE}"
echo "db_target=$(land_monitor_db_target)"

PGPASSWORD="${LAND_DB_PASSWORD}" pg_dump \
  -h "${LAND_DB_HOST}" \
  -p "${LAND_DB_PORT}" \
  -U "${LAND_DB_USER}" \
  -d "${LAND_DB_NAME}" \
  -Fc \
  -f "${BACKUP_FILE}"

ls -lh "${BACKUP_FILE}"
