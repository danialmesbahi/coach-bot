"""Centimetre measurements shared by the bot and staff forms."""
import math

MEASUREMENTS = {
    'abdomen': 'دور شکم', 'waist': 'دور کمر', 'arm': 'دور بازو',
    'thigh': 'دور ران', 'shoulders': 'عرض شانه', 'chest': 'دور سینه',
}


def validate_measurements(value, *, complete=False):
    if not isinstance(value, dict) or set(value) - MEASUREMENTS.keys():
        raise ValueError('اندازه‌ها نامعتبرند.')
    result = {}
    for key, number in value.items():
        if isinstance(number, bool):
            raise ValueError('اندازه باید عدد باشد.')
        try:
            number = float(str(number).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫', '01234567890123456789.')))
        except (ValueError, TypeError):
            raise ValueError(f'{MEASUREMENTS[key]} باید عدد باشد.') from None
        if not math.isfinite(number) or not 5 <= number <= 300:
            raise ValueError(f'{MEASUREMENTS[key]} باید بین ۵ تا ۳۰۰ سانتی‌متر باشد.')
        result[key] = number
    if complete and result.keys() != MEASUREMENTS.keys():
        raise ValueError('هر شش اندازه را وارد کن.')
    return result


def parse_measurements(text):
    values = {}
    labels = {label: key for key, label in MEASUREMENTS.items()}
    for line in text.strip().splitlines():
        label, sep, value = line.partition(':')
        label = label.strip().replace('ي', 'ی').replace('ك', 'ک')
        key = labels.get(label, label)
        if not sep or key not in MEASUREMENTS or key in values:
            raise ValueError('هر اندازه را در یک خط، با نام و دونقطه وارد کن.')
        values[key] = value.strip()
    return validate_measurements(values, complete=True)


def measurements_text(values):
    return '\n'.join(f'{label}: {values[key]:g} سانتی‌متر' for key, label in MEASUREMENTS.items() if key in values)


def required_body_photos(data):
    return 4 if data.get('gender') in {'مرد', 'male'} else 0
