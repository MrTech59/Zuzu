#!/usr/bin/env bash
# Zuzu PostgreSQL backup script (runs inside the deployment environment).
#
# Usage: backup.sh [output-dir]
# Produces a timestamped, compressed pg_dump of the zuzu database.
# Restore: pg_restore -U zuzu -d zuzu --clean <file>
set -euo pipefail

OUT_DIR="${1:-/var/backups/zuzu}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${OUT_DIR}/zuzu-db-${STAMP}.dump"

mkdir -p "${OUT_DIR}"

echo "[zuzu-backup] dumping to ${TARGET}"
pg_dump -U zuzu -d zuzu -Fc -f "${TARGET}"

echo "[zuzu-backup] pruning dumps older than 14 days"
find "${OUT_DIR}" -name 'zuzu-db-*.dump' -mtime +14 -delete

echo "[zuzu-backup] done"
