"""
Скрипт для быстрой проверки связки с Remnawave, в обход Telegram.

Запуск (при активном venv):
    python test_remnawave.py

Покажет точную ошибку, если что-то не так с REMNAWAVE_BASE_URL,
REMNAWAVE_API_TOKEN или REMNAWAVE_SQUAD_UUID в .env.
"""
import asyncio
import remnawave_client


async def test():
    print("Пробую создать/продлить тестового пользователя в Remnawave...")
    try:
        url = await remnawave_client.provision_subscription(telegram_id=999999999, days=1)
        print("\n✅ УСПЕХ!")
        print("Subscription URL:", url)
    except Exception as e:
        print("\n❌ ОШИБКА:", type(e).__name__)
        print(str(e))


if __name__ == "__main__":
    asyncio.run(test())
