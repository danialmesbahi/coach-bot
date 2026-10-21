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
