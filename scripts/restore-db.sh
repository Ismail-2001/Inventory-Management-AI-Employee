#!/bin/bash
set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <backup-file.sql.gz>"
    exit 1
fi

gunzip -c "$1" | psql "$DATABASE_URL"
echo "Restored from: $1"
