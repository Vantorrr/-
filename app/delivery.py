from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.digest import split_text
from app.logging_setup import get_logger

log = get_logger("delivery")


@dataclass
class DeliveryResult:
    status: str
    local_path: str | None = None
    telegram_message_ids: list[int] = field(default_factory=list)
    error: str | None = None


def write_local(body: str, data_dir: str) -> Path:
    folder = Path(data_dir) / "digests"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = folder / f"{stamp}.txt"
    path.write_text(body, encoding="utf-8")
    return path


def deliver_digest(
    body: str,
    *,
    token: str,
    chat_id: str,
    data_dir: str,
    post=httpx.post,
) -> DeliveryResult:
    path = write_local(body, data_dir)
    if not token or not chat_id:
        log.info("telegram_skipped", reason="credentials_unset", path=str(path))
        return DeliveryResult(status="skipped_no_credentials", local_path=str(path))
    message_ids = []
    for chunk in split_text(body):
        try:
            response = post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
                timeout=20,
            )
        except httpx.HTTPError as exc:
            log.warning("telegram_failed", error=str(exc))
            return DeliveryResult(
                status="failed",
                local_path=str(path),
                telegram_message_ids=message_ids,
                error=str(exc),
            )
        if response.status_code != 200:
            return DeliveryResult(
                status="failed",
                local_path=str(path),
                telegram_message_ids=message_ids,
                error=f"HTTP {response.status_code}",
            )
        payload = response.json()
        if not payload.get("ok") or "result" not in payload:
            return DeliveryResult(
                status="failed",
                local_path=str(path),
                telegram_message_ids=message_ids,
                error="telegram response was not ok",
            )
        message_ids.append(int(payload["result"]["message_id"]))
    log.info("telegram_sent", messages=len(message_ids))
    return DeliveryResult(status="sent", local_path=str(path), telegram_message_ids=message_ids)
