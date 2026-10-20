#!/usr/bin/env python3
"""Sensi server monitor (stdlib only, runs as root on the server).

  monitor.py check    every 5 minutes (coach-bot-health.timer via healthwatch.sh): samples the
                      server, sends a Telegram alert with a status snapshot and a log file when
                      something goes wrong, and sends the daily report once a day after 08:00 Tehran.
  monitor.py report   send the daily report now.
  monitor.py status   print the current status (no Telegram).

Alerts go to the first PLATFORM_TEAM_IDS owner through the bot. History: 5-minute samples for
8 days in /var/lib/coach-bot-health/metrics.jsonl.
"""
import collections, datetime as dt, gzip, json, os, re, shutil, subprocess, sys, time, urllib.request, uuid

APP = '/opt/coach-bot'
STATE = '/var/lib/coach-bot-health'
METRICS = f'{STATE}/metrics.jsonl'
STATEFILE = f'{STATE}/state.json'
ACCESS = '/var/log/nginx/coach-access.log'
BACKUPS = '/var/backups/coach-bot'
TEHRAN = dt.timezone(dt.timedelta(hours=3, minutes=30))
SERVICES = ['postgres', 'redis', 'bot', 'web-api', 'web', 'site', 'ingress']
URLS = {'سایت': 'https://sensibot.ir/robots.txt', 'پنل': 'https://apanel.sensibot.ir/health'}
# The public URLs go out through ArvanCloud's CDN; the origin tells a CDN hiccup from a real outage.
ORIGINS = {'سایت': 'http://127.0.0.1:3100/robots.txt'}
REPORT_HOUR = 8
REPEAT_SECONDS = 6 * 3600

# alert thresholds (per 5-minute sample)
CPU_PCT = 85            # sustained for two samples
MEM_FREE_PCT = 10       # available memory, sustained for two samples
SWAP_PCT = 60
DISK_WARN, DISK_CRIT = 85, 92
RATE_LIMITED = 300      # 429 responses in 5 minutes: likely a flood or scraper
ERRORS_5XX = 30
SSH_FAILED = 500
TRAFFIC = 9000          # requests in 5 minutes (30 per second sustained)


def sh(cmd, timeout=60):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=APP).stdout.strip()
    except Exception:
        return ''


def env_live():
    out = {}
    try:
        for line in open(f'{APP}/.env.live', encoding='utf-8'):
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.rstrip('\n').split('=', 1)
                out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def load_state():
    try:
        return json.load(open(STATEFILE))
    except Exception:
        return {}


def save_state(s):
    tmp = STATEFILE + '.tmp'
    json.dump(s, open(tmp, 'w'))
    os.replace(tmp, STATEFILE)


# ---------- Telegram ----------

def telegram(method, fields, filename=None, data=None):
    env = env_live()
    token = env.get('BOT_TOKEN', '')
    chat = re.sub(r'\D', '', env.get('PLATFORM_TEAM_IDS', '').split(',')[0])
    if not token or not chat:
        return False
    fields = {'chat_id': chat, **fields}
    boundary = uuid.uuid4().hex
    body = bytearray()
    for k, v in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    if filename:
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
        body += data + b'\r\n'
    body += f'--{boundary}--\r\n'.encode()
    req = urllib.request.Request(f'https://api.telegram.org/bot{token}/{method}', data=bytes(body),
                                 headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r).get('ok', False)
    except Exception as exc:
        print(f'telegram {method} failed: {exc}', file=sys.stderr)
        return False


def send_text(text):
    for i in range(0, len(text), 4000):
        telegram('sendMessage', {'text': text[i:i + 4000]})


# ---------- sampling ----------

def read_proc_stat():
    parts = open('/proc/stat').readline().split()[1:]
    vals = list(map(int, parts))
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
    return sum(vals), idle


def meminfo():
    m = {}
    for line in open('/proc/meminfo'):
        k, v = line.split(':', 1)
        m[k] = int(v.split()[0]) * 1024
    return m


def net_bytes(iface='eth0'):
    for line in open('/proc/net/dev'):
        if line.strip().startswith(iface + ':'):
            f = line.split(':', 1)[1].split()
            return int(f[0]), int(f[8])
    return 0, 0


