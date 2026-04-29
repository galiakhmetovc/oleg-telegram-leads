#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

git pull --ff-only origin main
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --no-build --force-recreate
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
curl -fsS "http://127.0.0.1:${PUR_WEB_PORT:-8000}/health"
printf '\n'
