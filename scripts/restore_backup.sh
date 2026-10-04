#!/usr/bin/env bash
# Restore the database from a backup made by scripts/backup.sh.
#   sudo bash scripts/restore_backup.sh                          # list server and off-site backups
#   sudo bash scripts/restore_backup.sh local/db-20261004T0100Z.dump
#   sudo bash scripts/restore_backup.sh offsite:db/daily/db-20261001T0000Z.dump
# A fresh safety dump of the current database is taken first, so a restore can itself be undone.
# Uploaded files: rclone --config /etc/coach-bot/rclone.conf copy offsite:files/current <volume path>
set -euo pipefail
cd /opt/coach-bot
DEST=/var/backups/coach-bot
RCLONE=(rclone --config /etc/coach-bot/rclone.conf)
offsite() { [ -f /etc/coach-bot/rclone.conf ] && "${RCLONE[@]}" listremotes 2>/dev/null | grep -q '^offsite:'; }

if [ $# -eq 0 ]; then
  echo "On this server:"; ls -1t "$DEST/local" 2>/dev/null | sed 's#^#  local/#'
  if offsite; then
    for tier in hourly daily monthly; do
      echo "Off-site $tier (newest first):"
      "${RCLONE[@]}" lsf "offsite:db/$tier/" | sort -r | head -8 | sed "s#^#  offsite:db/$tier/#"
    done
  fi
  echo; echo "Usage: sudo bash scripts/restore_backup.sh <one of the paths above>"; exit 0
fi

src=$1
umask 077
case "$src" in
  offsite:*) dump="$DEST/.restore-$(date +%s).dump"; "${RCLONE[@]}" copyto "$src" "$dump"; trap 'rm -f "$dump"' EXIT ;;
  local/*)   dump="$DEST/$src" ;;
  *)         dump="$src" ;;
esac
[ -s "$dump" ] || { echo "No such dump: $src"; exit 1; }
docker compose exec -T postgres pg_restore --list < "$dump" > /dev/null || { echo "Dump is not readable"; exit 1; }

echo "This replaces the LIVE database with: $src"
read -r -p "Type RESTORE to continue: " answer
[ "$answer" = "RESTORE" ] || { echo "Cancelled."; exit 1; }

mkdir -p "$DEST/local"
safety="$DEST/local/db-$(date -u +%Y%m%dT%H%MZ)-before-restore.dump"
docker compose exec -T postgres pg_dump -U coach -d coach -Fc -Z 6 > "$safety"
echo "Safety copy of the current database: $safety"

docker compose stop bot web-api
docker compose exec -T postgres pg_restore -U coach -d coach --clean --if-exists --no-owner --single-transaction < "$dump"
docker compose up -d bot web-api
docker compose restart ingress
echo "Restored. Check the panel and the bot."
