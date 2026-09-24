from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.utils.text import order_status_fa, subscription_time_fa

BACK = '⬅️ بازگشت'
MAIN = '🏠 منوی اصلی'


def rtl_pager(previous_data: str | None = None, next_data: str | None = None):
    buttons=[]
    if next_data:
        buttons.append(InlineKeyboardButton(text='بعدی ◀️',callback_data=next_data))
    if previous_data:
        buttons.append(InlineKeyboardButton(text='▶️ قبلی',callback_data=previous_data))
    return buttons


def _persistent(rows):
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder='انتخاب کن…',
    )


def main_reply_kb():
    return customer_main_reply_kb(True)


def customer_main_reply_kb(can_message_coach: bool):
    coach='💬 پیام به مربی' if can_message_coach else '🔒 پیام به مربی'
    return _persistent([
        [KeyboardButton(text='🛒 خرید دوره', style='success'), KeyboardButton(text='👤 اطلاعات من')],
        [KeyboardButton(text='🏋️ دوره‌های فعال', style='primary'), KeyboardButton(text='🧾 تاریخچه سفارشات')],
        [KeyboardButton(text=coach), KeyboardButton(text='🎧 پشتیبانی')],
    ])


def home_only_reply_kb(extra=None):
    rows=[]
    if extra:
        for row in extra:
            rows.append(row)
    rows.append([KeyboardButton(text=MAIN)])
    return _persistent(rows)


def customer_nav_rows(include_home=True):
    return [[KeyboardButton(text=MAIN)]] if include_home else []


def back_reply_kb(*extra: str, include_main: bool = True):
    rows = [[KeyboardButton(text=x)] for x in extra]
    if include_main:
        rows.append([KeyboardButton(text=MAIN)])
    return _persistent(rows)


def phone_kb():
    return _persistent([
        [KeyboardButton(text='📱 ارسال شماره تلفن', request_contact=True, style='primary')],
        [KeyboardButton(text=MAIN)],
    ])


def choice_reply_kb(options, include_home=True):
    rows = [[KeyboardButton(text=x, style='primary') for x in options[i:i + 2]] for i in range(0, len(options), 2)]
    if include_home:
        rows.append([KeyboardButton(text=MAIN)])
    return _persistent(rows)


def skip_reply_kb(skip_text='⏭️ ندارم', *more):
    rows = [[KeyboardButton(text=skip_text, style='success' if skip_text.startswith('✅') else None)]]
    for x in more:
        rows.append([KeyboardButton(text=x, style='success' if x.startswith('✅') else None)])
    rows.append([KeyboardButton(text=MAIN)])
    return _persistent(rows)


def previous_value_kb(label: str, value):
    return _persistent([
        [KeyboardButton(text=f'✅ {label} قبلی: {value}', style='primary')],
        [KeyboardButton(text=MAIN)],
    ])


def body_photo_kb(photo_count: int=0, collecting: bool=True, can_restore: bool=False, back_text: str | None=None):
    rows=[]
    if collecting:
        rows.append([KeyboardButton(text='👁 دیدن عکس‌های فعلی',style='primary')])
        rows.append([KeyboardButton(text='🗑 حذف آخرین عکس',style='danger')])
        rows.append([KeyboardButton(text='✅ اتمام و ادامه',style='success')])
    elif photo_count:
        rows.extend([
            [KeyboardButton(text='👁 دیدن عکس‌های فعلی',style='primary')],
            [KeyboardButton(text='🗑 حذف آخرین عکس',style='danger')],
            [KeyboardButton(text='✅ ادامه با همین عکس‌ها',style='success')],
            [KeyboardButton(text='➕ افزودن عکس جدید')],
        ])
    else:
        rows.append([KeyboardButton(text='✅ اتمام و ادامه',style='success')])
    if can_restore:
        rows.append([KeyboardButton(text=back_text or '↩️ بازگشت به عکس‌های قبلی',style='primary')])
    return _persistent(rows)


