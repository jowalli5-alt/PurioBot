"""
Раздел "Поддержка": тикет-система, прямой контакт, политика конфиденциальности
и пользовательское соглашение.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramForbiddenError

import database as db
import keyboards as kb
from states import TicketCreate
from config import (
    PRIVACY_POLICY_TEXT, TERMS_OF_USE_TEXT, SUPPORT_USERNAME, ADMIN_IDS,
)

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "menu_support")
async def cb_support(callback: CallbackQuery):
    text = (
        f"🆘 <b>Поддержка</b>\n\n"
        f"Если возникли вопросы или проблемы с подключением — создай тикет "
        f"кнопкой ниже, мы ответим прямо в этом чате. Либо напиши напрямую: "
        f"{SUPPORT_USERNAME}\n\n"
        f"Здесь же — политика конфиденциальности и пользовательское соглашение."
    )
    await callback.message.edit_text(text, reply_markup=kb.support_kb())
    await callback.answer()


@router.callback_query(F.data == "menu_privacy")
async def cb_privacy(callback: CallbackQuery):
    await callback.message.edit_text(PRIVACY_POLICY_TEXT, reply_markup=kb.back_to_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "menu_terms")
async def cb_terms(callback: CallbackQuery):
    await callback.message.edit_text(TERMS_OF_USE_TEXT, reply_markup=kb.back_to_menu_kb())
    await callback.answer()


# ---------------- Тикет-система (со стороны пользователя) ----------------

@router.callback_query(F.data == "ticket_create_start")
async def cb_ticket_create_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TicketCreate.waiting_text)
    await callback.message.edit_text(
        "🎫 Опиши свою проблему или вопрос одним сообщением — "
        "мы получим его и ответим здесь же, в этом чате.",
        reply_markup=kb.ticket_cancel_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "ticket_cancel")
async def cb_ticket_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🆘 <b>Поддержка</b>\n\nОтменено.", reply_markup=kb.support_kb()
    )
    await callback.answer()


@router.message(TicketCreate.waiting_text)
async def ticket_create_text(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    text = message.text or message.caption or "(пустое сообщение)"

    ticket_id = await db.create_ticket(user.id, user.username or "", text)
    await db.add_log(user.id, "ticket_created", details=f"ticket_id={ticket_id}")

    await message.answer(
        f"✅ Тикет #{ticket_id} создан. Мы ответим тебе прямо здесь, как только "
        f"администратор прочитает сообщение.",
        reply_markup=kb.ticket_created_kb(),
    )

    # уведомляем админов
    name_display = f"@{user.username}" if user.username else user.full_name
    admin_text = (
        f"🎫 <b>Новый тикет #{ticket_id}</b>\n"
        f"От: {name_display} (<code>{user.id}</code>)\n\n"
        f"{text}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id, admin_text,
                reply_markup=kb.admin_ticket_view_kb(ticket_id, "open"),
            )
        except (TelegramForbiddenError, Exception):
            pass
