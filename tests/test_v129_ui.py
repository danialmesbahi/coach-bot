from app.keyboards import team_purchasers_kb

def test_team_home_callback_is_role_specific():
    kb = team_purchasers_kb([{'user_id': 7, 'name': 'Ali', 'gender': 'مرد', 'age': 22}], 1, 1)
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data]
    assert 'team:home' in callbacks
    assert 'home' not in callbacks
