#!/bin/bash
#
# Weekly backup script for hydroponic controller
#

set -e

BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
USER_HOME="${HOME:-/home/$USER}"
HYDRO_DIR="$USER_HOME/hydro"
BACKUP_DIR="$HYDRO_DIR/backups"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Starting weekly backup - $BACKUP_DATE"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Create backup filename
BACKUP_FILE="$BACKUP_DIR/hydro_backup_$BACKUP_DATE.tar.gz"

echo "Backup location: $BACKUP_FILE"

# Create temporary directory for backup staging
TEMP_DIR=$(mktemp -d)
BACKUP_STAGING="$TEMP_DIR/hydro_backup_$BACKUP_DATE"
mkdir -p "$BACKUP_STAGING"

cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

echo "Staging backup data..."

# Copy database
if [[ -f "$HYDRO_DIR/db/hydro.db" ]]; then
    echo "  - Database"
    mkdir -p "$BACKUP_STAGING/db"
    cp "$HYDRO_DIR/db/hydro.db" "$BACKUP_STAGING/db/"
fi

# Copy configuration
if [[ -d "$PROJECT_DIR/app/config" ]]; then
    echo "  - Configuration"
    cp -r "$PROJECT_DIR/app/config" "$BACKUP_STAGING/"
fi

# Copy logs (last 7 days only)
if [[ -d "$HYDRO_DIR/logs" ]]; then
    echo "  - Recent logs"
    mkdir -p "$BACKUP_STAGING/logs"
    find "$HYDRO_DIR/logs" -name "*.log*" -mtime -7 -exec cp {} "$BACKUP_STAGING/logs/" \;
fi

# Copy images (last 30 days only)
if [[ -d "$HYDRO_DIR/images" ]]; then
    echo "  - Recent images"
    mkdir -p "$BACKUP_STAGING/images"
    find "$HYDRO_DIR/images" -name "*.jpg" -o -name "*.png" -mtime -30 -exec cp {} "$BACKUP_STAGING/images/" \;
fi

# Copy ChromaDB vector store
if [[ -d "$HYDRO_DIR/chroma" ]]; then
    echo "  - Vector memory"
    cp -r "$HYDRO_DIR/chroma" "$BACKUP_STAGING/"
fi

# Create system info file
echo "  - System information"
cat > "$BACKUP_STAGING/backup_info.txt" << EOF
Backup Date: $BACKUP_DATE
System: $(uname -a)
Python Version: $(python3 --version)
Project Directory: $PROJECT_DIR
User: $USER

Git Information:
$(cd "$PROJECT_DIR" && git rev-parse --short HEAD 2>/dev/null || echo "Not a git repository")
$(cd "$PROJECT_DIR" && git status --porcelain 2>/dev/null | wc -l) modified files

Disk Usage:
$(df -h "$HYDRO_DIR" 2>/dev/null || echo "Directory not found")

Service Status:
$(systemctl is-active hydro-sensor-poll 2>/dev/null || echo "sensor-poll: not installed")
$(systemctl is-active hydro-control-loop 2>/dev/null || echo "control-loop: not installed")
EOF

# Create backup archive
echo "Creating compressed archive..."
cd "$TEMP_DIR"
tar -czf "$BACKUP_FILE" "hydro_backup_$BACKUP_DATE"

# Calculate backup size
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "Backup created: $BACKUP_FILE ($BACKUP_SIZE)"

# Remove old backups (keep last 4 weeks)
echo "Cleaning up old backups..."
find "$BACKUP_DIR" -name "hydro_backup_*.tar.gz" -mtime +28 -delete

# List remaining backups
BACKUP_COUNT=$(find "$BACKUP_DIR" -name "hydro_backup_*.tar.gz" | wc -l)
echo "Backup complete. $BACKUP_COUNT backup(s) retained."

# Optional: Upload to remote storage
if [[ -n "$BACKUP_REMOTE_PATH" ]]; then
    echo "Uploading to remote storage: $BACKUP_REMOTE_PATH"
    
    # Examples for different storage types:
    
    # SCP/SSH
    if [[ "$BACKUP_REMOTE_PATH" == scp://* ]]; then
        REMOTE_PATH="${BACKUP_REMOTE_PATH#scp://}"
        scp "$BACKUP_FILE" "$REMOTE_PATH" && echo "  -> Upload successful"
    fi
    
    # S3 (requires awscli)
    if [[ "$BACKUP_REMOTE_PATH" == s3://* ]]; then
        aws s3 cp "$BACKUP_FILE" "$BACKUP_REMOTE_PATH" && echo "  -> S3 upload successful"
    fi
    
    # rsync
    if [[ "$BACKUP_REMOTE_PATH" == rsync://* ]]; then
        REMOTE_PATH="${BACKUP_REMOTE_PATH#rsync://}"
        rsync -avz "$BACKUP_FILE" "$REMOTE_PATH" && echo "  -> Rsync successful"
    fi
fi

echo "Weekly backup completed successfully."