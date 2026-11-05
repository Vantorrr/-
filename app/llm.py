import json
from dataclasses import dataclass

from app.logging_setup import get_logger
from app.proposals import CLICHES, clip, draft_proposal
from app.settings import get_settings

log = get_logger("llm")

ORIGIN_LABELS = {
    "template": "шаблон, не ответ модели",
    "model": "модель",
    "operator": "правка оператора",
}


@dataclass
class Draft:
    text: str
    origin: str
    provider: str | None = None


def origin_label(origin: str | None) -> str:
    return ORIGIN_LABELS.get(origin or "template", origin or "template")


def provider_ready(settings) -> bool:
    return bool(
        (getattr(settings, "llm_api_key", "") or "").strip()
        and (getattr(settings, "llm_base_url", "") or "").strip()
        and (getattr(settings, "llm_model", "") or "").strip()
    )


def draft_for_listing(listing, profile: dict | None, *, max_chars: int, settings=None, poster=None) -> Draft:
    profile = profile or {}
    settings = settings or get_settings()
    if not provider_ready(settings):
        return _template(listing, profile, max_chars)
    messages = _messages(listing, profile, max_chars)
    try:
        raw = (poster or _post_chat)(settings, messages)
    except Exception as exc:
        log.info("llm_draft_failed", error=type(exc).__name__)
        return _template(listing, profile, max_chars)
    if not _acceptable(raw, profile, listing):
        log.info("llm_draft_rejected", reason="empty profile facts or cliche")
        return _template(listing, profile, max_chars)
    return Draft(text=clip(str(raw).strip(), max_chars), origin="model", provider=settings.llm_model.strip())


def _template(listing, profile: dict, max_chars: int) -> Draft:
    return Draft(text=draft_proposal(listing, profile, max_chars=max_chars), origin="template", provider=None)


def _messages(listing, profile: dict, max_chars: int) -> list[dict]:
    facts = {
        "title": listing.title,
        "description": listing.description,
        "category": getattr(listing, "category", None),
        "lead_kind": getattr(listing, "lead_kind", None),
        "budget_kind": getattr(listing, "budget_kind", None),
        "budget_min": _plain(getattr(listing, "budget_min", None)),
        "budget_max": _plain(getattr(listing, "budget_max", None)),
        "budget_currency": getattr(listing, "budget_currency", None),
        "buyer_name": getattr(listing, "buyer_name", None),
        "remote": getattr(listing, "remote", None),
        "profile": profile,
        "max_chars": max_chars,
    }
    system = (
        "Составь короткий черновик отклика на русском только из JSON. "
        "Пустые поля профиля не упоминай. "
        "Не придумывай юрлицо, кейсы, команду, сертификаты, контакты и цену. "
        "Не пиши, что заявка уже отправлена."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(facts, ensure_ascii=False, default=str)},
    ]


def _plain(value):
    if value is None:
        return None
    return str(value)


def _acceptable(text: str, profile: dict, listing) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    lowered = cleaned.lower()
    for cliche in CLICHES:
        if cliche in lowered:
            return False
    if not (profile.get("cases") or []) and any(
        phrase in lowered for phrase in ("наш кейс", "наши кейсы", "похожий заполненный кейс", "наши проекты")
    ):
        return False
    if not (profile.get("legal_name") or "").strip() and "договор можем оформить" in lowered:
        return False
    listing_blob = " ".join(part or "" for part in (getattr(listing, "title", None), getattr(listing, "description", None))).lower()
    if not (profile.get("certificates") or []) and "сертификат" in lowered and "сертификат" not in listing_blob:
        return False
    if profile.get("team_size") in (None, "", 0) and "размер команды" in lowered:
        return False
    return True


def _post_chat(settings, messages: list[dict]) -> str:
    import httpx

    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={"model": settings.llm_model, "messages": messages, "temperature": 0},
        timeout=settings.http_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
