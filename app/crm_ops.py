import csv
import io
import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func

from app.crm import STATUSES, STATUS_LABELS, utcnow
from app.models import Expense, Listing, Reminder, StatusEvent
from app.queries import format_due, list_listings, public_listing

CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class OpsError(Exception):
    pass


def status_funnel(session) -> dict:
    current = {status: 0 for status in STATUSES}
    reached = {status: 0 for status in STATUSES}
    for status, count in session.query(Listing.status, func.count(Listing.id)).group_by(Listing.status):
        if status in current:
            current[status] = int(count)
    distinct_listings = func.count(func.distinct(StatusEvent.listing_id))
    for status, count in session.query(StatusEvent.to_status, distinct_listings).group_by(StatusEvent.to_status):
        if status in reached:
            reached[status] = int(count)
    return {"current": current, "reached": reached, "labels": dict(STATUS_LABELS)}


def money(amount) -> str:
    number = Decimal(str(amount))
    if number == number.to_integral():
        return str(int(number))
    return f"{number.quantize(Decimal('0.01')):f}"


def summarize_expenses(rows) -> str:
    if not rows:
        return "нет"
    buckets: dict[str, Decimal] = {}
    for row in rows:
        buckets.setdefault(row.currency, Decimal("0"))
        buckets[row.currency] += Decimal(str(row.amount))
    return "; ".join(f"{money(total)} {currency}" for currency, total in sorted(buckets.items()))


def expense_summaries(session, listing_ids: list[str]) -> dict[str, str]:
    if not listing_ids:
        return {}
    rows = session.query(Expense).filter(Expense.listing_id.in_(listing_ids)).all()
    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row.listing_id, []).append(row)
    return {listing_id: summarize_expenses(grouped.get(listing_id, [])) for listing_id in listing_ids}


def public_expense(row: Expense) -> dict:
    return {
        "id": row.id,
        "amount": money(row.amount),
        "currency": row.currency,
        "note": row.note or "",
        "spent_on": row.spent_on.isoformat() if row.spent_on else None,
    }


def public_task(row: Reminder) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "due_at": row.due_at.isoformat() + "Z" if row.due_at else None,
        "done": bool(row.done),
    }


def list_expenses(session, listing_id: str) -> list[Expense]:
    return session.query(Expense).filter(Expense.listing_id == listing_id).order_by(Expense.created_at.asc()).all()


def list_tasks(session, listing_id: str) -> list[Reminder]:
    return session.query(Reminder).filter(Reminder.listing_id == listing_id).order_by(Reminder.created_at.asc()).all()


def parse_amount(value) -> Decimal:
    try:
        amount = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, AttributeError) as exc:
        raise OpsError("Сумма не разобрана.") from exc
    if amount <= 0 or amount > Decimal("1000000000"):
        raise OpsError("Нужна сумма больше нуля.")
    return amount.quantize(Decimal("0.01"))


def parse_currency(value) -> str:
    currency = (value or "").strip().upper()
    if not CURRENCY_RE.match(currency):
        raise OpsError("Нужна валюта из трёх букв.")
    return currency


def parse_date(value) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise OpsError("Дата не разобрана.") from exc


def parse_due_at(value) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1]
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise OpsError("Дата задачи не разобрана.") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def add_expense(session, listing_id: str, *, amount, currency, note, spent_on) -> Expense:
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise OpsError("Заказ не найден.")
    row = Expense(
        id=str(uuid.uuid4()),
        listing_id=listing_id,
        amount=parse_amount(amount),
        currency=parse_currency(currency),
        note=(note or "").strip() or None,
        spent_on=parse_date(spent_on),
        created_at=utcnow(),
    )
    session.add(row)
    return row


def set_due(session, listing_id: str, due_on) -> Listing:
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise OpsError("Заказ не найден.")
    listing.crm_due_on = parse_date(due_on)
    listing.updated_at = utcnow()
    return listing


def add_task(session, listing_id: str, *, title, due_at) -> Reminder:
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise OpsError("Заказ не найден.")
    cleaned = (title or "").strip()
    if not cleaned:
        raise OpsError("Нужен текст задачи.")
    row = Reminder(
        id=str(uuid.uuid4()),
        listing_id=listing_id,
        title=cleaned,
        due_at=parse_due_at(due_at),
        done=False,
        created_at=utcnow(),
    )
    session.add(row)
    return row


def set_task_done(session, listing_id: str, task_id: str, done: bool) -> Reminder:
    row = session.get(Reminder, task_id)
    if row is None or row.listing_id != listing_id:
        raise OpsError("Задача не найдена.")
    row.done = bool(done)
    return row


def _cell(value) -> str:
    text = "" if value is None else str(value)
    if text[:1] in {"=", "+", "-", "@"}:
        return "'" + text
    return text


def render_csv(session, *, status: str | None, min_score: int | None, source_id: str | None, limit: int) -> str:
    rows = list_listings(session, status=status, min_score=min_score, source_id=source_id, limit=limit)
    summaries = expense_summaries(session, [row.id for row in rows])
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Идентификатор", "Название", "Источник", "Статус", "Балл", "Бюджет", "Срок", "Расходы", "Ссылка"])
    for row in rows:
        payload = public_listing(row)
        status_label = STATUS_LABELS.get(row.status or "", "неизвестно")
        writer.writerow(
            [
                _cell(row.id),
                _cell(row.title),
                _cell(row.source_id),
                _cell(status_label),
                _cell(row.score),
                _cell(payload["budget"]),
                _cell(format_due(row)),
                _cell(summaries.get(row.id, "нет")),
                _cell(row.url),
            ]
        )
    return "\ufeff" + buffer.getvalue()
