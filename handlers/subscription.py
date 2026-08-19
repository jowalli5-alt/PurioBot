"""
Раздел "Подписка": статус текущей подписки, покупка/продление тарифов.
Оплата тарифа списывается с внутреннего баланса пользователя.
"""
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery

import database as db
import keyboards as kb
import remnawave_client
from config import TARIFFS, REFERRAL_BONUS_DAYS

logger = logging.getLogger(__name__)
router = Router()


def _format_expire(expire_ts: int) -> str:
    if not expire_ts or expire_ts < datetime.now().timestamp():
        return "❌ Подписка не активна"
    dt = datetime.fromtimestamp(expire_ts)
    return f"✅ Активна до {dt.strftime('%d.%m.%Y %H:%M')}"


@router.callback_query(F.data == "menu_subscription")
async def cb_subscription(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    status = _format_expire(user["subscription_expire"])

    text = (
        f"🔑 <b>Подписка</b>\n\n"
        f"Статус: {status}\n\n"
        f"Выбери тариф для покупки или продления:"
    )
    await callback.message.edit_text(text, reply_markup=kb.subscription_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("buy_"))
async def cb_buy_tariff(callback: CallbackQuery):
    days = int(callback.data.removeprefix("buy_"))
    price = TARIFFS.get(days)
    if price is None:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    user_id = callback.from_user.id
    user = await db.get_user(user_id)

    if user["balance"] < price:
        missing = price - user["balance"]
        await callback.answer(
            f"Недостаточно средств. Не хватает {missing:.0f}₽. Пополни баланс в профиле.",
            show_alert=True,
        )
        return

    await callback.answer("Оформляю подписку, подожди пару секунд⏳")

    try:
        subscription_url = await remnawave_client.provision_subscription(user_id, days)
    except Exception:
        logger.exception("Ошибка выдачи подписки через Remnawave")
        await callback.message.answer(
            "⚠️ Не получилось выдать подписку автоматически. "
            "Деньги не списаны, напиши в поддержку — разберёмся вручную."
        )
        return

    # списываем деньги и продлеваем локально только после успешного ответа Remnawave
    await db.update_balance(user_id, -price)
    new_expire = await db.extend_subscription(user_id, days)
    await db.add_log(user_id, "subscription_purchased", details=f"days={days} price={price}")

    # если это первая покупка подписки у реферала — начисляем бонусные дни пригласившему
    if user["referrer_id"] and user["subscription_expire"] == 0:
        await credit_referral_days(user["referrer_id"])

    dt = datetime.fromtimestamp(new_expire)
    await callback.message.edit_text(
        f"✅ Подписка оформлена до <b>{dt.strftime('%d.%m.%Y')}</b>!\n\n"
        f"🔗 Твоя ссылка для подключения:\n<code>{subscription_url}</code>\n\n"
        f"Добавь её в приложение (Happ / v2rayNG / другое) и подключайся.",
        reply_markup=kb.back_to_menu_kb(),
    )


async def credit_referral_days(referrer_id: int):
    """Начисляет реферальные дни подписки пригласившему (используется после первой покупки реферала)."""
    await db.extend_subscription(referrer_id, REFERRAL_BONUS_DAYS)
    await db.add_log(referrer_id, "referral_days_bonus", details=f"days={REFERRAL_BONUS_DAYS}")
