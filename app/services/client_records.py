"""Explicit record edits and durable responses tied to an owned order."""
import json
import math
from app.db.core import db
from app.db.repositories import _json_object
from app.services import staff
from app.utils.measurements import validate_measurements

TEXT_FIELDS = {'name':100,'phone':30,'gender':10,'goal':500,'training_history':1000,
               'food_allergy':1000,'food_restriction':1000,'supplements':1000,'notes':4000}
NUMERIC_FIELDS = {'age':(10,100),'height_cm':(100,230),'weight_kg':(25,300),
                  'training_days':(0,7),'nutrition_training_days':(0,14),'workout_days':(0,7)}


async def telegram_media_kind(connection, file):
    """Reuse a Telegram file with its original method, not its filename suffix."""
    source=file['source']
    if source=='chat':
        return await connection.fetchval('SELECT content_type FROM support_messages WHERE id=$1 AND user_id=$2',file['source_id'],file['user_id']) or 'document'
    if source=='information':
        return await connection.fetchval('SELECT content_type FROM order_info_items WHERE id=$1',file['source_id']) or 'document'
    queries={
        'profile':'SELECT body_photo_file_ids FROM users WHERE id=$1',
        'assessment':"SELECT form_snapshot->'body_photo_file_ids' FROM orders WHERE id=$1",
        'record_revisions':"SELECT snapshot->'body_photo_file_ids' FROM record_revisions WHERE id=$1",
        'user_profile_history':"SELECT snapshot->'body_photo_file_ids' FROM user_profile_history WHERE id=$1",
    }
    if source in queries:
        from app.utils.photos import normalize_photos
        photos=await connection.fetchval(queries[source],file['source_id'])
        for photo in normalize_photos(photos):
            if photo.get('file_id')==file['file_id']: return photo['type']
        return 'photo'
    return 'document'


def validate_fields(fields):
    if not isinstance(fields,dict) or not fields or set(fields)-TEXT_FIELDS.keys()-NUMERIC_FIELDS.keys()-{'measurements','photo_ids'}:
        raise ValueError('invalid_fields')
    values={}
    for key,value in fields.items():
        if key=='photo_ids':
            if not isinstance(value,list) or len(value)>6 or any(type(i) is not int or i<=0 for i in value) or len(set(value))!=len(value):
                raise ValueError('invalid_photos')
            values[key]=value
        elif key=='measurements':
            values[key]=validate_measurements(value)
        elif key in TEXT_FIELDS:
            if not isinstance(value,str) or len(value)>TEXT_FIELDS[key] or '\x00' in value:
                raise ValueError('invalid_'+key)
            if key=='gender' and value not in {'مرد','زن','male','female',''}: raise ValueError('invalid_gender')
            values[key]=value.strip()
        else:
            if value is None:
                values[key]=None
                continue
            if isinstance(value,bool): raise ValueError('invalid_'+key)
            try: number=float(value)
            except (ValueError,TypeError): raise ValueError('invalid_'+key) from None
            low,high=NUMERIC_FIELDS[key]
            if not math.isfinite(number) or not low<=number<=high or (key not in {'height_cm','weight_kg'} and not number.is_integer()):
                raise ValueError('invalid_'+key)
            values[key]=number if key in {'height_cm','weight_kg'} else int(number)
    return values


async def edit_record(actor,user_id,fields,version,order_id=None):
    staff.require(actor,'customers.edit')
    values=validate_fields(fields)
    if not isinstance(version,str) or len(version)>50: raise ValueError('version_required')
    async with db.acquire() as c,c.transaction():
        if order_id is None:
            row=await c.fetchrow('SELECT updated_at FROM users WHERE id=$1 FOR UPDATE',user_id)
        else:
            row=await c.fetchrow('SELECT updated_at,form_snapshot FROM orders WHERE id=$1 AND user_id=$2 FOR UPDATE',order_id,user_id)
        if not row: raise ValueError('record_not_found')
        if row['updated_at'].isoformat()!=version: raise ValueError('record_changed')
        if 'photo_ids' in values:
            ids=values.pop('photo_ids')
            photos=[]
            for file_id in ids:
                file=await c.fetchrow('SELECT * FROM client_files WHERE id=$1 AND user_id=$2',file_id,user_id)
                if not file or (file['source']=='chat' and not staff.can(actor,'chats.read')):
                    raise ValueError('invalid_photos')
                from pathlib import Path
                if Path(file['filename']).suffix.lower() not in {'.jpg','.jpeg','.png','.webp'}:
                    raise ValueError('invalid_photos')
                if file['storage_key']:
                    from app.services.content import asset_path,preview_mime
                    import asyncio
                    def inspect():
                        with asset_path(file['storage_key']).open('rb') as stream:
                            return preview_mime(file['filename'],stream.read(64))
                    try: mime=await asyncio.to_thread(inspect)
                    except FileNotFoundError: raise ValueError('photo_unavailable') from None
                    if not mime or not mime.startswith('image/'): raise ValueError('invalid_photos')
                elif not file['file_id']: raise ValueError('photo_unavailable')
                kind=await telegram_media_kind(c,file) if file['file_id'] else 'photo'
                photo={'client_file_id':file_id,'type':'document' if kind=='document' else 'photo'}
                if file['file_id']: photo['file_id']=file['file_id']
                photos.append(photo)
            values['body_photo_file_ids']=photos
            values['body_photo_file_id']=photos[-1].get('file_id') if photos else None
        await c.execute("SELECT set_config('app.record_edit','staff',true)")
        if order_id is None:
            keys=list(values)
            assignments=','.join(f'{key}=${i+2}'+('::jsonb' if key in {'measurements','body_photo_file_ids'} else '') for i,key in enumerate(keys))
            await c.execute(f'UPDATE users SET {assignments},updated_at=NOW() WHERE id=$1',user_id,
                            *[json.dumps(values[k]) if k in {'measurements','body_photo_file_ids'} else values[k] for k in keys])
        else:
            snapshot=_json_object(row['form_snapshot'])
            snapshot.update({{'food_allergy':'allergy','food_restriction':'restriction'}.get(k,k):v for k,v in values.items()})
            await c.execute('UPDATE orders SET form_snapshot=$2::jsonb,updated_at=NOW() WHERE id=$1',order_id,json.dumps(snapshot,ensure_ascii=False))
        await staff.audit(c,actor,'record_updated','order' if order_id else 'customer',order_id or user_id,{'fields':list(values)})


