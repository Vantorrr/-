from app.display import buyer_type_label, format_budget, remote_label, unknown
from app.models import Listing


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
        "exclusion_reasons": row.exclusion_reasons or [],
        "proposal": row.proposal_text,
        "proposal_chars": row.proposal_chars,
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
