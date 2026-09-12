from pathlib import Path
ROOT = Path(__file__).parents[1]
def test_admin_payment_notifications_have_customer_id():
    repo=(ROOT/'app/db/repositories.py').read_text(encoding='utf-8')
    assert 'approve_card_payment' in repo and 'u.telegram_id' in repo
    assert 'reject_card_payment' in repo and 'u.telegram_id' in repo
def test_reply_keyboards_are_persistent():
    kb=(ROOT/'app/keyboards.py').read_text(encoding='utf-8')
    assert 'one_time_keyboard=False' in kb
    assert 'is_persistent=True' in kb
def test_allergy_negative_answers_are_supported():
    user=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    assert 'حساسیت غذایی داری؟' in user
    assert "'نه'" in user and "'خیر'" in user
    assert "skip_reply_kb('⏭️ ندارم')" in user
    assert 'restriction_skip' in user
