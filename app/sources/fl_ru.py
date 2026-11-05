import re

from app.http import FetchError
from app.sources.base import FetchResult, RawListing
from app.sources.rss_common import apply_budget, external_id_from_url, parse_http_date, parse_rss_items
from app.sources.rss_common import ParseError


class FlRssSource:
    def __init__(self, spec: dict):
        self.id = spec["id"]
        self.feeds = spec.get("feeds") or []
        self.min_interval = float(spec.get("min_interval_seconds") or 2)
        self.proposal_max_chars = int(spec.get("proposal_max_chars") or 900)

    def fetch(self, client) -> FetchResult:
        listings: list[RawListing] = []
        errors: list[str] = []
        seen: set[str] = set()
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
                parsed = self.parse(response.text, label)
            except ParseError as exc:
                errors.append(f"{label}: {exc}")
                continue
            for item in parsed:
                if item.external_id in seen:
                    continue
                seen.add(item.external_id)
                listings.append(item)
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
            title = re.sub(r"\s+", " ", item["title"]).strip()
            if not url or not title:
                continue
            listing = RawListing(
                source_id=self.id,
                external_id=external_id_from_url(url, r"/projects/(\d+)"),
                url=url,
                title=re.sub(r"\s*\(Бюджет:.*?\)\s*$", "", title).strip() or title,
                description=item["description"],
                category=", ".join(item["categories"]) or None,
                lead_kind="order",
                remote=True,
                published_at=parse_http_date(item["pub_date"]),
                status_text="open",
                raw={"feed": label, "rss_title": item["title"]},
            )
            apply_budget(listing, item["title"], item["description"])
            rows.append(listing)
        return rows
