#!/usr/bin/env bash
set -euo pipefail

cd /opt/land-monitor
source "$(dirname "$0")/common_env.sh"
ENV_FILE="$(load_land_monitor_env)"
require_land_monitor_db_env
source .venv/bin/activate

echo "env_file=${ENV_FILE}"
echo "db_target=$(land_monitor_db_target)"

PGPASSWORD="${LAND_DB_PASSWORD}" psql \
  -h "${LAND_DB_HOST}" \
  -p "${LAND_DB_PORT}" \
  -U "${LAND_DB_USER}" \
  -d "${LAND_DB_NAME}" \
  -Atqc "
    select 'current_database=' || current_database();
    select 'current_user=' || current_user;
    select 'auth_user_count=' || count(*) from auth_user;
    select 'alembic_version=' || version_num from alembic_version;
  "

python web/manage.py shell -c "
from django.db import connection
from django.contrib.auth import get_user_model
with connection.cursor() as cur:
    cur.execute('select current_database(), current_user')
    db, user = cur.fetchone()
print(f'django_current_database={db}')
print(f'django_current_user={user}')
print(f'django_auth_user_count={get_user_model().objects.count()}')
"

./.venv/bin/alembic current
