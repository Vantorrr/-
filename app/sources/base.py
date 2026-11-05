from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class RawListing:
    source_id: str
    external_id: str
    url: str
    title: str
    description: str | None = None
    category: str | None = None
    lead_kind: str = "order"
    budget_min: Decimal | None = None
    budget_max: Decimal | None = None
    budget_currency: str | None = None
    budget_text: str | None = None
    budget_kind: str = "unknown"
    buyer_name: str | None = None
    buyer_type: str = "unknown"
    buyer_evidence: str | None = None
    location: str | None = None
    remote: bool | None = None
    published_at: datetime | None = None
    deadline: datetime | None = None
    status_text: str = "open"
    raw: dict = field(default_factory=dict)


@dataclass
class FetchResult:
    source_id: str
    listings: list[RawListing] = field(default_factory=list)
    skipped: bool = False
    reason: str | None = None
    error: str | None = None
    warning: str | None = None
