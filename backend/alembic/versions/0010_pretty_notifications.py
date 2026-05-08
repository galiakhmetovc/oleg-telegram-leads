"""pretty notification template

Revision ID: 0010_pretty_notifications
Revises: 0009_runtime_log_indexes
Create Date: 2026-05-08
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0010_pretty_notifications"
down_revision: str | None = "0009_runtime_log_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHANNEL = "telegram_routing"
OLD_TEMPLATE = (
    "Найден лид ПУР\n"
    "Score: {score}\n"
    "Температура: {temperature}\n"
    "Очередь: {review_lane}\n"
    "Текст: {text}"
)
NEW_TEMPLATE = (
    "Лид ПУР\n\n"
    "Оценка: {score} ({temperature})\n"
    "Очередь: {review_lane_label}\n"
    "Зоны решения: {solution_areas}\n"
    "Сегменты: {customer_segments}\n\n"
    "Почему сработало:\n"
    "{reasons_detailed}\n\n"
    "Текст:\n"
    "{text_preview}"
)


def upgrade() -> None:
    _replace_template(OLD_TEMPLATE, NEW_TEMPLATE)


def downgrade() -> None:
    _replace_template(NEW_TEMPLATE, OLD_TEMPLATE)


def _replace_template(old: str, new: str) -> None:
    bind = op.get_bind()
    row = bind.execute(
        sa.text("select config from notification_settings where channel = :channel"),
        {"channel": CHANNEL},
    ).mappings().first()
    if row is None:
        return
    config = dict(row["config"] or {})
    routes = config.get("routes")
    if not isinstance(routes, list):
        return
    changed = False
    for item in routes:
        if isinstance(item, dict) and item.get("message_template") == old:
            item["message_template"] = new
            changed = True
    if not changed:
        return
    statement = sa.text(
        """
        update notification_settings
        set config = :config,
            updated_at = now()
        where channel = :channel
        """
    ).bindparams(sa.bindparam("config", type_=JSONB))
    bind.execute(statement, {"channel": CHANNEL, "config": _jsonable(config)})


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
