import io
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from app.backup import run_backup
from app.crm import apply_transition
from app.crm_ops import EXPORT_HEADERS, add_expense, render_csv, render_xlsx, set_due, status_funnel
from app.daily import run_daily_digest
from app.db import session_scope
from app.models import Listing, Reminder, StatusEvent
from app.settings import get_settings
from app.telegram.actions import approve_send

LISTING_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _listing(listing_id: str, **overrides) -> Listing:
    now = datetime(2026, 11, 5, 12, 0, 0)
    values = dict(
        id=listing_id,
        source_id="fl_ru",
        external_id=listing_id[-4:],
        url=f"https://www.fl.ru/projects/{listing_id[-4:]}/a.html",
        title="Каталог для мастерской",
        description="Нужен каталог.",
        lead_kind="order",
        budget_kind="unknown",
        buyer_type="unknown",
        status_text="open",
        status="awaiting_approval",
        score=80,
        fit=True,
        fingerprint=listing_id,
        proposal_origin="template",
        fetched_at=now,
        updated_at=now,
        last_seen_at=now,
    )
    values.update(overrides)
    return Listing(**values)


def test_csv_export_follows_the_filter_and_invents_nothing(memory_db):
    with session_scope() as session:
        first = _listing(LISTING_ID, status=None)
        second = _listing(
            OTHER_ID,
            source_id="habr_career",
            title="Вакансия без отправки",
            url="https://career.habr.com/vacancies/2",
            score=40,
            status="rejected",
            fit=False,
        )
        session.add(first)
        session.add(second)
        session.flush()
        for status in ("found", "checked", "proposal_ready", "awaiting_approval"):
            apply_transition(first, status, session, actor="system")
        add_expense(session, LISTING_ID, amount="1500", currency="RUB", note="хостинг", spent_on="2026-11-01")
        set_due(session, LISTING_ID, "2026-12-01")
        assert first.status == "awaiting_approval"
        text = render_csv(session, status="awaiting_approval", min_score=None, source_id="fl_ru", limit=100)
        funnel = status_funnel(session)
        empty = render_csv(session, status="won", min_score=None, source_id=None, limit=100)
    body = text.lstrip("\ufeff")
    lines = [line for line in body.splitlines() if line]
    assert lines[0].startswith("Идентификатор,Название")
    assert len(lines) == 2
    assert "Каталог для мастерской" in body
    assert "Вакансия без отправки" not in body
    assert "1500 RUB" in body
    assert "01.12.2026" in body
    assert "ООО Ромашка" not in body
    assert funnel["current"]["awaiting_approval"] == 1
    assert funnel["current"]["rejected"] == 1
    assert funnel["reached"]["awaiting_approval"] == 1
    assert funnel["current"]["won"] == 0
    empty_lines = [line for line in empty.lstrip("\ufeff").splitlines() if line]
    assert empty_lines == ["Идентификатор,Название,Источник,Статус,Балл,Бюджет,Срок,Расходы,Ссылка"]


def test_xlsx_export_one_row_of_the_current_filter(memory_db):
    with session_scope() as session:
        session.add(_listing(LISTING_ID, title="Каталог для мастерской"))
        session.add(
            _listing(
                OTHER_ID,
                source_id="habr_career",
                title="Вакансия без отправки",
                url="https://career.habr.com/vacancies/2",
                score=40,
                status="rejected",
                fit=False,
            )
        )
        payload = render_xlsx(session, status="awaiting_approval", min_score=None, source_id="fl_ru", limit=100)
    book = load_workbook(io.BytesIO(payload))
    sheet = book.active
    assert [cell.value for cell in sheet[1]] == EXPORT_HEADERS
    assert sheet.max_row == 2
    assert sheet["B2"].value == "Каталог для мастерской"
    assert sheet["D2"].value == "ждёт подтверждения"
    values = [value for row in sheet.iter_rows(values_only=True) for value in row]
    assert "Вакансия без отправки" not in values
    assert "ООО Ромашка" not in values


