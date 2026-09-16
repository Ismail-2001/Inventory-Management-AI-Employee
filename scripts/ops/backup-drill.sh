#!/usr/bin/env bash
# PostgreSQL Backup & Restore Drill Script
# Usage: ./backup-drill.sh [backup|restore|drill]

set -euo pipefail

BACKUP_DIR="./backups"
DB_NAME="${POSTGRES_DB:-inventory_agent}"
DB_USER="${POSTGRES_USER:-inventory}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/drill_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

backup_database() {
    log "Starting backup of database: ${DB_NAME}"
    pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
        --no-owner --no-acl --clean --if-exists | gzip > "${BACKUP_FILE}"
    
    if [[ -f "${BACKUP_FILE}" ]] && [[ -s "${BACKUP_FILE}" ]]; then
        SIZE=$(stat -f%z "${BACKUP_FILE}" 2>/dev/null || stat --printf="%s" "${BACKUP_FILE}" 2>/dev/null)
        log "Backup complete: ${BACKUP_FILE} (${SIZE} bytes)"
        return 0
    else
        log "ERROR: Backup failed"
        return 1
    fi
}

restore_database() {
    if [[ ! -f "${BACKUP_FILE}" ]]; then
        log "ERROR: Backup file not found: ${BACKUP_FILE}"
        return 1
    fi
    
    log "WARNING: This will DROP and recreate database '${DB_NAME}'!"
    read -p "Continue? (yes/no): " confirm
    [[ "${confirm}" != "yes" ]] && { log "Aborted."; return 1; }
    
    log "Dropping existing database..."
    dropdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" --if-exists "${DB_NAME}"
    
    log "Creating fresh database..."
    createdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" "${DB_NAME}"
    
    log "Restoring from backup..."
    gunzip -c "${BACKUP_FILE}" | psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -q
    
    log "Restore complete. Running verification..."
    verify_restore
}

verify_restore() {
    log "Verifying database integrity..."
    
    TABLE_COUNT=$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -t -c \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d ' ')
    
    MIGRATION_VERSION=$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -t -c \
        "SELECT COALESCE(MAX(version_num), 'none') FROM alembic_version;" | tr -d ' ')
    
    log "Tables found: ${TABLE_COUNT}"
    log "Migration version: ${MIGRATION_VERSION}"
    
    if [[ "${TABLE_COUNT}" -gt 0 ]]; then
        log "✅ Verification passed"
        return 0
    else
        log "❌ Verification failed - no tables found"
        return 1
    fi
}

run_drill() {
    log "=== STARTING BACKUP DRILL ==="
    
    log "Step 1: Backup"
    backup_database || { log "Drill failed at backup step"; return 1; }
    
    log "Step 2: Restore"
    restore_database || { log "Drill failed at restore step"; return 1; }
    
    log "Step 3: Cleanup"
    rm -f "${BACKUP_FILE}"
    log "Drill backup cleaned up"
    
    log "=== DRILL COMPLETE ==="
}

case "${1:-drill}" in
    backup)  backup_database ;;
    restore) restore_database ;;
    drill)   run_drill ;;
    *)       echo "Usage: $0 {backup|restore|drill}"; exit 1 ;;
esac
