from datetime import datetime
from decimal import Decimal

import yaml

from app.crm import TransitionError, apply_transition
from app.db import session_scope
from app.delivery import DeliveryResult, deliver_digest
from app.models import DigestRecord, Listing, StatusEvent
from app.pipeline import run_once
from app.settings import ROOT
from app.sources.base import FetchResult, RawListing
from app.sources.registry import build_sources, load_source_specs


REQUIRED_SOURCES = {
    "profi_ru",
    "fl_ru",
    "freelance_ru",
    "kwork",
    "habr_career",
    "workspace",
    "b2b_center",
    "rts_tender",
    "kontur_zakupki",
    "eis_zakupki",
    "avito_services",
    "telegram_channels",
    "agency_subcontract",
    "company_rfp",
}


class FakeSource:
    def __init__(self):
        self.id = "fl_ru"
        self.proposal_max_chars = 900

    def fetch(self, client):
        good = _order(
            "100",
            "Разработка корпоративного портала на React и Python для отдела продаж",
            "Нужно разработать корпоративный портал на React и Python: каталог, роли и интеграция оплаты. "
            "Работа удалённо, договор с ООО «Север».",
            budget=("exact", Decimal("800000"), Decimal("800000")),
        )
        duplicate = _order(
            "101",
            good.title,
            good.description,
            budget=("exact", Decimal("800000"), Decimal("800000")),
            url="https://www.fl.ru/projects/101/copy.html",
        )
        vague = _order("102", "Инфо", "Срочно")
        return FetchResult(source_id=self.id, listings=[good, duplicate, vague])


def _order(external_id, title, description, budget=("unknown", None, None), url=None):
    kind, low, high = budget
    return RawListing(
        source_id="fl_ru",
        external_id=external_id,
        url=url or f"https://www.fl.ru/projects/{external_id}/item.html",
        title=title,
        description=description,
        lead_kind="order",
        remote=True,
        budget_kind=kind,
        budget_min=low,
        budget_max=high,
        budget_currency="RUB" if kind != "unknown" else None,
        published_at=datetime(2026, 11, 1, 9, 0, 0),
        status_text="open",
    )


def test_registry_covers_named_sources_and_keeps_manual_disabled():
    specs = load_source_specs(ROOT / "config" / "sources.yaml")
    by_id = {item["id"]: item for item in specs}
    assert REQUIRED_SOURCES <= set(by_id)
    enabled = {item["id"] for item in specs if item.get("enabled")}
    assert enabled == {"fl_ru", "habr_career", "workspace", "eis_zakupki"}
    sources = build_sources(specs)
    manual = [source for source in sources if source.__class__.__name__ == "ManualSource"]
    assert {source.id for source in manual} == REQUIRED_SOURCES - enabled
    with __import__("pytest").raises(ValueError):
        build_sources([{"id": "x", "kind": "scrape", "enabled": True}])


def test_run_once_dedups_scores_and_does_not_fake_telegram(memory_db, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "telegram_bot_token", "", raising=False)
    monkeypatch.setattr(settings, "telegram_chat_id", "", raising=False)
    scoring = yaml.safe_load((ROOT / "config" / "scoring.yaml").read_text(encoding="utf-8"))
    profile = yaml.safe_load((ROOT / "config" / "company_profile.yaml").read_text(encoding="utf-8"))
    calls = []

    def deliver(body, **kwargs):
        calls.append(body)
        assert "message_id" not in body
        return DeliveryResult(status="skipped_no_credentials", local_path=None)

    result = run_once(sources=[FakeSource()], profile=profile, scoring=scoring, deliver=deliver)
    assert result["status"] == "ok"
    assert result["new"] == 3
    assert result["duplicates"] == 1
    assert result["fit"] == 1
    assert result["digest_status"] == "skipped_no_credentials"
    assert calls
    with session_scope() as session:
        rows = session.query(Listing).all()
        by_ext = {row.external_id: row for row in rows}
        assert by_ext["100"].status == "awaiting_approval"
        assert by_ext["100"].proposal_text
        assert "Договор можем оформить" not in by_ext["100"].proposal_text
        assert "Qora Group" not in by_ext["100"].proposal_text
        assert by_ext["101"].exclusion_reasons == ["дубликат"]
        assert by_ext["101"].score == 0
        assert by_ext["101"].status == "checked"
        assert "размытая задача" in by_ext["102"].exclusion_reasons
        digest = session.query(DigestRecord).one()
        assert digest.delivery_status == "skipped_no_credentials"
        assert "не отправлялся" in digest.body


def test_sent_requires_confirmed_api_result(memory_db):
    with session_scope() as session:
        row = Listing(
            id="1",
            source_id="fl_ru",
            external_id="1",
            url="https://www.fl.ru/projects/1/a.html",
            title="Задача",
            lead_kind="order",
            budget_kind="unknown",
            buyer_type="unknown",
            status_text="open",
            status=None,
            score=0,
            fit=False,
            fingerprint="abc",
            fetched_at=datetime(2026, 11, 5),
            updated_at=datetime(2026, 11, 5),
            last_seen_at=datetime(2026, 11, 5),
        )
        session.add(row)
        session.flush()
        for status in ("found", "checked", "proposal_ready", "awaiting_approval"):
            apply_transition(row, status, session, actor="system")
        try:
            apply_transition(row, "sent", session, actor="operator")
            raised = False
        except TransitionError:
            raised = True
        assert raised
        assert row.status == "awaiting_approval"
        apply_transition(
            row,
            "sent",
            session,
            actor="operator",
            confirmation={"ok": True, "external_result_id": "msg-9", "provider": "manual"},
        )
        assert row.status == "sent"
        notes = session.query(StatusEvent).filter(StatusEvent.to_status == "sent").one()
        assert "msg-9" in (notes.note or "")


def test_deliver_without_credentials_does_not_call_telegram(tmp_path):
    def explode(*args, **kwargs):
        raise AssertionError("telegram was called")

    result = deliver_digest(
        "черновик",
        token="",
        chat_id="",
        data_dir=str(tmp_path),
        post=explode,
    )
    assert result.status == "skipped_no_credentials"
    assert result.local_path
    assert "черновик" in open(result.local_path, encoding="utf-8").read()
