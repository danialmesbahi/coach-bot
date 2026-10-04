#!/usr/bin/env bash
# Hourly backup, run by coach-bot-backup.timer (installed by scripts/harden_server.sh).
#   hourly/  database dump every hour, newest 48 kept
#   daily/   database + uploaded catalog files + server config (.env files), newest 30 kept
#   monthly/ first daily backup of each month, newest 12 kept
# Every dump is verified with pg_restore before it is kept. If /etc/coach-bot/rclone.conf
# defines a remote named "offsite", the whole backup tree is mirrored there as well.
set -euo pipefail
APP_DIR=/opt/coach-bot
DEST=/var/backups/coach-bot
cd "$APP_DIR"
umask 077
mkdir -p "$DEST"/{hourly,daily,monthly}
exec 9>/run/coach-bot-backup.lock
flock -n 9 || exit 0

ts=$(date -u +%Y%m%dT%H%MZ)
tmp="$DEST/.db-$ts.dump.part"
trap 'rm -f "$tmp" "$DEST"/.files-*.part' EXIT

# consistent snapshot of the whole database (custom format, compressed)
docker compose exec -T postgres pg_dump -U coach -d coach -Fc -Z 6 > "$tmp"
docker compose exec -T postgres pg_restore --list < "$tmp" > /dev/null
[ -s "$tmp" ] || { echo "[backup] empty dump" >&2; exit 1; }
mv "$tmp" "$DEST/hourly/db-$ts.dump"

today=$(date -u +%Y%m%d)
if ! ls "$DEST/daily/" 2>/dev/null | grep -q "^$today"; then
  d="$DEST/daily/$ts"
  mkdir -p "$d"
  cp "$DEST/hourly/db-$ts.dump" "$d/db.dump"
  vol=$(docker volume inspect -f '{{.Mountpoint}}' coach-bot_catalogfiles)
  tar -C "$vol" -czf "$DEST/.files-$ts.part" . && mv "$DEST/.files-$ts.part" "$d/catalog-files.tar.gz"
  tar -C "$APP_DIR" -czf "$d/config.tar.gz" .env .env.live deploy/trusted-proxies.conf
  (cd "$d" && sha256sum ./* > SHA256SUMS)
  [ "$(date -u +%d)" = "01" ] && cp -a "$d" "$DEST/monthly/$ts"
fi

prune() { ls -1 "$1" | sort | head -n -"$2" | while read -r old; do rm -rf "${1:?}/$old"; done; }
prune "$DEST/hourly" 48
prune "$DEST/daily" 30
prune "$DEST/monthly" 12

if command -v rclone >/dev/null && [ -f /etc/coach-bot/rclone.conf ] && rclone --config /etc/coach-bot/rclone.conf listremotes | grep -q '^offsite:'; then
  rclone --config /etc/coach-bot/rclone.conf sync "$DEST" offsite:coach-bot --exclude '.*' --transfers 2 --quiet
fi
date -u +%FT%TZ > "$DEST/.last-success"
echo "[backup] ok db-$ts.dump ($(du -h "$DEST/hourly/db-$ts.dump" | cut -f1))"
