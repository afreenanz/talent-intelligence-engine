#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh. REPLACES the current database and uploads.
#
#   scripts/restore.sh backups/<timestamp>
#
# Steps: stop the app (keep Postgres), restore the database, restore uploads, start the app.
# The app's init step then runs migrations, which are a no-op for a backup from the same version.
set -euo pipefail
cd "$(dirname "$0")/.."

src="${1:?usage: scripts/restore.sh backups/<timestamp>}"
[ -f "$src/db.dump" ] || { echo "no $src/db.dump"; exit 1; }
project="${COMPOSE_PROJECT_NAME:-talent-engine}"
user="$(grep -E '^POSTGRES_USER=' .env 2>/dev/null | cut -d= -f2- || true)"; user="${user:-tie}"
db="$(grep -E '^POSTGRES_DB=' .env 2>/dev/null | cut -d= -f2- || true)"; db="${db:-tie}"

if [ "${RESTORE_YES:-}" != "1" ]; then
  read -r -p "This replaces database '$db' and all uploads in project '$project'. Type 'restore' to continue: " ok
  [ "$ok" = "restore" ] || { echo "Cancelled."; exit 1; }
fi

echo "Stopping the app (database stays up)..."
docker compose -p "$project" --profile app stop api worker beat web >/dev/null 2>&1 || true
docker compose -p "$project" up -d postgres redis >/dev/null
until docker compose -p "$project" exec -T postgres pg_isready -U "$user" -d "$db" >/dev/null 2>&1; do sleep 1; done

echo "Restoring the database..."
docker compose -p "$project" exec -T postgres pg_restore -U "$user" -d "$db" --clean --if-exists --no-owner < "$src/db.dump"

if [ -f "$src/uploads.tgz" ]; then
  echo "Restoring uploads..."
  docker run --rm --user 0 --entrypoint sh \
    -v "${project}_uploads:/data" -v "$PWD/$src:/backup:ro" \
    talent-engine-backend -c "rm -rf /data/* && tar xzf /backup/uploads.tgz -C /data && chown -R 10001:10001 /data"
fi

echo "Starting the app..."
docker compose -p "$project" --profile app up -d >/dev/null
echo "Restored from $src. Check: curl -s http://localhost:${WEB_HOST_PORT:-8090}/health/ready"
