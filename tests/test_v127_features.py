from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_sensi_has_messages_panel_and_reply_flow():
    kb=(ROOT/'app/keyboards.py').read_text(encoding='utf-8')
    admin=(ROOT/'app/handlers/admin.py').read_text(encoding='utf-8')
    assert "💬 پیام‌ها" in kb
    assert "sensi:messages" in admin
    assert "sensi:thread:" in admin
    assert "reply_to_customer" in admin

def test_support_storage_is_bidirectional():
    repo=(ROOT/'app/db/repositories.py').read_text(encoding='utf-8')
    schema=(ROOT/'app/db/schema.sql').read_text(encoding='utf-8')
    migration=(ROOT/'alembic/versions/0004_support_bidirectional.py').read_text(encoding='utf-8')
    assert "direction" in repo and "sender_telegram_id" in repo
    assert "reply_to_message_id" in schema
    assert "revision = \"0004_support_bidirectional\"" in migration

def test_restriction_has_only_skip_button():
    user=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    assert "'restriction':" in user
    assert "skip_reply_kb('⏭️ ندارم')" in user
    assert "restriction_skip" in user

def test_order_time_is_exposed_in_sensi_panel():
    admin=(ROOT/'app/handlers/admin.py').read_text(encoding='utf-8')
    assert '🕐 ثبت سفارش' in admin
