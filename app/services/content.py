"""Private streamed catalog files and purchase-bound download links."""
import asyncio
import codecs
import hashlib
import os
import secrets
import shutil
import struct
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile, BadZipFile

from aiohttp import web
from app.config import get_settings
from app.db.core import db
from app.services.catalog import object_value
from app.utils.media import _inspect_upload, SAFE_UPLOAD_TYPES


def asset_root():
    root=Path(os.environ.get('CATALOG_STORAGE','artifacts/catalog-files'))
    root.mkdir(parents=True,exist_ok=True)
    return root


def asset_path(key):
    if not isinstance(key,str) or len(key)!=48 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('invalid storage key')
    return asset_root()/key


def inspect_file(path,filename):
    """Check known formats; other coach files are opaque download-only attachments.

    This is not a malware scanner. Never execute, extract or serve these files inline.
    """
    suffix=Path(filename).suffix.lower()
    with path.open('rb') as stream:
        head=stream.read(65536)
        if suffix not in SAFE_UPLOAD_TYPES:
            return bool(head)
        if suffix in {'.docx','.xlsx'}:
            stream.seek(max(0,path.stat().st_size-65557))
            tail=stream.read(65557)
            index=tail.rfind(b'PK\x05\x06')
            if index<0 or len(tail)-index<22: return False
            entries=struct.unpack_from('<H',tail,index+10)[0]
            directory_size=struct.unpack_from('<I',tail,index+12)[0]
            if entries>1000 or directory_size>1024*1024: return False
            try:
                with ZipFile(path) as archive:
                    names=set(archive.namelist())
                    return '[Content_Types].xml' in names and ('word/document.xml' if suffix=='.docx' else 'xl/workbook.xml') in names
            except (BadZipFile,OSError): return False
        if suffix=='.txt':
            decoder=codecs.getincrementaldecoder('utf-8')()
            stream.seek(0)
            try:
                while chunk:=stream.read(1024*1024):
                    if b'\x00' in chunk: return False
                    decoder.decode(chunk)
                decoder.decode(b'',final=True)
                return bool(head)
            except UnicodeDecodeError: return False
        return bool(_inspect_upload(filename,head))


def preview_mime(filename,head):
    """Only validated raster images / video are eligible for inline catalog previews."""
    suffix=Path(filename).suffix.lower()
    if suffix=='.mov' and head[4:8] in {b'ftyp',b'moov',b'wide'}:
        return 'video/quicktime'
    if suffix=='.webm' and head.startswith(b'\x1a\x45\xdf\xa3'):
        return 'video/webm'
    if suffix in {'.jpg','.jpeg','.png','.webp','.gif','.mp4'}:
        inspected=_inspect_upload(filename,head)
        if inspected: return inspected[0]
    return None


