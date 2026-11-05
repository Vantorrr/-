import uuid
from datetime import datetime
from pathlib import Path

import yaml

from app.buyers import classify_buyer, classify_remote, gather_text
from app.crm import apply_transition, utcnow
from app.db import session_scope
from app.dedup import canonical_url, fingerprint, titles_are_duplicates
from app.delivery import deliver_digest
from app.digest import format_digest
from app.http import PoliteClient
from app.logging_setup import get_logger
from app.models import DigestRecord, Listing, PipelineRun
from app.proposals import draft_proposal
from app.runtime import acquire_run_lock, is_paused, release_run_lock
from app.scoring import load_check, score_listing
from app.settings import get_settings
from app.sources.registry import build_sources, load_source_specs

log = get_logger("pipeline")


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def run_once(
    *,
    sources=None,
    profile: dict | None = None,
    scoring: dict | None = None,
    deliver=None,
) -> dict:
    settings = get_settings()
    if is_paused():
        return {"status": "paused", "send_mode": settings.effective_send_mode}
    if not acquire_run_lock():
        return {"status": "already_running", "send_mode": settings.effective_send_mode}
    try:
        return _run_once(sources=sources, profile=profile, scoring=scoring, deliver=deliver)
    finally:
        release_run_lock()


def _run_once(*, sources, profile, scoring, deliver) -> dict:
    settings = get_settings()
    config_dir = settings.config_path
    if profile is None:
        profile = load_yaml(config_dir / "company_profile.yaml")
    if scoring is None:
        scoring = load_yaml(config_dir / "scoring.yaml")
    load_check(scoring)
    if sources is None:
        sources = build_sources(load_source_specs(config_dir / "sources.yaml"))
    started = utcnow()
    run_id = str(uuid.uuid4())
    source_rows = []
    raws = []
    client = PoliteClient(
        user_agent=settings.user_agent,
        timeout=settings.http_timeout_seconds,
        min_interval=settings.http_min_interval_seconds,
        max_retries=settings.http_max_retries,
    )
    limits = {}
    try:
        for source in sources:
            limits[source.id] = getattr(source, "proposal_max_chars", 900)
            if getattr(source, "reason", None) and source.__class__.__name__ == "ManualSource":
                source_rows.append(
                    {"id": source.id, "fetched": 0, "skipped": True, "reason": source.reason, "error": None}
                )
                continue
            try:
                result = source.fetch(client)
            except Exception as exc:
                log.exception("source_crashed", source=source.id)
                source_rows.append({"id": source.id, "fetched": 0, "skipped": False, "error": str(exc)})
                continue
            source_rows.append(
                {
                    "id": source.id,
                    "fetched": len(result.listings),
                    "skipped": result.skipped,
                    "reason": result.reason,
                    "error": result.error,
                    "warning": result.warning,
                }
            )
            raws.extend(result.listings)
            log.info("source_done", source=source.id, fetched=len(result.listings), error=result.error)
    finally:
        client.close()

    raws.sort(key=lambda item: item.published_at or datetime.max)
    summary = ingest(raws, profile=profile, scoring=scoring, limits=limits, now=started)
    fit_rows = summary.pop("fit_rows")
    ranked = sorted(fit_rows, key=lambda item: item.score, reverse=True)
    digest_rows = ranked[:15]
    body = format_digest(
        run_id=run_id,
        started_at=started.isoformat() + "Z",
        source_rows=source_rows,
        listings=digest_rows,
        total_fit=len(ranked),
        delivery_note="Отправка в Telegram выполняется только при заданных токене и чате и только после ответа API.",
    )
    sender = deliver or deliver_digest
    delivered = sender(
        body,
        token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        data_dir=settings.data_dir,
    )
    if delivered.status == "sent":
        delivery_note = "Telegram: отправлено, message_id=" + ",".join(
            str(item) for item in delivered.telegram_message_ids
        )
    elif delivered.status == "skipped_no_credentials":
        delivery_note = (
            "Telegram не отправлялся: не заданы TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID. "
            f"Локальная копия: {delivered.local_path}"
        )
    else:
        delivery_note = f"Telegram: ошибка отправки ({delivered.error}). Локальная копия: {delivered.local_path}"
    body = format_digest(
        run_id=run_id,
        started_at=started.isoformat() + "Z",
        source_rows=source_rows,
        listings=digest_rows,
        total_fit=len(ranked),
        delivery_note=delivery_note,
    )
    if delivered.local_path:
        Path(delivered.local_path).write_text(body, encoding="utf-8")
    stats = {
        "sources": source_rows,
        "new": summary["new"],
        "seen_existing": summary["seen_existing"],
        "duplicates": summary["duplicates"],
        "excluded": summary["excluded"],
        "fit": summary["fit"],
        "digest_status": delivered.status,
        "send_mode": settings.effective_send_mode,
    }
    with session_scope() as session:
        session.add(
            PipelineRun(
                id=run_id,
                started_at=started,
                finished_at=utcnow(),
                status="ok",
                stats=stats,
                error=None,
            )
        )
        session.add(
            DigestRecord(
                id=str(uuid.uuid4()),
                pipeline_run_id=run_id,
                created_at=utcnow(),
                body=body,
                delivery_status=delivered.status,
                telegram_message_ids=delivered.telegram_message_ids,
                error=delivered.error,
                local_path=delivered.local_path,
            )
        )
    log.info("run_finished", run_id=run_id, fit=summary["fit"], digest=delivered.status)
    return {"status": "ok", "run_id": run_id, **stats, "local_path": delivered.local_path}


