import asyncio
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers.edit import _begin_edit, add_photo_edit, collect_photo_edit, leave_added_photo_edit, restore_photo_edit
from app.handlers.user import add_purchase_photos, body_photo, leave_added_purchase_photos, purchase_route, replace_purchase_photos, restore_previous_purchase_photos, show_summary
from app.keyboards import body_photo_kb, confirm_kb, edit_photo_kb
from app.utils.photos import MAX_BODY_PHOTOS, append_photo, normalize_photos, photo_lock, stored_photos


class FakeState:
    def __init__(self, **data):
        self.data=data
        self.state=None

    async def get_data(self): return dict(self.data)
    async def update_data(self, **values): self.data.update(values)
    async def set_state(self, value): self.state=value
    async def clear(self): self.data.clear(); self.state=None


class FakeBot:
    def __init__(self):
        self.edits=[]; self.deleted=[]; self.answers=[]; self.next_message_id=1000

    async def edit_message_text(self, text, **kwargs): self.edits.append(text)
    async def delete_message(self, chat_id, message_id): self.deleted.append(message_id)


class FakeMessage:
    def __init__(self, bot, message_id, user_id, file_id=None, media_group_id=None):
        self.bot=bot; self.message_id=message_id; self.media_group_id=media_group_id
        self.date=datetime(2026,10,3,tzinfo=timezone.utc)
        self.from_user=SimpleNamespace(id=user_id); self.chat=SimpleNamespace(id=user_id)
        self.photo=[SimpleNamespace(file_id=file_id,file_size=100)] if file_id else []

    async def answer(self, text, reply_markup=None):
        self.bot.next_message_id+=1
        self.bot.answers.append((text,reply_markup))
        return SimpleNamespace(message_id=self.bot.next_message_id)


def test_photo_draft_keeps_the_first_six_and_serializes_a_user():
    photos = []
    for number in range(7):
        photos, accepted = append_photo(photos, {'file_id': str(number)})
        assert accepted is (number < MAX_BODY_PHOTOS)
    assert [item['file_id'] for item in photos] == ['0', '1', '2', '3', '4', '5']
    assert photo_lock(42) is photo_lock(42)
    assert stored_photos([{'file_id':'x','type':'photo','message_id':9}]) == [{'file_id':'x','type':'photo'}]
    assert normalize_photos('["legacy"]') == [{'file_id':'legacy','type':'photo'}]


def test_restart_and_photo_replacement_keep_the_short_flow_recoverable():
    source=(Path(__file__).resolve().parents[1] / 'app/handlers/user.py').read_text(encoding='utf-8')
    assert "active_steps=list(d.get('active_steps',PURCHASE_STEPS.get(d['product_code'],[])))" in source
    assert "F.text=='↩️ بازگشت به عکس‌های قبلی'" in source
    assert 'async def restore_previous_purchase_photos' in source and 'photo_replacing=True' in source


def test_purchase_album_is_counted_once_and_capped_without_prompt_spam():
    async def scenario():
        bot=FakeBot(); user_id=800001
        state=FakeState(product_code='training',active_steps=['body_photo'],body_photo_file_ids=[],photo_collecting=True,photo_prompt_message_id=99)
        messages=[FakeMessage(bot,i,user_id,f'p{i}','album-1') for i in range(1,9)]
        await asyncio.gather(*(body_photo(message,state) for message in messages))
        assert [item['file_id'] for item in state.data['body_photo_file_ids']] == ['p1','p2','p3','p4','p5','p6']
        assert bot.deleted == [7,8]
        assert sum('حداکثر' in text for text,_ in bot.answers) == 1
        assert all(any(f'— {number}/{MAX_BODY_PHOTOS}' in text for text in bot.edits) for number in range(1,7))
    asyncio.run(scenario())


