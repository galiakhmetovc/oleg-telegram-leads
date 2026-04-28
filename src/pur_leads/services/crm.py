"""CRM memory behavior."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.repositories.audit import AuditRepository
from pur_leads.repositories.crm import (
    ClientAssetRecord,
    ClientInterestRecord,
    ClientObjectRecord,
    ClientRecord,
    ContactReasonRecord,
    ContactRecord,
    CrmRepository,
    OpportunityRecord,
    SupportCaseRecord,
    TouchpointRecord,
)
from pur_leads.repositories.leads import CrmConversionActionRecord, LeadRepository
from pur_leads.repositories.tasks import TaskRecord, TaskRepository


@dataclass(frozen=True)
class ClientProfile:
    client: ClientRecord
    contacts: list[ContactRecord]
    objects: list[ClientObjectRecord]
    interests: list[ClientInterestRecord]
    assets: list[ClientAssetRecord]
    opportunities: list[OpportunityRecord]
    support_cases: list[SupportCaseRecord]
    contact_reasons: list[ContactReasonRecord]
    touchpoints: list[TouchpointRecord]


@dataclass(frozen=True)
class DuplicateHint:
    match_type: str
    client_id: str
    client_display_name: str
    contact_id: str
    matched_value: str
    confidence: float


@dataclass(frozen=True)
class LeadClusterConversionResult:
    client: ClientRecord
    contact: ContactRecord | None
    client_object: ClientObjectRecord | None
    interest: ClientInterestRecord | None
    task: TaskRecord | None
    action: CrmConversionActionRecord
    primary_entity_type: str
    primary_entity_id: str


class CrmService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CrmRepository(session)
        self.leads = LeadRepository(session)
        self.tasks = TaskRepository(session)
        self.audit = AuditRepository(session)

    def create_client_profile(
        self,
        *,
        actor: str,
        display_name: str,
        client_type: str = "unknown",
        status: str = "active",
        source_type: str = "manual",
        source_id: str | None = None,
        owner_user_id: str | None = None,
        assignee_user_id: str | None = None,
        notes: str | None = None,
        metadata_json: Any = None,
        contacts: list[dict[str, Any]] | None = None,
        objects: list[dict[str, Any]] | None = None,
        interests: list[dict[str, Any]] | None = None,
        assets: list[dict[str, Any]] | None = None,
        opportunities: list[dict[str, Any]] | None = None,
        support_cases: list[dict[str, Any]] | None = None,
        contact_reasons: list[dict[str, Any]] | None = None,
        touchpoints: list[dict[str, Any]] | None = None,
    ) -> ClientProfile:
        now = utc_now()
        client = self.repository.create_client(
            client_type=client_type,
            display_name=display_name,
            status=status,
            source_type=source_type,
            source_id=source_id,
            owner_user_id=owner_user_id,
            assignee_user_id=assignee_user_id,
            notes=notes,
            metadata_json=metadata_json,
            created_at=now,
            updated_at=now,
        )
        created_contacts = [
            self._create_contact(client.id, contact, now=now, fallback_primary=index == 0)
            for index, contact in enumerate(contacts or [])
        ]
        created_objects = [
            self._create_object(client.id, client_object, now=now)
            for client_object in objects or []
        ]
        created_interests = [
            self._create_interest(client.id, interest, now=now) for interest in interests or []
        ]
        created_assets = [self._create_asset(client.id, asset, now=now) for asset in assets or []]
        created_opportunities = [
            self._create_opportunity(client.id, opportunity, now=now)
            for opportunity in opportunities or []
        ]
        created_support_cases = [
            self._create_support_case(client.id, support_case, now=now)
            for support_case in support_cases or []
        ]
        created_contact_reasons = [
            self._create_contact_reason(client.id, reason, now=now)
            for reason in contact_reasons or []
        ]
        created_touchpoints = [
            self._create_touchpoint(client.id, touchpoint, actor=actor, now=now)
            for touchpoint in touchpoints or []
        ]
        self.audit.record_change(
            actor=actor,
            action="crm.client_profile_created",
            entity_type="client",
            entity_id=client.id,
            old_value_json=None,
            new_value_json={
                "display_name": client.display_name,
                "contact_count": len(created_contacts),
                "object_count": len(created_objects),
                "interest_count": len(created_interests),
                "asset_count": len(created_assets),
                "contact_reason_count": len(created_contact_reasons),
            },
        )
        self.session.commit()
        return ClientProfile(
            client=client,
            contacts=created_contacts,
            objects=created_objects,
            interests=created_interests,
            assets=created_assets,
            opportunities=created_opportunities,
            support_cases=created_support_cases,
            contact_reasons=created_contact_reasons,
            touchpoints=created_touchpoints,
        )

    def get_client_profile(self, client_id: str) -> ClientProfile:
        client = self.repository.get_client(client_id)
        if client is None:
            raise KeyError(client_id)
        return ClientProfile(
            client=client,
            contacts=self.repository.list_contacts(client_id),
            objects=self.repository.list_objects(client_id),
            interests=self.repository.list_interests(client_id),
            assets=self.repository.list_assets(client_id),
            opportunities=self.repository.list_opportunities(client_id),
            support_cases=self.repository.list_support_cases(client_id),
            contact_reasons=self.repository.list_contact_reasons(client_id),
            touchpoints=self.repository.list_touchpoints(client_id),
        )

    def find_duplicate_hints(
        self,
        *,
        telegram_user_id: str | None = None,
        telegram_username: str | None = None,
        phone: str | None = None,
        email: str | None = None,
    ) -> list[DuplicateHint]:
        checks = [
            ("telegram_user_id", telegram_user_id),
            ("telegram_username", _normalize_telegram_username(telegram_username)),
            ("phone", _normalize_phone(phone)),
            ("email", _normalize_email(email)),
        ]
        hints: list[DuplicateHint] = []
        seen: set[tuple[str, str]] = set()
        for match_type, value in checks:
            if not value:
                continue
            for contact in self.repository.find_contacts_by_field(match_type, value):
                key = (match_type, contact.id)
                if key in seen:
                    continue
                seen.add(key)
                client = self.repository.get_client(contact.client_id)
                if client is None:
                    continue
                hints.append(
                    DuplicateHint(
                        match_type=match_type,
                        client_id=client.id,
                        client_display_name=client.display_name,
                        contact_id=contact.id,
                        matched_value=value,
                        confidence=1.0,
                    )
                )
        return hints

    def convert_lead_cluster(
        self,
        lead_cluster_id: str,
        *,
        actor: str,
        client: dict[str, Any] | None = None,
        contact: dict[str, Any] | None = None,
        client_object: dict[str, Any] | None = None,
        interest: dict[str, Any] | None = None,
        task: dict[str, Any] | None = None,
        link_existing_client_id: str | None = None,
        used_candidate_ids: list[str] | None = None,
        owner_user_id: str | None = None,
        assignee_user_id: str | None = None,
    ) -> LeadClusterConversionResult:
        cluster = self.leads.get_cluster(lead_cluster_id)
        if cluster is None:
            raise KeyError(lead_cluster_id)

        now = utc_now()
        duplicate_hints = self.find_duplicate_hints(
            telegram_user_id=(contact or {}).get("telegram_user_id"),
            telegram_username=(contact or {}).get("telegram_username"),
            phone=(contact or {}).get("phone"),
            email=(contact or {}).get("email"),
        )
        if link_existing_client_id is None and duplicate_hints:
            raise ValueError("duplicate contact identity requires link_existing_client_id")

        linked_client: ClientRecord
        if link_existing_client_id is not None:
            linked_client = self.repository.get_client(link_existing_client_id)
            if linked_client is None:
                raise KeyError(link_existing_client_id)
            conflicting_hints = [
                hint for hint in duplicate_hints if hint.client_id != link_existing_client_id
            ]
            if conflicting_hints:
                raise ValueError("duplicate contact identity belongs to another client")
        else:
            client_values = client or {}
            linked_client = self.repository.create_client(
                client_type=client_values.get("client_type", "unknown"),
                display_name=client_values.get("display_name") or cluster.primary_sender_name or "Unknown",
                status=client_values.get("status", "active"),
                source_type="lead",
                source_id=cluster.id,
                owner_user_id=client_values.get("owner_user_id"),
                assignee_user_id=client_values.get("assignee_user_id"),
                notes=client_values.get("notes"),
                metadata_json=client_values.get("metadata_json"),
                created_at=now,
                updated_at=now,
            )

        created_contact = self._maybe_create_conversion_contact(
            linked_client.id,
            contact,
            duplicate_hints=duplicate_hints,
            now=now,
        )
        created_object = (
            self._create_object(linked_client.id, client_object, now=now)
            if client_object is not None
            else None
        )
        created_interest = None
        if interest is not None:
            interest_values = {
                **interest,
                "source_type": "lead",
                "source_id": cluster.id,
                "category_id": interest.get("category_id", cluster.category_id),
                "client_object_id": interest.get(
                    "client_object_id", created_object.id if created_object else None
                ),
            }
            created_interest = self._create_interest(linked_client.id, interest_values, now=now)

        created_task = self._maybe_create_conversion_task(
            cluster_id=cluster.id,
            lead_event_id=cluster.primary_lead_event_id,
            client_id=linked_client.id,
            values=task,
            owner_user_id=owner_user_id,
            assignee_user_id=assignee_user_id,
            now=now,
        )
        primary_entity_type, primary_entity_id, action_type, work_outcome = _conversion_primary(
            interest=created_interest,
            task=created_task,
            client=linked_client,
        )
        action = self.leads.create_crm_conversion_action(
            lead_cluster_id=cluster.id,
            action_type=action_type,
            used_candidate_ids_json=used_candidate_ids or [],
            created_entity_type=primary_entity_type,
            created_entity_id=primary_entity_id,
            linked_client_id=linked_client.id,
            linked_contact_id=created_contact.id if created_contact else None,
            manual_changes_json={
                "created_contact_id": created_contact.id if created_contact else None,
                "created_object_id": created_object.id if created_object else None,
                "created_task_id": created_task.id if created_task else None,
            },
            next_step=task.get("title") if task else None,
            next_step_at=created_task.due_at if created_task else None,
            created_by=actor,
            created_at=now,
        )
        self.leads.update_cluster(
            cluster.id,
            cluster_status="converted",
            review_status="confirmed",
            work_outcome=work_outcome,
            primary_task_id=created_task.id if created_task else cluster.primary_task_id,
            converted_entity_type=primary_entity_type,
            converted_entity_id=primary_entity_id,
            crm_conversion_action_id=action.id,
            updated_at=now,
        )
        self.audit.record_change(
            actor=actor,
            action="crm.lead_cluster_converted",
            entity_type="lead_cluster",
            entity_id=cluster.id,
            old_value_json={
                "cluster_status": cluster.cluster_status,
                "converted_entity_type": cluster.converted_entity_type,
                "converted_entity_id": cluster.converted_entity_id,
            },
            new_value_json={
                "cluster_status": "converted",
                "converted_entity_type": primary_entity_type,
                "converted_entity_id": primary_entity_id,
                "linked_client_id": linked_client.id,
                "crm_conversion_action_id": action.id,
            },
        )
        self.session.commit()
        return LeadClusterConversionResult(
            client=linked_client,
            contact=created_contact,
            client_object=created_object,
            interest=created_interest,
            task=created_task,
            action=action,
            primary_entity_type=primary_entity_type,
            primary_entity_id=primary_entity_id,
        )

    def _create_contact(
        self,
        client_id: str,
        values: dict[str, Any],
        *,
        now: datetime,
        fallback_primary: bool,
    ) -> ContactRecord:
        return self.repository.create_contact(
            client_id=client_id,
            contact_name=values.get("contact_name"),
            telegram_user_id=values.get("telegram_user_id"),
            telegram_username=_normalize_telegram_username(values.get("telegram_username")),
            phone=_normalize_phone(values.get("phone")),
            email=_normalize_email(values.get("email")),
            whatsapp=_normalize_phone(values.get("whatsapp")),
            preferred_channel=values.get("preferred_channel", "unknown"),
            source_type=values.get("source_type", "manual"),
            source_id=values.get("source_id"),
            is_primary=values.get("is_primary", fallback_primary),
            notes=values.get("notes"),
            metadata_json=values.get("metadata_json"),
            created_at=now,
            updated_at=now,
        )

    def _maybe_create_conversion_contact(
        self,
        client_id: str,
        values: dict[str, Any] | None,
        *,
        duplicate_hints: list[DuplicateHint],
        now: datetime,
    ) -> ContactRecord | None:
        if values is None:
            return None
        if any(hint.client_id == client_id for hint in duplicate_hints):
            return None
        return self._create_contact(
            client_id,
            {**values, "source_type": "lead"},
            now=now,
            fallback_primary=False,
        )

    def _create_object(
        self,
        client_id: str,
        values: dict[str, Any],
        *,
        now: datetime,
    ) -> ClientObjectRecord:
        object_type = values.get("object_type", "unknown")
        return self.repository.create_object(
            client_id=client_id,
            object_type=object_type,
            name=values.get("name") or object_type,
            location_text=values.get("location_text"),
            project_stage=values.get("project_stage", "unknown"),
            notes=values.get("notes"),
            metadata_json=values.get("metadata_json"),
            created_at=now,
            updated_at=now,
        )

    def _create_interest(
        self,
        client_id: str,
        values: dict[str, Any],
        *,
        now: datetime,
    ) -> ClientInterestRecord:
        return self.repository.create_interest(
            client_id=client_id,
            client_object_id=values.get("client_object_id"),
            category_id=values.get("category_id"),
            catalog_item_id=values.get("catalog_item_id"),
            catalog_term_id=values.get("catalog_term_id"),
            interest_text=values["interest_text"],
            interest_status=values.get("interest_status", "interested"),
            source_type=values.get("source_type", "manual"),
            source_id=values.get("source_id"),
            last_seen_at=values.get("last_seen_at", now),
            next_check_at=values.get("next_check_at"),
            notes=values.get("notes"),
            metadata_json=values.get("metadata_json"),
            created_at=now,
            updated_at=now,
        )

    def _create_asset(
        self,
        client_id: str,
        values: dict[str, Any],
        *,
        now: datetime,
    ) -> ClientAssetRecord:
        return self.repository.create_asset(
            client_id=client_id,
            client_object_id=values.get("client_object_id"),
            category_id=values.get("category_id"),
            catalog_item_id=values.get("catalog_item_id"),
            asset_name=values["asset_name"],
            asset_status=values.get("asset_status", "unknown"),
            installed_at=values.get("installed_at"),
            warranty_until=values.get("warranty_until"),
            service_due_at=values.get("service_due_at"),
            source_type=values.get("source_type", "manual"),
            source_id=values.get("source_id"),
            notes=values.get("notes"),
            metadata_json=values.get("metadata_json"),
            created_at=now,
            updated_at=now,
        )

    def _create_opportunity(
        self,
        client_id: str,
        values: dict[str, Any],
        *,
        now: datetime,
    ) -> OpportunityRecord:
        return self.repository.create_opportunity(
            client_id=client_id,
            client_object_id=values.get("client_object_id"),
            source_lead_cluster_id=values.get("source_lead_cluster_id"),
            source_lead_event_id=values.get("source_lead_event_id"),
            primary_category_id=values.get("primary_category_id"),
            title=values["title"],
            status=values.get("status", "new"),
            lost_reason=values.get("lost_reason"),
            estimated_value=values.get("estimated_value"),
            currency=values.get("currency"),
            owner_user_id=values.get("owner_user_id"),
            assignee_user_id=values.get("assignee_user_id"),
            next_step=values.get("next_step"),
            next_step_at=values.get("next_step_at"),
            notes=values.get("notes"),
            metadata_json=values.get("metadata_json"),
            created_at=now,
            updated_at=now,
            closed_at=values.get("closed_at"),
        )

    def _create_support_case(
        self,
        client_id: str,
        values: dict[str, Any],
        *,
        now: datetime,
    ) -> SupportCaseRecord:
        return self.repository.create_support_case(
            client_id=client_id,
            client_object_id=values.get("client_object_id"),
            client_asset_id=values.get("client_asset_id"),
            source_lead_cluster_id=values.get("source_lead_cluster_id"),
            source_lead_event_id=values.get("source_lead_event_id"),
            title=values["title"],
            status=values.get("status", "new"),
            priority=values.get("priority", "normal"),
            issue_text=values.get("issue_text"),
            resolution_text=values.get("resolution_text"),
            owner_user_id=values.get("owner_user_id"),
            assignee_user_id=values.get("assignee_user_id"),
            metadata_json=values.get("metadata_json"),
            created_at=now,
            updated_at=now,
            closed_at=values.get("closed_at"),
        )

    def _create_contact_reason(
        self,
        client_id: str,
        values: dict[str, Any],
        *,
        now: datetime,
    ) -> ContactReasonRecord:
        return self.repository.create_contact_reason(
            client_id=client_id,
            contact_id=values.get("contact_id"),
            client_object_id=values.get("client_object_id"),
            client_interest_id=values.get("client_interest_id"),
            client_asset_id=values.get("client_asset_id"),
            catalog_item_id=values.get("catalog_item_id"),
            catalog_offer_id=values.get("catalog_offer_id"),
            catalog_attribute_id=values.get("catalog_attribute_id"),
            source_id=values.get("source_id"),
            source_lead_cluster_id=values.get("source_lead_cluster_id"),
            source_lead_event_id=values.get("source_lead_event_id"),
            reason_type=values.get("reason_type", "manual"),
            title=values["title"],
            reason_text=values["reason_text"],
            priority=values.get("priority", "normal"),
            status=values.get("status", "new"),
            due_at=values.get("due_at"),
            snoozed_until=values.get("snoozed_until"),
            metadata_json=values.get("metadata_json"),
            created_at=now,
            updated_at=now,
        )

    def _create_touchpoint(
        self,
        client_id: str,
        values: dict[str, Any],
        *,
        actor: str,
        now: datetime,
    ) -> TouchpointRecord:
        return self.repository.create_touchpoint(
            client_id=client_id,
            contact_id=values.get("contact_id"),
            opportunity_id=values.get("opportunity_id"),
            support_case_id=values.get("support_case_id"),
            contact_reason_id=values.get("contact_reason_id"),
            lead_cluster_id=values.get("lead_cluster_id"),
            lead_event_id=values.get("lead_event_id"),
            channel=values.get("channel", "other"),
            direction=values.get("direction", "internal_note"),
            summary=values["summary"],
            outcome=values.get("outcome"),
            next_step=values.get("next_step"),
            created_by=values.get("created_by", actor),
            created_at=now,
        )

    def _maybe_create_conversion_task(
        self,
        *,
        cluster_id: str,
        lead_event_id: str | None,
        client_id: str,
        values: dict[str, Any] | None,
        owner_user_id: str | None,
        assignee_user_id: str | None,
        now: datetime,
    ) -> TaskRecord | None:
        if values is None:
            return None
        task = self.tasks.create(
            client_id=client_id,
            lead_cluster_id=cluster_id,
            lead_event_id=lead_event_id,
            opportunity_id=None,
            support_case_id=None,
            contact_reason_id=None,
            title=values.get("title", "Contact client"),
            description=values.get("description"),
            status=values.get("status", "open"),
            priority=values.get("priority", "normal"),
            due_at=values.get("due_at", now),
            owner_user_id=owner_user_id,
            assignee_user_id=assignee_user_id or owner_user_id,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        return task


def _normalize_telegram_username(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower().removeprefix("@")
    return normalized or None


def _normalize_email(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def _normalize_phone(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    digits = re.sub(r"\D+", "", raw)
    if not digits:
        return None
    return f"+{digits}" if raw.startswith("+") else digits


def _conversion_primary(
    *,
    interest: ClientInterestRecord | None,
    task: TaskRecord | None,
    client: ClientRecord,
) -> tuple[str, str, str, str]:
    if interest is not None:
        return "client_interest", interest.id, "create_interest", "client_interest_created"
    if task is not None:
        return "client", client.id, "create_client", "contact_task_created"
    return "client", client.id, "create_client", "contact_task_created"
