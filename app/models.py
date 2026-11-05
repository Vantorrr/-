from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_listing_source_ext"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    lead_kind: Mapped[str] = mapped_column(String(16), default="order")
    budget_min: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    budget_max: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    budget_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    budget_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_kind: Mapped[str] = mapped_column(String(16), default="unknown")
    buyer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    buyer_type: Mapped[str] = mapped_column(String(32), default="unknown")
    buyer_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status_text: Mapped[str] = mapped_column(String(16), default="open")
    status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    fit: Mapped[bool] = mapped_column(Boolean, default=False)
    score_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    exclusion_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    duplicate_of_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    proposal_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposal_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)


class StatusEvent(Base):
    __tablename__ = "status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DigestRecord(Base):
    __tablename__ = "digests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pipeline_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    body: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str] = mapped_column(String(32))
    telegram_message_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
