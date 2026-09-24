import json
import logging
import os
import queue
import subprocess
import sys

from app.services.diagnostics import DiagnosticFormat,DiagnosticQueue,operation
from scripts.review_diagnostics import summarize,timestamp


def test_timing_is_bounded_and_has_no_private_values(caplog):
    with caplog.at_level(logging.WARNING):
        operation('web','catalog_save',.1)
        assert not caplog.records
        operation('web','catalog_save',3.5,200,'a'*16,'POST')
    record=caplog.records[-1]
    record.password='secret';record.msg='token=secret'
    result=DiagnosticFormat().format(record)
    assert 'secret' not in result
    body=json.loads(result)
    assert body['elapsed_ms']==3500 and body['route']=='catalog_save' and body['request_id']=='a'*16


def test_overflow_is_nonblocking_and_reported_after_recovery():
    pending=queue.Queue(maxsize=3);handler=DiagnosticQueue(pending)
    record=logging.LogRecord('test',logging.WARNING,__file__,1,'secret',(),None)
    for _ in range(5):handler.enqueue(handler.prepare(record))
    assert pending.qsize()==3 and handler.dropped==2
    while not pending.empty():pending.get_nowait();pending.task_done()
    handler.enqueue(handler.prepare(record))
    pending.get_nowait()
    assert json.loads(pending.get_nowait().msg)['dropped']==2
    assert handler.dropped==0


def test_telegram_poll_error_keeps_class_not_secret_message():
    record=logging.LogRecord('aiogram.dispatcher',logging.ERROR,__file__,1,'Failed - %s: %s',('TelegramNetworkError','private token'),None,func='_listen_updates')
    result=DiagnosticFormat().format(record)
    assert json.loads(result)['exception']=='TelegramNetworkError'
    assert 'private token' not in result


def test_actual_file_writer_and_review_report(tmp_path):
    script="""
import logging
from app.services.diagnostics import configure,shutdown,operation
logging.basicConfig(level=logging.INFO)
configure('test')
operation('web','catalog_save',3.25,200)
try: raise ValueError('password=must-not-leak')
except ValueError: logging.getLogger('test').exception('private message')
shutdown()
"""
    subprocess.run([sys.executable,'-c',script],env={**os.environ,'DIAGNOSTICS_DIR':str(tmp_path)},check=True,capture_output=True)
    raw=(tmp_path/'test.jsonl').read_text(encoding='utf-8')
    assert 'must-not-leak' not in raw and 'private message' not in raw
    report=summarize(tmp_path)
    assert report['records']==3 and report['malformed_lines']==0
    assert any(r['event']=='slow_operation' and r['max_ms']==3250 for r in report['events'])
    assert any(r['exception']=='ValueError' for r in report['events'])
    assert summarize(tmp_path,timestamp('2099-01-01T00:00:00Z'))['records']==0
    (tmp_path/'broken.jsonl').write_text('{"time":12,"event":"error"}\n',encoding='utf-8')
    assert summarize(tmp_path)['malformed_lines']==1
