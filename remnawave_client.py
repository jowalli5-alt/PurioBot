"""
Обёртка над Remnawave через пакет `remnactual` (PyPI) — форк официального
SDK, сверенный побайтово с backend-contract панели версии 3.2.3.

ВАЖНО про версию 3.x: начиная с панели 3.0 пользователи identifицируются
числовым `id`, а не `uuid` (как было в 2.8.x) — это учтено в коде ниже.
Версия пакета жёстко привязана к версии панели:
    remnactual==3.2.3  ->  панель Remnawave >= 3.0.0 (сверено с 3.2.3)
Если обновите панель на более новую ветку — проверьте таблицу совместимости
на https://pypi.org/project/remnactual/ и обновите версию в requirements.txt.
"""
import logging
from datetime import datetime, timedelta, timezone

from remnawave import RemnawaveSDK
from remnawave.models import CreateUserBodyDto, UpdateUserBodyDto
from remnawave.exceptions import NotFoundError

from config import REMNAWAVE_BASE_URL, REMNAWAVE_API_TOKEN, REMNAWAVE_SQUAD_UUID

logger = logging.getLogger(__name__)

# base_url можно передавать БЕЗ /api на конце — библиотека сама его добавит
sdk = RemnawaveSDK(base_url=REMNAWAVE_BASE_URL, token=REMNAWAVE_API_TOKEN)


async def get_user_by_username(username: str):
    """Возвращает объект пользователя или None, если не найден."""
    try:
        return await sdk.users.get_user_by_username(username)
    except NotFoundError:
        return None


async def create_user(username: str, days: int):
    """Создаёт нового пользователя со сроком действия `days` дней от текущего момента."""
    expire_at = datetime.now(timezone.utc) + timedelta(days=days)
    body = CreateUserBodyDto(
        username=username,
        expire_at=expire_at,
        status="ACTIVE",
        active_internal_squads=[REMNAWAVE_SQUAD_UUID] if REMNAWAVE_SQUAD_UUID else [],
    )
    return await sdk.users.create_user(body)


async def extend_user(user_id: int, days_from_now: int):
    """Продлевает существующего пользователя — новая дата истечения = сейчас + days_from_now."""
    expire_at = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    body = UpdateUserBodyDto(id=user_id, expire_at=expire_at, status="ACTIVE")
    return await sdk.users.update_user(body)


async def provision_subscription(telegram_id: int, days: int) -> str:
    """
    Главная функция для бота: создаёт пользователя, если его ещё нет
    в Remnawave, либо продлевает существующего (прибавляя дни к оставшемуся
    сроку, если подписка ещё активна). Возвращает subscription URL.
    """
    username = f"tg_{telegram_id}"
    existing = await get_user_by_username(username)

    if existing is None:
        logger.info(f"Создаю нового пользователя Remnawave: {username}")
        user = await create_user(username, days)
    else:
        logger.info(f"Продлеваю пользователя Remnawave: {username}")
        base_days = days
        now = datetime.now(timezone.utc)
        if existing.expire_at and existing.expire_at > now:
            remaining_days = (existing.expire_at - now).days
            base_days = remaining_days + days
        # 3.x: пользователь идентифицируется числовым id, не uuid
        user = await extend_user(existing.id, base_days)

    return user.subscription_url