def test_edit_album_has_the_same_limit_and_counter_behavior():
    async def scenario():
        bot=FakeBot(); user_id=800002
        state=FakeState(edit_key='body_photo_file_ids',edit_photos=[],edit_collecting=True,edit_photo_prompt_id=88)
        messages=[FakeMessage(bot,i,user_id,f'e{i}','album-2') for i in range(1,9)]
        await asyncio.gather(*(collect_photo_edit(message,state) for message in messages))
        assert [item['file_id'] for item in state.data['edit_photos']] == ['e1','e2','e3','e4','e5','e6']
        assert bot.deleted == [7,8]
        assert sum('حداکثر' in text for text,_ in bot.answers) == 1
        assert all(any(f'— {number}/{MAX_BODY_PHOTOS}' in text for text in bot.edits) for number in range(1,7))
    asyncio.run(scenario())


def test_replacing_photos_can_restore_previous_list_and_deletes_new_draft():
    async def scenario():
        bot=FakeBot(); user_id=800003
        old=[{'file_id':'old','type':'photo'}]
        state=FakeState(product_code='training',active_steps=['body_photo'],body_photo_file_ids=old,previous_body_photo_file_ids=old,photo_collecting=False,photo_prompt_message_id=77)
        await replace_purchase_photos(FakeMessage(bot,50,user_id),state)
        labels={button.text for row in bot.answers[-1][1].keyboard for button in row}
        assert '↩️ بازگشت به عکس‌های قبلی' in labels
        await body_photo(FakeMessage(bot,51,user_id,'new'),state)
        await restore_previous_purchase_photos(FakeMessage(bot,52,user_id),state)
        assert state.data['body_photo_file_ids'] == old
        assert state.data['photo_collecting'] is False
        assert 51 in bot.deleted
    asyncio.run(scenario())


def test_adding_photos_has_a_back_action_without_discarding_the_current_list():
    async def scenario():
        bot=FakeBot(); user_id=800007
        old=[{'file_id':'old','type':'photo'}]
        state=FakeState(product_code='training',active_steps=['body_photo'],body_photo_file_ids=old,previous_body_photo_file_ids=old,photo_collecting=False,photo_prompt_message_id=71)
        await add_purchase_photos(FakeMessage(bot,72,user_id),state)
        labels={button.text for row in bot.answers[-1][1].keyboard for button in row}
        assert 'بازگشت' in labels
        await body_photo(FakeMessage(bot,73,user_id,'new'),state)
        await leave_added_purchase_photos(FakeMessage(bot,74,user_id),state)
        assert [photo['file_id'] for photo in state.data['body_photo_file_ids']] == ['old','new']
        assert state.data['photo_collecting'] is False
    asyncio.run(scenario())


def test_photo_keyboards_keep_all_controls_available_while_collecting():
    for markup in (body_photo_kb(0,True),edit_photo_kb(0,True)):
        labels={button.text for row in markup.keyboard for button in row}
        assert '👁 دیدن عکس‌های فعلی' in labels
        assert '🗑 حذف آخرین عکس' in labels
    for markup in (body_photo_kb(1,False),edit_photo_kb(1,False)):
        labels={button.text for row in markup.keyboard for button in row}
        assert '➕ افزودن عکس جدید' in labels
        assert '🆕 ارسال لیست عکس جدید' not in labels
        assert '🏠 منوی اصلی' not in labels


def test_confirmation_has_only_purchase_actions_and_photo_edit_can_leave_add_mode():
    assert [button.callback_data for row in confirm_kb().inline_keyboard for button in row] == ['confirm','restart_form']

    async def scenario():
        bot=FakeBot(); user_id=800008
        old=[{'file_id':'old','type':'photo'}]
        state=FakeState(edit_key='body_photo_file_ids',edit_photos=old,edit_previous_photos=old,edit_collecting=False,edit_photo_prompt_id=81)
        await add_photo_edit(FakeMessage(bot,82,user_id),state)
        labels={button.text for row in bot.answers[-1][1].keyboard for button in row}
        assert 'بازگشت' in labels
        await collect_photo_edit(FakeMessage(bot,83,user_id,'new'),state)
        await leave_added_photo_edit(FakeMessage(bot,84,user_id),state)
        assert [photo['file_id'] for photo in state.data['edit_photos']] == ['old','new']
        assert state.data['edit_collecting'] is False
    asyncio.run(scenario())