def edit_value_kb(*options: str, request_contact: bool=False):
    rows=[]
    if request_contact:
        rows.append([KeyboardButton(text='📱 ارسال شماره تلفن', request_contact=True, style='primary')])
    elif options:
        rows.append([KeyboardButton(text=x, style='primary') for x in options])
    rows.append([KeyboardButton(text='❌ لغو ویرایش', style='danger')])
    return _persistent(rows)


def edit_photo_kb(photo_count: int=0, collecting: bool=True, can_restore: bool=False, back_text: str | None=None):
    rows=[]
    if collecting:
        rows.extend([
            [KeyboardButton(text='👁 دیدن عکس‌های فعلی',style='primary')],
            [KeyboardButton(text='🗑 حذف آخرین عکس',style='danger')],
            [KeyboardButton(text='✅ ذخیره عکس‌ها', style='success')],
        ])
    elif photo_count:
        rows.extend([
            [KeyboardButton(text='👁 دیدن عکس‌های فعلی',style='primary')],
            [KeyboardButton(text='🗑 حذف آخرین عکس',style='danger')],
            [KeyboardButton(text='✅ نگه‌داشتن همین عکس‌ها',style='success')],
            [KeyboardButton(text='➕ افزودن عکس جدید')],
        ])
    if can_restore:
        rows.append([KeyboardButton(text=back_text or '↩️ بازگشت به عکس‌های قبلی',style='primary')])
    rows.append([KeyboardButton(text='❌ لغو ویرایش', style='danger')])
    return _persistent(rows)


def payment_methods_kb(mode: str):
    rows=[]
    if mode in {'card_to_card', 'both'}:
        rows.append([InlineKeyboardButton(text='💳 کارت‌به‌کارت', callback_data='pay:card', style='primary')])
    if mode in {'zarinpal', 'both'}:
        rows.append([InlineKeyboardButton(text='🔒 پرداخت امن زرین‌پال', callback_data='pay:zarinpal', style='primary')])
    if mode == 'mock':
        rows.append([InlineKeyboardButton(text='🧪 پرداخت آزمایشی', callback_data='pay:mock', style='success')])
    rows.append([InlineKeyboardButton(text=BACK, callback_data='payment_back')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def receipt_actions_kb(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ تأیید پرداخت', callback_data=f'admin:approvepay:{order_id}', style='success')],
        [InlineKeyboardButton(text='❌ رد رسید', callback_data=f'admin:rejectpay:{order_id}', style='danger')],
    ])


def sensi_reply_kb(unread_count: int = 0, actionable_count: int = 0, active_count: int = 0):
    return _persistent([
        [KeyboardButton(text=f'📋 کارها ({max(0,int(actionable_count))})', style='primary'), KeyboardButton(text=f'💬 پیام‌ها ({max(0,int(unread_count))})',style='primary' if unread_count else None)],
        [KeyboardButton(text=f'👥 شاگردها ({max(0,int(active_count))})'), KeyboardButton(text='📈 درآمد')],
    ])


def admin_team_reply_kb():
    return _persistent([
        [KeyboardButton(text='📊 آمار فروش', style='primary')],
        [KeyboardButton(text='👥 اطلاعات خریداران')],
        [KeyboardButton(text=MAIN)],
    ])


def products_kb(products, page=1, pages=1):
    b = InlineKeyboardBuilder()
    for p in products:
        if not p.get('purchased_before'):
            text=f"✨ خرید {p['title']} — {int(p['price_irr']):,} تومان"; data=f"buy:{p['id']}"; style='success'
        elif p.get('renewal_eligible'):
            text=f"🔄 تمدید {p['title']} — {subscription_time_fa(p.get('days_remaining'))}"; data=f"renew:{p['latest_order_id']}"; style='success'
        elif p.get('renewal_in_progress'):
            text=f"{p['title']} — {order_status_fa(p.get('latest_status') or 'paid',True)}"; data=f"subscription:status:{p['id']}"; style=None
        elif p.get('latest_status') == 'delivered':
            text=f"{p['title']} — {subscription_time_fa(p.get('days_remaining'),p.get('purchased_duration_days'))}"; data=f"subscription:status:{p['id']}"; style=None
        else:
            text=f"{p['title']} — {order_status_fa(p.get('latest_status') or 'paid')}"; data=f"subscription:status:{p['id']}"; style=None
        b.button(text=text, callback_data=data, style=style)
    b.adjust(1)
    nav=rtl_pager(f'products:page:{page-1}' if page>1 else None,f'products:page:{page+1}' if page<pages else None)
    if nav: b.row(*nav)
    b.row(InlineKeyboardButton(text=BACK,callback_data='home'))
    return b.as_markup()


def back_kb(callback_data='home'):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=BACK, callback_data=callback_data)]])


