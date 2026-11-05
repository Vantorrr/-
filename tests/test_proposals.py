from types import SimpleNamespace

import yaml

from app.proposals import CLICHES, draft_proposal
from app.settings import ROOT


def profile_file():
    return yaml.safe_load((ROOT / "config" / "company_profile.yaml").read_text(encoding="utf-8"))


def test_profile_file_starts_empty():
    data = profile_file()
    assert data["display_name"] == ""
    assert data["legal_name"] == ""
    assert data["services"] == []
    assert data["cases"] == []
    assert data["certificates"] == []
    assert data["team_size"] is None
    assert data["email"] == ""
    assert data["telegram"] == ""


def test_empty_profile_does_not_invent_company_facts():
    listing = SimpleNamespace(
        title="Разработка интернет-магазина на React",
        description="Нужно разработать интернет-магазин с каталогом и оплатой картой.",
        category="Сайты",
        lead_kind="order",
        budget_kind="unknown",
        remote=None,
    )
    text = draft_proposal(listing, profile_file(), max_chars=900)
    lowered = text.lower()
    assert "ооо" not in lowered
    assert "сертифик" not in lowered
    assert "кейс" not in lowered
    assert "наша команда" not in lowered
    for cliche in CLICHES:
        assert cliche not in lowered
    assert "бюджет" in lowered
    assert "удалённо или в офисе" in lowered


def test_filled_profile_uses_only_matching_facts():
    listing = SimpleNamespace(
        title="Интеграция CRM и платёжного API",
        description="Нужно интегрировать CRM и платёжный API для интернет-магазина.",
        category="",
        lead_kind="tender",
        budget_kind="exact",
        remote=True,
    )
    profile = {
        "display_name": "Qora Group",
        "legal_name": "ООО «Пример»",
        "services": ["Интеграции CRM и API", "3D и WebGL"],
        "cases": [{"title": "Внедрение CRM для сети", "summary": "CRM", "url": "https://example.test/crm"}],
        "certificates": [],
        "team_size": None,
        "email": "",
        "telegram": "",
    }
    text = draft_proposal(listing, profile, max_chars=900)
    assert "Qora Group" in text
    assert "ООО «Пример»" in text
    assert "Интеграции CRM и API" in text
    assert "WebGL" not in text
    assert "Внедрение CRM для сети" in text


def test_profi_draft_stays_within_500_chars():
    listing = SimpleNamespace(
        title="Нужен сайт",
        description="Нужно " + ("подробно описать задачу и согласовать состав работ " * 30),
        category="",
        lead_kind="order",
        budget_kind="unknown",
        remote=None,
    )
    text = draft_proposal(listing, profile_file(), max_chars=500)
    assert len(text) <= 500
