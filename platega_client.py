"""
Обёртка над Platega (app.platega.io) для приёма оплаты — пополнение баланса.

Точная схема запросов сверена с официальной документацией:
https://docs.platega.io/

Авторизация — два заголовка на каждый запрос:
    X-MerchantId: <ваш MerchantId>
    X-Secret:     <ваш API ключ>
Оба берутся в личном кабинете Platega на странице "Настройки", либо выдаются
менеджером при подключении.
"""
import logging
import httpx

from config import PLATEGA_MERCHANT_ID, PLATEGA_SECRET, PLATEGA_RETURN_URL

logger = logging.getLogger(__name__)

BASE_URL = "https://app.platega.io"

# Способ оплаты: 2 = СБП (QR-код) — самый ходовой для российских клиентов.
# Другие варианты по документации: 3 = ЕРИП, 11 = карты, 12 = международная
# оплата, 13 = крипта, 14 = Sberpay.
PAYMENT_METHOD_SBP = 2

HEADERS = {
    "X-MerchantId": PLATEGA_MERCHANT_ID,
    "X-Secret": PLATEGA_SECRET,
    "Content-Type": "application/json",
}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=20)


async def create_payment(amount: float, description: str, payload: str = "") -> tuple[str, str]:
    """
    Создаёт транзакцию в Platega.
    Возвращает (transaction_id, redirect_url) — ссылку, куда отправить пользователя платить.
    Поле `id` транзакции НЕ передаём — Platega генерирует его сама.
    """
    body = {
        "paymentMethod": PAYMENT_METHOD_SBP,
        "paymentDetails": {"amount": amount, "currency": "RUB"},
        "description": description,
        "return": PLATEGA_RETURN_URL,
        "failedUrl": PLATEGA_RETURN_URL,
        "payload": payload,
    }
    async with _client() as client:
        resp = await client.post("/transaction/process", json=body)
        resp.raise_for_status()
        data = resp.json()
        return data["transactionId"], data["redirect"]


async def check_payment_status(transaction_id: str) -> str:
    """
    Возвращает статус транзакции: PENDING / CONFIRMED / CANCELED / CHARGEBACKED.
    """
    async with _client() as client:
        resp = await client.get(f"/transaction/{transaction_id}")
        resp.raise_for_status()
        data = resp.json()
        return data["status"]
