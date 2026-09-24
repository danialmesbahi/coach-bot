"""Bounded, private JSONL diagnostics, separate from business/audit records.

Never record request bodies, exception messages, SQL parameters, locals or tokens.
File/line/exception type + request ID are enough to locate the failing code.
"""
import atexit
import json
import logging
import os
import queue
import re
import traceback
from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path

_listener=None


def safe_name(value):
    return re.sub(r'[^a-zA-Z0-9_.:-]','_',str(value))[:100]


class DiagnosticFormat(logging.Formatter):
    def format(self,record):
        result={'time':datetime.fromtimestamp(record.created,timezone.utc).isoformat(),
                'level':record.levelname,'logger':safe_name(record.name),
                'source':f'{Path(record.pathname).name}:{record.lineno}',
                'event':safe_name(getattr(record,'event',record.funcName)),
                'request_id':safe_name(getattr(record,'request_id',''))}
        if record.exc_info:
            result['exception']=safe_name(record.exc_info[0].__name__)
            result['frames']=[{'file':str(Path(f.filename)).replace('\\','/').split('/app/')[-1][-160:],
                'line':f.lineno,'function':safe_name(f.name)} for f in traceback.extract_tb(record.exc_info[2])[-20:]]
        elif record.name=='aiogram.dispatcher' and record.funcName=='_listen_updates' and isinstance(record.args,tuple) and record.args:
            # aiogram logs the exception class as a format argument, not exc_info.
            kind=record.args[0]
            if isinstance(kind,str) and kind in {'TelegramNetworkError','TelegramServerError','TelegramConflictError','TelegramUnauthorizedError','TelegramRetryAfter'}:
                result['exception']=kind
        if hasattr(record,'client_frames'): result['client_frames']=record.client_frames
        for key in ('order_id','asset_id'):
            value=getattr(record,key,None)
            if type(value) is int: result[key]=value
        if hasattr(record,'error_code'): result['error_code']=safe_name(record.error_code)
        for key in ('elapsed_ms','status','dropped'):
            value=getattr(record,key,None)
            if type(value) in (int,float) and 0<=value<=86400000: result[key]=round(value,2)
        for key in ('route','method'):
            if hasattr(record,key): result[key]=safe_name(getattr(record,key))
        return json.dumps(result,ensure_ascii=False)


class DiagnosticQueue(QueueHandler):
    def prepare(self,record):
        # Serialize before queueing; don't retain traceback locals/user data in memory.
        clean=logging.LogRecord(record.name,record.levelno,record.pathname,record.lineno,
                                DiagnosticFormat().format(record),(),None)
        return clean

    def enqueue(self,record):
        try: self.queue.put_nowait(record)
        except queue.Full:
            self.dropped=getattr(self,'dropped',0)+1
            return
        dropped=getattr(self,'dropped',0)
        if dropped:
            notice=logging.LogRecord(__name__,logging.WARNING,__file__,0,'',(),None)
            notice.event='diagnostics_dropped';notice.dropped=dropped
            try: self.queue.put_nowait(self.prepare(notice))
            except queue.Full: return
            self.dropped=0


def operation(source,route,elapsed,status=200,request_id='',method=''):
    """Slow operations are diagnostic; successful traffic remains aggregated in KPI."""
    if elapsed<2 and status<500: return
    logging.getLogger(source).warning('Operation timing',extra={
        'event':'slow_operation' if elapsed>=2 else 'failed_operation','route':route,
        'elapsed_ms':min(max(elapsed*1000,0),86400000),'status':status,'request_id':request_id,'method':method})


def configure(service):
    global _listener
    if _listener: return
    root=Path(os.environ.get('DIAGNOSTICS_DIR','artifacts/diagnostics'))
    root.mkdir(parents=True,exist_ok=True)
    sink=RotatingFileHandler(root/f'{service}.jsonl',maxBytes=5*1024*1024,backupCount=4,encoding='utf-8')
    sink.setFormatter(logging.Formatter('%(message)s'))
    pending=queue.Queue(maxsize=1000)
    handler=DiagnosticQueue(pending)
    handler.setLevel(logging.INFO)
    handler.addFilter(lambda record:record.levelno>=logging.WARNING or getattr(record,'event','')=='service_started')
    logging.getLogger().addHandler(handler)
    _listener=QueueListener(pending,sink,respect_handler_level=True)
    _listener.start()
    logging.getLogger(__name__).info('Diagnostics ready',extra={'event':'service_started','route':service})
    atexit.register(shutdown)


def shutdown():
    global _listener
    if _listener:
        # QueueListener.stop inserts a sentinel non-blockingly; wait for room first.
        _listener.queue.join()
        _listener.stop()
        _listener=None
