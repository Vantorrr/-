from dataclasses import dataclass

from sqlalchemy import func

from app.crm import STATUSES, STATUS_LABELS, TransitionError, apply_transition, utcnow
from app.llm import provider_ready
from app.logging_setup import get_logger
from app.models import DraftEdit, Listing, StatusEvent
from app.submit import SubmitAdapter, adapter_for

log = get_logger("telegram_actions")

PROFILE_TEXT_KEYS = (
    "display_name",
    "legal_name",
    "inn",
    "city",
    "website",
    "email",
    "phone",
    "telegram",
)
PROFILE_LIST_KEYS = ("services", "cases", "certificates", "extra_facts")


@dataclass
class ActionResult:
    ok: bool
    status: str | None
    sent: bool
    message: str


def approve_send(session, listing_id: str, adapter: SubmitAdapter | None = None) -> ActionResult:
    listing = session.get(Listing, listing_id)
    if listing is None:
        return ActionResult(False, None, False, "Карточка не найдена.")
    if listing.status != "awaiting_approval":
        return ActionResult(
            False,
            listing.status,
            False,
            f"Сейчас статус {listing.status}. Отправка не выполнялась, статус sent не поставлен.",
        )
    adapter = adapter or adapter_for(listing.source_id)
    if not adapter.can_submit:
        return ActionResult(
            True,
            listing.status,
            False,
            "У источника нет разрешённого API отправки. Черновик остаётся на ручной отправке. Статус sent не поставлен.",
        )
    try:
        result = adapter.submit(listing)
    except Exception as exc:
        log.info("submit_adapter_failed", source_id=listing.source_id, error=type(exc).__name__)
        return ActionResult(False, listing.status, False, "Адаптер отправки не подтвердил результат. Статус sent не поставлен.")
    if not (result and result.ok is True and result.external_result_id):
        return ActionResult(False, listing.status, False, "Адаптер не подтвердил отправку. Статус sent не поставлен.")
    try:
        apply_transition(
            listing,
            "sent",
            session,
            actor="operator",
            confirmation={
                "ok": True,
                "external_result_id": result.external_result_id,
                "provider": adapter.name,
            },
        )
    except TransitionError:
        return ActionResult(False, listing.status, False, "Переход в sent отклонён. Статус sent не поставлен.")
    return ActionResult(True, listing.status, True, "Отправка подтверждена адаптером. Статус: sent.")


def reject_listing(session, listing_id: str) -> ActionResult:
    listing = session.get(Listing, listing_id)
    if listing is None:
        return ActionResult(False, None, False, "Карточка не найдена.")
    try:
        apply_transition(listing, "rejected", session, actor="operator", note="кнопка «Отклонить»")
    except TransitionError:
        return ActionResult(False, listing.status, False, "Отклонить из этого статуса нельзя. Отправка не выполнялась.")
    return ActionResult(True, listing.status, False, "Отклонено. Заявка не отправлялась.")


def add_to_crm(session, listing_id: str) -> ActionResult:
    listing = session.get(Listing, listing_id)
    if listing is None:
        return ActionResult(False, None, False, "Карточка не найдена.")
    listing.in_crm = True
    listing.updated_at = utcnow()
    return ActionResult(
        True,
        listing.status,
        False,
        f"Карточка отмечена в CRM: /orders/{listing.id}. Статус отправки не менялся.",
    )


def begin_edit(session, chat_id: str, listing_id: str) -> ActionResult:
    listing = session.get(Listing, listing_id)
    if listing is None:
        return ActionResult(False, None, False, "Карточка не найдена.")
    row = session.get(DraftEdit, chat_id)
    now = utcnow()
    if row is None:
        session.add(DraftEdit(chat_id=chat_id, listing_id=listing_id, created_at=now))
    else:
        row.listing_id = listing_id
        row.created_at = now
    return ActionResult(True, listing.status, False, "Пришлите новый текст черновика одним сообщением.")


def apply_pending_edit(session, chat_id: str, text: str) -> ActionResult | None:
    pending = session.get(DraftEdit, chat_id)
    if pending is None:
        return None
    cleaned = (text or "").strip()
    if not cleaned:
        return ActionResult(False, None, False, "Пустой текст не сохранён. Пришлите черновик ещё раз.")
    listing = session.get(Listing, pending.listing_id)
    if listing is None:
        session.delete(pending)
        return ActionResult(False, None, False, "Карточка не найдена.")
    listing.proposal_text = cleaned
    listing.proposal_chars = len(cleaned)
    listing.proposal_origin = "operator"
    listing.updated_at = utcnow()
    session.delete(pending)
    message = "Черновик обновлён. Это правка оператора, не ответ модели. Статус отправки не менялся."
    if listing.source_id == "profi_ru" and len(cleaned) > 500:
        message += f" На Profi.ru лимит 500 знаков, сейчас {len(cleaned)}."
    return ActionResult(True, listing.status, False, message)


def stats_text(session) -> str:
    counts = dict(session.query(Listing.status, func.count(Listing.id)).group_by(Listing.status).all())
    lines = ["Счётчики"]
    for status in STATUSES:
        lines.append(f"{STATUS_LABELS[status]} ({status}): {counts.get(status, 0)}")
    if counts.get(None):
        lines.append(f"без статуса: {counts[None]}")
    origins = dict(
        session.query(Listing.proposal_origin, func.count(Listing.id))
        .filter(Listing.proposal_text.is_not(None))
        .group_by(Listing.proposal_origin)
        .all()
    )
    lines.append(f"Черновики-шаблоны: {origins.get('template', 0)}")
    lines.append(f"Черновики модели: {origins.get('model', 0)}")
    lines.append(f"Отправлено: {counts.get('sent', 0)}")
    sent_events = session.query(StatusEvent).filter(StatusEvent.to_status == "sent").count()
    lines.append(f"Подтверждённых переходов в sent: {sent_events}")
    return "\n".join(lines)


def profile_has_facts(profile: dict | None) -> bool:
    profile = profile or {}
    for key in PROFILE_TEXT_KEYS:
        if str(profile.get(key) or "").strip():
            return True
    for key in PROFILE_LIST_KEYS:
        if profile.get(key):
            return True
    return profile.get("team_size") not in (None, "", 0)


def settings_text(*, settings, profile: dict | None, redis_up: bool, paused: bool) -> str:
    if not redis_up:
        pause_line = "Пауза: Redis недоступен, состояние не читается."
    elif paused:
        pause_line = "Пауза: да."
    else:
        pause_line = "Пауза: нет."
    if provider_ready(settings):
        llm_line = "LLM: ключ, адрес и модель заданы. Новый черновик может быть помечен как модель."
    elif (settings.llm_api_key or "").strip():
        llm_line = "LLM: ключ есть, адрес или модель пустые. Черновики остаются шаблоном."
    else:
        llm_line = "LLM: ключ не задан. Черновики — шаблон, не ответ модели."
    profile_line = "Профиль компании: есть заполненные поля." if profile_has_facts(profile) else "Профиль компании: пустой."
    chat_line = "Чат команд: задан." if (settings.telegram_chat_id or "").strip() else "Чат команд: не задан."
    return "\n".join(
        [
            "Режим: подтверждение (2). Автоотправка выключена.",
            pause_line,
            llm_line,
            profile_line,
            chat_line,
        ]
    )
