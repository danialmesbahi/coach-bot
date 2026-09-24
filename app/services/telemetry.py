"""Best-effort, bounded counters: no bodies, identities, URLs, IPs or secrets.

Financial and staff KPIs use durable business tables, never these counters.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone

from aiogram import BaseMiddleware
from aiohttp import web
from app.db.core import db
from app.services.diagnostics import operation

log = logging.getLogger(__name__)
MAX_KEYS = 2048
_buckets = {}
_dropped = 0
STEPS = {'name','phone','age','gender','height','weight','goal','training_history',
         'allergy','restriction','supplements','notes','body_photo','custom_question',
         'confirm','payment_method','receipt','submitting'}


def record(source, event, dimension, outcome='ok', elapsed=0):
    global _dropped
    if source not in {'web','bot','payment'} or event not in {'request','step','checkout','throttled','client'}:
        return
    # All dimensions come from server route/state names, never user input.
    if not isinstance(dimension,str) or len(dimension)>64 or not dimension.replace('_','').isalnum():
        return
    if outcome not in {'ok','client_error','server_error','advanced','waiting','blocked'}:
        return
    hour = datetime.now(timezone.utc).replace(minute=0,second=0,microsecond=0)
    key = (hour,source,event,dimension,outcome)
    if key not in _buckets and len(_buckets)>=MAX_KEYS:
        _dropped += 1
        return
    values = _buckets.setdefault(key,[0,0.,0])
    values[0] += 1
    values[1] += min(max(elapsed,0),120) * 1000
    values[2] += int(elapsed>2)


async def flush(source):
    global _dropped
    keys = list(_buckets)[:256]
    batch = [(*key,*_buckets.pop(key)) for key in keys]
    dropped,_dropped = _dropped,0
    try:
        async with asyncio.timeout(5),db.acquire() as c,c.transaction():
            if batch:
                await c.executemany('''INSERT INTO analytics_buckets VALUES($1,$2,$3,$4,$5,$6,$7,$8)
                    ON CONFLICT(hour,source,event,dimension,outcome) DO UPDATE SET
                    count=analytics_buckets.count+EXCLUDED.count,
                    elapsed_ms=analytics_buckets.elapsed_ms+EXCLUDED.elapsed_ms,
                    slow_count=analytics_buckets.slow_count+EXCLUDED.slow_count''',batch)
            await c.execute('''INSERT INTO analytics_collectors(source,dropped) VALUES($1,$2)
                ON CONFLICT(source) DO UPDATE SET last_seen=NOW(),dropped=analytics_collectors.dropped+$2''',source,dropped)
    except Exception:
        # ponytail: volatile telemetry can be lost on crashes; use a durable queue if exact event accounting becomes required.
        _dropped += dropped + sum(row[5] for row in batch)
        log.warning('Telemetry batch unavailable; business requests remain unaffected')


async def run_telemetry_loop(source):
    cleanup_at=0.
    try:
        while True:
            await flush(source)
            if time.monotonic()>=cleanup_at:
                try:
                    async with db.acquire() as c:
                        # Delete in bounded batches; do not delete financial or audit records.
                        await c.execute("DELETE FROM analytics_buckets WHERE ctid IN (SELECT ctid FROM analytics_buckets WHERE hour<NOW()-INTERVAL '100 days' LIMIT 2000)")
                        # Retain consumed one-use tombstones; deleting them would permit redemption again.
                        await c.execute("""DELETE FROM content_links WHERE token_hash IN (
                            SELECT l.token_hash FROM content_links l JOIN orders o ON o.id=l.order_id
                            WHERE l.expires_at<NOW()-INTERVAL '7 days'
                            AND (l.redeemed_at IS NULL OR o.duration_days<>-1) LIMIT 500)""")
                    cleanup_at=time.monotonic()+3600
                except Exception:
                    cleanup_at=time.monotonic()+60
            await asyncio.sleep(5)
    finally:
        await flush(source)


@web.middleware
async def web_metrics(request, handler):
    from app.services.staff import ROUTE_PERMISSIONS
    name=getattr(request.match_info.handler,'__name__','unknown')
    if name in {'realtime_events','analytics','client_error','health'} or name not in {*ROUTE_PERMISSIONS,'password_login'}:
        return await handler(request)
    started=time.monotonic(); status=500
    try:
        result=await handler(request)
        status=result.status
        return result
    except web.HTTPException as exc:
        status=exc.status
        raise
    finally:
        elapsed=time.monotonic()-started
        record('web','request',name,'server_error' if status>=500 else 'client_error' if status>=400 else 'ok',elapsed)
        operation('web',name,elapsed,status,request.get('request_id',''),request.method)


class BotMetrics(BaseMiddleware):
    async def __call__(self,handler,event,data):
        before=data.get('raw_state') or ''
        step=before.split(':')[-1] if before.startswith('PurchaseForm:') else ''
        started=time.monotonic()
        try:
            result=await handler(event,data)
        except Exception:
            record('bot','request','purchase' if step in STEPS else 'other','server_error',time.monotonic()-started)
            log.exception('Bot operation failed',extra={'event':'bot_operation_failed','route':step or 'other','elapsed_ms':(time.monotonic()-started)*1000})
            raise
        record('bot','request','purchase' if step in STEPS else 'other','ok',time.monotonic()-started)
        operation('bot',step or 'other',time.monotonic()-started)
        if step in STEPS and data.get('state'):
            try:
                after=await data['state'].get_state()
                record('bot','step',step,'waiting' if after==before else 'advanced')
            except Exception:
                pass  # Observability must never break checkout.
        return result
