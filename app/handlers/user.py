from __future__ import annotations
import json
import logging
from decimal import Decimal
from html import escape
from pathlib import Path
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.media_group import MediaGroupBuilder
from app.keyboards import main_reply_kb, customer_main_reply_kb, products_kb, phone_kb, choice_reply_kb, skip_reply_kb, back_reply_kb, back_kb, confirm_kb, checkout_kb, order_form_kb, pending_order_kb, rejected_receipt_kb, cancel_confirm_kb, profile_kb, profile_history_kb, profile_history_page_kb, customer_compose_kb, orders_list_kb, purchase_entry_kb, renewal_list_kb, renewal_order_kb, plan_download_kb, previous_value_kb, body_photo_kb, support_contact_kb
from app.states.forms import PurchaseForm, SupportForm, CancelOrder, CustomerInfoForm
from app.db import repositories as repo
from app.services.payment import payment
from app.services.telemetry import record
from app.services import client_records
from app.config import get_settings
from app.utils.text import money, status_fa, order_status_fa, split_message, progress_path, subscription_time_fa, order_code, jalali_dt
from app.utils.validation import clean_text, parse_number, parse_int
from app.utils.photos import MAX_BODY_PHOTOS, append_photo, delete_draft_photos, delete_photo_message, edit_photo_status, normalize_photos, photo_lock, stored_photos
from app.utils.media import BoundedBuffer, _inspect_upload
from app.utils.measurements import required_body_photos

router=Router(); log=logging.getLogger(__name__)
# PAYMENT_MODE=pending: orders are saved now and paid once the ZarinPal gateway is approved
PAYMENT_PENDING_NOTE=('⏳ درگاه پرداخت آنلاین در حال فعال‌سازی است.\n'
                      'به‌محض فعال شدن، از «🧾 تاریخچه سفارشات» و دکمه «💳 ادامه پرداخت» پرداخت را انجام بده؛ اطلاعات سفارش محفوظ است.')

def local_dt(value):
    return jalali_dt(value,get_settings().timezone)

def is_customer(_uid:int)->bool: return True


