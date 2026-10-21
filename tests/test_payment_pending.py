from app.config import Settings
from app.handlers.user import _checkout_method

BASE = dict(bot_token='1:x', database_url='postgresql://x', redis_url='redis://x', sensi_id=1, _env_file=None)
PRODUCTION = dict(app_env='production', webhook_secret='s' * 32, public_base_url='https://sensibot.ir')


def test_retired_card_to_card_means_waiting_for_the_gateway():
    s = Settings(payment_mode='card_to_card', **BASE)
    assert s.payment_mode == 'pending' and s.payment_pending


def test_pending_mode_runs_in_production_without_a_merchant():
    s = Settings(payment_mode='pending', **BASE, **PRODUCTION)
    s.validate_runtime()
    assert s.payment_pending


def test_pending_mode_saves_gateway_orders_for_later_payment():
    assert _checkout_method(Settings(payment_mode='pending', **BASE)) == 'zarinpal'