def parse_access(lines):
    """coach log format: msec|host|status|request_time|bytes|ip|method|uri|cache"""
    c = {'req': 0, 'site': 0, 'panel': 0, 's4': 0, 's429': 0, 's5': 0, 'bytes': 0, 'rt': 0.0, 'hit': 0, 'cacheable': 0}
    ips, limited = collections.Counter(), collections.Counter()
    for line in lines:
        f = line.rstrip('\n').split('|')
        if len(f) < 9:
            continue
        try:
            status = int(f[2])
            c['rt'] += float(f[3] or 0)
            c['bytes'] += int(f[4] or 0)
        except ValueError:
            continue
        c['req'] += 1
        if f[1].startswith('apanel.'):
            c['panel'] += 1
        else:
            c['site'] += 1
        if f[8] in ('HIT', 'MISS', 'EXPIRED', 'STALE', 'UPDATING', 'REVALIDATED'):
            c['cacheable'] += 1
            c['hit'] += f[8] in ('HIT', 'STALE', 'UPDATING')
        if status == 429:
            c['s429'] += 1
            limited[f[5]] += 1
        elif 400 <= status < 500:
            c['s4'] += 1
        elif status >= 500:
            c['s5'] += 1
        ips[f[5]] += 1
    return c, ips, limited


def new_access_lines(state):
    try:
        st = os.stat(ACCESS)
    except OSError:
        return []
    if 'log_inode' not in state:
        # first run: start at the end so old history is not counted as one 5-minute burst
        state['log_inode'], state['log_pos'] = st.st_ino, st.st_size
        return []
    pos = state.get('log_pos', 0) if state.get('log_inode') == st.st_ino else 0
    if pos > st.st_size:
        pos = 0
    with open(ACCESS, encoding='utf-8', errors='replace') as fh:
        fh.seek(pos)
        lines = fh.readlines()
        state['log_pos'] = fh.tell()
    state['log_inode'] = st.st_ino
    return lines


def banned_total():
    total = 0
    for jail in ('sshd', 'recidive'):
        m = re.search(r'Total banned:\s*(\d+)', sh(f'fail2ban-client status {jail}'))
        total += int(m.group(1)) if m else 0
    return total


def containers():
    out = {}
    ids = sh('docker compose ps -aq').split()
    if not ids:
        return out
    fmt = '{{index .Config.Labels "com.docker.compose.service"}}|{{.State.Status}}|{{.RestartCount}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}|{{.State.StartedAt}}'
    for line in sh(f"docker inspect --format '{fmt}' {' '.join(ids)}").splitlines():
        svc, status, restarts, health, started = (line.split('|') + [''] * 5)[:5]
        out[svc] = {'status': status, 'restarts': int(restarts or 0), 'health': health, 'started': started[:19]}
    return out


def sample(state):
    now = time.time()
    total, idle = read_proc_stat()
    prev = state.get('cpu')
    cpu = None
    if prev and total > prev[0]:
        cpu = round(100 * (1 - (idle - prev[1]) / (total - prev[0])), 1)
    state['cpu'] = [total, idle]

    m = meminfo()
    mem_pct = round(100 * (1 - m['MemAvailable'] / m['MemTotal']), 1)
    swap_pct = round(100 * (1 - m['SwapFree'] / m['SwapTotal']), 1) if m.get('SwapTotal') else 0.0
    du = shutil.disk_usage('/')
    rx, tx = net_bytes()
    prx, ptx = state.get('net', [rx, tx])
    state['net'] = [rx, tx]

    acc, ips, limited = parse_access(new_access_lines(state))
    since = int(state.get('last_ts', now - 300))
    ssh_failed = int(sh(f"journalctl -u ssh --since @{since} --no-pager -o cat | grep -cE 'Invalid user|Failed (password|publickey)|maximum authentication attempts'") or 0)
    bans = banned_total()
    new_bans = max(0, bans - state.get('bans', bans))
    state['bans'] = bans
    state['last_ts'] = int(now)

    s = {
        'ts': int(now), 'cpu': cpu, 'load': float(open('/proc/loadavg').read().split()[0]),
        'mem': mem_pct, 'mem_free_mb': m['MemAvailable'] // 2**20, 'swap': swap_pct,
        'disk': round(100 * du.used / du.total, 1), 'disk_free_gb': round(du.free / 2**30, 1),
        'rx': max(0, rx - prx), 'tx': max(0, tx - ptx), **acc,
        'uniq': len(ips), 'top': ips.most_common(3), 'limited_top': limited.most_common(3),
        'ssh_failed': ssh_failed, 'bans': new_bans,
    }
    with open(METRICS, 'a') as fh:
        fh.write(json.dumps(s) + '\n')
    return s


