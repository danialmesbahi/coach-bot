#!/usr/bin/env bash
# Run by coach-bot-health.timer every 5 minutes. The checks, Telegram alerts and the daily
# report live in scripts/monitor.py.
exec /usr/bin/python3 "$(dirname "$0")/monitor.py" check
