import asyncio
import hashlib
import hmac
import json
from types import SimpleNamespace
from urllib.parse import urlencode

from app.config import get_settings
from app.db.repositories import purchaser_order_by
from app.webapp import ASSET_FILES, SALES_PERIODS, _broadcast_update, _cached, _inspect_upload, _sales_period, _web_message, _web_order, _web_user, management_record_visible, validate_telegram_auth


def _signed(data: dict, webapp: bool):
    values = {key: str(value) for key, value in data.items()}
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    token = get_settings().bot_token.encode()
    secret = hmac.new(b"WebAppData", token, hashlib.sha256).digest() if webapp else hashlib.sha256(token).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_telegram_auth_accepts_fresh_signed_data_and_rejects_tampering():
    now = 1_800_000_000
    raw = _signed({"auth_date": now, "user": json.dumps({"id": 5819561965})}, True)
    assert validate_telegram_auth(raw, webapp=True, now=now)["id"] == 5819561965
    assert validate_telegram_auth(raw.replace("5819561965", "5819561966"), webapp=True, now=now) is None
    widget = _signed({"auth_date": now, "id": 5819561965, "first_name": "Danial"}, False)
    assert validate_telegram_auth(widget, webapp=False, now=now)["id"] == 5819561965


def test_web_console_has_responsive_theme_and_role_service():
    css = open("app/web/app.css", encoding="utf-8").read()
    compose = open("docker-compose.yml", encoding="utf-8").read()
    client = open("app/web/app.js", encoding="utf-8").read()
    service = open("app/webapp.py", encoding="utf-8").read()
    assert '@media (max-width:900px)' in css and 'data-theme="dark"' in css
    assert "app.webapp" in compose and '0.0.0.0:8090:3000' in compose
    assert "BACKEND_URL: http://web-api:8090" in compose
    assert 'data-sales-period' in client and 'data-sales-gate' in client
    assert "Math.round(slot*(total-1)/(limit-1))" in client
    assert 'grid-template-columns:repeat(4,minmax(0,1fr))' in css
    assert 'web.post("/api/sales-gate", sales_gate)' in service


def test_production_rejects_dev_login(monkeypatch):
    from app.config import Settings
    values = get_settings().model_dump()
    values.update(app_env="production", web_dev_login=True, webhook_secret="x" * 32, public_base_url="https://example.com", payment_mode="card_to_card", card_to_card_bank_info="configured")
    settings = Settings(**values)
    try:
        settings.validate_runtime()
    except RuntimeError as error:
        assert "WEB_DEV_LOGIN" in str(error)
    else:
        raise AssertionError("production dev login must fail closed")


def test_admin_management_records_require_a_successful_payment():
    assert management_record_visible("sensi", None)
    assert not management_record_visible("admin_team", {"paid_at": None})
    assert management_record_visible("admin_team", [{"paid_at": None}, {"paid_at": "2026-08-26"}])


def test_dashboard_sales_periods_are_whitelisted():
    assert [_sales_period(value) for value in ("day", "week", "month", "all")] == ["day", "week", "month", "all"]
    assert _sales_period("arbitrary SQL") == "month"
    assert SALES_PERIODS["day"][-1] == "1 hour"
    assert SALES_PERIODS["month"][-1] == "1 day"
    assert SALES_PERIODS["all"][1:] == (
        "date_trunc('month', paid_at)",
        "COALESCE((SELECT date_trunc('month', MIN(paid_at)) FROM orders WHERE paid_at IS NOT NULL), date_trunc('month', NOW()))",
        "COALESCE((SELECT date_trunc('month', MAX(paid_at)) FROM orders WHERE paid_at IS NOT NULL), date_trunc('month', NOW()))",
        "1 month",
    )


def test_read_cache_coalesces_identical_requests_and_realtime_invalidates_it():
    async def exercise():
        app = {"read_cache": {}, "read_cache_locks": {}, "realtime_subscribers": set()}
        request = SimpleNamespace(app=app)
        calls = 0

        async def load():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            return {"ok": True}

        values = await asyncio.gather(*(_cached(request, "dashboard:sensi:month", 2, load) for _ in range(20)))
        assert calls == 1 and all(value == {"ok": True} for value in values)
        _broadcast_update(app, json.dumps({"table": "orders", "action": "insert"}))
        assert "dashboard:sensi:month" not in app["read_cache"]

    asyncio.run(exercise())