def history(seconds):
    cutoff = time.time() - seconds
    rows = []
    try:
        for line in open(METRICS):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r['ts'] >= cutoff:
                rows.append(r)
    except OSError:
        pass
    return rows


def prune_history():
    keep = history(8 * 86400)
    tmp = METRICS + '.tmp'
    with open(tmp, 'w') as fh:
        for r in keep:
            fh.write(json.dumps(r) + '\n')
    os.replace(tmp, METRICS)


# ---------- checks ----------

def url_ok(url, attempts=2):
    # one retry: a single dropped request through the CDN is not an outage
    for attempt in range(attempts):
        if attempt:
            time.sleep(5)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'sensi-monitor'}), timeout=15) as r:
                if 200 <= r.status < 400:
                    return True
        except Exception:
            pass
    return False


def file_text(path):
    try:
        return open(path).read().strip()
    except OSError:
        return ''


def age_seconds(stamp):
    try:
        return time.time() - dt.datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()
    except Exception:
        return None


def problems_now(s, prev, state):
    found = {}

    def add(key, text):
        found[key] = text

    for name, url in URLS.items():
        if not url_ok(url):
            origin = ORIGINS.get(name)
            if origin and url_ok(origin, attempts=1):
                add(f'url:{name}', f'{name} از مسیر CDN آروان جواب نمی‌دهد، ولی خود سرور سالم است ({url})')
            else:
                add(f'url:{name}', f'{name} جواب نمی‌دهد ({url})')
    cont = containers()
    old = state.get('containers', {})
    for svc in SERVICES:
        c = cont.get(svc)
        if not c or c['status'] != 'running':
            add(f'down:{svc}', f'کانتینر {svc} اجرا نمی‌شود ({c["status"] if c else "وجود ندارد"})')
        elif c['health'] == 'unhealthy':
            add(f'unhealthy:{svc}', f'کانتینر {svc} ناسالم است')
        if c and svc in old and c['restarts'] > old[svc]['restarts']:
            add(f'restart:{svc}', f'کانتینر {svc} ری‌استارت شد ({c["restarts"] - old[svc]["restarts"]} بار در ۵ دقیقه اخیر)')
    state['containers'] = cont

    if s['cpu'] is not None and s['cpu'] >= CPU_PCT and prev and (prev.get('cpu') or 0) >= CPU_PCT:
        add('cpu', f'پردازنده بیش از ۱۰ دقیقه زیر فشار است ({s["cpu"]}٪)')
    if 100 - s['mem'] <= MEM_FREE_PCT and prev and 100 - prev.get('mem', 0) <= MEM_FREE_PCT:
        add('mem', f'حافظه رم رو به اتمام است (فقط {s["mem_free_mb"]} مگابایت آزاد)')
    if s['swap'] >= SWAP_PCT:
        add('swap', f'سرور از حافظه کمکی (swap) زیاد استفاده می‌کند ({s["swap"]}٪)؛ رم کم است')
    if s['disk'] >= DISK_CRIT:
        add('disk', f'دیسک تقریباً پر است: {s["disk"]}٪ (فقط {s["disk_free_gb"]} گیگ آزاد)')
    elif s['disk'] >= DISK_WARN:
        add('disk', f'دیسک رو به پر شدن است: {s["disk"]}٪ ({s["disk_free_gb"]} گیگ آزاد)')
    if s['s429'] >= RATE_LIMITED:
        who = '، '.join(f'{ip} ({n})' for ip, n in s['limited_top'])
        add('flood', f'احتمال حمله: {s["s429"]} درخواست در ۵ دقیقه به سقف مجاز خورد و رد شد. بیشترین: {who}')
    if s['req'] >= TRAFFIC:
        add('traffic', f'ترافیک خیلی بالا: {s["req"]} درخواست در ۵ دقیقه')
    if s['s5'] >= ERRORS_5XX:
        add('5xx', f'{s["s5"]} خطای سرور (5xx) در ۵ دقیقه اخیر')
    if s['ssh_failed'] >= SSH_FAILED:
        add('ssh', f'حمله حدس رمز به SSH: {s["ssh_failed"]} تلاش ناموفق در ۵ دقیقه (ورود فقط با کلید ممکن است؛ fail2ban مسدود می‌کند)')

    cert = '/etc/letsencrypt/live/sensibot.ir/fullchain.pem'
    if os.path.exists(cert) and sh(f'openssl x509 -checkend {14 * 86400} -noout -in {cert} >/dev/null && echo ok') != 'ok':
        add('cert', 'گواهی HTTPS کمتر از ۱۴ روز دیگر منقضی می‌شود')
    a = age_seconds(file_text(f'{BACKUPS}/.last-success'))
    if a is None or a > 7200:
        add('backup', 'در ۲ ساعت گذشته هیچ بکاپ موفقی گرفته نشده')
    if os.path.exists('/etc/coach-bot/rclone.conf'):
        a = age_seconds(file_text(f'{BACKUPS}/.last-offsite'))
        if a is None or a > 7200:
            add('offsite', 'بکاپ بیرونی (فضای ابری) در ۲ ساعت گذشته انجام نشده')
    if os.path.exists('/etc/coach-bot/backup-archive.pass'):
        tg = file_text(f'{BACKUPS}/.last-telegram')
        today = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d')
        yesterday = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).strftime('%Y%m%d')
        if tg not in (today, yesterday):
            add('tgbackup', 'بکاپ روزانه تلگرام ارسال نشده؛ مطمئن شو اکانت اصلی بات را استارت کرده')
    failed = file_text('/var/lib/coach-bot-deploy/failed')
    if failed:
        add('deploy', f'آخرین دیپلوی خودکار شکست خورد و به نسخه قبل برگشت (commit {failed[:7]})')
    return found


