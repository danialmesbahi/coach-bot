#!/usr/bin/env bash
# Installs the pull-based auto deploy (systemd timer, every minute). Run once: sudo bash scripts/install_auto_deploy.sh
# Logs: journalctl -u coach-bot-deploy -n 50     Stop: systemctl disable --now coach-bot-deploy.timer
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo"; exit 1; }

cat > /etc/systemd/system/coach-bot-deploy.service <<UNIT
[Unit]
Description=Deploy coach-bot from the GitHub deploy branch
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$(pwd)
ExecStart=/bin/bash $(pwd)/scripts/auto_deploy.sh
TimeoutStartSec=1800
UNIT

cat > /etc/systemd/system/coach-bot-deploy.timer <<'UNIT'
[Unit]
Description=Check for a new coach-bot release every minute

[Timer]
OnBootSec=2min
OnUnitInactiveSec=1min
AccuracySec=10s

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now coach-bot-deploy.timer
systemctl list-timers coach-bot-deploy.timer --no-pager
