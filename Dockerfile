FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

RUN uv sync --frozen --no-dev

ENTRYPOINT ["uv", "run", "--no-dev", "pur-leads"]
