from decimal import Decimal

from app.budget import parse_budget


def test_exact_ruble_budget():
    parsed = parse_budget("Массовое изменение (Бюджет: 12 000  ₽)")
    assert parsed.kind == "exact"
    assert parsed.minimum == Decimal("12000")
    assert parsed.currency == "RUB"


def test_cap_without_currency_word():
    parsed = parse_budget("до 200 000")
    assert parsed.kind == "cap"
    assert parsed.maximum == Decimal("200000")
    assert parsed.currency == "RUB"


def test_range_and_floor():
    parsed = parse_budget("100 000 - 300 000 руб")
    assert parsed.kind == "range"
    assert parsed.minimum == Decimal("100000")
    assert parsed.maximum == Decimal("300000")
    floor = parse_budget("от 900 000 ₽")
    assert floor.kind == "floor"
    assert floor.minimum == Decimal("900000")


def test_negotiable_and_small_noise_stay_unknown():
    assert parse_budget("Бюджет: по договоренности").kind == "unknown"
    assert parse_budget("до 300 позиций в каталоге").kind == "unknown"


def test_nmck_with_kopecks():
    parsed = parse_budget("НМЦК: 1 500 000,00 Российский рубль")
    assert parsed.kind == "exact"
    assert parsed.minimum == Decimal("1500000.00")


def test_from_to_is_a_range():
    parsed = parse_budget("От 180 000 ₽ до 220 000 ₽")
    assert parsed.kind == "range"
    assert parsed.minimum == Decimal("180000")
    assert parsed.maximum == Decimal("220000")
    assert parsed.currency == "RUB"


def test_usd_is_not_rewritten_as_rub_amount():
    parsed = parse_budget("Бюджет: 400 USD")
    assert parsed.kind == "exact"
    assert parsed.minimum == Decimal("400")
    assert parsed.currency == "USD"
