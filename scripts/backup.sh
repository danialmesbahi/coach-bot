#!/usr/bin/env bash
# Hourly backup, run by coach-bot-backup.timer (installed by scripts/harden_server.sh).
# The server disk is small, so backups live OFF the server (rclone remote "offsite",
# configured by scripts/setup_offsite_backup.sh, encrypted with rclone crypt):
#   offsite:db/hourly/    database dump every hour, kept 7 days
#   offsite:db/daily/     first dump of each day, kept 90 days
#   offsite:db/monthly/   first dump of each month, kept 2 years
#   offsite:files/current uploaded catalog files, synced incrementally (each file uploaded once)
#   offsite:files/history files deleted or replaced on the server, kept 30 days
#   offsite:config/       .env files and trusted proxies, daily, kept 90 days
# On the server only the newest 6 dumps are kept (fast restore). Every dump is verified with
# pg_restore before it is kept or uploaded.
set -euo pipefail
APP_DIR=/opt/coach-bot
DEST=/var/backups/coach-bot
RCLONE=(rclone --config /etc/coach-bot/rclone.conf --quiet)
cd "$APP_DIR"
umask 077
mkdir -p "$DEST/local"
exec 9>/run/coach-bot-backup.lock
flock -n 9 || exit 0

ts=$(date -u +%Y%m%dT%H%MZ)
day=$(date -u +%Y%m%d)
month=$(date -u +%Y%m)
tmp="$DEST/.db-$ts.part"
trap 'rm -f "$DEST"/.db-*.part "$DEST"/.config-*.part' EXIT

# 1. consistent, verified database dump
docker compose exec -T postgres pg_dump -U coach -d coach -Fc -Z 6 > "$tmp"
[ -s "$tmp" ] || { echo "[backup] empty dump" >&2; exit 1; }
docker compose exec -T postgres pg_restore --list < "$tmp" > /dev/null
dump="$DEST/local/db-$ts.dump"
mv "$tmp" "$dump"

# 2. keep only a few dumps on the server; fewer when the disk is getting full
keep=6
[ "$(df --output=pcent / | tail -1 | tr -dc 0-9)" -ge 80 ] && keep=2
ls -1 "$DEST/local" | sort | head -n -"$keep" | while read -r old; do rm -f "$DEST/local/$old"; done

# 3. off-site copy
if ! { command -v rclone >/dev/null && [ -f /etc/coach-bot/rclone.conf ] && "${RCLONE[@]}" listremotes | grep -q '^offsite:'; }; then
  echo "[backup] local dump ok ($(du -h "$dump" | cut -f1)); OFF-SITE NOT CONFIGURED (run scripts/setup_offsite_backup.sh)"
  date -u +%FT%TZ > "$DEST/.last-success"
  exit 0
fi

"${RCLONE[@]}" copyto "$dump" "offsite:db/hourly/db-$ts.dump"
"${RCLONE[@]}" lsf "offsite:db/daily/" 2>/dev/null | grep -q "^db-$day" || "${RCLONE[@]}" copyto "$dump" "offsite:db/daily/db-$ts.dump"
"${RCLONE[@]}" lsf "offsite:db/monthly/" 2>/dev/null | grep -q "^db-$month" || "${RCLONE[@]}" copyto "$dump" "offsite:db/monthly/db-$ts.dump"

# uploaded files: incremental; anything removed or replaced on the server moves to history/<date>
vol=$(docker volume inspect -f '{{.Mountpoint}}' coach-bot_catalogfiles)
"${RCLONE[@]}" sync "$vol" offsite:files/current --backup-dir "offsite:files/history/$day" --transfers 4

# server configuration, once a day
if ! "${RCLONE[@]}" lsf offsite:config/ 2>/dev/null | grep -q "^config-$day"; then
  tar -C "$APP_DIR" -czf "$DEST/.config-$ts.part" .env .env.live deploy/trusted-proxies.conf
  "${RCLONE[@]}" copyto "$DEST/.config-$ts.part" "offsite:config/config-$ts.tar.gz"
fi

# off-site retention
"${RCLONE[@]}" delete --min-age 7d offsite:db/hourly
"${RCLONE[@]}" delete --min-age 90d offsite:db/daily
"${RCLONE[@]}" delete --min-age 730d offsite:db/monthly
"${RCLONE[@]}" delete --min-age 90d offsite:config
# history folders are named by the day files left the server (moved files keep their old dates)
cutoff=$(date -u -d '30 days ago' +%Y%m%d)
"${RCLONE[@]}" lsf --dirs-only offsite:files/history 2>/dev/null | while read -r dir; do
  dir=${dir%/}
  if [[ "$dir" =~ ^[0-9]{8}$ && "$dir" < "$cutoff" ]]; then "${RCLONE[@]}" purge "offsite:files/history/$dir"; fi
done

date -u +%FT%TZ > "$DEST/.last-success"
date -u +%FT%TZ > "$DEST/.last-offsite"
echo "[backup] ok db-$ts.dump ($(du -h "$dump" | cut -f1)) + files, copied off-site"
