#!/bin/bash
# Сброс данных бота + пересборка контейнера
# Выполнять из корня проекта: bash reset_and_rebuild.sh

set -e

echo "=== 1. Сброс данных внутри контейнера ==="
docker exec leads-finder sh -c 'echo "[]" > /app/data/chats.json && echo "{}" > /app/data/checkpoints.json && echo "[]" > /app/data/leads.json && echo "Данные сброшены"'

echo "=== 2. Пересборка образа ==="
docker compose build --no-cache 2>&1 | tail -5

echo "=== 3. Перезапуск контейнера ==="
docker compose down 2>&1
docker compose up -d 2>&1

echo "=== 4. Ожидание запуска (5 сек) ==="
sleep 5

echo "=== 5. Лог запуска ==="
docker logs --tail 20 leads-finder 2>&1

echo ""
echo "=== Готово! Отправь ссылку в управляющую группу ==="
