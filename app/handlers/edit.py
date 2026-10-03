import json

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import get_settings
from app.db import repositories as repo
from app.keyboards import customer_main_reply_kb, edit_photo_kb, edit_value_kb
from app.states.forms import EditForm
from app.utils.photos import MAX_BODY_PHOTOS, append_photo, delete_draft_photos, delete_photo_message, edit_photo_status, normalize_photos, photo_lock, stored_photos
from app.utils.validation import clean_text, parse_int, parse_number


router = Router()
settings = get_settings()
FIELDS = [
    ('body_photo_file_ids', '📸 عکس‌های بدن'), ('name', 'نام'), ('phone', 'شماره تلفن'),
    ('age', 'سن'), ('gender', 'جنسیت'), ('height_cm', 'قد'), ('weight_kg', 'وزن'),
    ('goal', 'هدف'), ('training_history', 'سابقه تمرین'),
    ('food_allergy', 'حساسیت غذایی'), ('food_restriction', 'محدودیت غذایی'),
    ('supplements', 'مکمل‌ها'), ('notes', 'توضیحات'),
]
ALLOWED = {key for key, _ in FIELDS}



def customer(_uid: int) -> bool:
    return True


async def _finish(m: Message, state: FSMContext, text: str):
    await state.clear()
    menu=customer_main_reply_kb(await repo.has_course_access(m.from_user.id))
    await m.answer(text, reply_markup=menu)
    from app.handlers.user import show_profile
    await show_profile(m)


async def _save_profile_edit(tg_id: int, key: str, value):
    await repo.update_user(tg_id, **{key: value})


async def _show_edit_photo_prompt(m: Message, state: FSMContext):
    data=await state.get_data(); photos=normalize_photos(data.get('edit_photos'))
    count=len(photos); collecting=bool(data.get('edit_collecting'))
    replacing=bool(data.get('edit_replacing')); adding=bool(data.get('edit_adding'))
    can_restore=replacing or adding
    back_text='↩️ بازگشت به عکس‌های قبلی' if replacing else 'بازگشت' if adding else None
    text=(f'📸 عکس‌های بدن — {count}/{MAX_BODY_PHOTOS}\n\n' +
          ('عکس بعدی را بفرست یا «✅ ذخیره عکس‌ها» را بزن.' if collecting and count else
           'عکس‌های فعلی آماده‌اند؛ می‌توانی نگه‌شان داری، عکس اضافه کنی یا یک لیست تازه بسازی.' if count else
           'لیست جدید عکس‌ها را بفرست یا به عکس‌های قبلی برگرد.' if can_restore else
           f'تا {MAX_BODY_PHOTOS} عکس واضح از بدن بفرست.'))
    if await edit_photo_status(m.bot,m.chat.id,data.get('edit_photo_prompt_id'),text):
        return
    sent=await m.answer(text,reply_markup=edit_photo_kb(count,collecting,can_restore,back_text))
    await state.update_data(edit_photo_prompt_id=sent.message_id)


def _edit_link(bot_username: str | None, key: str) -> str:
    return f'https://t.me/{bot_username}?start=edit_{key}' if bot_username else f'/edit_{key}'


async def _show_edit_menu(m: Message, actor, edit: bool=False):
    user=await repo.get_user(actor.id) or {}
    builder=InlineKeyboardBuilder()
    for key, label in FIELDS:
        value=user.get(key)
        if key == 'body_photo_file_ids':
            if isinstance(value,str):
                try: value=json.loads(value)
                except (TypeError,ValueError): value=[]
            value=f'{len(value or [])} عکس' if value else 'ثبت نشده'
        shown=str(value if value not in (None, '') else '-')[:28]
        builder.button(text=f'{label}: {shown}', callback_data=f'edit:{key}')
    builder.button(text='⬅️ بازگشت', callback_data='profile')
    builder.adjust(2)
    text='✏️ موردی که می‌خواهی تغییر بدهی انتخاب کن:'
    if edit:
        try:
            return await m.edit_text(text,reply_markup=builder.as_markup())
        except TelegramBadRequest:
            pass
    return await m.answer(text,reply_markup=builder.as_markup())


