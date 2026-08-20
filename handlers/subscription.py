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
from config import TARIFFS, REFERRAL_BONUS_DAYS, REFERRAL_PERCENT

logger = logging.getLogger(__name__)
router = Router()


def _is_active(expire_ts: int) -> bool:
    return bool(expire_ts) and expire_ts >= datetime.now().timestamp()


def _format_expire(expire_ts: int) -> str:
    if not _is_active(expire_ts):
        return "❌ Подписка не активна"
    dt = datetime.fromtimestamp(expire_ts)
    return f"✅ Активна до {dt.strftime('%d.%m.%Y %H:%M')}"


@router.callback_query(F.data == "menu_subscription")
async def cb_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    status = _format_expire(user["subscription_expire"])

    text = f"🔑 <b>Подписка</b>\n\nСтатус: {status}\n"

    # Фикс бага "ссылка пропадает после выхода из бота": ссылка хранится в БД
    # и подтягивается заново при каждом заходе в раздел, а не только в момент покупки.
    if _is_active(user["subscription_expire"]):
        url = user["subscription_url"]
        if not url:
            # Старый пользователь, у которого ссылка ещё не сохранялась локально —
            # подтягиваем её напрямую из Remnawave и сохраняем на будущее.
            try:
                url = await remnawave_client.get_existing_subscription_url(user_id)
                if url:
                    await db.extend_subscription(user_id, 0, subscription_url=url)
            except Exception:
                logger.exception("Не удалось получить subscription_url из Remnawave")
                url = None

        if url:
            text += f"\n🔗 Твоя ссылка для подключения:\n<code>{url}</code>\n"
        else:
            text += (
                "\n⚠️ Не получилось получить ссылку автоматически — "
                "напиши в поддержку, поможем вручную.\n"
            )

    text += "\nВыбери тариф для покупки или продления:"
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

    # списываем деньги и продлеваем локально только после успешного ответа Remnawave.
    # Ссылка сохраняется в БД (users.subscription_url + таблица subscriptions),
    # поэтому больше не теряется, если человек выйдет из бота и зайдёт снова.
    await db.update_balance(user_id, -price)
    new_expire = await db.extend_subscription(
        user_id, days, subscription_url=subscription_url, tariff_days=days, price=price,
    )
    await db.add_log(user_id, "subscription_purchased", details=f"days={days} price={price}")

    is_first_purchase = user["subscription_expire"] == 0
    referrer_id = user["referrer_id"]

    if referrer_id:
        # 7% от суммы КАЖДОЙ покупки уходят пригласившему деньгами на баланс —
        # раньше это начислялось только при пополнении через Platega и никогда
        # не срабатывало, если баланс был выдан админом вручную. Теперь привязано
        # к самой покупке и не зависит от того, откуда взялись деньги на балансе.
        bonus = round(price * REFERRAL_PERCENT, 2)
        if bonus > 0:
            await db.update_balance(referrer_id, bonus)
            await db.add_referral_earned(referrer_id, bonus)
            await db.add_log(
                referrer_id, "referral_purchase_bonus",
                details=f"from={user_id} bonus={bonus} price={price}",
            )
            try:
                await callback.bot.send_message(
                    referrer_id,
                    f"💰 Твой реферал купил подписку — тебе начислено {bonus:.2f}₽ (7%) на баланс.",
                )
            except Exception:
                pass

        # Бонусные дни + реальный доступ VPN пригласившему — только за первую
        # покупку реферала (чтобы не начислять их за каждое продление).
        if is_first_purchase:
            await credit_referral_days(callback.bot, referrer_id)
            await db.increment_referral_paid_count(referrer_id)

    dt = datetime.fromtimestamp(new_expire)
    await callback.message.edit_text(
        f"✅ Подписка оформлена до <b>{dt.strftime('%d.%m.%Y')}</b>!\n\n"
        f"🔗 Твоя ссылка для подключения:\n<code>{subscription_url}</code>\n\n"
        f"Добавь её в приложение (Happ / v2rayNG / другое) и подключайся.\n\n"
        f"Эта ссылка теперь всегда доступна в разделе «🔑 Подписка», даже если "
        f"ты выйдешь из бота и зайдёшь заново.",
        reply_markup=kb.back_to_menu_kb(),
    )


async def credit_referral_days(bot, referrer_id: int):
    """
    Начисляет реферальные дни подписки пригласившему (после первой покупки реферала).

    ВАЖНО: раньше это только прибавляло дни в локальной БД, но НЕ продлевало
    и не создавало реальный доступ в Remnawave — из-за этого у пригласившего
    "привилегии" не появлялись: дата в боте росла, а реального VPN-доступа не было.
    Теперь дни реально выдаются через Remnawave, как при обычной покупке.
    """
    try:
        subscription_url = await remnawave_client.provision_subscription(referrer_id, REFERRAL_BONUS_DAYS)
    except Exception:
        logger.exception("Не удалось выдать реферальные дни через Remnawave для %s", referrer_id)
        # Дни в локальной БД всё равно начисляем, чтобы не терять бонус — но
        # без ссылки, реальный доступ нужно будет выдать вручную через поддержку.
        await db.extend_subscription(referrer_id, REFERRAL_BONUS_DAYS)
        await db.add_log(referrer_id, "referral_days_bonus_failed", details=f"days={REFERRAL_BONUS_DAYS}")
        return

    await db.extend_subscription(
        referrer_id, REFERRAL_BONUS_DAYS,
        subscription_url=subscription_url, tariff_days=REFERRAL_BONUS_DAYS, price=0,
    )
    await db.add_log(referrer_id, "referral_days_bonus", details=f"days={REFERRAL_BONUS_DAYS}")

    try:
        await bot.send_message(
            referrer_id,
            f"🎁 Твой реферал купил подписку впервые — тебе начислено "
            f"{REFERRAL_BONUS_DAYS} дня VPN бесплатно!\n\n"
            f"🔗 Ссылка для подключения:\n<code>{subscription_url}</code>",
        )
    except Exception:
        pass
