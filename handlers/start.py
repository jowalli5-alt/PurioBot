"""
/start, обработка реферальной ссылки, главное меню.
"""
from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext

import database as db
import keyboards as kb
from middlewares import is_subscribed
from config import CHANNEL_USERNAME

router = Router()

WELCOME_TEXT = (
    "👋 Добро пожаловать в <b>PurioVPN</b>!\n\n"
    "Быстрый и надёжный VPN. Выбирай раздел ниже 👇 mellivora"
)


def _parse_referrer(command: CommandObject) -> int | None:
    if not command.args:
        return None
    arg = command.args.strip()
    if arg.startswith("ref_"):
        try:
            return int(arg.removeprefix("ref_"))
        except ValueError:
            return None
    return None


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    # Примечание: если пользователь ещё не подписан на канал, до этого хендлера
    # дело не дойдёт — его перехватит SubscriptionCheckMiddleware и сам сохранит
    # referrer_id (см. middlewares.py: _extract_pending_referrer), поэтому здесь
    # достаточно обработать только "уже подписан" сценарий.
    user = message.from_user
    referrer_id = _parse_referrer(command)

    db_user, is_new = await db.get_or_create_user(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name or "",
        referrer_id=referrer_id,
    )

    await db.add_log(
        user.id, "start",
        details=f"new={is_new} referrer={referrer_id if is_new else db_user['referrer_id']}"
    )

    await message.answer(WELCOME_TEXT, reply_markup=kb.main_menu_kb(user.id))


@router.callback_query(F.data == "check_subscription")
async def cb_check_subscription(callback: CallbackQuery, state: FSMContext):
    subscribed = await is_subscribed(callback.bot, callback.from_user.id)
    if not subscribed:
        await callback.answer("Ты ещё не подписался 🙁", show_alert=True)
        return

    user = callback.from_user
    data = await state.get_data()
    referrer_id = data.get("pending_referrer")

    db_user, is_new = await db.get_or_create_user(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name or "",
        referrer_id=referrer_id,
    )
    if "pending_referrer" in data:
        await state.update_data(pending_referrer=None)

    await db.add_log(
        user.id, "channel_subscribed_confirmed",
        details=f"new={is_new} referrer={referrer_id if is_new else db_user['referrer_id']}",
    )
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=kb.main_menu_kb(user.id))
    await callback.answer()


@router.callback_query(F.data == "back_to_menu")
async def cb_back_to_menu(callback: CallbackQuery):
    try:
        await callback.message.edit_text(WELCOME_TEXT, reply_markup=kb.main_menu_kb(callback.from_user.id))
    except TelegramBadRequest:
        pass
    await callback.answer()
