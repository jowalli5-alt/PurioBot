"""
Middleware, который не даёт пользоваться ботом без подписки на канал.
Пропускает только callback "check_subscription" (кнопка "Я подписался"),
чтобы пользователь всегда мог перепроверить подписку.
"""
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from typing import Callable, Awaitable, Any
import logging

from config import CHANNEL_USERNAME
import keyboards as kb

logger = logging.getLogger(__name__)


async def is_subscribed(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status not in ("left", "kicked")
    except TelegramBadRequest as e:
        # Если бот не админ канала или канал недоступен — не блокируем пользователей,
        # но пишем в лог, чтобы админ заметил проблему.
        logger.warning(f"Не удалось проверить подписку на канал: {e}")
        return True
    except Exception as e:
        logger.warning(f"Ошибка проверки подписки: {e}")
        return True


def _extract_pending_referrer(text: str | None) -> int | None:
    """Достаёт ref_<id> из текста команды /start, если он там есть.
    Нужно, чтобы не терять реферала, когда пользователь ещё не подписан
    на канал и обработчик /start не вызывается (мидлварь блокирует раньше)."""
    if not text or not text.startswith("/start"):
        return None
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    arg = parts[1].strip()
    if arg.startswith("ref_"):
        try:
            return int(arg.removeprefix("ref_"))
        except ValueError:
            return None
    return None


class SubscriptionCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        bot = data.get("bot")

        if user is None or bot is None:
            return await handler(event, data)

        # Всегда пропускаем нажатие кнопки проверки подписки
        if isinstance(event, CallbackQuery) and event.data == "check_subscription":
            return await handler(event, data)

        subscribed = await is_subscribed(bot, user.id)
        if not subscribed:
            # Если это /start с реферальной ссылкой — запоминаем реферера в FSM,
            # чтобы не потерять его: сам обработчик /start сейчас не вызовется.
            state = data.get("state")
            if state is not None and isinstance(event, Message):
                referrer_id = _extract_pending_referrer(event.text)
                if referrer_id and referrer_id != user.id:
                    await state.update_data(pending_referrer=referrer_id)

            text = (
                "🔒 Чтобы пользоваться ботом, подпишись на наш канал:\n\n"
                "После подписки нажми кнопку «Я подписался»."
            )
            if isinstance(event, Message):
                await event.answer(text, reply_markup=kb.channel_subscribe_kb())
            elif isinstance(event, CallbackQuery):
                await event.answer("Сначала подпишись на канал 🔒", show_alert=True)
                try:
                    await event.message.edit_text(text, reply_markup=kb.channel_subscribe_kb())
                except TelegramBadRequest:
                    pass
            return  # обрываем цепочку, дальше хендлер не вызывается

        return await handler(event, data)
