"""Staff-authorized client records and private files."""
import asyncio
from urllib.parse import quote
from aiohttp import web
from app.db.core import db
from app.services import staff, client_records
from app.services.content import asset_path, store_upload, preview_mime


async def client_record(request):
    from app.webapp import response, _rate_limited
    user_id=int(request.match_info['user_id'])
    if request.method=='POST':
        staff.require(request['actor'],'customers.edit')
        if await _rate_limited(request,'record_edit',20): return response({'error':'rate_limited'},429)
        body=await request.json()
        if not isinstance(body,dict): return response({'error':'invalid_payload'},400)
        order_id=body.get('order_id')
        if order_id is not None and (type(order_id) is not int or order_id<=0): return response({'error':'invalid_order'},400)
        try: await client_records.edit_record(request['actor'],user_id,body.get('fields'),body.get('version'),order_id)
        except ValueError as exc: return response({'error':str(exc)},409 if str(exc)=='record_changed' else 400)
        request.app['read_cache'].clear()
        return response({'ok':True})
    async with db.acquire() as c:
        user=await c.fetchrow('SELECT * FROM users WHERE id=$1',user_id)
        if not user: raise web.HTTPNotFound()
        order_id=request.query.get('order_id')
        if order_id is not None:
            if not order_id.isdigit() or len(order_id)>15: raise web.HTTPBadRequest()
            order_id=int(order_id)
            if not await c.fetchval('SELECT 1 FROM orders WHERE id=$1 AND user_id=$2',order_id,user_id): raise web.HTTPNotFound()
        from app.utils.photos import normalize_photos
        photo_values=user['body_photo_file_ids']
        if order_id:
            order=await c.fetchrow('SELECT form_snapshot,updated_at FROM orders WHERE id=$1',order_id)
            snapshot=client_records._json_object(order['form_snapshot'])
            photo_values=snapshot.get('body_photo_file_ids',[])
        photo_ids=[]
        for photo in normalize_photos(photo_values):
            file_id=photo.get('client_file_id') or await c.fetchval('SELECT id FROM client_files WHERE user_id=$1 AND file_id=$2 ORDER BY id DESC LIMIT 1',user_id,photo.get('file_id'))
            if file_id and file_id not in photo_ids: photo_ids.append(file_id)
        def cursor(key):
            value=request.query.get(key,'')
            return int(value) if value.isdigit() and len(value)<19 else 2**63-1
        revisions=await c.fetch("SELECT id,order_id,snapshot,created_at FROM record_revisions WHERE origin='staff' AND user_id=$1 AND id<$2 AND ($3::bigint IS NULL OR order_id=$3) ORDER BY id DESC LIMIT 20",user_id,cursor('revisions_before'),order_id)
        files=await c.fetch('''SELECT id,order_id,source,filename,status,error,byte_size,created_at FROM client_files
            WHERE user_id=$1 AND id<$2 AND (source<>'chat' OR $3) AND ($4::bigint IS NULL OR order_id=$4) ORDER BY id DESC LIMIT 20''',user_id,cursor('files_before'),staff.can(request['actor'],'chats.read'),order_id)
    values={k:user[k] for k in {*client_records.TEXT_FIELDS,*client_records.NUMERIC_FIELDS,'measurements','updated_at'} if k in user}
    values['measurements']=client_records._json_object(values.get('measurements'))
    values['photo_ids']=photo_ids
    safe=[]
    for row in revisions:
        item=dict(row); snapshot=client_records._json_object(item['snapshot'])
        item['snapshot']={k:v for k,v in snapshot.items() if k in {*client_records.TEXT_FIELDS,*client_records.NUMERIC_FIELDS,'measurements','allergy','restriction'}}
        safe.append(item)
    return response({'values':values,'revisions':safe,'files':[dict(r) for r in files]})


async def client_file_list(request):
    from app.webapp import response
    staff.require(request['actor'],'client.files.read')
    before=request.query.get('before','')
    cursor=int(before) if before.isdigit() and len(before)<19 else 2**63-1
    async with db.acquire() as c:
        rows=await c.fetch('''SELECT id,filename,source,order_id,status,byte_size,created_at FROM client_files
            WHERE user_id=$1 AND id<$2 AND (source<>'chat' OR $3) ORDER BY id DESC LIMIT 20''',int(request.match_info['user_id']),cursor,staff.can(request['actor'],'chats.read'))
    return response({'files':[dict(r) for r in rows]})


