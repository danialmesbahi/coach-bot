import asyncio

from app.handlers import user


class _Message:
    def __init__(self):
        self.sent=[]

    async def answer(self, text, reply_markup=None, **kwargs):
        self.sent.append((text,reply_markup))


def _order(status, **extra):
    return {'id':42,'status':status,'product_title':'دوره تست','amount':1500,'created_at':None,'paid_at':None,
            'days_remaining':None,'duration_days':30,'plan_file_id':'file-1','product_snapshot':{},**extra}


def _show(monkeypatch, order, **flags):
    async def get_user_order(oid, tg_id): return order
    monkeypatch.setattr(user.repo,'get_user_order',get_user_order)
    m=_Message()
    asyncio.run(user.show_order_detail_message(m,7,42,**flags))
    return m.sent[-1]


def _buttons(markup):
    return [button.text for row in (markup.inline_keyboard if markup else []) for button in row]


def test_cancelled_order_from_history_link_shows_only_its_status(monkeypatch):
    text,markup=_show(monkeypatch,_order('cancelled'),from_link=True)
    assert 'لغو شده' in text and 'ORD-000042' in text and 'دوره تست' in text
    assert 'مسیر انجام دوره' not in text and 'زمان دوره' not in text
    assert markup is None


def test_cancelled_order_from_a_button_only_offers_the_way_back(monkeypatch):
    text,markup=_show(monkeypatch,_order('cancelled',paid_at='2026-10-21'))
    assert 'مسیر انجام دوره' not in text and 'تکمیل فرم' not in text
    assert _buttons(markup) == ['⬅️ تاریخچه سفارشات']


def test_unpaid_order_from_history_link_offers_payment_not_a_file(monkeypatch):
    text,markup=_show(monkeypatch,_order('awaiting_payment'),from_link=True)
    assert '📥 دریافت فایل دوره' not in _buttons(markup) and '💳 ادامه پرداخت' in _buttons(markup)


def test_delivered_order_from_history_link_keeps_the_download(monkeypatch):
    text,markup=_show(monkeypatch,_order('delivered',paid_at='2026-10-21',form_completed_at='2026-10-21'),from_link=True)
    assert 'مسیر انجام دوره' in text and _buttons(markup) == ['📥 دریافت فایل دوره']


def test_cancelled_order_never_sends_the_plan_file(monkeypatch):
    async def get_user_order(oid, tg_id): return _order('cancelled',paid_at='2026-10-21')
    monkeypatch.setattr(user.repo,'get_user_order',get_user_order)
    m=_Message()
    asyncio.run(user.send_plan_to_customer(m,7,42))
    assert m.sent == [('این سفارش لغو شده و فایلی برای آن وجود ندارد.',None)]
