# Fresh Ubuntu 24.04 launch

This runbook is for a **new** VPS and a **new, empty** PostgreSQL volume. Never apply its product-deletion step to an existing customer database. The local test database and ignored backups are not part of Git and are not copied to the VPS.

## 1. Network and access

- In the provider firewall, allow TCP 22 from your own IP and TCP 80/443 from the Internet. Do not expose 8080, 8090, 5432 or 6379. Keep SSH key login.
- Point an `A` record for the intended panel domain to the VPS IPv4. Use a domain you control; verify DNS before requesting a certificate.
- SSH into the VPS using the username and private key supplied for the image. Keep the key private.
- Install security updates, Git and Nginx. Install Docker Engine and the Compose plugin from the [official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/). Verify `sudo docker compose version`.

## 2. Code and private configuration

Clone the private repository's `main` branch with a **read-only GitHub deploy key**. In the checkout:

```sh
git rev-parse HEAD
cp .env.example .env
cp .env.live.example .env.live
chmod 600 .env .env.live
```

Edit `.env` with independent, random PostgreSQL and Redis passwords. Keep the matching password identical in each service URL. Edit `.env.live` with the real bot token, `SENSI_ID`, one `PLATFORM_TEAM_IDS` entry for the initial owner, the final HTTPS `PUBLIC_BASE_URL`, a random `WEBHOOK_SECRET` of at least 32 characters, `APP_ENV=production`, `WEB_DEV_LOGIN=false`, and a real payment mode. For `PAYMENT_MODE=zarinpal` or `both`, set a valid merchant ID; for card-to-card, set real bank details. Production rejects mock payments. Do not copy local `.env`/`.env.live` to the VPS or commit them.

Before starting the bot, review the configuration without printing secrets:

```sh
sudo docker compose config --quiet
```

## 3. Empty database, closed sales

On a new VPS, start only the data services and apply all schema migrations:

```sh
sudo docker compose up -d postgres redis
sudo docker compose run --rm bot true
```

The first migration seeds three **placeholder-price products**, and another seeds an open sales gate. For this fresh launch, confirm `users` and `orders` both return zero, then remove only the seeded products and close sales before publishing the bot:

```sh
sudo docker compose exec -T postgres psql -U coach -d coach -c 'SELECT count(*) FROM users; SELECT count(*) FROM orders;'
sudo docker compose exec -T postgres psql -U coach -d coach -v ON_ERROR_STOP=1 -c "DELETE FROM products WHERE code IN ('nutrition','training','complete'); UPDATE sales_gate SET is_open=false WHERE id=1;"
```

Do not import any local `.dump`, `seed_demo.sql` or test media. The new database has schema and required system rows, but no customers, orders or saleable products.

## 4. Admin account and HTTPS

Start the API, web UI and inner ingress; leave the bot stopped until the public HTTPS endpoint is ready:

```sh
sudo docker compose up -d --build web-api web ingress
sudo docker compose ps
curl -fsS http://127.0.0.1:8090/health
```

Create a private JSON file containing `{"username":"danial","password":"..."}` under ignored `artifacts/private/` with mode 600. Use an initial password that meets the policy in `docs/STAFF_ACCESS.md`. Initialize the seeded platform owner once, substituting that owner's configured numeric Telegram ID. The JSON goes through standard input; it is not mounted into the container or printed in the command:

```sh
sudo docker compose exec -T web-api python scripts/setup_staff_password.py --telegram-id OWNER_ID --credentials-file - < artifacts/private/initial-login.json
```

