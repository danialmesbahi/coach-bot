from pathlib import Path

from decimal import Decimal

from app.keyboards import products_kb, renewal_order_kb, sensi_reply_kb
from app.handlers.admin import recorded_weights
from app.utils.text import progress_path, subscription_time_fa


ROOT=Path(__file__).resolve().parents[1]


def test_renewal_is_visible_only_when_eligible():
    hidden=str(renewal_order_kb(7,True,False))
    visible=str(renewal_order_kb(7,True,True))
    assert 'renew:7' not in hidden and 'renew:7' in visible
    assert 'تأیید تمدید' in progress_path('paid',True)
    assert subscription_time_fa(5)=='5 روز تا پایان'


def test_inbox_badge_and_silent_draft_capture():
    assert any('پیام‌ها (12)' in button.text for row in sensi_reply_kb(12).keyboard for button in row)
    user=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    block=user.split('async def support_message',1)[1]
    assert 'به پیش‌نویس اضافه شد' not in block
    assert "فقط عکس تلگرام را می‌پذیرد" in user


def test_subscription_queries_use_purchased_duration_and_five_day_window():
    repo=(ROOT/'app/db/repositories.py').read_text(encoding='utf-8')
    assert "course_expiry(o.delivered_at,o.duration_days,o.subscription_expires_at)" in repo
    assert "INTERVAL '5 days'" in repo
    assert "old.status='delivered'" in repo
    assert "(newer.created_at,newer.id)>(old.created_at,old.id)" in repo
    assert "plan already purchased; renew it" in repo


def test_three_plan_catalog_exposes_only_the_valid_next_action():
    rows=[
        {'id':1,'title':'پلن یک','price_irr':Decimal('399000'),'purchased_before':False},
        {'id':2,'title':'پلن دو','price_irr':Decimal('499000'),'purchased_before':True,'renewal_eligible':True,'latest_order_id':8},
        {'id':3,'title':'پلن سه','price_irr':Decimal('799000'),'purchased_before':True,'renewal_in_progress':True},
    ]
    markup=str(products_kb(rows))
    assert 'buy:1' in markup and 'renew:8' in markup and 'subscription:status:3' in markup


def test_history_pages_edit_in_place_and_fsm_price_is_json_safe():
    user=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    history=user.split('async def show_profile_history',1)[1].split("@router.callback_query(F.data=='profile')",1)[0]
    purchase=user.split('async def begin_purchase',1)[1].split("@router.callback_query(F.data=='renew:list')",1)[0]
    assert "profile_history_page_kb(page,total_pages,include_back=not from_link)" in history
    assert "price=int(p['price_irr'])" in purchase


def test_weight_progress_ignores_old_invalid_snapshots():
    assert recorded_weights([{'snapshot':{'weight_kg':'bad'}},{'snapshot':{'weight_kg':'79.5'}}]) == [79.5]