def test_welcome_copy_is_only_enabled_by_the_start_route():
    source=(Path(__file__).resolve().parents[1] / 'app/handlers/user.py').read_text(encoding='utf-8')
    assert "welcome: bool=False" in source
    assert "await home_message(m,welcome=is_new_customer)" in source
    assert "async def nav_main(m,state): await state.clear(); await home_message(m)" in source


def test_empty_replacement_can_always_go_back_in_purchase_and_edit():
    async def scenario():
        bot=FakeBot(); user_id=800004
        purchase=FakeState(product_code='training',active_steps=['body_photo'],body_photo_file_ids=[],previous_body_photo_file_ids=[],photo_collecting=True,photo_replacing=True)
        await restore_previous_purchase_photos(FakeMessage(bot,60,user_id),purchase)
        assert purchase.data['photo_replacing'] is False
        assert purchase.data['photo_collecting'] is True

        edit=FakeState(edit_key='body_photo_file_ids',edit_photos=[],edit_previous_photos=[],edit_collecting=True,edit_replacing=True)
        await restore_photo_edit(FakeMessage(bot,61,user_id),edit)
        assert edit.data['edit_replacing'] is False
        assert edit.data['edit_collecting'] is True
    asyncio.run(scenario())


def test_profile_edits_do_not_change_order_photos():
    root=Path(__file__).resolve().parents[1]
    user_source=(root / 'app/handlers/user.py').read_text(encoding='utf-8')
    edit_source=(root / 'app/handlers/edit.py').read_text(encoding='utf-8')
    repo_source=(root / 'app/db/repositories.py').read_text(encoding='utf-8')
    assert 'previous_photos=[]' in user_source
    assert "current=normalize_photos((await repo.get_user(tg_id) or {}).get('body_photo_file_ids'))" in edit_source
    assert 'update_body_photos_for_latest_course(m.from_user.id,photos)' not in edit_source
    assert "ORDER BY o.created_at DESC,o.id DESC LIMIT 1" in repo_source


def test_edit_callback_uses_the_customer_id_not_the_bot_message_author():
    async def scenario():
        bot=FakeBot(); customer_id=800005
        message=FakeMessage(bot,70,8697023888)
        state=FakeState()
        with patch('app.handlers.edit.repo.get_user',AsyncMock(return_value={'body_photo_file_ids':[{'file_id':'latest','type':'photo'}]})) as latest, \
             patch('app.handlers.edit._show_edit_photo_prompt',AsyncMock()):
            await _begin_edit(message,state,'body_photo_file_ids',customer_id)
        latest.assert_awaited_once_with(customer_id)
        assert state.data['edit_photos'] == [{'file_id':'latest','type':'photo'}]
    asyncio.run(scenario())


def test_purchase_summary_has_confirmation_buttons_on_the_summary_message():
    async def scenario():
        bot=FakeBot(); customer_id=800006
        message=FakeMessage(bot,80,customer_id)
        state=FakeState(product_code='training',product_title='تمرین',name='کاربر',phone='1',age=20,gender='مرد',height_cm=180,weight_kg=80,goal='هدف',training_history='-',notes='',body_photo_file_ids=[],price=1)
        with patch('app.handlers.user.customer_menu',AsyncMock(return_value='customer-main')):
            await show_summary(message,state,customer_id)
        assert len(bot.answers) == 2
        assert all('مرحلهٔ عکس‌ها تمام شد' not in text for text,_ in bot.answers)
        assert bot.answers[0] == ('⏳ در حال پردازش اطلاعات…','customer-main')
        assert bot.answers[1][0].startswith('📋 بررسی اطلاعات سفارش')
        callbacks=[button.callback_data for row in bot.answers[1][1].inline_keyboard for button in row]
        assert callbacks == ['confirm','restart_form']
        assert all(text != '\u2063' for text,_ in bot.answers)
        assert bot.deleted == []
        assert state.state is not None
    asyncio.run(scenario())


def test_returning_customer_refreshes_notes_in_the_five_step_purchase_flow():
    profile={'name':'کاربر','phone':'1','age':20,'gender':'مرد','height_cm':180,'weight_kg':80,'goal':'هدف','training_history':'سابقه','notes':'قدیمی'}
    assert purchase_route('training',profile) == ['age','height','weight','measurements','notes','body_photo']
