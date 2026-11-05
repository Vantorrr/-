import re

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