async def _begin_edit(m: Message, state: FSMContext, key: str, tg_id: int):
    if key not in ALLOWED:
        return await m.answer('درخواست نامعتبر است.')
    await state.clear()
    await state.update_data(edit_key=key)
    await state.set_state(EditForm.value)
    if key == 'body_photo_file_ids':
        current=normalize_photos((await repo.get_user(tg_id) or {}).get('body_photo_file_ids'))
        await state.update_data(
            edit_photos=current,
            edit_previous_photos=current,
            edit_collecting=not bool(current),
            edit_adding=False,
            edit_replacing=False,
            edit_photo_prompt_id=None,
        )
        await _show_edit_photo_prompt(m,state)
    else:
        markup=(edit_value_kb(request_contact=True) if key == 'phone' else
                edit_value_kb('مرد','زن') if key == 'gender' else edit_value_kb())
        await m.answer(f"مقدار جدید «{dict(FIELDS)[key]}» را ارسال کن:", reply_markup=markup)


async def _delete_link_command(m: Message):
    try:
        await m.delete()
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == 'edit_profile')
async def edit_profile(c: CallbackQuery):
    if not customer(c.from_user.id):
        return await c.answer('دسترسی ندارید.', show_alert=True)
    await _show_edit_menu(c.message,c.from_user,edit=True)
    await c.answer()


@router.callback_query(F.data.startswith('edit:'))
async def edit_field(c: CallbackQuery, state: FSMContext):
    if not customer(c.from_user.id):
        return await c.answer('دسترسی ندارید.', show_alert=True)
    key=c.data.split(':', 1)[1]
    if key not in ALLOWED:
        return await c.answer('درخواست نامعتبر است.', show_alert=True)
    await _begin_edit(c.message,state,key,c.from_user.id)
    await c.answer()


@router.message(F.text.regexp(r'^/start(?:@\w+)? edit_profile$'))
async def edit_profile_link(m: Message, state: FSMContext):
    if not customer(m.from_user.id):
        return await m.answer('این لینک فقط برای مشتری فعال است.')
    await state.clear()
    await _show_edit_menu(m,m.from_user)
    await _delete_link_command(m)


@router.message(F.text.regexp(r'^/start(?:@\w+)? edit_[a-z_]+$'))
async def edit_field_link(m: Message, state: FSMContext):
    if not customer(m.from_user.id):
        return await m.answer('این لینک فقط برای مشتری فعال است.')
    key=m.text.rsplit(' ',1)[-1].removeprefix('edit_')
    await _begin_edit(m,state,key,m.from_user.id)
    await _delete_link_command(m)


@router.message(EditForm.value, F.text == '❌ لغو ویرایش')
async def cancel_edit(m: Message, state: FSMContext):
    if not customer(m.from_user.id):
        return await state.clear()
    data=await state.get_data()
    if data.get('edit_key') == 'body_photo_file_ids':
        await delete_draft_photos(m.bot,m.chat.id,data.get('edit_photos'))
    await _finish(m,state,'ویرایش لغو شد؛ اطلاعات قبلی دست‌نخورده ماند.')


@router.message(EditForm.value, F.contact)
async def save_contact_edit(m: Message, state: FSMContext):
    if not customer(m.from_user.id):
        return await state.clear()
    data=await state.get_data()
    if data.get('edit_key') != 'phone':
        return await m.answer('این ورودی برای مورد انتخاب‌شده مناسب نیست.')
    contact=m.contact
    if contact.user_id and contact.user_id != m.from_user.id:
        return await m.answer('لطفاً شماره خودت را ارسال کن.')
    phone=clean_text(contact.phone_number,32)
    if not phone or len(phone) < 7:
        return await m.answer('شماره تلفن معتبر دریافت نشد.')
    await _save_profile_edit(m.from_user.id,'phone',phone)
    await _finish(m,state,'✅ شماره تلفن به‌روزرسانی شد.')


