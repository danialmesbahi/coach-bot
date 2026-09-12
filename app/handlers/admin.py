from __future__ import annotations
import json
import logging
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
from zipfile import ZipFile, BadZipFile
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.config import get_settings
from app.db import repositories as repo
from app.keyboards import sensi_kb, admin_team_kb, admin_order_kb, sensi_reply_kb, admin_team_reply_kb, receipt_actions_kb, rejected_receipt_kb, sensi_compose_kb, sensi_workflow_kb, sensi_customer_kb, MAIN, team_purchasers_kb, team_buyer_detail_kb, sensi_orders_list_kb, rtl_pager
from app.utils.text import money, split_message, status_fa, order_status_fa, payment_method_fa, public_user_id, progress_path, jalali_dt
from app.states.forms import NeedInfoForm, SupportForm, PlanDelivery

router = Router()
settings = get_settings()
log = logging.getLogger(__name__)
MAX_SUPPORT_DRAFT_ITEMS = 10


def role(uid: int): return settings.role(uid)
def is_sensi(uid: int): return role(uid) == 'sensi'
def is_team(uid: int): return role(uid) == 'admin_team'


def staff_link(bot_username: str | None, user_id: int, destination: str = 'profile') -> str:
    uid=public_user_id(user_id)
    return f'<a href="https://t.me/{bot_username}?start=staff_{destination}_{int(user_id)}">{uid}</a>' if bot_username else uid


def staff_order_link(bot_username: str | None, user_id: int, order_id: int) -> str:
    uid=public_user_id(user_id)
    return f'<a href="https://t.me/{bot_username}?start=staff_order_{int(order_id)}">{uid}</a>' if bot_username else uid


def _staff_page_url(bot_username: str | None, payload: str, text: str) -> str:
    url=f'https://t.me/{bot_username}?start={payload}' if bot_username else f'/{payload}'
    return f'{text}: {url}'


async def sensi_menu_kb():
    counts=await repo.sensi_dashboard_counts()
    return sensi_reply_kb(counts['unread'],counts['actionable'],counts['active'])


async def show_sensi_home(message: Message):
    counts=await repo.sensi_dashboard_counts()
    text=(
        '👨‍🏫 پنل سنسی\n\n'
        f"🔴 {int(counts['receipts'])} رسید برای بررسی\n"
        f"🟡 {int(counts['new_orders'])} سفارش برای شروع\n"
        f"🔵 {int(counts['designing'])} برنامه در حال طراحی\n"
        f"🟠 {int(counts['needs_info'])} سفارش منتظر اطلاعات\n"
        f"💬 {int(counts['unread'])} پیام خوانده‌نشده\n\n"
        'از منوی پایین انتخاب کن.'
    )
    return await message.answer(text,reply_markup=sensi_reply_kb(counts['unread'],counts['actionable'],counts['active']))


def parse_order_id(data: str):
    try: return int(data.split(':')[-1])
    except (ValueError, IndexError): return None


def local_dt(value):
    return jalali_dt(value,settings.timezone)


async def answer_long(message: Message, text: str, reply_markup=None):
    parts=split_message(text)
    for index, part in enumerate(parts):
        await message.answer(part, reply_markup=reply_markup if index==len(parts)-1 else None)


async def _delete_link_command(m: Message):
    try:
        await m.delete()
    except TelegramBadRequest:
        pass


def media_refs(raw):
    if isinstance(raw,str):
        try: raw=json.loads(raw)
        except Exception: raw=[raw]
    refs=[]
    for item in raw or []:
        if isinstance(item,dict) and item.get('file_id'):
            refs.append((item['file_id'],item.get('type','photo')))
        elif item:
            refs.append((item,'photo'))
    return refs


def recorded_weights(history) -> list[float]:
    values=[]
    for item in reversed(history):
        try: values.append(float((item.get('snapshot') or {}).get('weight_kg')))
        except (TypeError,ValueError): pass
    return values


async def notify_new_order(order_id: int):
    o = await repo.get_order(order_id)
    if not o: return False
    from app.main import bot
    text = f"🆕 سفارش جدید #{o['id']}\n\n👤 {o.get('name') or '-'}\n📱 {o.get('phone') or '-'}\n📦 {o['product_title']}\n💰 {money(o['amount'])}\n\nوضعیت: 🟡 پرداخت شده"
    try:
        await bot.send_message(settings.sensi_id, text, reply_markup=admin_order_kb(o['id'],o['status']))
        return True
    except Exception:
        log.exception('Failed to notify Sensi about order %s', order_id)
        return False


async def notify_receipt(order_id:int):
    o=await repo.get_order(order_id)
    if not o or not o.get('receipt_file_id'): return False
    from app.main import bot
    text=f"🧾 رسید کارت‌به‌کارت سفارش #{order_id}\n\n👤 {o.get('name') or '-'}\n📱 {o.get('phone') or '-'}\n📦 {o['product_title']}\n💰 {money(o['amount'])}\n\nرسید را بررسی کن:"
    try:
        if o.get('receipt_type')=='document':
            await bot.send_document(settings.sensi_id,o['receipt_file_id'],caption=text,reply_markup=receipt_actions_kb(order_id))
        else:
            await bot.send_photo(settings.sensi_id,o['receipt_file_id'],caption=text,reply_markup=receipt_actions_kb(order_id))
        return True
    except Exception:
        log.exception('Failed to notify receipt %s',order_id); return False

@router.callback_query(F.data.startswith('admin:approvepay:'))
async def approve_pay(c:CallbackQuery,state:FSMContext):
    if not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    await state.clear()
    oid=parse_order_id(c.data); o=await repo.approve_card_payment(oid,c.from_user.id) if oid else None
    if not o: return await c.answer('این رسید قبلاً بررسی شده یا معتبر نیست.',show_alert=True)
    await c.message.edit_reply_markup(reply_markup=None)
    await c.message.answer(f'✅ پرداخت سفارش #{oid} تأیید شد.')
    try:
        await c.bot.send_message(o['telegram_id'], f'✅ پرداخت سفارش #{oid} تأیید شد.\n\nسفارش شما در حال طراحی توسط مربی می‌باشد. 🏋️')
    except Exception:
        log.exception('Failed to notify customer after payment approval for order %s', oid)
        await c.message.answer('⚠️ پرداخت ثبت شد، اما ارسال پیام به مشتری ناموفق بود. سفارش همچنان تأییدشده است.')
    await c.answer('پرداخت تأیید شد.')

