from pathlib import Path

from app.services.motivation import MOTIVATIONAL_MESSAGES, message_for


ROOT=Path(__file__).resolve().parents[1]


def test_profile_history_has_no_repeated_history_button():
    user=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    keyboards=(ROOT/'app/keyboards.py').read_text(encoding='utf-8')
    block=user.split("async def profile_history_view",1)[1].split("@router.callback_query(F.data=='profile')",1)[0]
    assert 'show_profile_history(c.message,c.from_user.id,page,edit=True)' in block
    assert 'profile_history_page_kb(page,total_pages,include_back=not from_link)' in user
    assert 'سوابق اطلاعات' not in keyboards.split('def profile_history_kb()',1)[1].split('def customer_compose_kb',1)[0]


def test_sensi_and_admin_share_the_same_sales_report_with_commission():
    source=(ROOT/'app/handlers/admin.py').read_text(encoding='utf-8')
    assert source.count('sales_report(now,month,total,items,') >= 3
    assert 'سهم تیم توسعه' in source


def test_need_info_collects_the_coachs_specific_request_before_sending():
    source=(ROOT/'app/handlers/admin.py').read_text(encoding='utf-8')
    assert 'NeedInfoForm.waiting' in source
    assert 'لطفاً این مورد را ارسال یا توضیح بده' in source
    assert "'request_length':len(request)" in source


def test_support_messages_are_staged_and_customer_mail_waits_in_inbox():
    user=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    admin=(ROOT/'app/handlers/admin.py').read_text(encoding='utf-8')
    assert "F.text == '✅ ارسال پیام'" in user
    assert "F.text == '✅ ارسال پیام'" in admin
    assert 'draft_items' in user and 'draft_items' in admin
    assert 'copy_message(s.sensi_id' not in user
    assert 'repo.add_support_message' in user
    assert 'copy_message' in admin


def test_motivation_is_bounded_and_deterministic():
    assert len(MOTIVATIONAL_MESSAGES) >= 3
    assert message_for(7,42) == message_for(7,42)
    config=(ROOT/'app/config.py').read_text(encoding='utf-8')
    repo=(ROOT/'app/db/repositories.py').read_text(encoding='utf-8')
    assert 'motivation_batch_size' in config
    assert 'LIMIT $2' in repo
