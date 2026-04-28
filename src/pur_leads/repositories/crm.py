"""CRM memory persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.crm import (
    client_assets_table,
    client_interests_table,
    client_objects_table,
    clients_table,
    contact_reasons_table,
    contacts_table,
    opportunities_table,
    support_cases_table,
    touchpoints_table,
)


@dataclass(frozen=True)
class ClientRecord:
    id: str
    client_type: str
    display_name: str
    status: str
    source_type: str
    source_id: str | None
    owner_user_id: str | None
    assignee_user_id: str | None
    notes: str | None
    metadata_json: Any
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ContactRecord:
    id: str
    client_id: str
    contact_name: str | None
    telegram_user_id: str | None
    telegram_username: str | None
    phone: str | None
    email: str | None
    whatsapp: str | None
    preferred_channel: str
    source_type: str
    source_id: str | None
    is_primary: bool
    notes: str | None
    metadata_json: Any
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ClientObjectRecord:
    id: str
    client_id: str
    object_type: str
    name: str
    location_text: str | None
    project_stage: str
    notes: str | None
    metadata_json: Any
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ClientInterestRecord:
    id: str
    client_id: str
    client_object_id: str | None
    category_id: str | None
    catalog_item_id: str | None
    catalog_term_id: str | None
    interest_text: str
    interest_status: str
    source_type: str
    source_id: str | None
    last_seen_at: datetime | None
    next_check_at: datetime | None
    notes: str | None
    metadata_json: Any
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ClientAssetRecord:
    id: str
    client_id: str
    client_object_id: str | None
    category_id: str | None
    catalog_item_id: str | None
    asset_name: str
    asset_status: str
    installed_at: datetime | None
    warranty_until: datetime | None
    service_due_at: datetime | None
    source_type: str
    source_id: str | None
    notes: str | None
    metadata_json: Any
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class OpportunityRecord:
    id: str
    client_id: str
    client_object_id: str | None
    source_lead_cluster_id: str | None
    source_lead_event_id: str | None
    primary_category_id: str | None
    title: str
    status: str
    lost_reason: str | None
    estimated_value: float | None
    currency: str | None
    owner_user_id: str | None
    assignee_user_id: str | None
    next_step: str | None
    next_step_at: datetime | None
    notes: str | None
    metadata_json: Any
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


@dataclass(frozen=True)
class SupportCaseRecord:
    id: str
    client_id: str
    client_object_id: str | None
    client_asset_id: str | None
    source_lead_cluster_id: str | None
    source_lead_event_id: str | None
    title: str
    status: str
    priority: str
    issue_text: str | None
    resolution_text: str | None
    owner_user_id: str | None
    assignee_user_id: str | None
    metadata_json: Any
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


@dataclass(frozen=True)
class ContactReasonRecord:
    id: str
    client_id: str
    contact_id: str | None
    client_object_id: str | None
    client_interest_id: str | None
    client_asset_id: str | None
    catalog_item_id: str | None
    catalog_offer_id: str | None
    catalog_attribute_id: str | None
    source_id: str | None
    source_lead_cluster_id: str | None
    source_lead_event_id: str | None
    reason_type: str
    title: str
    reason_text: str
    priority: str
    status: str
    due_at: datetime | None
    snoozed_until: datetime | None
    metadata_json: Any
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class TouchpointRecord:
    id: str
    client_id: str
    contact_id: str | None
    opportunity_id: str | None
    support_case_id: str | None
    contact_reason_id: str | None
    lead_cluster_id: str | None
    lead_event_id: str | None
    channel: str
    direction: str
    summary: str
    outcome: str | None
    next_step: str | None
    created_by: str
    created_at: datetime


class CrmRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_client(self, **values) -> ClientRecord:  # type: ignore[no-untyped-def]
        client_id = new_id()
        self.session.execute(insert(clients_table).values(id=client_id, **values))
        return self.get_client(client_id)  # type: ignore[return-value]

    def get_client(self, client_id: str) -> ClientRecord | None:
        row = (
            self.session.execute(select(clients_table).where(clients_table.c.id == client_id))
            .mappings()
            .first()
        )
        return ClientRecord(**dict(row)) if row is not None else None

    def list_clients(self, *, status: str | None = None, limit: int = 100) -> list[ClientRecord]:
        statement = select(clients_table).order_by(clients_table.c.updated_at.desc()).limit(limit)
        if status is not None:
            statement = statement.where(clients_table.c.status == status)
        rows = self.session.execute(statement).mappings().all()
        return [ClientRecord(**dict(row)) for row in rows]

    def create_contact(self, **values) -> ContactRecord:  # type: ignore[no-untyped-def]
        contact_id = new_id()
        self.session.execute(insert(contacts_table).values(id=contact_id, **values))
        return self.get_contact(contact_id)  # type: ignore[return-value]

    def get_contact(self, contact_id: str) -> ContactRecord | None:
        row = (
            self.session.execute(select(contacts_table).where(contacts_table.c.id == contact_id))
            .mappings()
            .first()
        )
        return ContactRecord(**dict(row)) if row is not None else None

    def list_contacts(self, client_id: str) -> list[ContactRecord]:
        rows = (
            self.session.execute(
                select(contacts_table)
                .where(contacts_table.c.client_id == client_id)
                .order_by(contacts_table.c.is_primary.desc(), contacts_table.c.created_at)
            )
            .mappings()
            .all()
        )
        return [ContactRecord(**dict(row)) for row in rows]

    def find_contacts_by_field(self, field: str, value: str) -> list[ContactRecord]:
        column = getattr(contacts_table.c, field)
        rows = (
            self.session.execute(select(contacts_table).where(column == value))
            .mappings()
            .all()
        )
        return [ContactRecord(**dict(row)) for row in rows]

    def create_object(self, **values) -> ClientObjectRecord:  # type: ignore[no-untyped-def]
        object_id = new_id()
        self.session.execute(insert(client_objects_table).values(id=object_id, **values))
        return self.get_object(object_id)  # type: ignore[return-value]

    def get_object(self, object_id: str) -> ClientObjectRecord | None:
        row = (
            self.session.execute(
                select(client_objects_table).where(client_objects_table.c.id == object_id)
            )
            .mappings()
            .first()
        )
        return ClientObjectRecord(**dict(row)) if row is not None else None

    def list_objects(self, client_id: str) -> list[ClientObjectRecord]:
        rows = (
            self.session.execute(
                select(client_objects_table)
                .where(client_objects_table.c.client_id == client_id)
                .order_by(client_objects_table.c.created_at)
            )
            .mappings()
            .all()
        )
        return [ClientObjectRecord(**dict(row)) for row in rows]

    def create_interest(self, **values) -> ClientInterestRecord:  # type: ignore[no-untyped-def]
        interest_id = new_id()
        self.session.execute(insert(client_interests_table).values(id=interest_id, **values))
        return self.get_interest(interest_id)  # type: ignore[return-value]

    def get_interest(self, interest_id: str) -> ClientInterestRecord | None:
        row = (
            self.session.execute(
                select(client_interests_table).where(client_interests_table.c.id == interest_id)
            )
            .mappings()
            .first()
        )
        return ClientInterestRecord(**dict(row)) if row is not None else None

    def list_interests(self, client_id: str) -> list[ClientInterestRecord]:
        rows = (
            self.session.execute(
                select(client_interests_table)
                .where(client_interests_table.c.client_id == client_id)
                .order_by(client_interests_table.c.updated_at.desc())
            )
            .mappings()
            .all()
        )
        return [ClientInterestRecord(**dict(row)) for row in rows]

    def create_asset(self, **values) -> ClientAssetRecord:  # type: ignore[no-untyped-def]
        asset_id = new_id()
        self.session.execute(insert(client_assets_table).values(id=asset_id, **values))
        return self.get_asset(asset_id)  # type: ignore[return-value]

    def get_asset(self, asset_id: str) -> ClientAssetRecord | None:
        row = (
            self.session.execute(
                select(client_assets_table).where(client_assets_table.c.id == asset_id)
            )
            .mappings()
            .first()
        )
        return ClientAssetRecord(**dict(row)) if row is not None else None

    def list_assets(self, client_id: str) -> list[ClientAssetRecord]:
        rows = (
            self.session.execute(
                select(client_assets_table)
                .where(client_assets_table.c.client_id == client_id)
                .order_by(client_assets_table.c.updated_at.desc())
            )
            .mappings()
            .all()
        )
        return [ClientAssetRecord(**dict(row)) for row in rows]

    def create_opportunity(self, **values) -> OpportunityRecord:  # type: ignore[no-untyped-def]
        opportunity_id = new_id()
        self.session.execute(insert(opportunities_table).values(id=opportunity_id, **values))
        return self.get_opportunity(opportunity_id)  # type: ignore[return-value]

    def get_opportunity(self, opportunity_id: str) -> OpportunityRecord | None:
        row = (
            self.session.execute(
                select(opportunities_table).where(opportunities_table.c.id == opportunity_id)
            )
            .mappings()
            .first()
        )
        return OpportunityRecord(**dict(row)) if row is not None else None

    def list_opportunities(self, client_id: str) -> list[OpportunityRecord]:
        rows = (
            self.session.execute(
                select(opportunities_table)
                .where(opportunities_table.c.client_id == client_id)
                .order_by(opportunities_table.c.updated_at.desc())
            )
            .mappings()
            .all()
        )
        return [OpportunityRecord(**dict(row)) for row in rows]

    def create_support_case(self, **values) -> SupportCaseRecord:  # type: ignore[no-untyped-def]
        case_id = new_id()
        self.session.execute(insert(support_cases_table).values(id=case_id, **values))
        return self.get_support_case(case_id)  # type: ignore[return-value]

    def get_support_case(self, case_id: str) -> SupportCaseRecord | None:
        row = (
            self.session.execute(
                select(support_cases_table).where(support_cases_table.c.id == case_id)
            )
            .mappings()
            .first()
        )
        return SupportCaseRecord(**dict(row)) if row is not None else None

    def list_support_cases(self, client_id: str) -> list[SupportCaseRecord]:
        rows = (
            self.session.execute(
                select(support_cases_table)
                .where(support_cases_table.c.client_id == client_id)
                .order_by(support_cases_table.c.updated_at.desc())
            )
            .mappings()
            .all()
        )
        return [SupportCaseRecord(**dict(row)) for row in rows]

    def create_contact_reason(self, **values) -> ContactReasonRecord:  # type: ignore[no-untyped-def]
        reason_id = new_id()
        self.session.execute(insert(contact_reasons_table).values(id=reason_id, **values))
        return self.get_contact_reason(reason_id)  # type: ignore[return-value]

    def get_contact_reason(self, reason_id: str) -> ContactReasonRecord | None:
        row = (
            self.session.execute(
                select(contact_reasons_table).where(contact_reasons_table.c.id == reason_id)
            )
            .mappings()
            .first()
        )
        return ContactReasonRecord(**dict(row)) if row is not None else None

    def list_contact_reasons(self, client_id: str) -> list[ContactReasonRecord]:
        rows = (
            self.session.execute(
                select(contact_reasons_table)
                .where(contact_reasons_table.c.client_id == client_id)
                .order_by(contact_reasons_table.c.status, contact_reasons_table.c.due_at)
            )
            .mappings()
            .all()
        )
        return [ContactReasonRecord(**dict(row)) for row in rows]

    def create_touchpoint(self, **values) -> TouchpointRecord:  # type: ignore[no-untyped-def]
        touchpoint_id = new_id()
        self.session.execute(insert(touchpoints_table).values(id=touchpoint_id, **values))
        return self.get_touchpoint(touchpoint_id)  # type: ignore[return-value]

    def get_touchpoint(self, touchpoint_id: str) -> TouchpointRecord | None:
        row = (
            self.session.execute(
                select(touchpoints_table).where(touchpoints_table.c.id == touchpoint_id)
            )
            .mappings()
            .first()
        )
        return TouchpointRecord(**dict(row)) if row is not None else None

    def list_touchpoints(self, client_id: str) -> list[TouchpointRecord]:
        rows = (
            self.session.execute(
                select(touchpoints_table)
                .where(touchpoints_table.c.client_id == client_id)
                .order_by(touchpoints_table.c.created_at.desc())
            )
            .mappings()
            .all()
        )
        return [TouchpointRecord(**dict(row)) for row in rows]
