"""Server-scoped KPIs. Never accept an actor or a financial scope from the client."""
from datetime import datetime, timedelta, timezone
import asyncio
from aiohttp import web
from app.db.core import db
from app.services import staff


def options(actor, query):
    staff.require(actor,'analytics.self')
    scope=query.get('scope','personal' if actor['role']=='staff' else 'platform')
    if scope not in {'personal','platform'}:
        raise web.HTTPBadRequest()
    if scope=='platform' and actor['role'] not in {'leader','platform'}:
        raise web.HTTPForbidden()
    days=query.get('days','30')
    category=query.get('category','all')
    page=query.get('page','1')
    if days not in {'7','30','90'} or category not in {'all','login','orders','messages','team','notes'} or len(page)>3 or not page.isdigit() or not 1<=int(page)<=200:
        raise web.HTTPBadRequest()
    return scope,int(days),category,int(page)


def change(current, previous):
    return round((current-previous)/previous*100,1) if previous else None


async def analytics(request):
    from app.webapp import _cached,_rate_limited,response
    actor=request['actor']
    scope,days,category,page=options(actor,request.query)
    if await _rate_limited(request,'analytics',20):
        return response({'error':'rate_limited'},429)
    identity=actor['staff_id'] if scope=='personal' else 0
    activity_only=request.query.get('section')=='activity'
    include_platform=actor['role']=='platform'
    async def load():
        slots=request.app.setdefault('analytics_slots',asyncio.Semaphore(2))
        try:
            async with asyncio.timeout(.2):
                await slots.acquire()
        except TimeoutError:
            raise web.HTTPServiceUnavailable(headers={'Retry-After':'5'})
        try:
            async with asyncio.timeout(9):
                if activity_only:
                    end=datetime.now(timezone.utc)
                    async with db.acquire() as c,c.transaction(readonly=True):
                        await c.execute("SET LOCAL statement_timeout='7000ms'")
                        return await activity_log(c,end-timedelta(days=days),end,identity,category,page,include_platform)
                return await snapshot(identity,days,category,page,include_platform)
        finally:
            slots.release()
    # Same-role shared single-flight cache; personal entries cannot cross identities.
    result=await _cached(request,f'analytics:{identity}:{days}:{category}:{page}:{activity_only}:{include_platform}',60,load)
    return response(result)


