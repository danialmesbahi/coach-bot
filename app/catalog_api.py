"""Leader-only catalog management; historical purchases retain their own terms."""
import asyncio
import json
import logging
import secrets

from aiohttp import web
from app.db.core import db
from app.services import staff
from app.services.catalog import validate_product, object_value
from app.services.content import store_upload, asset_path, preview_mime
from app.config import get_settings


async def catalog(request):
    from app.webapp import response, _safe_page
    staff.require(request['actor'],'catalog.manage')
    page=_safe_page(request)
    async with db.acquire() as c:
        total=await c.fetchval('SELECT COUNT(*) FROM products WHERE NOT archived')
        rows=await c.fetch('''SELECT p.*,a.filename FROM products p LEFT JOIN product_assets a ON a.id=p.asset_id
            WHERE NOT p.archived ORDER BY p.sort_order,p.id LIMIT 21 OFFSET $1''',(page-1)*20)
        next_id=rows[20]['id'] if len(rows)>20 else None
        rows=rows[:20]
        channels=await c.fetch('SELECT * FROM managed_channels ORDER BY title LIMIT 100')
        asset_ids=list({a for row in rows for a in row['asset_ids']})
        assets={r['id']:dict(r) for r in await c.fetch('SELECT id,filename,byte_size FROM product_assets WHERE id=ANY($1::bigint[])',asset_ids)}
    items=[dict(row) for row in rows]
    for item in items:
        for key in ('form_fields','questions','content_urls'): item[key]=object_value(item[key])
        item['assets']=[assets[a] for a in item['asset_ids'] if a in assets]
    return response({'items':items,'total':total,'page':page,'pageSize':20,'next_id':next_id,
        'download_base_configured':bool(get_settings().public_base_url),'channels':[dict(r) for r in channels]})


async def catalog_save(request):
    from app.webapp import response
    staff.require(request['actor'],'catalog.manage')
    async with asyncio.timeout(5):
        body=await request.clone(client_max_size=32768).json()
    try:
        data=validate_product(body)
    except (ValueError,TypeError) as exc:
        logging.getLogger(__name__).warning('Product validation failed',extra={'event':'product_invalid','error_code':str(exc)})
        return response({'error':'invalid_product','field':str(exc)},400)
    product_id=int(request.match_info['product_id']) if 'product_id' in request.match_info else None
    async with db.acquire() as c,c.transaction():
        await c.execute('SELECT pg_advisory_xact_lock(917003)')
        if len(data['asset_ids'])!=await c.fetchval('SELECT COUNT(*) FROM product_assets WHERE id=ANY($1::bigint[])',data['asset_ids']):
            return response({'error':'asset_missing'},400)
        if data['active'] and data['delivery_mode']=='content' and not get_settings().public_base_url:
            needs_link=await c.fetchval(
                'SELECT EXISTS(SELECT 1 FROM product_assets WHERE id=ANY($1::bigint[]) AND byte_size>$2 AND file_id IS NULL)',data['asset_ids'],50*1024*1024)
            if needs_link:
                logging.getLogger(__name__).warning('Download domain missing',extra={'event':'product_invalid','error_code':'download_base_required'})
                return response({'error':'download_base_required'},400)
        if data['channel_id'] and not await c.fetchval('SELECT chat_id FROM managed_channels WHERE chat_id=$1',data['channel_id']):
            return response({'error':'channel_not_connected'},400)
        keys=list(data)
        values=[json.dumps(data[k],ensure_ascii=False) if k in ('form_fields','questions','content_urls') else data[k] for k in keys]
        if product_id:
            if type(body.get('version')) is not int: return response({'error':'version_required'},400)
            assignments=','.join(f'{key}=${i+1}' for i,key in enumerate(keys))
            row=await c.fetchrow(f'''UPDATE products SET {assignments},version=version+1,updated_at=NOW()
                WHERE id=${len(keys)+1} AND version=${len(keys)+2} AND NOT archived RETURNING id''',*values,product_id,body['version'])
            if not row: return response({'error':'product_changed'},409)
        else:
            placeholders=','.join(f'${i+1}' for i in range(len(keys)+1))
            row=await c.fetchrow(f'INSERT INTO products({",".join(keys)},code) VALUES({placeholders}) RETURNING id',*values,'course_'+secrets.token_hex(6))
        if 'before_id' in body:
            before=body['before_id']
            if before is not None and (type(before) is not int or before==row['id']):
                raise web.HTTPBadRequest(text='Invalid position')
            await move_product(c,row['id'],before)
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
    from app.webapp import response, _rate_limited
    staff.require(request['actor'],'catalog.manage')
    if await _rate_limited(request,'catalog_upload',60): return response({'error':'rate_limited'},429)
    if request.app['catalog_upload_slots'].locked(): return response({'error':'uploads_busy'},503)
    async with request.app['catalog_upload_slots']:
        part=await (await request.multipart()).next()
        if not part or part.name!='file' or not part.filename: return response({'error':'file_required'},400)
        try:
            key,filename,size=await store_upload(part)
        except (web.HTTPException,TimeoutError) as exc:
            status=exc.status if isinstance(exc,web.HTTPException) else 408
            code={400:'invalid_file_type',408:'upload_timeout',507:'storage_full'}.get(status,'upload_failed')
            logging.getLogger(__name__).warning('Catalog upload failed',extra={'event':'catalog_upload_failed','error_code':code})
            return response({'error':code},status)
        try:
            async with db.acquire() as c,c.transaction():
                asset_id=await c.fetchval('INSERT INTO product_assets(filename,storage_key,byte_size) VALUES($1,$2,$3) RETURNING id',filename,key,size)
                await staff.audit(c,request['actor'],'product_asset_uploaded','product_asset',asset_id)
        except BaseException:
            asset_path(key).unlink(missing_ok=True)
            raise
    return response({'id':asset_id,'filename':filename,'byte_size':size})


