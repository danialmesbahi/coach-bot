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
