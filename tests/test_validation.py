from app.utils.validation import clean_text, parse_int, parse_number


def test_persian_digits():
    assert parse_int('۲۲', 10, 100) == 22
    assert parse_number('۱۷۸٫۵') == 178.5
    assert parse_number('۱۷۸.۵') == 178.5


def test_bounds():
    assert parse_int('7', 1, 7) == 7
    assert parse_int('8', 1, 7) is None
    assert parse_number('79') == 79


def test_clean_text():
    assert clean_text('  hello   world  ') == 'hello world'
    assert len(clean_text('x' * 600, 500)) == 500
