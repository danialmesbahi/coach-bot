#!/usr/bin/env bash
# Pull-based deploy, run every minute by coach-bot-deploy.timer (see scripts/install_auto_deploy.sh).
# Deploys the `deploy` branch, which GitHub moves only after Checks pass on main.
# Health-checks the result and rolls back to the previous commit if anything fails.
set -euo pipefail

APP_DIR=/opt/coach-bot
BRANCH=deploy
PANEL=apanel.sensibot.ir
cd "$APP_DIR"
exec 9>/run/coach-bot-deploy.lock
flock -n 9 || exit 0

log() { echo "[deploy] $*"; }

git fetch -q origin "$BRANCH"
old=$(git rev-parse HEAD)
new=$(git rev-parse "origin/$BRANCH")
[ "$old" = "$new" ] && exit 0
# a commit that already failed and was rolled back is not retried; the next push is
STATE=/var/lib/coach-bot-deploy
mkdir -p "$STATE"
[ "$(cat "$STATE/failed" 2>/dev/null)" = "$new" ] && exit 0

log "updating $(git log --oneline -1 "$old" | cut -c1-60) -> $(git log --oneline -1 "$new" | cut -c1-60)"
changed=$(git diff --name-only "$old" "$new")

healthy() {
  for _ in $(seq 1 40); do
    if curl -fsS --max-time 3 http://127.0.0.1:8090/health >/dev/null 2>&1 \
      && curl -fsS --max-time 3 http://127.0.0.1:3100/robots.txt >/dev/null 2>&1 \
      && [ -z "$(docker compose ps --status restarting -q)" ]; then
      return 0
    fi
    sleep 3
  done
  return 1
}

apply() {
  docker compose build
  docker compose up -d --remove-orphans
  # the inner ingress caches container addresses; refresh it after containers are recreated
  docker compose restart ingress
}

nginx_sync() {
  local changed_any=0
  for name in http https; do
    src="deploy/nginx-sensibot-$name.conf"
    dst="/etc/nginx/sites-available/sensibot-$name"
    if [ -f "$src" ] && ! cmp -s "$src" "$dst"; then
      cp "$dst" "$dst.prev" 2>/dev/null || true
      cp "$src" "$dst"
      changed_any=1
    fi
  done
  if [ "$changed_any" = 1 ]; then
    if nginx -t 2>/dev/null; then
      systemctl reload nginx && log "host nginx config updated"
    else
      for name in http https; do [ -f "/etc/nginx/sites-available/sensibot-$name.prev" ] && cp "/etc/nginx/sites-available/sensibot-$name.prev" "/etc/nginx/sites-available/sensibot-$name"; done
      log "new host nginx config failed nginx -t; kept the previous one"
    fi
  fi
}

# keep server-only edits (e.g. deploy/trusted-proxies.conf) while moving to the new commit
if ! git merge --ff-only -q "$new"; then
  git checkout -q --detach "$new" 2>/dev/null || { log "cannot move to $new (local edits conflict); deploy skipped"; exit 1; }
fi

if apply && healthy; then
  echo "$changed" | grep -q '^deploy/nginx-sensibot-' && nginx_sync
  rm -f "$STATE/failed"
  date -u +%FT%TZ > "$STATE/last-success"
  docker image prune -f >/dev/null 2>&1 || true
  log "deployed $(git log --oneline -1 | cut -c1-70)"
  curl -fsS --max-time 10 "https://$PANEL/health" >/dev/null 2>&1 || log "warning: https://$PANEL/health did not answer"
  exit 0
fi

log "health check failed; rolling back to $old"
echo "$new" > "$STATE/failed"
docker compose logs --tail=40 bot web-api web site 2>&1 | sed 's/^/[deploy]   /' || true
git checkout -q --detach "$old"
apply || true
healthy && log "rolled back to $(git log --oneline -1 | cut -c1-70)" || log "ROLLBACK ALSO UNHEALTHY: check the server"
exit 1
