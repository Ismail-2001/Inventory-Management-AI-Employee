#!/bin/bash
set -e

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR=${BACKUP_DIR:-./backups}
mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/inventory-agent-$TIMESTAMP.sql.gz"

pg_dump "$DATABASE_URL" | gzip > "$FILE"
echo "Backup saved: $FILE"