async def client_error(request):
    from app.webapp import _rate_limited,response
    from app.services.telemetry import record
    if await _rate_limited(request,'client_error',6):
        return response({'error':'rate_limited'},429)
    if request.content_length is not None and request.content_length>2048:
        raise web.HTTPRequestEntityTooLarge(max_size=2048,actual_size=request.content_length)
    async with asyncio.timeout(2):
        body=await request.clone(client_max_size=2048).json()
    if not isinstance(body,dict) or set(body)-{'view','frames','kind','request_id'} or not isinstance(body.get('view'),str) or body['view'] not in {
        'dashboard','customers','orders','messages','sales','followups','catalog','analytics'}:
        raise web.HTTPBadRequest()
    import logging, re
    frames=body.get('frames',[])
    if not isinstance(frames,list) or len(frames)>10 or any(not isinstance(f,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}\.js:\d{1,8}:\d{1,8}',f) for f in frames):
        raise web.HTTPBadRequest()
    kind=body.get('kind','Error')
    if not isinstance(kind,str) or kind not in {'Error','TypeError','RangeError','ReferenceError','SyntaxError','URIError','AggregateError','NetworkError','TimeoutError','HttpError','SlowRequest','MediaError'}: kind='Error'
    request_id=body.get('request_id','')
    if not isinstance(request_id,str) or (request_id and not re.fullmatch('[a-f0-9]{16}',request_id)): raise web.HTTPBadRequest()
    record('web','client',body['view'],'ok' if kind=='SlowRequest' else 'server_error',2.001 if kind=='SlowRequest' else 0)
    logging.getLogger('client').log(logging.WARNING if kind=='SlowRequest' else logging.ERROR,'Client failure',extra={'event':body['view']+'.'+kind,'client_frames':frames,'request_id':request_id})
    return response({'ok':True})


async def activity_log(c,start,end,identity,category,page,include_platform=True):
    # Both report surfaces use this metadata-only feed; never return message bodies or audit metadata.
    logs=await c.fetch('''WITH events AS (
        SELECT a.id,a.created_at,a.actor_name,s.role AS actor_role,a.action,a.target_type AS target,a.target_id,'audit' AS source,
            CASE WHEN a.action='staff_login' THEN 'login' WHEN a.action IN ('internal_note','assigned') THEN 'notes'
            WHEN a.target_type='order' THEN 'orders' ELSE 'team' END AS category
        FROM audit_logs a LEFT JOIN staff_accounts s ON s.id=a.actor_staff_id
        WHERE a.created_at>=$1 AND a.created_at<$2 AND ($3::bigint=0 OR a.actor_staff_id=$3)
            AND ($6 OR s.role IS DISTINCT FROM 'platform')
        UNION ALL
        SELECT m.id,m.created_at,m.sender_name,s.role,'reply_sent','thread',m.user_id,'message','messages'
        FROM support_messages m LEFT JOIN staff_accounts s ON s.id=m.sender_staff_id
        WHERE m.direction='sensi' AND m.created_at>=$1 AND m.created_at<$2 AND ($3::bigint=0 OR m.sender_staff_id=$3)
            AND ($6 OR s.role IS DISTINCT FROM 'platform')
    ) SELECT * FROM events WHERE $4='all' OR category=$4
    ORDER BY created_at DESC,source,id DESC LIMIT 26 OFFSET $5''',start,end,identity,category,(page-1)*25,include_platform)
    return {'items':[dict(r) for r in logs[:25]],'page':page,'has_more':len(logs)>25}


async def snapshot(identity, days, category='all', page=1,include_platform=True):
    end=datetime.now(timezone.utc)
    start=end-timedelta(days=days); previous=start-timedelta(days=days)
    result={'scope':'personal' if identity else 'platform','days':days,'from':start,'to':end,'generated_at':end}
    async with db.acquire() as c,c.transaction(isolation='repeatable_read',readonly=True):
        await c.execute("SET LOCAL statement_timeout='7000ms'")
        await c.execute("SET LOCAL TIME ZONE 'Asia/Tehran'")
        activity=dict(await c.fetchrow('''SELECT
            COUNT(*) FILTER(WHERE created_at>=$1) AS actions,
            COUNT(*) FILTER(WHERE created_at<$1) AS previous_actions,
            COUNT(*) FILTER(WHERE created_at>=$1 AND action='staff_login') AS logins,
            COUNT(*) FILTER(WHERE created_at>=$1 AND action='internal_note') AS notes,
            COUNT(*) FILTER(WHERE created_at>=$1 AND action='web_deliver_plan') AS deliveries,
            COUNT(*) FILTER(WHERE created_at>=$1 AND target_type='order') AS order_actions
            FROM audit_logs WHERE created_at>=$2 AND created_at<$3 AND ($4::bigint=0 OR actor_staff_id=$4)''',start,previous,end,identity))
        messages=dict(await c.fetchrow('''SELECT COUNT(*) FILTER(WHERE created_at>=$1) AS replies,
            COUNT(*) FILTER(WHERE created_at<$1) AS previous_replies,
            COUNT(DISTINCT user_id) FILTER(WHERE created_at>=$1) AS clients
            FROM support_messages WHERE direction='sensi' AND created_at>=$2 AND created_at<$3
            AND ($4::bigint=0 OR sender_staff_id=$4)''',start,previous,end,identity))
        activity.update(messages)
        activity['unseen']=await c.fetchval('SELECT COUNT(*) FROM staff_assignments WHERE seen_at IS NULL AND ($1::bigint=0 OR staff_id=$1)',identity)
        activity['replies_change']=change(activity['replies'],activity['previous_replies'])
        result['activity']=activity
        result['logs']=await activity_log(c,start,end,identity,category,page,include_platform)
        if identity:
            return result
        sales=dict(await c.fetchrow('''SELECT
            COALESCE(SUM(amount) FILTER(WHERE paid_at>=$1),0) AS revenue,
            COALESCE(SUM(amount) FILTER(WHERE paid_at<$1),0) AS previous_revenue,
            COUNT(*) FILTER(WHERE paid_at>=$1) AS payments,
            COUNT(DISTINCT user_id) FILTER(WHERE paid_at>=$1) AS buyers
            FROM orders WHERE paid_at>=$2 AND paid_at<$3''',start,previous,end))
        sales['revenue_change']=change(sales['revenue'],sales['previous_revenue'])
        sales.update(dict(await c.fetchrow('''SELECT COUNT(*) AS invoices,
            COUNT(*) FILTER(WHERE paid_at IS NOT NULL) AS converted,
            COUNT(*) FILTER(WHERE status='delivered') AS delivered
            FROM orders WHERE created_at>=$1 AND created_at<$2''',start,end)))
        sales['conversion']=round(sales['converted']/sales['invoices']*100,1) if sales['invoices'] else None
        sales['new_users']=await c.fetchval('SELECT COUNT(*) FROM users WHERE created_at>=$1 AND created_at<$2',start,end)
        sales['repeat_buyers']=await c.fetchval('''SELECT COUNT(DISTINCT o.user_id) FROM orders o WHERE o.paid_at>=$1 AND o.paid_at<$2
            AND EXISTS(SELECT 1 FROM orders old WHERE old.user_id=o.user_id AND old.paid_at<o.paid_at)''',start,end)
        result['sales']=sales
        result['trend']=[dict(r) for r in await c.fetch('''WITH days AS (
            SELECT generate_series($1::timestamptz::date,$2::timestamptz::date,INTERVAL '1 day')::date AS day
        ), sales AS (SELECT paid_at::date AS day,SUM(amount) AS revenue,COUNT(*) AS payments
            FROM orders WHERE paid_at>=$1 AND paid_at<$2 GROUP BY 1)
            SELECT d.day,COALESCE(s.revenue,0) AS revenue,COALESCE(s.payments,0) AS payments
            FROM days d LEFT JOIN sales s USING(day) ORDER BY d.day''',start,end)]
        result['products']=[dict(r) for r in await c.fetch('''SELECT o.product_id,p.title,COUNT(*) AS payments,SUM(o.amount) AS revenue
            FROM orders o JOIN products p ON p.id=o.product_id WHERE o.paid_at>=$1 AND o.paid_at<$2
            GROUP BY o.product_id,p.title ORDER BY revenue DESC,o.product_id LIMIT 10''',start,end)]
        result['operations']=dict(await c.fetchrow('''SELECT
            COUNT(*) FILTER(WHERE paid_at IS NOT NULL AND status IN ('paid','in_progress','needs_info','ready')) AS backlog,
            COUNT(*) FILTER(WHERE paid_at IS NOT NULL AND NOT fulfillment_done AND fulfillment_error IS NOT NULL) AS failed_delivery,
            EXTRACT(EPOCH FROM NOW()-MIN(paid_at) FILTER(WHERE status IN ('paid','in_progress','needs_info','ready')))/3600 AS oldest_hours,
            (SELECT COUNT(DISTINCT user_id) FROM support_messages WHERE direction='customer' AND read_at IS NULL) AS unread_chats,
            percentile_cont(.5) WITHIN GROUP(ORDER BY EXTRACT(EPOCH FROM delivered_at-paid_at)/3600)
                FILTER(WHERE delivered_at>=$1 AND delivered_at<$2 AND delivered_at>=paid_at AND COALESCE(product_snapshot->>'delivery_mode','manual')='manual') AS delivery_hours,
            COUNT(*) FILTER(WHERE delivered_at>=$1 AND delivered_at<$2 AND delivered_at>=paid_at AND COALESCE(product_snapshot->>'delivery_mode','manual')='manual') AS delivery_sample
            FROM orders''',start,end))
        result['team']=[dict(r) for r in await c.fetch('''WITH replies AS (
            SELECT sender_staff_id AS id,COUNT(*) AS replies FROM support_messages
            WHERE direction='sensi' AND created_at>=$1 AND created_at<$2 GROUP BY 1
        ), work AS (SELECT actor_staff_id AS id,COUNT(*) FILTER(WHERE action='web_deliver_plan') AS deliveries,
            COUNT(*) FILTER(WHERE action='internal_note') AS notes FROM audit_logs WHERE created_at>=$1 AND created_at<$2 GROUP BY 1)
            SELECT s.id,s.display_name,s.role,COALESCE(r.replies,0) AS replies,COALESCE(w.deliveries,0) AS deliveries,COALESCE(w.notes,0) AS notes
            FROM staff_accounts s LEFT JOIN replies r USING(id) LEFT JOIN work w USING(id)
            WHERE s.status='active' ORDER BY s.display_name,s.id LIMIT 50''',start,end)]
        result['telemetry']=[dict(r) for r in await c.fetch('''SELECT source,event,dimension,outcome,SUM(count) AS count,
            SUM(elapsed_ms)/NULLIF(SUM(count),0) AS mean_ms,SUM(slow_count) AS slow
            FROM analytics_buckets WHERE hour>=date_trunc('hour',$1::timestamptz) AND hour<$2
            GROUP BY source,event,dimension,outcome ORDER BY source,event,dimension,outcome''',start,end)]
        result['collectors']=[dict(r) for r in await c.fetch('SELECT * FROM analytics_collectors ORDER BY source')]
        return result
