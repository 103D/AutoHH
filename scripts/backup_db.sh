#!/bin/bash
# Database backup script for AI Job Hunter
# Usage: ./scripts/backup_db.sh [container_name] [output_dir]

set -euo pipefail

CONTAINER_NAME="${1:-jobhunter-postgres}"
OUTPUT_DIR="${2:-./backups}"
DB_USER="${DB_USER:-jobhunter}"
DB_NAME="${DB_NAME:-jobhunter}"

mkdir -p "$OUTPUT_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$OUTPUT_DIR/jobhunter_${TIMESTAMP}.dump"

echo "Creating backup: $BACKUP_FILE"

docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$BACKUP_FILE"

echo "Backup created: $BACKUP_FILE"
echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"

# Clean old backups (keep last 7 days)
find "$OUTPUT_DIR" -name "jobhunter_*.dump" -mtime +7 -delete 2>/dev/null || true
echo "Old backups cleaned (kept last 7 days)"