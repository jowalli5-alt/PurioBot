from aiogram.fsm.state import State, StatesGroup


class AdminGiveBalance(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()


class AdminBroadcast(StatesGroup):
    waiting_text = State()


class AdminMessageUser(StatesGroup):
    """Отправка личного сообщения одному пользователю по Telegram ID."""
    waiting_user_id = State()
    waiting_text = State()


class AdminFindUser(StatesGroup):
    """Поиск карточки пользователя (баланс, подписка, рефералы) по Telegram ID."""
    waiting_user_id = State()


class TicketCreate(StatesGroup):
    """Пользователь создаёт тикет в поддержку."""
    waiting_text = State()


class AdminTicketReply(StatesGroup):
    """Админ отвечает на тикет."""
    waiting_text = State()
