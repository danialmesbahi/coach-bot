from pathlib import Path
ROOT=Path(__file__).parents[1]

def test_home_reply_has_no_home_button():
    s=(ROOT/'app/keyboards.py').read_text(encoding='utf-8')
    assert "def main_reply_kb()" in s
    block=s.split('def main_reply_kb()',1)[1].split('def home_only_reply_kb',1)[0]
    assert "MAIN" not in block

def test_phone_saves_to_profile():
    s=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    assert 'repo.update_user(m.from_user.id,phone=phone)' in s

def test_allergy_skip_only():
    s=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    assert "skip_reply_kb('⏭️ ندارم')" in s and "حساسیت غذایی داری؟\\nاگر داری، همینجا توضیحش بده." in s

def test_no_training_days_prompt():
    s=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    assert "'training_days'" not in s
    assert "nutrition_training_days" not in s
