#!/usr/bin/env bash
# Back up the database and uploaded résumés of the running stack.
#
#   scripts/backup.sh                 -> backups/<UTC timestamp>/{db.dump, uploads.tgz}
#   COMPOSE_PROJECT_NAME=x scripts/backup.sh    (a different compose project)
#
# db.dump is a pg_dump custom-format archive (both schemas: app tables and LangGraph checkpoints).
# Backups contain personal data (profiles, résumés, conversations): backups/ is git-ignored; keep it private.
set -euo pipefail
cd "$(dirname "$0")/.."

project="${COMPOSE_PROJECT_NAME:-talent-engine}"
dir="backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$dir"
user="$(grep -E '^POSTGRES_USER=' .env 2>/dev/null | cut -d= -f2- || true)"; user="${user:-tie}"
db="$(grep -E '^POSTGRES_DB=' .env 2>/dev/null | cut -d= -f2- || true)"; db="${db:-tie}"

echo "Dumping database '$db' from project '$project'..."
docker compose -p "$project" exec -T postgres pg_dump -U "$user" -d "$db" -Fc > "$dir/db.dump"

echo "Archiving uploaded résumés..."
# The backend image already has tar; run it as root only to read the volume.
docker run --rm --user 0 --entrypoint tar \
  -v "${project}_uploads:/data:ro" -v "$PWD/$dir:/backup" \
  talent-engine-backend czf /backup/uploads.tgz -C /data .

echo "Backup written to $dir"
ls -lh "$dir"
