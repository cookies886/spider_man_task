#!/usr/bin/env bash
# SpiderMan 自动备份脚本，由 cron 每日调用。
#
# 备份内容：
#   1. Postgres 全库 dump (pg_dump)
#   2. 持久化数据目录（projects/zips/taskLogs/persistent/workerdata）
#
# 保留策略：最近 7 天日备份 + 每周一份长期保留 4 周
#
# 用法：直接调用，所需变量自动从同目录的 .env 读取。
#   bash backup.sh [destination_dir]
#
# 推荐 cron 配置：
#   0 3 * * * cd /opt/spiderman/install && bash scripts/backup.sh >> /var/log/spiderman-backup.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
cd "$INSTALL_DIR"

# Load .env
if [ ! -f .env ]; then
    echo "[ERR] .env not found at $INSTALL_DIR" >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

DATA_ROOT="${DATA_ROOT:-/opt/spiderman}"
BACKUP_DEST="${1:-${DATA_ROOT}/backups}"
mkdir -p "$BACKUP_DEST"

TS="$(date +%Y%m%d-%H%M%S)"
DOW="$(date +%u)"  # 1-7 (Monday=1)

# ---------- Postgres dump ----------
echo "[$(date)] postgres dump..."
PGDUMP_FILE="$BACKUP_DEST/pgdump-$TS.sql.gz"
docker compose exec -T postgres pg_dump -U spiderman spiderman | gzip > "$PGDUMP_FILE"
PG_SIZE="$(du -h "$PGDUMP_FILE" | cut -f1)"

# ---------- Persistent data tarball ----------
echo "[$(date)] data tar..."
DATA_FILE="$BACKUP_DEST/data-$TS.tar.gz"
tar -czf "$DATA_FILE" -C "$DATA_ROOT" \
    --exclude='backups' \
    --exclude='pgdata' \
    --exclude='redisdata' \
    projects zips taskLogs persistent workerdata 2>/dev/null || true
DATA_SIZE="$(du -h "$DATA_FILE" | cut -f1)"

# ---------- Long-term retention (Monday only) ----------
# Promote a daily backup into the long-term pool on Mondays.
if [ "$DOW" = "1" ]; then
    cp "$PGDUMP_FILE" "$BACKUP_DEST/pgdump-weekly-$TS.sql.gz"
    cp "$DATA_FILE"   "$BACKUP_DEST/data-weekly-$TS.tar.gz"
fi

# ---------- Cleanup ----------
# Keep daily backups for 7 days
find "$BACKUP_DEST" -maxdepth 1 -name 'pgdump-2*.sql.gz' -mtime +7 -delete 2>/dev/null || true
find "$BACKUP_DEST" -maxdepth 1 -name 'data-2*.tar.gz'   -mtime +7 -delete 2>/dev/null || true
# Keep weekly backups for 28 days (4 weeks)
find "$BACKUP_DEST" -maxdepth 1 -name 'pgdump-weekly-*.sql.gz' -mtime +28 -delete 2>/dev/null || true
find "$BACKUP_DEST" -maxdepth 1 -name 'data-weekly-*.tar.gz'   -mtime +28 -delete 2>/dev/null || true

echo "[$(date)] OK: pg=$PG_SIZE data=$DATA_SIZE → $BACKUP_DEST"
