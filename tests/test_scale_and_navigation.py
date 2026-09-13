import pytest

from app.config import Settings, get_settings


def test_database_pool_limits_fail_closed():
    values = get_settings().model_dump()
    values.update(db_pool_min=10, db_pool_max=5)
    with pytest.raises(RuntimeError, match="DB_POOL_MIN"):
        Settings(**values).validate_runtime()


def test_console_navigation_keeps_content_while_loading_and_coalesces_events():
    client = open("web/src/components/console-app.tsx", encoding="utf-8").read()
    css = open("web/src/app/globals.css", encoding="utf-8").read()
    assert "cache.current[path]" in client and "renderedView" in client
    assert "refreshTimer.current === null" in client
    assert "Object.keys(cache.current).length >= 24" in client and "1_000" in client
    assert "realtimeTables[viewRef.current].includes(update.table)" in client
    menu = open("web/src/components/select-menu.tsx", encoding="utf-8").read()
    assert 'event.key === "ArrowDown"' in menu and 'role="option"' in menu
    assert 'className="page-progress"' in client and ".content-pane{min-height:" in css
    assert ".customer-card.glass{backdrop-filter:none" in css


def test_dashboard_kpis_precede_chart_and_collapsed_nav_can_reopen():
    client = open("web/src/components/console-app.tsx", encoding="utf-8").read()
    css = open("web/src/app/globals.css", encoding="utf-8").read()
    assert client.index('className={`dashboard-kpis') < client.index('className={`dashboard-grid')
    assert 'kpi-card sales-summary' in client and 'className="segmented sales-periods"' in client
    assert 't("salesTrend")' in client
    assert 'aria-expanded={collapsed !== "1"}' in client
    assert ".nav-collapsed .collapse-button{display:grid" in css
    assert ".nav-collapsed .sidebar nav button{grid-template-columns:24px 0 0" in css
    assert "@media(max-width:1280px)" in css and "@media(max-width:1120px)" in css
    assert 'SENSI / LIVE' not in client and 't("overview")}</h1>' not in client


def test_scale_indexes_and_bounded_polling_are_wired():
    migration = open("alembic/versions/0013_scale_indexes.py", encoding="utf-8").read()
    main = open("app/main.py", encoding="utf-8").read()
    web = open("app/webapp.py", encoding="utf-8").read()
    assert all(name in migration for name in ("idx_orders_actionable_created", "idx_orders_user_product_latest", "idx_support_unread_created"))
    assert "tasks_concurrency_limit=settings.bot_concurrency" in main
    assert web.count("await asyncio.gather(") >= 3


def test_avatar_path_uses_lightweight_identity_and_negative_cache():
    service = open("app/webapp.py", encoding="utf-8").read()
    repository = open("app/db/repositories.py", encoding="utf-8").read()
    assert "async def purchaser_identity" in repository
    assert "repo.purchaser_identity(user_id)" in service
    assert 'except TelegramBadRequest:' in service and 'set(cache_key, "-", ex=3600)' in service
    assert 'async with asyncio.timeout(3), request.app["avatar_slots"]' in service
    assert 'app["avatar_slots"] = asyncio.Semaphore(3)' in service


def test_console_requests_fail_fast_and_open_chat_refreshes_live():
    client = open("web/src/components/console-app.tsx", encoding="utf-8").read()
    api = open("web/src/lib/api.ts", encoding="utf-8").read()
    assert "15_000" in api and "controller.abort()" in api
    assert "JSON.parse(text)" in api and '"invalid_response"' in api
    assert "realtimeVersion={refresh}" in client
    assert "delete cache.current[pathRef.current]" in client
    assert "if (opened)" in client
    assert "avatarSources" in client and "avatarLoads" in client
    assert 'cache:"force-cache"' in client and "URL.createObjectURL" in client


