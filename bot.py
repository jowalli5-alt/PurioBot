"""
Точка входа. Запуск: python bot.py
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ENABLE_PLATEGA
import database as db
from middlewares import SubscriptionCheckMiddleware

from handlers import start, profile, subscription, referral, support, admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def payments_watcher(bot: Bot):
    """
    Фоновая задача: раз в 20 секунд проверяет незавершённые платежи Platega
    и зачисляет баланс автоматически, даже если пользователь не нажал
    "Проверить оплату" сам. Работает только если Platega подключена в .env.
    """
    import platega_client
    from handlers.profile import _credit_payment

    while True:
        try:
            pending = await db.get_pending_payments()
            for payment in pending:
                try:
                    status = await platega_client.check_payment_status(payment["id"])
                except Exception:
                    continue
                if status == "CONFIRMED":
                    await _credit_payment(payment["id"], payment["user_id"], payment["amount"])
                    try:
                        await bot.send_message(
                            payment["user_id"],
                            f"✅ Оплата на {payment['amount']:.0f}₽ прошла успешно! Баланс пополнен.",
                        )
                    except Exception:
                        pass
                elif status in ("CANCELED", "CHARGEBACKED"):
                    await db.mark_payment(payment["id"], "canceled")
        except Exception:
            logger.exception("Ошибка в фоновой проверке платежей")

        await asyncio.sleep(20)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в .env")

    await db.init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(SubscriptionCheckMiddleware())
    dp.callback_query.middleware(SubscriptionCheckMiddleware())

    dp.include_router(start.router)
    dp.include_router(profile.router)
    dp.include_router(subscription.router)
    dp.include_router(referral.router)
    dp.include_router(support.router)
    dp.include_router(admin.router)

    if ENABLE_PLATEGA:
        asyncio.create_task(payments_watcher(bot))

    logger.info("Бот запущен")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
