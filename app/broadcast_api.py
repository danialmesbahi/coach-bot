"""Leader-only targeted announcements, with preview and explicit queueing."""
import asyncio
import json

from aiohttp import web

from app.db.core import db
from app.services import staff
from app.services.broadcasts import AUDIENCE_SQL, audience_args


async def broadcast_overview(request):
    from app.webapp import response
    staff.require(request['actor'],'broadcast.manage')
    async with db.acquire() as c:
        products=await c.fetch('SELECT id,title,archived FROM products ORDER BY archived,sort_order,id LIMIT 200')
        campaigns=await c.fetch('''SELECT b.id,b.message,b.audience,b.status,b.created_at,
            COUNT(r.user_id)::int AS total,COUNT(*) FILTER(WHERE r.status='sent')::int AS sent,
            COUNT(*) FILTER(WHERE r.status='failed')::int AS failed,
            COUNT(*) FILTER(WHERE r.status='paused')::int AS paused
            FROM (SELECT * FROM broadcasts ORDER BY id DESC LIMIT 20) b
            LEFT JOIN broadcast_recipients r ON r.broadcast_id=b.id
            GROUP BY b.id,b.message,b.audience,b.status,b.created_at ORDER BY b.id DESC''')
    return response({'products':[dict(p) for p in products],'campaigns':[dict(c) for c in campaigns]})


async def _body(request, *, require_message=True):
    async with asyncio.timeout(5):
        body=await request.clone(client_max_size=32768).json()
    if not isinstance(body,dict): raise web.HTTPBadRequest()
    try:
        args=audience_args(body.get('audience',{}))
    except ValueError:
        raise web.HTTPBadRequest(text='Invalid audience')
    message=body.get('message','')
    if not isinstance(message,str) or (require_message and not 1<=len(message.strip())<=4000):
        raise web.HTTPBadRequest(text='Invalid message')
    return body,message.strip(),args


async def broadcast_preview(request):
    from app.webapp import response, _rate_limited
    staff.require(request['actor'],'broadcast.manage')
    if await _rate_limited(request,'broadcast_preview',30): return response({'error':'rate_limited'},429)
    body,_,args=await _body(request,require_message=False)
    after_id=body.get('after_id')
    if after_id is not None and (type(after_id) is not int or not 1<=after_id<=9_223_372_036_854_775_807):
        raise web.HTTPBadRequest(text='Invalid cursor')
    async with db.acquire() as c:
        count=await c.fetchval('SELECT COUNT(*) '+AUDIENCE_SQL,*args)
        rows=await c.fetch('SELECT u.id,u.name,u.first_name,u.last_name,u.username '
            +AUDIENCE_SQL+(' AND u.id<$25::bigint' if after_id is not None else '')
            +' ORDER BY u.id DESC LIMIT 13',*args,*([after_id] if after_id is not None else []))
    return response({'count':count,'recipients':[dict(row) for row in rows[:12]],
                     'next_cursor':rows[11]['id'] if len(rows)>12 else None})


async def broadcast_send(request):
    from app.webapp import response, _rate_limited
    staff.require(request['actor'],'broadcast.manage')
    if await _rate_limited(request,'broadcast_send',2): return response({'error':'rate_limited'},429)
    body,message,args=await _body(request)
    expected=body.get('expected_count')
    if type(expected) is not int or expected<1: return response({'error':'preview_required'},400)
    # The advisory lock serializes campaigns; each check must see a campaign
    # committed by a sender that held the lock before us.
    async with db.acquire() as c,c.transaction(isolation='read_committed'):
        await c.execute('SELECT pg_advisory_xact_lock(917004)')
        if await c.fetchval("SELECT 1 FROM broadcasts WHERE status='queued' LIMIT 1"):
            return response({'error':'broadcast_in_progress'},409)
        count=await c.fetchval('SELECT COUNT(*) '+AUDIENCE_SQL,*args)
        if count!=expected or count>100000: return response({'error':'audience_changed','count':count},409)
        campaign=await c.fetchval('INSERT INTO broadcasts(staff_id,message,audience) VALUES($1,$2,$3::jsonb) RETURNING id',request['actor']['staff_id'],message,json.dumps(body.get('audience',{})))
        await c.execute('''INSERT INTO broadcast_recipients(broadcast_id,user_id,telegram_id)
            SELECT $25::bigint,u.id,u.telegram_id '''+AUDIENCE_SQL, *args,campaign)
        await staff.audit(c,request['actor'],'broadcast_queued','broadcast',campaign,{'recipients':count})
    return response({'ok':True,'id':campaign,'count':count})


def routes():
    return [web.get('/api/broadcasts',broadcast_overview),web.post('/api/broadcasts/preview',broadcast_preview),web.post('/api/broadcasts',broadcast_send)]
