from decimal import Decimal

from app.dedup import canonical_url, titles_are_duplicates


def test_long_exact_title_is_duplicate():
    title = "Разработка корпоративного портала на React и Python"
    assert titles_are_duplicates(title, title)


def test_short_repeated_title_is_not_cross_duplicate():
    assert not titles_are_duplicates("Создание бота", "Создание бота")


def test_short_title_with_same_budget_can_match():
    assert titles_are_duplicates(
        "Нужен Python разработчик",
        "Нужен Python разработчик",
        Decimal("12000"),
        Decimal("12000"),
    )


def test_near_duplicate_long_titles():
    left = "Разработка корпоративного портала на React и Python для отдела"
    right = "Разработка корпоративного портала на React и Python для отдела продаж"
    assert titles_are_duplicates(left, right)


def test_different_long_titles_stay_distinct():
    assert not titles_are_duplicates(
        "Интеграция Битрикс 24 с учетной системой 1С",
        "Дизайн лендинга для частной клиники в Казани",
    )


def test_url_canonicalization_drops_query():
    assert canonical_url("https://www.FL.ru/projects/1/?utm=a") == "https://www.fl.ru/projects/1"
