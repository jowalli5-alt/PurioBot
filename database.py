"""
Работа с базой данных (SQLite, асинхронно через aiosqlite).
Хранит пользователей, логи действий и платежи.
"""
import time
import aiosqlite
from config import DB_PATH

_db: aiosqlite.Connection | None = None


async def init_db():
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            balance REAL DEFAULT 0,
            subscription_expire INTEGER DEFAULT 0,   -- unix timestamp, 0 = нет подписки
            referrer_id INTEGER DEFAULT NULL,
            remnawave_uuid TEXT DEFAULT NULL,
            referral_earned REAL DEFAULT 0,          -- сколько заработано с рефералов (в рублях)
            created_at INTEGER,
            last_seen INTEGER
        )
    """)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            created_at INTEGER
        )
    """)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY,           -- id платежа в ЮKassa
            user_id INTEGER,
            amount REAL,
            status TEXT DEFAULT 'pending', -- pending / succeeded / canceled
            created_at INTEGER
        )
    """)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            status TEXT DEFAULT 'open',    -- open / answered / closed
            created_at INTEGER,
            updated_at INTEGER
        )
    """)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS ticket_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            sender TEXT,        -- 'user' / 'admin'
            sender_id INTEGER,
            text TEXT,
            created_at INTEGER
        )
    """)
    await _db.commit()

    # Лёгкая миграция для баз, созданных до появления столбца referral_earned.
    try:
        await _db.execute("ALTER TABLE users ADD COLUMN referral_earned REAL DEFAULT 0")
        await _db.commit()
    except Exception:
        pass  # столбец уже существует


def _now() -> int:
    return int(time.time())


# ---------------- USERS ----------------

async def get_user(user_id: int) -> aiosqlite.Row | None:
    _db.row_factory = aiosqlite.Row
    cur = await _db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return await cur.fetchone()


async def get_or_create_user(user_id: int, username: str, full_name: str,
                              referrer_id: int | None = None) -> tuple[aiosqlite.Row, bool]:
    """Возвращает (пользователь, создан_ли_новый)."""
    user = await get_user(user_id)
    if user:
        await _db.execute(
            "UPDATE users SET username = ?, full_name = ?, last_seen = ? WHERE user_id = ?",
            (username, full_name, _now(), user_id),
        )
        await _db.commit()
        return user, False

    # реферер не может быть самим собой и должен существовать
    valid_referrer = None
    if referrer_id and referrer_id != user_id:
        ref = await get_user(referrer_id)
        if ref:
            valid_referrer = referrer_id

    await _db.execute(
        "INSERT INTO users (user_id, username, full_name, balance, subscription_expire, "
        "referrer_id, created_at, last_seen) VALUES (?, ?, ?, 0, 0, ?, ?, ?)",
        (user_id, username, full_name, valid_referrer, _now(), _now()),
    )
    await _db.commit()
    user = await get_user(user_id)
    return user, True


async def update_balance(user_id: int, delta: float):
    await _db.execute(
        "UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id)
    )
    await _db.commit()


async def set_balance(user_id: int, value: float):
    await _db.execute(
        "UPDATE users SET balance = ? WHERE user_id = ?", (value, user_id)
    )
    await _db.commit()


async def extend_subscription(user_id: int, days: int):
    user = await get_user(user_id)
    now = _now()
    current_expire = user["subscription_expire"] or 0
    base = current_expire if current_expire > now else now
    new_expire = base + days * 86400
    await _db.execute(
        "UPDATE users SET subscription_expire = ? WHERE user_id = ?", (new_expire, user_id)
    )
    await _db.commit()
    return new_expire


async def set_remnawave_uuid(user_id: int, uuid: str):
    await _db.execute(
        "UPDATE users SET remnawave_uuid = ? WHERE user_id = ?", (uuid, user_id)
    )
    await _db.commit()


async def get_referrals(user_id: int) -> list[aiosqlite.Row]:
    _db.row_factory = aiosqlite.Row
    cur = await _db.execute("SELECT * FROM users WHERE referrer_id = ?", (user_id,))
    return await cur.fetchall()


async def count_all_users() -> int:
    cur = await _db.execute("SELECT COUNT(*) FROM users")
    row = await cur.fetchone()
    return row[0]


async def list_users(limit: int = 20, offset: int = 0) -> list[aiosqlite.Row]:
    _db.row_factory = aiosqlite.Row
    cur = await _db.execute(
        "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
    )
    return await cur.fetchall()


async def get_all_user_ids() -> list[int]:
    cur = await _db.execute("SELECT user_id FROM users")
    rows = await cur.fetchall()
    return [r[0] for r in rows]


# ---------------- LOGS ----------------

async def add_log(user_id: int, action: str, details: str = ""):
    await _db.execute(
        "INSERT INTO logs (user_id, action, details, created_at) VALUES (?, ?, ?, ?)",
        (user_id, action, details, _now()),
    )
    await _db.commit()


async def get_recent_logs(limit: int = 30) -> list[aiosqlite.Row]:
    _db.row_factory = aiosqlite.Row
    cur = await _db.execute(
        "SELECT * FROM logs ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    return await cur.fetchall()


# ---------------- PAYMENTS ----------------

async def create_payment_record(payment_id: str, user_id: int, amount: float):
    await _db.execute(
        "INSERT INTO payments (id, user_id, amount, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
        (payment_id, user_id, amount, _now()),
    )
    await _db.commit()


async def get_payment(payment_id: str) -> aiosqlite.Row | None:
    _db.row_factory = aiosqlite.Row
    cur = await _db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    return await cur.fetchone()


async def mark_payment(payment_id: str, status: str):
    await _db.execute("UPDATE payments SET status = ? WHERE id = ?", (status, payment_id))
    await _db.commit()


async def get_pending_payments() -> list[aiosqlite.Row]:
    _db.row_factory = aiosqlite.Row
    cur = await _db.execute("SELECT * FROM payments WHERE status = 'pending'")
    return await cur.fetchall()


async def add_referral_earned(user_id: int, amount: float):
    await _db.execute(
        "UPDATE users SET referral_earned = referral_earned + ? WHERE user_id = ?",
        (amount, user_id),
    )
    await _db.commit()


# ---------------- TICKETS (тикет-система поддержки) ----------------

async def create_ticket(user_id: int, username: str, text: str) -> int:
    """Создаёт тикет и первое сообщение в нём. Возвращает id тикета."""
    now = _now()
    cur = await _db.execute(
        "INSERT INTO tickets (user_id, username, status, created_at, updated_at) "
        "VALUES (?, ?, 'open', ?, ?)",
        (user_id, username, now, now),
    )
    ticket_id = cur.lastrowid
    await _db.execute(
        "INSERT INTO ticket_messages (ticket_id, sender, sender_id, text, created_at) "
        "VALUES (?, 'user', ?, ?, ?)",
        (ticket_id, user_id, text, now),
    )
    await _db.commit()
    return ticket_id


async def add_ticket_message(ticket_id: int, sender: str, sender_id: int, text: str):
    now = _now()
    await _db.execute(
        "INSERT INTO ticket_messages (ticket_id, sender, sender_id, text, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ticket_id, sender, sender_id, text, now),
    )
    new_status = "answered" if sender == "admin" else "open"
    await _db.execute(
        "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
        (new_status, now, ticket_id),
    )
    await _db.commit()


async def get_ticket(ticket_id: int) -> aiosqlite.Row | None:
    _db.row_factory = aiosqlite.Row
    cur = await _db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    return await cur.fetchone()


async def get_ticket_messages(ticket_id: int) -> list[aiosqlite.Row]:
    _db.row_factory = aiosqlite.Row
    cur = await _db.execute(
        "SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY created_at ASC", (ticket_id,)
    )
    return await cur.fetchall()


async def list_open_tickets(limit: int = 5, offset: int = 0) -> list[aiosqlite.Row]:
    """Тикеты, которые ещё не закрыты (open / answered), новые сверху."""
    _db.row_factory = aiosqlite.Row
    cur = await _db.execute(
        "SELECT * FROM tickets WHERE status != 'closed' ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return await cur.fetchall()


async def count_open_tickets() -> int:
    cur = await _db.execute("SELECT COUNT(*) FROM tickets WHERE status != 'closed'")
    row = await cur.fetchone()
    return row[0]


async def close_ticket(ticket_id: int):
    await _db.execute(
        "UPDATE tickets SET status = 'closed', updated_at = ? WHERE id = ?", (_now(), ticket_id)
    )
    await _db.commit()