For host Nginx, first serve the domain on HTTP/80 and use [Certbot's Nginx instructions](https://certbot.eff.org/instructions?ws=nginx&os=snap) to obtain a certificate. Then install `deploy/nginx.conf.example` as the domain's Nginx site, replacing every `BOT_DOMAIN` with the real hostname. Test with `sudo nginx -t`, reload Nginx and run `sudo certbot renew --dry-run`. The repo's HTTPS edge forwards to the loopback-only Docker ingress; the auto-assigned server hostname alone does not guarantee HTTPS.

Find the host's Docker-facing address for this ingress and set **only that address** in `deploy/trusted-proxies.conf`, then restart ingress:

```sh
sudo docker inspect "$(sudo docker compose ps -q ingress)" --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}'
```

The file must contain one `set_real_ip_from IP;` line. The host Nginx config overwrites `X-Real-IP`; never trust a whole Docker subnet or arbitrary forwarded headers. Confirm `https://YOUR_DOMAIN/health` returns successfully, then start the bot:

```sh
sudo docker compose up -d bot
sudo docker compose ps
sudo docker compose logs --tail=100 bot web-api ingress
```

Sign in, change the temporary admin password and remove its private JSON file. Add products with final prices/content; only then open sales and test one real gateway callback plus Telegram delivery. Check `getWebhookInfo` and the bot log after a `/start` message.

## 5. Recovery and capacity

Keep weekly VPS snapshots and daily PostgreSQL **and catalog-file** backups outside the VPS. Test restoring both. The 30 GB root disk is suitable for initial testing, not an unlimited video library: monitor free space and add storage before accepting large uploads. Build on 4 GB RAM may require temporary swap. The first launch is not evidence of capacity for tens of thousands of simultaneous users; load-test the deployed service before promising that scale.

## 6. Landing page on the main domain

Layout: `sensibot.ir` serves the public site (`site` container, `127.0.0.1:3100`); `www.sensibot.ir` redirects to it; `apanel.sensibot.ir` serves the staff panel through the inner ingress (`127.0.0.1:8090`). The main domain also forwards `/telegram/webhook`, `/payment/zarinpal/callback`, `/content/` and `/health` to the ingress, so `PUBLIC_BASE_URL=https://sensibot.ir` keeps the bot, payments and download links working.

1. DNS (ArvanCloud, CDN proxy off): `A` records `@`, `www` and `apanel` → the VPS IPv4.
2. In the server's `.env` (read by Compose for the `site` build and runtime), set the public identity that must match the eNamad registration: `SITE_URL=https://sensibot.ir`, `BOT_USERNAME`, `BUSINESS_LEGAL_NAME`, `BUSINESS_ADDRESS`, `BUSINESS_POSTAL_CODE`, `BUSINESS_PHONE`, `BUSINESS_EMAIL`, `BUSINESS_HOURS`, and later `ENAMAD_ID`, `ENAMAD_CODE`, `SAMANDEHI_ID`, `SAMANDEHI_P`, `ZARINPAL_TRUST=true`. Empty values fall back to `site/sensi.config.ts`.
3. HTTP first, then the certificate, then HTTPS:

```sh
sudo cp deploy/nginx-sensibot-http.conf /etc/nginx/sites-available/sensibot-http
sudo ln -sf /etc/nginx/sites-available/sensibot-http /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/html -d sensibot.ir -d www.sensibot.ir -d apanel.sensibot.ir
sudo cp deploy/nginx-sensibot-https.conf /etc/nginx/sites-available/sensibot-https
sudo ln -sf /etc/nginx/sites-available/sensibot-https /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

4. Start the site: `sudo docker compose up -d --build site`, then check `curl -fsS http://127.0.0.1:3100/robots.txt` and `https://sensibot.ir`.
5. Move the bot: set `PUBLIC_BASE_URL=https://sensibot.ir` in `.env.live` and run `sudo docker compose up -d bot web-api` (the bot re-registers its webhook on start). Register `https://sensibot.ir` as the website in the ZarinPal merchant panel.

## 7. Automatic deploy

Every push to `main` runs **Checks**; when they pass, the **Release** workflow moves the `deploy` branch to that commit. On the server, `coach-bot-deploy.timer` runs `scripts/auto_deploy.sh` every minute: it fetches `deploy` with the read-only deploy key, rebuilds, restarts the inner ingress, health-checks the panel API and the site, and rolls back to the previous commit if they fail (a failed commit is not retried; push a fix). GitHub holds no server credentials.

- Install once: `sudo bash scripts/install_auto_deploy.sh`
- Logs: `journalctl -u coach-bot-deploy -n 50`
- Pause: `systemctl disable --now coach-bot-deploy.timer`

## 8. Security, backups and monitoring

Apply or re-apply with `sudo bash scripts/harden_server.sh` (idempotent). Configs live in `deploy/server/`.

- **SSH**: keys only (`PasswordAuthentication no`, root by key only), max 3 tries, no forwarding. fail2ban bans an IP for 1 hour after 4 failures and for 1 week if it keeps coming back. If every key is lost, log in through the ArvanCloud web console.
- **Updates**: unattended security updates nightly; if one needs a reboot it happens at 04:00 Tehran. Containers restart by themselves.
- **Edge (host Nginx)**: per-IP limits (site 30 req/s, panel 20 req/s, with bursts; deliberately generous because Iranian carriers share IPs), slow-client timeouts, requests by bare IP or unknown host are dropped, HSTS on the panel. The landing page is cached at the edge for 60 s and served stale if the site container is down; `/_next/static` is cached for 30 days.
- **Containers**: memory limits per service, so a runaway process is restarted on its own instead of exhausting the server. PostgreSQL is tuned for 4 GB.
- **Backups (off-site first, the disk is only 30 GB)**: `coach-bot-backup.timer` every hour. Each database dump is verified with `pg_restore`, the newest 6 stay on the server (`/var/backups/coach-bot/local`), and everything goes to an encrypted rclone `crypt` remote in ArvanCloud Object Storage: database hourly (7 days), daily (90 days) and monthly (2 years); uploaded catalog files synced incrementally, with deleted or replaced files kept 30 days in `files/history`; `.env` files daily. Set it up once with `sudo bash scripts/setup_offsite_backup.sh` and store the printed encryption password and salt somewhere safe off the server; without them the backups cannot be decrypted. Body photos and delivered plans are Telegram file references, so they are not on the disk.
- **Daily Telegram copy**: once a day (about 03:30 Tehran) the bot sends the owner (first `PLATFORM_TEAM_IDS`, who must have started the bot) a 7z archive of the database and server config, AES-256 with encrypted file names, split into 45 MB parts if needed. The password is generated by `harden_server.sh`, printed once, and kept in `/etc/coach-bot/backup-archive.pass`; save it off the server. Open the archive with 7-Zip.
- **Restore**: `sudo bash scripts/restore_backup.sh` lists server and off-site backups; pass one of the listed paths to restore it. A safety dump of the current database is taken first.
- **Monitoring** (`scripts/monitor.py`, every 5 minutes via `coach-bot-health.timer`): samples CPU, RAM, swap, disk, network, the compact Nginx log `/var/log/nginx/coach-access.log` (requests, 429s, 5xx, top IPs), SSH failures and fail2ban bans, keeping 8 days of 5-minute history. It alerts the first `PLATFORM_TEAM_IDS` owner on Telegram, with a status snapshot and a redacted log file, when a site or container fails or restarts, CPU stays above 85% or free RAM below 10% for 10 minutes, swap passes 60%, the disk passes 85%/92%, more than 300 requests in 5 minutes are rate-limited (likely flood), 5xx errors spike, SSH is hammered, the certificate nears expiry, or a backup or deploy fails. It repeats every 6 hours while a problem lasts and confirms recovery. A daily report (server, traffic, security, backups, business numbers, plus the day's logs) is sent after 08:00 Tehran. `python3 scripts/monitor.py report` sends one now; `status` prints the latest sample.
