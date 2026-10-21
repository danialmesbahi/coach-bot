"""Branded pages the customer sees in the browser around the gateway: hand-off, success and failure.

They share the public site's look (dark, ember accent, IRANYekanX) and stay light for low-end phones:
one inline stylesheet, an inline SVG icon and no script except the gateway hand-off.
"""
import json
from html import escape
from pathlib import Path

FONT = Path(__file__).resolve().parent.parent / 'web' / 'IRANYekanXVFaNumVF.woff2'
FONT_URL = '/pay/assets/yekan.woff2'

_ICONS = {
    'ok': '<path d="M15 25.5l6.5 6.5L34 18.5" class="draw"/>',
    'fail': '<path d="M17 17l14 14M31 17L17 31" class="draw"/>',
    'wait': '<rect x="16" y="22" width="16" height="12" rx="3"/><path d="M19.5 22v-3.5a4.5 4.5 0 0 1 9 0V22"/>',
    'info': '<path d="M24 15v11M24 32.5v.5"/>',
}

_CSS = '''
@font-face{font-family:Yekan;src:url(%(font)s) format("woff2");font-weight:100 1000;font-display:swap}
:root{--night:#0b0c0e;--carbon:#131518;--carbon2:#1a1d21;--line:rgba(242,237,230,.12);--bone:#f2ede6;--ash:#9ba1a8;
--ember:#ff5b1f;--ember-hot:#ff7a3d;--ok:#22c55e;--fail:#f43f5e;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;min-height:100svh;display:grid;place-items:center;padding:24px 16px;background:var(--night);color:var(--bone);
font:400 16px/1.9 Yekan,Tahoma,system-ui,sans-serif;-webkit-font-smoothing:antialiased;
background-image:radial-gradient(120%% 60%% at 50%% -10%%,var(--glow),transparent 60%%)}
.wrap{width:100%%;max-width:420px}
.brand{display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:20px;font-weight:900;font-size:20px;letter-spacing:-.2px}
.brand svg{width:34px;height:34px}
.card{background:linear-gradient(180deg,var(--carbon2),var(--carbon));border:1px solid var(--line);border-radius:24px;
padding:32px 24px 24px;text-align:center;box-shadow:0 24px 60px -24px rgba(0,0,0,.7)}
.icon{width:84px;height:84px;margin:0 auto 18px;border-radius:50%%;display:grid;place-items:center;position:relative;
background:color-mix(in srgb,var(--tone) 14%%,transparent);box-shadow:0 0 0 8px color-mix(in srgb,var(--tone) 6%%,transparent)}
.icon svg{width:48px;height:48px;fill:none;stroke:var(--tone);stroke-width:3.2;stroke-linecap:round;stroke-linejoin:round}
.draw{stroke-dasharray:48;stroke-dashoffset:48;animation:draw .55s .15s cubic-bezier(.16,1,.3,1) forwards}
.spin{position:absolute;inset:-4px;border-radius:50%%;border:3px solid transparent;border-top-color:var(--tone);animation:spin 1s linear infinite}
h1{margin:0 0 6px;font-size:22px;font-weight:900;line-height:1.5}
p{margin:0;color:var(--ash)}
dl{margin:20px 0 0;padding:4px 16px;border:1px solid var(--line);border-radius:16px;background:rgba(0,0,0,.18);text-align:right}
dl div{display:flex;justify-content:space-between;gap:12px;padding:10px 0}
dl div+div{border-top:1px dashed var(--line)}
dt{color:var(--ash)}dd{margin:0;font-weight:800;unicode-bidi:plaintext}
.note{margin-top:16px;padding:12px 14px;border-radius:14px;background:rgba(255,91,31,.08);border:1px solid rgba(255,91,31,.22);color:#f6c8b3;font-size:14px;line-height:1.8;text-align:right}
.bar{height:4px;margin-top:22px;border-radius:4px;background:var(--line);overflow:hidden}
.bar i{display:block;height:100%%;width:40%%;border-radius:4px;background:var(--tone);animation:slide 1.2s ease-in-out infinite}
.btn{display:flex;align-items:center;justify-content:center;gap:8px;width:100%%;min-height:52px;margin-top:22px;border-radius:16px;
background:var(--ember);color:#0b0c0e;font-weight:900;font-size:16px;text-decoration:none;transition:background .2s}
.btn:hover,.btn:focus-visible{background:var(--ember-hot)}
.foot{margin-top:18px;text-align:center;color:var(--ash);font-size:13px}
@keyframes draw{to{stroke-dashoffset:0}}@keyframes spin{to{transform:rotate(360deg)}}
@keyframes slide{0%%{transform:translateX(130%%)}100%%{transform:translateX(-260%%)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}.draw{stroke-dashoffset:0}}
'''

_GLOW = {'ok': 'rgba(34,197,94,.16)', 'fail': 'rgba(244,63,94,.14)', 'wait': 'rgba(255,91,31,.18)', 'info': 'rgba(245,158,11,.14)'}
_TONE = {'ok': 'var(--ok)', 'fail': 'var(--fail)', 'wait': 'var(--ember)', 'info': '#f59e0b'}

_LOGO = ('<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#ff5b1f"/>'
         '<path d="M5 18h5.2l2.4-7.5 4.2 13 2.6-8 1.4 2.5H27" fill="none" stroke="#0b0c0e" stroke-width="2.6" '
         'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def render(tone: str, title: str, detail: str, *, rows=(), action: tuple[str, str] | None = None,
           note: str = '', redirect: str = '') -> str:
    """tone is ok, fail, wait or info. detail and note are trusted markup; row values and links are escaped here."""
    items=''.join(f'<div><dt>{escape(label)}</dt><dd>{escape(str(value))}</dd></div>' for label,value in rows)
    button=f'<a class="btn" href="{escape(action[1],quote=True)}" referrerpolicy="origin">{escape(action[0])}</a>' if action else ''
    spinner='<span class="spin"></span>' if tone=='wait' else ''
    progress='<div class="bar"><i></i></div>' if redirect else ''
    # A short pause lets the customer read where they are going; the referrer stays our origin.
    script=f'<script>setTimeout(function(){{location.replace({json.dumps(redirect)})}},1200)</script>' if redirect else ''
    css=_CSS % {'font': FONT_URL}
    return (f'<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="origin">'
            f'<meta name="robots" content="noindex"><meta name="theme-color" content="#0b0c0e">'
            f'<title>{escape(title)} · سنسی</title><link rel="preload" href="{FONT_URL}" as="font" type="font/woff2" crossorigin>'
            f'<style>{css}</style></head>'
            f'<body style="--glow:{_GLOW[tone]};--tone:{_TONE[tone]}"><div class="wrap">'
            f'<div class="brand">{_LOGO}<span>سنسی</span></div>'
            f'<main class="card"><div class="icon">{spinner}<svg viewBox="0 0 48 48" aria-hidden="true">{_ICONS[tone]}</svg></div>'
            f'<h1>{escape(title)}</h1><p>{detail}</p>'
            f'{f"<dl>{items}</dl>" if items else ""}{f"<div class=note>{note}</div>" if note else ""}{progress}{button}</main>'
            f'<div class="foot">پرداخت امن با زرین‌پال · پشتیبانی داخل ربات</div></div>{script}</body></html>')
