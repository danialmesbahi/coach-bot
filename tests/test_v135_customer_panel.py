from decimal import Decimal
from pathlib import Path

from app.handlers.user import _fsm_value, _table
from app.keyboards import customer_main_reply_kb
from app.utils.text import order_code


ROOT=Path(__file__).resolve().parents[1]


def test_customer_menu_order_codes_and_json_safe_profile_numbers():
    locked=str(customer_main_reply_kb(False)); unlocked=str(customer_main_reply_kb(True))
    assert '🔒 پیام به مربی' in locked and '💬 پیام به مربی' not in locked
    assert '💬 پیام به مربی' in unlocked and '🛒 خرید دوره' in unlocked
    assert order_code(7) == 'ORD-000007'
    assert _fsm_value(Decimal('79.5')) == 79.5
    assert '&lt;script&gt;' in _table('test',[('name','<script>')])


def test_customer_lists_and_photo_edit_keep_the_requested_limits():
    user=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    edit=(ROOT/'app/handlers/edit.py').read_text(encoding='utf-8')
    assert 'repo.profile_history(tg_id,page,3)' in user
    assert 'page_size=3' in user
    assert 'append_photo' in edit and 'MAX_BODY_PHOTOS' in edit
    assert '❌ لغو ویرایش' in edit and '🏠 منوی اصلی' not in edit