async def client_file_upload(request):
    from app.webapp import response, _rate_limited
    staff.require(request['actor'],'customers.files')
    if request.app['upload_slots'].locked(): return response({'error':'uploads_busy'},503)
    if await _rate_limited(request,'record_upload',10): return response({'error':'rate_limited'},429)
    user_id=int(request.match_info['user_id']); order_id=request.query.get('order_id')
    if order_id is not None and (not order_id.isdigit() or len(order_id)>15): raise web.HTTPBadRequest()
    order_id=int(order_id) if order_id else None
    async with db.acquire() as c:
        if not await c.fetchval('SELECT 1 FROM users WHERE id=$1',user_id): raise web.HTTPNotFound()
        if order_id and not await c.fetchval('SELECT 1 FROM orders WHERE id=$1 AND user_id=$2',order_id,user_id): raise web.HTTPNotFound()
    key=None; committed=False
    try:
        async with asyncio.timeout(180),request.app['upload_slots']:
            reader=await request.multipart(); part=await reader.next()
            if not part or part.name!='file' or not part.filename: raise web.HTTPBadRequest()
            key,filename,size=await store_upload(part,max_bytes=50*1024*1024)
            async with db.acquire() as c,c.transaction():
                file_id=await c.fetchval('''INSERT INTO client_files(user_id,order_id,source,source_id,filename,storage_key,byte_size,status)
                    VALUES($1,$2,'staff',0,$3,$4,$5,'archived') RETURNING id''',user_id,order_id,filename,key,size)
                await staff.audit(c,request['actor'],'client_file_added','customer',user_id,{'file_id':file_id,'order_id':order_id})
            committed=True
            return response({'ok':True,'id':file_id})
    finally:
        if key and not committed: asset_path(key).unlink(missing_ok=True)


async def client_file(request):
    async with db.acquire() as c:
        row=await c.fetchrow('SELECT * FROM client_files WHERE id=$1',int(request.match_info['file_id']))
    if not row: raise web.HTTPNotFound()
    staff.require(request['actor'],'chats.read' if row['source']=='chat' else 'client.files.read')
    result=await stored_response(request,row)
    if result is not None: return result
    if row['file_id']:
        from app.webapp import _telegram_media
        return await _telegram_media(request,row['file_id'],row['mime_type'] or 'application/octet-stream',row['filename'])
    raise web.HTTPNotFound()


async def stored_response(request,row):
    if row['storage_key']:
        path=asset_path(row['storage_key'])
        def head():
            with path.open('rb') as stream: return stream.read(64)
        try: data=await asyncio.to_thread(head)
        except FileNotFoundError: return None
        mime=preview_mime(row['filename'],data)
        if row['filename'].lower().endswith('.pdf') and data.startswith(b'%PDF-'): mime='application/pdf'
        if request.query.get('download')=='1': mime=None
        headers={'Content-Type':mime or 'application/octet-stream','X-Content-Type-Options':'nosniff',
                 'Cache-Control':'private, no-store','Content-Disposition':('inline' if mime else 'attachment')+"; filename*=UTF-8''"+quote(row['filename'],safe='')}
        return web.FileResponse(path,headers=headers)
    return None


async def archived_response(request,file_id):
    """Call only after the originating message/order/profile permission check."""
    async with db.acquire() as c:
        row=await c.fetchrow("SELECT storage_key,filename FROM client_files WHERE file_id=$1 AND status='archived' AND storage_key IS NOT NULL LIMIT 1",file_id)
    return await stored_response(request,row) if row else None


async def order_information(request):
    from app.webapp import response
    order_id=int(request.match_info['order_id'])
    async with db.acquire() as c:
        rows=await c.fetch('SELECT id,body,status,created_at,submitted_at,notification_sent FROM order_info_requests WHERE order_id=$1 ORDER BY id DESC LIMIT 10',order_id)
        items=await c.fetch('''SELECT i.id,i.request_id,i.content_type,i.content_text,i.file_name,i.created_at,
            (SELECT f.id FROM client_files f WHERE f.source='information' AND f.source_id=i.id LIMIT 1) AS attachment_id
            FROM order_info_items i WHERE request_id=ANY($1::bigint[]) ORDER BY i.id''',[r['id'] for r in rows])
    return response({'requests':[dict(r) for r in rows],'items':[dict(i) for i in items]})


def routes():
    return [web.get('/api/customers/{user_id:\\d+}/record',client_record),web.post('/api/customers/{user_id:\\d+}/record',client_record),
            web.get('/api/customers/{user_id:\\d+}/files',client_file_list),web.post('/api/customers/{user_id:\\d+}/files',client_file_upload),web.get('/media/client-files/{file_id:\\d+}',client_file),
            web.get('/api/orders/{order_id:\\d+}/information',order_information)]
