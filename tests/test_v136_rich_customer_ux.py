from pathlib import Path

from app.handlers.user import _bot_link, _command_id, _table, _visible_bot_link
from app.keyboards import body_photo_kb, orders_list_kb, previous_value_kb, profile_history_page_kb, profile_kb


ROOT=Path(__file__).resolve().parents[1]


def test_standard_customer_navigation_and_photo_limit_regression():
    table=_table('پروفایل',[('نام','دانیال')])
    assert '<table' not in table and '┌─ پروفایل' in table and 'نام: دانیال' in table
    assert _bot_link('isensir_bot','نمایش دوره','course_42') == '<a href="https://t.me/isensir_bot?start=course_42">نمایش دوره</a>'
    assert _bot_link(None,'نمایش دوره','course_42') == '<a href="/course_42">نمایش دوره</a>'
    assert _visible_bot_link('isensir_bot','course_42') == '<a href="https://t.me/isensir_bot?start=course_42">نمایش</a>'
    assert _command_id('/photos_42@isensir_bot','/photos_')==42
    assert 'home' not in str(profile_kb())
    history_markup=profile_history_page_kb(1,1)
    assert 'profile' in str(history_markup) and 'history_photos:' not in str(history_markup) and 'home' not in str(history_markup)
    assert orders_list_kb([],1,1) is None
    assert orders_list_kb([{'id':7}],1,1) is None
    assert 'بعدی؛ بدون تغییر' not in str(previous_value_kb('سن',28))
    assert any('دیدن عکس‌های فعلی' in button.text for row in body_photo_kb(3,False).keyboard for button in row)
    source=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    edit=(ROOT/'app/handlers/edit.py').read_text(encoding='utf-8')
    assert 'ids.pop(0)' not in source and 'photos.pop(0)' not in edit
    assert "r'^/course_\\d+(?:@\\w+)?$'" in source
    assert 'InputRich' not in source and 'send_rich' not in source
    assert 'https://t.me/{bot_username}?start=' in source
    assert 'async def _finish_deep_link' in source and 'await m.delete()' in source
    assert 'show_order_detail_message(m,m.from_user.id,oid,from_link=True)' in source
    assert 'if from_link or active_course:\n        markup=plan_download_kb(oid)' in source
    assert "F.data.startswith('history_photos:')" not in source and "F.data.startswith('course:')" not in source
    repository=(ROOT/'app/db/repositories.py').read_text(encoding='utf-8')
    ownership=repository[repository.index('async def get_user_order'):repository.index('async def get_user_orders')]
    assert 'WHERE o.id=$1 AND u.telegram_id=$2' in ownership
