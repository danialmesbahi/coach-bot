"""Browser pages around the gateway (hand-off, success, failure) in one Sensi design.

Self-contained HTML: inline CSS, the bundled IRANYekan font and compositor-only motion,
so they open fast on weak phones and inside Telegram's in-app browser.
"""
import json
from html import escape
from pathlib import Path

from aiohttp import web

FONT_PATH = Path(__file__).parent / 'web' / 'IRANYekanXVFaNumVF.woff2'
FONT_URL = '/pay/assets/yekan.woff2'

TONES = {
    'redirect': ('#ff5b1f', 'rgba(255,91,31,.14)'),
    'success': ('#22c55e', 'rgba(34,197,94,.14)'),
    'fail': ('#ef4444', 'rgba(239,68,68,.14)'),
    'info': ('#f59e0b', 'rgba(245,158,11,.14)'),
}

ICONS = {
    'redirect': '<span class="spin"></span>',
    'success': '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    'fail': '<svg viewBox="0 0 24 24"><path d="M7 7l10 10M17 7L7 17"/></svg>',
    'info': '<svg viewBox="0 0 24 24"><path d="M12 7v6M12 16.5v.5"/></svg>',
}

CSS = (
    f'@font-face{{font-family:Yekan;src:url({FONT_URL}) format("woff2");font-weight:100 900;font-display:swap}}'
    ':root{color-scheme:dark}*{box-sizing:border-box}'
    'body{margin:0;min-height:100vh;min-height:100dvh;display:grid;place-items:center;padding:20px 16px;'
    'background:#0b0c0e radial-gradient(110% 60% at 50% -8%,var(--soft),transparent 62%) no-repeat;'
    'color:#f2ede6;font:15px/1.9 Yekan,Tahoma,system-ui,sans-serif;-webkit-font-smoothing:antialiased}'
    '.card{width:100%;max-width:400px;background:#131518;border:1px solid #2a2e34;border-radius:24px;'
    'padding:28px 22px 22px;text-align:center;box-shadow:0 24px 60px rgba(0,0,0,.45);animation:rise .45s cubic-bezier(.2,.8,.2,1) both}'
    '.brand{display:inline-flex;align-items:center;gap:8px;color:#9ba1a8;font-size:13px;font-weight:600;margin-bottom:22px}'
    '.brand b{width:26px;height:26px;border-radius:8px;background:#ff5b1f;color:#0b0c0e;display:grid;place-items:center;font-weight:900;font-size:15px}'
    '.badge{width:76px;height:76px;border-radius:50%;margin:0 auto 16px;display:grid;place-items:center;background:var(--soft);'
    'box-shadow:0 0 0 8px rgba(255,255,255,.02);animation:pop .5s .1s cubic-bezier(.2,1.4,.4,1) both}'
    '.badge svg{width:38px;height:38px;fill:none;stroke:var(--tone);stroke-width:2.6;stroke-linecap:round;stroke-linejoin:round}'
    '.spin{width:38px;height:38px;border-radius:50%;border:3px solid var(--soft);border-top-color:var(--tone);animation:spin .8s linear infinite}'
    'h1{margin:0 0 6px;font-size:21px;font-weight:800;line-height:1.6}'
    '.detail{margin:0;color:#c9c4bd;font-size:14px}'
    'dl{margin:20px 0 0;padding:4px 16px;border-radius:16px;background:#0f1113;border:1px solid #23272c;text-align:right}'
    'dl div{display:flex;justify-content:space-between;gap:12px;padding:10px 0;font-size:14px}'
    'dl div+div{border-top:1px dashed #2a2e34}dt{color:#9ba1a8;white-space:nowrap}dd{margin:0;font-weight:700;unicode-bidi:plaintext;overflow-wrap:anywhere}'
    '.btn{display:block;margin-top:20px;padding:14px 18px;border-radius:14px;background:var(--tone);color:#0b0c0e;'
    'font-weight:800;font-size:15px;text-decoration:none;transition:transform .15s}.btn:active{transform:scale(.98)}'
    '.note{margin:14px 0 0;color:#7d838a;font-size:12.5px;line-height:1.8}'
    # Motion only moves things: content stays visible even where animations never run.
    '@keyframes rise{from{transform:translateY(14px)}}@keyframes pop{from{transform:scale(.6)}}'
    '@keyframes spin{to{transform:rotate(360deg)}}'
    '@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}'
)


def page(tone: str, title: str, detail: str = '', *, rows=(), action=None, note: str = '',
         redirect: str = '', status: int = 200, headers=None) -> web.Response:
    """Render one state. Text arguments are plain text; they are escaped here."""
    color, soft = TONES[tone]
    details = ''.join(f'<div><dt>{escape(str(k))}</dt><dd>{escape(str(v))}</dd></div>' for k, v in rows if v not in (None, ''))
    button = f'<a class="btn" href="{escape(action[1], quote=True)}">{escape(action[0])}</a>' if action else ''
    script = f'<script>setTimeout(function(){{location.replace({json.dumps(redirect)})}},1200)</script>' if redirect else ''
    html = ('<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<meta name="theme-color" content="#0b0c0e"><title>{escape(title)} | سنسی</title>'
            f'<link rel="preload" href="{FONT_URL}" as="font" type="font/woff2" crossorigin>'
            f'<style>{CSS}</style></head><body style="--tone:{color};--soft:{soft}"><main class="card">'
            '<div class="brand"><b>S</b>Sensi</div>'
            f'<div class="badge" aria-hidden="true">{ICONS[tone]}</div>'
            f'<h1>{escape(title)}</h1>'
            + (f'<p class="detail">{escape(detail)}</p>' if detail else '')
            + (f'<dl>{details}</dl>' if details else '')
            + button
            + (f'<p class="note">{escape(note)}</p>' if note else '')
            + f'</main>{script}</body></html>')
    base = {'Cache-Control': 'no-store'}
    base.update(headers or {})
    return web.Response(text=html, content_type='text/html', status=status, headers=base)


async def font(request):
    return web.FileResponse(FONT_PATH, headers={'Content-Type': 'font/woff2', 'Cache-Control': 'public, max-age=2592000, immutable'})
