from pathlib import Path

from app.utils.text import progress_path, public_user_id


ROOT=Path(__file__).resolve().parents[1]


def test_public_ids_and_progress():
    assert public_user_id(7)=='U000007'
    assert progress_path('delivered').count('●')==4
    assert progress_path('awaiting_payment').count('●')==1


def test_unread_messages_and_renewals_are_persisted():
    migration=(ROOT/'alembic/versions/0009_unread_and_renewals.py').read_text(encoding='utf-8')
    repo=(ROOT/'app/db/repositories.py').read_text(encoding='utf-8')
    assert 'read_at IS NULL' in migration and 'renewal_of_order_id' in migration
    assert "direction='customer' AND sm.read_at IS NULL" in repo
    assert 'async def renewable_orders' in repo
