#!/usr/bin/env bash
# Every 5 minutes (coach-bot-health.timer): checks the platform and sends a Telegram alert
# to the first PLATFORM_TEAM_IDS owner when something breaks, again every 6 hours while it
# stays broken, and once more when it recovers.
set -uo pipefail
cd /opt/coach-bot
STATE=/var/lib/coach-bot-health
mkdir -p "$STATE"

problems=()
check_url() { curl -fsS --max-time 15 -o /dev/null "$1" || problems+=("$2 is not answering ($1)"); }
check_url https://sensibot.ir/robots.txt "Landing page"
check_url https://apanel.sensibot.ir/health "Staff panel / API"

for svc in postgres redis bot web-api web site ingress; do
  state=$(docker compose ps --format '{{.State}}' "$svc" 2>/dev/null)
  [ "$state" = "running" ] || problems+=("Container $svc is ${state:-missing}")
done

disk=$(df --output=pcent / | tail -1 | tr -dc 0-9)
[ "$disk" -ge 85 ] && problems+=("Disk is ${disk}% full")
mem=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
[ "$mem" -lt 200 ] && problems+=("Only ${mem} MB of memory available")

cert=/etc/letsencrypt/live/sensibot.ir/fullchain.pem
[ -f "$cert" ] && ! openssl x509 -checkend $((14*86400)) -noout -in "$cert" >/dev/null && problems+=("HTTPS certificate expires within 14 days")

last=$(cat /var/backups/coach-bot/.last-success 2>/dev/null)
if [ -z "$last" ] || [ $(( $(date +%s) - $(date -d "$last" +%s) )) -gt 7200 ]; then
  problems+=("No successful backup in the last 2 hours (last: ${last:-never})")
fi
if [ ! -f /etc/coach-bot/rclone.conf ]; then
  problems+=("Off-site backup is not configured: backups exist only on this server (run scripts/setup_offsite_backup.sh)")
else
  off=$(cat /var/backups/coach-bot/.last-offsite 2>/dev/null)
  if [ -z "$off" ] || [ $(( $(date +%s) - $(date -d "$off" +%s) )) -gt 7200 ]; then
    problems+=("No successful off-site backup in the last 2 hours (last: ${off:-never})")
  fi
fi
[ -f /var/lib/coach-bot-deploy/failed ] && problems+=("Last automatic deploy failed and was rolled back (commit $(cut -c1-7 /var/lib/coach-bot-deploy/failed))")

send() {
  local token chat
  token=$(grep -E '^BOT_TOKEN=' .env.live | cut -d= -f2-)
  chat=$(grep -E '^PLATFORM_TEAM_IDS=' .env.live | cut -d= -f2- | cut -d, -f1 | tr -dc 0-9)
  [ -n "$token" ] && [ -n "$chat" ] || return 0
  curl -fsS --max-time 15 "https://api.telegram.org/bot$token/sendMessage" \
    --data-urlencode "chat_id=$chat" --data-urlencode "text=$1" >/dev/null || true
}

now=$(date +%s)
if [ ${#problems[@]} -gt 0 ]; then
  summary=$(printf '• %s\n' "${problems[@]}")
  prev=$(cat "$STATE/summary" 2>/dev/null)
  last_sent=$(cat "$STATE/sent" 2>/dev/null || echo 0)
  if [ "$summary" != "$prev" ] || [ $((now - last_sent)) -gt 21600 ]; then
    send "🚨 Sensi server alert
$summary"
    echo "$summary" > "$STATE/summary"; echo "$now" > "$STATE/sent"
  fi
  echo "$summary"
  exit 1
elif [ -f "$STATE/summary" ]; then
  send "✅ Sensi server recovered: all checks pass again."
  rm -f "$STATE/summary" "$STATE/sent"
fi
