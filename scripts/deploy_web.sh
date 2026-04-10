#!/usr/bin/env bash
set -euo pipefail

cd /opt/land-monitor
source "$(dirname "$0")/common_env.sh"
ENV_FILE="$(load_land_monitor_env)"
source .venv/bin/activate
cd /opt/land-monitor/web
echo "env_file=${ENV_FILE}"
python manage.py collectstatic --noinput
systemctl daemon-reload
systemctl restart land-monitor-web
