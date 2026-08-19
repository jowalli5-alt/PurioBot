"""
Админ-панель: выдать баланс, рассылка сообщений, список пользователей, статистика.
Доступна только ID из config.ADMIN_IDS.
"""
import asyncio
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

import database as db
import keyboards as kb
from config import ADMIN_IDS
from states import AdminGiveBalance, AdminBroadcast, AdminMessageUser, AdminTicketReply

logger = logging.getLogger(__name__)
router = Router()


def admin_only(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@router.callback_query(F.data == "menu_admin")
async def cb_admin_menu(callback: CallbackQuery):
    if not admin_only(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text("⚙️ <b>Админ-панель</b>", reply_markup=kb.admin_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "admin_cancel")
async def cb_admin_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("⚙️ <b>Админ-панель</b>", reply_markup=kb.admin_menu_kb())
    await callback.answer("Отменено")


# ---------------- Выдать баланс ----------------

@router.callback_query(F.data == "admin_give_balance")
async def cb_give_balance_start(callback: CallbackQuery, state: FSMContext):
    if not admin_only(callback.from_user.id):
        return await callback.answer("Доступ запрещён", show_alert=True)

    await state.set_state(AdminGiveBalance.waiting_user_id)
    await callback.message.edit_text(
        "Введи Telegram ID пользователя, которому нужно начислить баланс:",
        reply_markup=kb.cancel_fsm_kb(),
    )
    await callback.answer()


@router.message(AdminGiveBalance.waiting_user_id)
async def admin_give_balance_userid(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно прислать число (Telegram ID). Попробуй ещё раз:")
        return

    user = await db.get_user(target_id)
    if user is None:
        await message.answer(
            "Пользователь с таким ID не найден в базе (он ни разу не запускал бота). "
            "Проверь ID и попробуй ещё раз:"
        )
        return

    await state.update_data(target_id=target_id)
    await state.set_state(AdminGiveBalance.waiting_amount)
    await message.answer(
        f"Пользователь найден: {user['username'] or user['full_name']} "
        f"(текущий баланс {user['balance']:.2f}₽).\n\n"
        f"Введи сумму для начисления (можно отрицательную, чтобы списать):"
    )


@router.message(AdminGiveBalance.waiting_amount)
async def admin_give_balance_amount(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return

    try:
        amount = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("Нужно число, например 500 или -100. Попробуй ещё раз:")
        return

    data = await state.get_data()
    target_id = data["target_id"]

    await db.update_balance(target_id, amount)
    await db.add_log(target_id, "admin_balance_change", details=f"amount={amount} by={message.from_user.id}")
    await state.clear()

    user = await db.get_user(target_id)
    await message.answer(
        f"✅ Готово. Новый баланс пользователя {target_id}: <b>{user['balance']:.2f}₽</b>",
        reply_markup=kb.admin_menu_kb(),
    )

    try:
        await message.bot.send_message(
            target_id,
            f"💰 Тебе начислено {amount:+.2f}₽ администратором.\nТекущий баланс: {user['balance']:.2f}₽",
        )
    except (TelegramForbiddenError, Exception):
        pass


# ---------------- Рассылка ----------------

@router.callback_query(F.data == "admin_broadcast")
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not admin_only(callback.from_user.id):
        return await callback.answer("Доступ запрещён", show_alert=True)

    await state.set_state(AdminBroadcast.waiting_text)
    await callback.message.edit_text(
        "Пришли текст сообщения, которое нужно разослать всем пользователям бота:",
        reply_markup=kb.cancel_fsm_kb(),
    )
    await callback.answer()


@router.message(AdminBroadcast.waiting_text)
async def admin_broadcast_send(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return

    await state.clear()
    text = message.html_text
    user_ids = await db.get_all_user_ids()

    status_msg = await message.answer(f"📣 Начинаю рассылку на {len(user_ids)} пользователей...")

    sent, failed = 0, 0
    for uid in user_ids:
        try:
            await message.bot.send_message(uid, text)
            sent += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await message.bot.send_message(uid, text)
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # чтобы не упереться в лимиты Telegram

    await db.add_log(message.from_user.id, "admin_broadcast", details=f"sent={sent} failed={failed}")
    await status_msg.edit_text(
        f"✅ Рассылка завершена.\nДоставлено: {sent}\nНе доставлено: {failed}",
        reply_markup=kb.admin_menu_kb(),
    )


# ---------------- Написать одному пользователю (по ID) ----------------

@router.callback_query(F.data == "admin_message_user")
async def cb_message_user_start(callback: CallbackQuery, state: FSMContext):
    if not admin_only(callback.from_user.id):
        return await callback.answer("Доступ запрещён", show_alert=True)

    await state.set_state(AdminMessageUser.waiting_user_id)
    await callback.message.edit_text(
        "Введи Telegram ID пользователя, которому нужно написать:",
        reply_markup=kb.cancel_fsm_kb(),
    )
    await callback.answer()


@router.message(AdminMessageUser.waiting_user_id)
async def admin_message_user_id(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно прислать число (Telegram ID). Попробуй ещё раз:")
        return

    user = await db.get_user(target_id)
    if user is None:
        await message.answer(
            "Пользователь с таким ID не найден в базе (он ни разу не запускал бота). "
            "Проверь ID и попробуй ещё раз:"
        )
        return

    await state.update_data(target_id=target_id)
    await state.set_state(AdminMessageUser.waiting_text)
    await message.answer(
        f"Пользователь найден: {user['username'] or user['full_name']}.\n\n"
        f"Введи текст сообщения:"
    )


@router.message(AdminMessageUser.waiting_text)
async def admin_message_user_text(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return

    data = await state.get_data()
    target_id = data["target_id"]
    await state.clear()

    try:
        await message.bot.send_message(target_id, message.html_text)
        await db.add_log(target_id, "admin_direct_message", details=f"by={message.from_user.id}")
        await message.answer("✅ Сообщение отправлено.", reply_markup=kb.admin_menu_kb())
    except TelegramForbiddenError:
        await message.answer(
            "⚠️ Не получилось отправить — пользователь заблокировал бота.",
            reply_markup=kb.admin_menu_kb(),
        )
    except Exception:
        logger.exception("Ошибка отправки личного сообщения пользователю")
        await message.answer(
            "⚠️ Не получилось отправить сообщение, попробуй ещё раз.",
            reply_markup=kb.admin_menu_kb(),
        )


# ---------------- Тикеты поддержки ----------------

@router.callback_query(F.data.startswith("admin_tickets_"))
async def cb_admin_tickets(callback: CallbackQuery):
    if not admin_only(callback.from_user.id):
        return await callback.answer("Доступ запрещён", show_alert=True)

    offset = int(callback.data.removeprefix("admin_tickets_"))
    tickets = await db.list_open_tickets(limit=5, offset=offset)
    total = await db.count_open_tickets()

    if not tickets:
        await callback.message.edit_text(
            "🎫 Открытых тикетов нет.", reply_markup=kb.admin_menu_kb()
        )
        await callback.answer()
        return

    has_more = offset + len(tickets) < total
    await callback.message.edit_text(
        f"🎫 <b>Тикеты</b> (открытых: {total})\n\n"
        f"🆕 — новый, ждёт ответа. 💬 — уже отвечен, можно закрыть.",
        reply_markup=kb.admin_tickets_list_kb(tickets, offset, has_more),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_ticket_view_"))
async def cb_admin_ticket_view(callback: CallbackQuery):
    if not admin_only(callback.from_user.id):
        return await callback.answer("Доступ запрещён", show_alert=True)

    ticket_id = int(callback.data.removeprefix("admin_ticket_view_"))
    ticket = await db.get_ticket(ticket_id)
    if ticket is None:
        await callback.answer("Тикет не найден", show_alert=True)
        return

    messages = await db.get_ticket_messages(ticket_id)
    lines = [f"🎫 <b>Тикет #{ticket_id}</b> — статус: {ticket['status']}\n"]
    for m in messages:
        dt = datetime.fromtimestamp(m["created_at"]).strftime("%d.%m %H:%M")
        who = "👤 Пользователь" if m["sender"] == "user" else "🛠 Админ"
        lines.append(f"{who} ({dt}):\n{m['text']}\n")

    await callback.message.edit_text(
        "\n".join(lines), reply_markup=kb.admin_ticket_view_kb(ticket_id, ticket["status"])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_ticket_reply_"))
async def cb_admin_ticket_reply_start(callback: CallbackQuery, state: FSMContext):
    if not admin_only(callback.from_user.id):
        return await callback.answer("Доступ запрещён", show_alert=True)

    ticket_id = int(callback.data.removeprefix("admin_ticket_reply_"))
    ticket = await db.get_ticket(ticket_id)
    if ticket is None:
        await callback.answer("Тикет не найден", show_alert=True)
        return

    await state.update_data(ticket_id=ticket_id, ticket_user_id=ticket["user_id"])
    await state.set_state(AdminTicketReply.waiting_text)
    await callback.message.edit_text(
        f"✍️ Введи ответ для тикета #{ticket_id} "
        f"(пользователю <code>{ticket['user_id']}</code>):",
        reply_markup=kb.cancel_fsm_kb(),
    )
    await callback.answer()


@router.message(AdminTicketReply.waiting_text)
async def admin_ticket_reply_send(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return

    data = await state.get_data()
    ticket_id = data["ticket_id"]
    target_id = data["ticket_user_id"]
    await state.clear()

    reply_text = message.text or message.caption or ""
    await db.add_ticket_message(ticket_id, "admin", message.from_user.id, reply_text)
    await db.add_log(target_id, "ticket_answered", details=f"ticket_id={ticket_id} by={message.from_user.id}")

    try:
        await message.bot.send_message(
            target_id,
            f"🎫 Ответ по твоему тикету #{ticket_id}:\n\n{reply_text}",
        )
        sent_note = "✅ Ответ отправлен пользователю."
    except (TelegramForbiddenError, Exception):
        sent_note = "⚠️ Ответ сохранён, но отправить пользователю не удалось (заблокировал бота?)."

    ticket = await db.get_ticket(ticket_id)
    await message.answer(
        sent_note, reply_markup=kb.admin_ticket_view_kb(ticket_id, ticket["status"])
    )


@router.callback_query(F.data.startswith("admin_ticket_close_"))
async def cb_admin_ticket_close(callback: CallbackQuery):
    if not admin_only(callback.from_user.id):
        return await callback.answer("Доступ запрещён", show_alert=True)

    ticket_id = int(callback.data.removeprefix("admin_ticket_close_"))
    await db.close_ticket(ticket_id)
    await db.add_log(callback.from_user.id, "ticket_closed", details=f"ticket_id={ticket_id}")
    await callback.answer("Тикет закрыт ✅")

    await callback.message.edit_text(
        f"🎫 Тикет #{ticket_id} закрыт.", reply_markup=kb.admin_menu_kb()
    )


# ---------------- Список пользователей ----------------

@router.callback_query(F.data.startswith("admin_users_"))
async def cb_admin_users(callback: CallbackQuery):
    if not admin_only(callback.from_user.id):
        return await callback.answer("Доступ запрещён", show_alert=True)

    offset = int(callback.data.removeprefix("admin_users_"))
    users = await db.list_users(limit=10, offset=offset)
    total = await db.count_all_users()

    if not users:
        await callback.message.edit_text("Пользователей пока нет.", reply_markup=kb.admin_menu_kb())
        await callback.answer()
        return

    lines = [f"👥 <b>Пользователи</b> (показано {offset + 1}-{offset + len(users)} из {total})\n"]
    for u in users:
        expire = "—"
        if u["subscription_expire"]:
            expire = datetime.fromtimestamp(u["subscription_expire"]).strftime("%d.%m.%Y")
        ref = f", пригласил {u['referrer_id']}" if u["referrer_id"] else ""
        lines.append(
            f"• <code>{u['user_id']}</code> @{u['username'] or '—'} | "
            f"баланс {u['balance']:.0f}₽ | до {expire}{ref}"
        )

    has_more = offset + len(users) < total
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=kb.admin_users_pagination_kb(offset, has_more)
    )
    await callback.answer()


# ---------------- Статистика ----------------

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    if not admin_only(callback.from_user.id):
        return await callback.answer("Доступ запрещён", show_alert=True)

    total = await db.count_all_users()
    logs = await db.get_recent_logs(limit=15)

    lines = [f"📊 <b>Статистика</b>\n\nВсего пользователей: <b>{total}</b>\n\n<b>Последние действия:</b>"]
    for log in logs:
        dt = datetime.fromtimestamp(log["created_at"]).strftime("%d.%m %H:%M")
        lines.append(f"• {dt} — {log['user_id']} — {log['action']} {log['details'] or ''}")

    await callback.message.edit_text("\n".join(lines), reply_markup=kb.admin_menu_kb())
    await callback.answer()