# ---------- formatting ----------

def human_bytes(n):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024:
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} PB'


def status_block(s):
    cpu = '—' if s['cpu'] is None else f'{s["cpu"]}٪'
    lines = [
        f'🖥 پردازنده {cpu} | بار {s["load"]}',
        f'🧠 رم {s["mem"]}٪ (آزاد {s["mem_free_mb"]} مگ) | swap {s["swap"]}٪',
        f'💾 دیسک {s["disk"]}٪ (آزاد {s["disk_free_gb"]} گیگ)',
        f'🌐 ۵ دقیقه اخیر: {s["req"]} درخواست، {s["uniq"]} IP، {s["s429"]} رد شده (429)، {s["s5"]} خطای 5xx',
    ]
    if s['top']:
        lines.append('🔝 پرترافیک‌ترین IPها: ' + '، '.join(f'{ip} ({n})' for ip, n in s['top']))
    return '\n'.join(lines)


REDACT = [(re.compile(r'\b\d{6,12}:[A-Za-z0-9_-]{30,}\b'), '[BOT_TOKEN]'),
          (re.compile(r'(?i)(password|secret|token|merchant)[^\s=:]*\s*[=:]\s*\S+'), r'\1=[REDACTED]'),
          (re.compile(r'postgres(ql)?://[^\s@]+@'), 'postgresql://[REDACTED]@'),
          (re.compile(r'redis://:[^\s@]+@'), 'redis://:[REDACTED]@')]


def log_bundle(since):
    parts = [('containers', 'docker compose ps -a')]
    for svc in ('bot', 'web-api', 'web', 'site', 'ingress', 'postgres'):
        parts.append((f'{svc} log', f'docker compose logs --no-color --since {since} --tail 400 {svc}'))
    parts += [('nginx errors', 'tail -n 200 /var/log/nginx/error.log'),
              ('system warnings', f'journalctl -p warning --since -{since} --no-pager -o short-iso | tail -n 300'),
              ('fail2ban', 'tail -n 150 /var/log/fail2ban.log'),
              ('deploy', 'journalctl -u coach-bot-deploy -n 60 --no-pager -o short-iso'),
              ('backup', 'journalctl -u coach-bot-backup -n 40 --no-pager -o short-iso'),
              ('memory/disk', 'free -m; df -h /; docker stats --no-stream')]
    out = []
    for title, cmd in parts:
        text = sh(cmd, timeout=90)
        for rx, rep in REDACT:
            text = rx.sub(rep, text)
        out.append(f'===== {title} =====\n$ {cmd}\n{text}\n')
    return gzip.compress('\n'.join(out).encode('utf-8'))


