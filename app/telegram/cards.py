from app.display import format_budget
from app.llm import origin_label

HELP_TEXT = """Режим 2: подтверждение. Заявки сами не отправляются.
/start — эта справка
/orders — карточки, которые ждут решения
/top — пять лучших по баллу
/stats — счётчики
/replies — ответы заказчиков
/settings — режим, пауза, черновики
/pause — остановить сбор
/resume — снять паузу
Одобрение источника без разрешённого API отправки не ставит статус «отправлено»."""


def short_brief(listing, limit: int = 280) -> str:
    text = (getattr(listing, "description", None) or "").strip()
    if not text:
        return "неизвестно"
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]) + "…"


def proposed_price(listing) -> str:
    text = (getattr(listing, "proposed_price_text", None) or "").strip()
    return text or "неизвестно"


def order_card(listing) -> str:
    title = (getattr(listing, "title", None) or "").strip() or "неизвестно"
    lines = [
        title,
        f"Бюджет: {format_budget(listing)}",
        f"Источник: {listing.source_id}",
        f"Балл: {listing.score}",
        f"Ссылка: {listing.url}",
        f"Кратко: {short_brief(listing)}",
        f"Предлагаемая цена: {proposed_price(listing)}",
        f"Черновик ({origin_label(getattr(listing, 'proposal_origin', None))}):",
        (listing.proposal_text or "").strip() or "неизвестно",
    ]
    return "\n".join(lines)


def order_actions(listing) -> list[list[dict]]:
    rows = [
        [
            {"text": "Одобрить отправку", "data": f"ap:{listing.id}"},
            {"text": "Править", "data": f"ed:{listing.id}"},
        ],
        [
            {"text": "Отклонить", "data": f"rj:{listing.id}"},
            {"text": "В CRM", "data": f"crm:{listing.id}"},
        ],
    ]
    url = listing.url or ""
    if url.startswith("http://") or url.startswith("https://"):
        rows.append([{"text": "Открыть заказ", "url": url}])
    else:
        rows.append([{"text": "Открыть заказ", "data": f"op:{listing.id}"}])
    return rows
