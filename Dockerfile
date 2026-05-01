FROM node:22-slim AS web-assets

WORKDIR /app

COPY package.json package-lock.json ./
COPY src/pur_leads/web/assets ./src/pur_leads/web/assets

RUN npm ci
RUN npm run build:assets


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY --from=web-assets /app/src/pur_leads/web/static/vendor ./src/pur_leads/web/static/vendor
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

RUN uv sync --frozen --no-dev

ENTRYPOINT ["uv", "run", "--no-dev", "pur-leads"]