def _fsm_value(value):
    if isinstance(value,Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def _photos(snapshot: dict | None) -> list:
    raw=(snapshot or {}).get('body_photo_file_ids') or []
    if isinstance(raw,str):
        try: raw=json.loads(raw)
        except (TypeError,ValueError): raw=[]
    return raw if isinstance(raw,list) else []


def _value(value) -> str:
    if isinstance(value,_Html):
        return str(value)
    return escape(str(value if value not in (None, '') else '-'))


class _Html(str):
    pass


def _table(caption: str, rows: list[tuple], headers=None) -> str:
    """A narrow-screen-safe text card; no Rich Message client support required."""
    lines=[f'┌─ {escape(caption)}']
    for index, row in enumerate(rows):
        if headers:
            lines.append(f'├─ ردیف {index + 1}')
            lines.extend(f'│ {header}: {_value(value)}' for header, value in zip(headers, row))
        else:
            label, value=row
            lines.append(f'├─ {label}: {_value(value)}')
    lines.append('└────────────')
    return '\n'.join(lines)


def _bot_link(bot_username: str | None, text: str, payload: str) -> _Html:
    url=f'https://t.me/{bot_username}?start={payload}' if bot_username else f'/{payload}'
    return _Html(f'<a href="{url}">{escape(text)}</a>')


def _visible_bot_link(bot_username: str | None, payload: str) -> _Html:
    return _bot_link(bot_username,'نمایش',payload)


async def _screen(m: Message, text: str, markup=None, edit: bool=False):
    if edit:
        try:
            return await m.edit_text(text,reply_markup=markup,parse_mode='HTML',disable_web_page_preview=True)
        except TelegramBadRequest:
            return await m.answer(text,reply_markup=markup,parse_mode='HTML',disable_web_page_preview=True)
    return await m.answer(text,reply_markup=markup,parse_mode='HTML',disable_web_page_preview=True)


async def customer_menu(tg_id: int):
    return customer_main_reply_kb(await repo.has_course_access(tg_id))

async def home_message(message:Message, actor=None, welcome: bool=False):
    actor=actor or message.from_user
    user=await repo.get_user(actor.id)
    name=((user or {}).get('name') or actor.first_name or '').strip()
    hello=f'سلام {name} 👋' if name else 'سلام 👋'
    text=(f'{hello}\n\n🏆 برنامهٔ اختصاصی تمرین و تغذیه، متناسب با شرایط خودت.\n'
          'برای شروع «🛒 خرید دوره» رو بزن.' if welcome else '🏠 منوی اصلی')
    return await message.answer(
        text,
        reply_markup=await customer_menu(actor.id),
    )

async def show_products_message(message, edit: bool=False, actor_id: int | None=None, page: int=1):
    actor_id=actor_id or message.from_user.id
    if not await repo.sales_are_open():
        text='⏸️ فروش دوره‌ها موقتاً بسته است تا سفارش‌های فعلی با دقت رسیدگی شوند. لطفاً کمی بعد دوباره امتحان کن.'
        markup=products_kb([]) if edit else await customer_menu(actor_id)
        return await _screen(message,text,markup,edit)
    ps=await repo.get_products_for_user(actor_id)
    if ps:
        text=('🛒 خرید دوره\n\nدورهٔ موردنظرت را انتخاب کن؛ مدت و شرایط هر دوره در توضیحات آن مشخص است. '
              'از ۵ روز مانده به پایان، همان‌جا دکمهٔ تمدید فعال می‌شود.')
        page=max(1,min(page,(len(ps)+9)//10))
        markup=products_kb(ps[(page-1)*10:page*10],page,(len(ps)+9)//10)
    else:
        text='فعلاً هیچ برنامه‌ای برای خرید فعال نیست. کمی بعد دوباره سر بزن.'
        markup=products_kb([]) if edit else await customer_menu(actor_id)
    return await _screen(message,text,markup,edit)


async def _finish_deep_link(m: Message, reply):
    result=await reply
    try:
        await m.delete()
    except TelegramBadRequest:
        log.warning('Could not delete deep-link command message=%s',m.message_id)
    return result

@router.message(CommandStart())
async def start(m:Message,state:FSMContext,command:CommandObject):
    is_new_customer=await repo.get_user(m.from_user.id) is None
    await state.clear(); await repo.upsert_user(m.from_user)
    arg=(command.args or '').strip()
    if is_customer(m.from_user.id) and arg.startswith('order_'):
        try: oid=int(arg.removeprefix('order_'))
        except ValueError: return await _finish_deep_link(m,home_message(m))
        return await _finish_deep_link(m,show_order_detail_message(m,m.from_user.id,oid,from_link=True))
    if is_customer(m.from_user.id) and arg.startswith('photos_'):
        try: history_id=int(arg.removeprefix('photos_'))
        except ValueError: return await _finish_deep_link(m,home_message(m))
        return await _finish_deep_link(m,send_history_photos(m,m.from_user.id,history_id))
    if is_customer(m.from_user.id) and arg.startswith('course_'):
        try: oid=int(arg.removeprefix('course_'))
        except ValueError: return await _finish_deep_link(m,home_message(m))
        return await _finish_deep_link(m,show_order_detail_message(m,m.from_user.id,oid,active_course=True,from_link=True))
    if is_customer(m.from_user.id) and arg == 'profile_photos':
        row=await repo.latest_profile_photos(m.from_user.id)
        reply=_send_photo_items(m,row.get('product_title') or 'آخرین دوره',_photos(row.get('snapshot'))) if row else m.answer('هنوز عکسی برای دوره‌ای ثبت نشده است.')
        return await _finish_deep_link(m,reply)
    if is_customer(m.from_user.id) and arg.startswith('profile_history_'):
        try: page=int(arg.removeprefix('profile_history_'))
        except ValueError: return await _finish_deep_link(m,home_message(m))
        return await _finish_deep_link(m,show_profile_history(m,m.from_user.id,page,from_link=True))
    if is_customer(m.from_user.id) and arg.startswith('orders_'):
        try: page=int(arg.removeprefix('orders_'))
        except ValueError: return await _finish_deep_link(m,home_message(m))
        return await _finish_deep_link(m,show_orders(m,page,actor=m.from_user))
    if is_customer(m.from_user.id) and arg == 'profile':
        return await _finish_deep_link(m,show_profile(m))
    if is_customer(m.from_user.id) and arg.startswith('buy_'):
        try: pid=int(arg.removeprefix('buy_'))
        except ValueError: return await _finish_deep_link(m,home_message(m))
        return await _finish_deep_link(m,begin_purchase(m,state,pid,m.from_user))
    if is_customer(m.from_user.id) and arg.startswith('renew_'):
        try: oid=int(arg.removeprefix('renew_'))
        except ValueError: return await _finish_deep_link(m,home_message(m))
        return await _finish_deep_link(m,start_renewal(m,state,m.from_user,oid))
    if is_customer(m.from_user.id) and arg == 'support':
        return await _finish_deep_link(m,start_support(m,state))
    if is_customer(m.from_user.id) and arg.startswith('plan_'):
        try: oid=int(arg.removeprefix('plan_'))
        except ValueError: return await _finish_deep_link(m,home_message(m))
        return await _finish_deep_link(m,send_plan_to_customer(m,m.from_user.id,oid))
    if is_customer(m.from_user.id) and arg.startswith('receipt_'):
        try: oid=int(arg.removeprefix('receipt_'))
        except ValueError: return await _finish_deep_link(m,home_message(m))
        return await _finish_deep_link(m,retry_receipt_for_customer(m,state,m.from_user.id,oid))
    if is_customer(m.from_user.id) and arg.startswith('pay_'):
        try: oid=int(arg.removeprefix('pay_'))
        except ValueError: return await _finish_deep_link(m,home_message(m))
        return await _finish_deep_link(m,start_pending_payment(m,state,m.from_user.id,oid))
    if is_customer(m.from_user.id) and arg.startswith('form_'):
        try: oid=int(arg.removeprefix('form_'))
        except ValueError: return await _finish_deep_link(m,home_message(m))
        return await _finish_deep_link(m,start_order_form(m,state,m.from_user,oid))
    if is_customer(m.from_user.id) and arg.startswith('cancel_'):
        try: oid=int(arg.removeprefix('cancel_'))
        except ValueError: return await _finish_deep_link(m,home_message(m))
        return await _finish_deep_link(m,prompt_cancel_order(m,state,m.from_user.id,oid))
    if arg:
        return await _finish_deep_link(m,home_message(m))
    await home_message(m,welcome=is_new_customer)


def _command_id(text: str, prefix: str) -> int | None:
    command=(text or '').split('@',1)[0]
    try: return int(command.removeprefix(prefix)) if command.startswith(prefix) else None
    except ValueError: return None


@router.message(F.text.regexp(r'^/photos_\d+(?:@\w+)?$'))
async def history_photos_command(m: Message, state: FSMContext):
    await state.clear(); history_id=_command_id(m.text,'/photos_')
    if history_id is not None and is_customer(m.from_user.id):
        await send_history_photos(m,m.from_user.id,history_id)


@router.message(F.text.regexp(r'^/order_\d+(?:@\w+)?$'))
async def order_detail_command(m: Message, state: FSMContext):
    await state.clear(); oid=_command_id(m.text,'/order_')
    if oid is not None and is_customer(m.from_user.id):
        await show_order_detail_message(m,m.from_user.id,oid,from_link=True)


@router.message(F.text.regexp(r'^/course_\d+(?:@\w+)?$'))
async def course_detail_command(m: Message, state: FSMContext):
    await state.clear(); oid=_command_id(m.text,'/course_')
    if oid is not None and is_customer(m.from_user.id):
        await show_order_detail_message(m,m.from_user.id,oid,active_course=True)

@router.message(F.text=='/menu')
async def menu(m:Message,state:FSMContext):
    await state.clear(); await repo.upsert_user(m.from_user); await home_message(m)

@router.message(F.text=='/help')
async def help_command(m: Message):
    if not is_customer(m.from_user.id): return await home_message(m)
    await m.answer('راهنمای سریع\n\n🛒 خرید دوره: خرید یا تمدید سه دوره\n🏋️ دوره‌های فعال: برنامه‌های در حال استفاده\n🧾 تاریخچه سفارشات: وضعیت و جزئیات سفارش‌ها\n👤 اطلاعات من: مشاهده، عکس‌ها، ویرایش و سوابق\n💬 پیام به مربی: ویژه خریداران\n🎧 پشتیبانی: ارتباط مستقیم با ادمین\n\nهرجا مسیر را گم کردی، /menu را بزن.',reply_markup=await customer_menu(m.from_user.id))

@router.message(F.text.in_({'🛒 خرید دوره','🛒 خرید برنامه','📅 اشتراک ماهانه'}))
async def nav_products(m,state):
    if not is_customer(m.from_user.id): return await m.answer('این بخش برای مشتری‌هاست.')
    await state.clear(); await show_products_message(m,actor_id=m.from_user.id)

@router.message(F.text=='👤 اطلاعات من')
async def nav_profile(m,state):
    if not is_customer(m.from_user.id): return await m.answer('این بخش برای مشتری‌هاست.')
    await state.clear(); await show_profile(m)

@router.message(F.text.in_({'🧾 تاریخچه سفارشات','📦 سفارش‌های من'}))
async def nav_orders(m,state):
    if not is_customer(m.from_user.id): return await m.answer('این بخش برای مشتری‌هاست.')
    await state.clear(); await show_orders(m)

@router.message(F.text=='💬 پیام به مربی')
async def nav_support(m,state):
    if not is_customer(m.from_user.id): return await m.answer('این بخش برای مشتری‌هاست.')
    await start_support(m,state)

@router.message(F.text=='🔒 پیام به مربی')
async def locked_support(m, state):
    # A reply keyboard can outlive the payment that originally rendered it.
    await start_support(m, state)

@router.message(F.text=='🏋️ دوره‌های فعال')
async def nav_active_courses(m,state):
    if not is_customer(m.from_user.id): return await m.answer('این بخش برای مشتری‌هاست.')
    await state.clear(); await show_active_courses(m,m.from_user.id)

@router.message(F.text.in_({'🎧 پشتیبانی','🆘 پشتیبانی'}))
async def nav_admin_support(m):
    if not is_customer(m.from_user.id): return await m.answer('این بخش برای مشتری‌هاست.')
    await m.answer('🎧 پشتیبانی فنی\n\nبرای باز کردن گفت‌وگوی خصوصی ادمین، دکمه زیر رو بزن.',reply_markup=support_contact_kb(get_settings().support_url))

@router.message(F.text=='🏠 منوی اصلی')
async def nav_main(m,state): await state.clear(); await home_message(m)

@router.callback_query(F.data=='home')
async def home(c,state): await state.clear(); await home_message(c.message,c.from_user); await c.answer()

@router.callback_query(F.data=='buy:entry')
async def buy_entry(c,state):
    if not is_customer(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    await state.clear(); await show_products_message(c.message,edit=True,actor_id=c.from_user.id); await c.answer()

@router.callback_query(F.data=='products')
async def products(c,state:FSMContext):
    if not is_customer(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    await state.clear()
    await show_products_message(c.message,edit=True,actor_id=c.from_user.id); await c.answer()


@router.callback_query(F.data.startswith('products:page:'))
async def product_page(c,state:FSMContext):
    try: page=int(c.data.rsplit(':',1)[1])
    except ValueError: return await c.answer('درخواست نامعتبر است.')
    await state.clear(); await c.answer()
    await show_products_message(c.message,edit=True,actor_id=c.from_user.id,page=page)

@router.callback_query(F.data=='active_courses')
async def active_courses_callback(c,state):
    if not is_customer(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    await state.clear(); await show_active_courses(c.message,c.from_user.id,edit=True); await c.answer()


@router.callback_query(F.data.startswith('subscription:status:'))
async def subscription_status(c: CallbackQuery):
    if not is_customer(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    await c.answer('برای این پلن فعلاً اقدام تازه‌ای لازم نیست؛ وضعیت و زمان باقی‌مانده روی همین دکمه نوشته شده است.',show_alert=True)

# Checkout asks only for contact details; the questionnaire opens after a verified payment.
CONTACT_STEPS=('name','phone')
PURCHASE_STEPS={
 'nutrition':['age','gender','height','weight','allergy','restriction','supplements','notes','body_photo'],
 'training':['age','gender','height','weight','goal','training_history','notes','body_photo'],
 'complete':['age','gender','height','weight','allergy','restriction','supplements','goal','training_history','notes','body_photo']}
KEYMAP={'name':'name','phone':'phone','age':'age','gender':'gender','height':'height_cm','weight':'weight_kg','allergy':'allergy','restriction':'restriction','supplements':'supplements','goal':'goal','training_history':'training_history','notes':'notes','body_photo':'body_photo_file_ids','measurements':'measurements'}
PROFILE_KEYMAP={'allergy':'food_allergy','restriction':'food_restriction'}


def purchase_route(code: str, data: dict, fields=None) -> list[str]:
    refresh={'age','height','weight','notes','body_photo'}
    from app.services.catalog import FIELDS
    sequence=[step for step in FIELDS if step in fields] if fields is not None else PURCHASE_STEPS.get(code,[])
    sequence=[step for step in sequence if step not in CONTACT_STEPS]
    if 'measurements' in sequence:
        # Measurements are optional free text inside the notes step, never a separate template to fill.
        sequence=[step for step in sequence if step!='measurements'] if 'notes' in sequence else ['notes' if step=='measurements' else step for step in sequence]
    return [step for step in sequence if step in refresh or not data.get(KEYMAP[step])]


def contact_route(data: dict) -> list[str]:
    return [step for step in CONTACT_STEPS if not data.get(step)]


def _step_title(data: dict, step: str) -> str:
    steps=data.get('active_steps',PURCHASE_STEPS.get(data.get('product_code'),[]))
    if step not in steps: return ''
    return f'▫️ مرحله {steps.index(step)+1} از {len(steps)}\n'


def notes_prompt(data: dict) -> str:
    examples='اندازه‌های بدن (مثل دور کمر و شکم)، آسیب‌دیدگی یا بیماری' if data.get('measurement_hint') else 'آسیب‌دیدگی یا بیماری'
    return f'📝 توضیحات (اختیاری)\nاگه نکته‌ای هست که مربی باید بدونه بنویس؛ مثل {examples}.'

async def prompt(state, msg, step):
    d=await state.get_data()
    prompts={
      'name':('👤 نام و نام خانوادگی‌ات رو بنویس:',back_reply_kb(placeholder='مثلاً: علی رضایی')),
      'phone':('📱 شمارهٔ موبایلت رو با دکمهٔ زیر بفرست:',phone_kb()),
      'age':('چند سالته؟\nمثال: ۲۸',previous_value_kb('سن',d['age']) if d.get('age') is not None else back_reply_kb()),
      'gender':('جنسیت را انتخاب کن:',choice_reply_kb(['مرد','زن'])),
      'height':('قدت رو به سانتی‌متر وارد کن.\nمثال: ۱۷۸',previous_value_kb('قد',d['height_cm']) if d.get('height_cm') is not None else back_reply_kb()),
      'weight':('وزن فعلی‌ات رو به کیلوگرم وارد کن.\nمثال: ۷۹.۵',previous_value_kb('وزن',d['weight_kg']) if d.get('weight_kg') is not None else back_reply_kb()),
      'allergy':('حساسیت غذایی داری؟\nاگر داری، همینجا توضیحش بده.',skip_reply_kb('⏭️ ندارم')),
      'restriction':('محدودیت غذایی داری؟\nیکی از گزینه‌ها را انتخاب کن یا محدودیت‌هایت را با جزئیات بنویس.',choice_reply_kb(['⏭️ ندارم','گیاه‌خوار هستم','وگان هستم'])),
      'supplements':('اگر مکمل مصرف می‌کنی، اسمش رو بنویس؛ یا یکی از گزینه‌های زیر را بزن.',skip_reply_kb('⏭️ مصرف نمی‌کنم','مصرف می‌کنم')),
      'goal':('🎯 هدفت چیه؟\nیک گزینه را انتخاب کن یا هدف دلخواهت را بنویس. اگر چند هدف داری، همه را در یک پیام بفرست.',choice_reply_kb(['کاهش وزن و چربی','عضله‌سازی','افزایش قدرت','آمادگی و تناسب اندام'])),
      'training_history':('🏋️ سابقهٔ تمرینت چقدره؟\nیک گزینه را انتخاب کن یا مدت، نوع تمرین و وقفه‌ها را خودت بنویس.',choice_reply_kb(['تازه شروع می‌کنم','کمتر از ۶ ماه','۶ ماه تا ۲ سال','بیشتر از ۲ سال'])),
      'notes':(notes_prompt(d),skip_reply_kb('⏭️ بدون توضیحات',placeholder='مثلاً: دور کمر ۸۵، دور شکم ۹۲، زانوی چپم آسیب دیده…')),
    }
    if step=='body_photo': return await ask_photo(msg,state)
    text,markup=prompts[step]; await msg.answer(_step_title(d,step)+text,reply_markup=markup)

@router.callback_query(F.data.startswith('buy:'))
async def choose_product(c: CallbackQuery, state: FSMContext):
    """Start a completely fresh purchase session. Previous FSM data must never block a new order."""
    uid = c.from_user.id
    if not is_customer(uid):
        return await c.answer('دسترسی ندارید.', show_alert=True)

    try:
        pid = int(c.data.split(':', 1)[1])
    except (ValueError, IndexError):
        return await c.answer('درخواست نامعتبر.', show_alert=True)

    await c.answer('⏳ در حال آماده‌سازی فرم خرید…')
    await begin_purchase(c.message,state,pid,c.from_user)


def _stored_profile(user: dict) -> dict:
    """Stable profile values to reuse; changeable body values are only offered as defaults."""
    profile={
        'name': user.get('name') or '',
        'phone': user.get('phone') or '',
        'gender': user.get('gender') or '',
        'goal': user.get('goal') or '',
        'training_history': user.get('training_history') or '',
        'allergy': user.get('food_allergy') or '',
        'restriction': user.get('food_restriction') or '',
        'supplements': user.get('supplements') or '',
        'notes': user.get('notes') or '',
        'age': _fsm_value(user.get('age')),
        'height_cm': _fsm_value(user.get('height_cm')),
        'weight_kg': _fsm_value(user.get('weight_kg')),
    }
    if profile['supplements'] == 'مصرف می‌کنم':
        profile['supplements'] = ''
    return profile


async def begin_purchase(message: Message, state: FSMContext, pid: int, actor, renewal_of_order_id: int | None = None):
    """Checkout: contact details -> payment link. The questionnaire opens only after a verified payment."""
    uid=actor.id

    try:
        if not await repo.sales_are_open():
            await state.clear()
            return await message.answer('⏸️ فروش دوره‌ها موقتاً بسته است. کمی بعد دوباره تلاش کن.',reply_markup=await customer_menu(uid))
        # Make sure the user row exists even if /start was not used in this session.
        await repo.upsert_user(actor)
        p = await repo.get_product(pid)
        if not p or not p.get('active'):
            return await message.answer('❌ این محصول در حال حاضر در دسترس نیست.')
        # An unpaid checkout for the same plan is resumed instead of blocking a new one.
        pending=await repo.awaiting_payment_order(uid,pid)
        if pending:
            await state.clear()
            order=await repo.get_user_order(int(pending['id']),uid)
            return await send_payment_message(message,order)
        if renewal_of_order_id is None:
            catalog=await repo.get_products_for_user(uid)
            selected=next((x for x in catalog if int(x['id'])==pid),None)
            if selected and selected.get('form_pending') and selected.get('latest_order_id'):
                return await start_order_form(message,state,actor,int(selected['latest_order_id']))
            if selected and selected.get('purchased_before'):
                return await message.answer('این پلن قبلاً خریده شده است. از صفحهٔ خرید دوره، همان پلن را تمدید کن.')

        # Clear any stale FSM state before constructing the new order session.
        await state.clear()
        user = await repo.get_user(uid) or {}
        profile=_stored_profile(user)
        active_steps=contact_route(profile)
        await state.update_data(
            phase='checkout',
            product_id=int(p['id']),
            product_code=str(p['code']),
            product_title=str(p['title']),
            product_version=p.get('version',1),
            renewal_of_order_id=renewal_of_order_id,
            active_steps=active_steps,
            name=profile['name'],
            phone=profile['phone'],
        )
        from app.services.catalog import duration_label
        await message.answer(f"{p['title']}\n\n{p['description']}\n\nمدت: {duration_label(p)}\nمبلغ: {money(p['price_irr'])}")
        record('bot','checkout','started')
        if not active_steps:
            return await create_checkout(message,state,uid)
        first=active_steps[0]
        await state.set_state(getattr(PurchaseForm, first))
        await prompt(state, message, first)
    except Exception as exc:
        log.exception('Failed to start purchase for product=%s user=%s', pid, uid)
        # Never leave a broken FSM session behind after a failed start.
        try:
            await state.clear()
        except Exception:
            log.exception('Failed to clear FSM after purchase-start failure for user=%s', uid)
        await message.answer('❌ شروع خرید انجام نشد. اتصال به سرویس موقتاً با مشکل مواجه شد؛ دوباره روی همان برنامه بزن.')


def _checkout_method(settings) -> str | None:
    mode=settings.payment_mode.lower()
    if mode in {'zarinpal','both','pending'}: return 'zarinpal'
    if mode=='mock' and settings.app_env!='production': return 'mock'
    return None


async def create_checkout(message: Message, state: FSMContext, uid: int):
    """Save the unpaid order with the contact details, then show the payment button."""
    d=await state.get_data()
    contact={'name':d.get('name') or '','phone':d.get('phone') or ''}
    if d.get('order_id'):
        order=await repo.update_order_contact(int(d['order_id']),uid,contact['name'],contact['phone'])
        await state.clear()
        if not order:
            return await message.answer('این سفارش دیگر در انتظار پرداخت نیست.',reply_markup=await customer_menu(uid))
        return await send_payment_message(message,await repo.get_user_order(int(order['id']),uid))
    if not await repo.sales_are_open():
        await state.clear()
        return await message.answer('⏸️ فروش دوره‌ها موقتاً بسته است. کمی بعد دوباره تلاش کن.',reply_markup=await customer_menu(uid))
    p=await repo.get_product(d['product_id'])
    if not p or not p['active']:
        await state.clear()
        return await message.answer('❌ این محصول دیگه فعال نیست؛ یک برنامهٔ دیگه انتخاب کن.',reply_markup=await customer_menu(uid))
    if p.get('version',1)!=d.get('product_version',1):
        await state.clear()
        return await message.answer('شرایط دوره تغییر کرده است؛ لطفاً دوباره دوره را انتخاب و شرایط جدید را تأیید کن.',reply_markup=await customer_menu(uid))
    method=_checkout_method(get_settings())
    if not method:
        await state.clear()
        return await message.answer('❌ پرداخت آنلاین فعلاً فعال نیست. کمی بعد دوباره تلاش کن.',reply_markup=await customer_menu(uid))
    await state.set_state(PurchaseForm.submitting)
    try:
        order=await repo.create_order(uid,p,contact,method,d.get('renewal_of_order_id'))
    except ValueError as exc:
        await state.clear()
        if str(exc) in {'plan already purchased; renew it','renewal not eligible'}:
            return await message.answer('این دوره قبلاً خریده شده یا هنوز زمان تمدیدش نرسیده است. وضعیت دقیق را از «خرید دوره» ببین.',reply_markup=await customer_menu(uid))
        log.warning('Order validation rejected: %s',exc)
        return await message.answer('شرایط دوره تغییر کرده است؛ سفارش ثبت نشد. لطفاً دوباره دوره را انتخاب کن.',reply_markup=await customer_menu(uid))
    except Exception:
        record('bot','checkout','invoice','server_error')
        log.exception('create order failed'); await state.clear()
        return await message.answer('❌ ثبت سفارش انجام نشد. اتصال رو بررسی کن و دوباره روی همان دوره بزن.',reply_markup=await customer_menu(uid))
    record('bot','checkout','invoice')
    await state.clear()
    await send_payment_message(message,await repo.get_user_order(int(order['id']),uid) or {**order,'product_title':p['title']})


async def send_payment_message(message: Message, o: dict):
    """One message per payment attempt: order summary plus a fresh gateway link."""
    oid=int(o['id']); contact=repo._json_object(o.get('form_snapshot'))
    text=_table(f'🧾 سفارش {order_code(oid)}',[('دوره',o['product_title']),('نام',contact.get('name')),('شماره',contact.get('phone')),('مبلغ',money(o['amount']))])
    if get_settings().payment_pending:
        return await _screen(message,f'{text}\n\n{PAYMENT_PENDING_NOTE}',pending_order_kb(oid))
    after=('بعد از پرداخت موفق، همین‌جا فرم کوتاه ثبت‌نام را کامل می‌کنی.'
           if repo.form_required(repo._json_object(o.get('product_snapshot'))) else 'بعد از پرداخت موفق، دوره برایت فعال می‌شود.')
    if o.get('payment_method')=='mock':
        return await _screen(message,f'{text}\n\n🧪 حالت آزمایشی: پرداخت واقعی انجام نمی‌شود.\n{after}',checkout_kb(oid,mock=True))
    if o.get('payment_method')!='zarinpal':
        return await message.answer('روش پرداخت این سفارش قدیمی غیرفعال شده است. اگر قبلاً واریز کرده‌ای، پیش از خرید دوباره با پشتیبانی تماس بگیر.')
    try:
        pay=await payment.create_zarinpal(oid,o['amount'],o['product_title'])
        if not pay.success: raise RuntimeError(pay.message)
        await repo.set_zarinpal_authority(oid,pay.authority)
    except Exception:
        log.exception('zarinpal create failed for order=%s',oid)
        return await _screen(message,f'{text}\n\n❌ ساخت لینک پرداخت انجام نشد. سفارش ذخیره شده؛ چند لحظه بعد «💳 ادامه پرداخت» را بزن.',pending_order_kb(oid))
    await _screen(message,f'{text}\n\n🔒 برای پرداخت، دکمهٔ «پرداخت امن زرین‌پال» را بزن.\n{after}',checkout_kb(oid,pay.payment_url))


@router.callback_query(F.data.startswith('checkout:edit:'))
async def edit_checkout_contact(c: CallbackQuery, state: FSMContext):
    try: oid=int(c.data.rsplit(':',1)[1])
    except ValueError: return await c.answer('درخواست نامعتبر است.',show_alert=True)
    o=await repo.get_user_order(oid,c.from_user.id)
    if not o or o['status']!='awaiting_payment':
        return await c.answer('این سفارش دیگر در انتظار پرداخت نیست.',show_alert=True)
    await c.answer()
    await state.clear()
    await state.update_data(phase='checkout',order_id=oid,product_title=o['product_title'],active_steps=list(CONTACT_STEPS),name='',phone='')
    await state.set_state(PurchaseForm.name)
    await prompt(state,c.message,'name')


@router.callback_query(F.data.startswith('mockpay:'))
async def mock_pay(c: CallbackQuery, state: FSMContext):
    settings=get_settings()
    if settings.payment_mode.lower()!='mock' or settings.app_env=='production':
        return await c.answer('این روش پرداخت فعال نیست.',show_alert=True)
    try: oid=int(c.data.split(':',1)[1])
    except ValueError: return await c.answer('درخواست نامعتبر است.',show_alert=True)
    o=await repo.get_user_order(oid,c.from_user.id)
    if not o or o['status']!='awaiting_payment' or o.get('payment_method')!='mock':
        return await c.answer('این سفارش دیگر در انتظار پرداخت نیست.',show_alert=True)
    if not await repo.mark_mock_payment(oid,f'mock:{oid}'):
        return await c.answer('❌ پرداخت آزمایشی ثبت نشد؛ دوباره تلاش کن.',show_alert=True)
    await c.answer('✅ پرداخت آزمایشی ثبت شد.')
    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    # Same durable path as a verified gateway payment.
    from app.services.fulfillment import fulfill_order, record_delivery_failure
    try:
        await fulfill_order(c.bot,oid)
    except Exception as exc:
        await record_delivery_failure(oid,exc)


@router.callback_query(F.data.startswith('form:'))
async def open_order_form(c: CallbackQuery, state: FSMContext):
    try: oid=int(c.data.split(':',1)[1])
    except ValueError: return await c.answer('درخواست نامعتبر است.',show_alert=True)
    await c.answer()
    await start_order_form(c.message,state,c.from_user,oid)


async def start_order_form(message: Message, state: FSMContext, actor, oid: int):
    """Open (or reopen from the start) the questionnaire of a paid order."""
    o=await repo.get_user_order(oid,actor.id)
    if not o:
        return await message.answer('سفارش پیدا نشد یا متعلق به حساب شما نیست.')
    if o.get('form_completed_at'):
        return await message.answer(f'✅ فرم ثبت‌نام {order_code(oid)} قبلاً ثبت شده است.',reply_markup=await customer_menu(actor.id))
    if o['status']=='awaiting_payment':
        return await message.answer('فرم ثبت‌نام بعد از پرداخت موفق باز می‌شود.',reply_markup=pending_order_kb(oid))
    if not o.get('paid_at') or o['status']=='cancelled':
        return await message.answer('این سفارش فعال نیست.',reply_markup=await customer_menu(actor.id))
    terms=repo._json_object(o.get('product_snapshot'))
    fields=terms.get('form_fields') or []; questions=terms.get('questions') or []
    profile=_stored_profile(await repo.get_user(actor.id) or {})
    contact=repo._json_object(o.get('form_snapshot'))
    profile.update(name=contact.get('name') or profile['name'],phone=contact.get('phone') or profile['phone'])
    active_steps=purchase_route(str(o.get('product_code') or ''),profile,fields)
    await state.clear()
    await state.update_data(
        phase='form',
        order_id=oid,
        product_id=int(o['product_id']),
        product_code=str(o.get('product_code') or ''),
        product_title=str(o['product_title']),
        configured_fields=fields,
        measurement_hint='measurements' in fields,
        questions=questions,
        question_index=0,
        custom_answers=[],
        body_photo_file_ids=[],  # Every purchase starts a new dated assessment.
        previous_body_photo_file_ids=[],
        previous_body_photo_count=0,
        photo_collecting=True,
        active_steps=active_steps,
        **profile,
    )
    await message.answer(f"📝 فرم ثبت‌نام {o['product_title']}\n\nچند سؤال کوتاه تا مربی برنامه را دقیق برای خودت طراحی کند.")
    if not active_steps:
        return await finish_questionnaire(message,state,actor.id)
    first=active_steps[0]
    await state.set_state(getattr(PurchaseForm, first))
    await prompt(state, message, first)


@router.callback_query(F.data=='renew:list')
async def renew_list(c: CallbackQuery, state: FSMContext):
    if not is_customer(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    await state.clear(); rows=await repo.renewable_orders(c.from_user.id)
    if not rows: return await c.message.edit_text('فعلاً برنامه‌ای در بازهٔ تمدید نیست. تمدید فقط بعد از تحویل و از ۵ روز مانده به پایان اعتبار دوره فعال می‌شود.',reply_markup=purchase_entry_kb())
    await c.message.edit_text('🔄 تمدید برنامه\n\nبرنامهٔ قبلی را انتخاب کن؛ اطلاعات متغیر مثل سن، قد، وزن و عکس‌ها دوباره گرفته می‌شوند.',reply_markup=renewal_list_kb(rows)); await c.answer()


@router.callback_query(F.data.startswith('renew:'))
async def renew_order(c: CallbackQuery, state: FSMContext):
    if not is_customer(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    try: oid=int(c.data.split(':',1)[1])
    except (ValueError,IndexError): return await c.answer('درخواست نامعتبر است.',show_alert=True)
    old=await repo.get_user_order(oid,c.from_user.id)
    if not old or not old.get('renewal_eligible'): return await c.answer('تمدید فقط برای برنامهٔ تحویل‌شده و از ۵ روز مانده به پایان فعال است.',show_alert=True)
    await c.answer('⏳ فرم تمدید با اطلاعات جدید آماده می‌شود…')
    await begin_purchase(c.message,state,int(old['product_id']),c.from_user,oid)


async def start_renewal(message: Message, state: FSMContext, actor, oid: int):
    old=await repo.get_user_order(oid,actor.id)
    if not old or not old.get('renewal_eligible'):
        return await message.answer('تمدید فقط برای برنامهٔ تحویل‌شده و از ۵ روز مانده به پایان فعال است.')
    await begin_purchase(message,state,int(old['product_id']),actor,oid)

async def advance_after(state: FSMContext, msg: Message, current: str):
    d=await state.get_data(); seq=d.get('active_steps',PURCHASE_STEPS.get(d.get('product_code'),[]))
    if current==seq[-1]:
        if d.get('phase')=='checkout': return await create_checkout(msg,state,msg.chat.id)
        return await finish_questionnaire(msg,state)
    nxt=seq[seq.index(current)+1]
    await state.set_state(getattr(PurchaseForm,nxt)); await prompt(state,msg,nxt)


async def reuse_previous(m: Message,state: FSMContext,step: str):
    d=await state.get_data(); key=KEYMAP[step]
    if d.get(key) is None: return await m.answer('مقدار قبلی پیدا نشد؛ مقدار جدید را وارد کن.')
    await advance_after(state,m,step)


@router.message(PurchaseForm.age,F.text.startswith('✅ سن قبلی:'))
async def reuse_age(m,state): await reuse_previous(m,state,'age')

@router.message(PurchaseForm.height,F.text.startswith('✅ قد قبلی:'))
async def reuse_height(m,state): await reuse_previous(m,state,'height')

@router.message(PurchaseForm.weight,F.text.startswith('✅ وزن قبلی:'))
async def reuse_weight(m,state): await reuse_previous(m,state,'weight')

@router.message(PurchaseForm.name)
async def f_name(m,state):
    v=clean_text(m.text or '',100)
    if not v:return await m.answer('لطفاً نام را وارد کن.')
    await repo.update_user(m.from_user.id,name=v); await state.update_data(name=v); await advance_after(state,m,'name')

@router.message(PurchaseForm.phone,F.contact)
async def f_phone(m,state):
    c=m.contact
    if c.user_id and c.user_id!=m.from_user.id:return await m.answer('لطفاً شماره خودت را ارسال کن.')
    phone=clean_text(c.phone_number,32)
    if not phone or len(phone)<7:return await m.answer('شماره تلفن معتبر دریافت نشد. دوباره از دکمه ارسال شماره تلفن استفاده کن.')
    await repo.update_user(m.from_user.id,phone=phone); await state.update_data(phone=phone)
    await m.answer('✅ شماره تلفن دریافت و ذخیره شد.',reply_markup=ReplyKeyboardRemove()); await advance_after(state,m,'phone')

@router.message(PurchaseForm.phone)
async def f_phone_text(m): await m.answer('لطفاً از دکمه «📱 ارسال شماره تلفن» استفاده کن.')

@router.message(PurchaseForm.age)
async def f_age(m,state):
    v=parse_int(m.text,10,100)
    if v is None:return await m.answer('سن معتبر وارد کن.')
    await repo.update_user(m.from_user.id,age=v); await state.update_data(age=v); await advance_after(state,m,'age')

@router.message(PurchaseForm.gender)
async def f_gender(m,state):
    if m.text not in ('مرد','زن'):return await m.answer('یکی از گزینه‌ها را انتخاب کن.')
    await repo.update_user(m.from_user.id,gender=m.text); await state.update_data(gender=m.text); await advance_after(state,m,'gender')

@router.message(PurchaseForm.height)
async def f_height(m,state):
    v=parse_number(m.text)
    if v is None or not 100<=v<=230:return await m.answer('قد معتبر وارد کن (۱۰۰ تا ۲۳۰).')
    await repo.update_user(m.from_user.id,height_cm=v); await state.update_data(height_cm=v); await advance_after(state,m,'height')

@router.message(PurchaseForm.weight)
async def f_weight(m,state):
    v=parse_number(m.text)
    if v is None or not 25<=v<=300:return await m.answer('وزن معتبر وارد کن (۲۵ تا ۳۰۰).')
    await repo.update_user(m.from_user.id,weight_kg=v); await state.update_data(weight_kg=v); await advance_after(state,m,'weight')

async def simple_text(m,state,key,limit=500):
    raw=(m.text or '').strip()
    negative = raw in {'ندارم','نه','خیر','⏭️ ندارم','⏭️ رد کردن'}
    v='ندارم' if negative else clean_text(raw,limit)
    if not v:return await m.answer('یک مقدار وارد کن یا گزینه مناسب را انتخاب کن.')
    await state.update_data(**{key:v})
    profile_key=PROFILE_KEYMAP.get(key,key)
    await repo.update_user(m.from_user.id, **{profile_key:v})
    await advance_after(state,m,key)

@router.message(PurchaseForm.allergy, F.text.in_({'⏭️ ندارم','ندارم','نه','خیر'}))
async def allergy_skip(m,state):
    await state.update_data(allergy='ندارم'); await repo.update_user(m.from_user.id,food_allergy='ندارم'); await advance_after(state,m,'allergy')

@router.message(PurchaseForm.allergy)
async def allergy(m,state):
    await simple_text(m,state,'allergy')
@router.message(PurchaseForm.restriction, F.text.in_({'⏭️ ندارم','ندارم','نه','خیر'}))
async def restriction_skip(m,state):
    await state.update_data(restriction='ندارم'); await repo.update_user(m.from_user.id,food_restriction='ندارم'); await advance_after(state,m,'restriction')

@router.message(PurchaseForm.restriction)
async def restriction(m,state): await simple_text(m,state,'restriction')
@router.message(PurchaseForm.supplements)
async def supplements(m,state):
    raw=(m.text or '').strip()
    if raw == 'مصرف می‌کنم': return await m.answer('اسم مکمل‌هایی که مصرف می‌کنی رو بنویس.')
    v='ندارم' if raw in {'مصرف نمی‌کنم','ندارم','نه','خیر','⏭️ ندارم','⏭️ مصرف نمی‌کنم','⏭️ رد کردن'} else clean_text(raw,500)
    if not v:return await m.answer('اسم مکمل را بنویس یا «⏭️ مصرف نمی‌کنم» را بزن.')
    await state.update_data(supplements=v); await repo.update_user(m.from_user.id,supplements=v); await advance_after(state,m,'supplements')

@router.message(PurchaseForm.goal)
async def goal(m,state):
    v=clean_text(m.text or '',500)
    if not v:return await m.answer('هدفت را وارد کن.')
    await state.update_data(goal=v); await repo.update_user(m.from_user.id,goal=v); await advance_after(state,m,'goal')

@router.message(PurchaseForm.training_history)
async def history(m,state):
    v=clean_text(m.text or '',500)
    if not v:return await m.answer('سابقه تمرینت را وارد کن.')
    await state.update_data(training_history=v); await repo.update_user(m.from_user.id,training_history=v); await advance_after(state,m,'training_history')

@router.message(PurchaseForm.notes)
async def notes(m,state):
    raw=(m.text or '').strip(); v='' if raw.startswith('⏭️') or raw=='ندارم' else clean_text(raw,2000)
    await state.update_data(notes=v); await repo.update_user(m.from_user.id,notes=v); await advance_after(state,m,'notes')


async def ask_photo(msg,state):
    d=await state.get_data(); count=len(d.get('body_photo_file_ids',[])); collecting=bool(d.get('photo_collecting'))
    replacing=bool(d.get('photo_replacing')); adding=bool(d.get('photo_adding'))
    can_restore=replacing or adding
    back_text='↩️ بازگشت به عکس‌های قبلی' if replacing else 'بازگشت' if adding else None
    await state.set_state(PurchaseForm.body_photo)
    text=(_step_title(d,'body_photo')+f'📸 عکس بدن — {count}/{MAX_BODY_PHOTOS}\n\n'+
          ('عکس بعدی رو بفرست یا «✅ اتمام و ادامه» رو بزن.' if collecting and count else
           'عکس‌های قبلی آماده‌اند؛ می‌تونی همین‌ها رو نگه داری، بهشون اضافه کنی یا یک لیست تازه بسازی.' if count else
           'لیست جدید عکس‌ها را بفرست یا به عکس‌های قبلی برگرد.' if can_restore else
           'عکس‌های تازه این دوره را به ترتیب روبه‌رو، پشت، نیم‌رخ راست و نیم‌رخ چپ بفرست؛ با نور کافی، فاصله یکسان و پوشش ورزشی مناسب. صورت لازم نیست دیده شود. این عکس‌ها برای ارزیابی مربی هستند، نه انتشار عمومی.\n'+('برای آقایان هر چهار عکس لازم است.' if required_body_photos(d) else 'برای خانم‌ها اختیاری است؛ ارسال عکس به ارزیابی دقیق‌تر کمک می‌کند.')))
    message_id=d.get('photo_prompt_message_id')
    if await edit_photo_status(msg.bot,msg.chat.id,message_id,text):
        return
    sent=await msg.answer(text,reply_markup=body_photo_kb(count,collecting,can_restore,back_text,optional=not required_body_photos(d)))
    await state.update_data(photo_prompt_message_id=sent.message_id)


def _image_ref(file_id: str, kind: str, message_id: int | None = None) -> dict:
    item={'file_id':file_id,'type':kind}
    if message_id: item['message_id']=message_id
    return item

# Override skip keyboard helper compatibility below through explicit text handlers
@router.message(PurchaseForm.body_photo,F.photo)
async def body_photo(m,state):
    if not is_customer(m.from_user.id): return await state.clear()
    async with photo_lock(m.from_user.id):
        d=await state.get_data(); ids=list(d.get('body_photo_file_ids',[]))
        photo=m.photo[-1]
        if photo.file_size and photo.file_size > get_settings().max_body_photo_mb * 1024 * 1024:
            return await m.answer(f'❌ حجم هر عکس باید کمتر از {get_settings().max_body_photo_mb}MB باشه.')
        item=_image_ref(photo.file_id,'photo',m.message_id)
        item.update(direction=('front','back','right','left','extra','extra')[min(len(ids),5)],captured_at=m.date.isoformat())
        ids, accepted=append_photo(ids,item)
        if not accepted:
            await delete_photo_message(m.bot,m.chat.id,m.message_id)
            group_id=str(m.media_group_id) if m.media_group_id else None
            if not group_id or d.get('photo_limit_media_group_id') != group_id:
                await state.update_data(photo_limit_media_group_id=group_id)
                await m.answer('حداکثر ۶ عکس می‌تونی بفرستی؛ عکس‌های اضافه برای هر دو طرف پاک شدند و ۶ عکس اول نگه داشته شد.')
            return
        await state.update_data(body_photo_file_ids=ids,previous_body_photo_count=0,photo_collecting=True,photo_limit_media_group_id=None)
        await ask_photo(m,state)

@router.message(PurchaseForm.body_photo,F.document)
async def body_photo_doc(m,state):
    if not is_customer(m.from_user.id): return await state.clear()
    await m.answer(f'❌ این بخش فقط عکس تلگرام را می‌پذیرد. فایل، PDF یا تصویرِ ارسال‌شده به‌صورت Document قبول نیست؛ عکس را با گزینهٔ Gallery/Photo و حداکثر {get_settings().max_body_photo_mb}MB بفرست.')

@router.message(PurchaseForm.body_photo,F.text=='👁 دیدن عکس‌های فعلی')
async def view_purchase_photos(m: Message, state: FSMContext):
    d=await state.get_data()
    await _send_photo_items(m,'عکس‌های فعلی',list(d.get('body_photo_file_ids') or []))


@router.message(PurchaseForm.body_photo,F.text=='🗑 حذف آخرین عکس')
async def remove_purchase_photo(m: Message, state: FSMContext):
    async with photo_lock(m.from_user.id):
        data=await state.get_data(); photos=list(data.get('body_photo_file_ids') or [])
        if not photos:
            return await m.answer('هنوز عکسی برای حذف وجود ندارد.')
        removed=photos.pop()
        message_id=removed.get('message_id') if isinstance(removed,dict) else None
        await delete_photo_message(m.bot,m.chat.id,message_id)
        await state.update_data(body_photo_file_ids=photos)
        await ask_photo(m,state)


@router.message(PurchaseForm.body_photo,F.text=='✅ ادامه با همین عکس‌ها')
async def keep_previous_photos(m,state): await finish_photos(m,state)


@router.message(PurchaseForm.body_photo,F.text=='➕ افزودن عکس جدید')
async def add_purchase_photos(m: Message, state: FSMContext):
    data=await state.get_data()
    if len(data.get('body_photo_file_ids') or []) >= MAX_BODY_PHOTOS:
        return await m.answer('۶ عکس کامل است؛ برای افزودن عکس جدید اول «حذف آخرین عکس» را بزن.')
    await delete_photo_message(m.bot,m.chat.id,data.get('photo_prompt_message_id'))
    await state.update_data(photo_collecting=True,photo_adding=True,photo_prompt_message_id=None)
    await ask_photo(m,state)


@router.message(PurchaseForm.body_photo,F.text=='بازگشت')
async def leave_added_purchase_photos(m: Message, state: FSMContext):
    async with photo_lock(m.from_user.id):
        data=await state.get_data()
        await delete_photo_message(m.bot,m.chat.id,data.get('photo_prompt_message_id'))
        await state.update_data(photo_collecting=False,photo_adding=False,photo_prompt_message_id=None)
        await ask_photo(m,state)


@router.message(PurchaseForm.body_photo,F.text=='🆕 ارسال لیست عکس جدید')
async def replace_purchase_photos(m: Message, state: FSMContext):
    async with photo_lock(m.from_user.id):
        data=await state.get_data()
        previous=(list(data.get('previous_body_photo_file_ids') or []) if data.get('photo_replacing') else list(data.get('body_photo_file_ids') or []))
        await delete_photo_message(m.bot,m.chat.id,data.get('photo_prompt_message_id'))
        await state.update_data(
            previous_body_photo_file_ids=previous,
            body_photo_file_ids=[],
            previous_body_photo_count=0,
            photo_collecting=True,
            photo_adding=False,
            photo_replacing=True,
            photo_prompt_message_id=None,
        )
        await ask_photo(m,state)


@router.message(PurchaseForm.body_photo,F.text=='↩️ بازگشت به عکس‌های قبلی')
async def restore_previous_purchase_photos(m: Message, state: FSMContext):
    async with photo_lock(m.from_user.id):
        data=await state.get_data(); previous=normalize_photos(data.get('previous_body_photo_file_ids'))
        await delete_draft_photos(m.bot,m.chat.id,data.get('body_photo_file_ids'))
        await delete_photo_message(m.bot,m.chat.id,data.get('photo_prompt_message_id'))
        await state.update_data(
            body_photo_file_ids=previous,
            previous_body_photo_count=len(previous),
            photo_collecting=not bool(previous),
            photo_adding=False,
            photo_replacing=False,
            photo_prompt_message_id=None,
        )
        await ask_photo(m,state)

@router.message(PurchaseForm.body_photo,F.text.in_({'⏭️ رد کردن','⏭️ ادامه بدون عکس','✅ اتمام عکس‌ها','✅ اتمام و ادامه'}))
async def finish_photos(m,state):
    async with photo_lock(m.from_user.id):
        d=await state.get_data()
        photos=stored_photos(d.get('body_photo_file_ids'))
        if len(photos)<required_body_photos(d):
            return await m.answer('برای این ارزیابی چهار عکس تازه از روبه‌رو، پشت، راست و چپ لازم است؛ عکس‌های باقی‌مانده را بفرست.')
        await state.update_data(body_photo_file_ids=photos,photo_adding=False,photo_replacing=False,photo_limit_media_group_id=None)
        await advance_after(state,m,'body_photo')

@router.message(PurchaseForm.body_photo)
async def body_photo_invalid(m,state):
    await m.answer('❌ ورودی قابل قبول نیست. لطفاً فقط عکس را با گزینهٔ Photo/Gallery بفرست یا «✅ اتمام و ادامه» را بزن.')

async def finish_questionnaire(msg,state,tg_id=None):
    d=await state.get_data(); questions=d.get('questions',[]); index=d.get('question_index',0)
    if index<len(questions):
        await state.set_state(PurchaseForm.custom_question)
        return await msg.answer(f'📝 {questions[index]}',reply_markup=back_reply_kb())
    return await show_summary(msg,state,tg_id)


@router.message(PurchaseForm.custom_question)
async def custom_question(m,state):
    value=clean_text(m.text or '',1000)
    if not value: return await m.answer('لطفاً پاسخ را به صورت متن بفرست.')
    d=await state.get_data(); index=d.get('question_index',0); answers=d.get('custom_answers',[])
    answers.append({'question':d['questions'][index],'answer':value})
    await state.update_data(custom_answers=answers,question_index=index+1)
    await finish_questionnaire(m,state)


FIELD_LABELS={'name':'نام','phone':'تلفن','age':'سن','gender':'جنسیت','height':'قد','weight':'وزن','allergy':'حساسیت','restriction':'محدودیت غذایی','supplements':'مکمل','goal':'هدف','training_history':'سابقه تمرین','notes':'توضیحات','body_photo':'عکس‌ها'}


async def show_summary(msg,state,tg_id: int | None=None):
    d=await state.get_data(); ids=d.get('body_photo_file_ids',[])
    if 'body_photo' in d.get('active_steps',[]) and len(ids)<required_body_photos(d):
        return await ask_photo(msg,state)
    fields=[field for field in d.get('configured_fields') or d.get('active_steps') or [] if field in FIELD_LABELS]
    for field in CONTACT_STEPS:
        if field not in fields: fields.insert(CONTACT_STEPS.index(field),field)
    if d.get('measurement_hint') and 'notes' not in fields: fields.append('notes')
    details=[f"{FIELD_LABELS[field]}: {len(ids) if field=='body_photo' else d.get(KEYMAP[field]) or '-'}" for field in fields]
    details.extend(f"{a['question']}: {a['answer']}" for a in d.get('custom_answers',[]))
    text=f"📋 بررسی اطلاعات ثبت‌نام\n\n{d['product_title']}\n"+'\n'.join(details)+'\n\nاگر همه‌چیز درست است، «ثبت نهایی اطلاعات» را بزن.'
    await state.update_data(photo_prompt_message_id=None)
    await state.set_state(PurchaseForm.confirm)
    await msg.answer('✅ سؤال‌ها تمام شد.',reply_markup=await customer_menu(tg_id or msg.chat.id))
    parts=split_message(text)
    for part in parts[:-1]: await msg.answer(part)
    await msg.answer(parts[-1],reply_markup=confirm_kb())

@router.callback_query(PurchaseForm.confirm,F.data=='restart_form')
async def restart(c,state):
    d=await state.get_data()
    active_steps=list(d.get('active_steps',PURCHASE_STEPS.get(d.get('product_code'),[])))
    keep={k:d.get(k) for k in ('phase','order_id','product_id','product_code','product_title','measurement_hint','configured_fields','questions','name','phone','age','gender','height_cm','weight_kg','allergy','restriction','supplements','goal','training_history','notes')}
    previous=normalize_photos(d.get('body_photo_file_ids'))
    await state.clear()
    await state.update_data(**keep,body_photo_file_ids=previous,previous_body_photo_file_ids=previous,photo_collecting=not bool(previous),active_steps=active_steps)
    await state.update_data(question_index=0,custom_answers=[])
    if not active_steps:
        await c.answer()
        return await finish_questionnaire(c.message,state,c.from_user.id)
    first=active_steps[0]
    await state.set_state(getattr(PurchaseForm,first)); await prompt(state,c.message,first); await c.answer()

@router.callback_query(PurchaseForm.confirm,F.data=='confirm')
async def confirm(c,state):
    """Submit the questionnaire of an already paid order."""
    if not is_customer(c.from_user.id):return await c.answer('دسترسی ندارید.',show_alert=True)
    d=await state.get_data(); oid=d.get('order_id')
    if not oid:
        # A checkout started before pay-first checkout; its answers cannot be attached to an order.
        await state.clear(); await c.answer()
        return await c.message.answer('روند خرید به‌روز شده است؛ لطفاً دوره را دوباره از «🛒 خرید دوره» انتخاب کن.',reply_markup=await customer_menu(c.from_user.id))
    if 'body_photo' in d.get('active_steps',[]) and len(d.get('body_photo_file_ids') or [])<required_body_photos(d):
        await c.answer()
        return await ask_photo(c.message,state)
    snapshot={KEYMAP[field]:d.get(KEYMAP[field]) for field in d.get('configured_fields') or d.get('active_steps') or [] if field in KEYMAP and field not in CONTACT_STEPS and field!='measurements'}
    snapshot['custom_answers']=d.get('custom_answers',[])
    await c.answer('⏳ در حال ثبت اطلاعات…')
    await state.set_state(PurchaseForm.submitting)
    try:
        order=await repo.complete_order_form(int(oid),c.from_user.id,snapshot)
    except ValueError as exc:
        if str(exc)=='four body photos required':
            await state.set_state(PurchaseForm.body_photo)
            return await ask_photo(c.message,state)
        await state.clear()
        if str(exc)=='form already completed':
            return await c.message.answer(f'✅ فرم ثبت‌نام {order_code(oid)} قبلاً ثبت شده است.',reply_markup=await customer_menu(c.from_user.id))
        log.warning('Questionnaire rejected for order=%s: %s',oid,exc)
        return await c.message.answer('این سفارش دیگر فعال نیست؛ اگر فکر می‌کنی اشتباهی رخ داده، با پشتیبانی تماس بگیر.',reply_markup=await customer_menu(c.from_user.id))
    except Exception:
        log.exception('questionnaire submit failed for order=%s',oid)
        await state.set_state(PurchaseForm.confirm)
        return await c.message.answer('❌ ثبت اطلاعات انجام نشد؛ اطلاعاتت محفوظ است. چند لحظه بعد دوباره «ثبت نهایی اطلاعات» را بزن.',reply_markup=confirm_kb())
    await state.clear()
    record('bot','checkout','questionnaire')
    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    terms=repo._json_object(order.get('product_snapshot'))
    if terms.get('delivery_mode','manual')=='manual':
        text=terms.get('response_text') or '✅ ثبت‌نام کامل شد!\n\nاطلاعاتت برای مربی ارسال شد و در صف بررسی قرار گرفت؛ وقتی برنامه آماده شد، همین‌جا برات ارسال می‌شه.'
    else:
        text='✅ اطلاعاتت ثبت شد. ممنون!'
    await c.message.answer(text,reply_markup=await customer_menu(c.from_user.id))

@router.callback_query(PurchaseForm.confirm,F.data=='form_back')
async def form_back_from_confirm(c,state):
    d=await state.get_data(); steps=d.get('active_steps',[]); await c.answer()
    if not steps: return await finish_questionnaire(c.message,state,c.from_user.id)
    await state.set_state(getattr(PurchaseForm,steps[-1])); await prompt(state,c.message,steps[-1])

async def _handle_receipt(m, state, file_id: str, receipt_type: str):
    await state.clear()
    await m.answer('پرداخت فقط از درگاه انجام می‌شود؛ دریافت رسید غیرفعال است.', reply_markup=await customer_menu(m.from_user.id))

@router.message(PurchaseForm.receipt,F.photo)
async def receipt_photo(m,state):
    return await _handle_receipt(m,state,None,None)

@router.message(PurchaseForm.receipt,F.document)
async def receipt_document(m,state):
    return await _handle_receipt(m,state,None,None)


async def _valid_image_document(m: Message) -> bool:
    document = m.document
    limit = get_settings().max_body_photo_mb * 1024 * 1024
    if not document or not document.file_size or document.file_size > limit:
        return False
    if Path(document.file_name or '').suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
        return False
    try:
        buffer = BoundedBuffer(limit)
        await m.bot.download(document, destination=buffer, timeout=15)
        return bool(_inspect_upload(document.file_name, buffer.getvalue()))
    except (ValueError, TimeoutError, TelegramBadRequest):
        return False

@router.message(PurchaseForm.receipt)
async def receipt_other(m, state): await _handle_receipt(m,state,'','')

# Back: one logical step, never jump to home except at first step.
@router.message(F.text=='⬅️ بازگشت')
async def back(m,state):
    current=await state.get_state()
    if not current or not current.startswith('PurchaseForm:'):
        await state.clear(); return await home_message(m)
    name=current.split(':',1)[1]; d=await state.get_data(); code=d.get('product_code'); order=d.get('active_steps') or PURCHASE_STEPS.get(code,[])
    if name == 'receipt':
        oid=d.get('order_id'); await state.clear()
        return await m.answer(f'سفارش #{oid} ذخیره شده و هنوز پرداخت نشده.',reply_markup=pending_order_kb(oid))
    if name == 'confirm':
        if not order: return await show_products_message(m)
        prev=order[-1]
    else:
        if name not in order:return await home_message(m)
        idx=order.index(name)
        if idx==0:
            await state.clear(); return await show_products_message(m)
        prev=order[idx-1]
    key=KEYMAP.get(name)
    if key and key!='body_photo_file_ids': await state.update_data(**{key: None})
    await state.set_state(getattr(PurchaseForm,prev)); await prompt(state,m,prev)

# Generic explicit main button is handled above; no automatic main on every step.

async def show_profile(m, actor=None, edit: bool=False):
    actor=actor or m.from_user
    u=await repo.get_user(actor.id)
    if not u: await repo.upsert_user(actor); u=await repo.get_user(actor.id)
    photos=_photos(u)
    if not photos and u.get('body_photo_file_id'): photos=[u['body_photo_file_id']]
    sections=[
        _table('👤 اطلاعات من · مشخصات فردی',[('نام',u.get('name')),('شماره',u.get('phone')),('سن',u.get('age')),('جنسیت',u.get('gender'))]),
        _table('📏 وضعیت بدنی',[('قد',f"{u.get('height_cm') or '-'} سانتی‌متر"),('وزن',f"{u.get('weight_kg') or '-'} کیلوگرم"),('عکس‌های فعلی',f'{len(photos)} عدد')]),
        _table('🎯 تمرین',[('هدف',u.get('goal')),('سابقه تمرین',u.get('training_history'))]),
        _table('🥗 تغذیه',[('حساسیت غذایی',u.get('food_allergy')),('محدودیت غذایی',u.get('food_restriction')),('مکمل‌ها',u.get('supplements')),('توضیحات',u.get('notes'))]),
    ]
    await _screen(m,'\n\n'.join(sections),profile_kb(),edit)


async def _send_photo_items(m: Message, title: str, items: list):
    if not items:
        return await m.answer('برای این دوره عکسی ثبت نشده است.')
    selected=[]
    for item in items[:6]:
        file_id=item.get('file_id') if isinstance(item,dict) else item
        kind=item.get('type','photo') if isinstance(item,dict) else 'photo'
        if not file_id and isinstance(item,dict) and item.get('client_file_id'):
            from app.services.content import asset_path
            async with repo.db.acquire() as connection:
                record_file=await connection.fetchrow('''SELECT f.storage_key,f.filename,f.byte_size FROM client_files f
                    JOIN users u ON u.id=f.user_id WHERE f.id=$1 AND u.telegram_id=$2''',item['client_file_id'],m.chat.id)
            if record_file and record_file['storage_key']:
                path=asset_path(record_file['storage_key'])
                if path.is_file():
                    file_id=FSInputFile(path,filename=record_file['filename'])
                    if (record_file['byte_size'] or 0)>10*1024*1024: kind='document'
        if file_id: selected.append((file_id,kind))
    if not selected:
        return await m.answer('عکس‌های این دوره دیگر در تلگرام قابل دریافت نیستند.')
    photos=[file_id for file_id,kind in selected if kind=='photo']
    if len(photos) == len(selected) and len(photos) > 1:
        album=MediaGroupBuilder(caption=f'📸 {title} · {len(photos)} عکس')
        for file_id in photos: album.add_photo(media=file_id)
        try:
            await m.bot.send_media_group(m.chat.id,media=album.build())
            return
        except TelegramBadRequest:
            log.warning('Stored rich photo gallery is unavailable for user=%s',m.from_user.id)
    sent=0
    for index,(file_id,kind) in enumerate(selected,1):
        try:
            caption=f'📸 {title} — عکس {index} از {len(selected)}'
            if kind=='document': await m.bot.send_document(m.chat.id,file_id,caption=caption)
            else: await m.bot.send_photo(m.chat.id,file_id,caption=caption)
            sent+=1
        except TelegramBadRequest: log.warning('Stored profile photo is unavailable for user=%s',m.from_user.id)
    if not sent:
        await m.answer('عکس‌های این دوره دیگر در تلگرام قابل دریافت نیستند.')


async def send_history_photos(m: Message, tg_id: int, history_id: int):
    row=await repo.profile_history_entry(tg_id,history_id)
    if not row:
        return await m.answer('این سابقه پیدا نشد یا متعلق به حساب شما نیست.')
    await _send_photo_items(m,row.get('product_title') or 'دوره',_photos(row.get('snapshot')))


@router.callback_query(F.data=='profile_photos')
async def profile_photos(c: CallbackQuery):
    if not is_customer(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    row=await repo.latest_profile_photos(c.from_user.id)
    if not row:
        return await c.answer('هنوز عکسی برای دوره‌ای ثبت نشده است.',show_alert=True)
    await _send_photo_items(c.message,row.get('product_title') or 'آخرین دوره',_photos(row.get('snapshot')))
    await c.answer()

@router.callback_query(F.data.startswith('profile_history'))
async def profile_history_view(c,state:FSMContext):
    if not is_customer(c.from_user.id): return await c.answer('دسترسی ندارید.', show_alert=True)
    await state.clear()
    try: page=int(c.data.split(':',1)[1]) if ':' in c.data else 1
    except ValueError: page=1
    await show_profile_history(c.message,c.from_user.id,page,edit=True)
    await c.answer()


async def show_profile_history(m: Message, tg_id: int, page: int=1, edit: bool=False, from_link: bool=False):
    rows,total=await repo.profile_history(tg_id,page,3); total_pages=max(1,(total+2)//3)
    if not rows:
        return await _screen(m,'📚 هنوز سابقه‌ای از تکمیل فرم ثبت نشده است.',None,edit)
    lines=[f'📚 سوابق اطلاعات  ·  صفحه {page} از {total_pages}']
    bot_username=(await m.bot.me()).username
    for i,r in enumerate(rows,(page-1)*3+1):
        snap=r.get('snapshot') or {}
        photo_count=len(_photos(snap)); command=f'/photos_{r["id"]}'
        order=order_code(r['order_id']) if r.get('order_id') else '-'
        lines.append(_table(f'{i}. {r.get("product_title") or "-"}',[
            ('تاریخ',local_dt(r.get('created_at'))),('سفارش',order),
            ('مشخصات',f'{snap.get("age") or "-"} سال · {snap.get("gender") or "-"}'),
            ('قد / وزن',f'{snap.get("height_cm") or "-"} cm · {snap.get("weight_kg") or "-"} kg'),
            ('عکس‌ها',f'{photo_count} عکس'),
            ('دیدن عکس‌ها',_bot_link(bot_username,'نمایش عکس‌ها',command.removeprefix('/'))),
        ]))
    await _screen(m,'\n\n'.join(lines),profile_history_page_kb(page,total_pages,include_back=not from_link),edit)

@router.callback_query(F.data=='profile')
async def profile(c,state:FSMContext):
    if not is_customer(c.from_user.id):return await c.answer('دسترسی ندارید.',show_alert=True)
    await state.clear()
    await show_profile(c.message,c.from_user,edit=True); await c.answer()

async def show_orders(m, page: int = 1, edit: bool = False, actor=None):
    actor=actor or m.from_user
    orders=await repo.get_user_orders(actor.id)
    if not orders:
        if edit: return await m.edit_text('🧾 هنوز سفارشی نداری.',reply_markup=None)
        return await m.answer('🧾 هنوز سفارشی نداری.')
    page_size=3; total_pages=max(1,(len(orders)+page_size-1)//page_size); page=max(1,min(page,total_pages))
    rows=orders[(page-1)*page_size:page*page_size]
    lines=[f'🧾 تاریخچه سفارشات — صفحه {page} از {total_pages}']
    bot_username=(await m.bot.me()).username
    for o in rows:
        code=order_code(o['id']); renewal=bool(o.get('renewal_of_order_id'))
        status=order_status_fa(o['status'],renewal); command=f'/order_{o["id"]}'
        time=[] if o['status']=='cancelled' else [('زمان',subscription_time_fa(o.get('days_remaining'),o.get('duration_days')))]
        lines.append(_table(code,[('دوره',o['product_title']),('وضعیت',status),*time,('جزئیات',_bot_link(bot_username,'نمایش سفارش',command.removeprefix('/')))]))
    return await _screen(m,'\n\n'.join(lines),orders_list_kb(rows,page,total_pages),edit)


async def show_active_courses(m: Message, tg_id: int, edit: bool=False):
    rows=await repo.active_courses(tg_id)
    if not rows:
        text='🏋️ در حال حاضر دوره فعالی نداری. برای شروع یک دوره انتخاب کن.'
        return await (m.edit_text(text,reply_markup=None) if edit else m.answer(text))
    fallback=['🏋️ دوره‌های فعال']
    bot_username=(await m.bot.me()).username
    for row in rows:
        remaining=subscription_time_fa(row.get('days_remaining'),row.get('duration_days'))
        command=f'/course_{row["id"]}'
        fallback.append(_table(order_code(row['id']),[
            ('دوره',row['product_title']),
            ('وضعیت',order_status_fa(row['status'],bool(row.get('renewal_of_order_id')))),
            ('زمان',remaining),
            ('نمایش دوره',_bot_link(bot_username,'نمایش دوره',command.removeprefix('/'))),
        ]))
    await _screen(m,'\n\n'.join(fallback),None,edit)

@router.callback_query(F.data=='orders')
async def orders(c,state:FSMContext):
    if not is_customer(c.from_user.id):return await c.answer('دسترسی ندارید.',show_alert=True)
    await state.clear()
    await show_orders(c.message,edit=True,actor=c.from_user); await c.answer()


@router.callback_query(F.data.startswith('orders:page:'))
async def orders_page(c,state:FSMContext):
    if not is_customer(c.from_user.id):return await c.answer('دسترسی ندارید.',show_alert=True)
    await state.clear()
    try: page=int(c.data.split(':')[2])
    except (ValueError,IndexError): return await c.answer('درخواست نامعتبره.',show_alert=True)
    await show_orders(c.message,page,edit=True,actor=c.from_user); await c.answer()

@router.callback_query(F.data.startswith('order:plan:'))
async def get_plan(c,state:FSMContext):
    if not is_customer(c.from_user.id):return await c.answer('دسترسی ندارید.',show_alert=True)
    await state.clear()
    try:oid=int(c.data.split(':')[2])
    except (ValueError,IndexError):return await c.answer('درخواست نامعتبر.',show_alert=True)
    o=await repo.get_user_order(oid,c.from_user.id)
    if not o:return await c.answer('سفارش پیدا نشد.',show_alert=True)
    await c.answer()
    await send_plan_to_customer(c.message,c.from_user.id,oid)


@router.callback_query(F.data.startswith('order:pay:'))
async def pay_pending_order(c: CallbackQuery, state: FSMContext):
    if not is_customer(c.from_user.id):
        return await c.answer('دسترسی ندارید.', show_alert=True)
    try:
        oid=int(c.data.split(':')[2])
    except (ValueError, IndexError):
        return await c.answer('درخواست نامعتبر است.', show_alert=True)
    o=await repo.get_user_order(oid, c.from_user.id)
    if not o or o['status'] != 'awaiting_payment':
        return await c.answer('این سفارش دیگر در انتظار پرداخت نیست.', show_alert=True)

    await c.answer('⏳ در حال آماده‌سازی پرداخت…')
    await state.clear()
    await send_payment_message(c.message,o)


@router.callback_query(F.data.startswith('order:receipt:'))
async def retry_rejected_receipt(c: CallbackQuery, state: FSMContext):
    await c.answer('دریافت رسید غیرفعال شده است؛ پرداخت فقط از درگاه انجام می‌شود.',show_alert=True)


@router.callback_query(F.data.startswith('order:cancel:'))
async def cancel_order_prompt(c: CallbackQuery, state: FSMContext):
    if not is_customer(c.from_user.id):
        return await c.answer('دسترسی ندارید.', show_alert=True)
    try:
        oid=int(c.data.split(':')[2])
    except (ValueError, IndexError):
        return await c.answer('درخواست نامعتبر است.', show_alert=True)
    o=await repo.get_user_order(oid, c.from_user.id)
    if not o or o['status'] != 'awaiting_payment':
        return await c.answer('این سفارش دیگر قابل لغو نیست.', show_alert=True)
    await state.clear()
    await c.message.answer(
        f'⚠️ سفارش #{oid} لغو بشه؟\n\nسوابق سفارش برای پیگیری مالی حفظ می‌شه و بعدش می‌تونی سفارش تازه‌ای بسازی.',
        reply_markup=cancel_confirm_kb(oid)
    )
    await c.answer()


@router.callback_query(F.data.startswith('order:cancel_confirm:'))
async def cancel_order_confirm(c: CallbackQuery,state:FSMContext):
    if not is_customer(c.from_user.id):
        return await c.answer('دسترسی ندارید.', show_alert=True)
    try:
        oid=int(c.data.split(':')[2])
    except (ValueError, IndexError):
        return await c.answer('درخواست نامعتبر است.', show_alert=True)
    await state.clear()
    cancelled=await repo.cancel_awaiting_payment_order(oid, c.from_user.id)
    if not cancelled:
        return await c.answer('این سفارش دیگر قابل لغو نیست.', show_alert=True)
    await repo.add_audit(c.from_user.id,'cancel_unpaid_order','order',oid)
    await c.message.edit_text(f'✅ سفارش #{oid} لغو شد. هر زمان خواستی می‌تونی سفارش تازه‌ای شروع کنی.')
    await c.answer('سفارش لغو شد.')


@router.callback_query(F.data.startswith('order:cancel_abort:'))
async def cancel_order_abort(c: CallbackQuery,state:FSMContext):
    if not is_customer(c.from_user.id):
        return await c.answer('دسترسی ندارید.', show_alert=True)
    try:
        oid=int(c.data.split(':')[2])
    except (ValueError, IndexError):
        return await c.answer('درخواست نامعتبر است.', show_alert=True)
    await state.clear()
    o=await repo.get_user_order(oid, c.from_user.id)
    if not o or o['status'] != 'awaiting_payment':
        return await c.answer('این سفارش دیگر وجود ندارد.', show_alert=True)
    await c.message.edit_text(
        f"📦 سفارش #{oid}\n{o['product_title']}\n{status_fa(o['status'])}\n💰 {money(o['amount'])}",
        reply_markup=pending_order_kb(oid)
    )
    await c.answer('لغو سفارش انجام نشد.')

@router.callback_query(F.data.startswith('order:'))
async def order_detail(c,state:FSMContext):
    if not is_customer(c.from_user.id):return await c.answer('دسترسی ندارید.',show_alert=True)
    await state.clear()
    try:oid=int(c.data.split(':')[1])
    except (ValueError,IndexError):return await c.answer('درخواست نامعتبر.',show_alert=True)
    await show_order_detail_message(c.message,c.from_user.id,oid)
    await c.answer()


async def show_order_detail_message(m: Message, tg_id: int, oid: int, active_course: bool=False, from_link: bool=False):
    o=await repo.get_user_order(oid,tg_id)
    if not o:return await m.answer('سفارش پیدا نشد یا متعلق به حساب شما نیست.')
    code=order_code(oid)
    if o['status']=='cancelled':
        # A cancelled order has nothing to deliver: show which order it was and its status, no files or course path.
        if from_link: markup=None
        else: b=InlineKeyboardBuilder(); b.button(text='⬅️ تاریخچه سفارشات',callback_data='orders'); markup=b.as_markup()
        return await _screen(m,_table(f'📋 جزئیات سفارش {code}',[('دوره',o['product_title']),('کد سفارش',code),('وضعیت',status_fa('cancelled'))]),markup)
    if o['status']=='awaiting_payment':
        markup=pending_order_kb(oid)
    elif from_link or active_course:
        markup=plan_download_kb(oid)
    elif o['status']=='payment_rejected':
        markup=rejected_receipt_kb(oid)
    elif o.get('paid_at'):
        markup=renewal_order_kb(oid,bool(o.get('plan_file_id') or repo._json_object(o.get('product_snapshot')).get('delivery_mode') in {'content','channel'}),bool(o.get('renewal_eligible')))
    else:
        b=InlineKeyboardBuilder(); b.button(text='⬅️ تاریخچه سفارشات',callback_data='orders'); b.adjust(1); markup=b.as_markup()
    form_pending=bool(o.get('paid_at')) and not o.get('form_completed_at') and o['status']!='cancelled'
    if form_pending and not active_course:
        b=InlineKeyboardBuilder.from_markup(markup) if markup else InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text='📝 تکمیل فرم ثبت‌نام',callback_data=f'form:{oid}',style='success'))
        markup=b.as_markup()
    if o['status']=='needs_info':
        from app.db.core import db
        async with db.acquire() as connection:
            request_id=await connection.fetchval("SELECT id FROM order_info_requests WHERE order_id=$1 AND status='waiting'",oid)
        if request_id:
            b=InlineKeyboardBuilder.from_markup(markup)
            b.button(text='📝 تکمیل اطلاعات این سفارش',callback_data=f'info:{request_id}'); b.adjust(1)
            markup=b.as_markup()
    renewal=bool(o.get('renewal_of_order_id'))
    active_renewal=(f"\n\n🔄 تمدید #{o['active_renewal_id']}\n{progress_path(o['active_renewal_status'],True)}" if o.get('active_renewal_id') else '')
    text='\n\n'.join([
        _table(f"📋 {'جزئیات دوره' if active_course else ('تمدید' if renewal else 'جزئیات سفارش')} {code}",[
            ('دوره',o['product_title']),('کد سفارش',code),('زمان ثبت',local_dt(o.get('created_at'))),
            ('مبلغ',money(o['amount'])),('وضعیت','📝 منتظر تکمیل فرم ثبت‌نام' if form_pending else order_status_fa(o['status'],renewal)),
            ('زمان دوره',subscription_time_fa(o.get('days_remaining'),o.get('duration_days'))),
        ]),
        f'🧭 مسیر انجام دوره\n{progress_path(o["status"],renewal)}{active_renewal}',
    ])
    await _screen(m,text,markup)


async def send_plan_to_customer(m: Message, tg_id: int, oid: int):
    o=await repo.get_user_order(oid,tg_id)
    if o and o.get('status')=='cancelled':
        return await m.answer('این سفارش لغو شده و فایلی برای آن وجود ندارد.')
    if o and o.get('paid_at') and o.get('status')=='delivered':
        terms=repo._json_object(o.get('product_snapshot'))
        if terms.get('delivery_mode')=='channel':
            from app.services.fulfillment import channel_link
            link=await channel_link(m.bot,oid,tg_id)
            return await m.answer(f'ورود به کانال (فقط برای همین حساب):\n{link}' if link else 'اعتبار این اشتراک به پایان رسیده است؛ برای ادامه دوره را تمدید کن.')
        if terms.get('delivery_mode')=='content':
            from app.services.fulfillment import resend_content
            return await resend_content(m.bot,o,tg_id)
    if not o or not o.get('plan_file_id'):
        return await m.answer('برنامه هنوز آماده نیست یا به حساب شما تعلق ندارد.')
    if o.get('plan_type')=='photo':
        await m.bot.send_photo(tg_id,o['plan_file_id'],caption=f'📥 برنامه سفارش #{oid}',protect_content=True)
    elif o.get('plan_type')=='sticker':
        await m.bot.send_sticker(tg_id,o['plan_file_id'],protect_content=True)
    elif o.get('plan_type') in {'animation','video','audio','voice'}:
        await getattr(m.bot,'send_'+o['plan_type'])(tg_id,o['plan_file_id'],caption=f'📥 برنامه سفارش #{oid}',protect_content=True)
    else:
        await m.bot.send_document(tg_id,o['plan_file_id'],caption=f'📥 برنامه سفارش #{oid}',protect_content=True)
    if o.get('status')=='ready':
        await repo.update_order_status(oid,'delivered')


async def retry_receipt_for_customer(m: Message, state: FSMContext, tg_id: int, oid: int):
    await m.answer('دریافت رسید غیرفعال شده است؛ پرداخت فقط از درگاه انجام می‌شود.')


async def start_pending_payment(m: Message, state: FSMContext, tg_id: int, oid: int):
    o=await repo.get_user_order(oid,tg_id)
    if not o or o['status'] != 'awaiting_payment':
        return await m.answer('این سفارش دیگر در انتظار پرداخت نیست.')
    await send_payment_message(m,o)


async def prompt_cancel_order(m: Message, state: FSMContext, tg_id: int, oid: int):
    o=await repo.get_user_order(oid,tg_id)
    if not o or o['status'] != 'awaiting_payment':
        return await m.answer('این سفارش دیگر قابل لغو نیست.')
    await state.clear(); await state.update_data(cancel_order_id=oid); await state.set_state(CancelOrder.confirm)
    await m.answer(f'⚠️ برای لغو {order_code(oid)}، دقیقاً عبارت «لغو {order_code(oid)}» را ارسال کن.\nسوابق سفارش برای پیگیری مالی حفظ می‌شود.')


@router.message(CancelOrder.confirm)
async def confirm_cancel_order(m: Message, state: FSMContext):
    oid=(await state.get_data()).get('cancel_order_id')
    if not oid or (m.text or '').strip() != f'لغو {order_code(oid)}':
        return await m.answer('لغو انجام نشد. برای تأیید، همان عبارت نمایش‌داده‌شده را دقیق ارسال کن یا /menu را بزن.')
    cancelled=await repo.cancel_awaiting_payment_order(int(oid),m.from_user.id)
    await state.clear()
    if not cancelled:
        return await m.answer('این سفارش دیگر قابل لغو نیست.')
    await repo.add_audit(m.from_user.id,'cancel_unpaid_order','order',int(oid))
    await m.answer(f'✅ {order_code(oid)} لغو شد. هر زمان خواستی می‌توانی سفارش تازه‌ای شروع کنی.',reply_markup=await customer_menu(m.from_user.id))

@router.callback_query(F.data.startswith('info:'))
async def open_information_request(c,state):
    try: request_id=int(c.data.split(':')[1])
    except (ValueError,IndexError): return await c.answer('درخواست نامعتبر است.',show_alert=True)
    row=await client_records.owned_request(request_id,c.from_user.id)
    if not row or row['status']!='waiting' or row['order_status']!='needs_info':
        return await c.answer('این درخواست منتظر پاسخ شما نیست.',show_alert=True)
    await c.answer()
    await state.clear(); await state.update_data(info_request_id=request_id)
    await state.set_state(CustomerInfoForm.waiting)
    await c.message.answer(f"📝 تکمیل اطلاعات {order_code(row['order_id'])}\n\n{row['body']}\n\nمتن و فایل‌ها را همین‌جا بفرست؛ پاسخ‌های هر مرحله ذخیره می‌شوند. پس از تکمیل، «ثبت پاسخ برای بررسی» را بزن. این پاسخ به همین سفارش می‌رود.",reply_markup=choice_reply_kb(['👁 مرور پاسخ','✅ ثبت پاسخ برای بررسی','↩️ ادامه در فرصتی دیگر']))


@router.message(CustomerInfoForm.waiting)
async def information_response(m,state):
    d=await state.get_data(); request_id=d.get('info_request_id')
    if not request_id:
        await state.clear(); return await m.answer('دکمه تکمیل اطلاعات را در پیام درخواست دوباره بزن.')
    if m.text=='👁 مرور پاسخ':
        items=await client_records.response_summary(request_id,m.from_user.id)
        text='\n\n'.join(f"{i}. {item['content_text'] or ''}"+(f"\nپیوست: {item['file_name'] or item['content_type']}" if item['content_type']!='text' else '') for i,item in enumerate(items,1)) or 'هنوز پاسخی وارد نکرده‌ای.'
        for part in split_message(text): await m.answer(part)
        return
    if m.text=='↩️ ادامه در فرصتی دیگر':
        await state.clear()
        return await m.answer('پاسخ‌های واردشده ذخیره‌اند؛ با همان دکمه می‌توانی ادامه بدهی.',reply_markup=await customer_menu(m.from_user.id))
    if m.text=='✅ ثبت پاسخ برای بررسی':
        if not await client_records.submit_response(request_id,m.from_user.id):
            return await m.answer('ابتدا پاسخ را وارد کن؛ اگر قبلاً ثبت کرده‌ای منتظر بررسی مربی باش.')
        await state.clear()
        return await m.answer('✅ پاسخ ثبت شد و در صف بازبینی اطلاعات همین سفارش قرار گرفت.',reply_markup=await customer_menu(m.from_user.id))
    if len(m.text or m.caption or '')>2000 or _draft_file_too_large(m) or not _draft_file_allowed(m):
        return await m.answer('متن تا ۲۰۰۰ کاراکتر و فایل معتبر در محدوده حجم مجاز بفرست.')
    try: saved=await client_records.append_response(request_id,m.from_user.id,_draft_item(m))
    except ValueError: return await m.answer('حداکثر ۲۰ بخش پاسخ ثبت شده؛ «ثبت پاسخ برای بررسی» را بزن.')
    if not saved:
        await state.clear(); return await m.answer('این درخواست دیگر منتظر پاسخ نیست.',reply_markup=await customer_menu(m.from_user.id))
    if not m.media_group_id: await m.answer('به پاسخ این سفارش اضافه شد؛ پس از تکمیل، ثبت پاسخ را بزن.')


MAX_SUPPORT_DRAFT_ITEMS=10
SAFE_SUPPORT_SUFFIXES={'.jpg','.jpeg','.png','.webp','.gif','.heic','.mov','.mp4','.mp3','.m4a','.ogg','.wav','.pdf','.doc','.docx','.xlsx','.zip','.txt'}


async def start_support(m,state,actor=None):
    actor=actor or m.from_user
    if not is_customer(actor.id):return await m.answer('این بخش برای مشتری‌هاست.')
    if not await repo.has_course_access(actor.id):
        return await m.answer('🔒 پیام به مربی فقط برای افرادی فعال است که حداقل یک دوره را خریده‌اند. ابتدا از «🛒 خرید دوره» اقدام کن.',reply_markup=await customer_menu(actor.id))
    previous=await state.get_data()
    if previous.get('draft_items'):
        return await m.answer('پیش‌نویس قبلی هنوز ارسال نشده است؛ ابتدا «✅ ارسال پیام» یا «❌ لغو ارسال پیام» را بفرست.')
    await state.clear(); await state.update_data(support_mode='live',support_sent=False); await state.set_state(SupportForm.waiting)
    await m.answer('💬 گفتگو با مربی\nهر متن، عکس یا فایلی که اینجا بفرستی مستقیماً ثبت می‌شود؛ تأیید دیگری لازم نیست. می‌توانی چند پیام پشت‌سرهم بفرستی.',reply_markup=customer_compose_kb())

@router.callback_query(F.data=='support')
async def support(c,state):
    await start_support(c.message,state,c.from_user); await c.answer()

def _draft_item(m: Message) -> dict:
    media = m.photo[-1] if m.photo else m.video or m.animation or m.audio or m.voice or m.document
    file_name = getattr(media,'file_name',None)
    content_type = ('text' if m.text else 'photo' if m.photo else 'video' if m.video else 'animation' if m.animation else
                    'audio' if m.audio else 'voice' if m.voice else 'document' if m.document else 'other')
    return {
        'message_id':m.message_id,
        'content_type':content_type,
        'content_text':(m.text or m.caption or '')[:2000] or None,
        'file_id':getattr(media,'file_id',None),
        'file_name':file_name,
        'mime_type':getattr(media,'mime_type',None),
        'file_size':getattr(media,'file_size',None),
    }


def _draft_file_too_large(m: Message) -> bool:
    media = m.photo[-1] if m.photo else m.video or m.animation or m.audio or m.voice or m.document
    size=getattr(media,'file_size',0) or 0
    return size > get_settings().max_plan_file_mb * 1024 * 1024


def _draft_file_allowed(m: Message) -> bool:
    if m.text or m.photo or m.video or m.animation or m.audio or m.voice:
        return True
    if not m.document or not m.document.file_name:
        return False
    return Path(m.document.file_name).suffix.lower() in SAFE_SUPPORT_SUFFIXES


async def _discard_customer_draft(m: Message, items: list[dict]):
    ids=[int(item['message_id']) for item in items if item.get('message_id')]
    await repo.delete_support_messages(m.from_user.id,ids)
    for message_id in ids:
        try: await m.bot.delete_message(m.chat.id,message_id)
        except TelegramBadRequest: pass


@router.message(SupportForm.waiting, F.text == '🗑 پاک کردن پیش‌نویس')
async def clear_customer_draft(m: Message, state: FSMContext):
    if not is_customer(m.from_user.id): return
    d=await state.get_data()
    if d.get('support_mode') != 'customer_compose': return
    await _discard_customer_draft(m,list(d.get('draft_items') or []))
    await state.update_data(draft_items=[],draft_header_sent=False)
    await m.answer('🗑 پیش‌نویس پاک شد. پیام جدیدت رو اضافه کن.',reply_markup=customer_compose_kb())


@router.message(SupportForm.waiting, F.text == '❌ لغو ارسال پیام')
async def cancel_customer_draft(m: Message, state: FSMContext):
    if not is_customer(m.from_user.id): return
    d=await state.get_data(); await _discard_customer_draft(m,list(d.get('draft_items') or []))
    await state.clear(); await m.answer('ارسال پیام لغو شد و پیش‌نویس پاک شد.',reply_markup=await customer_menu(m.from_user.id))


@router.message(SupportForm.waiting, F.text == '✅ ارسال پیام')
async def send_customer_draft(m: Message, state: FSMContext):
    if not is_customer(m.from_user.id): return
    d=await state.get_data()
    if d.get('support_mode') != 'customer_compose': return
    items=list(d.get('draft_items') or [])
    if not items: return await m.answer('اول متن، عکس یا فایل پیامت رو اضافه کن.')
    try:
        while items:
            item=items[0]
            await repo.add_support_message(m.from_user.id,item['message_id'],direction='customer',sender_telegram_id=m.from_user.id,content_type=item['content_type'],content_text=item['content_text'],file_id=item.get('file_id'),file_name=item.get('file_name'),mime_type=item.get('mime_type'),file_size=item.get('file_size'))
            items.pop(0); await state.update_data(draft_items=items)
    except Exception:
        log.exception('support draft delivery failed')
        return await m.answer('❌ ارسال کامل نشد. دوباره «ارسال پیام» رو بزن؛ بخش‌های باقی‌مانده نگه داشته شدند.')
    await state.clear(); await m.answer('✅ پیام برای مربی ارسال شد.',reply_markup=await customer_menu(m.from_user.id))


@router.message(SupportForm.waiting)
async def support_message(m,state):
    if not is_customer(m.from_user.id): return
    d=await state.get_data()
    if d.get('support_mode')=='live':
        if m.text=='پایان گفتگو و بازگشت':
            await state.clear()
            return await m.answer('گفتگو بسته شد. همه پیام‌های شما با موفقیت ارسال و برای مربی ثبت شده‌اند.' if d.get('support_sent') else 'گفتگو بسته شد.',reply_markup=await customer_menu(m.from_user.id))
        if not await repo.has_course_access(m.from_user.id):
            await state.clear()
            return await m.answer('دسترسی گفتگو فعال نیست؛ از پشتیبانی پیگیری کن.',reply_markup=await customer_menu(m.from_user.id))
        if len(m.text or m.caption or '')>2000 or _draft_file_too_large(m) or not _draft_file_allowed(m):
            return await m.answer('پیام ثبت نشد؛ متن تا ۲۰۰۰ کاراکتر و فایل معتبر در محدوده حجم مجاز بفرست.')
        item=_draft_item(m); item.pop('message_id')
        try:
            await repo.add_support_message(m.from_user.id,m.message_id,direction='customer',sender_telegram_id=m.from_user.id,**item)
        except Exception:
            log.exception('Customer chat persistence failed')
            return await m.answer('پیام ثبت نشد؛ لطفاً دوباره بفرست.')
        await state.update_data(support_sent=True)
        return
    if d.get('support_mode') != 'customer_compose': return
    if len(m.text or m.caption or '')>2000:
        return await m.answer('لطفاً هر متن یا کپشن را حداکثر ۲۰۰۰ کاراکتر بفرست.')
    if _draft_file_too_large(m):
        return await m.answer(f'حجم هر فایل باید حداکثر {get_settings().max_plan_file_mb}MB باشد.')
    if not _draft_file_allowed(m):
        return await m.answer('این نوع فایل پشتیبانی نمی‌شود. عکس، ویدیو، صوت، PDF، Word، Excel، ZIP یا فایل متنی بفرست.')
    items=list(d.get('draft_items') or [])
    if len(items) >= MAX_SUPPORT_DRAFT_ITEMS:
        return await m.answer('پیامت آمادهٔ ارسال است؛ «✅ ارسال پیام» را بزن.')
    items.append(_draft_item(m)); await state.update_data(draft_items=items)
