import re

from app.http import FetchError
from app.sources.base import FetchResult, RawListing
from app.sources.rss_common import ParseError, apply_budget, external_id_from_url, parse_http_date, parse_rss_items


class HabrCareerSource:
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
            title = item["title"].strip()
            if not url or not title:
                continue
            description = item["description"] or ""
            location = None
            located = re.search(r"\(([^)]+)\)\s*$", title)
            if located:
                location = located.group(1).strip()
            lowered = description.lower().replace("ё", "е")
            if re.search(r"удален|remote", lowered):
                remote = True
            elif location and "полный рабочий день" in lowered:
                remote = False
            else:
                remote = None
            author = item["author"]
            listing = RawListing(
                source_id=self.id,
                external_id=item["guid"] or external_id_from_url(url, r"/vacancies/(\d+)"),
                url=url,
                title=title,
                description=description or None,
                lead_kind="vacancy",
                buyer_name=author,
                buyer_type="legal_entity" if author else "unknown",
                buyer_evidence="employer_in_habr_feed" if author else None,
                location=location,
                remote=remote,
                published_at=parse_http_date(item["pub_date"]),
                status_text="open",
                raw={"feed": label},
            )
            apply_budget(listing, description)
            rows.append(listing)
        return rows
