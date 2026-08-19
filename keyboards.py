"""
Все inline-клавиатуры бота в одном месте.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import (
    CHANNEL_LINK, TOPUP_AMOUNTS, TARIFF_LABELS, SUPPORT_USERNAME, ADMIN_IDS,
    PRIVACY_POLICY_URL, TERMS_OF_USE_URL,
)


def channel_subscribe_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Подписаться на канал", url=CHANNEL_LINK)
    kb.button(text="✅ Я подписался", callback_data="check_subscription")
    kb.adjust(1)
    return kb.as_markup()


def main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Профиль", callback_data="menu_profile")
    kb.button(text="🔑 Подписка", callback_data="menu_subscription")
    kb.button(text="🤝 Рефералы", callback_data="menu_referral")
    kb.button(text="🆘 Поддержка", callback_data="menu_support")
    kb.button(text="📢 Наш канал", url=CHANNEL_LINK)
    rows = [2, 2, 1]
    if user_id in ADMIN_IDS:
        kb.button(text="⚙️ Админ-панель", callback_data="menu_admin")
        rows.append(1)
    kb.adjust(*rows)
    return kb.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ В главное меню", callback_data="back_to_menu")
    return kb.as_markup()


def profile_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Пополнить баланс", callback_data="topup_menu")
    kb.button(text="◀️ В главное меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def topup_amounts_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for amount in TOPUP_AMOUNTS:
        kb.button(text=f"{amount}₽", callback_data=f"topup_{amount}")
    kb.button(text="◀️ Назад", callback_data="menu_profile")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def payment_link_kb(pay_url: str, transaction_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Оплатить (СБП)", url=pay_url)
    kb.button(text="🔄 Проверить оплату", callback_data=f"check_pay_{transaction_id}")
    kb.button(text="◀️ В главное меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def subscription_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for days, label in TARIFF_LABELS.items():
        kb.button(text=label, callback_data=f"buy_{days}")
    kb.button(text="◀️ В главное меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def referral_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ В главное меню", callback_data="back_to_menu")
    return kb.as_markup()


def support_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎫 Создать тикет", callback_data="ticket_create_start")
    kb.button(text="✍️ Написать напрямую", url=f"https://t.me/{SUPPORT_USERNAME.lstrip('@')}")
    if PRIVACY_POLICY_URL:
        kb.button(text="📄 Политика конфиденциальности", url=PRIVACY_POLICY_URL)
    else:
        kb.button(text="📄 Политика конфиденциальности", callback_data="menu_privacy")
    if TERMS_OF_USE_URL:
        kb.button(text="📃 Пользовательское соглашение", url=TERMS_OF_USE_URL)
    else:
        kb.button(text="📃 Пользовательское соглашение", callback_data="menu_terms")
    kb.button(text="◀️ В главное меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def ticket_cancel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="ticket_cancel")
    return kb.as_markup()


def ticket_created_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ В главное меню", callback_data="back_to_menu")
    return kb.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Выдать баланс", callback_data="admin_give_balance")
    kb.button(text="✉️ Написать одному (ID)", callback_data="admin_message_user")
    kb.button(text="📣 Рассылка всем", callback_data="admin_broadcast")
    kb.button(text="🎫 Тикеты", callback_data="admin_tickets_0")
    kb.button(text="👥 Пользователи", callback_data="admin_users_0")
    kb.button(text="📊 Статистика", callback_data="admin_stats")
    kb.button(text="◀️ В главное меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def admin_tickets_list_kb(tickets, offset: int, has_more: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in tickets:
        mark = "🆕" if t["status"] == "open" else "💬"
        kb.button(text=f"{mark} Тикет #{t['id']} — {t['username'] or t['user_id']}",
                   callback_data=f"admin_ticket_view_{t['id']}")
    nav = []
    if offset > 0:
        nav.append(("⬅️ Назад", f"admin_tickets_{max(offset - 5, 0)}"))
    if has_more:
        nav.append(("Вперёд ➡️", f"admin_tickets_{offset + 5}"))
    for text, cb in nav:
        kb.button(text=text, callback_data=cb)
    kb.button(text="◀️ В админ-панель", callback_data="menu_admin")
    rows = [1] * len(tickets) + ([2] if len(nav) == 2 else [1] * len(nav)) + [1]
    kb.adjust(*rows)
    return kb.as_markup()


def admin_ticket_view_kb(ticket_id: int, status: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✍️ Ответить", callback_data=f"admin_ticket_reply_{ticket_id}")
    if status != "closed":
        kb.button(text="✅ Закрыть тикет", callback_data=f"admin_ticket_close_{ticket_id}")
    kb.button(text="◀️ К тикетам", callback_data="admin_tickets_0")
    kb.adjust(1)
    return kb.as_markup()


def cancel_fsm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="admin_cancel")
    return kb.as_markup()


def admin_users_pagination_kb(offset: int, has_more: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    buttons = []
    if offset > 0:
        buttons.append(("⬅️ Назад", f"admin_users_{max(offset - 10, 0)}"))
    if has_more:
        buttons.append(("Вперёд ➡️", f"admin_users_{offset + 10}"))
    for text, cb in buttons:
        kb.button(text=text, callback_data=cb)
    kb.button(text="◀️ В админ-панель", callback_data="menu_admin")
    kb.adjust(2, 1)
    return kb.as_markup()
