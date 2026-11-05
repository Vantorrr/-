from datetime import datetime
from types import SimpleNamespace

import pytest
import yaml

from app.db import init_db, session_scope
from app.logging_setup import configure_logging
from app.llm import draft_for_listing
from app.models import Listing, StatusEvent
from app.settings import ROOT, get_settings
from app.submit import SubmitResult
from app.telegram.actions import add_to_crm, apply_pending_edit, approve_send, begin_edit, reject_listing
from app.telegram.bot import main
from app.telegram.cards import HELP_TEXT, order_actions, order_card

LISTING_ID = "11111111-1111-1111-1111-111111111111"


def _listing(**overrides) -> Listing:
    now = datetime(2026, 11, 5, 12, 0, 0)
    values = dict(
        id=LISTING_ID,
        source_id="fl_ru",
        external_id="ext-1",
        url="https://www.fl.ru/projects/1/a.html",
        title="Сайт каталога",
        description="Нужен каталог товаров на React.",
        lead_kind="order",
        budget_kind="range",
        budget_min=150000,
        budget_max=300000,
        budget_currency="RUB",
        buyer_type="unknown",
        status_text="open",
        status="awaiting_approval",
        score=72,
        fit=True,
        fingerprint="fp",
        proposal_text="Здравствуйте. По задаче готовы работать по тексту объявления.",
        proposal_chars=58,
        proposal_origin="template",
        fetched_at=now,
        updated_at=now,
        last_seen_at=now,
    )
    values.update(overrides)
    return Listing(**values)


def _sample():
    return SimpleNamespace(
        id=LISTING_ID,
        source_id="fl_ru",
        url="https://www.fl.ru/projects/1/a.html",
        title="Сайт каталога",
        description="Нужен каталог товаров на React.",
        lead_kind="order",
        budget_kind="unknown",
        budget_currency=None,
        budget_min=None,
        budget_max=None,
        score=72,
        proposal_text="Здравствуйте.",
        proposal_origin="template",
        proposed_price_text=None,
        category=None,
        remote=None,
        buyer_name=None,
    )


class ConfirmedAdapter:
    can_submit = True
    name = "fake"

    def submit(self, listing):
        return SubmitResult(ok=True, external_result_id="ext-42", detail="ok")


class MissingResultAdapter:
    can_submit = True
    name = "fake"

    def submit(self, listing):
        return SubmitResult(ok=True, external_result_id=None, detail="missing")


def test_reject_moves_awaiting_approval_to_rejected(memory_db):
    with session_scope() as session:
        session.add(_listing())
    with session_scope() as session:
        result = reject_listing(session, LISTING_ID)
        row = session.get(Listing, LISTING_ID)
        event = session.query(StatusEvent).one()
        assert result.sent is False
        assert result.status == "rejected"
        assert row.status == "rejected"
        assert event.from_status == "awaiting_approval"
        assert event.to_status == "rejected"
        assert session.query(StatusEvent).filter(StatusEvent.to_status == "sent").count() == 0


def test_approve_without_adapter_stays_unsent(memory_db):
    with session_scope() as session:
        session.add(_listing())
    with session_scope() as session:
        result = approve_send(session, LISTING_ID)
        row = session.get(Listing, LISTING_ID)
        assert result.sent is False
        assert result.status == "awaiting_approval"
        assert row.status == "awaiting_approval"
        assert session.query(StatusEvent).filter(StatusEvent.to_status == "sent").count() == 0
        assert "sent не поставлен" in result.message


def test_adapter_without_result_id_stays_unsent(memory_db):
    with session_scope() as session:
        session.add(_listing())
    with session_scope() as session:
        result = approve_send(session, LISTING_ID, adapter=MissingResultAdapter())
        row = session.get(Listing, LISTING_ID)
        assert result.sent is False
        assert row.status == "awaiting_approval"


