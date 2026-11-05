import re

from app.display import format_budget, unknown

CLICHES = (
    "команда профессионалов",
    "индивидуальный подход",
    "лучшие цены",
    "гарантируем",
    "лидер рынка",
    "многолетний опыт",
    "уникальное предложение",
    "высокое качество",
    "недорого",
)


def _tokens(value: str) -> list[str]:
    found = []
    for part in re.findall(r"[A-Za-zА-Яа-яЁё0-9+#.]{2,}", value):
        token = part.lower().replace("ё", "е")
        ascii_token = token.isascii() and len(token) >= 3
        if len(token) >= 4 or any(char.isdigit() for char in token) or token in {"ai", "ux", "ui"} or ascii_token:
            found.append(token)
    return found


def matching_services(text: str, services: list) -> list[str]:
    lowered = text.lower().replace("ё", "е")
    matched = []
    for service in services or []:
        if not isinstance(service, str) or not service.strip():
            continue
        if any(token in lowered for token in _tokens(service)):
            matched.append(service.strip())
    return matched


def matching_case(text: str, cases: list) -> str | None:
    lowered = text.lower().replace("ё", "е")
    for case in cases or []:
        if not isinstance(case, dict):
            continue
        title = (case.get("title") or "").strip()
        summary = (case.get("summary") or "").strip()
        blob = f"{title} {summary}"
        if title and any(token in lowered for token in _tokens(blob)):
            url = (case.get("url") or "").strip()
            return f"{title}" + (f" ({url})" if url else "")
    return None


def _quote(description: str | None, limit: int = 220) -> str | None:
    if not description:
        return None
    text = " ".join(description.split())
    if len(text) < 40:
        return None
    if len(text) <= limit:
        return text if text[-1:] in ".!?…" else text + "."
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return cut + "…"


def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    room = max(1, limit - 1)
    cut = text[:room].rsplit(" ", 1)[0].rstrip(" ,;:")
    if not cut:
        cut = text[:room]
    return cut + "…"


def draft_proposal(listing, profile: dict, *, max_chars: int) -> str:
    profile = profile or {}
    text_blob = " ".join(
        part for part in (listing.title, listing.description, listing.category) if part
    )
    sentences = []
    display_name = (profile.get("display_name") or "").strip()
    if display_name:
        sentences.append(f"Здравствуйте, это {display_name}.")
    else:
        sentences.append("Здравствуйте.")
    title = (listing.title or "").strip()
    if listing.lead_kind == "vacancy":
        sentences.append(f"Смотрим вакансию «{title}».")
    elif listing.lead_kind == "tender":
        sentences.append(f"Готовы разобрать тендер «{title}» по тексту объявления.")
    else:
        sentences.append(f"По задаче «{title}» готовы работать по тому, что написано в объявлении.")
    quote = _quote(listing.description)
    if quote:
        sentences.append(f"В объявлении сказано: {quote}")
    services = matching_services(text_blob, profile.get("services") or [])
    if services:
        sentences.append("Из профиля сюда относится: " + "; ".join(services[:3]) + ".")
    case = matching_case(text_blob, profile.get("cases") or [])
    if case:
        sentences.append(f"Похожий заполненный кейс: {case}.")
    legal_name = (profile.get("legal_name") or "").strip()
    if legal_name:
        sentences.append(f"Договор можем оформить на {legal_name}.")
    if profile.get("team_size") not in (None, "", 0) and re.search(r"команд|штат", text_blob, re.IGNORECASE):
        sentences.append(f"В профиле указан размер команды: {profile['team_size']}.")
    certificates = [
        item.strip()
        for item in (profile.get("certificates") or [])
        if isinstance(item, str) and item.strip() and any(token in text_blob.lower() for token in _tokens(item))
    ]
    if certificates:
        sentences.append("Из профиля по теме есть документ: " + certificates[0] + ".")
    questions = []
    if (listing.budget_kind or "unknown") == "unknown":
        questions.append("бюджет")
    if listing.remote is None:
        questions.append("удалённо или в офисе")
    if questions:
        sentences.append("Напишите, пожалуйста, " + " и ".join(questions) + ".")
    contacts = [item for item in ((profile.get("telegram") or "").strip(), (profile.get("email") or "").strip()) if item]
    if contacts:
        sentences.append("Связь: " + ", ".join(contacts) + ".")
    draft = " ".join(sentences)
    for cliche in CLICHES:
        if cliche in draft.lower():
            raise RuntimeError(f"proposal template produced a cliche: {cliche}")
    return clip(draft, max_chars)


