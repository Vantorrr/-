import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.bootstrap import prepare_storage
from app.crm import TransitionError, apply_transition
from app import db
from app.db import session_scope
from app.logging_setup import configure_logging
from app.models import DigestRecord, Listing, PipelineRun
from app.pipeline import run_once
from app.queries import list_listings, list_status_events, public_listing
from app.runtime import is_paused, set_paused
from app.settings import get_settings
from app.sources.registry import load_source_specs

_last_manual_run = 0.0


class TransitionIn(BaseModel):
    status: str
    confirmation: dict | None = None
    note: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    prepare_storage()
    yield


app = FastAPI(title="Qora intake", lifespan=lifespan)


@app.get("/health")
def health():
    database = "ok"
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database = "error"
    redis_ok = False
    try:
        from app.runtime import redis_client

        redis_ok = redis_client() is not None
    except Exception:
        redis_ok = False
    body = {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "redis": "ok" if redis_ok else "unavailable",
        "paused": is_paused() if redis_ok else False,
        "send_mode": get_settings().effective_send_mode,
    }
    return JSONResponse(body, status_code=200 if database == "ok" else 503)


@app.get("/api/sources")
def sources():
    specs = load_source_specs(get_settings().config_path / "sources.yaml")
    return [
        {
            "id": spec["id"],
            "kind": spec["kind"],
            "enabled": bool(spec.get("enabled")),
            "reason": spec.get("reason"),
        }
        for spec in specs
    ]


@app.get("/api/profile")
def profile():
    from app.pipeline import load_yaml

    return load_yaml(get_settings().config_path / "company_profile.yaml")


@app.get("/api/listings")
def listings(status: str | None = None, min_score: int | None = None, source_id: str | None = None, limit: int = 50):
    with session_scope() as session:
        rows = list_listings(session, status=status, min_score=min_score, source_id=source_id, limit=limit)
        return [public_listing(row) for row in rows]


@app.get("/api/listings/{listing_id}")
def listing_detail(listing_id: str):
    with session_scope() as session:
        row = session.get(Listing, listing_id)
        if row is None:
            raise HTTPException(status_code=404, detail="listing not found")
        payload = public_listing(row)
        payload["description"] = row.description or "неизвестно"
        payload["score_breakdown"] = row.score_breakdown or {}
        return payload


@app.get("/api/listings/{listing_id}/history")
def listing_history(listing_id: str):
    with session_scope() as session:
        row = session.get(Listing, listing_id)
        if row is None:
            raise HTTPException(status_code=404, detail="listing not found")
        events = list_status_events(session, listing_id)
        return [
            {
                "from_status": event.from_status,
                "to_status": event.to_status,
                "actor": event.actor,
                "note": event.note,
                "at": event.created_at.isoformat() + "Z",
            }
            for event in events
        ]


@app.post("/api/listings/{listing_id}/transition")
def transition(listing_id: str, body: TransitionIn):
    with session_scope() as session:
        row = session.get(Listing, listing_id)
        if row is None:
            raise HTTPException(status_code=404, detail="listing not found")
        try:
            apply_transition(
                row,
                body.status,
                session,
                actor="operator",
                confirmation=body.confirmation,
                note=body.note,
            )
        except TransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return public_listing(row)


@app.post("/api/pipeline/run")
def pipeline_run():
    global _last_manual_run
    now = time.monotonic()
    if now - _last_manual_run < 15:
        raise HTTPException(status_code=429, detail="pipeline run is rate limited")
    _last_manual_run = now
    return run_once()


@app.get("/api/pipeline/status")
def pipeline_status():
    with session_scope() as session:
        row = session.query(PipelineRun).order_by(PipelineRun.started_at.desc()).first()
        payload = _run_payload(row)
    return {"paused": is_paused(), "send_mode": get_settings().effective_send_mode, "last_run": payload}


def _run_payload(row) -> dict | None:
    if row is None:
        return None
    return {"id": row.id, "status": row.status, "started_at": row.started_at.isoformat() + "Z", "stats": row.stats}


@app.post("/api/pipeline/pause")
def pipeline_pause():
    if not set_paused(True):
        raise HTTPException(status_code=503, detail="redis unavailable, pause was not stored")
    return {"paused": True}


@app.post("/api/pipeline/resume")
def pipeline_resume():
    if not set_paused(False):
        raise HTTPException(status_code=503, detail="redis unavailable, pause was not stored")
    return {"paused": False}


@app.get("/api/digests")
def digests(limit: int = 10):
    with session_scope() as session:
        rows = session.query(DigestRecord).order_by(DigestRecord.created_at.desc()).limit(min(limit, 50)).all()
        return [
            {
                "id": row.id,
                "created_at": row.created_at.isoformat() + "Z",
                "delivery_status": row.delivery_status,
                "telegram_message_ids": row.telegram_message_ids or [],
                "error": row.error,
                "local_path": row.local_path,
                "pipeline_run_id": row.pipeline_run_id,
            }
            for row in rows
        ]
