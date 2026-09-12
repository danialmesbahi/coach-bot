import ast
from pathlib import Path
from app.handlers.user import purchase_route

def test_purchase_handler_resets_state_and_refreshes_dynamic_fields():
    src=Path("app/handlers/user.py").read_text(encoding='utf-8')
    assert "await state.clear()" in src
    profile={'name':'کاربر','phone':'09120000000','gender':'مرد','goal':'تناسب اندام','training_history':'تازه‌کار','notes':'-'}
    assert purchase_route('training',profile) == ['age','height','weight','notes','body_photo']
    assert "@router.callback_query(F.data.startswith('buy:'))" in src
    ast.parse(src)
