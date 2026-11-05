import uuid
from pathlib import Path

from sqlalchemy import or_

from app.crm import STATUS_LABELS, STATUSES, utcnow
from app.crm_ops import status_funnel
from app.db import session_scope
from app.delivery import deliver_digest
from app.digest import format_listing_block
from app.logging_setup import get_logger
from app.models import DigestRecord, Reminder
from app.queries import format_due, list_listings
from app.runtime import is_paused
from app.settings import get_settings

log = get_logger("daily_digest")


def render_daily_digest(session) -> str:
    funnel = status_funnel(session)
    lines = [
        "Qora Group — ежедневная сводка",
        "Режим отправки: подтверждение. Заявки на площадки не отправлялись.",
        "",
        "Сейчас по статусам:",
    ]
    for status in STATUSES:
        label = STATUS_LABELS[status]
        lines.append(f"- {label}: сейчас {funnel['current'][status]}, дошли {funnel['reached'][status]}")
    waiting = list_listings(session, status="awaiting_approval", limit=15)
    lines.append("")
    if not waiting:
        lines.append("Карточек, которые ждут решения, нет.")
    else:
        lines.append(f"Ждут решения, в тексте до {len(waiting)}:")
        lines.append("")
        for index, row in enumerate(waiting, start=1):
            lines.append(format_listing_block(row, index))
            lines.append(f"Срок: {format_due(row)}")
            lines.append("")
    now = utcnow()
    lines.append("Задачи к сроку:")
    due_tasks = (
        session.query(Reminder)
        .filter(Reminder.done.is_(False), Reminder.due_at.is_not(None), Reminder.due_at <= now)
        .order_by(Reminder.due_at.asc())
        .limit(30)
        .all()
    )
    if not due_tasks:
        lines.append("Задач к сроку нет.")
    else:
        for task in due_tasks:
            due = task.due_at.isoformat() + "Z"
            lines.append(f"- {task.title} (срок: {due})")
    lines.append("")
    lines.append("Открытые задачи:")
    open_tasks = (
        session.query(Reminder)
        .filter(Reminder.done.is_(False))
        .filter(or_(Reminder.due_at.is_(None), Reminder.due_at > now))
        .order_by(Reminder.created_at.asc())
        .limit(30)
        .all()
    )
    if not open_tasks:
        lines.append("Открытых задач нет.")
    else:
        for task in open_tasks:
            due = task.due_at.isoformat() + "Z" if task.due_at else "неизвестно"
            lines.append(f"- {task.title} (срок: {due})")
    return "\n".join(lines).strip() + "\n"


def run_daily_digest() -> dict:
    if is_paused():
        log.info("daily_digest_skipped", reason="paused")
        return {"status": "paused"}
    settings = get_settings()
    with session_scope() as session:
        body = render_daily_digest(session)
    delivered = deliver_digest(
        body,
        token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        data_dir=settings.data_dir,
    )
    if delivered.status == "skipped_no_credentials":
        log.info("skipped_no_credentials", path=delivered.local_path)
        note = "Telegram не отправлялся: нет TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID."
    elif delivered.status == "sent":
        note = "Telegram: отправлено, id=" + ",".join(str(item) for item in delivered.telegram_message_ids)
    else:
        note = f"Telegram: ошибка отправки ({delivered.error})."
    body = body + note + "\n"
    if delivered.local_path:
        Path(delivered.local_path).write_text(body, encoding="utf-8")
    with session_scope() as session:
        session.add(
            DigestRecord(
                id=str(uuid.uuid4()),
                pipeline_run_id=None,
                created_at=utcnow(),
                body=body,
                delivery_status=delivered.status,
                telegram_message_ids=delivered.telegram_message_ids,
                error=delivered.error,
                local_path=delivered.local_path,
            )
        )
    return {"status": delivered.status, "path": delivered.local_path}