def support_contact_kb(url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎧 گفت‌وگو با پشتیبانی فنی',url=url,style='primary')],
    ])


def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ تأیید و رفتن به پرداخت', callback_data='confirm', style='success')],
        [InlineKeyboardButton(text='✏️ شروع دوباره', callback_data='restart_form', style='danger')],
    ])


def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📸 دیدن عکس‌ها', callback_data='profile_photos', style='primary')],
        [InlineKeyboardButton(text='📚 سوابق اطلاعات', callback_data='profile_history')],
        [InlineKeyboardButton(text='✏️ ویرایش اطلاعات', callback_data='edit_profile')],
    ])


def profile_history_kb():
    return profile_history_page_kb(1,1)


def profile_history_page_kb(page: int=1, total_pages: int=1, include_back: bool=True):
    rows=[]
    nav=rtl_pager(f'profile_history:{page-1}' if page>1 else None,f'profile_history:{page+1}' if page<total_pages else None)
    if nav: rows.append(nav)
    if include_back:
        rows.append([InlineKeyboardButton(text=BACK, callback_data='profile')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def customer_compose_kb():
    return _persistent([
        [KeyboardButton(text='✅ ارسال پیام', style='success')],
        [KeyboardButton(text='🗑 پاک کردن پیش‌نویس')],
        [KeyboardButton(text='❌ لغو ارسال پیام', style='danger')],
    ])


def sensi_compose_kb():
    return _persistent([
        [KeyboardButton(text='✅ ارسال پیام', style='success')],
        [KeyboardButton(text='🗑 پاک کردن پیش‌نویس', style='danger')],
        [KeyboardButton(text='❌ لغو ارسال پیام', style='danger')],
    ])


def pending_order_kb(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💳 ادامه پرداخت', callback_data=f'order:pay:{order_id}', style='primary')],
        [InlineKeyboardButton(text='❌ لغو سفارش', callback_data=f'order:cancel:{order_id}', style='danger')],
        [InlineKeyboardButton(text='⬅️ تاریخچه سفارشات',callback_data='orders')],
    ])


def rejected_receipt_kb(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔁 ارسال رسید جدید', callback_data=f'order:receipt:{order_id}', style='primary')],
        [InlineKeyboardButton(text=BACK, callback_data='orders')],
    ])


def orders_list_kb(rows, page: int, total_pages: int):
    b=InlineKeyboardBuilder()
    nav=rtl_pager(f'orders:page:{page-1}' if page>1 else None,f'orders:page:{page+1}' if page<total_pages else None)
    if nav:
        b.row(*nav)
    return b.as_markup() if nav else None


def purchase_entry_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✨ خرید برنامه جدید', callback_data='products', style='primary')],
        [InlineKeyboardButton(text='🔄 تمدید برنامه قبلی', callback_data='renew:list', style='primary')],
        [InlineKeyboardButton(text=BACK, callback_data='home')],
    ])


def renewal_list_kb(rows):
    b=InlineKeyboardBuilder()
    for o in rows:
        days=max(0,int(o.get('days_remaining') or 0))
        b.button(text=f"🔄 #{o['id']} · {o['product_title']} · {days} روز", callback_data=f"renew:{o['id']}", style='primary')
    b.button(text=BACK, callback_data='buy:entry')
    b.adjust(1)
    return b.as_markup()


