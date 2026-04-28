FROM python:3.12-slim

WORKDIR /app

# Системные зависимости для Telethon
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Исходный код
COPY src/ src/
COPY docs/ docs/
COPY tg-connect.py tg-auth.py .gitignore .env.example config.example.py ./

# Директории для данных (сессии, чекпоинты, лиды, логи)
RUN mkdir -p /app/data /app/artifacts/logs /app/vault/05-Journal/oleg-telegram-leads /app/notes
RUN mkdir -p /app/data /app/artifacts /app/vault/05-Journal/oleg-telegram-leads /app/notes

# Volumes
VOLUME ["/app/data", "/app/vault", "/app/sessions", "/app/artifacts"]

# Запуск: daemon-режим по умолчанию
CMD ["python", "src/pipeline.py", "--daemon"]
