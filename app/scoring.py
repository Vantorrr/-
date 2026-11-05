import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.buyers import gather_text


@dataclass
class ScoreResult:
    score: int
    component_score: int
    excluded: bool
    reasons: list[str] = field(default_factory=list)
    breakdown: dict = field(default_factory=dict)


def load_check(cfg: dict) -> None:
    weights = cfg["weights"]
    total = sum(int(value) for value in weights.values())
    if total != 100:
        raise ValueError(f"scoring weights must sum to 100, got {total}")


def _text(listing) -> str:
    return gather_text(listing).lower().replace("ё", "е")


def _hit(text: str, needle: str) -> bool:
    return re.search(rf"(?<![a-zа-я0-9]){re.escape(needle.lower())}", text) is not None


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(_hit(text, needle) for needle in needles)


def _to_rub(amount: Decimal | None, currency: str | None, cfg: dict) -> tuple[Decimal | None, str | None]:
    if amount is None:
        return None, None
    code = (currency or "RUB").upper()
    if code == "RUB":
        return amount, None
    rate = cfg.get("fx_rub", {}).get(code)
    if not rate:
        return None, None
    return (amount * Decimal(str(rate))), f"{code}->{rate} RUB"


def _exact_points(amount: Decimal, cfg: dict) -> int:
    points = cfg["budget_points"]
    bounds = cfg["bounds"]
    if amount < bounds["small_rub"]:
        return points["below_30k"]
    if amount < bounds["preferred_min_rub"]:
        return points["from_30k_to_100k"]
    if amount <= bounds["mid_rub"]:
        return points["from_100k_to_500k"]
    if amount <= bounds["preferred_max_rub"]:
        return points["from_500k_to_3m"]
    return points["above_3m"]


def budget_component(listing, cfg: dict) -> tuple[int, dict]:
    kind = listing.budget_kind or "unknown"
    points = cfg["budget_points"]
    if kind == "unknown":
        return points["unknown"], {"band": "unknown"}
    currency = listing.budget_currency
    low, fx_low = _to_rub(_as_decimal(listing.budget_min), currency, cfg)
    high, fx_high = _to_rub(_as_decimal(listing.budget_max), currency, cfg)
    fx = fx_low or fx_high
    if kind == "exact" and low is None:
        return points["unknown"], {"band": "fx_unknown", "fx": None}
    detail = {"kind": kind, "fx": fx}
    if kind == "cap":
        ceiling = high
        if ceiling is None:
            return points["unknown"], detail
        detail["rub_ceiling"] = str(ceiling)
        if ceiling < cfg["bounds"]["small_rub"]:
            detail["band"] = "below_30k"
            return points["below_30k"], detail
        if ceiling < cfg["bounds"]["preferred_min_rub"]:
            detail["band"] = "from_30k_to_100k"
            return points["from_30k_to_100k"], detail
        detail["band"] = "cap_reaches_preferred"
        return points["cap_reaches_preferred"], detail
    if kind == "floor":
        floor = low
        if floor is None:
            return points["unknown"], detail
        detail["rub_floor"] = str(floor)
        if floor >= cfg["bounds"]["preferred_max_rub"]:
            detail["band"] = "above_3m"
            return points["above_3m"], detail
        if floor >= cfg["bounds"]["preferred_min_rub"]:
            detail["band"] = "floor_in_preferred"
            return points["floor_in_preferred"], detail
        if floor >= cfg["bounds"]["small_rub"]:
            detail["band"] = "from_30k_to_100k"
            return points["from_30k_to_100k"], detail
        detail["band"] = "floor_open"
        return points["unknown"], detail
    if kind == "range" and low is not None and high is not None:
        detail["rub_min"] = str(low)
        detail["rub_max"] = str(high)
        if high < cfg["bounds"]["small_rub"]:
            detail["band"] = "below_30k"
            return points["below_30k"], detail
        if high < cfg["bounds"]["preferred_min_rub"]:
            detail["band"] = "from_30k_to_100k"
            return points["from_30k_to_100k"], detail
        if low > cfg["bounds"]["preferred_max_rub"]:
            detail["band"] = "above_3m"
            return points["above_3m"], detail
        detail["band"] = "range_overlaps_preferred"
        return points["range_overlaps_preferred"], detail
    if kind == "exact" and low is not None:
        detail["rub"] = str(low)
        detail["band"] = "exact"
        return _exact_points(low, cfg), detail
    return points["unknown"], detail


def _as_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def scope_clarity(listing, cfg: dict) -> str:
    description = (listing.description or "").strip()
    text = _text(listing)
    verbs = _contains_any(text, cfg["scope_verbs"])
    nouns = _contains_any(text, cfg["scope_nouns"])
    limits = cfg["scope_limits"]
    title = listing.title or ""
    if len(description) >= limits["clear_min_chars"] and verbs and nouns:
        return "clear"
    if len(description) >= limits["partial_min_chars"] and (verbs or nouns):
        return "partial"
    if (verbs or nouns) and len(title) >= 25:
        return "partial"
    return "vague"


