from datetime import datetime, timezone

from app.models import StatusEvent

STATUSES = (
    "found",
    "checked",
    "proposal_ready",
    "awaiting_approval",
    "sent",
    "replied",
    "negotiation",
    "contract",
    "won",
    "lost",
    "rejected",
)

STATUS_LABELS = {
    "found": "найдено",
    "checked": "проверено",
    "proposal_ready": "черновик готов",
    "awaiting_approval": "ждёт подтверждения",
    "sent": "отправлено",
    "replied": "есть ответ",
    "negotiation": "переговоры",
    "contract": "договор",
    "won": "выиграно",
    "lost": "проиграно",
    "rejected": "отклонено",
}

ALLOWED: dict[str | None, set[str]] = {
    None: {"found"},
    "found": {"checked"},
    "checked": {"proposal_ready", "lost"},
    "proposal_ready": {"awaiting_approval", "lost"},
    "awaiting_approval": {"sent", "lost", "rejected"},
    "rejected": set(),
    "sent": {"replied", "lost"},
    "replied": {"negotiation", "lost"},
    "negotiation": {"contract", "lost"},
    "contract": {"won", "lost"},
    "won": set(),
    "lost": set(),
}


class TransitionError(Exception):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def apply_transition(
    listing,
    new_status: str,
    session,
    *,
    actor: str,
    confirmation: dict | None = None,
    note: str | None = None,
) -> None:
    if new_status not in STATUSES:
        raise TransitionError(f"unknown status {new_status}")
    current = listing.status
    if new_status == "sent":
        ok = bool(confirmation and confirmation.get("ok") is True and confirmation.get("external_result_id"))
        if not ok:
            raise TransitionError("status sent requires a confirmed API result with external_result_id")
        note = note or f"provider={confirmation.get('provider')}; result={confirmation.get('external_result_id')}"
    allowed = ALLOWED.get(current, set())
    if new_status not in allowed:
        raise TransitionError(f"cannot move {current} -> {new_status}")
    listing.status = new_status
    listing.updated_at = utcnow()
    session.add(
        StatusEvent(
            listing_id=listing.id,
            from_status=current,
            to_status=new_status,
            actor=actor,
            note=note,
            created_at=listing.updated_at,
        )
    )
