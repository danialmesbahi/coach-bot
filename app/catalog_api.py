"""Leader-only catalog management; historical purchases retain their own terms."""
import asyncio
import json
import secrets
from pathlib import Path

from aiohttp import web
from app.db.core import db
from app.services import staff
from app.services.catalog import validate_product, object_value
from app.utils.media import _inspect_upload


async def catalog(request):
    from app.webapp import response, _safe_page
    staff.require(request['actor'],'catalog.manage')
    page=_safe_page(request)
    async with db.acquire() as c:
        total=await c.fetchval('SELECT COUNT(*) FROM products WHERE NOT archived')
        rows=await c.fetch('''SELECT p.*,a.filename FROM products p LEFT JOIN product_assets a ON a.id=p.asset_id
            WHERE NOT p.archived ORDER BY p.sort_order,p.id LIMIT 20 OFFSET $1''',(page-1)*20)
        channels=await c.fetch('SELECT * FROM managed_channels ORDER BY title LIMIT 100')
    items=[dict(row) for row in rows]
    for item in items:
        for key in ('form_fields','questions'): item[key]=object_value(item[key])
    return response({'items':items,'total':total,'page':page,'pageSize':20,'channels':[dict(r) for r in channels]})


async def catalog_save(request):
    from app.webapp import response
    staff.require(request['actor'],'catalog.manage')
    body=await request.json()
    try:
        data=validate_product(body)
    except (ValueError,TypeError) as exc:
        return response({'error':'invalid_product','field':str(exc)},400)
    product_id=int(request.match_info['product_id']) if 'product_id' in request.match_info else None
    async with db.acquire() as c,c.transaction():
        if data['asset_id'] and not await c.fetchval('SELECT id FROM product_assets WHERE id=$1',data['asset_id']):
            return response({'error':'asset_missing'},400)
        if data['channel_id'] and not await c.fetchval('SELECT chat_id FROM managed_channels WHERE chat_id=$1',data['channel_id']):
            return response({'error':'channel_not_connected'},400)
        keys=list(data)
        values=[json.dumps(data[k],ensure_ascii=False) if k in ('form_fields','questions') else data[k] for k in keys]
        if product_id:
            if type(body.get('version')) is not int: return response({'error':'version_required'},400)
            assignments=','.join(f'{key}=${i+1}' for i,key in enumerate(keys))
            row=await c.fetchrow(f'''UPDATE products SET {assignments},version=version+1,updated_at=NOW()
                WHERE id=${len(keys)+1} AND version=${len(keys)+2} AND NOT archived RETURNING id''',*values,product_id,body['version'])
            if not row: return response({'error':'product_changed'},409)
        else:
            placeholders=','.join(f'${i+1}' for i in range(len(keys)+1))
            row=await c.fetchrow(f'INSERT INTO products({",".join(keys)},code) VALUES({placeholders}) RETURNING id',*values,'course_'+secrets.token_hex(6))
        await staff.audit(c,request['actor'],'product_saved','product',row['id'])
    request.app['read_cache'].clear()
    return response({'ok':True,'id':row['id']})


async def catalog_archive(request):
    from app.webapp import response
    staff.require(request['actor'],'catalog.manage')
    async with db.acquire() as c,c.transaction():
        row=await c.fetchrow('UPDATE products SET archived=true,active=false,version=version+1,updated_at=NOW() WHERE id=$1 AND NOT archived RETURNING id',int(request.match_info['product_id']))
        if not row: raise web.HTTPNotFound()
        await staff.audit(c,request['actor'],'product_archived','product',row['id'])
    request.app['read_cache'].clear()
    return response({'ok':True})


async def catalog_asset(request):
    from app.webapp import response, _read_part, _rate_limited
    staff.require(request['actor'],'catalog.manage')
    if await _rate_limited(request,'catalog_upload',6): return response({'error':'rate_limited'},429)
    if request.app['upload_slots'].locked(): return response({'error':'uploads_busy'},503)
    async with request.app['upload_slots'],asyncio.timeout(45):
        part=await (await request.multipart()).next()
        if not part or part.name!='file' or not part.filename: return response({'error':'file_required'},400)
        filename=Path(part.filename.replace('\\','/').rsplit('/',1)[-1]).name[:150]
        payload=await _read_part(part,10*1024*1024)
        if not _inspect_upload(filename,payload): return response({'error':'invalid_file_type'},400)
        async with db.acquire() as c,c.transaction():
            asset_id=await c.fetchval('INSERT INTO product_assets(filename,payload) VALUES($1,$2) RETURNING id',filename,payload)
            await staff.audit(c,request['actor'],'product_asset_uploaded','product_asset',asset_id)
    return response({'id':asset_id,'filename':filename})


async def catalog_channel(request):
    from app.webapp import response
    staff.require(request['actor'],'catalog.manage')
    body=await request.json()
    chat_id=body.get('chat_id') if isinstance(body,dict) else None
    if type(chat_id) is not int or not -(2**52)<chat_id<0: return response({'error':'invalid_channel_id'},400)
    bot=request.app['bot']
    try:
        async with asyncio.timeout(15):
            chat=await bot.get_chat(chat_id)
            member=await bot.get_chat_member(chat_id,bot.id)
        if chat.type!='channel' or chat.username or member.status!='administrator' or not member.can_invite_users or not member.can_restrict_members:
            return response({'error':'private_channel_admin_required'},400)
    except Exception:
        return response({'error':'channel_unavailable'},400)
    async with db.acquire() as c,c.transaction():
        await c.execute('''INSERT INTO managed_channels(chat_id,title) VALUES($1,$2) ON CONFLICT(chat_id)
            DO UPDATE SET title=$2,verified_at=NOW(),last_error=NULL''',chat_id,chat.title)
        await staff.audit(c,request['actor'],'channel_connected','channel',chat_id)
    return response({'ok':True,'title':chat.title})


def routes():
    return [web.get('/api/catalog',catalog),web.post('/api/catalog',catalog_save),
            web.post('/api/catalog/{product_id:\\d+}',catalog_save),web.post('/api/catalog/{product_id:\\d+}/archive',catalog_archive),
            web.post('/api/catalog-assets',catalog_asset),web.post('/api/catalog-channels',catalog_channel)]
