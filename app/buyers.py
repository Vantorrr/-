import re


def gather_text(listing) -> str:
    parts = [listing.title or "", listing.description or "", listing.category or ""]
    return " ".join(part for part in parts if part)


def classify_buyer(text: str, name: str | None, preset: str, evidence: str | None = None) -> tuple[str | None, str, str | None]:
    if preset in {"legal_entity", "individual"}:
        return name, preset, evidence
    quoted = re.search(r"(ООО|ПАО|АО|ЗАО|ОАО)\s*[«\"]([^»\"]{2,80})[»\"]", text)
    if quoted and not name:
        name = f"{quoted.group(1)} «{quoted.group(2).strip()}»"
        return name, "legal_entity", "text:legal_name"
    if re.search(r"безналич|эдо|юридическ|госзаказчик|44-фз|223-фз|\bооо\b|\bпао\b", text, re.IGNORECASE):
        return name, "legal_entity", "text:business_terms"
    if re.search(r"частн\w*\s+лиц|физлиц|самозанят", text, re.IGNORECASE):
        return name, "individual", "text:individual"
    return name, "unknown", evidence


def classify_remote(text: str, preset: bool | None) -> bool | None:
    lowered = text.lower().replace("ё", "е")
    remote = bool(re.search(r"удален|remote|дистанцион|из любой точки", lowered))
    office = bool(re.search(r"только в офис|в офисе заказчик|на территории заказчик|очный формат", lowered))
    if remote and not office:
        return True
    if office and not remote:
        return False
    return preset