async def request_information(actor,order_id,body):
    staff.require(actor,'orders.review')
    if not isinstance(body,str) or not body.strip() or len(body)>1000: raise ValueError('invalid_message')
    async with db.acquire() as c,c.transaction():
        row=await c.fetchrow("SELECT * FROM orders WHERE id=$1 AND paid_at IS NOT NULL AND status IN ('paid','in_progress') FOR UPDATE",order_id)
        if not row or _json_object(row['product_snapshot']).get('delivery_mode','manual')!='manual': return None
        request_id=await c.fetchval('INSERT INTO order_info_requests(order_id,staff_id,body) VALUES($1,$2,$3) RETURNING id',order_id,actor.get('staff_id',actor.get('id')),body)
        await c.execute("UPDATE order_info_requests SET status='reviewed' WHERE order_id=$1 AND status='submitted'",order_id)
        await c.execute("UPDATE orders SET status='needs_info',updated_at=NOW() WHERE id=$1",order_id)
        await staff.audit(c,actor,'web_needs_info','order',order_id,{'request_id':request_id})
        return request_id


async def owned_request(request_id,tg_id):
    async with db.acquire() as c:
        row=await c.fetchrow('''SELECT r.*,o.user_id,o.status AS order_status FROM order_info_requests r
            JOIN orders o ON o.id=r.order_id JOIN users u ON u.id=o.user_id WHERE r.id=$1 AND u.telegram_id=$2 AND o.paid_at IS NOT NULL''',request_id,tg_id)
        return dict(row) if row else None


async def append_response(request_id,tg_id,item):
    async with db.acquire() as c,c.transaction():
        row=await c.fetchrow('''SELECT r.id FROM order_info_requests r JOIN orders o ON o.id=r.order_id
            JOIN users u ON u.id=o.user_id WHERE r.id=$1 AND u.telegram_id=$2 AND r.status='waiting'
            AND o.status='needs_info' AND o.paid_at IS NOT NULL FOR UPDATE OF r''',request_id,tg_id)
        if not row: return False
        if await c.fetchval('SELECT 1 FROM order_info_items WHERE request_id=$1 AND message_id=$2',request_id,item.get('message_id')):
            return True
        if await c.fetchval('SELECT COUNT(*) FROM order_info_items WHERE request_id=$1',request_id)>=20: raise ValueError('response_full')
        await c.execute('''INSERT INTO order_info_items(request_id,message_id,content_type,content_text,file_id,file_name,file_size,mime_type)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT(request_id,message_id) DO NOTHING''',request_id,
            *[item.get(k) for k in ('message_id','content_type','content_text','file_id','file_name','file_size','mime_type')])
        return True


async def submit_response(request_id,tg_id):
    async with db.acquire() as c,c.transaction():
        # Order lock first, matching staff workflow actions.
        order=await c.fetchrow('''SELECT o.id FROM orders o JOIN users u ON u.id=o.user_id
            JOIN order_info_requests r ON r.order_id=o.id WHERE r.id=$1 AND u.telegram_id=$2
            AND o.status='needs_info' AND o.paid_at IS NOT NULL FOR UPDATE OF o''',request_id,tg_id)
        if not order: return False
        changed=await c.fetchval('''UPDATE order_info_requests SET status='submitted',submitted_at=NOW()
            WHERE id=$1 AND status='waiting' AND EXISTS(SELECT 1 FROM order_info_items WHERE request_id=$1) RETURNING id''',request_id)
        if not changed: return False
        await c.execute("UPDATE orders SET status='paid',updated_at=NOW() WHERE id=$1",order['id'])
        await c.execute("UPDATE staff_assignments SET updated_at=NOW(),seen_at=NULL WHERE target_type='order' AND target_id=$1",order['id'])
        return True


async def response_summary(request_id,tg_id):
    async with db.acquire() as c:
        return await c.fetch('''SELECT i.content_text,i.file_name,i.content_type FROM order_info_items i
            JOIN order_info_requests r ON r.id=i.request_id JOIN orders o ON o.id=r.order_id
            JOIN users u ON u.id=o.user_id WHERE r.id=$1 AND u.telegram_id=$2 ORDER BY i.id LIMIT 20''',request_id,tg_id)