def tech_component(listing, cfg: dict) -> tuple[int, list[str]]:
    text = _text(listing)
    matched = []
    for name, needles in cfg["tech_categories"].items():
        if _contains_any(text, needles):
            matched.append(name)
    if len(matched) >= 2:
        return cfg["tech_points"]["strong"], matched
    if len(matched) == 1:
        return cfg["tech_points"]["one"], matched
    if _contains_any(text, cfg["tech_adjacent"]):
        return cfg["tech_points"]["adjacent"], ["adjacent"]
    return cfg["tech_points"]["none"], []


def large_scope(text: str, cfg: dict) -> bool:
    strong = sum(1 for needle in cfg["strong_large_scope"] if _hit(text, needle))
    medium = sum(1 for needle in cfg["medium_large_scope"] if _hit(text, needle))
    return strong >= 1 or medium >= 2


def exclusion_reasons(listing, cfg: dict) -> list[str]:
    text = _text(listing)
    reasons = []
    if (listing.status_text or "open") in set(cfg["closed_statuses"]):
        reasons.append("завершён")
    if _contains_any(text, cfg["closed_patterns"]):
        reasons.append("завершён")
    if scope_clarity(listing, cfg) == "vague":
        reasons.append("размытая задача")
    if _unrealistic(listing, text, cfg):
        reasons.append("нереалистичный бюджет")
    if _unpaid_test(text, cfg):
        reasons.append("неоплачиваемое тестовое")
    if _prepaid_middleman(text, cfg):
        reasons.append("предоплата посреднику")
    if _contains_any(text, cfg["hard_exclude_patterns"]):
        reasons.append("вне профиля")
    # keep order, drop repeats
    unique = []
    for reason in reasons:
        if reason not in unique:
            unique.append(reason)
    return unique


def _rub_ceiling(listing, cfg: dict) -> Decimal | None:
    currency = listing.budget_currency
    high = _as_decimal(listing.budget_max)
    low = _as_decimal(listing.budget_min)
    amount = high if high is not None else low
    converted, _fx = _to_rub(amount, currency, cfg)
    return converted


def _unrealistic(listing, text: str, cfg: dict) -> bool:
    if (listing.budget_kind or "unknown") == "unknown":
        return False
    ceiling = _rub_ceiling(listing, cfg)
    if ceiling is None:
        return False
    if ceiling < cfg["bounds"]["absurd_low_rub"]:
        return True
    if large_scope(text, cfg) and ceiling < cfg["bounds"]["large_scope_max_rub"]:
        return True
    return False


def _unpaid_test(text: str, cfg: dict) -> bool:
    if not _contains_any(text, cfg["unpaid_test_patterns"]):
        return False
    if _contains_any(text, cfg["unpaid_markers"]):
        return True
    return large_scope(text, cfg)


def _prepaid_middleman(text: str, cfg: dict) -> bool:
    return _contains_any(text, cfg["prepaid_markers"]) and _contains_any(text, cfg["middleman_markers"])


def score_listing(listing, cfg: dict) -> ScoreResult:
    reasons = exclusion_reasons(listing, cfg)
    budget_pts, budget_detail = budget_component(listing, cfg)
    buyer_pts = cfg["buyer_points"].get(listing.buyer_type or "unknown", cfg["buyer_points"]["unknown"])
    clarity = scope_clarity(listing, cfg)
    scope_pts = cfg["scope_points"][clarity]
    if listing.remote is True:
        remote_pts = cfg["remote_points"]["remote"]
        remote_band = "remote"
    elif listing.remote is False:
        remote_pts = cfg["remote_points"]["office"]
        remote_band = "office"
    else:
        remote_pts = cfg["remote_points"]["unknown"]
        remote_band = "unknown"
    tech_pts, tech_matched = tech_component(listing, cfg)
    component = budget_pts + buyer_pts + scope_pts + remote_pts + tech_pts
    component = max(0, min(100, int(component)))
    excluded = bool(reasons)
    return ScoreResult(
        score=0 if excluded else component,
        component_score=component,
        excluded=excluded,
        reasons=reasons,
        breakdown={
            "budget": budget_pts,
            "budget_detail": budget_detail,
            "buyer": buyer_pts,
            "buyer_type": listing.buyer_type or "unknown",
            "scope": scope_pts,
            "scope_clarity": clarity,
            "remote": remote_pts,
            "remote_band": remote_band,
            "tech": tech_pts,
            "tech_matched": tech_matched,
            "component_score": component,
        },
    )
