import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import text

from app.bootstrap import prepare_storage
from app.crm import TransitionError, apply_transition
from app.crm_ops import (
    OpsError,
    add_expense,
    add_task,
    expense_summaries,
    list_expenses,
    list_tasks,
    public_expense,
    public_task,
    render_csv,
    set_due,
    set_task_done,
    status_funnel,
    summarize_expenses,
)
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


class ExpenseIn(BaseModel):
    amount: str
    currency: str
    note: str | None = None
    spent_on: str | None = None


class DueIn(BaseModel):
    due_on: str | None = None


class TaskIn(BaseModel):
    title: str
    due_at: str | None = None


class TaskDoneIn(BaseModel):
    done: bool


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
        "api": "ok",
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


@app.get("/api/stats/statuses")
def status_stats():
    with session_scope() as session:
        return status_funnel(session)


@app.get("/api/listings")
def listings(status: str | None = None, min_score: int | None = None, source_id: str | None = None, limit: int = 50):
    with session_scope() as session:
        rows = list_listings(session, status=status, min_score=min_score, source_id=source_id, limit=limit)
        summaries = expense_summaries(session, [row.id for row in rows])
        payload = []
        for row in rows:
            item = public_listing(row)
            item["expenses"] = summaries.get(row.id, "нет")
            payload.append(item)
        return payload


@app.get("/api/listings.csv")
def listings_csv(status: str | None = None, min_score: int | None = None, source_id: str | None = None, limit: int = 100):
    with session_scope() as session:
        payload = render_csv(session, status=status, min_score=min_score, source_id=source_id, limit=limit)
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=orders.csv"},
    )


@app.get("/api/listings/{listing_id}")
def listing_detail(listing_id: str):
    with session_scope() as session:
        row = session.get(Listing, listing_id)
        if row is None:
            raise HTTPException(status_code=404, detail="listing not found")
        expenses = list_expenses(session, listing_id)
        tasks = list_tasks(session, listing_id)
        payload = public_listing(row)
        payload["description"] = row.description or "неизвестно"
        payload["score_breakdown"] = row.score_breakdown or {}
        payload["expenses"] = summarize_expenses(expenses)
        payload["expense_items"] = [public_expense(item) for item in expenses]
        payload["tasks"] = [public_task(item) for item in tasks]
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


def _ops_call(listing_id: str, action):
    with session_scope() as session:
        if session.get(Listing, listing_id) is None:
            raise HTTPException(status_code=404, detail="listing not found")
        try:
            action(session)
        except OpsError as exc:
            message = str(exc)
            status_code = 404 if message in {"Заказ не найден.", "Задача не найдена."} else 400
            raise HTTPException(status_code=status_code, detail=message) from exc
        row = session.get(Listing, listing_id)
        return public_listing(row) if row is not None else {"ok": True}


@app.post("/api/listings/{listing_id}/expenses")
def create_expense(listing_id: str, body: ExpenseIn):
    def action(session):
        add_expense(
            session,
            listing_id,
            amount=body.amount,
            currency=body.currency,
            note=body.note,
            spent_on=body.spent_on,
        )

    return _ops_call(listing_id, action)


@app.post("/api/listings/{listing_id}/due")
def update_due(listing_id: str, body: DueIn):
    def action(session):
        set_due(session, listing_id, body.due_on)

    return _ops_call(listing_id, action)


@app.post("/api/listings/{listing_id}/tasks")
def create_task(listing_id: str, body: TaskIn):
    def action(session):
        add_task(session, listing_id, title=body.title, due_at=body.due_at)

    return _ops_call(listing_id, action)


@app.post("/api/listings/{listing_id}/tasks/{task_id}")
def update_task(listing_id: str, task_id: str, body: TaskDoneIn):
    def action(session):
        set_task_done(session, listing_id, task_id, body.done)

    return _ops_call(listing_id, action)


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
