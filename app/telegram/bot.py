import asyncio

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bootstrap import prepare_storage
from app.db import session_scope
from app.logging_setup import configure_logging, get_logger
from app.models import Listing
from app.pipeline import load_yaml
from app.queries import list_listings, reply_listings, top_listings
from app.runtime import is_paused, redis_client, set_paused
from app.settings import get_settings
from app.telegram.actions import (
    add_to_crm,
    apply_pending_edit,
    approve_send,
    begin_edit,
    reject_listing,
    settings_text,
    stats_text,
)
from app.telegram.cards import HELP_TEXT, order_actions, order_card

log = get_logger("telegram_bot")
router = Router()


def _allowed_chat(chat_id) -> bool:
    expected = (get_settings().telegram_chat_id or "").strip()
    return bool(expected) and chat_id is not None and str(chat_id) == expected


def _keyboard(listing) -> InlineKeyboardMarkup:
    rows = []
    for action_row in order_actions(listing):
        buttons = []
        for action in action_row:
            if action.get("url"):
                buttons.append(InlineKeyboardButton(text=action["text"], url=action["url"]))
            else:
                buttons.append(InlineKeyboardButton(text=action["text"], callback_data=action["data"]))
        rows.append(buttons)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_cards(message: Message, rows, header: str) -> None:
    await message.answer(header)
    for row in rows:
        text = order_card(row)
        if len(text) > 3900:
            text = text[:3899] + "…"
        await message.answer(text, reply_markup=_keyboard(row))


@router.message(Command("start"))
async def start(message: Message) -> None:
    if not _allowed_chat(message.chat.id):
        return
    await message.answer(HELP_TEXT)


@router.message(Command("orders"))
async def orders(message: Message) -> None:
    if not _allowed_chat(message.chat.id):
        return
    with session_scope() as session:
        rows = list_listings(session, status="awaiting_approval", limit=5)
    if not rows:
        await message.answer("Нет карточек в статусе «ждёт подтверждения».")
        return
    await _send_cards(message, rows, "Ждут подтверждения. Заявки сами не отправляются.")


@router.message(Command("top"))
async def top(message: Message) -> None:
    if not _allowed_chat(message.chat.id):
        return
    with session_scope() as session:
        rows = top_listings(session, limit=5)
    if not rows:
        await message.answer("Подходящих карточек пока нет.")
        return
    await _send_cards(message, rows, "Пять лучших по баллу. Заявки сами не отправляются.")


@router.message(Command("stats"))
async def stats(message: Message) -> None:
    if not _allowed_chat(message.chat.id):
        return
    with session_scope() as session:
        text = stats_text(session)
    await message.answer(text)


@router.message(Command("replies"))
async def replies(message: Message) -> None:
    if not _allowed_chat(message.chat.id):
        return
    with session_scope() as session:
        rows = reply_listings(session, limit=5)
    if not rows:
        await message.answer("Ответов заказчиков нет. Черновики, которые ещё не отправлялись, смотрите в /orders.")
        return
    await _send_cards(message, rows, "Ответы заказчиков. Это не новые отправки.")


@router.message(Command("settings"))
async def settings_cmd(message: Message) -> None:
    if not _allowed_chat(message.chat.id):
        return
    settings = get_settings()
    profile = load_yaml(settings.config_path / "company_profile.yaml")
    client = redis_client()
    text = settings_text(
        settings=settings,
        profile=profile,
        redis_up=client is not None,
        paused=is_paused() if client is not None else False,
    )
    await message.answer(text)


@router.message(Command("pause"))
async def pause(message: Message) -> None:
    if not _allowed_chat(message.chat.id):
        return
    if set_paused(True):
        await message.answer("Сбор поставлен на паузу. Новые прогоны по расписанию пропускаются.")
        return
    await message.answer("Пауза не записана: Redis недоступен.")


@router.message(Command("resume"))
async def resume(message: Message) -> None:
    if not _allowed_chat(message.chat.id):
        return
    if set_paused(False):
        await message.answer("Пауза снята.")
        return
    await message.answer("Пауза не снята: Redis недоступен.")


@router.callback_query(F.data)
async def on_button(query: CallbackQuery) -> None:
    message = query.message
    chat_id = message.chat.id if message is not None else None
    if not _allowed_chat(chat_id):
        await query.answer()
        return
    parsed = _parse_callback(query.data or "")
    if parsed is None:
        await query.answer("Неизвестная кнопка")
        return
    prefix, listing_id = parsed
    with session_scope() as session:
        if prefix == "ap":
            result = approve_send(session, listing_id)
        elif prefix == "rj":
            result = reject_listing(session, listing_id)
        elif prefix == "ed":
            result = begin_edit(session, str(chat_id), listing_id)
        elif prefix == "crm":
            result = add_to_crm(session, listing_id)
        else:
            listing = session.get(Listing, listing_id)
            if listing is None:
                result_message = "Карточка не найдена."
            else:
                result_message = f"Заказ: {listing.url}"
            await query.answer("Ссылка")
            if message is not None:
                await message.answer(result_message)
            return
    await query.answer("Не отправлено" if not result.sent else "Отправлено")
    if message is not None:
        await message.answer(result.message)


@router.message(F.text, ~F.text.startswith("/"))
async def on_text(message: Message) -> None:
    if not _allowed_chat(message.chat.id):
        return
    with session_scope() as session:
        result = apply_pending_edit(session, str(message.chat.id), message.text or "")
    if result is None:
        return
    await message.answer(result.message)


def _parse_callback(data: str) -> tuple[str, str] | None:
    if ":" not in data:
        return None
    prefix, listing_id = data.split(":", 1)
    if prefix not in {"ap", "ed", "rj", "crm", "op"} or not listing_id:
        return None
    return prefix, listing_id


async def _poll() -> None:
    settings = get_settings()
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot)


def main() -> None:
    configure_logging()
    settings = get_settings()
    if not (settings.telegram_bot_token or "").strip():
        log.info(
            "telegram_bot_disabled",
            reason="TELEGRAM_BOT_TOKEN unset; process exits without sending messages",
        )
        raise SystemExit(0)
    prepare_storage()
    log.info("telegram_bot_starting", chat_configured=bool(settings.telegram_chat_id))
    asyncio.run(_poll())


if __name__ == "__main__":
    main()