async def store_upload(part,max_bytes=None):
    filename=Path(part.filename.replace('\\','/')).name[:150]
    filename=''.join(c for c in filename if ord(c)>=32 and ord(c)!=127)
    if not filename or filename in {'.','..'}:
        raise web.HTTPBadRequest(text='Invalid filename')
    key=secrets.token_hex(24); path=asset_path(key); size=0
    try:
        with path.open('xb') as stream:
            while True:
                async with asyncio.timeout(30):
                    chunk=await part.read_chunk(1024*1024)
                if not chunk: break
                if max_bytes is not None and size+len(chunk)>max_bytes:
                    raise web.HTTPRequestEntityTooLarge(max_size=max_bytes,actual_size=size+len(chunk))
                # No per-file ceiling, but never let catalog uploads fill the server.
                # Check each 1 MiB chunk, keeping 20% of the volume (at least 1 GiB) free.
                usage=await asyncio.to_thread(shutil.disk_usage,path.parent)
                if usage.free<len(chunk)+max(1024**3,usage.total//5):
                    raise web.HTTPInsufficientStorage(text='Storage reserve reached')
                task=asyncio.create_task(asyncio.to_thread(stream.write,chunk))
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    await task
                    raise
                size+=len(chunk)
        if not await asyncio.to_thread(inspect_file,path,filename):
            raise web.HTTPBadRequest(text='Invalid file contents')
        return key,filename,size
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


async def content_link(c,order_id,asset_id=None):
    base=get_settings().public_base_url.rstrip('/')
    if not base:
        raise ValueError('PUBLIC_BASE_URL is required for purchased downloads')
    if await c.fetchval('''SELECT 1 FROM content_links l JOIN orders o ON o.id=l.order_id
        WHERE l.order_id=$1 AND l.asset_id IS NOT DISTINCT FROM $2 AND o.duration_days=-1
        AND l.redeemed_at IS NOT NULL LIMIT 1''',order_id,asset_id):
        return None
    token=secrets.token_urlsafe(32)
    await c.execute("INSERT INTO content_links(token_hash,order_id,asset_id,expires_at) VALUES($1,$2,$3,NOW()+INTERVAL '2 days')",digest(token),order_id,asset_id)
    return f'{base}/content/{token}'


async def purchased_content(request):
    """GET never consumes a purchase (Telegram previews/prefetches links)."""
    token=request.match_info['token']
    if len(token)!=43: raise web.HTTPNotFound()
    cookie_name='content_'+digest(token)[:16]
    async with db.acquire() as c,c.transaction():
        row=await c.fetchrow('''SELECT l.*,o.duration_days,o.product_snapshot FROM content_links l
            JOIN orders o ON o.id=l.order_id WHERE l.token_hash=$1 AND l.expires_at>NOW()
            AND o.paid_at IS NOT NULL AND o.status IN ('paid','delivered') AND o.product_snapshot->>'delivery_mode'='content'
            AND (o.duration_days=-1 OR course_expiry(COALESCE(o.delivered_at,o.paid_at),o.duration_days,o.subscription_expires_at)>NOW())
            FOR UPDATE OF l''',digest(token))
        if not row: raise web.HTTPGone(text='This download link has expired. Request it again in the bot.')
        terms=object_value(row['product_snapshot'])
        session=request.cookies.get(cookie_name,'')
        from datetime import datetime, timezone, timedelta
        resumed=bool(session and row['redeemed_at'] and row['redeemed_at']>datetime.now(timezone.utc)-timedelta(hours=1)
                     and secrets.compare_digest(digest(session),row['session_hash'] or ''))
        if request.method=='POST':
            # Each asset has its own one-use grant; the short session allows range/retry.
            if row['duration_days']==-1 and not resumed:
                await c.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))',f"content:{row['order_id']}:{row['asset_id']}")
                used=await c.fetchval('SELECT 1 FROM content_links WHERE order_id=$1 AND asset_id IS NOT DISTINCT FROM $2 AND redeemed_at IS NOT NULL LIMIT 1',row['order_id'],row['asset_id'])
                if used: raise web.HTTPGone(text='This one-time download was already opened.')
            if not resumed:
                session=secrets.token_urlsafe(32)
                await c.execute("UPDATE content_links SET redeemed_at=NOW(),session_hash=$2 WHERE token_hash=$1",digest(token),digest(session))
            result=web.HTTPSeeOther(location=request.path+'?download=1')
            result.set_cookie(cookie_name,session,max_age=3600,httponly=True,secure=request.headers.get('X-Forwarded-Proto',request.scheme)=='https',samesite='Lax',path=request.path)
            result.headers['Cache-Control']='no-store'
            return result
        if request.query.get('download')=='1':
            if not resumed: raise web.HTTPForbidden()
            if row['asset_id']:
                asset=await c.fetchrow('SELECT filename,storage_key,payload FROM product_assets WHERE id=$1',row['asset_id'])
                if not asset: raise web.HTTPNotFound()
                headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(asset['filename'],safe=''),
                         'Cache-Control':'private, no-store','Content-Type':'application/octet-stream',
                         'X-Content-Type-Options':'nosniff'}
                if asset['storage_key']:
                    result=web.FileResponse(asset_path(asset['storage_key']),headers=headers)
                else:
                    result=web.Response(body=bytes(asset['payload']),headers=headers)
                return result
            if terms.get('content_url'):
                return web.HTTPSeeOther(location=terms['content_url'],headers={'Cache-Control':'no-store'})
            raise web.HTTPNotFound()
    return web.Response(text='''<!doctype html><html lang="fa" dir="rtl"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>محتوای خریداری‌شده</title><link rel="stylesheet" href="/content/style.css"><main><h1>محتوای خریداری‌شده</h1><p>برای دریافت محتوا روی دکمه بزنید. لینک اختصاصی را برای دیگران ارسال نکنید.</p><form method="post"><button>دریافت محتوا · Download</button></form></main></html>''',content_type='text/html',headers={'Cache-Control':'no-store'})


async def content_style(request):
    return web.Response(text=':root{color-scheme:dark light}body{margin:0;min-height:100dvh;display:grid;place-items:center;font-family:system-ui;background:light-dark(#f4f5f8,#141720);color:light-dark(#242735,#eef0f8)}main{max-width:32rem;margin:24px;padding:28px;border:1px solid #80808040;border-radius:24px}h1{font-size:24px}p{line-height:1.9}button{border:0;border-radius:14px;padding:16px 24px;background:#7066ed;color:white;font:inherit;cursor:pointer}',content_type='text/css')
