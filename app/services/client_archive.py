"""Bounded private archive; retries never run on the payment/delivery worker."""
import asyncio
import logging
import secrets
import shutil
from pathlib import Path
from app.db.core import db
from app.services.content import asset_path, inspect_file

log=logging.getLogger(__name__)


async def index_existing():
    """Resume one bounded history batch per pass, without scanning the archive."""
    async with db.acquire() as c,c.transaction():
        cursor=await c.fetchrow('SELECT * FROM client_archive_cursors ORDER BY source LIMIT 1 FOR UPDATE SKIP LOCKED')
        if not cursor: return
        table=cursor['source']  # Fixed migration-owned table names, never user input.
        if table=='order_content_delivery':
            rows=await c.fetch('''SELECT * FROM order_content_delivery WHERE (order_id,asset_id)>($1,$2)
                ORDER BY order_id,asset_id LIMIT 100''',cursor['last_id'],cursor['last_asset_id'])
            for row in rows:
                await c.execute("""INSERT INTO client_files(user_id,order_id,source,source_id,asset_id,filename,storage_key,byte_size,status,file_id)
                    SELECT o.user_id,o.id,'content',o.id,a.id,a.filename,a.storage_key,a.byte_size,
                        CASE WHEN a.storage_key IS NOT NULL THEN 'archived' ELSE 'pending' END,COALESCE($3,a.file_id)
                    FROM orders o JOIN product_assets a ON a.id=$2 WHERE o.id=$1 ON CONFLICT DO NOTHING""",row['order_id'],row['asset_id'],row['file_id'])
            if rows:
                await c.execute('UPDATE client_archive_cursors SET last_id=$2,last_asset_id=$3 WHERE source=$1',table,rows[-1]['order_id'],rows[-1]['asset_id'])
            else: await c.execute('DELETE FROM client_archive_cursors WHERE source=$1',table)
            return
        rows=await c.fetch(f'SELECT * FROM {table} WHERE id>$1 ORDER BY id LIMIT 100',cursor['last_id'])
        for row in rows:
            if table in {'orders','users','user_profile_history'}:
                from app.utils.photos import normalize_photos
                from app.db.repositories import _json_object
                data=_json_object(row['form_snapshot']) if table=='orders' else _json_object(row['snapshot']) if table=='user_profile_history' else row
                raw=data.get('body_photo_file_ids') or ([data['body_photo_file_id']] if data.get('body_photo_file_id') else [])
                for photo in normalize_photos(raw):
                    if photo.get('client_file_id') or not photo.get('file_id'): continue
                    await c.execute("""INSERT INTO client_files(user_id,order_id,source,source_id,file_id,filename,mime_type)
                        VALUES($1,$2,$3,$4,$5,'body-photo.jpg','image/jpeg') ON CONFLICT DO NOTHING""",
                        row['id'] if table=='users' else row['user_id'],row['id'] if table=='orders' else row['order_id'] if table=='user_profile_history' else None,
                        'assessment' if table=='orders' else 'profile' if table=='users' else 'user_profile_history',row['id'],photo['file_id'])
                if table=='orders' and row['plan_file_id']:
                    await c.execute("""INSERT INTO client_files(user_id,order_id,source,source_id,file_id,filename)
                        VALUES($1,$2,'legacy_delivery',$2,$3,$4) ON CONFLICT DO NOTHING""",row['user_id'],row['id'],row['plan_file_id'],row['plan_file_name'] or 'plan')
            elif table=='support_messages' and row['file_id']:
                await c.execute("""INSERT INTO client_files(user_id,source,source_id,file_id,filename,mime_type,byte_size)
                    VALUES($1,'chat',$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING""",row['user_id'],row['id'],row['file_id'],row['file_name'] or ('photo.jpg' if row['content_type']=='photo' else 'attachment'),row['mime_type'],row['file_size'])
            elif table=='manual_delivery_items' and row['asset_id']:
                await c.execute("""INSERT INTO client_files(user_id,order_id,source,source_id,asset_id,filename,storage_key,byte_size,status,file_id)
                    SELECT o.user_id,o.id,'delivery',$1,a.id,a.filename,a.storage_key,a.byte_size,
                        CASE WHEN a.storage_key IS NOT NULL THEN 'archived' ELSE 'pending' END,a.file_id
                    FROM orders o JOIN product_assets a ON a.id=$3 WHERE o.id=$2 ON CONFLICT DO NOTHING""",row['id'],row['order_id'],row['asset_id'])
        if rows: await c.execute('UPDATE client_archive_cursors SET last_id=$2 WHERE source=$1',table,rows[-1]['id'])
        else: await c.execute('DELETE FROM client_archive_cursors WHERE source=$1',table)


