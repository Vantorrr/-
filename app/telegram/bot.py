import asyncio
import time

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bootstrap import prepare_storage
from app.db import session_scope
from app.display import format_budget
from app.logging_setup import configure_logging, get_logger
from app.models import Listing
from app.queries import list_listings
from app.runtime import set_paused
from app.settings import get_settings

log = get_logger("telegram_bot")
router = Router()


def _allowed(message: Message) -> bool:
    chat_id = get_settings().telegram_chat_id
    return bool(chat_id) and str(message.chat.id) == str(chat_id)


@router.message(Command("orders"))
async def orders(message: Message) -> None:
    if not _allowed(message):
        return
    with session_scope() as session:
        rows = list_listings(session, status="awaiting_approval", limit=10)
        if not rows:
            await message.answer("Нет карточек в статусе awaiting_approval.")
            return
        lines = ["Ждут подтверждения. Сами заявки не отправляются.", ""]
        for row in rows:
            lines.append(f"{row.score}/100 {row.source_id}: {row.title}")
            lines.append(format_budget(row))
            lines.append(row.url)
            lines.append("")
        await message.answer("\n".join(lines)[:3900])


@router.message(Command("top"))
async def top(message: Message) -> None:
    if not _allowed(message):
        return
    with session_scope() as session:
        rows = (
            session.query(Listing)
            .filter(Listing.fit.is_(True))
            .order_by(Listing.score.desc())
            .limit(5)
            .all()
        )
        if not rows:
            await message.answer("Подходящих карточек пока нет.")
            return
        lines = [f"{row.score}/100 {row.title}\n{row.url}" for row in rows]
        await message.answer("\n\n".join(lines)[:3900])


@router.message(Command("pause"))
async def pause(message: Message) -> None:
    if not _allowed(message):
        return
    if set_paused(True):
        await message.answer("Сбор поставлен на паузу. Новые прогоны по расписанию пропускаются.")
        return
    await message.answer("Пауза не записана: Redis недоступен.")


@router.message(Command("resume"))
async def resume(message: Message) -> None:
    if not _allowed(message):
        return
    if set_paused(False):
        await message.answer("Пауза снята.")
        return
    await message.answer("Пауза не снята: Redis недоступен.")


async def _poll() -> None:
    settings = get_settings()
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot)


def main() -> None:
    configure_logging()
    settings = get_settings()
    if not settings.telegram_bot_token:
        log.info("telegram_bot_disabled", reason="TELEGRAM_BOT_TOKEN unset")
        while True:
            time.sleep(3600)
    prepare_storage()
    log.info("telegram_bot_starting", chat_configured=bool(settings.telegram_chat_id))
    asyncio.run(_poll())


if __name__ == "__main__":
    main()