@router.message(EditForm.value, F.photo)
async def collect_photo_edit(m: Message, state: FSMContext):
    if not customer(m.from_user.id):
        return await state.clear()
    async with photo_lock(m.from_user.id):
        data=await state.get_data()
        if data.get('edit_key') != 'body_photo_file_ids':
            return await m.answer('عکس برای این مورد مناسب نیست.')
        photo=m.photo[-1]
        if photo.file_size and photo.file_size > settings.max_body_photo_mb * 1024 * 1024:
            return await m.answer(f'❌ حجم هر عکس باید کمتر از {settings.max_body_photo_mb}MB باشد.')
        photos, accepted=append_photo(list(data.get('edit_photos') or []),{'file_id':photo.file_id,'type':'photo','message_id':m.message_id})
        if not accepted:
            await delete_photo_message(m.bot,m.chat.id,m.message_id)
            group_id=str(m.media_group_id) if m.media_group_id else None
            if not group_id or data.get('edit_photo_limit_media_group_id') != group_id:
                await state.update_data(edit_photo_limit_media_group_id=group_id)
                await m.answer(f'حداکثر {MAX_BODY_PHOTOS} عکس می‌تونی ثبت کنی؛ عکس‌های اضافه برای هر دو طرف پاک شدند و {MAX_BODY_PHOTOS} عکس اول نگه داشته شد.')
            return
        await state.update_data(edit_photos=photos,edit_collecting=True,edit_photo_limit_media_group_id=None)
        await _show_edit_photo_prompt(m,state)


@router.message(EditForm.value, F.text == '👁 دیدن عکس‌های فعلی')
async def view_photo_edit(m: Message, state: FSMContext):
    data=await state.get_data()
    if data.get('edit_key') != 'body_photo_file_ids':
        return await m.answer('درخواست نامعتبر است.')
    from app.handlers.user import _send_photo_items
    await _send_photo_items(m,'عکس‌های فعلی',normalize_photos(data.get('edit_photos')))


@router.message(EditForm.value, F.text == '➕ افزودن عکس جدید')
async def add_photo_edit(m: Message, state: FSMContext):
    data=await state.get_data(); photos=normalize_photos(data.get('edit_photos'))
    if len(photos) >= MAX_BODY_PHOTOS:
        return await m.answer('۶ عکس کامل است؛ برای افزودن عکس جدید اول یک عکس را حذف کن یا لیست تازه بساز.')
    await delete_photo_message(m.bot,m.chat.id,data.get('edit_photo_prompt_id'))
    await state.update_data(edit_collecting=True,edit_adding=True,edit_photo_prompt_id=None)
    await _show_edit_photo_prompt(m,state)


@router.message(EditForm.value, F.text == 'بازگشت')
async def leave_added_photo_edit(m: Message, state: FSMContext):
    async with photo_lock(m.from_user.id):
        data=await state.get_data()
        if data.get('edit_key') != 'body_photo_file_ids':
            return await m.answer('درخواست نامعتبر است.')
        await delete_photo_message(m.bot,m.chat.id,data.get('edit_photo_prompt_id'))
        await state.update_data(edit_collecting=False,edit_adding=False,edit_photo_prompt_id=None)
        await _show_edit_photo_prompt(m,state)


@router.message(EditForm.value, F.text == '🆕 ارسال لیست عکس جدید')
async def replace_photo_edit(m: Message, state: FSMContext):
    async with photo_lock(m.from_user.id):
        data=await state.get_data()
        previous=(normalize_photos(data.get('edit_previous_photos')) if data.get('edit_replacing') else normalize_photos(data.get('edit_photos')))
        await delete_photo_message(m.bot,m.chat.id,data.get('edit_photo_prompt_id'))
        await state.update_data(edit_previous_photos=previous,edit_photos=[],edit_collecting=True,edit_adding=False,edit_replacing=True,edit_photo_prompt_id=None)
        await _show_edit_photo_prompt(m,state)


@router.message(EditForm.value, F.text == '↩️ بازگشت به عکس‌های قبلی')
async def restore_photo_edit(m: Message, state: FSMContext):
    async with photo_lock(m.from_user.id):
        data=await state.get_data(); previous=normalize_photos(data.get('edit_previous_photos'))
        await delete_draft_photos(m.bot,m.chat.id,data.get('edit_photos'))
        await delete_photo_message(m.bot,m.chat.id,data.get('edit_photo_prompt_id'))
        await state.update_data(edit_photos=previous,edit_collecting=not bool(previous),edit_adding=False,edit_replacing=False,edit_photo_prompt_id=None)
        await _show_edit_photo_prompt(m,state)