@router.callback_query(F.data.startswith('admin:rejectpay:'))
async def reject_pay(c:CallbackQuery,state:FSMContext):
    if not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    await state.clear()
    oid=parse_order_id(c.data); o=await repo.reject_card_payment(oid,c.from_user.id) if oid else None
    if not o: return await c.answer('این رسید قبلاً بررسی شده یا معتبر نیست.',show_alert=True)
    await c.message.edit_reply_markup(reply_markup=None)
    await c.message.answer(f'❌ رسید سفارش #{oid} رد شد.')
    try:
        await c.bot.send_message(o['telegram_id'], f'❌ رسید سفارش #{oid} تأیید نشد.\n\nمی‌تونی یک رسید واضح‌تر بفرستی یا با مربی در ارتباط باشی.', reply_markup=rejected_receipt_kb(oid))
    except Exception:
        log.exception('Failed to notify customer after payment rejection for order %s', oid)
        await c.message.answer('⚠️ رسید رد شد، اما ارسال پیام به مشتری ناموفق بود.')
    await c.answer('رسید رد شد.')

@router.message(F.text == '/admin')
async def admin_start(m: Message):
    r = role(m.from_user.id)
    if r == 'sensi': await show_sensi_home(m)
    elif r == 'admin_team': await m.answer('👥 پنل ادمین', reply_markup=admin_team_reply_kb())


@router.message(F.text == '/sensi')
async def sensi_command(m: Message):
    if is_sensi(m.from_user.id): await show_sensi_home(m)


@router.message(F.text == '/finance')
async def finance_command(m: Message):
    if is_team(m.from_user.id): await m.answer('📊 داشبورد مالی', reply_markup=admin_team_reply_kb())



@router.message(F.text.startswith('📋 کارها') | F.text.startswith('🗂 کارتابل') | (F.text == '🆕 سفارش‌های نیازمند اقدام'))
async def sensi_orders_reply(m: Message, state: FSMContext):
    if not is_sensi(m.from_user.id):
        return await m.answer('دسترسی ندارید.')
    await state.clear()
    await send_sensi_order_page(m,1)


