import re
from urllib.parse import parse_qs, urlparse

from app.http import FetchError
from app.sources.base import FetchResult, RawListing
from app.sources.rss_common import ParseError, apply_budget, external_id_from_url, parse_http_date, parse_rss_items


class EisRssSource:
    """Public extended-search RSS. The SOAP archive API needs a token we do not have."""

    def __init__(self, spec: dict):
        self.id = spec["id"]
        self.feeds = spec.get("feeds") or []
        self.min_interval = float(spec.get("min_interval_seconds") or 5)
        self.timeout = float(spec.get("timeout_seconds") or 20)
        self.proposal_max_chars = int(spec.get("proposal_max_chars") or 900)

    def fetch(self, client) -> FetchResult:
        listings: list[RawListing] = []
        errors: list[str] = []
        for feed in self.feeds:
            label = feed.get("label") or "eis"
            try:
                response = client.get(feed["url"], timeout=self.timeout, min_interval=self.min_interval)
            except FetchError as exc:
                errors.append(f"{label}: {exc}")
                continue
            if response.status_code != 200:
                errors.append(f"{label}: HTTP {response.status_code}")
                continue
            content_type = response.headers.get("content-type", "")
            if "html" in content_type and "xml" not in content_type and "rss" not in content_type:
                errors.append(f"{label}: content-type {content_type}")
                continue
            try:
                listings.extend(self.parse(response.text, label))
            except ParseError as exc:
                errors.append(f"{label}: {exc}")
        return FetchResult(
            source_id=self.id,
            listings=listings,
            error="; ".join(errors) if errors and not listings else None,
            warning="; ".join(errors) if errors and listings else None,
        )

    def parse(self, xml_text: str, label: str) -> list[RawListing]:
        rows = []
        for item in parse_rss_items(xml_text):
            url = item["link"]
            title = item["title"].strip()
            if not url or not title:
                continue
            description = item["description"]
            reg_number = _reg_number(url) or external_id_from_url(url, r"regNumber=(\d+)")
            buyer_name = _labeled(description, "Заказчик") or _labeled(description, "Организация")
            closed = bool(re.search(r"отмен", title, re.IGNORECASE))
            listing = RawListing(
                source_id=self.id,
                external_id=reg_number,
                url=url,
                title=title,
                description=description,
                lead_kind="tender",
                buyer_name=buyer_name,
                buyer_type="legal_entity",
                buyer_evidence="eis_procurement_notice",
                published_at=parse_http_date(item["pub_date"]),
                status_text="closed" if closed else "open",
                raw={"feed": label},
            )
            apply_budget(listing, title, description)
            rows.append(listing)
        return rows


def _reg_number(url: str) -> str | None:
    query = parse_qs(urlparse(url).query)
    values = query.get("regNumber") or query.get("regnumber")
    if values:
        return values[0]
    return None


def _labeled(text: str | None, label: str) -> str | None:
    if not text:
        return None
    match = re.search(rf"{label}\s*:\s*([^<\n.]{{3,120}})", text)
    if not match:
        return None
    return " ".join(match.group(1).split())
