import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from app.budget import parse_budget
from app.sources.base import RawListing


class ParseError(Exception):
    pass


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def child_text(node: ET.Element, name: str) -> str | None:
    for child in list(node):
        if local_name(child.tag) == name and child.text:
            value = " ".join(child.text.split())
            return value or None
    return None


def parse_rss_items(xml_text: str) -> list[dict]:
    stripped = xml_text.lstrip("\ufeff").strip()
    if not stripped or stripped[0] != "<":
        raise ParseError("body is not XML")
    try:
        root = ET.fromstring(stripped)
    except ET.ParseError as exc:
        raise ParseError(f"XML parse error: {exc}") from exc
    if local_name(root.tag).lower() != "rss":
        raise ParseError(f"root is {local_name(root.tag)}, expected rss")
    channel = next((child for child in list(root) if local_name(child.tag) == "channel"), None)
    if channel is None:
        raise ParseError("rss channel is missing")
    items = []
    for node in list(channel):
        if local_name(node.tag) != "item":
            continue
        categories = [
            " ".join(child.text.split())
            for child in list(node)
            if local_name(child.tag) == "category" and child.text
        ]
        items.append(
            {
                "title": child_text(node, "title") or "",
                "link": child_text(node, "link") or "",
                "description": child_text(node, "description"),
                "pub_date": child_text(node, "pubDate"),
                "guid": child_text(node, "guid"),
                "author": child_text(node, "author"),
                "categories": categories,
            }
        )
    return items


def parse_http_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def external_id_from_url(url: str, *patterns: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"url:{digest}"


def apply_budget(listing: RawListing, *parts: str | None) -> None:
    budget = parse_budget(*parts)
    listing.budget_kind = budget.kind
    listing.budget_min = budget.minimum
    listing.budget_max = budget.maximum
    listing.budget_currency = budget.currency
    listing.budget_text = budget.text
