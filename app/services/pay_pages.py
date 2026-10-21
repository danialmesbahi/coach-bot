"""Branded pages the customer sees in the browser around the gateway: hand-off, VPN help, success and failure.

They share the public site's look (dark, ember accent, IRANYekanX) and stay light for low-end phones:
one inline stylesheet, inline SVG icons and no script except the gateway hand-off.
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
    'vpn': '<circle cx="24" cy="24" r="11"/><path d="M13 24h22M24 13c3.2 3.4 4.6 7 4.6 11s-1.4 7.6-4.6 11c-3.2-3.4-4.6-7-4.6-11s1.4-7.6 4.6-11"/>'
           '<path d="M10 10l28 28" class="draw slash"/>',
}

# What a VPN user does before the bank gateway will open. Shared by the server check and the "came back" state.
VPN_STEPS = ('فیلترشکن (VPN) را کامل خاموش کن، نه فقط قطع و وصل.',
             'دکمه «خاموش کردم، تلاش دوباره» را بزن.',
             'بعد از پرداخت می‌توانی دوباره روشنش کنی.')

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
.steps{margin:20px 0 0;padding:0;list-style:none;counter-reset:s;text-align:right}
.steps li{counter-increment:s;display:flex;gap:12px;align-items:flex-start;padding:10px 0;font-size:15px;line-height:1.8}
.steps li+li{border-top:1px dashed var(--line)}
.steps li::before{content:counter(s);flex:none;width:28px;height:28px;margin-top:1px;border-radius:9px;display:grid;place-items:center;
background:color-mix(in srgb,var(--tone) 16%%,transparent);color:var(--tone);font-weight:900;font-size:14px}
.alt{display:block;margin-top:14px;color:var(--ash);font-size:14px;text-decoration:underline;text-underline-offset:4px}
.slash{stroke:var(--fail)}
.back,body.came-back .first{display:none}body.came-back .back{display:block}
.foot{margin-top:18px;text-align:center;color:var(--ash);font-size:13px}
@keyframes draw{to{stroke-dashoffset:0}}@keyframes spin{to{transform:rotate(360deg)}}
@keyframes slide{0%%{transform:translateX(130%%)}100%%{transform:translateX(-260%%)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}.draw{stroke-dashoffset:0}}
'''

_GLOW = {'ok': 'rgba(34,197,94,.16)', 'fail': 'rgba(244,63,94,.14)', 'wait': 'rgba(255,91,31,.18)', 'info': 'rgba(245,158,11,.14)',
         'vpn': 'rgba(56,189,248,.14)'}
_TONE = {'ok': 'var(--ok)', 'fail': 'var(--fail)', 'wait': 'var(--ember)', 'info': '#f59e0b', 'vpn': '#38bdf8'}

_LOGO = ('<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#ff5b1f"/>'
         '<path d="M5 18h5.2l2.4-7.5 4.2 13 2.6-8 1.4 2.5H27" fill="none" stroke="#0b0c0e" stroke-width="2.6" '
         'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def card(tone: str, title: str, detail: str, *, rows=(), steps=(), action: tuple[str, str] | None = None,
         alt: tuple[str, str] | None = None, note: str = '', progress: bool = False, cls: str = '') -> str:
    """One card. detail and note are trusted markup; rows, steps, labels and links are escaped here."""
    items=''.join(f'<div><dt>{escape(label)}</dt><dd>{escape(str(value))}</dd></div>' for label,value in rows)
    todo=''.join(f'<li>{escape(step)}</li>' for step in steps)
    button=f'<a class="btn" href="{escape(action[1],quote=True)}" referrerpolicy="origin">{escape(action[0])}</a>' if action else ''
    link=f'<a class="alt" href="{escape(alt[1],quote=True)}" referrerpolicy="origin">{escape(alt[0])}</a>' if alt else ''
    spinner='<span class="spin"></span>' if tone=='wait' else ''
    style='' if not cls else f' style="--tone:{_TONE[tone]}"'
    return (f'<main class="card {cls}"{style}><div class="icon">{spinner}<svg viewBox="0 0 48 48" aria-hidden="true">{_ICONS[tone]}</svg></div>'
            f'<h1>{escape(title)}</h1><p>{detail}</p>'
            f'{f"<dl>{items}</dl>" if items else ""}{f"<ol class=steps>{todo}</ol>" if todo else ""}'
            f'{f"<div class=note>{note}</div>" if note else ""}{"<div class=bar><i></i></div>" if progress else ""}{button}{link}</main>')


def document(tone: str, title: str, cards: str, script: str = '') -> str:
    css=_CSS % {'font': FONT_URL}
    return (f'<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="origin">'
            f'<meta name="robots" content="noindex"><meta name="theme-color" content="#0b0c0e">'
            f'<title>{escape(title)} · سنسی</title><link rel="preload" href="{FONT_URL}" as="font" type="font/woff2" crossorigin>'
            f'<style>{css}</style></head>'
            f'<body style="--glow:{_GLOW[tone]};--tone:{_TONE[tone]}"><div class="wrap">'
            f'<div class="brand">{_LOGO}<span>سنسی</span></div>{cards}'
            f'<div class="foot">پرداخت امن با زرین‌پال · پشتیبانی داخل ربات</div></div>{script}</body></html>')


def render(tone: str, title: str, detail: str, **parts) -> str:
    """A single-state page: tone is ok, fail, wait, info or vpn."""
    return document(tone,title,card(tone,title,detail,**parts))


def handoff(target: str, rows, retry_back: str) -> str:
    """Opens the gateway after a short pause. If the customer comes back here (ZarinPal refused a VPN, or they
    pressed back), the page shows the VPN steps instead of bouncing them to the gateway again."""
    first=card('wait','در حال انتقال به درگاه پرداخت','چند لحظه صبر کن؛ صفحه پرداخت امن زرین‌پال خودکار باز می‌شود.',
               rows=rows,progress=True,action=('ورود به درگاه زرین‌پال',target),cls='first')
    back=card('vpn','به درگاه نرسیدی؟','اگر زرین‌پال خطای فیلترشکن یا «دسترسی غیرمجاز» داد، این کارها را انجام بده:',
              steps=VPN_STEPS,action=('خاموش کردم، تلاش دوباره',target),alt=('بازگشت به ربات',retry_back),cls='back')
    # assign (not replace) keeps this page in history, so the back button from the gateway lands here.
    script=('<script>(function(){var u='+json.dumps(target)+',k="sensi-pay:"+u,b=document.body;'
            'function go(){try{sessionStorage.setItem(k,"1")}catch(e){}location.assign(u)}'
            'document.querySelectorAll(".btn").forEach(function(a){a.addEventListener("click",function(e){e.preventDefault();go()})});'
            'addEventListener("pageshow",function(e){var seen;try{seen=sessionStorage.getItem(k)}catch(x){}'
            'if(seen||e.persisted){b.classList.add("came-back");b.style.setProperty("--tone","#38bdf8");'
            'b.style.setProperty("--glow","rgba(56,189,248,.14)")}else{setTimeout(go,1200)}})})()</script>')
    return document('wait','در حال انتقال به درگاه پرداخت',first+back,script)