@router.message(EditForm.value, F.text == '✅ نگه‌داشتن همین عکس‌ها')
async def keep_photo_edit(m: Message, state: FSMContext):
    data=await state.get_data()
    if data.get('edit_key') != 'body_photo_file_ids':
        return await m.answer('درخواست نامعتبر است.')
    await _finish(m,state,'عکس‌های قبلی بدون تغییر نگه داشته شدند.')


@router.message(EditForm.value, F.text == '🗑 حذف آخرین عکس')
async def remove_photo_edit(m: Message, state: FSMContext):
    async with photo_lock(m.from_user.id):
        data=await state.get_data()
        if data.get('edit_key') != 'body_photo_file_ids':
            return await m.answer('درخواست نامعتبر است.')
        photos=list(data.get('edit_photos') or [])
        if not photos:
            return await m.answer('هنوز عکسی برای حذف وجود ندارد.')
        removed=photos.pop()
        await delete_photo_message(m.bot,m.chat.id,removed.get('message_id'))
        await state.update_data(edit_photos=photos)
        await _show_edit_photo_prompt(m,state)


@router.message(EditForm.value, F.document)
async def reject_photo_document_edit(m: Message, state: FSMContext):
    data=await state.get_data()
    if data.get('edit_key') == 'body_photo_file_ids':
        return await m.answer(f'❌ فقط عکس تلگرام پذیرفته می‌شود. از Gallery/Photo و عکس کمتر از {settings.max_body_photo_mb}MB استفاده کن.')
    await m.answer('این نوع فایل برای مورد انتخاب‌شده مناسب نیست.')


@router.message(EditForm.value, F.text == '✅ ذخیره عکس‌ها')
async def save_photo_edit(m: Message, state: FSMContext):
    async with photo_lock(m.from_user.id):
        data=await state.get_data(); photos=list(data.get('edit_photos') or [])
        if data.get('edit_key') != 'body_photo_file_ids':
            return await m.answer('درخواست نامعتبر است.')
        if not photos:
            return await m.answer('حداقل یک عکس بفرست یا «لغو ویرایش» را بزن.')
        photos=stored_photos(photos)
        await repo.update_user(m.from_user.id,body_photo_file_ids=photos,body_photo_file_id=photos[-1]['file_id'])
        await _finish(m,state,f'✅ {len(photos)} عکس بدن ذخیره شد.')


@router.message(EditForm.value)
async def save_edit(m: Message, state: FSMContext):
    if not customer(m.from_user.id):
        return await state.clear()
    data=await state.get_data(); key=data.get('edit_key')
    if key not in ALLOWED:
        await state.clear()
        return await m.answer('درخواست ویرایش نامعتبر است.')
    if key == 'body_photo_file_ids':
        return await m.answer('فقط عکس بفرست و بعد «ذخیره عکس‌ها» را بزن.')
    if key == 'phone':
        return await m.answer('شماره را با دکمه «ارسال شماره تلفن» بفرست.')
    value=clean_text(m.text or '',500)
    if not value:
        return await m.answer('مقدار معتبر ارسال کن.')
    if key == 'gender' and value not in ('مرد','زن'):
        return await m.answer('یکی از گزینه‌های مرد یا زن را انتخاب کن.')
    if key == 'age':
        value=parse_int(value,10,100)
    elif key == 'height_cm':
        value=parse_number(value)
        if value is not None and not 100 <= value <= 230:
            value=None
    elif key == 'weight_kg':
        value=parse_number(value)
        if value is not None and not 25 <= value <= 300:
            value=None
    if key in {'age','height_cm','weight_kg'} and value is None:
        return await m.answer('مقدار واردشده معتبر نیست.')
    await _save_profile_edit(m.from_user.id,key,value)
    await _finish(m,state,'✅ اطلاعات با موفقیت به‌روزرسانی شد.')
