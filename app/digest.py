from app.display import buyer_type_label, format_budget, remote_label, unknown


def format_listing_block(listing, index: int) -> str:
    lines = [
        f"{index}. {listing.score}/100 — {listing.source_id}",
        f"Название: {listing.title}",
        f"Заказчик: {unknown(listing.buyer_name)} ({buyer_type_label(listing.buyer_type)})",
        f"Бюджет: {format_budget(listing)}",
        f"Формат: {remote_label(listing.remote)}",
        f"Город: {unknown(listing.location)}",
        f"Ссылка: {listing.url}",
    ]
    if listing.proposal_text:
        lines.append("Черновик:")
        lines.append(listing.proposal_text)
    return "\n".join(lines)


def format_digest(
    *,
    run_id: str,
    started_at: str,
    source_rows: list[dict],
    listings: list,
    delivery_note: str,
    total_fit: int | None = None,
) -> str:
    lines = [
        "Qora Group — подборка к подтверждению",
        "Режим отправки: подтверждение. Заявки на площадки не отправлялись.",
        f"Прогон: {run_id}",
        f"Старт: {started_at}",
        "",
        "Источники:",
    ]
    for row in source_rows:
        if row.get("skipped"):
            lines.append(f"- {row['id']}: вручную, не опрашивался")
            continue
        if row.get("error"):
            lines.append(f"- {row['id']}: ошибка, карточек 0 ({row['error']})")
            continue
        warning = f"; предупреждение: {row['warning']}" if row.get("warning") else ""
        lines.append(f"- {row['id']}: получено {row.get('fetched', 0)}{warning}")
    lines.append("")
    if not listings:
        lines.append("Подходящих новых карточек нет.")
    else:
        total = total_fit if total_fit is not None else len(listings)
        lines.append(f"Подходящие, ждут решения: {total}")
        if total > len(listings):
            lines.append(f"В тексте первые {len(listings)} по баллу. Остальные лежат в базе.")
        lines.append("")
        for index, listing in enumerate(listings, start=1):
            lines.append(format_listing_block(listing, index))
            lines.append("")
    lines.append(delivery_note)
    return "\n".join(lines).strip() + "\n"


def split_text(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    rest = text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        cut = rest.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    return chunks
