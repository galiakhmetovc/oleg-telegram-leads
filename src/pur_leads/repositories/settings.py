"""Settings persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.settings import settings_revisions_table, settings_table


@dataclass(frozen=True)
class SettingRecord:
    id: str
    key: str
    value_json: Any
    value_type: str
    scope: str
    scope_id: str
    description: str | None
    requires_restart: bool
    is_secret_ref: bool
    updated_by: str
    updated_at: datetime


class SettingsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(
        self,
        key: str,
        scope: str = "global",
        scope_id: str | None = None,
    ) -> SettingRecord | None:
        row = (
            self.session.execute(
                select(settings_table).where(
                    settings_table.c.key == key,
                    settings_table.c.scope == scope,
                    settings_table.c.scope_id == self._scope_id(scope_id),
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return SettingRecord(**dict(row))

    def set(
        self,
        key: str,
        value: Any,
        value_type: str,
        updated_by: str,
        updated_at: datetime,
        *,
        scope: str = "global",
        scope_id: str | None = None,
        description: str | None = None,
        requires_restart: bool = False,
        is_secret_ref: bool = False,
    ) -> SettingRecord:
        normalized_scope_id = self._scope_id(scope_id)
        existing = self.get(key, scope=scope, scope_id=normalized_scope_id)

        values = {
            "key": key,
            "value_json": value,
            "value_type": value_type,
            "scope": scope,
            "scope_id": normalized_scope_id,
            "description": description,
            "requires_restart": requires_restart,
            "is_secret_ref": is_secret_ref,
            "updated_by": updated_by,
            "updated_at": updated_at,
        }

        if existing is None:
            setting_id = new_id()
            self.session.execute(insert(settings_table).values(id=setting_id, **values))
        else:
            setting_id = existing.id
            self.session.execute(
                update(settings_table).where(settings_table.c.id == setting_id).values(**values)
            )

        return self.get(key, scope=scope, scope_id=normalized_scope_id)  # type: ignore[return-value]

    def list(self, scope: str | None = None) -> list[SettingRecord]:
        statement = select(settings_table)
        if scope is not None:
            statement = statement.where(settings_table.c.scope == scope)
        rows = self.session.execute(statement).mappings().all()
        return [SettingRecord(**dict(row)) for row in rows]

    def add_revision(
        self,
        *,
        setting_key: str,
        scope: str,
        scope_id: str | None,
        old_value_hash: str | None,
        new_value_hash: str,
        old_value_json: Any,
        new_value_json: Any,
        changed_by: str,
        change_reason: str | None,
        created_at: datetime,
    ) -> None:
        self.session.execute(
            insert(settings_revisions_table).values(
                id=new_id(),
                setting_key=setting_key,
                scope=scope,
                scope_id=self._scope_id(scope_id),
                old_value_hash=old_value_hash,
                new_value_hash=new_value_hash,
                old_value_json=old_value_json,
                new_value_json=new_value_json,
                changed_by=changed_by,
                change_reason=change_reason,
                created_at=created_at,
            )
        )

    @staticmethod
    def _scope_id(scope_id: str | None) -> str:
        return scope_id or ""