def test_approve_without_adapter_stays_unsent(memory_db):
    with session_scope() as session:
        session.add(_listing(LISTING_ID))
    with session_scope() as session:
        result = approve_send(session, LISTING_ID)
        row = session.get(Listing, LISTING_ID)
        assert result.sent is False
        assert row.status == "awaiting_approval"
        assert session.query(StatusEvent).filter(StatusEvent.to_status == "sent").count() == 0


def test_daily_digest_without_credentials_is_local(memory_db, tmp_path, monkeypatch):
    monkeypatch.setattr("app.daily.is_paused", lambda: False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    get_settings.cache_clear()
    with session_scope() as session:
        session.add(_listing(LISTING_ID))
        session.add(
            Reminder(
                id="cccccccc-cccc-cccc-cccc-cccccccccccc",
                listing_id=LISTING_ID,
                title="Позвонить по каталогу",
                due_at=None,
                done=False,
                created_at=datetime(2026, 11, 5, 12, 0, 0),
            )
        )
    result = run_daily_digest()
    assert result["status"] == "skipped_no_credentials"
    text = Path(result["path"]).read_text(encoding="utf-8")
    assert "не отправлялся" in text
    assert "Каталог для мастерской" in text
    assert "Позвонить по каталогу" in text
    assert "срок: неизвестно" in text
    assert "ООО Ромашка" not in text
    get_settings.cache_clear()


def test_daily_digest_includes_due_tasks_and_stays_unsent(memory_db, tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr("app.daily.is_paused", lambda: False)
    monkeypatch.setattr("app.daily.log.info", lambda event, **kwargs: events.append(event))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    get_settings.cache_clear()
    with session_scope() as session:
        session.add(_listing(LISTING_ID))
        session.add(
            Reminder(
                id="dddddddd-dddd-dddd-dddd-dddddddddddd",
                listing_id=LISTING_ID,
                title="Срок по каталогу уже прошёл",
                due_at=datetime(2026, 11, 1, 8, 0, 0),
                done=False,
                created_at=datetime(2026, 11, 1, 8, 0, 0),
            )
        )
    result = run_daily_digest()
    assert result["status"] == "skipped_no_credentials"
    assert "skipped_no_credentials" in events
    text = Path(result["path"]).read_text(encoding="utf-8")
    assert "Задачи к сроку:" in text
    assert "Срок по каталогу уже прошёл" in text
    assert "2026-11-01T08:00:00Z" in text
    assert "не отправлялся" in text
    with session_scope() as session:
        row = session.get(Listing, LISTING_ID)
        assert row.status == "awaiting_approval"
        assert session.query(StatusEvent).filter(StatusEvent.to_status == "sent").count() == 0
    get_settings.cache_clear()


def test_daily_digest_honors_pause(memory_db, tmp_path, monkeypatch):
    monkeypatch.setattr("app.daily.is_paused", lambda: True)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    result = run_daily_digest()
    assert result["status"] == "paused"
    assert list(tmp_path.rglob("*")) == []
    get_settings.cache_clear()


def test_backup_on_sqlite_does_not_write_a_dump(tmp_path):
    code = run_backup("sqlite:////tmp/intake.sqlite", tmp_path)
    assert code == 2
    assert list(tmp_path.iterdir()) == []


def test_backup_command_keeps_the_password_out_of_argv(tmp_path):
    seen = {}

    def runner(args, env, check):
        seen["args"] = args
        seen["env"] = env
        seen["check"] = check

        class Done:
            returncode = 0

        return Done()

    code = run_backup(
        "postgresql+psycopg://intake:s3cret@postgres:5432/intake",
        tmp_path,
        runner=runner,
    )
    assert code == 0
    assert seen["args"][0] == "pg_dump"
    assert "s3cret" not in seen["args"]
    assert seen["env"]["PGPASSWORD"] == "s3cret"
    assert seen["args"][seen["args"].index("-d") + 1] == "intake"
    assert seen["check"] is False
