"""The bot's payment button opens our own /pay/ page, which hands the browser to ZarinPal."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _request(authority):
    return SimpleNamespace(match_info={'authority': authority})


def _order(**changes):
    order = {'id': 42, 'amount': 1500, 'status': 'awaiting_payment', 'payment_status': 'pending',
             'paid_at': None, 'payment_authority': 'A000000000000000000000000000000abcde'}
    order.update(changes)
    return order


def test_payment_link_points_at_our_domain(monkeypatch):
    from app.services import payment
    settings = payment.get_settings()
    monkeypatch.setattr(settings, 'public_base_url', 'https://sensibot.ir/')
    assert payment.relay_url('A123') == 'https://sensibot.ir/pay/A123'
    monkeypatch.setattr(settings, 'public_base_url', '')
    assert payment.relay_url('A123') == ''  # Local runs keep the direct gateway link.


def test_handoff_page_sends_our_origin_to_zarinpal(monkeypatch):
    from app import main
    order = _order()
    monkeypatch.setattr(main.repo, 'get_order_by_authority', AsyncMock(return_value=order))
    response = asyncio.run(main.payment_redirect(_request(order['payment_authority'])))
    assert response.status == 200
    assert response.headers['Referrer-Policy'] == 'origin'
    assert response.headers['Cache-Control'] == 'no-store'
    assert main.payment.start_url(order['payment_authority']) in response.text
    assert '1,500 تومان' in response.text
    assert 'در حال انتقال به درگاه پرداخت' in response.text
    assert 'setTimeout' in response.text  # The transfer message stays visible before the redirect.


def test_success_page_shows_receipt_and_escapes_values(monkeypatch):
    from app import main
    order = _order(product_title='<b>دوره</b>', telegram_id=9,
                   product_snapshot={'form_fields': ['name', 'phone', 'age']})
    monkeypatch.setattr(main.repo, 'get_order_by_authority', AsyncMock(return_value=order))
    monkeypatch.setattr(main.payment, 'verify_zarinpal', AsyncMock(return_value=SimpleNamespace(success=True, reference_id='REF-77')))
    monkeypatch.setattr(main.repo, 'mark_zarinpal_paid', AsyncMock(return_value={'id': 42}))
    monkeypatch.setattr(main.repo, 'add_audit', AsyncMock())
    response = asyncio.run(main._verify_payment_callback(order['payment_authority'], 'OK'))
    assert response.status == 200
    assert 'REF-77' in response.text and 'پرداخت با موفقیت انجام شد' in response.text
    assert '&lt;b&gt;دوره&lt;/b&gt;' in response.text and '<b>دوره</b>' not in response.text
    assert 'تکمیل فرم ثبت‌نام' in response.text and 'start=form_42' in response.text
    assert 'هٔ' not in response.text


def test_failure_page_offers_a_retry(monkeypatch):
    from app import main
    order = _order(telegram_id=9)
    monkeypatch.setattr(main.repo, 'get_order_by_authority', AsyncMock(return_value=order))
    monkeypatch.setattr(main, '_notify_payment_failed', lambda *args: None)
    response = asyncio.run(main._verify_payment_callback(order['payment_authority'], 'NOK'))
    assert 'پرداخت ناموفق بود' in response.text and 'start=pay_42' in response.text and '۷۲ ساعت' in response.text


def test_pages_use_the_bundled_font():
    from app import payment_pages as pages
    assert pages.FONT_PATH.is_file()
    assert pages.FONT_URL.startswith('/pay/')  # Served through the same edge route as the page.
    response = asyncio.run(pages.font(None))
    assert response.headers['Content-Type'] == 'font/woff2'


@pytest.mark.parametrize('changes,status', [
    ({'payment_authority': 'Bnewer0000000000000000000000000000000'}, 410),  # A newer attempt replaced this link.
    ({'status': 'cancelled'}, 410),
    ({'paid_at': '2026-10-21', 'payment_status': 'paid'}, 200),
])
def test_handoff_never_reopens_a_stale_or_paid_order(monkeypatch, changes, status):
    from app import main
    order = _order(**changes)
    monkeypatch.setattr(main.repo, 'get_order_by_authority', AsyncMock(return_value=order))
    response = asyncio.run(main.payment_redirect(_request('A000000000000000000000000000000abcde')))
    assert response.status == status
    assert 'StartPay' not in response.text


def test_handoff_rejects_malformed_or_unknown_links(monkeypatch):
    from app import main
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(main.repo, 'get_order_by_authority', lookup)
    assert asyncio.run(main.payment_redirect(_request('<script>'))).status == 404
    lookup.assert_not_awaited()
    assert asyncio.run(main.payment_redirect(_request('A000000000000000000000000000000abcde'))).status == 404