def renewal_order_kb(order_id: int, has_plan: bool=False, renewal_eligible: bool=False):
    b=InlineKeyboardBuilder()
    if has_plan: b.button(text='📥 دریافت برنامه',callback_data=f'order:plan:{order_id}',style='primary')
    if renewal_eligible: b.button(text='🔄 تمدید همین برنامه',callback_data=f'renew:{order_id}',style='primary')
    b.button(text='💬 پیام به مربی',callback_data='support')
    b.button(text='⬅️ تاریخچه سفارشات',callback_data='orders')
    b.adjust(1)
    return b.as_markup()


def plan_download_kb(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='📥 دریافت فایل دوره',callback_data=f'order:plan:{order_id}',style='primary')
    ]])


def sensi_orders_list_kb(rows, page: int, total_pages: int):
    b=InlineKeyboardBuilder()
    nav=rtl_pager(f'sensi:orders:{page-1}' if page>1 else None,f'sensi:orders:{page+1}' if page<total_pages else None)
    if nav:
        b.row(*nav)
    b.adjust(1)
    return b.as_markup() if nav else None


def sensi_customer_kb(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='💬 پاسخ به شاگرد',callback_data=f'sensi:reply:{user_id}',style='primary')
    ]])


def cancel_confirm_kb(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='بله، سفارش را لغو کن', callback_data=f'order:cancel_confirm:{order_id}', style='danger')],
        [InlineKeyboardButton(text='↩️ انصراف', callback_data=f'order:cancel_abort:{order_id}')],
    ])


def admin_order_kb(order_id: int, status: str = 'paid'):
    b = InlineKeyboardBuilder()
    b.button(text='👤 مشاهده پرونده', callback_data=f'admin:view:{order_id}')
    if status in {'paid','needs_info'}:
        b.button(text='🔵 شروع طراحی' if status == 'paid' else '🔵 ادامه طراحی', callback_data=f'admin:progress:{order_id}', style='primary')
    if status in {'paid','needs_info','in_progress'}:
        b.button(text='🟠 درخواست تکمیل اطلاعات', callback_data=f'admin:need:{order_id}')
        b.button(text='📤 تحویل فایل دوره', callback_data=f'admin:send:{order_id}', style='success')
    b.adjust(1)
    return b.as_markup()


def sensi_workflow_kb(cancel_text: str):
    return _persistent([
        [KeyboardButton(text=cancel_text, style='danger')],
        [KeyboardButton(text='🏠 داشبورد سنسی')],
    ])


def sensi_kb():
    b = InlineKeyboardBuilder()
    b.button(text='🆕 سفارش‌های نیازمند اقدام', callback_data='sensi:orders')
    b.button(text='📊 آمار فروش', callback_data='sensi:stats')
    b.button(text='💬 پیام‌ها', callback_data='sensi:messages')
    b.adjust(1)
    return b.as_markup()


def admin_team_kb():
    b = InlineKeyboardBuilder()
    b.button(text='📊 آمار فروش', callback_data='team:stats')
    b.adjust(1)
    return b.as_markup()


def team_purchasers_kb(rows, page: int, total_pages: int):
    b = InlineKeyboardBuilder()
    for r in rows:
        name = r.get('name') or r.get('first_name') or 'بدون نام'
        gender = r.get('gender') or '-'
        age = r.get('age') or '-'
        b.button(text=f"🆔 U{int(r['user_id']):06d} · {name} · {gender} · {age}", callback_data=f"team:buyer:{r['user_id']}:{page}")
    nav=rtl_pager(f'team:buyers:{page-1}' if page>1 else None,f'team:buyers:{page+1}' if page<total_pages else None)
    if nav:
        b.row(*nav)
    b.button(text='🏠 منوی اصلی', callback_data='team:home')
    b.adjust(1)
    return b.as_markup()


def team_buyer_detail_kb(page: int):
    b=InlineKeyboardBuilder()
    b.button(text='⬅️ بازگشت به لیست', callback_data=f'team:buyers:{page}')
    b.adjust(1)
    return b.as_markup()