def tehran_now():
    return dt.datetime.now(TEHRAN)


# ---------- daily report ----------

def access_window(seconds):
    cutoff = time.time() - seconds
    lines = []
    for path in (ACCESS + '.1', ACCESS):
        try:
            with open(path, encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    try:
                        if float(line.split('|', 1)[0]) >= cutoff:
                            lines.append(line)
                    except ValueError:
                        pass
        except OSError:
            pass
    return parse_access(lines)


def sql(query):
    return sh(f'docker compose exec -T postgres psql -U coach -d coach -tA -F"|" -c "{query}"')


def report(state):
    rows = history(86400)
    cpus = [r['cpu'] for r in rows if r.get('cpu') is not None]
    mems = [r['mem'] for r in rows]
    last = rows[-1] if rows else sample(state)
    acc, ips, limited = access_window(86400)
    peak = max(rows, key=lambda r: r.get('req', 0)) if rows else None
    ssh_failed = int(sh("journalctl -u ssh --since -24h --no-pager -o cat | grep -cE 'Invalid user|Failed (password|publickey)|maximum authentication attempts'") or 0)
    bans = sum(r.get('bans', 0) for r in rows)
    cont = containers()
    restarts = {svc: c['restarts'] for svc, c in cont.items() if c['restarts']}
    problems = problems_now(last, rows[-2] if len(rows) > 1 else None, dict(state))

    biz = sql("SELECT (SELECT count(*) FROM users), (SELECT count(*) FROM users WHERE created_at > now()-interval '24 hours'),"
              " (SELECT count(*) FROM orders WHERE created_at > now()-interval '24 hours'),"
              " (SELECT count(*) FROM orders WHERE paid_at > now()-interval '24 hours'),"
              " (SELECT coalesce(sum(amount),0) FROM orders WHERE paid_at > now()-interval '24 hours'),"
              " (SELECT count(*) FROM orders WHERE status='awaiting_payment'),"
              " (SELECT count(*) FROM orders WHERE status IN ('paid','needs_info','in_progress','ready'))").split('|')
    biz = (biz + ['?'] * 7)[:7]
    try:
        revenue = f'{int(biz[4]) // 10:,} تومان'
    except ValueError:
        revenue = '?'

    disk_free = last.get('disk_free_gb', '?')
    days_left = ''
    old = history(7 * 86400)
    if len(old) > 12 and old[0]['disk'] < last['disk']:
        per_day = (last['disk'] - old[0]['disk']) / max(1, (last['ts'] - old[0]['ts']) / 86400)
        if per_day > 0:
            days_left = f'، با این سرعت حدود {int((100 - last["disk"]) / per_day)} روز دیگر پر می‌شود'

    backup_age = age_seconds(file_text(f'{BACKUPS}/.last-success'))
    offsite = os.path.exists('/etc/coach-bot/rclone.conf')
    local_dumps = sorted(os.listdir(f'{BACKUPS}/local')) if os.path.isdir(f'{BACKUPS}/local') else []
    hit = f'{100 * acc["hit"] // acc["cacheable"]}٪' if acc['cacheable'] else '—'
    avg_rt = f'{1000 * acc["rt"] / acc["req"]:.0f} ms' if acc['req'] else '—'
    d = tehran_now()
    head = '✅ همه سرویس‌ها سالم‌اند' if not problems else '⚠️ ' + ' | '.join(problems.values())

    text = f"""📊 گزارش روزانه سنسی — {d:%Y-%m-%d} (۲۴ ساعت گذشته)
{head}

🖥 سرور
• پردازنده: میانگین {(sum(cpus) / len(cpus)) if cpus else 0:.0f}٪، بیشترین {max(cpus) if cpus else 0:.0f}٪
• رم: میانگین {(sum(mems) / len(mems)) if mems else 0:.0f}٪، بیشترین {max(mems) if mems else 0:.0f}٪ (الان آزاد {last.get('mem_free_mb', '?')} مگ)
• دیسک: {round(last.get('disk', 0), 1)}٪ پر، {disk_free} گیگ آزاد{days_left}
• شبکه: دریافت {human_bytes(sum(r.get('rx', 0) for r in rows))}، ارسال {human_bytes(sum(r.get('tx', 0) for r in rows))}
• ری‌استارت کانتینرها (از آخرین ساخت): {('، '.join(f'{k}×{v}' for k, v in restarts.items())) if restarts else 'هیچ'}

🌐 ترافیک
• {acc['req']:,} درخواست (سایت {acc['site']:,}، پنل {acc['panel']:,}) از {len(ips):,} IP
• اوج: {peak['req'] if peak else 0} درخواست در ۵ دقیقه ({dt.datetime.fromtimestamp(peak['ts'], TEHRAN):%H:%M} تهران)""" + (f"""
• زمان پاسخ میانگین {avg_rt} | کش سایت {hit} | خطای 4xx {acc['s4']:,} | خطای 5xx {acc['s5']:,}""") + f"""

🛡 امنیت
• تلاش ناموفق ورود به SSH: {ssh_failed:,} (ورود فقط با کلید است)
• IPهای مسدودشده توسط fail2ban: {bans}
• درخواست‌های ردشده به‌خاطر سقف مجاز (429): {acc['s429']:,}""" + (
        '\n• بیشترین ردشده‌ها: ' + '، '.join(f'{ip} ({n})' for ip, n in limited.most_common(3)) if limited else '') + f"""

🗄 بکاپ
• آخرین بکاپ: {'%d دقیقه پیش' % (backup_age // 60) if backup_age is not None else 'هیچ'} | {len(local_dumps)} نسخه روی سرور
• تلگرام: {file_text(BACKUPS + '/.last-telegram') or 'هنوز ارسال نشده'}
• بیرون از سرور (فضای ابری): {'فعال، آخرین: ' + (file_text(BACKUPS + '/.last-offsite') or '؟') if offsite else '❗ تنظیم نشده (عکس‌ها و فایل‌ها بکاپ جدا ندارند)'}

💼 کسب‌وکار
• کاربران: {biz[0]} (جدید امروز {biz[1]})
• سفارش‌های جدید: {biz[2]} | پرداخت‌شده: {biz[3]} ({revenue})
• در انتظار پرداخت: {biz[5]} | در حال انجام: {biz[6]}

📎 فایل پیوست: گزارش خطاها و هشدارهای ۲۴ ساعت گذشته (برای بررسی با Claude)"""
    send_text(text)
    telegram('sendDocument', {'caption': f'لاگ‌های ۲۴ ساعت گذشته — {d:%Y-%m-%d}'},
             f'sensi-logs-{d:%Y%m%d}.txt.gz', log_bundle('24h'))
    state['report_day'] = d.strftime('%Y-%m-%d')


# ---------- main ----------

def check():
    os.makedirs(STATE, exist_ok=True)
    state = load_state()
    prev_rows = history(900)
    prev = prev_rows[-1] if prev_rows else None
    s = sample(state)
    found = problems_now(s, prev, state)
    now = int(time.time())
    active = state.get('active', {})
    new_keys = set(found) - set(active)
    if found and (new_keys or now - state.get('alert_sent', 0) > REPEAT_SECONDS):
        lines = '\n'.join(f'• {t}' for t in found.values())
        send_text(f'🚨 هشدار سرور سنسی\n{lines}\n\n📟 وضعیت الان\n{status_block(s)}\n\n📎 لاگ‌های ۳۰ دقیقه اخیر پیوست است.')
        telegram('sendDocument', {'caption': 'لاگ‌های هنگام هشدار'}, f'sensi-alert-{tehran_now():%Y%m%d-%H%M}.txt.gz', log_bundle('30m'))
        state['alert_sent'] = now
    elif not found and active:
        send_text(f'✅ سرور سنسی دوباره سالم است.\n\n{status_block(s)}')
    state['active'] = found

    d = tehran_now()
    if d.hour >= REPORT_HOUR and state.get('report_day') != d.strftime('%Y-%m-%d'):
        report(state)
    if d.minute < 5:
        prune_history()
    save_state(state)
    if found:
        print('\n'.join(found.values()))
        sys.exit(1)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    os.makedirs(STATE, exist_ok=True)
    if cmd == 'check':
        check()
    elif cmd == 'report':
        state = load_state()
        report(state)
        save_state(state)
    elif cmd == 'status':
        rows = history(900)
        print(status_block(rows[-1]) if rows else 'no samples yet; the 5-minute check has not run')
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
