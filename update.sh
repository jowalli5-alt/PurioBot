#!/usr/bin/env bash
# Безопасное обновление бота из GitHub.
# База данных (data/bot.db) и .env НЕ трогаются: они лежат в .gitignore,
# поэтому git pull их не видит и не может перезаписать.
#
# Использование: ./update.sh   (запускать из папки проекта)

set -e

echo "== Обновление PurioVPN Bot =="

if [ -f "data/bot.db" ] || [ -f "bot.db" ]; then
    mkdir -p backups
    ts=$(date +%Y%m%d_%H%M%S)
    src="data/bot.db"
    [ -f "bot.db" ] && [ ! -f "data/bot.db" ] && src="bot.db"
    cp "$src" "backups/bot_${ts}.db"
    echo "Бэкап БД сохранён: backups/bot_${ts}.db"
fi

echo "-- git pull --"
git pull

echo "-- зависимости --"
if [ -d "venv" ]; then
    source venv/bin/activate
fi
pip install -r requirements.txt --upgrade

echo "-- перезапуск сервиса --"
if systemctl list-units --full -all | grep -q "purio-bot.service"; then
    sudo systemctl restart purio-bot
    echo "Сервис purio-bot перезапущен."
else
    echo "Systemd-сервис purio-bot не найден — перезапусти бота вручную."
fi

echo "== Готово =="
