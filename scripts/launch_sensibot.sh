#!/usr/bin/env bash
# One-shot, re-runnable launch of the landing page on sensibot.ir and the panel on apanel.sensibot.ir.
# Run from the project checkout on the server:  sudo bash scripts/launch_sensibot.sh
# Every step checks its result and stops on the first problem; running it again is safe.
set -euo pipefail

MAIN=sensibot.ir
PANEL=apanel.sensibot.ir
DOMAINS=("$MAIN" "www.$MAIN" "$PANEL")
cd "$(dirname "$0")/.."

say() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
ok() { printf '\033[1;32m    OK\033[0m %s\n' "$*"; }
die() { printf '\n\033[1;31m!! %s\033[0m\n' "$*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run with sudo: sudo bash scripts/launch_sensibot.sh"

say "1/9 Latest code from GitHub"
OWNER=$(stat -c %U .)
sudo -u "$OWNER" git pull --ff-only
ok "$(git log --oneline -1)"

say "2/9 DNS must point straight at this server (ArvanCloud cloud/CDN switch OFF)"
MYIP=$(curl -fsS --max-time 10 https://api.ipify.org || true)
[ -n "$MYIP" ] || die "Could not detect this server's public IP"
for d in "${DOMAINS[@]}"; do
  ips=$(getent ahostsv4 "$d" | awk '{print $1}' | sort -u | tr '\n' ' ')
  [[ " $ips " == *" $MYIP "* ]] || die "$d resolves to [$ips], not $MYIP. Turn OFF the cloud switch for this record in ArvanCloud DNS, wait 2 minutes, run again."
  ok "$d -> $MYIP"
done

say "3/9 Memory for building (adds a 2 GB swap file once if the server has none)"
if [ "$(swapon --show --noheadings | wc -l)" -eq 0 ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  ok "swap enabled"
else
  ok "swap already present"
fi

say "4/9 Build and start all containers (site is new; the bot applies DB migrations on start)"
docker compose build site
docker compose up -d --build
for i in $(seq 1 60); do
  curl -fsS --max-time 3 http://127.0.0.1:3100/robots.txt >/dev/null 2>&1 && break
  sleep 3
  [ "$i" -eq 60 ] && { docker compose logs --tail=60 site; die "site container did not become ready"; }
done
ok "site answers on 127.0.0.1:3100"
curl -fsS --max-time 5 http://127.0.0.1:8090/health >/dev/null || die "panel ingress (127.0.0.1:8090) is not healthy"
ok "panel ingress healthy"

say "5/9 Nginx: HTTP + certificate challenge"
mkdir -p /var/www/html
cp deploy/nginx-sensibot-http.conf /etc/nginx/sites-available/sensibot-http
ln -sf /etc/nginx/sites-available/sensibot-http /etc/nginx/sites-enabled/sensibot-http
nginx -t && systemctl reload nginx
ok "HTTP config live"

say "6/9 HTTPS certificate for ${DOMAINS[*]}"
certbot certonly --webroot -w /var/www/html --non-interactive --agree-tos --register-unsafely-without-email \
  --keep-until-expiring --expand --cert-name "$MAIN" -d "$MAIN" -d "www.$MAIN" -d "$PANEL"
ok "certificate ready"

say "7/9 Nginx: HTTPS sites"
cp deploy/nginx-sensibot-https.conf /etc/nginx/sites-available/sensibot-https
ln -sf /etc/nginx/sites-available/sensibot-https /etc/nginx/sites-enabled/sensibot-https
nginx -t && systemctl reload nginx
sleep 2
curl -fsS --max-time 10 "https://$MAIN/robots.txt" >/dev/null || die "https://$MAIN is not answering"
ok "https://$MAIN"
curl -fsS --max-time 10 "https://$PANEL/health" >/dev/null || die "https://$PANEL is not answering"
ok "https://$PANEL"
curl -fsS --max-time 10 -o /dev/null -w '%{http_code}' "https://www.$MAIN/" | grep -q '^30' && ok "www redirects to $MAIN"

say "8/9 Bot address (Telegram webhook, ZarinPal callback, download links)"
current=$(grep -E '^PUBLIC_BASE_URL=' .env.live | cut -d= -f2- || true)
if [ "$current" = "https://$MAIN" ]; then
  ok "PUBLIC_BASE_URL already https://$MAIN"
else
  echo "    Current PUBLIC_BASE_URL: ${current:-<empty>}"
  read -r -p "    Move the bot to https://$MAIN now? The ZarinPal merchant website must be $MAIN. [y/N] " answer
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    cp .env.live ".env.live.bak.$(date +%Y%m%d%H%M%S)"
    if grep -qE '^PUBLIC_BASE_URL=' .env.live; then
      sed -i "s#^PUBLIC_BASE_URL=.*#PUBLIC_BASE_URL=https://$MAIN#" .env.live
    else
      echo "PUBLIC_BASE_URL=https://$MAIN" >> .env.live
    fi
    grep -qE '^ZARINPAL_CALLBACK_URL=.+' .env.live && echo "    NOTE: ZARINPAL_CALLBACK_URL is set explicitly in .env.live; update it to https://$MAIN/payment/zarinpal/callback if it still uses the old domain."
    docker compose up -d --force-recreate bot web-api
    sleep 8
    docker compose logs --tail=20 bot
    ok "bot moved to https://$MAIN"
  else
    echo "    Skipped. The bot keeps its current address; run this script again to move it later."
  fi
fi

say "9/9 Retire the old panel address (sensibot.danimes.ir)"
OLD=sensibot.danimes.ir
base=$(grep -E '^PUBLIC_BASE_URL=' .env.live | cut -d= -f2- || true)
callback=$(grep -E '^ZARINPAL_CALLBACK_URL=' .env.live | cut -d= -f2- || true)
if [ "$base" != "https://$MAIN" ] || [[ "$callback" == *danimes* ]]; then
  echo "    Skipped: the bot still uses the old address (PUBLIC_BASE_URL=${base:-<empty>}${callback:+, ZARINPAL_CALLBACK_URL=$callback})."
  echo "    Move the bot first (step 8), then run this script again."
else
  mkdir -p /etc/nginx/disabled-sites
  for f in /etc/nginx/sites-enabled/*; do
    [ -e "$f" ] || continue
    grep -q "${OLD//./\\.}" "$f" || continue
    names=$(grep -hE '^\s*server_name' "$f" | sed -E 's/^\s*server_name\s+//; s/;.*//' | tr ' \t' '\n\n' | grep -v '^$' | sort -u | tr '\n' ' ')
    if [ "$names" = "$OLD " ]; then
      mv "$f" /etc/nginx/disabled-sites/
      ok "disabled Nginx site $(basename "$f") (kept in /etc/nginx/disabled-sites)"
    else
      echo "    Not touching $f: it also serves [$names]. Remove the $OLD server block from it by hand."
    fi
  done
  nginx -t && systemctl reload nginx
  if certbot certificates 2>/dev/null | grep -q "Certificate Name: $OLD\$"; then
    certbot delete --non-interactive --cert-name "$OLD"
    ok "removed the $OLD certificate (no more renewals)"
  fi
  ok "$OLD is no longer served. Also delete its DNS record (sensibot in the danimes.ir zone) in ArvanCloud."
fi

say "Done"
docker compose ps
echo
echo "  Landing page : https://$MAIN"
echo "  Staff panel  : https://$PANEL"
