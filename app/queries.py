from datetime import date

from app.display import buyer_type_label, format_budget, remote_label, unknown
from app.llm import origin_label
from app.models import Listing, StatusEvent


def format_due(row) -> str:
    value = getattr(row, "crm_due_on", None)
    if not isinstance(value, date):
        return "неизвестно"
    return f"{value.day:02d}.{value.month:02d}.{value.year}"


def public_listing(row) -> dict:
    published = row.published_at.isoformat() + "Z" if row.published_at else "неизвестно"
    deadline = row.deadline.isoformat() + "Z" if row.deadline else "неизвестно"
    return {
        "id": row.id,
        "source_id": row.source_id,
        "external_id": row.external_id,
        "url": row.url,
        "title": row.title,
        "lead_kind": row.lead_kind,
        "status": row.status,
        "score": row.score,
        "fit": row.fit,
        "buyer_name": unknown(row.buyer_name),
        "buyer_type": buyer_type_label(row.buyer_type),
        "budget": format_budget(row),
        "remote": remote_label(row.remote),
        "location": unknown(row.location),
        "published_at": published,
        "deadline": deadline,
        "due_on": format_due(row),
        "exclusion_reasons": row.exclusion_reasons or [],
        "proposal": row.proposal_text,
        "proposal_chars": row.proposal_chars,
        "proposal_origin": getattr(row, "proposal_origin", None) or "template",
        "proposal_origin_label": origin_label(getattr(row, "proposal_origin", None)),
        "proposed_price": (getattr(row, "proposed_price_text", None) or "").strip() or "неизвестно",
        "in_crm": bool(getattr(row, "in_crm", False)),
        "duplicate_of_id": row.duplicate_of_id,
    }


def list_listings(
    session,
    *,
    status: str | None = None,
    min_score: int | None = None,
    source_id: str | None = None,
    limit: int = 50,
):
    query = session.query(Listing)
    if status:
        query = query.filter(Listing.status == status)
    if min_score is not None:
        query = query.filter(Listing.score >= min_score)
    if source_id:
        query = query.filter(Listing.source_id == source_id)
    return query.order_by(Listing.score.desc(), Listing.fetched_at.desc()).limit(min(limit, 200)).all()


def top_listings(session, limit: int = 5):
    return (
        session.query(Listing)
        .filter(Listing.fit.is_(True))
        .order_by(Listing.score.desc(), Listing.fetched_at.desc())
        .limit(limit)
        .all()
    )


def reply_listings(session, limit: int = 5):
    return (
        session.query(Listing)
        .filter(Listing.status.in_(("replied", "negotiation")))
        .order_by(Listing.updated_at.desc())
        .limit(limit)
        .all()
    )


def list_status_events(session, listing_id: str):
    return (
        session.query(StatusEvent)
        .filter(StatusEvent.listing_id == listing_id)
        .order_by(StatusEvent.created_at.asc(), StatusEvent.id.asc())
        .all()
    )
