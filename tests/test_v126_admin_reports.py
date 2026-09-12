from pathlib import Path
ROOT = Path(__file__).parents[1]


def test_stats_reply_is_single_role_aware_handler():
    s=(ROOT/'app/handlers/admin.py').read_text(encoding='utf-8')
    assert "@router.message(F.text.in_({'📊 آمار فروش','📊 فروش ماه جاری','📊 فروش و درآمد','📈 درآمد'}))" in s
    assert "async def stats_reply" in s
    # Avoid the old route-order bug where the Sensi-only handler intercepted admins.
    assert s.count("async def team_stats_reply") == 0


def test_monthly_commission_uses_monthly_revenue():
    s=(ROOT/'app/handlers/admin.py').read_text(encoding='utf-8')
    assert "monthly_revenue=int(month['revenue'] or 0)" in s
    assert "commission=monthly_revenue*settings.development_team_percent//100" in s
    assert "سهم تیم توسعه" in s


def test_purchasers_are_paginated_in_tens():
    kb=(ROOT/'app/keyboards.py').read_text(encoding='utf-8')
    repo=(ROOT/'app/db/repositories.py').read_text(encoding='utf-8')
    assert "LIMIT $1 OFFSET $2" in repo
    assert "team:buyer:{r['user_id']}:{page}" in kb
    assert "total_pages = max(1, (total + 9) // 10)" in (ROOT/'app/handlers/admin.py').read_text(encoding='utf-8')


def test_buyer_detail_includes_photos_and_receipt():
    s=(ROOT/'app/handlers/admin.py').read_text(encoding='utf-8')
    assert "body_photo_file_ids" in s
    assert "receipt_file_id" in s
    assert "answer_photo" in s
    assert "🔖 مرجع پرداخت" in s


def test_allergy_has_explicit_skip_handler():
    s=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    assert "@router.message(PurchaseForm.allergy, F.text.in_({'⏭️ ندارم','ندارم','نه','خیر'}))" in s
    assert "advance_after(state,m,'allergy')" in s


def test_phone_keyboard_removed_after_contact():
    s=(ROOT/'app/handlers/user.py').read_text(encoding='utf-8')
    assert "ReplyKeyboardRemove()" in s
    assert "phone=clean_text(c.phone_number,32)" in s
