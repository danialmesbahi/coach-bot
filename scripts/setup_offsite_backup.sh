#!/usr/bin/env bash
# One-time setup of the encrypted off-site backup in ArvanCloud Object Storage.
#   sudo bash scripts/setup_offsite_backup.sh
# Asks for the bucket details (the secret key is typed hidden and never printed), generates a
# random encryption password, writes /etc/coach-bot/rclone.conf (root only) and tests a round trip.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo"; exit 1; }
command -v rclone >/dev/null || apt-get install -y -qq rclone
mkdir -p /etc/coach-bot && chmod 700 /etc/coach-bot
CONF=/etc/coach-bot/rclone.conf

echo "ArvanCloud > Object Storage: create a PRIVATE bucket and an access key first."
read -r -p "Endpoint (for example s3.ir-thr-at1.arvanstorage.ir): " endpoint
read -r -p "Bucket name: " bucket
read -r -p "Access key: " access
read -r -s -p "Secret key (hidden): " secret; echo
endpoint=${endpoint#https://}; endpoint=${endpoint%/}
[ -n "$endpoint" ] && [ -n "$bucket" ] && [ -n "$access" ] && [ -n "$secret" ] || { echo "All four values are required."; exit 1; }

pass=$(openssl rand -base64 33 | tr -d '\n')
salt=$(openssl rand -base64 33 | tr -d '\n')
umask 077
cat > "$CONF" <<EOF
[arvan]
type = s3
provider = Other
endpoint = https://$endpoint
access_key_id = $access
secret_access_key = $secret
acl = private
no_check_bucket = true

[offsite]
type = crypt
remote = arvan:$bucket/coach-bot
filename_encryption = standard
directory_name_encryption = true
password = $(rclone obscure "$pass")
password2 = $(rclone obscure "$salt")
EOF
chmod 600 "$CONF"

echo "Testing upload, read-back and delete..."
probe=$(mktemp)
date -u > "$probe"
rclone --config "$CONF" copyto "$probe" offsite:.probe
rclone --config "$CONF" cat offsite:.probe | cmp -s - "$probe" || { echo "Round trip FAILED: check endpoint, bucket and keys."; exit 1; }
rclone --config "$CONF" deletefile offsite:.probe
rm -f "$probe"
echo "Off-site backup works. Files in the bucket are encrypted."

cat <<EOF

================  SAVE THIS SOMEWHERE SAFE, OFF THIS SERVER  ================
Without these two values the encrypted backups cannot be read if the server is lost.
  bucket   : $bucket ($endpoint), folder coach-bot
  password : $pass
  salt     : $salt
============================================================================
EOF

echo "Running the first backup now (the first upload of files can take a while)..."
systemctl start coach-bot-backup.service 2>/dev/null && journalctl -u coach-bot-backup -n 2 -o cat --no-pager || bash "$(dirname "$0")/backup.sh"
