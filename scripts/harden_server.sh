#!/usr/bin/env bash
# Server hardening, backups and monitoring. Idempotent; run from the checkout:
#   sudo bash scripts/harden_server.sh
set -euo pipefail
cd "$(dirname "$0")/.."
APP=$(pwd)
S=deploy/server
say() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
ok() { printf '\033[1;32m    OK\033[0m %s\n' "$*"; }
die() { printf '\n\033[1;31m!! %s\033[0m\n' "$*"; exit 1; }
[ "$(id -u)" -eq 0 ] || die "Run with sudo"

say "1/8 Security updates and tools"
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
apt-get update -qq
apt-get -y -qq -o Dpkg::Options::=--force-confold upgrade >/dev/null
apt-get -y -qq install fail2ban rclone unattended-upgrades >/dev/null
cp $S/auto-upgrades.conf /etc/apt/apt.conf.d/52coach-auto-reboot
ok "system up to date; nightly security updates with 04:00 reboot when needed"

say "2/8 SSH: keys only"
keys=$(grep -cE '^(ssh-(ed25519|rsa)|ecdsa-)' /root/.ssh/authorized_keys 2>/dev/null || true)
[ "${keys:-0}" -ge 1 ] || die "No SSH key in /root/.ssh/authorized_keys; refusing to disable passwords"
cp $S/sshd-hardening.conf /etc/ssh/sshd_config.d/00-coach-hardening.conf
sshd -t || { rm -f /etc/ssh/sshd_config.d/00-coach-hardening.conf; die "sshd config test failed; nothing changed"; }
systemctl reload ssh
[ "$(sshd -T | awk '/^passwordauthentication/ {print $2}')" = "no" ] || die "password login still enabled"
ok "password and keyboard logins off ($keys authorized key(s)); recovery via ArvanCloud web console"

say "3/8 Brute-force protection (fail2ban)"
cp $S/fail2ban-jail.local /etc/fail2ban/jail.local
touch /var/log/fail2ban.log
systemctl enable -q fail2ban && systemctl restart fail2ban
sleep 2
fail2ban-client status sshd | grep -E "Currently banned|Total banned" | sed 's/^/    /'

say "4/8 Kernel network hardening"
cp $S/sysctl-coach.conf /etc/sysctl.d/90-coach.conf
sysctl -q --system
ok "sysctl applied"

say "5/8 Nginx edge: rate limits, caching, unknown hosts dropped"
mkdir -p /var/cache/nginx/sensi /etc/nginx/coach-backup
cp -a /etc/nginx/sites-enabled /etc/nginx/coach-backup/sites-enabled.$(date +%s)
cp /etc/nginx/nginx.conf /etc/nginx/coach-backup/nginx.conf.prev
cp $S/nginx-edge.conf /etc/nginx/conf.d/coach-edge.conf
cp $S/nginx-default.conf /etc/nginx/sites-available/coach-default
cp deploy/nginx-sensibot-http.conf /etc/nginx/sites-available/sensibot-http
cp deploy/nginx-sensibot-https.conf /etc/nginx/sites-available/sensibot-https
ln -sf /etc/nginx/sites-available/coach-default /etc/nginx/sites-enabled/coach-default
rm -f /etc/nginx/sites-enabled/default
sed -i 's/worker_connections [0-9]*;/worker_connections 4096;/' /etc/nginx/nginx.conf
grep -q '^worker_rlimit_nofile' /etc/nginx/nginx.conf || sed -i 's/^worker_processes.*/&\nworker_rlimit_nofile 16384;/' /etc/nginx/nginx.conf
if nginx -t 2>/dev/null; then
  systemctl reload nginx
  ok "nginx reloaded"
else
  nginx -t || true
  rm -f /etc/nginx/conf.d/coach-edge.conf /etc/nginx/sites-enabled/coach-default
  ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default
  cp /etc/nginx/coach-backup/nginx.conf.prev /etc/nginx/nginx.conf
  die "nginx test failed; previous nginx config restored"
fi

say "6/8 Backups every hour (verified), restore with scripts/restore_backup.sh"
mkdir -p /etc/coach-bot && chmod 700 /etc/coach-bot
cat > /etc/systemd/system/coach-bot-backup.service <<UNIT
[Unit]
Description=Back up the coach-bot database and files
After=docker.service
[Service]
Type=oneshot
ExecStart=/bin/bash $APP/scripts/backup.sh
TimeoutStartSec=1800
UNIT
cat > /etc/systemd/system/coach-bot-backup.timer <<'UNIT'
[Unit]
Description=Hourly coach-bot backup
[Timer]
OnCalendar=hourly
RandomizedDelaySec=120
Persistent=true
[Install]
WantedBy=timers.target
UNIT

say "7/8 Monitoring with Telegram alerts every 5 minutes"
cat > /etc/systemd/system/coach-bot-health.service <<UNIT
[Unit]
Description=coach-bot health check and Telegram alerts
[Service]
Type=oneshot
ExecStart=/bin/bash $APP/scripts/healthwatch.sh
UNIT
cat > /etc/systemd/system/coach-bot-health.timer <<'UNIT'
[Unit]
Description=coach-bot health check every 5 minutes
[Timer]
OnBootSec=3min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable -q --now coach-bot-backup.timer coach-bot-health.timer

say "8/8 First backup and health check"
systemctl start coach-bot-backup.service && journalctl -u coach-bot-backup -n 1 -o cat --no-pager | sed 's/^/    /'
ls -lh /var/backups/coach-bot/daily/*/ | sed 's/^/    /'
systemctl start coach-bot-health.service && ok "all health checks pass" || echo "    health check reported problems (see above)"

echo
[ -f /var/run/reboot-required ] && echo "NOTE: updates need a reboot; it will happen automatically at 04:00 Tehran time (or run: sudo reboot)"
systemctl list-timers 'coach-bot-*' --no-pager
