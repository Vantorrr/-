from decimal import Decimal


def unknown(value) -> str:
    if value is None or value == "":
        return "неизвестно"
    return str(value)


def remote_label(value) -> str:
    if value is True:
        return "удалённо"
    if value is False:
        return "не удалённо"
    return "неизвестно"


def buyer_type_label(value: str | None) -> str:
    return {
        "legal_entity": "юрлицо",
        "individual": "частное лицо",
        "unknown": "неизвестно",
    }.get(value or "unknown", "неизвестно")


def _amount(value) -> str:
    if value is None:
        return ""
    number = Decimal(str(value))
    if number == number.to_integral():
        return f"{int(number):,}".replace(",", " ")
    return f"{number.normalize():f}"


def format_budget(listing) -> str:
    kind = getattr(listing, "budget_kind", None) or "unknown"
    if kind == "unknown":
        return "неизвестно"
    currency = listing.budget_currency or ""
    suffix = f" {currency}" if currency else ""
    if kind == "exact":
        return f"{_amount(listing.budget_min)}{suffix}"
    if kind == "cap":
        return f"до {_amount(listing.budget_max)}{suffix}"
    if kind == "floor":
        return f"от {_amount(listing.budget_min)}{suffix}"
    if kind == "range":
        return f"{_amount(listing.budget_min)}–{_amount(listing.budget_max)}{suffix}"
    return "неизвестно"
