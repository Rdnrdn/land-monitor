#!/usr/bin/env bash
set -euo pipefail

cd /opt/land-monitor
source .venv/bin/activate
cd /opt/land-monitor/web
python manage.py collectstatic --noinput
systemctl daemon-reload
systemctl restart land-monitor-web
systemctl reload caddy