def test_web_font_assets_are_explicitly_whitelisted():
    assert {"IRANYekanXVFaNumVF.woff2", "InterVariable.woff2"} <= ASSET_FILES


def test_web_media_metadata_never_exposes_telegram_file_ids():
    user = _web_user({"id": 4, "body_photo_file_id": "legacy", "body_photo_file_ids": [{"file_id": "photo-1"}]})
    order = _web_order({"id": 8, "form_snapshot": {"goal": "fit", "body_photo_file_ids": ["photo-2"]}, "plan_file_id": "plan"})
    message = _web_message({"id": 9, "file_id": "message-photo", "content_type": "photo"})
    assert user["photo_count"] == order["photo_count"] == 1
    assert "body_photo_file_ids" not in user and "body_photo_file_ids" not in order["form_snapshot"]
    assert "plan_file_id" not in order and "file_id" not in message and message["has_attachment"]


def test_customer_sorting_is_whitelisted_and_customer_ui_is_wired():
    client = open("app/web/app.js", encoding="utf-8").read()
    service = open("app/webapp.py", encoding="utf-8").read()
    assert purchaser_order_by("spend_desc").startswith("total_spend DESC")
    assert purchaser_order_by("spend_asc").startswith("total_spend ASC")
    assert purchaser_order_by("orders_desc").startswith("orders_count DESC")
    assert purchaser_order_by("orders_asc").startswith("orders_count ASC")
    assert purchaser_order_by("name_desc").endswith("DESC, user_id DESC")
    assert purchaser_order_by("DROP TABLE users") == purchaser_order_by("recent")
    assert all(value in client for value in ("customer-card", "data-customer-search", "data-customer-filter", 'role="listbox"', "closeCustomerFilters"))
    assert "customer-card>.row-link" not in open("app/web/app.css", encoding="utf-8").read()
    assert all(value in client for value in ("sidebarCollapsed", "applySidebar", "sidebar-collapsed"))
    assert 'id="page-title"' not in open("app/web/index.html", encoding="utf-8").read()
    assert 'web.get("/media/customers/{user_id:\\\\d+}/avatar", customer_avatar)' in service


def test_realtime_and_pwa_are_wired_without_caching_private_api_data():
    service = open("app/webapp.py", encoding="utf-8").read()
    client = open("app/web/app.js", encoding="utf-8").read()
    worker = open("app/web/service-worker.js", encoding="utf-8").read()
    manifest = json.load(open("app/web/manifest.webmanifest", encoding="utf-8"))
    migration = open("alembic/versions/0012_realtime_events.py", encoding="utf-8").read()
    assert "LISTEN" not in service and "add_listener" in service and 'web.get("/api/events", realtime_events)' in service
    assert "new EventSource('/api/events')" in client and "serviceWorker.register('/service-worker.js'" in client
    assert "url.pathname.startsWith('/api/')" in worker
    assert {icon["sizes"] for icon in manifest["icons"]} == {"192x192", "512x512"}
    assert all(table in migration for table in ("users", "orders", "support_messages", "sales_gate"))


def test_web_chat_reply_accepts_only_bounded_safe_attachments():
    service = open("app/webapp.py", encoding="utf-8").read()
    assert 'request.content_type.startswith("multipart/")' in service
    assert "settings.max_plan_file_mb * 1024 * 1024" in service
    assert "_inspect_upload(filename, payload)" in service
    assert all(sender in service for sender in ("send_photo", "send_video", "send_voice", "send_audio", "send_document", "send_animation"))


def test_upload_validation_checks_file_bytes_not_only_extension():
    assert _inspect_upload("proof.pdf", b"%PDF-1.7\n") == ("application/pdf", "document")
    assert _inspect_upload("renamed.pdf", b"MZ-not-a-pdf") is None
    assert _inspect_upload("photo.jpg", b"\xff\xd8\xffsample") == ("image/jpeg", "image")
