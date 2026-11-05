import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.http import FetchError
from app.sources.base import FetchResult, RawListing
from app.sources.rss_common import apply_budget

MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


class WorkspaceCatalogSource:
    def __init__(self, spec: dict):
        self.id = spec["id"]
        self.catalog_url = spec["catalog_url"]
        self.fetch_details = bool(spec.get("fetch_details", True))
        self.max_details = int(spec.get("max_details") or 8)
        self.min_interval = float(spec.get("min_interval_seconds") or 2)
        self.proposal_max_chars = int(spec.get("proposal_max_chars") or 900)

    def fetch(self, client) -> FetchResult:
        try:
            response = client.get(self.catalog_url, min_interval=self.min_interval)
        except FetchError as exc:
            return FetchResult(source_id=self.id, error=str(exc))
        if response.status_code != 200:
            return FetchResult(source_id=self.id, error=f"HTTP {response.status_code}")
        listings = self.parse_catalog(response.text)
        warnings = []
        if self.fetch_details:
            fetched = 0
            for listing in listings:
                if fetched >= self.max_details:
                    warnings.append(f"details capped at {self.max_details}")
                    break
                if listing.status_text != "open":
                    continue
                if not _detail_allowed(listing.url):
                    continue
                try:
                    detail = client.get(listing.url, min_interval=self.min_interval)
                except FetchError as exc:
                    warnings.append(f"{listing.external_id}: {exc}")
                    continue
                fetched += 1
                if detail.status_code != 200:
                    warnings.append(f"{listing.external_id}: HTTP {detail.status_code}")
                    continue
                self.merge_detail(listing, detail.text)
        return FetchResult(
            source_id=self.id,
            listings=listings,
            warning="; ".join(warnings) or None,
        )

    def parse_catalog(self, html: str) -> list[RawListing]:
        soup = BeautifulSoup(html, "html.parser")
        rows = []
        for card in soup.select("[data-tender-card]"):
            link = card.select_one(".b-tender__title a")
            if link is None or not link.get("href"):
                continue
            href = link["href"]
            url = urljoin("https://workspace.ru", href)
            title = " ".join(link.get_text(" ", strip=True).split())
            status_node = card.select_one(".tendercart-type__status-public")
            status_raw = " ".join(status_node.get_text(" ", strip=True).split()) if status_node else ""
            status_text = "open" if "идет прием" in status_raw.lower().replace("ё", "е") else "closed"
            title_block = card.select_one(".b-tender__block--title")
            budget_node = title_block.select_one(".b-tender__info-item-text") if title_block else None
            budget_raw = " ".join(budget_node.get_text(" ", strip=True).split()) if budget_node else ""
            has_rub = bool(card.select_one(".rub"))
            if budget_raw and has_rub and "руб" not in budget_raw.lower() and "₽" not in budget_raw:
                budget_raw = f"{budget_raw} RUB"
            published = None
            deadline = None
            for item in card.select(".b-tender__info-item"):
                label_node = item.select_one(".b-tender__info-item-title")
                value_node = item.select_one(".b-tender__info-item-text")
                if not label_node or not value_node:
                    continue
                label = label_node.get_text(" ", strip=True).lower().replace("ё", "е")
                value = value_node.get_text(" ", strip=True)
                if "опубликован" in label:
                    published = _ru_date(value)
                if "крайний срок" in label:
                    deadline = _ru_date(value)
            external_id = _trailing_id(url) or (link.get("data-analytics-id") or "")
            if not external_id:
                continue
            listing = RawListing(
                source_id=self.id,
                external_id=str(external_id),
                url=url,
                title=title,
                lead_kind="tender",
                published_at=published,
                deadline=deadline,
                status_text=status_text,
                raw={"card_status": status_raw},
            )
            apply_budget(listing, budget_raw)
            rows.append(listing)
        return rows

    def merge_detail(self, listing: RawListing, html: str) -> None:
        soup = BeautifulSoup(html, "html.parser")
        node = soup.select_one(".tendercard__desc")
        if node is None:
            return
        text = " ".join(node.get_text(" ", strip=True).split())
        if text:
            listing.description = text
            if listing.budget_kind == "unknown":
                apply_budget(listing, text)


def _trailing_id(url: str) -> str | None:
    match = re.search(r"-(\d+)/?$", url.split("?", 1)[0])
    return match.group(1) if match else None


def _detail_allowed(url: str) -> bool:
    if "?" in url or "private-tender" in url:
        return False
    return url.startswith("https://workspace.ru/tenders/")


def _ru_date(value: str) -> datetime | None:
    match = re.search(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", value.lower().replace("ё", "е"))
    if not match:
        return None
    month = MONTHS.get(match.group(2))
    if not month:
        return None
    return datetime(int(match.group(3)), month, int(match.group(1)))
