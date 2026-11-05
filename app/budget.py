import html
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

AMOUNT = r"(?:\d{1,3}(?:[ \u00a0]\d{3})+|\d+)(?:[.,]\d+)?"
MONEY = rf"(?:₽|руб\w*|rub|rur|usd|eur|€|\$)"
LABELED = re.compile(
    rf"(бюджет|нмцк|нмц|цена контракта|начальн\w* цен\w*)\s*[:\-]?\s*"
    rf"(?P<prefix>до|от)?\s*(?P<a>{AMOUNT})(?:\s*[-–—]\s*(?P<b>{AMOUNT}))?",
    re.IGNORECASE,
)
BARE = re.compile(
    rf"(?P<prefix>до|от)\s+(?P<a>{AMOUNT})(?:\s*{MONEY})?"
    rf"|(?P<a2>{AMOUNT})\s*[-–—]\s*(?P<b>{AMOUNT})(?:\s*{MONEY})?",
    re.IGNORECASE,
)
CURRENCY_RE = re.compile(MONEY, re.IGNORECASE)


@dataclass
class Budget:
    kind: str
    minimum: Decimal | None
    maximum: Decimal | None
    currency: str | None
    text: str | None


def _decimal(token: str) -> Decimal:
    cleaned = token.replace("\u00a0", " ").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(token) from exc


def _currency(window: str) -> str | None:
    match = CURRENCY_RE.search(window)
    if not match:
        return None
    token = match.group(0).lower()
    if token.startswith("руб") or token in {"₽", "rur", "rub"}:
        return "RUB"
    if token in {"$", "usd"}:
        return "USD"
    if token in {"€", "eur"}:
        return "EUR"
    return None


def _from_match(match: re.Match, text: str) -> Budget:
    window = text[max(0, match.start() - 12) : match.end() + 24]
    currency = _currency(window)
    prefix = (match.groupdict().get("prefix") or "").lower()
    first = match.groupdict().get("a") or match.groupdict().get("a2")
    second = match.groupdict().get("b")
    if not first:
        return Budget("unknown", None, None, None, None)
    amounts = [_decimal(token) for token in (first, second) if token]
    explicit_currency = currency is not None
    if currency is None:
        if max(amounts) >= 1000:
            currency = "RUB"
        else:
            return Budget("unknown", None, None, None, None)
    snippet = " ".join(match.group(0).split())
    if not explicit_currency:
        snippet = snippet + " RUB"
    if second:
        low, high = min(amounts), max(amounts)
        return Budget("range", low, high, currency, snippet)
    amount = amounts[0]
    if prefix == "до":
        return Budget("cap", None, amount, currency, snippet)
    if prefix == "от":
        return Budget("floor", amount, None, currency, snippet)
    return Budget("exact", amount, amount, currency, snippet)


SPAN = re.compile(
    rf"от\s+(?P<a>{AMOUNT})(?:\s*{MONEY})?\s*до\s+(?P<b>{AMOUNT})(?:\s*{MONEY})?",
    re.IGNORECASE,
)


def parse_budget(*parts: str | None) -> Budget:
    text = html.unescape("\n".join(part for part in parts if part)).replace("\u00a0", " ")
    span = SPAN.search(text)
    if span:
        parsed = _from_match(span, text)
        if parsed.kind != "unknown":
            return parsed
    labeled = LABELED.search(text)
    if labeled:
        parsed = _from_match(labeled, text)
        if parsed.kind != "unknown":
            return parsed
    if re.search(r"по\s+договор[её]нност", text, re.IGNORECASE) and not labeled:
        return Budget("unknown", None, None, None, None)
    chosen = None
    for match in BARE.finditer(text):
        parsed = _from_match(match, text)
        if parsed.kind == "unknown":
            continue
        window = text[match.start() : match.end() + 12]
        if _currency(window):
            return parsed
        chosen = parsed
    return chosen or Budget("unknown", None, None, None, None)