async def archive_one(bot):
    async with db.acquire() as c,c.transaction():
        row=await c.fetchrow("""SELECT * FROM client_files WHERE
            (status='pending' OR status='archiving') AND next_at<=NOW()
            ORDER BY next_at,id LIMIT 1 FOR UPDATE SKIP LOCKED""")
        if not row: return False
        await c.execute("UPDATE client_files SET status='archiving',next_at=NOW()+INTERVAL '5 minutes',attempts=attempts+1 WHERE id=$1",row['id'])
    key=secrets.token_hex(24); path=asset_path(key); committed=False
    try:
        async with asyncio.timeout(120):
            if row['asset_id']:
                async with db.acquire() as c:
                    asset=await c.fetchrow('SELECT storage_key,file_id FROM product_assets WHERE id=$1',row['asset_id'])
                if asset and asset['storage_key']:
                    async with db.acquire() as c:
                        await c.execute("UPDATE client_files SET storage_key=$2,status='archived',error=NULL WHERE id=$1",row['id'],asset['storage_key'])
                    return True
                row=dict(row)
                row['file_id']=row['file_id'] or (asset['file_id'] if asset else None)
            if not row['file_id']: raise ValueError('archive_source_unavailable')
            async with db.acquire() as c:
                existing=await c.fetchrow("SELECT storage_key,filename FROM client_files WHERE file_id=$1 AND status='archived' AND storage_key IS NOT NULL LIMIT 1",row['file_id'])
                if existing and asset_path(existing['storage_key']).is_file():
                    filename=existing['filename'] if row['filename']=='body-photo.jpg' else row['filename']
                    await c.execute("UPDATE client_files SET storage_key=$2,filename=$3,status='archived',error=NULL WHERE id=$1",row['id'],existing['storage_key'],filename)
                    return True
            remote=await bot.get_file(row['file_id'])
            size=remote.file_size
            if size is None or size>20*1024*1024:
                # Telegram's hosted getFile ceiling: retain the remote reference.
                async with db.acquire() as c:
                    await c.execute("UPDATE client_files SET status='remote',error='archive_size_limit' WHERE id=$1",row['id'])
                return True
            usage=await asyncio.to_thread(shutil.disk_usage,path.parent)
            if usage.free<size+max(1024**3,usage.total//5): raise OSError('storage_reserve')
            await bot.download_file(remote.file_path,destination=path,timeout=100)
            filename=row['filename']
            # Historical assessment rows lack document filenames. Preserve a validated
            # raster format instead of rejecting a PNG/WEBP as a synthetic JPEG.
            if filename=='body-photo.jpg':
                suffix=Path(remote.file_path or '').suffix.lower()
                if suffix in {'.jpg','.jpeg','.png','.webp'}: filename='body-photo'+suffix
            if path.stat().st_size!=size or not await asyncio.to_thread(inspect_file,path,filename):
                raise ValueError('invalid_archive')
            async with db.acquire() as c:
                await c.execute("UPDATE client_files SET storage_key=$2,byte_size=$3,filename=$4,status='archived',error=NULL WHERE id=$1",row['id'],key,size,filename)
            committed=True
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception('Client attachment archive failed',extra={'event':'client_archive_failed','file_record_id':row['id']})
        async with db.acquire() as c:
            await c.execute("""UPDATE client_files SET status=CASE WHEN attempts>=5 THEN 'remote' ELSE 'pending' END,
                error='archive_failed',next_at=NOW()+INTERVAL '30 minutes' WHERE id=$1""",row['id'])
    finally:
        if not committed: path.unlink(missing_ok=True)
    return True


async def run_client_archive_loop(bot):
    while True:
        try:
            await index_existing()
            worked=await archive_one(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Client archive worker failed')
            worked=False
        await asyncio.sleep(1 if worked else 30)
