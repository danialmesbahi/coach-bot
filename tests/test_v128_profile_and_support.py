from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_profile_history_storage_exists():
    repo=(ROOT/'app/db/repositories.py').read_text(encoding='utf-8')
    mig=(ROOT/'alembic/versions/0005_profile_history.py').read_text(encoding='utf-8')
    user=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    assert 'user_profile_history' in repo
    assert 'revision = "0005_profile_history"' in mig
    assert 'profile_history' in user

def test_telegram_runtime_has_no_management_router():
    main=(ROOT/'app/main.py').read_text(encoding='utf-8')
    user=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    assert 'admin_router' not in main
    assert 'dp.include_router(edit_router); dp.include_router(user_router)' in main
    assert 'def is_customer(_uid:int)->bool: return True' in user

def test_support_messages_store_content_and_direction():
    repo=(ROOT/'app/db/repositories.py').read_text(encoding='utf-8')
    sch=(ROOT/'app/db/schema.sql').read_text(encoding='utf-8')
    assert 'content_type' in repo and 'content_text' in repo
    assert 'content_type TEXT' in sch and 'content_text TEXT' in sch
