from pathlib import Path
import pytest

from app.config import Settings
from app.keyboards import confirm_kb, payment_methods_kb
from app.handlers.user import PROFILE_KEYMAP, PURCHASE_STEPS, purchase_route
from app.db.repositories import _json_object
from app.services.payment import toman_to_irr
from app.utils.text import split_message


ROOT = Path(__file__).resolve().parents[1]


def callbacks(markup):
    return {button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data}


def test_payment_keyboard_only_shows_enabled_methods():
    assert callbacks(payment_methods_kb('mock')) == {'pay:mock', 'payment_back'}
    assert callbacks(payment_methods_kb('card_to_card')) == {'payment_back'}
    assert callbacks(payment_methods_kb('zarinpal')) == {'pay:zarinpal', 'payment_back'}
    assert callbacks(payment_methods_kb('both')) == {'pay:zarinpal', 'payment_back'}


def test_primary_and_destructive_actions_have_native_telegram_styles():
    payment={button.callback_data: getattr(button,'style',None) for row in payment_methods_kb('mock').inline_keyboard for button in row}
    confirm={button.callback_data: getattr(button,'style',None) for row in confirm_kb().inline_keyboard for button in row}
    assert payment['pay:mock'] == 'success'
    assert confirm['confirm'] == 'success'
    assert confirm['restart_form'] == 'danger'


def test_returning_customer_gets_short_contiguous_purchase_route():
    profile={'name':'کاربر','phone':'09120000000','gender':'مرد','goal':'عضله‌سازی','training_history':'یک سال','notes':'-'}
    assert purchase_route('training',profile) == ['age','height','weight','measurements','notes','body_photo']
    assert purchase_route('nutrition',{}) == PURCHASE_STEPS['nutrition']


def test_profile_history_snapshots_are_always_objects():
    assert _json_object('{"age": 28}') == {'age':28}
    assert _json_object({'age':28}) == {'age':28}
    assert _json_object('broken') == {}


def test_zarinpal_receives_rials_for_toman_prices():
    assert toman_to_irr(399_000) == 3_990_000


def test_long_telegram_messages_are_bounded():
    parts = split_message('\n'.join(f'line {i}' for i in range(1500)), 500)
    assert len(parts) > 1
    assert all(0 < len(part) <= 500 for part in parts)


def test_plan_media_handlers_are_scoped_to_delivery_state():
    source=(ROOT/'app/handlers/admin.py').read_text(encoding='utf-8')
    assert '@router.message(PlanDelivery.waiting, F.photo' in source
    assert '@router.message(PlanDelivery.waiting, F.document' in source
    assert "status='delivered'" in (ROOT/'app/db/repositories.py').read_text(encoding='utf-8')


def test_unpaid_cancellation_preserves_order_audit_record():
    source=(ROOT/'app/db/repositories.py').read_text(encoding='utf-8')
    block=source.split('async def cancel_awaiting_payment_order',1)[1].split('async def total_sales',1)[0]
    assert "status='cancelled'" in block
    assert 'DELETE FROM orders' not in block


def test_repeated_status_clicks_do_not_repeat_customer_notifications():
    source=(ROOT/'app/db/repositories.py').read_text(encoding='utf-8')
    block=source.split('async def update_order_status',1)[1].split('async def attach_plan',1)[0]
    assert 'if current == status: return None' in block


def test_paid_sales_do_not_disappear_when_operational_status_changes():
    source=(ROOT/'app/db/repositories.py').read_text(encoding='utf-8')
    reporting=source.split('async def monthly_sales',1)[1].split('async def profile_history_for_user',1)[0]
    assert "status IN ('paid','needs_info','in_progress','ready','delivered')" not in reporting
    migration=(ROOT/'alembic/versions/0007_paid_reporting_index.py').read_text(encoding='utf-8')
    assert 'WHERE paid_at IS NOT NULL' in migration


def test_receipt_type_and_gateway_callback_are_deployable():
    migration=(ROOT/'alembic/versions/0006_receipt_type.py').read_text(encoding='utf-8')
    nginx=(ROOT/'deploy/nginx.conf.example').read_text(encoding='utf-8')
    assert 'receipt_type' in migration
    ingress=(ROOT/'deploy/ingress.conf').read_text(encoding='utf-8')
    assert 'proxy_pass http://127.0.0.1:8090' in nginx
    assert 'location = /payment/zarinpal/callback' in ingress


def test_alembic_supports_offline_migration_validation():
    source=(ROOT/'alembic/env.py').read_text(encoding='utf-8')
    assert 'context.is_offline_mode()' in source
    assert 'run_migrations_offline()' in source


def test_purchase_flow_exposes_progress_and_paginated_orders():
    source=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    assert "data.get('active_steps'," in source
    assert "page_size=3" in source


def test_optional_nutrition_answers_update_the_real_profile_columns():
    assert PROFILE_KEYMAP == {'allergy':'food_allergy','restriction':'food_restriction'}


def test_sensi_recovery_queues_are_paginated_and_receipts_actionable():
    source=(ROOT/'app/handlers/admin.py').read_text(encoding='utf-8')
    assert "page_size=10" in source
    assert "sensi:messages:page:" in source
    assert "o['status']=='awaiting_receipt'" in source
    assert 'receipt_actions_kb(oid)' in source


def test_navigation_clears_stale_conversation_state():
    user=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    admin=(ROOT/'app/handlers/admin.py').read_text(encoding='utf-8')
    assert 'async def order_detail(c,state:FSMContext)' in user
    assert 'async def view_order(c: CallbackQuery,state:FSMContext)' in admin
    assert "await repo.add_audit(c.from_user.id,'cancel_unpaid_order','order',oid)" in user


def test_sensi_conversation_preview_uses_latest_messages():
    source=(ROOT/'app/db/repositories.py').read_text(encoding='utf-8')
    block=source.split('async def support_messages_for_user',1)[1].split('async def monthly_sales',1)[0]
    assert 'ORDER BY sm.created_at DESC, sm.id DESC LIMIT $2' in block
    assert 'ORDER BY recent.created_at ASC, recent.id ASC' in block


def runtime_settings(**overrides):
    values=dict(bot_token='123:token',database_url='postgresql://db',redis_url='redis://cache',sensi_id=1,web_dev_login=False)
    values.update(overrides)
    return Settings(_env_file=None,**values)


def test_unsafe_payment_configuration_is_rejected():
    with pytest.raises(RuntimeError,match='PAYMENT_MODE'):
        runtime_settings(payment_mode='invalid').validate_runtime()
    with pytest.raises(RuntimeError,match='forbidden'):
        runtime_settings(app_env='production',payment_mode='mock').validate_runtime()


def test_valid_production_gateway_configuration_passes():
    runtime_settings(
        app_env='production',payment_mode='zarinpal',zarinpal_merchant_id='merchant-test',public_base_url='https://bot.example',
        webhook_secret='x'*32,
    ).validate_runtime()