def high_fit(listing, threshold: int) -> bool:
    if getattr(listing, "duplicate_of_id", None):
        return False
    if getattr(listing, "exclusion_reasons", None):
        return False
    try:
        score = int(listing.score)
    except (TypeError, ValueError):
        return False
    return score >= int(threshold)


def _plain(value) -> str:
    if value is None:
        return "неизвестно"
    text = " ".join(str(value).split())
    return text or "неизвестно"


def _team(value) -> str:
    if value in (None, "", 0):
        return "неизвестно"
    return _plain(value)


def _strings(items) -> str:
    if not isinstance(items, list):
        return "неизвестно"
    cleaned = [item.strip() for item in items if isinstance(item, str) and item.strip()]
    return "; ".join(cleaned) if cleaned else "неизвестно"


def _cases(items) -> str:
    if not isinstance(items, list):
        return "неизвестно"
    rendered = []
    for case in items:
        if not isinstance(case, dict):
            continue
        parts = [
            str(case.get(key) or "").strip()
            for key in ("title", "summary", "url")
            if str(case.get(key) or "").strip()
        ]
        if parts:
            rendered.append(" — ".join(parts))
    return "; ".join(rendered) if rendered else "неизвестно"


def _excerpt(description: str | None, limit: int = 700) -> str:
    if not description or not str(description).strip():
        return "неизвестно"
    text = " ".join(str(description).split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return (cut or text[: limit - 1]) + "…"


def _crm_due(listing) -> str:
    value = getattr(listing, "crm_due_on", None)
    if not hasattr(value, "day"):
        return "неизвестно"
    return f"{value.day:02d}.{value.month:02d}.{value.year}"


def _moment(value) -> str:
    if value is None or value == "":
        return "неизвестно"
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y")
    return _plain(value)


def commercial_proposal(listing, profile: dict | None, *, threshold: int) -> str | None:
    """Full Markdown proposal for a high-fit order.

    The short marketplace draft is a different text and stays clipped, including
    the 500-character Profi.ru limit. This document is not clipped to that limit.
    Empty profile fields stay «неизвестно».
    """
    if not high_fit(listing, threshold):
        return None
    profile = profile or {}
    quote = _excerpt(getattr(listing, "description", None))
    price = (getattr(listing, "proposed_price_text", None) or "").strip() or "неизвестно"
    lines = [
        "# Коммерческое предложение",
        "",
        f"Порог полного предложения — {int(threshold)} баллов из config/scoring.yaml. Балл этого заказа — {int(listing.score)}.",
        "",
        "## Понимание задачи",
        f"Название: {_plain(getattr(listing, 'title', None))}",
        f"Из объявления: {quote}",
        f"Заказчик: {unknown(getattr(listing, 'buyer_name', None))}",
        f"Категория: {_plain(getattr(listing, 'category', None))}",
        "",
        "## Подход",
        f"Исполнитель: {_plain(profile.get('display_name'))}",
        f"Юрлицо: {_plain(profile.get('legal_name'))}",
        f"Услуги: {_strings(profile.get('services'))}",
        f"Кейсы: {_cases(profile.get('cases'))}",
        f"Сертификаты: {_strings(profile.get('certificates'))}",
        f"Размер команды: {_team(profile.get('team_size'))}",
        f"Дополнительные факты: {_strings(profile.get('extra_facts'))}",
        "",
        "## Срок",
        f"Срок в объявлении: {_moment(getattr(listing, 'deadline', None))}",
        f"Срок в CRM: {_crm_due(listing)}",
        "",
        "## Обоснование цены",
        f"Бюджет в объявлении: {format_budget(listing)}",
        f"Предлагаемая цена: {price}",
        "Сумма из объявления не подставляется как наша цена.",
        f"ИНН: {_plain(profile.get('inn'))}",
        f"Город: {_plain(profile.get('city'))}",
        f"Сайт: {_plain(profile.get('website'))}",
        f"Почта: {_plain(profile.get('email'))}",
        f"Телефон: {_plain(profile.get('phone'))}",
        f"Telegram: {_plain(profile.get('telegram'))}",
    ]
    own_words = "\n".join(line for line in lines if not line.startswith("Из объявления:"))
    for cliche in CLICHES:
        if cliche in own_words.lower():
            raise RuntimeError(f"commercial proposal produced a cliche: {cliche}")
    return "\n".join(lines).strip() + "\n"


def stored_or_commercial(listing, profile: dict | None, *, threshold: int) -> str | None:
    stored = getattr(listing, "commercial_proposal", None)
    if isinstance(stored, str) and stored.strip():
        return stored
    return commercial_proposal(listing, profile, threshold=threshold)