def test_confirmed_adapter_result_marks_sent(memory_db):
    with session_scope() as session:
        session.add(_listing())
    with session_scope() as session:
        result = approve_send(session, LISTING_ID, adapter=ConfirmedAdapter())
        row = session.get(Listing, LISTING_ID)
        assert result.sent is True
        assert row.status == "sent"
        note = session.query(StatusEvent).filter(StatusEvent.to_status == "sent").one().note
        assert "ext-42" in (note or "")


def test_edit_and_crm_do_not_mark_sent(memory_db):
    with session_scope() as session:
        session.add(_listing())
    with session_scope() as session:
        begin_edit(session, "42", LISTING_ID)
        edited = apply_pending_edit(session, "42", "Новый текст оператора.")
        marked = add_to_crm(session, LISTING_ID)
        row = session.get(Listing, LISTING_ID)
        assert edited.sent is False
        assert marked.sent is False
        assert row.status == "awaiting_approval"
        assert row.proposal_origin == "operator"
        assert row.proposal_text == "Новый текст оператора."
        assert row.in_crm is True


def test_schema_ensure_is_idempotent(memory_db):
    init_db()
    init_db()
    with session_scope() as session:
        session.add(_listing())
        row = session.get(Listing, LISTING_ID)
        assert row.proposal_origin == "template"
        assert row.in_crm is False


def test_card_labels_template_and_unknown_price():
    card = order_card(_sample())
    assert "Черновик (шаблон, не ответ модели):" in card
    assert "Предлагаемая цена: неизвестно" in card
    labels = [item["text"] for row in order_actions(_sample()) for item in row]
    assert labels == ["Одобрить отправку", "Править", "Отклонить", "В CRM", "Открыть заказ"]
    data = next(item["data"] for row in order_actions(_sample()) for item in row if "data" in item)
    assert len(data.encode("utf-8")) <= 64


def test_help_lists_commands():
    for command in ("/start", "/orders", "/top", "/stats", "/replies", "/settings", "/pause", "/resume"):
        assert command in HELP_TEXT
    assert "подтверждение" in HELP_TEXT


def test_missing_llm_key_keeps_template_and_skips_provider():
    def poster(*args, **kwargs):
        raise AssertionError("provider was called")

    settings = SimpleNamespace(llm_api_key="", llm_base_url="", llm_model="")
    draft = draft_for_listing(_sample(), {}, max_chars=500, settings=settings, poster=poster)
    assert draft.origin == "template"
    assert draft.provider is None
    assert "Похожий заполненный кейс" not in draft.text
    assert "Договор можем оформить" not in draft.text


def test_unsafe_model_text_falls_back_to_template():
    def poster(settings, messages):
        assert "Не придумывай" in messages[0]["content"]
        return "Наш кейс: внедрили ERP для банка. Договор можем оформить на ООО Ромашка."

    settings = SimpleNamespace(
        llm_api_key="test-key",
        llm_base_url="http://127.0.0.1:9",
        llm_model="test-model",
        http_timeout_seconds=1,
    )
    draft = draft_for_listing(_sample(), {}, max_chars=500, settings=settings, poster=poster)
    assert draft.origin == "template"
    assert "Ромашка" not in draft.text
    assert "банк" not in draft.text.lower()


def test_profile_file_stays_empty():
    profile = yaml.safe_load((ROOT / "config" / "company_profile.yaml").read_text(encoding="utf-8"))
    assert profile["legal_name"] == ""
    assert profile["display_name"] == ""
    assert profile["cases"] == []
    assert profile["services"] == []
    assert profile["certificates"] == []
    assert profile["team_size"] is None


@pytest.fixture
def restore_logging():
    yield
    configure_logging()


def test_bot_exits_when_token_missing(monkeypatch, restore_logging, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    get_settings.cache_clear()
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "TELEGRAM_BOT_TOKEN unset" in captured.err
    assert "without sending messages" in captured.err
    get_settings.cache_clear()
