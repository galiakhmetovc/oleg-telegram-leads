"""Shared metadata update helpers for Telegram raw export runs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pur_leads.models.telegram_sources import telegram_raw_export_runs_table


def merge_raw_export_run_metadata(
    session: Session,
    raw_export_run_id: str,
    *,
    key: str,
    value: dict[str, Any],
) -> None:
    """Merge one metadata block without dropping concurrently written blocks."""
    row = (
        session.execute(
            select(telegram_raw_export_runs_table.c.metadata_json).where(
                telegram_raw_export_runs_table.c.id == raw_export_run_id
            )
        )
        .mappings()
        .one()
    )
    metadata = dict(row["metadata_json"] or {})
    metadata[key] = value
    session.execute(
        update(telegram_raw_export_runs_table)
        .where(telegram_raw_export_runs_table.c.id == raw_export_run_id)
        .values(metadata_json=metadata)
    )