def ingest(raws, *, profile: dict, scoring: dict, limits: dict, now: datetime) -> dict:
    threshold = int(scoring["threshold"])
    new = 0
    seen_existing = 0
    duplicates = 0
    excluded = 0
    fit = 0
    fit_rows = []
    seen_keys: set[tuple[str, str]] = set()
    with session_scope() as session:
        for raw in raws:
            key = (raw.source_id, raw.external_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            _enrich(raw)
            existing = (
                session.query(Listing)
                .filter(Listing.source_id == raw.source_id, Listing.external_id == raw.external_id)
                .one_or_none()
            )
            if existing is not None:
                existing.last_seen_at = now
                if not existing.description and raw.description:
                    existing.description = raw.description
                seen_existing += 1
                continue
            listing = _new_listing(raw, now)
            session.add(listing)
            session.flush()
            apply_transition(listing, "found", session, actor="system")
            new += 1
            duplicate = _find_duplicate(session, listing)
            if duplicate is not None:
                listing.duplicate_of_id = duplicate.id
                listing.score = 0
                listing.fit = False
                listing.exclusion_reasons = ["дубликат"]
                listing.score_breakdown = {"duplicate_of": duplicate.id}
                apply_transition(listing, "checked", session, actor="system", note="дубликат")
                duplicates += 1
                excluded += 1
                continue
            result = score_listing(listing, scoring)
            listing.score = result.score
            listing.score_breakdown = result.breakdown
            listing.exclusion_reasons = result.reasons
            listing.fit = (not result.excluded) and result.score >= threshold
            apply_transition(listing, "checked", session, actor="system")
            if result.excluded or not listing.fit:
                excluded += int(result.excluded)
                continue
            listing.proposal_text = draft_proposal(
                listing,
                profile,
                max_chars=int(limits.get(listing.source_id) or 900),
            )
            listing.proposal_chars = len(listing.proposal_text)
            apply_transition(listing, "proposal_ready", session, actor="system")
            apply_transition(listing, "awaiting_approval", session, actor="system", note="send_mode=confirmation")
            fit += 1
            fit_rows.append(_snapshot(listing))
        session.flush()
        # Detach-friendly copies: expire_on_commit is false, objects stay usable after commit.
        fit_rows = list(fit_rows)
    return {
        "new": new,
        "seen_existing": seen_existing,
        "duplicates": duplicates,
        "excluded": excluded,
        "fit": fit,
        "fit_rows": fit_rows,
    }


def _snapshot(listing: Listing):
    return ListingView(
        score=listing.score,
        source_id=listing.source_id,
        title=listing.title,
        buyer_name=listing.buyer_name,
        buyer_type=listing.buyer_type,
        budget_kind=listing.budget_kind,
        budget_min=listing.budget_min,
        budget_max=listing.budget_max,
        budget_currency=listing.budget_currency,
        remote=listing.remote,
        location=listing.location,
        url=listing.url,
        proposal_text=listing.proposal_text,
    )


class ListingView:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _enrich(raw) -> None:
    text = gather_text(raw)
    name, buyer_type, evidence = classify_buyer(text, raw.buyer_name, raw.buyer_type, raw.buyer_evidence)
    raw.buyer_name = name
    raw.buyer_type = buyer_type
    raw.buyer_evidence = evidence
    raw.remote = classify_remote(text, raw.remote)


def _new_listing(raw, now: datetime) -> Listing:
    return Listing(
        id=str(uuid.uuid4()),
        source_id=raw.source_id,
        external_id=raw.external_id,
        url=raw.url,
        title=raw.title,
        description=raw.description,
        category=raw.category,
        lead_kind=raw.lead_kind,
        budget_min=raw.budget_min,
        budget_max=raw.budget_max,
        budget_currency=raw.budget_currency,
        budget_text=raw.budget_text,
        budget_kind=raw.budget_kind,
        buyer_name=raw.buyer_name,
        buyer_type=raw.buyer_type,
        buyer_evidence=raw.buyer_evidence,
        location=raw.location,
        remote=raw.remote,
        published_at=raw.published_at,
        deadline=raw.deadline,
        status_text=raw.status_text,
        status=None,
        score=0,
        fit=False,
        fingerprint=fingerprint(raw.title),
        raw_payload=raw.raw,
        fetched_at=now,
        updated_at=now,
        last_seen_at=now,
    )


def _find_duplicate(session, listing: Listing):
    candidates = (
        session.query(Listing)
        .filter(Listing.id != listing.id, Listing.duplicate_of_id.is_(None))
        .order_by(Listing.fetched_at.desc())
        .limit(1000)
        .all()
    )
    this_url = canonical_url(listing.url)
    for other in candidates:
        if canonical_url(other.url) == this_url:
            return other
        if titles_are_duplicates(listing.title, other.title, _dec(listing.budget_min), _dec(other.budget_min)):
            return other
    return None


def _dec(value):
    if value is None:
        return None
    from decimal import Decimal

    return Decimal(str(value))