def test_ios_pwa_navigation_respects_safe_areas():
    css = open("web/src/app/globals.css", encoding="utf-8").read()
    layout = open("web/src/app/layout.tsx", encoding="utf-8").read()
    assert 'viewportFit: "cover"' in layout and 'statusBarStyle: "black-translucent"' in layout
    assert all(token in css for token in (
        "safe-area-inset-top", "safe-area-inset-right",
        "safe-area-inset-bottom", "safe-area-inset-left",
    ))
    assert ".topbar{inset-block-start:calc(16px + var(--safe-top))}" in css
    assert "inset-block-end:calc(10px + var(--safe-bottom))" in css
    assert "padding-block-end:calc(98px + var(--safe-bottom))" in css
    assert ".mobile-nav{width:min(80vw,500px);height:62px;padding:6px;border-radius:24px;inset-block-end:calc(4px + var(--safe-bottom));left:50%;right:auto;transform:translateX(-50%)}" in css
    assert "orientation:landscape" in css and "padding-left:max(14px,var(--safe-left))" in css
    assert "html::-webkit-scrollbar" in css and "@media(hover:none),(pointer:coarse)" in css


def test_connection_status_expands_only_while_reconnecting():
    client = open("web/src/components/console-app.tsx", encoding="utf-8").read()
    css = open("web/src/app/globals.css", encoding="utf-8").read()
    assert 'className={`sync-status glass ${connection} ${lang}`}' in client
    assert 'connection !== "online" && <LoaderCircle className="spin"/>' in client
    assert ".sync-status.connecting,.sync-status.offline{width:172px" in css
    assert ".sync-status.en{right:auto;left:" in css
    assert ".sync-status.en.connecting,.sync-status.en.offline{grid-template-columns:40px 18px max-content;justify-content:start;column-gap:13px}" in css
    assert "@keyframes connection-ring" in css
    assert ".sync-status>i{grid-column:3;grid-row:1" in css
    assert ".sync-status{position:fixed" in css and "direction:ltr" in css
    assert "@media(min-width:1121px){.sync-status,.sync-status.en{inset-block-start:16px;inset-inline-end:18px;left:auto;right:auto}}" in css


def test_dashboard_exposes_total_users_and_ordered_quick_actions():
    client = open("web/src/components/console-app.tsx", encoding="utf-8").read()
    service = open("app/webapp.py", encoding="utf-8").read()
    assert 't("usersCount")' in client and "data.users" in client
    assert client.index('navigate("messages")') < client.index('navigate("orders")')
    assert 'repo.user_count()' in service and '"users": users' in service
    css = open("web/src/app/globals.css", encoding="utf-8").read()
    assert ".dashboard-kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:11px" in css
    assert ".dashboard-kpis .sales-summary{grid-column:1/-1}" in css


def test_customer_cards_use_spacious_image_led_layout():
    client = open("web/src/components/console-app.tsx", encoding="utf-8").read()
    css = open("web/src/app/globals.css", encoding="utf-8").read()
    assert 'className="customer-name"' in client and 'className="customer-code"' in client
    assert 'className="customer-footer"' in client and 'className="customer-message"' in client
    assert 'className="customer-action"' not in client
    assert ".customer-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:24px}" in css
    assert ".customer-card{aspect-ratio:auto;min-height:0;border-radius:24px;translate:none}" in css
    assert ".customer-photo{height:auto;aspect-ratio:1/1;border-radius:0 0 28px 28px" in css
    assert ".customer-photo .customer-code{inset-inline-start:auto;inset-inline-end:12px}" in css
    assert ".customer-name{text-align:center}" in css
    customers = client[client.index("function CustomerTools"):client.index("function Orders")]
    assert 't("spent")' not in customers
    assert ".customer-footer dl{flex:1;min-width:0;margin:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr))" in css
    assert '[dir="rtl"] .customer-footer{flex-direction:row-reverse}' in css
    assert '.customer-footer dt{min-height:28px;display:flex;align-items:flex-end;justify-content:center' in css
    assert '[dir="rtl"] .customer-photo .customer-code{left:12px;right:auto}' in css
    assert '.customer-card{height:100%}.customer-profile-action{flex:1;display:flex;flex-direction:column}' in css
    assert 'const hasFilters = Boolean(searchDraft || filters.activity !== "all"' in client
    assert 'disabled={!hasFilters}' in client
    assert 'SelectMenu compact compactDefault={compact[0]} label={t("activityFilter")}' in client
    assert 'lang === "en" ? "Active" : t("activeCourses")' in client
    assert 'compactDefault={compact[0]}' in client
    assert 'Search name, @handle, U-code or ID…' in open("web/src/lib/i18n.ts", encoding="utf-8").read()
    assert '.customer-footer{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))' in css
    assert '.customer-footer .customer-message>i{display:grid;place-items:center;width:40px;height:40px' in css
    assert '.customer-footer dt{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}' in css
    assert "@media(min-width:1440px){.customer-grid{grid-template-columns:repeat(5,minmax(0,1fr))" in css
    assert "@media(max-width:900px){.customer-grid{grid-template-columns:repeat(2,minmax(0,1fr))" in css


