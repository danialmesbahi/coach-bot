"""The bot's payment button opens our own /pay/ page, which hands the browser to ZarinPal."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _request(authority, ip='', **query):
    return SimpleNamespace(match_info={'authority': authority}, query=query, headers={'X-Coach-Client-IP': ip} if ip else {})


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


def test_payment_pages_share_one_branded_design_and_font():
    from app import main
    from app.services import pay_pages
    assert pay_pages.FONT.is_file() and pay_pages.FONT_URL.startswith('/pay/')  # Routed to the bot by nginx.
    response = asyncio.run(main.payment_font(None))
    assert response.headers['Cache-Control'].endswith('immutable')
    page = main._result_page(True, 'پرداخت با موفقیت انجام شد', 'ok', 'form_42', rows=(('کد پیگیری', '<b>1</b>'),)).text
    assert pay_pages.FONT_URL in page and 'سنسی' in page and 'start=form_42' in page
    assert '&lt;b&gt;1&lt;/b&gt;' in page and 'هٔ' not in page


def test_iranian_address_lookup_is_fail_open():
    from app.services.geo import is_iranian
    assert is_iranian('5.213.60.248') is True and is_iranian('2.176.1.1') is True
    assert is_iranian('8.8.8.8') is False
    for unknown in ('10.0.0.1', '172.18.0.1', '2001:4860::1', 'not-an-ip', '', None):
        assert is_iranian(unknown) is None  # Never warn about an address we cannot place.


@pytest.mark.parametrize('ip,query,vpn', [('8.8.8.8', {}, True), ('8.8.8.8', {'vpn': 'off'}, False),
                                          ('5.213.60.248', {}, False), ('172.18.0.1', {}, False), ('', {}, False)])
def test_foreign_visitors_get_vpn_steps_before_the_gateway(monkeypatch, ip, query, vpn):
    from app import main
    order = _order()
    monkeypatch.setattr(main.repo, 'get_order_by_authority', AsyncMock(return_value=order))
    response = asyncio.run(main.payment_redirect(_request(order['payment_authority'], ip, **query)))
    assert response.status == 200
    assert ('فیلترشکن روشن است' in response.text) is vpn
    assert ('location.assign' in response.text) is not vpn  # The VPN page never forwards to the gateway itself.
    if vpn:
        assert f"/pay/{order['payment_authority']}?vpn=off" in response.text


def test_handoff_shows_vpn_help_when_the_customer_comes_back():
    from app.services import pay_pages
    page = pay_pages.handoff('https://www.zarinpal.com/pg/StartPay/A1', (('مبلغ', '1,500 تومان'),), 'https://t.me/bot?start=pay_1')
    assert 'class="card first"' in page and 'class="card back"' in page
    assert 'pageshow' in page and 'sessionStorage' in page and 'location.assign' in page
    assert 'خاموش کردم، تلاش دوباره' in page and 'start=pay_1' in page
