import math

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def normalize_digits(value: str) -> str:
    return (value or '').translate(_DIGITS).strip()


def clean_text(value: str, max_len: int = 500) -> str:
    value = ' '.join((value or '').strip().split())
    return value[:max_len]


def parse_number(value: str):
    try:
        v = float(normalize_digits(value).replace(',', '.').replace('٫', '.').replace('٬', ''))
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def parse_int(value: str, minimum: int, maximum: int):
    try:
        s = normalize_digits(value)
        if not s.isdigit():
            return None
        v = int(s)
        return v if minimum <= v <= maximum else None
    except (TypeError, ValueError):
        return None
