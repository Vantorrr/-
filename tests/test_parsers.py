from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.sources.eis import EisRssSource
from app.sources.fl_ru import FlRssSource
from app.sources.habr_career import HabrCareerSource
from app.sources.rss_common import ParseError, parse_rss_items
from app.sources.workspace import WorkspaceCatalogSource

FIXTURES = Path(__file__).parent / "fixtures"


def test_rss_rejects_html_page():
    with pytest.raises(ParseError):
        parse_rss_items("<html><title>login</title></html>")


def test_fl_recorded_fixture():
    source = FlRssSource({"id": "fl_ru", "feeds": []})
    rows = source.parse((FIXTURES / "fl_ru_recorded.xml").read_text(encoding="utf-8"), "programming")
    assert len(rows) == 2
    assert rows[0].external_id == "5528169"
    assert rows[0].url.startswith("https://www.fl.ru/projects/5528169/")
    assert rows[0].remote is True
    assert rows[0].budget_kind == "unknown"
    priced = rows[1]
    assert priced.external_id == "5527831"
    assert priced.budget_kind == "exact"
    assert priced.budget_min == Decimal("12000")
    assert priced.budget_currency == "RUB"
    assert "Бюджет" not in priced.title
    assert priced.published_at == datetime(2026, 11, 3, 9, 26, 8)


def test_habr_recorded_fixture():
    source = HabrCareerSource({"id": "habr_career", "feeds": []})
    rows = source.parse((FIXTURES / "habr_career_recorded.xml").read_text(encoding="utf-8"), "python")
    assert len(rows) == 1
    row = rows[0]
    assert row.external_id == "1000169471"
    assert row.lead_kind == "vacancy"
    assert row.buyer_name == "YCLIENTS"
    assert row.buyer_type == "legal_entity"
    assert row.location == "Москва"
    assert row.remote is False
    assert row.budget_kind == "unknown"


def test_workspace_recorded_card_and_detail():
    source = WorkspaceCatalogSource(
        {"id": "workspace", "catalog_url": "https://workspace.ru/tenders/", "fetch_details": False}
    )
    rows = source.parse_catalog((FIXTURES / "workspace_catalog_recorded.html").read_text(encoding="utf-8"))
    assert len(rows) == 1
    row = rows[0]
    assert row.external_id == "19105"
    assert row.status_text == "open"
    assert row.budget_kind == "cap"
    assert row.budget_max == Decimal("200000")
    assert row.published_at == datetime(2026, 11, 5)
    assert row.deadline == datetime(2026, 11, 15)
    assert row.url.startswith("https://workspace.ru/tenders/")
    source.merge_detail(row, (FIXTURES / "workspace_detail_recorded.html").read_text(encoding="utf-8"))
    assert "интернет-магазин" in (row.description or "")
    assert row.buyer_name is None


def test_eis_synthetic_fixture_is_labeled_and_parsed():
    text = (FIXTURES / "eis_rss_synthetic.xml").read_text(encoding="utf-8")
    assert "SYNTHETIC FIXTURE" in text
    source = EisRssSource({"id": "eis_zakupki", "feeds": []})
    rows = source.parse(text, "software-dev")
    assert len(rows) == 1
    row = rows[0]
    assert row.external_id == "0373100040126000001"
    assert row.buyer_type == "legal_entity"
    assert row.buyer_name.startswith("ГБУ")
    assert row.budget_min == Decimal("1500000.00")
    assert row.lead_kind == "tender"
