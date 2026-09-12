from pathlib import Path

from app.keyboards import admin_order_kb, sensi_customer_kb, sensi_orders_list_kb, sensi_reply_kb, sensi_workflow_kb


ROOT=Path(__file__).resolve().parents[1]


def _callbacks(markup):
    return {button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data}


def test_sensi_workspace_surfaces_daily_work_and_only_valid_order_actions():
    labels=[button.text for row in sensi_reply_kb(3,5,8).keyboard for button in row]
    assert '📋 کارها (5)' in labels
    assert '💬 پیام‌ها (3)' in labels
    assert '👥 شاگردها (8)' in labels

    paid=_callbacks(admin_order_kb(11,'paid'))
    designing=_callbacks(admin_order_kb(11,'in_progress'))
    assert 'admin:progress:11' in paid
    assert 'admin:send:11' in designing and 'admin:progress:11' not in designing
    assert any(button.text == '❌ لغو ارسال فایل' for row in sensi_workflow_kb('❌ لغو ارسال فایل').keyboard for button in row)
    assert _callbacks(sensi_customer_kb(7)) == {'sensi:reply:7'}
    assert sensi_orders_list_kb([],1,1) is None

    source=(ROOT/'app/handlers/admin.py').read_text(encoding='utf-8')
    assert 'staff_order_{int(order_id)}' in source
    assert "compose=kind=='thread'" in source
    assert 'async def show_sensi_order' in source
