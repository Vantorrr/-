from decimal import Decimal
from types import SimpleNamespace

import yaml

from app.scoring import load_check, score_listing
from app.settings import ROOT


def cfg():
    data = yaml.safe_load((ROOT / "config" / "scoring.yaml").read_text(encoding="utf-8"))
    load_check(data)
    return data


def listing(**kwargs):
    base = dict(
        title="",
        description="",
        category="",
        budget_kind="unknown",
        budget_min=None,
        budget_max=None,
        budget_currency=None,
        buyer_type="unknown",
        remote=None,
        status_text="open",
        lead_kind="order",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_weights_sum_to_100():
    load_check(cfg())


def test_preferred_budget_scores_high_and_keeps_components():
    row = listing(
        title="Разработка интернет-магазина на React и Python",
        description=(
            "Нужно разработать интернет-магазин: каталог, корзина, личный кабинет и интеграция оплаты. "
            "Стек React и Python, работа удалённо по договору с ООО «Север»."
        ),
        budget_kind="exact",
        budget_min=Decimal("800000"),
        budget_max=Decimal("800000"),
        budget_currency="RUB",
        buyer_type="legal_entity",
        remote=True,
    )
    result = score_listing(row, cfg())
    assert result.excluded is False
    assert result.score == 100
    assert result.breakdown["budget"] == 25
    assert result.breakdown["tech"] == 20


def test_unknown_budget_is_not_invented():
    row = listing(
        title="Интеграция Битрикс 24 с 1С для отдела продаж",
        description="Нужно интегрировать Битрикс 24 и 1С: контакты, счета и статусы оплат. Формат пока не описан.",
        remote=None,
        buyer_type="unknown",
    )
    result = score_listing(row, cfg())
    assert result.breakdown["budget_detail"]["band"] == "unknown"
    assert result.breakdown["remote_band"] == "unknown"
    assert "нереалистичный бюджет" not in result.reasons


def test_vague_completed_unrealistic_unpaid_and_middleman_are_excluded():
    rules = cfg()
    vague = score_listing(listing(title="Инфо", description="Срочно"), rules)
    assert vague.score == 0
    assert "размытая задача" in vague.reasons

    closed = score_listing(
        listing(
            title="Разработка сайта компании на React",
            description="Нужно разработать сайт компании с каталогом услуг и формой заявки для отдела продаж.",
            status_text="closed",
        ),
        rules,
    )
    assert "завершён" in closed.reasons

    tiny_shop = score_listing(
        listing(
            title="Интернет-магазин под ключ",
            description="Нужно разработать интернет-магазин под ключ с каталогом и оплатой.",
            budget_kind="exact",
            budget_min=Decimal("5000"),
            budget_max=Decimal("5000"),
            budget_currency="RUB",
        ),
        rules,
    )
    assert "нереалистичный бюджет" in tiny_shop.reasons

    unpaid = score_listing(
        listing(
            title="Тестовое задание",
            description="Тестовое задание бесплатно: сверстать одну страницу.",
        ),
        rules,
    )
    assert "неоплачиваемое тестовое" in unpaid.reasons

    middleman = score_listing(
        listing(
            title="Перевод предоплаты",
            description="Сначала предоплата на карту посреднику, потом обсудим задачу по сайту и интеграции.",
        ),
        rules,
    )
    assert "предоплата посреднику" in middleman.reasons


def test_safe_deal_is_not_a_middleman_exclusion():
    result = score_listing(
        listing(
            title="Доработка сайта на Python",
            description="Нужно доработать сайт на Python, оплата через безопасную сделку площадки, бюджет обсудим.",
        ),
        cfg(),
    )
    assert "предоплата посреднику" not in result.reasons


def test_foreign_currency_band_uses_configured_rate_without_replacing_amount():
    result = score_listing(
        listing(
            title="Разработка сервиса на Python и React",
            description="Нужно разработать веб-сервис на Python и React с личным кабинетом и оплатой.",
            budget_kind="exact",
            budget_min=Decimal("6000"),
            budget_max=Decimal("6000"),
            budget_currency="USD",
            buyer_type="legal_entity",
            remote=True,
        ),
        cfg(),
    )
    assert result.breakdown["budget_detail"]["fx"] == "USD->90 RUB"
    assert result.breakdown["budget"] == 25