def test_customer_search_supports_name_handle_user_code_and_telegram_id():
    repo = open("app/db/repositories.py", encoding="utf-8").read()
    migration = open("alembic/versions/0014_customer_list_index.py", encoding="utf-8").read()
    assert 'identity_query = query[1:] if query[:1].lower() == "u" else query' in repo
    assert 'text_query = query[1:] if query.startswith("@") else query' in repo
    assert "WITH matched_users AS MATERIALIZED" in repo
    assert 'u.id=$6::bigint OR u.telegram_id=$6::bigint' in repo
    assert "idx_orders_paid_user" in migration


def test_customer_list_debounces_search_lazy_loads_and_reuses_http_avatar_cache():
    client = open("web/src/components/console-app.tsx", encoding="utf-8").read()
    service = open("app/webapp.py", encoding="utf-8").read()
    customers = client[client.index("function CustomerTools"):client.index("function Orders")]
    assert "searchDraft ? 650 : 0" in client
    assert 'new IntersectionObserver' in customers and 'rootMargin:"500px"' in customers
    assert "data.items.length >= data.total" in customers
    assert 'loading="lazy" decoding="async"' in client
    assert "avatarSources" in client and "avatarLoads" in client
    assert 'Cache-Control": "private, max-age=86400"' in service
    assert all(value in customers for value in ("name_asc", "name_desc", "spend_desc", "spend_asc", "orders_desc", "orders_asc"))
    assert 'sortActive' not in customers
    assert 'className={`customer-tools ${className}`}' in customers
    assert 'addEventListener("scroll", onScroll, { passive:true })' not in customers
    assert 'customerToolsReveal' not in client and 'className={`top-search glass ${lang}`}' not in client
    css = open("web/src/app/globals.css", encoding="utf-8").read()
    assert ".customer-grid{grid-template-columns:repeat(auto-fill,minmax(190px,1fr))}" in css
    assert "@media(min-width:1700px){.customer-grid{grid-template-columns:repeat(5,minmax(190px,1fr))}}" in css


def test_dashboard_reads_are_coalesced_and_health_checks_dependencies():
    service = open("app/webapp.py", encoding="utf-8").read()
    compose = open("docker-compose.yml", encoding="utf-8").read()
    assert 'await _cached(request, f"dashboard:{role}:{period}", 2, load)' in service
    assert 'request.app["read_cache_locks"].setdefault(key, asyncio.Lock())' in service
    assert 'await connection.fetchval("SELECT 1")' in service and 'await request.app["redis"].ping()' in service
    assert "max-size: \"10m\"" in compose and "http://127.0.0.1:8090/health" in compose
    assert '{ source: "/health", destination: `${backend}/health` }' in open("web/next.config.ts", encoding="utf-8").read()


def test_dashboard_uses_safe_chart_values_and_responsive_workspace_layout():
    client = open("web/src/components/console-app.tsx", encoding="utf-8").read()
    css = open("web/src/app/globals.css", encoding="utf-8").read()
    assert 'useLocalState<SalesPeriod>("sensi-sales-period-v2", "all")' in client
    assert "Number.isFinite(value) && value >= 0 ? value : 0" in client
    assert 'preserveAspectRatio="xMidYMid meet"' in client
    assert 'compactMoney(values[index], lang)' in client
    assert 'className="customers-layout"' in client and 'className="customer-results"' in client
    assert 'html[dir="rtl"] .sync-status,html[dir="rtl"] .sync-status.en{right:var(--sidebar-space)' in css
    assert ".customers-layout{display:grid;grid-template-columns:minmax(0,1fr) 248px" in css
    assert "@media(display-mode:standalone)" in css
    service = open("app/webapp.py", encoding="utf-8").read()
    assert "MAX(paid_at)) FROM orders WHERE paid_at IS NOT NULL" in service
