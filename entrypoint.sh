#!/bin/sh
set -eu

if [ "${MIGRATE_ON_START:-true}" = "true" ]; then
  echo "[entrypoint] Running database migrations..."
  alembic upgrade head
fi

exec "$@"
