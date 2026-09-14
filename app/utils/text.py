from zoneinfo import ZoneInfo

import jdatetime


_FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def jalali_dt(value, timezone: str = 'Asia/Tehran', fmt: str = '%Y/%m/%d - %H:%M') -> str:
    if not value:
        return '-'
    try:
        local=value.astimezone(ZoneInfo(timezone))
        return jdatetime.datetime.fromgregorian(datetime=local).strftime(fmt).translate(_FA_DIGITS)
    except (AttributeError, TypeError, ValueError):
        return str(value)


def money(v): return f"{int(v):,} تومان"

def status_fa(s):
    return {'awaiting_payment':'💳 در انتظار پرداخت','awaiting_receipt':'🧾 در انتظار بررسی رسید','payment_rejected':'❌ رسید پرداخت رد شده','paid':'🟡 پرداخت شده / در انتظار بررسی','needs_info':'🟠 نیاز به اطلاعات بیشتر','in_progress':'🔵 در حال طراحی','ready':'🟢 برنامه آماده','delivered':'📥 تحویل داده شده','cancelled':'🔴 لغو شده'}.get(s,s)


def order_status_fa(status: str, renewal: bool=False) -> str:
    if not renewal: return status_fa(status)
    return {'paid':'🟠 در انتظار تأیید تمدید','needs_info':'🟠 تمدید؛ نیازمند اطلاعات',
            'in_progress':'🔵 طراحی تمرین جدید','ready':'🟢 آمادهٔ انتشار تمرین جدید',
            'delivered':'✅ تمرین جدید منتشر شد'}.get(status,status_fa(status))

def payment_method_fa(value):
    return {'card_to_card':'کارت‌به‌کارت','zarinpal':'زرین‌پال','mock':'آزمایشی'}.get(value,value or '-')


def public_user_id(user_id: int) -> str:
    return f'U{int(user_id):06d}'


def order_code(order_id: int) -> str:
    return f'ORD-{int(order_id):06d}'


def progress_path(status: str, renewal: bool=False) -> str:
    order = ['awaiting_payment','awaiting_receipt','payment_rejected','paid','needs_info','in_progress','ready','delivered']
    current = order.index(status) if status in order else -1
    steps = [('پرداخت', 0), ('تأیید تمدید' if renewal else 'تأیید', 3), ('طراحی جدید' if renewal else 'طراحی', 5), ('انتشار تمرین جدید' if renewal else 'تحویل', 7)]
    return '  ←  '.join(('●' if current >= index else '○') + ' ' + label for label, index in steps)


def subscription_time_fa(days_remaining) -> str:
    if days_remaining is None: return 'شروع اعتبار پس از تحویل'
    days=int(days_remaining)
    if days<0: return f'{abs(days)} روز از پایان گذشته'
    if days==0: return 'امروز به پایان می‌رسد'
    return f'{days} روز تا پایان'


def split_message(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, current = [], ''
    for line in text.splitlines(keepends=True):
        if current and len(current) + len(line) > limit:
            parts.append(current.rstrip())
            current = ''
        while len(line) > limit:
            room = limit - len(current)
            current += line[:room]
            parts.append(current.rstrip())
            current, line = '', line[room:]
        current += line
    if current:
        parts.append(current.rstrip())
    return parts
