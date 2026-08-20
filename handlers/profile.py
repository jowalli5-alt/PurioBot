"""
Профиль пользователя, пополнение баланса через Platega (СБП).
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

import database as db
import keyboards as kb
import platega_client
from config import ENABLE_PLATEGA

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "menu_profile")
async def cb_profile(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    username = callback.from_user.username
    name_display = f"@{username}" if username else callback.from_user.full_name

    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"Ник: {name_display}\n"
        f"ID: <code>{user['user_id']}</code>\n"
        f"💰 Баланс: <b>{user['balance']:.2f}₽</b>\n"
    )
    await callback.message.edit_text(text, reply_markup=kb.profile_kb())
    await callback.answer()


@router.callback_query(F.data == "topup_menu")
async def cb_topup_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "💳 Выбери сумму пополнения:", reply_markup=kb.topup_amounts_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("topup_"))
async def cb_topup_amount(callback: CallbackQuery):
    amount = int(callback.data.removeprefix("topup_"))
    user_id = callback.from_user.id

    if not ENABLE_PLATEGA:
        await db.add_log(user_id, "topup_attempt_no_payment_configured", details=f"amount={amount}")
        await callback.answer("🚧 Оплата ещё в разработке", show_alert=True)
        await callback.message.edit_text(
            "🚧 <b>Пополнение баланса скоро будет доступно</b>\n\n"
            "Мы уже подключаем оплату — совсем немного осталось. "
            "Загляни чуть позже 🙌",
            reply_markup=kb.back_to_menu_kb(),
        )
        return

    try:
        transaction_id, pay_url = await platega_client.create_payment(
            amount=amount,
            description=f"Пополнение баланса PurioVPN на {amount}₽ (ID {user_id})",
            payload=str(user_id),
        )
    except Exception:
        logger.exception("Ошибка создания платежа Platega")
        await callback.answer("Платёжная система временно недоступна, попробуй позже 🙁", show_alert=True)
        return

    await db.create_payment_record(transaction_id, user_id, amount)
    await db.add_log(user_id, "topup_created", details=f"amount={amount} transaction_id={transaction_id}")

    await callback.message.edit_text(
        f"💳 Счёт на <b>{amount}₽</b> создан.\n\n"
        f"Нажми «Оплатить», заверши оплату через СБП, затем вернись и нажми "
        f"«Проверить оплату» (либо бот сам зачислит в течение минуты).",
        reply_markup=kb.payment_link_kb(pay_url, transaction_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("check_pay_"))
async def cb_check_payment(callback: CallbackQuery):
    transaction_id = callback.data.removeprefix("check_pay_")
    payment = await db.get_payment(transaction_id)

    if payment is None:
        await callback.answer("Платёж не найден", show_alert=True)
        return

    if payment["status"] == "succeeded":
        await callback.answer("Этот платёж уже зачислен ✅", show_alert=True)
        return

    try:
        status = await platega_client.check_payment_status(transaction_id)
    except Exception:
        logger.exception("Ошибка проверки статуса платежа Platega")
        await callback.answer("Не получилось проверить оплату, попробуй ещё раз чуть позже", show_alert=True)
        return

    if status == "CONFIRMED":
        await _credit_payment(transaction_id, payment["user_id"], payment["amount"])
        await callback.answer("Оплата прошла! Баланс пополнен ✅", show_alert=True)
        user = await db.get_user(callback.from_user.id)
        await callback.message.edit_text(
            f"✅ Баланс успешно пополнен на {payment['amount']:.0f}₽.\n\n"
            f"💰 Текущий баланс: <b>{user['balance']:.2f}₽</b>",
            reply_markup=kb.back_to_menu_kb(),
        )
    elif status in ("CANCELED", "CHARGEBACKED"):
        await db.mark_payment(transaction_id, "canceled")
        await callback.answer("Платёж отменён", show_alert=True)
    else:
        await callback.answer("Оплата пока не поступила, попробуй проверить через минуту", show_alert=True)


async def _credit_payment(transaction_id: str, user_id: int, amount: float):
    """
    Зачисляет оплату на баланс. Реферальные 7% теперь начисляются не за само
    пополнение, а за покупку подписки (см. handlers/subscription.py) — это и
    чинит баг, когда баланс выдан админом вручную (без Platega): раньше 7%
    были жёстко привязаны именно к этому топ-апу и не срабатывали для
    покупок, оплаченных админским балансом. Так поведение одинаково для
    любого источника денег на балансе.
    """
    await db.mark_payment(transaction_id, "succeeded")
    await db.update_balance(user_id, amount)
    await db.add_log(user_id, "topup_succeeded", details=f"amount={amount} transaction_id={transaction_id}")
