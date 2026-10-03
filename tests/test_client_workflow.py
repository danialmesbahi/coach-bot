"""Customer workflow regressions; never contact Telegram or payment providers."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from app.handlers import user


def test_stale_locked_keyboard_rechecks_purchase(monkeypatch):
    monkeypatch.setattr(user, 'is_customer', lambda _: True)
    access = AsyncMock(return_value=True)
    monkeypatch.setattr(user.repo, 'has_course_access', access)
    message = SimpleNamespace(from_user=SimpleNamespace(id=987), answer=AsyncMock())
    state = SimpleNamespace(get_data=AsyncMock(return_value={}), clear=AsyncMock(), update_data=AsyncMock(), set_state=AsyncMock())
    asyncio.run(user.locked_support(message, state))
    access.assert_awaited_once_with(987)
    state.set_state.assert_awaited_once_with(user.SupportForm.waiting)
    assert '🔒' not in message.answer.await_args.args[0]


def test_measurement_input_accepts_local_digits_and_rejects_invalid_values():
    from app.utils.measurements import parse_measurements,validate_measurements,required_body_photos
    text='دور شکم: ۹۲٫۵\nدور کمر: ۸۸\nدور بازو: ٣٥\nدور ران: ۵۸\nعرض شانه: ۴۶\nدور سینه: ۱۰۲'
    values=parse_measurements(text)
    assert values['abdomen']==92.5 and values['arm']==35 and values['shoulders']==46
    for invalid in ({'waist':True},{'waist':'nan'},{'waist':400},{'unknown':80}):
        with pytest.raises(ValueError): validate_measurements(invalid)
    with pytest.raises(ValueError): parse_measurements('دور شکم: ۹۰')
    assert required_body_photos({'gender':'مرد'})==4
    assert required_body_photos({'gender':'زن'})==0


def test_record_edit_rejects_identity_payment_and_invalid_numbers():
    from app.services.client_records import validate_fields
    for invalid in ({'telegram_id':1},{'paid_at':'today'},{'age':3},{'height_cm':500},{'weight_kg':True}):
        with pytest.raises(ValueError): validate_fields(invalid)
    assert validate_fields({'age':'30','notes':'  updated  '})=={'age':30,'notes':'updated'}


def test_live_chat_persists_each_message_without_leaving_chat(monkeypatch):
    access=AsyncMock(return_value=True);persist=AsyncMock()
    monkeypatch.setattr(user.repo,'has_course_access',access)
    monkeypatch.setattr(user.repo,'add_support_message',persist)
    message=SimpleNamespace(from_user=SimpleNamespace(id=987),answer=AsyncMock(),text='Hello',caption=None,
        photo=[],video=None,animation=None,audio=None,voice=None,document=None,media_group_id=None,message_id=10)
    state=SimpleNamespace(get_data=AsyncMock(return_value={'support_mode':'live'}),clear=AsyncMock(),update_data=AsyncMock())
    asyncio.run(user.support_message(message,state))
    assert persist.await_args.kwargs['content_text']=='Hello'
    message.answer.assert_not_awaited()
    state.update_data.assert_awaited_once_with(support_sent=True)
    state.clear.assert_not_awaited()
    persist.side_effect=RuntimeError('Unavailable')
    message.answer.reset_mock()
    asyncio.run(user.support_message(message,state))
    assert 'ثبت نشد' in message.answer.await_args.args[0]
    state.clear.assert_not_awaited()


def test_migrated_fields_use_canonical_order_and_refresh_measurements():
    fields=['name','gender','weight','body_photo','measurements']
    assert user.purchase_route('custom',{'name':'Client','gender':'زن'},fields)==['weight','measurements','body_photo']


@pytest.mark.parametrize('gender,count,allowed',[('زن',0,True),('female',0,True),('مرد',0,False),('مرد',3,False),('مرد',4,True)])
def test_photos_required_only_for_men_and_remaining_steps_are_not_skipped(monkeypatch,gender,count,allowed):
    data={'gender':gender,'body_photo_file_ids':[{'file_id':str(i)} for i in range(count)],
          'product_code':'custom','active_steps':['body_photo','measurements']}
    state=SimpleNamespace(get_data=AsyncMock(return_value=data),update_data=AsyncMock(),set_state=AsyncMock())
    message=SimpleNamespace(from_user=SimpleNamespace(id=998),answer=AsyncMock())
    prompt=AsyncMock();finish=AsyncMock()
    monkeypatch.setattr(user,'prompt',prompt)
    monkeypatch.setattr(user,'finish_questionnaire',finish)
    asyncio.run(user.finish_photos(message,state))
    finish.assert_not_awaited()
    if allowed:
        state.set_state.assert_awaited_once_with(user.PurchaseForm.measurements)
        prompt.assert_awaited_once_with(state,message,'measurements')
    else:
        prompt.assert_not_awaited()
        assert 'چهار عکس' in message.answer.await_args.args[0]


def test_optional_photo_keyboard_has_explicit_skip():
    from app.keyboards import body_photo_kb
    optional=body_photo_kb(optional=True)
    required=body_photo_kb(optional=False)
    assert any(b.text=='⏭️ ادامه بدون عکس' for row in optional.keyboard for b in row)
    assert not any(b.text=='⏭️ ادامه بدون عکس' for row in required.keyboard for b in row)


@pytest.mark.parametrize('sent',[False,True])
def test_chat_end_acknowledges_only_messages_actually_saved(monkeypatch,sent):
    monkeypatch.setattr(user,'is_customer',lambda _:True)
    monkeypatch.setattr(user,'customer_menu',AsyncMock(return_value=None))
    message=SimpleNamespace(from_user=SimpleNamespace(id=987),text='پایان گفتگو و بازگشت',answer=AsyncMock())
    state=SimpleNamespace(get_data=AsyncMock(return_value={'support_mode':'live','support_sent':sent}),clear=AsyncMock())
    asyncio.run(user.support_message(message,state))
    state.clear.assert_awaited_once()
    assert ('با موفقیت' in message.answer.await_args.args[0]) is sent


def test_record_photo_selection_validation():
    from app.services.client_records import validate_fields
    for ids in ([True],[0],[-1],[1,1],list(range(1,8)),['1']):
        with pytest.raises(ValueError): validate_fields({'photo_ids':ids})
    assert validate_fields({'photo_ids':[]})=={'photo_ids':[]}
    assert validate_fields({'photo_ids':[9,2]})=={'photo_ids':[9,2]}


def test_measurement_prompt_has_copyable_template_and_contextual_input():
    message=SimpleNamespace(answer=AsyncMock())
    state=SimpleNamespace(get_data=AsyncMock(return_value={'product_code':'custom','active_steps':['measurements']}))
    asyncio.run(user.prompt(state,message,'measurements'))
    first,last=message.answer.await_args_list
    assert 'انتخاب کن' not in first.kwargs['reply_markup'].input_field_placeholder
    template=last.kwargs['reply_markup'].inline_keyboard[0][0].copy_text.text
    assert 'دور کمر:' in template and len(template.splitlines())==6


@pytest.mark.parametrize('step,expected',[('goal','عضله‌سازی'),('training_history','تازه شروع می‌کنم'),('restriction','گیاه‌خوار هستم'),('supplements','مصرف می‌کنم')])
def test_purchase_prompts_offer_fast_choices_without_numeric_defaults(step,expected):
    data={'product_code':'custom','active_steps':[step]}
    state=SimpleNamespace(get_data=AsyncMock(return_value=data))
    message=SimpleNamespace(answer=AsyncMock())
    asyncio.run(user.prompt(state,message,step))
    keyboard=message.answer.await_args.kwargs['reply_markup']
    assert any(b.text==expected for row in keyboard.keyboard for b in row)


@pytest.mark.parametrize('handler,step,value',[(user.goal,'goal','عضله‌سازی'),(user.goal,'goal','هدف دلخواه من'),(user.history,'training_history','کمتر از ۶ ماه'),(user.restriction,'restriction','گیاه‌خوار هستم')])
def test_preset_and_free_text_answers_are_saved_and_advance(monkeypatch,handler,step,value):
    advance=AsyncMock();save=AsyncMock()
    monkeypatch.setattr(user,'advance_after',advance)
    monkeypatch.setattr(user.repo,'update_user',save)
    message=SimpleNamespace(text=value,from_user=SimpleNamespace(id=998),answer=AsyncMock())
    state=SimpleNamespace(update_data=AsyncMock())
    asyncio.run(handler(message,state))
    state.update_data.assert_awaited_once_with(**{step:value})
    advance.assert_awaited_once_with(state,message,step)


@pytest.mark.parametrize('missing_measurements',[True,False])
def test_checkout_validation_does_not_report_false_previous_purchase(monkeypatch,missing_measurements):
    from app.utils.measurements import MEASUREMENTS
    monkeypatch.setattr(user,'is_customer',lambda _:True)
    monkeypatch.setattr(user,'get_settings',lambda:SimpleNamespace(payment_mode='mock',app_env='development'))
    monkeypatch.setattr(user.repo,'sales_are_open',AsyncMock(return_value=True))
    monkeypatch.setattr(user.repo,'get_product',AsyncMock(return_value={'id':4,'active':True,'version':1}))
    create=AsyncMock(side_effect=ValueError('product changed'))
    monkeypatch.setattr(user.repo,'create_order',create)
    data={'product_id':4,'product_version':1,'product_code':'custom',
          'configured_fields':['measurements'],'active_steps':['measurements'],
          'measurements':None if missing_measurements else {k:60 for k in MEASUREMENTS}}
    state=SimpleNamespace(get_data=AsyncMock(return_value=data),set_state=AsyncMock(),clear=AsyncMock())
    c=SimpleNamespace(from_user=SimpleNamespace(id=998),data='pay:mock',answer=AsyncMock(),message=SimpleNamespace(answer=AsyncMock()))
    prompt=AsyncMock();monkeypatch.setattr(user,'prompt',prompt)
    asyncio.run(user.choose_payment(c,state))
    state.clear.assert_not_awaited()
    assert all('قبلاً' not in call.args[0] for call in c.message.answer.await_args_list)
    if missing_measurements:
        create.assert_not_awaited()
        prompt.assert_awaited_once_with(state,c.message,'measurements')
    else:
        create.assert_awaited_once()
        assert state.set_state.await_args.args[0]==user.PurchaseForm.payment_method
