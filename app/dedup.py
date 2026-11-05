import hashlib
import re
from decimal import Decimal


def normalize_title(title: str) -> str:
    text = title.lower().replace("ё", "е")
    text = re.sub(r"\(бюджет:.*?\)", " ", text)
    text = re.sub(r"[^a-zа-я0-9]+", " ", text)
    return " ".join(text.split())


def fingerprint(title: str) -> str:
    return hashlib.sha256(normalize_title(title).encode("utf-8")).hexdigest()


def canonical_url(url: str) -> str:
    base = url.split("#", 1)[0].split("?", 1)[0].rstrip("/").lower()
    return base


def _close(left: Decimal | None, right: Decimal | None) -> bool:
    if left is None or right is None:
        return False
    if left == right:
        return True
    scale = max(abs(left), abs(right), Decimal("1"))
    return abs(left - right) / scale <= Decimal("0.05")


def titles_are_duplicates(
    title_a: str,
    title_b: str,
    budget_a: Decimal | None = None,
    budget_b: Decimal | None = None,
) -> bool:
    left = normalize_title(title_a)
    right = normalize_title(title_b)
    if not left or not right:
        return False
    tokens_a = left.split()
    tokens_b = right.split()
    if left == right and len(tokens_a) >= 5:
        return True
    if left == right and len(tokens_a) >= 3 and _close(budget_a, budget_b):
        return True
    if len(tokens_a) >= 5 and len(tokens_b) >= 5:
        union = set(tokens_a) | set(tokens_b)
        if not union:
            return False
        overlap = len(set(tokens_a) & set(tokens_b)) / len(union)
        return overlap >= 0.85
    return False
