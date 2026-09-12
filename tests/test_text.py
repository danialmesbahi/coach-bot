from app.utils.text import money, status_fa, payment_method_fa

def test_money(): assert money(399000) == '399,000 تومان'
def test_status(): assert 'در انتظار' in status_fa('paid')
def test_payment_method(): assert payment_method_fa('card_to_card') == 'کارت‌به‌کارت'
