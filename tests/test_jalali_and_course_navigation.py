from datetime import datetime, timezone
from decimal import Decimal

from app.keyboards import orders_list_kb, plan_download_kb, products_kb
from app.utils.text import jalali_dt


def test_customer_course_navigation_status_and_jalali_dates():
    pager=orders_list_kb([{'id': 1}],2,3)
    labels=[button.text for row in pager.inline_keyboard for button in row]
    assert labels == ['بعدی ◀️', '▶️ قبلی']

    download=plan_download_kb(42).inline_keyboard[0][0]
    assert download.text == '📥 دریافت فایل دوره'
    assert download.callback_data == 'order:plan:42'

    products=products_kb([
        {'id': 1, 'title': 'تمرینی', 'price_irr': Decimal('1'), 'purchased_before': True,
         'latest_status': 'delivered', 'days_remaining': 21, 'renewal_eligible': False,
         'renewal_in_progress': False},
        {'id': 2, 'title': 'تغذیه', 'price_irr': Decimal('1'), 'purchased_before': True,
         'latest_status': 'in_progress', 'days_remaining': None, 'renewal_eligible': False,
         'renewal_in_progress': False},
    ])
    labels=[button.text for row in products.inline_keyboard for button in row]
    assert any('تمرینی — 21 روز تا پایان' in label for label in labels)
    assert any('تغذیه — 🔵 در حال طراحی' in label for label in labels)

    value=datetime(2025,3,20,12,30,tzinfo=timezone.utc)
    assert jalali_dt(value,'UTC') == '۱۴۰۳/۱۲/۳۰ - ۱۲:۳۰'
