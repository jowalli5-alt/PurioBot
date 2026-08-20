"""
Раздел "Рефералы": реферальная ссылка и статистика.
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery

import database as db
import keyboards as kb
from config import REFERRAL_BONUS_DAYS, REFERRAL_PERCENT, BOT_USERNAME

router = Router()


@router.callback_query(F.data == "menu_referral")
async def cb_referral(callback: CallbackQuery):
    user_id = callback.from_user.id
    bot_username = BOT_USERNAME or (await callback.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    referrals = await db.get_referrals(user_id)
    me = await db.get_user(user_id)
    earned = me["referral_earned"] if me is not None else 0
    paid_count = me["referral_paid_count"] if me is not None else 0

    lines = [
        "🤝 <b>Реферальная программа</b>\n",
        f"За каждого приглашённого друга, который оформит подписку впервые — "
        f"тебе <b>{REFERRAL_BONUS_DAYS} дня подписки бесплатно</b>.",
        f"Плюс <b>{int(REFERRAL_PERCENT * 100)}%</b> от суммы каждой его покупки подписки — "
        f"сразу деньгами на твой счёт.\n",
        f"🔗 Твоя реферальная ссылка:\n<code>{ref_link}</code>\n",
        f"👥 Приглашено друзей: <b>{len(referrals)}</b>",
        f"✅ Из них купили подписку: <b>{paid_count}</b>",
        f"💰 Заработано с рефералов: <b>{earned:.2f}₽</b>",
    ]

    if referrals:
        lines.append("\n<b>Твои рефералы:</b>")
        for r in referrals[:15]:
            name = f"@{r['username']}" if r["username"] else str(r["user_id"])
            status = "✅ есть подписка" if r["subscription_expire"] else "— без подписки"
            lines.append(f"• {name} ({status})")
        if len(referrals) > 15:
            lines.append(f"…и ещё {len(referrals) - 15}")

    await callback.message.edit_text("\n".join(lines), reply_markup=kb.referral_kb())
    await callback.answer()