async def catalog_asset_preview(request):
    """Authenticated, range-capable media; never render arbitrary coach attachments."""
    staff.require(request['actor'],'catalog.manage')
    async with db.acquire() as c:
        asset=await c.fetchrow('SELECT filename,storage_key,payload FROM product_assets WHERE id=$1',int(request.match_info['asset_id']))
    if not asset: raise web.HTTPNotFound()
    path=asset_path(asset['storage_key']) if asset['storage_key'] else None
    def head():
        with path.open('rb') as stream: return stream.read(64)
    try:
        data=await asyncio.to_thread(head) if path else bytes(asset['payload'] or b'')[:64]
    except FileNotFoundError:
        raise web.HTTPNotFound()
    mime=preview_mime(asset['filename'],data)
    if not mime: raise web.HTTPUnsupportedMediaType()
    headers={'Content-Type':mime,'Cache-Control':'private, no-store',
             'X-Content-Type-Options':'nosniff','Content-Disposition':'inline'}
    if path: return web.FileResponse(path,headers=headers)
    return web.Response(body=bytes(asset['payload']),headers=headers)


async def move_product(c,product_id,before_id):
    rows=await c.fetch('SELECT id,sort_order FROM products WHERE NOT archived ORDER BY sort_order,id FOR UPDATE')
    ids=[r['id'] for r in rows if r['id']!=product_id]
    if before_id is not None and before_id not in ids:
        raise web.HTTPConflict(text='Product position changed')
    ids.insert(ids.index(before_id) if before_id is not None else len(ids),product_id)
    original={r['id']:r['sort_order'] for r in rows}
    await c.executemany('UPDATE products SET sort_order=$2,version=version+1,updated_at=NOW() WHERE id=$1',
        [(pid,index) for index,pid in enumerate(ids) if original.get(pid)!=index])


async def catalog_reorder(request):
    from app.webapp import response
    staff.require(request['actor'],'catalog.manage')
    async with asyncio.timeout(5):
        body=await request.clone(client_max_size=256).json()
    if not isinstance(body,dict) or type(body.get('id')) is not int or type(body.get('version')) is not int:
        raise web.HTTPBadRequest()
    before=body.get('before_id')
    if before is not None and (type(before) is not int or before==body['id']): raise web.HTTPBadRequest()
    async with db.acquire() as c,c.transaction():
        await c.execute('SELECT pg_advisory_xact_lock(917003)')
        if not await c.fetchval('SELECT id FROM products WHERE id=$1 AND version=$2 AND NOT archived',body['id'],body['version']):
            return response({'error':'product_changed'},409)
        await move_product(c,body['id'],before)
        await staff.audit(c,request['actor'],'product_reordered','product',body['id'])
    request.app['read_cache'].clear()
    return response({'ok':True})


async def catalog_channel(request):
    from app.webapp import response, _rate_limited
    staff.require(request['actor'],'catalog.manage')
    if await _rate_limited(request,'catalog_channel',6): return response({'error':'rate_limited'},429)
    async with asyncio.timeout(5):
        body=await request.clone(client_max_size=256).json()
    chat_id=body.get('chat_id') if isinstance(body,dict) else None
    if type(chat_id) is not int or not -(2**52)<chat_id<0: return response({'error':'invalid_channel_id'},400)
    bot=request.app['bot']
    slots=request.app['channel_slots']
    if slots.locked(): return response({'error':'channel_busy'},503)
    try:
        async with slots,asyncio.timeout(15):
            chat=await bot.get_chat(chat_id)
            member=await bot.get_chat_member(chat_id,bot.id)
        if chat.type!='channel' or chat.username or member.status!='administrator' or not member.can_invite_users or not member.can_restrict_members:
            return response({'error':'private_channel_admin_required'},400)
    except Exception:
        logging.getLogger(__name__).warning('Channel verification failed',exc_info=True)
        return response({'error':'channel_unavailable'},400)
    async with db.acquire() as c,c.transaction():
        await c.execute('''INSERT INTO managed_channels(chat_id,title) VALUES($1,$2) ON CONFLICT(chat_id)
            DO UPDATE SET title=$2,verified_at=NOW(),last_error=NULL''',chat_id,chat.title)
        await staff.audit(c,request['actor'],'channel_connected','channel',chat_id)
    return response({'ok':True,'title':chat.title})


def routes():
    return [web.get('/api/catalog',catalog),web.post('/api/catalog',catalog_save),
            web.post('/api/catalog/{product_id:\\d+}',catalog_save),web.post('/api/catalog/{product_id:\\d+}/archive',catalog_archive),
            web.post('/api/catalog-assets',catalog_asset),web.get('/api/catalog-assets/{asset_id:\\d+}/preview',catalog_asset_preview),
            web.post('/api/catalog-channels',catalog_channel),
            web.post('/api/catalog-order',catalog_reorder)]
