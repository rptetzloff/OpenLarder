#!/bin/sh
# Migrate, then serve. set -e so a failed migration stops the container
# instead of serving against a schema it does not expect.
set -e

if [ -z "${OPENLARDER_DATABASE_URL}" ]; then
  echo "OPENLARDER_DATABASE_URL is not set; refusing to start." >&2
  exit 1
fi

echo "running migrations..."
alembic upgrade head

echo "serving on :${PORT:-8000}"
exec uvicorn openlarder.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
