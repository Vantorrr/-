from app.http import FetchError
from app.sources.base import FetchResult, RawListing
from app.sources.rss_common import ParseError, apply_budget, external_id_from_url, parse_http_date, parse_rss_items


class GenericRssSource:
    """Config-only RSS. Use this when a publisher documents a public feed."""

    def __init__(self, spec: dict):
        self.id = spec["id"]
        self.feeds = spec.get("feeds") or []
        self.min_interval = float(spec.get("min_interval_seconds") or 2)
        self.proposal_max_chars = int(spec.get("proposal_max_chars") or 900)
        self.lead_kind = spec.get("lead_kind") or "order"

    def fetch(self, client) -> FetchResult:
        if not self.feeds:
            return FetchResult(source_id=self.id, error="rss_generic source has no feeds")
        listings: list[RawListing] = []
        errors: list[str] = []
        for feed in self.feeds:
            label = feed.get("label") or feed["url"]
            try:
                response = client.get(feed["url"], min_interval=self.min_interval)
            except FetchError as exc:
                errors.append(f"{label}: {exc}")
                continue
            if response.status_code != 200:
                errors.append(f"{label}: HTTP {response.status_code}")
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
            listing = RawListing(
                source_id=self.id,
                external_id=item["guid"] or external_id_from_url(url),
                url=url,
                title=title,
                description=item["description"],
                category=", ".join(item["categories"]) or None,
                lead_kind=self.lead_kind,
                buyer_name=item["author"],
                published_at=parse_http_date(item["pub_date"]),
                raw={"feed": label},
            )
            apply_budget(listing, item["title"], item["description"])
            rows.append(listing)
        return rows


class ManualSource:
    def __init__(self, spec: dict):
        self.id = spec["id"]
        self.reason = spec.get("reason") or "manual"
        self.proposal_max_chars = int(spec.get("proposal_max_chars") or 900)

    def fetch(self, client) -> FetchResult:
        return FetchResult(source_id=self.id, skipped=True, reason=self.reason)
