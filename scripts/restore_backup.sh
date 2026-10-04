#!/usr/bin/env bash
# Restore the database from a backup made by scripts/backup.sh.
#   sudo bash scripts/restore_backup.sh                  # lists available backups
#   sudo bash scripts/restore_backup.sh /var/backups/coach-bot/hourly/db-20261004T0100Z.dump
# A fresh safety dump of the current database is taken first, so a restore can itself be undone.
set -euo pipefail
cd /opt/coach-bot
DEST=/var/backups/coach-bot
if [ $# -eq 0 ]; then
  echo "Hourly:"; ls -1t "$DEST/hourly" | head -12
  echo "Daily:";  ls -1t "$DEST/daily" | head -12
  echo; echo "Usage: sudo bash scripts/restore_backup.sh <path to db.dump>"; exit 0
fi
dump=$1
[ -s "$dump" ] || { echo "No such dump: $dump"; exit 1; }
docker compose exec -T postgres pg_restore --list < "$dump" > /dev/null || { echo "Dump is not readable"; exit 1; }

echo "This replaces the LIVE database with: $dump"
read -r -p "Type RESTORE to continue: " answer
[ "$answer" = "RESTORE" ] || { echo "Cancelled."; exit 1; }

safety="$DEST/hourly/db-$(date -u +%Y%m%dT%H%MZ)-before-restore.dump"
docker compose exec -T postgres pg_dump -U coach -d coach -Fc -Z 6 > "$safety"
echo "Safety copy of the current database: $safety"

docker compose stop bot web-api
docker compose exec -T postgres pg_restore -U coach -d coach --clean --if-exists --no-owner --single-transaction < "$dump"
docker compose up -d bot web-api
docker compose restart ingress
echo "Restored. Check the panel and the bot."