async def send_sensi_order_page(target: Message, page: int, edit: bool=False):
    page_size=10
    orders,total=await repo.list_sensi_orders(page,page_size)
    if not orders:
        return await target.answer('✅ فعلاً سفارشی منتظر اقدام نیست.', reply_markup=await sensi_menu_kb())
    total_pages=max(1,(total+page_size-1)//page_size); page=max(1,min(page,total_pages))
    bot_username=(await target.bot.me()).username
    lines=[f'📋 کارهای سنسی  ·  صفحه {page} از {total_pages}','━━━━━━━━━━━━━━━━━━━━']
    for o in orders:
        name=o.get('name') or o.get('first_name') or 'بدون نام'
        kind='تمدید' if o.get('renewal_of_order_id') else 'خرید جدید'
        lines.extend([f"┃ {staff_order_link(bot_username,o['customer_id'],o['id'])}  │  {escape(name)}",f"┃ {escape(o['product_title'])}  │  {kind}",f"┃ {order_status_fa(o['status'],bool(o.get('renewal_of_order_id')))}",f"┗ سفارش #{o['id']}"])
    text='\n'.join(lines)+"\n\nروی شناسهٔ آبی بزن تا همان سفارش باز شود."
    markup=sensi_orders_list_kb(orders,page,total_pages)
    if edit:return await target.edit_text(text,reply_markup=markup,parse_mode='HTML',disable_web_page_preview=True)
    return await target.answer(text,reply_markup=markup,parse_mode='HTML',disable_web_page_preview=True)


async def send_progress_page(target, page: int=1, edit: bool=False):
    rows,total=await repo.customer_progress(page,10); pages=max(1,(total+9)//10); page=max(1,min(page,pages))
    if not rows: return await target.answer('هنوز مسیری برای نمایش وجود ندارد.',reply_markup=await sensi_menu_kb())
    bot_username=(await target.bot.me()).username
    lines=[f'👥 مشتری‌های فعال  ·  صفحه {page} از {pages}','━━━━━━━━━━━━━━━━━━━━']
    b=InlineKeyboardBuilder()
    for o in rows:
        name=escape(o.get('name') or o.get('first_name') or 'بدون نام')
        remaining='در حال آماده‌سازی' if o.get('days_remaining') is None else f'{max(0,int(o["days_remaining"]))} روز باقی‌مانده'
        if o.get('start_weight') is not None and o.get('current_weight') is not None:
            delta=float(o['current_weight'])-float(o['start_weight'])
            weight=f'تغییر وزن: {delta:+.1f} کیلو'
        else: weight='تغییر وزن: داده کافی نیست'
        lines.extend([f'┃ {staff_link(bot_username,o["user_id"],"profile")}  │  {name}',f'┃ {escape(o["product_title"])}  │  {remaining}',f'┃ {weight}  │  {int(o.get("delivered_count") or 0)} تحویل','┗━━━━━━━━━━━━━━━━━━'])
    nav=rtl_pager(f'sensi:progress:{page-1}' if page>1 else None,f'sensi:progress:{page+1}' if page<pages else None)
    if nav: b.row(*nav)
    b.row(InlineKeyboardButton(text='⌃ بستن فهرست',callback_data='sensi:progress:collapse'))
    text='\n'.join(lines).rstrip()
    if edit: return await target.edit_text(text,reply_markup=b.as_markup(),parse_mode='HTML',disable_web_page_preview=True)
    return await target.answer(text,reply_markup=b.as_markup(),parse_mode='HTML',disable_web_page_preview=True)


@router.callback_query(F.data=='sensi:progress:collapse')
async def progress_collapse(c: CallbackQuery):
    if not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    b=InlineKeyboardBuilder(); b.button(text='⌄ نمایش اشتراک‌های فعال',callback_data='sensi:progress:1',style='primary')
    await c.message.edit_text('🧭 فهرست اشتراک‌های فعال بسته شد.',reply_markup=b.as_markup()); await c.answer()


@router.message(F.text.startswith('👥 شاگردها') | F.text.startswith('👥 شاگردان فعال') | F.text.in_({'🧭 مسیر پیشرفت مشتری‌ها','👥 مشتری‌های فعال'}))
async def progress_reply(m: Message,state:FSMContext):
    if not is_sensi(m.from_user.id): return await m.answer('دسترسی ندارید.')
    await state.clear(); await send_progress_page(m)


@router.callback_query(F.data.startswith('sensi:progress:'))
async def progress_page(c: CallbackQuery,state:FSMContext):
    if not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    try: page=int(c.data.rsplit(':',1)[1])
    except (ValueError,IndexError): return await c.answer('درخواست نامعتبر است.',show_alert=True)
    await state.clear(); await send_progress_page(c.message,page,True); await c.answer()


def sales_report(now, month, total, items, title: str):
    monthly_revenue=int(month['revenue'] or 0)
    commission=monthly_revenue*settings.development_team_percent//100
    net=monthly_revenue-commission
    text=(f'{title}\n━━━━━━━━━━━━━━━━━━━━\n📅 {jalali_dt(now,settings.timezone,"%Y/%m")}\n'
          f'تعداد فروش │ {int(month["orders"] or 0)}\n'
          f'فروش ماه   │ {money(monthly_revenue)}\n'
          '━━━━━━━━━━━━━━━━━━━━\n')
    if items:
        for item in items:
            name=item.get('name') or 'بدون نام'
            text+=f"┃ #{item['order_id']}  │  {name}\n┃ {item['product_title']}\n┃ {money(item['amount'])}\n┗━━━━━━━━━━━━━━━━━━\n"
    else: text+='— بدون فروش ثبت‌شده\n'
    return (text+'\n━━━━━━━━━━━━━━━━━━\n'
            f'🛠 سهم تیم توسعه ({settings.development_team_percent}%): {money(commission)}\n'
            f'💵 سهم سنسی پس از کسر کارمزد: {money(net)}\n'
            f'📊 فروش کل تاریخ: {money(int(total["revenue"] or 0))}\n'
            f'🔢 تعداد فروش کل: {int(total["orders"] or 0)}')


def sales_pager(kind: str,page: int,total: int):
    pages=max(1,(total+7)//8)
    nav=rtl_pager(f'sales:{kind}:{page-1}' if page>1 else None,f'sales:{kind}:{page+1}' if page<pages else None)
    return InlineKeyboardBuilder().row(*nav).as_markup() if nav else None

@router.message(F.text.in_({'📊 آمار فروش','📊 فروش ماه جاری','📊 فروش و درآمد','📈 درآمد'}))
async def stats_reply(m: Message, state: FSMContext):
    if not (is_sensi(m.from_user.id) or is_team(m.from_user.id)):
        return await m.answer('دسترسی ندارید.')
    await state.clear()
    now = datetime.now(ZoneInfo(settings.timezone))
    month = await repo.monthly_sales(now.year, now.month)
    total = await repo.total_sales()
    items,item_count = await repo.monthly_sales_items(now.year, now.month)
    if is_sensi(m.from_user.id):
        return await answer_long(m,sales_report(now,month,total,items,'📊 فاکتور فروش سنسی'),reply_markup=sales_pager('s',1,item_count))
    await answer_long(m,sales_report(now,month,total,items,'🧾 فاکتور ماهانه تیم ادمین'),reply_markup=sales_pager('t',1,item_count))


@router.callback_query(F.data.startswith('sales:'))
async def sales_page(c: CallbackQuery):
    try: _,kind,raw_page=c.data.split(':'); page=int(raw_page)
    except (ValueError,IndexError): return await c.answer('درخواست نامعتبر است.',show_alert=True)
    if kind=='s' and not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    if kind=='t' and not is_team(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    now=datetime.now(ZoneInfo(settings.timezone)); month=await repo.monthly_sales(now.year,now.month); total=await repo.total_sales()
    items,count=await repo.monthly_sales_items(now.year,now.month,page,8); pages=max(1,(count+7)//8); page=max(1,min(page,pages))
    title='📊 فاکتور فروش سنسی' if kind=='s' else '🧾 فاکتور ماهانه تیم ادمین'
    await c.message.edit_text(sales_report(now,month,total,items,f'{title} · صفحه {page}/{pages}'),reply_markup=sales_pager(kind,page,count)); await c.answer()


@router.message(F.text == '👥 اطلاعات خریداران')
async def team_purchasers_reply(m: Message):
    if not is_team(m.from_user.id):
        return await m.answer('دسترسی ندارید.')
    await send_purchaser_page(m, 1)


async def send_purchaser_page(target, page: int, edit: bool=False):
    rows, total = await repo.purchaser_list(page, 10)
    if not rows:
        return await target.answer('در این صفحه خریداری وجود ندارد.', reply_markup=admin_team_reply_kb())
    total_pages = max(1, (total + 9) // 10)
    text = f'👥 خریداران موفق  ·  صفحه {page} از {total_pages}\n━━━━━━━━━━━━━━━━━━\nروی شناسهٔ یکتا بزن تا پروفایل کامل، پیام‌ها و خریدها را ببینی.'
    markup=team_purchasers_kb(rows,page,total_pages)
    if edit: return await target.edit_text(text,reply_markup=markup)
    return await target.answer(text,reply_markup=markup)


@router.callback_query(F.data == 'team:home')
async def team_home(c: CallbackQuery, state: FSMContext):
    if not is_team(c.from_user.id):
        return await c.answer('دسترسی ندارید.', show_alert=True)
    await state.clear()
    await c.message.answer(
        '👥 پنل ادمین',
        reply_markup=admin_team_reply_kb()
    )
    await c.answer()


@router.callback_query(F.data.startswith('team:buyers:'))
async def team_buyers_page(c: CallbackQuery):
    if not is_team(c.from_user.id):
        return await c.answer('دسترسی ندارید.', show_alert=True)
    try: page=int(c.data.split(':')[2])
    except (ValueError,IndexError): return await c.answer('درخواست نامعتبر است.', show_alert=True)
    await send_purchaser_page(c.message, page, edit=True)
    await c.answer()


@router.callback_query(F.data.startswith('team:buyer:'))
async def team_buyer_detail(c: CallbackQuery):
    if not is_team(c.from_user.id):
        return await c.answer('دسترسی ندارید.', show_alert=True)
    try:
        parts=c.data.split(':'); user_id=int(parts[2]); page=int(parts[3])
    except (ValueError,IndexError): return await c.answer('درخواست نامعتبر است.', show_alert=True)
    user, orders = await repo.purchaser_detail(user_id)
    if not user: return await c.answer('کاربر پیدا نشد.', show_alert=True)
    history=await repo.profile_history_for_user(user_id,50)
    messages=await repo.support_messages_for_user(user_id,50)
    text=(
        '👤 اطلاعات کامل مشتری\n\n'
        f"شناسه یکتا: {public_user_id(user_id)}\n"
        f"نام: {user.get('name') or '-'}\n"
        f"شماره تلفن: {user.get('phone') or '-'}\n"
        f"Telegram ID: {user.get('telegram_id') or '-'}\n"
        f"Username: {('@'+user['username']) if user.get('username') else '-'}\n"
        f"سن: {user.get('age') or '-'}\n"
        f"جنسیت: {user.get('gender') or '-'}\n"
        f"قد: {user.get('height_cm') or '-'}\n"
        f"وزن: {user.get('weight_kg') or '-'}\n"
        f"هدف: {user.get('goal') or '-'}\n"
        f"سابقه تمرین: {user.get('training_history') or '-'}\n"
        f"حساسیت غذایی: {user.get('food_allergy') or '-'}\n"
        f"محدودیت غذایی: {user.get('food_restriction') or '-'}\n"
        f"مکمل‌ها: {user.get('supplements') or '-'}\n"
        f"توضیحات: {user.get('notes') or '-'}\n"
        f"\n🧾 تعداد سفارش‌ها: {len(orders)}"
        f"\n📚 تعداد نسخه‌های تاریخی پروفایل: {len(history)}"
        f"\n💬 تعداد پیام‌های اخیر: {len(messages)}"
    )
    await c.message.answer(text, reply_markup=team_buyer_detail_kb(page))
    seen=set()
    for o in orders:
        d=o.get('form_snapshot') or {}
        if isinstance(d, str):
            try: d=json.loads(d)
            except Exception: d={}
        otext=(
            f"🧾 سفارش #{o['id']}\n"
            f"📦 {o['product_title']}\n"
            f"🕐 ثبت سفارش: {local_dt(o.get('created_at'))}\n"
            f"💰 مبلغ: {money(o['amount'])}\n"
            f"💳 روش پرداخت: {payment_method_fa(o.get('payment_method'))}\n"
            f"📌 وضعیت: {status_fa(o.get('status'))}\n"
            f"🔖 مرجع پرداخت: {o.get('gateway_ref') or '-'}\n"
            f"📅 پرداخت: {local_dt(o.get('paid_at'))}\n"
            f"🎂 سن هنگام خرید: {d.get('age') or '-'}\n"
            f"جنسیت هنگام خرید: {d.get('gender') or '-'}\n"
            f"📏 قد هنگام خرید: {d.get('height_cm') or '-'}\n"
            f"⚖️ وزن هنگام خرید: {d.get('weight_kg') or '-'}\n"
            f"🎯 هدف: {d.get('goal') or '-'}\n"
            f"🏋️ سابقه تمرین: {d.get('training_history') or '-'}\n"
            f"🥜 حساسیت: {d.get('allergy') or '-'}\n"
            f"🍽️ محدودیت: {d.get('restriction') or '-'}\n"
            f"💊 مکمل‌ها: {d.get('supplements') or '-'}\n"
            f"📝 توضیحات: {d.get('notes') or '-'}"
        )
        await c.message.answer(otext)
        photos = []
        raw_photos = d.get('body_photo_file_ids') or []
        photos.extend(media_refs(raw_photos))
        if d.get('body_photo_file_id'):
            photos.append((d.get('body_photo_file_id'),'photo'))
        for fid, kind in photos[:6]:
            if fid in seen: continue
            seen.add(fid)
            try:
                if kind=='document': await c.message.answer_document(fid, caption=f"📸 عکس بدن مشتری — سفارش #{o['id']}")
                else: await c.message.answer_photo(fid, caption=f"📸 عکس بدن مشتری — سفارش #{o['id']}")
            except Exception: log.exception('Failed to send purchaser body photo')
        if o.get('receipt_file_id'):
            try:
                if o.get('receipt_type')=='document': await c.message.answer_document(o['receipt_file_id'], caption=f"🧾 رسید پرداخت سفارش #{o['id']}")
                else: await c.message.answer_photo(o['receipt_file_id'], caption=f"🧾 رسید پرداخت سفارش #{o['id']}")
            except Exception: log.exception('Failed to send purchaser receipt')
    if history:
        lines=['📚 تاریخچهٔ ثبت اطلاعات مشتری','']
        for item in history:
            snap=item.get('snapshot') or {}
            if isinstance(snap,str):
                try: snap=json.loads(snap)
                except Exception: snap={}
            lines.append(f"• {item.get('product_title') or '-'} · {local_dt(item.get('created_at'))} · سفارش #{item.get('order_id') or '-'}")
            lines.append(f"  سن {snap.get('age') or '-'} · قد {snap.get('height_cm') or '-'} · وزن {snap.get('weight_kg') or '-'}")
        await answer_long(c.message,'\n'.join(lines))
    if messages:
        lines=['💬 پیام‌های اخیر مشتری','']
        for item in messages[-20:]:
            who='مشتری' if item.get('direction')=='customer' else 'سنسی'
            lines.append(f"{who} · {local_dt(item.get('created_at'))}\n{(item.get('content_text') or '['+(item.get('content_type') or 'پیام')+']')[:500]}\n")
        await answer_long(c.message,'\n'.join(lines))
    await repo.add_audit(c.from_user.id,'view_purchaser','user',user_id,{'page':page})
    await c.answer()


@router.message(F.text.startswith('💬 پیام‌ها'))
async def sensi_messages_reply(m: Message, state: FSMContext):
    if not is_sensi(m.from_user.id):
        return await m.answer('دسترسی ندارید.')
    await state.clear()
    await send_support_threads(m)


@router.message(F.text == '🏠 داشبورد سنسی')
async def sensi_home_reply(m: Message, state: FSMContext):
    if not is_sensi(m.from_user.id):
        return await m.answer('دسترسی ندارید.')
    await state.clear()
    await show_sensi_home(m)

async def send_support_threads(target, page: int=1, edit: bool=False):
    page_size=10
    threads,total = await repo.support_threads(page,page_size)
    if not threads:
        return await target.answer('💬 هنوز هیچ گفت‌وگویی ثبت نشده است.', reply_markup=await sensi_menu_kb())
    total_pages=max(1,(total+page_size-1)//page_size); page=max(1,min(page,total_pages)); rows=threads
    b = InlineKeyboardBuilder()
    bot_username=(await target.bot.me()).username
    lines=[f'💬 همهٔ گفت‌وگوها  ·  صفحه {page} از {total_pages}','━━━━━━━━━━━━━━━━━━━━']
    for t in rows:
        name=escape(t.get('name') or t.get('first_name') or 'بدون نام')
        unread=int(t.get('unread_count') or 0)
        state_text=f'{unread} خوانده‌نشده' if unread else 'همه خوانده‌شده'
        lines.extend([f'┃ {staff_link(bot_username,t["user_id"],"thread")}  │  {name}',f'┃ {state_text}  │  {int(t.get("message_count") or 0)} پیام',f'┃ {local_dt(t.get("last_message_at"))}','┗━━━━━━━━━━━━━━━━━━'])
    nav=rtl_pager(f'sensi:messages:page:{page-1}' if page>1 else None,f'sensi:messages:page:{page+1}' if page<total_pages else None)
    if nav: b.row(*nav)
    b.row(InlineKeyboardButton(text='⌃ بستن فهرست',callback_data='sensi:messages:collapse'))
    text='\n'.join(lines)+'\nروی شناسهٔ آبی بزن تا پروفایل، مسیر پیشرفت و پیام‌ها باز شود.'
    if edit: return await target.edit_text(text,reply_markup=b.as_markup(),parse_mode='HTML',disable_web_page_preview=True)
    return await target.answer(text,reply_markup=b.as_markup(),parse_mode='HTML',disable_web_page_preview=True)


@router.callback_query(F.data=='sensi:messages:collapse')
async def messages_collapse(c: CallbackQuery):
    if not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    count=await repo.unread_support_count(); b=InlineKeyboardBuilder(); b.button(text=f'⌄ نمایش پیام‌ها ({count})',callback_data='sensi:messages',style='primary')
    await c.message.edit_text('💬 فهرست پیام‌ها بسته شد.',reply_markup=b.as_markup()); await c.answer()

@router.callback_query(F.data == 'sensi:messages')
async def sensi_messages(c: CallbackQuery, state: FSMContext):
    if not is_sensi(c.from_user.id):
        return await c.answer('دسترسی ندارید.', show_alert=True)
    await state.clear(); await send_support_threads(c.message)
    await c.answer()

@router.callback_query(F.data.startswith('sensi:messages:page:'))
async def sensi_messages_page(c: CallbackQuery,state:FSMContext):
    if not is_sensi(c.from_user.id):
        return await c.answer('دسترسی ندارید.',show_alert=True)
    try: page=int(c.data.rsplit(':',1)[1])
    except (ValueError,IndexError): return await c.answer('درخواست نامعتبره.',show_alert=True)
    await state.clear()
    await send_support_threads(c.message,page,edit=True); await c.answer()

async def open_sensi_customer(message: Message, actor_id: int, user_id: int, state: FSMContext, compose: bool=False):
    user=await repo.get_user_by_id(user_id)
    if not user: return await message.answer('مشتری پیدا نشد.')
    messages=await repo.support_messages_for_user(user_id, 50)
    _,orders=await repo.purchaser_detail(user_id)
    history=await repo.profile_history_for_user(user_id,10)
    title=user.get('name') or user.get('first_name') or 'مشتری'
    latest=orders[0] if orders else None
    recorded=recorded_weights(history)
    current=float(user['weight_kg']) if user.get('weight_kg') is not None else (recorded[-1] if recorded else None)
    weight_result=(f'{current-recorded[0]:+.1f} کیلو از اولین ثبت' if current is not None and recorded else 'دادهٔ کافی ثبت نشده')
    delivered=sum(1 for o in orders if o.get('status')=='delivered')
    preview=[f'👤 {title}  ·  {public_user_id(user_id)}', f'📱 {user.get("phone") or "-"}',
             f'سن {user.get("age") or "-"} · قد {user.get("height_cm") or "-"} · وزن {user.get("weight_kg") or "-"}',
             f'🎯 {user.get("goal") or "-"}', f'🏋️ {user.get("training_history") or "-"}',
             f'📦 {len(orders)} سفارش · 📚 {len(history)} سابقه',
             f'⚖️ نتیجهٔ وزن: {weight_result} · ✅ {delivered} برنامه تحویل‌شده',
             f'🧭 {progress_path(latest["status"],bool(latest.get("renewal_of_order_id"))) if latest else "هنوز سفارشی ندارد"}', '', '💬 پیام‌های اخیر', '━━━━━━━━━━━━━━━━━━']
    if messages:
        for mm in messages[-20:]:
            who='👤 مشتری' if mm.get('direction')=='customer' else '👨‍🏫 سنسی'
            body=mm.get('content_text') or f'[{mm.get("content_type") or "پیام"}]'
            preview.append(f'{who}: {body[:500]}')
    else:
        preview.append('هنوز پیامی ثبت نشده است.')
    for mm in [x for x in messages[-20:] if x.get('file_id')][-10:]:
        caption=f"{('مشتری' if mm.get('direction')=='customer' else 'سنسی')} · {local_dt(mm.get('created_at'))}\n{mm.get('content_text') or ''}"[:1000]
        try:
            if mm.get('content_type')=='photo': await message.bot.send_photo(actor_id,mm['file_id'],caption=caption)
            elif mm.get('content_type')=='document': await message.bot.send_document(actor_id,mm['file_id'],caption=caption)
        except TelegramBadRequest: log.warning('Stored support media is unavailable: message=%s',mm.get('id'))
    await repo.mark_customer_messages_read(user_id)
    await state.clear()
    if compose:
        preview.extend(['', 'پاسخت را کامل بفرست و در پایان «✅ ارسال پیام» را بزن.'])
        await state.update_data(support_mode='sensi_compose', support_target_user_id=user_id, support_target_telegram_id=user['telegram_id'], draft_items=[], draft_header_sent=False)
        await state.set_state(SupportForm.waiting)
        return await answer_long(message,'\n'.join(preview),reply_markup=sensi_compose_kb())
    preview.extend(['', 'برای ارتباط با این شاگرد، «پاسخ به شاگرد» را بزن.'])
    return await answer_long(message,'\n'.join(preview),reply_markup=sensi_customer_kb(user_id))


@router.callback_query(F.data.startswith('sensi:thread:'))
async def sensi_thread(c: CallbackQuery, state: FSMContext):
    if not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    try: user_id=int(c.data.split(':')[2])
    except (ValueError,IndexError): return await c.answer('درخواست نامعتبر است.',show_alert=True)
    await open_sensi_customer(c.message,c.from_user.id,user_id,state,compose=True); await c.answer()


@router.callback_query(F.data.startswith('sensi:reply:'))
async def sensi_reply_to_customer(c: CallbackQuery, state: FSMContext):
    if not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    try: user_id=int(c.data.split(':')[2])
    except (ValueError,IndexError): return await c.answer('درخواست نامعتبر است.',show_alert=True)
    await open_sensi_customer(c.message,c.from_user.id,user_id,state,compose=True)
    await c.answer()


@router.message(F.text.regexp(r'^/start(?:@\w+)? staff_\d+$'))
async def staff_customer_link(m: Message, state: FSMContext):
    if not is_sensi(m.from_user.id): return await m.answer('این لینک فقط برای پنل سنسی فعال است.')
    try: user_id=int(m.text.rsplit('_',1)[1])
    except (ValueError,IndexError): return await m.answer('شناسهٔ مشتری معتبر نیست.')
    await open_sensi_customer(m,m.from_user.id,user_id,state)
    await _delete_link_command(m)


@router.message(F.text.regexp(r'^/start(?:@\w+)? staff_(?:profile|thread|order)_\d+$'))
async def staff_target_link(m: Message, state: FSMContext):
    if not is_sensi(m.from_user.id): return await m.answer('این لینک فقط برای پنل سنسی فعال است.')
    try:
        payload=m.text.rsplit(' ',1)[1]
        _, kind, raw_id=payload.split('_',2)
        target_id=int(raw_id)
    except (ValueError,IndexError):
        return await m.answer('لینک معتبر نیست.')
    await state.clear()
    if kind == 'order':
        await show_sensi_order(m,m.from_user.id,target_id)
    else:
        await open_sensi_customer(m,m.from_user.id,target_id,state,compose=kind=='thread')
    await _delete_link_command(m)


@router.message(F.text.regexp(r'^/start(?:@\w+)? staff_(?:orders|progress|messages)_\d+$'))
async def staff_page_link(m: Message, state: FSMContext):
    if not is_sensi(m.from_user.id):
        return await m.answer('این لینک فقط برای پنل سنسی فعال است.')
    try:
        payload=m.text.rsplit(' ',1)[1]
        _, kind, raw_page=payload.split('_',2)
        page=max(1,int(raw_page))
    except (ValueError,IndexError):
        return await m.answer('صفحهٔ درخواستی معتبر نیست.')
    await state.clear()
    if kind == 'orders':
        await send_sensi_order_page(m,page)
    elif kind == 'progress':
        await send_progress_page(m,page)
    else:
        await send_support_threads(m,page)
    await _delete_link_command(m)

@router.message(SupportForm.waiting, F.from_user.id == settings.sensi_id, F.text == '🗑 پاک کردن پیش‌نویس')
async def clear_sensi_draft(m: Message, state: FSMContext):
    if not is_sensi(m.from_user.id):
        return
    d=await state.get_data()
    if d.get('support_mode') != 'sensi_compose':
        return
    items=list(d.get('draft_items') or []); ids=[int(x['message_id']) for x in items if x.get('message_id')]
    await repo.delete_support_messages(m.from_user.id,ids)
    for message_id in ids:
        try: await m.bot.delete_message(m.chat.id,message_id)
        except TelegramBadRequest: pass
    await state.update_data(draft_items=[],draft_header_sent=False)
    await m.answer('🗑 پیش‌نویس پاک شد.',reply_markup=sensi_compose_kb())


@router.message(SupportForm.waiting, F.from_user.id == settings.sensi_id, F.text == '❌ لغو ارسال پیام')
async def leave_sensi_draft(m: Message, state: FSMContext):
    if not is_sensi(m.from_user.id): return
    d=await state.get_data(); items=list(d.get('draft_items') or []); ids=[int(x['message_id']) for x in items if x.get('message_id')]
    await repo.delete_support_messages(m.from_user.id,ids)
    for message_id in ids:
        try: await m.bot.delete_message(m.chat.id,message_id)
        except TelegramBadRequest: pass
    await state.clear()
    await m.answer('ارسال پیام لغو شد.',reply_markup=await sensi_menu_kb())
    await send_support_threads(m)


@router.message(SupportForm.waiting, F.from_user.id == settings.sensi_id, F.text == '✅ ارسال پیام')
async def send_sensi_draft(m: Message, state: FSMContext):
    if not is_sensi(m.from_user.id): return
    d=await state.get_data()
    if d.get('support_mode') != 'sensi_compose': return
    items=list(d.get('draft_items') or [])
    if not items: return await m.answer('اول متن، عکس یا فایل پاسخ را اضافه کن.')
    target=int(d['support_target_telegram_id'])
    try:
        if not d.get('draft_header_sent'):
            header=await m.bot.send_message(target, '📩 پیام جدید از طرف سنسی')
            await repo.add_support_message(target,header.message_id,direction='sensi',sender_telegram_id=m.from_user.id,content_type='header',content_text='📩 پیام جدید از طرف سنسی')
            await state.update_data(draft_header_sent=True)
        while items:
            item=items[0]
            sent=await m.bot.copy_message(target,m.chat.id,item['message_id'])
            await repo.add_support_message(target,sent.message_id,direction='sensi',sender_telegram_id=m.from_user.id,reply_to_message_id=item['message_id'],content_type=item['content_type'],content_text=item['content_text'],file_id=item.get('file_id'))
            items.pop(0); await state.update_data(draft_items=items)
    except Exception:
        log.exception('Failed to send Sensi draft to customer %s', target)
        return await m.answer('❌ ارسال کامل نشد. دوباره «ارسال پیام» را بزن؛ بخش‌های باقی‌مانده حفظ شدند.')
    await state.clear()
    await repo.add_audit(m.from_user.id, 'reply_to_customer', 'user', int(d['support_target_user_id']))
    await m.answer('✅ پاسخ برای مشتری ارسال شد.', reply_markup=await sensi_menu_kb())


@router.message(SupportForm.waiting, F.from_user.id == settings.sensi_id)
async def sensi_reply_message(m: Message, state: FSMContext):
    if not is_sensi(m.from_user.id): return
    d=await state.get_data()
    if d.get('support_mode') != 'sensi_compose': return
    if len(m.text or m.caption or '') > 2000:
        return await m.answer('لطفاً هر متن یا کپشن را حداکثر ۲۰۰۰ کاراکتر بفرست.')
    size=(m.document.file_size if m.document else (m.photo[-1].file_size if m.photo else 0)) or 0
    if size > settings.max_plan_file_mb * 1024 * 1024:
        return await m.answer(f'حجم هر فایل باید حداکثر {settings.max_plan_file_mb}MB باشد.')
    items=list(d.get('draft_items') or [])
    if len(items) >= MAX_SUPPORT_DRAFT_ITEMS:
        return await m.answer('پاسخت آمادهٔ ارسال است؛ «✅ ارسال پیام» را بزن.')
    items.append({'message_id':m.message_id,'content_type':'text' if m.text else ('photo' if m.photo else ('document' if m.document else 'other')),'content_text':(m.text or m.caption or '')[:2000] or None,'file_id':m.photo[-1].file_id if m.photo else (m.document.file_id if m.document else None)})
    await state.update_data(draft_items=items)

@router.callback_query(F.data == 'sensi:orders')
async def sensi_orders(c: CallbackQuery, state: FSMContext):
    if not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.', show_alert=True)
    await state.clear(); await send_sensi_order_page(c.message,1)
    await c.answer()


@router.callback_query(F.data.startswith('sensi:orders:'))
async def sensi_orders_page(c: CallbackQuery,state:FSMContext):
    if not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.',show_alert=True)
    try: page=int(c.data.split(':')[2])
    except (ValueError,IndexError): return await c.answer('درخواست نامعتبره.',show_alert=True)
    await state.clear()
    await send_sensi_order_page(c.message,page,edit=True); await c.answer()


@router.callback_query(F.data == 'sensi:stats')
async def sensi_stats(c: CallbackQuery, state: FSMContext):
    if not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.', show_alert=True)
    await state.clear()
    now = datetime.now(ZoneInfo(settings.timezone)); month = await repo.monthly_sales(now.year, now.month); total = await repo.total_sales(); items,count=await repo.monthly_sales_items(now.year,now.month)
    await answer_long(c.message,sales_report(now,month,total,items,'📊 فاکتور فروش سنسی'),reply_markup=sales_pager('s',1,count))
    await c.answer()


@router.callback_query(F.data == 'team:stats')
async def team_stats(c: CallbackQuery):
    if not is_team(c.from_user.id): return await c.answer('دسترسی ندارید.', show_alert=True)
    now = datetime.now(ZoneInfo(settings.timezone)); month = await repo.monthly_sales(now.year, now.month); total = await repo.total_sales(); items,count=await repo.monthly_sales_items(now.year,now.month)
    await answer_long(c.message,sales_report(now,month,total,items,'🧾 فاکتور ماهانه تیم ادمین'),reply_markup=sales_pager('t',1,count))
    await c.answer()


async def show_sensi_order(message: Message, actor_id: int, oid: int):
    o=await repo.get_order(oid)
    if not o:
        await message.answer('سفارش پیدا نشد.')
        return False
    d = o['form_snapshot'] if isinstance(o['form_snapshot'], dict) else json.loads(o['form_snapshot'])
    renewal=bool(o.get('renewal_of_order_id'))
    lines = [f"📋 {'تمدید' if renewal else 'سفارش'} #{oid}", f"📦 {o['product_title']}", f"📌 {order_status_fa(o['status'],renewal)}", f"🧭 {progress_path(o['status'],renewal)}", f"🕐 {local_dt(o.get('created_at'))}", '', f"👤 {d.get('name','-')}", f"📱 {d.get('phone','-')}", f"سن: {d.get('age','-')}", f"جنسیت: {d.get('gender','-')}", f"قد: {d.get('height_cm','-')}", f"وزن: {d.get('weight_kg','-')}"]
    for k, label in [('goal','هدف'),('training_history','سابقه تمرین'),('allergy','حساسیت'),('restriction','محدودیت'),('supplements','مکمل‌ها'),('notes','توضیحات')]:
        if d.get(k) is not None: lines.append(f"{label}: {d.get(k) or '-'}")
    photo_ids=media_refs(d.get('body_photo_file_ids') or [])
    if not photo_ids and d.get('body_photo_file_id'): photo_ids=[(d.get('body_photo_file_id'),'photo')]
    for i, (fid,kind) in enumerate(photo_ids[:6],1):
        try:
            if kind=='document': await message.answer_document(fid,caption=f'📸 عکس بدن {i}/{len(photo_ids[:6])}')
            else: await message.answer_photo(fid, caption=f'📸 عکس بدن {i}/{len(photo_ids[:6])}')
        except Exception: log.exception('Failed to send body photo for order %s', oid)
    await message.answer('\n'.join(lines),reply_markup=None if o['status']=='awaiting_receipt' else admin_order_kb(oid,o['status']))
    if o['status']=='awaiting_receipt' and o.get('receipt_file_id'):
        caption='🧾 رسید این سفارش را بررسی کن:'
        if o.get('receipt_type')=='document':
            await message.answer_document(o['receipt_file_id'],caption=caption,reply_markup=receipt_actions_kb(oid))
        else:
            await message.answer_photo(o['receipt_file_id'],caption=caption,reply_markup=receipt_actions_kb(oid))
    await repo.add_audit(actor_id,'view_order','order',oid)
    return True


@router.callback_query(F.data.startswith('admin:view:'))
async def view_order(c: CallbackQuery,state:FSMContext):
    if not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.', show_alert=True)
    await state.clear()
    oid = parse_order_id(c.data)
    if oid is None: return await c.answer('درخواست نامعتبر است.', show_alert=True)
    await show_sensi_order(c.message,c.from_user.id,oid)
    await c.answer()


@router.callback_query(F.data.startswith('admin:progress:'))
async def progress(c: CallbackQuery,state:FSMContext):
    if not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.', show_alert=True)
    await state.clear()
    oid = parse_order_id(c.data)
    if oid is None: return await c.answer('درخواست نامعتبر است.', show_alert=True)
    o = await repo.update_order_status(oid, 'in_progress')
    if not o: return await c.answer('این سفارش در وضعیت قابل تغییر نیست.', show_alert=True)
    full = await repo.get_order(oid)
    await repo.add_audit(c.from_user.id, 'start_order', 'order', oid)
    if full:
        try:
            await c.bot.send_message(full['telegram_id'], f'🔵 سفارش #{oid} وارد مرحله طراحی شد.')
        except Exception:
            log.exception('Failed to notify customer for order %s', oid)
    await c.message.edit_reply_markup(reply_markup=admin_order_kb(oid,'in_progress'))
    await c.answer('وضعیت تغییر کرد.')


@router.callback_query(F.data.startswith('admin:need:'))
async def need(c: CallbackQuery,state:FSMContext):
    if not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.', show_alert=True)
    await state.clear()
    oid = parse_order_id(c.data)
    if oid is None: return await c.answer('درخواست نامعتبر است.', show_alert=True)
    o=await repo.get_order(oid)
    if not o or o['status'] not in {'paid','in_progress','needs_info'}:
        return await c.answer('این سفارش در وضعیت قابل تغییر نیست.',show_alert=True)
    await state.update_data(need_info_order_id=oid)
    await state.set_state(NeedInfoForm.waiting)
    await c.message.answer(f'🟠 تکمیل اطلاعات سفارش #{oid}\n\nدقیق بنویس مشتری چه چیزی را باید بفرستد یا توضیح دهد. بعد از ارسال متن، همان پیام برای مشتری می‌رود.',reply_markup=sensi_workflow_kb('❌ لغو درخواست'))
    await c.answer()


@router.message(NeedInfoForm.waiting, F.from_user.id == settings.sensi_id, F.text != '❌ لغو درخواست')
async def send_need_info_request(m: Message, state: FSMContext):
    if not is_sensi(m.from_user.id): return
    request=(m.text or '').strip()
    if not request: return await m.answer('لطفاً درخواست تکمیل اطلاعات را به‌صورت متن بنویس.')
    if len(request)>2000: return await m.answer('متن درخواست حداکثر ۲۰۰۰ کاراکتر باشد.')
    d=await state.get_data(); oid=d.get('need_info_order_id')
    o=await repo.get_order(oid) if oid else None
    if not o or o['status'] not in {'paid','in_progress','needs_info'}:
        await state.clear(); return await m.answer('این سفارش دیگر در وضعیت قابل تغییر نیست.',reply_markup=await sensi_menu_kb())
    try:
        b=InlineKeyboardBuilder(); b.button(text='💬 پیام به مربی',callback_data='support',style='primary'); b.adjust(1)
        await m.bot.send_message(o['telegram_id'],f'🟠 برای تکمیل سفارش #{oid} لطفاً این مورد را ارسال یا توضیح بده:\n\n{request}',reply_markup=b.as_markup())
    except Exception:
        log.exception('Failed to send need-info request for order %s',oid)
        return await m.answer('❌ ارسال پیام برای مشتری ناموفق بود؛ دوباره تلاش کن.')
    if o['status'] != 'needs_info':
        updated=await repo.update_order_status(oid,'needs_info')
        if not updated:
            await state.clear()
            return await m.answer('پیام ارسال شد، اما وضعیت سفارش تغییر نکرد؛ دوباره سفارش را بررسی کن.',reply_markup=await sensi_menu_kb())
    await repo.add_audit(m.from_user.id,'needs_info','order',oid,{'request_length':len(request)})
    await state.clear(); await m.answer('✅ درخواست دقیق تکمیل اطلاعات برای مشتری ارسال شد.',reply_markup=await sensi_menu_kb())


@router.message(NeedInfoForm.waiting, F.from_user.id == settings.sensi_id, F.text == '❌ لغو درخواست')
async def cancel_need_info_request(m: Message, state: FSMContext):
    await state.clear()
    await show_sensi_home(m)


@router.callback_query(F.data.startswith('admin:send:'))
async def send_plan_prompt(c: CallbackQuery, state: FSMContext):
    if not is_sensi(c.from_user.id): return await c.answer('دسترسی ندارید.', show_alert=True)
    oid = parse_order_id(c.data)
    if oid is None: return await c.answer('درخواست نامعتبر است.', show_alert=True)
    o = await repo.get_order(oid)
    if not o or o['status'] not in ('paid', 'in_progress', 'needs_info'):
        return await c.answer('این سفارش در وضعیت قابل تحویل نیست.', show_alert=True)
    await state.clear(); await state.update_data(admin_order_id=oid); await state.set_state(PlanDelivery.waiting)
    await c.message.answer(f'📤 تحویل فایل دوره #{oid}\n\nفایل PDF/DOCX یا عکس برنامه رو بفرست. بعد از اعتبارسنجی، مستقیم برای مشتری ارسال می‌شه.\nحداکثر حجم: {settings.max_plan_file_mb}MB',reply_markup=sensi_workflow_kb('❌ لغو ارسال فایل'))
    await c.answer()


async def _valid_plan_document(m: Message) -> bool:
    doc = m.document
    name = (doc.file_name or '').lower()
    allowed = {'.pdf': 'application/pdf', '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
    ext = next((x for x in allowed if name.endswith(x)), None)
    if not ext: return False
    if doc.file_size and doc.file_size > settings.max_plan_file_mb * 1024 * 1024: return False
    if doc.mime_type and doc.mime_type not in (allowed[ext], 'application/octet-stream'):
        return False
    # Verify magic bytes without persisting the upload.
    try:
        from io import BytesIO
        buf = BytesIO()
        tg_file = await m.bot.get_file(doc.file_id)
        await m.bot.download(tg_file, destination=buf)
        raw = buf.getvalue()
        if ext == '.pdf':
            return raw.startswith(b'%PDF-')
        if ext == '.docx':
            if not raw.startswith(b'PK\x03\x04'): return False
            try:
                with ZipFile(BytesIO(raw)) as z:
                    names = set(z.namelist())
                    return '[Content_Types].xml' in names and 'word/document.xml' in names
            except (BadZipFile, RuntimeError):
                return False
    except Exception:
        log.exception('Failed to validate uploaded plan file')
        return False
    return False


@router.message(PlanDelivery.waiting, F.from_user.id == settings.sensi_id, F.text == '❌ لغو ارسال فایل')
async def cancel_plan_delivery(m: Message, state: FSMContext):
    await state.clear()
    await show_sensi_home(m)


@router.message(PlanDelivery.waiting, F.photo, F.from_user.id == settings.sensi_id)
async def receive_plan_photo(m: Message, state: FSMContext):
    if not is_sensi(m.from_user.id): return
    d=await state.get_data(); oid=d.get('admin_order_id')
    if not oid: return
    photo=m.photo[-1]
    if photo.file_size and photo.file_size > settings.max_plan_file_mb * 1024 * 1024:
        return await m.answer(f'❌ حجم عکس باید کمتر از {settings.max_plan_file_mb}MB باشه.')
    o=await repo.get_order(oid)
    if not o: return await m.answer('سفارش پیدا نشد.')
    try:
        await m.bot.send_photo(o['telegram_id'],photo.file_id,caption=f'🎉 برنامهٔ اختصاصی تو آماده شد!\n\n📦 شماره سفارش: #{oid}\nاز بخش «سفارش‌های من» هم همیشه به برنامه دسترسی داری.')
    except Exception:
        log.exception('Failed to deliver plan photo %s',oid); return await m.answer('❌ ارسال عکس ناموفق بود؛ دوباره تلاش کن.')
    saved=await repo.attach_plan(oid,photo.file_id,None,'photo')
    if not saved: return await m.answer('⚠️ عکس ارسال شد اما ثبت وضعیت ناموفق بود.')
    await repo.add_audit(m.from_user.id,'deliver_plan_photo','order',oid)
    await state.clear()
    await m.answer(f'✅ عکس برنامه سفارش #{oid} تحویل داده شد.',reply_markup=await sensi_menu_kb())

@router.message(PlanDelivery.waiting, F.document, F.from_user.id == settings.sensi_id)
async def receive_plan(m: Message, state: FSMContext):
    if not is_sensi(m.from_user.id): return
    d = await state.get_data(); oid = d.get('admin_order_id')
    if not oid: return
    o = await repo.get_order(oid)
    if not o: return await m.answer('سفارش پیدا نشد.')
    if not await _valid_plan_document(m):
        return await m.answer('❌ فایل معتبر نیست. فقط PDF/DOCX واقعی و تا حجم مجاز پذیرفته می‌شود.')
    # Send first. If Telegram delivery fails, DB remains retryable.
    try:
        await m.bot.send_document(o['telegram_id'], m.document.file_id, caption=f'🎉 برنامهٔ اختصاصی تو آماده شد!\n\n📦 شماره سفارش: #{oid}\nاز بخش «سفارش‌های من» هم همیشه به برنامه دسترسی داری.')
    except Exception:
        log.exception('Failed to deliver plan for order %s', oid)
        return await m.answer('❌ ارسال به کاربر ناموفق بود؛ سفارش تغییر نکرده و می‌توانی دوباره تلاش کنی.')
    saved = await repo.attach_plan(oid, m.document.file_id, m.document.file_name)
    if not saved:
        return await m.answer('⚠️ فایل برای کاربر ارسال شد اما ثبت وضعیت سفارش ناموفق بود؛ لطفاً لاگ سرور بررسی شود.')
    await repo.add_audit(m.from_user.id, 'deliver_plan', 'order', oid, {'file_name': m.document.file_name})
    await state.clear()
    await m.answer(f'✅ برنامه سفارش #{oid} تحویل داده شد.',reply_markup=await sensi_menu_kb())


@router.message(PlanDelivery.waiting, F.from_user.id == settings.sensi_id)
async def receive_plan_invalid(m: Message):
    await m.answer('❌ برای تحویل برنامه فقط PDF، DOCX یا عکس بفرست.')
