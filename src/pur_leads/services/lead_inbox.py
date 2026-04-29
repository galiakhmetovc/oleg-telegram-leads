"""Lead inbox query service."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import Select, func, not_, or_, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.orm import Session

from pur_leads.models.catalog import (
    catalog_categories_table,
    catalog_items_table,
    catalog_terms_table,
)
from pur_leads.models.leads import (
    feedback_events_table,
    lead_cluster_actions_table,
    lead_cluster_members_table,
    lead_clusters_table,
    lead_events_table,
    lead_matches_table,
)
from pur_leads.models.telegram_sources import source_messages_table


@dataclass(frozen=True)
class LeadInboxFilters:
    status: str | None = None
    source_id: str | None = None
    category_id: str | None = None
    retro: bool | None = None
    maybe: bool | None = None
    auto_pending: bool | None = None
    operator_issues: bool | None = None
    min_confidence: float | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class LeadClusterQueueRow:
    cluster_id: str
    source_id: str | None
    primary_sender_id: str | None
    primary_sender_name: str | None
    primary_message: dict[str, Any]
    status: str
    review_status: str
    work_outcome: str
    confidence: float | None
    category: dict[str, str | None] | None
    matched_terms: list[dict[str, Any]]
    matched_items: list[dict[str, Any]]
    is_retro: bool
    is_maybe: bool
    has_auto_pending: bool
    has_auto_merge_pending: bool
    merge_strategy: str
    merge_reason: str | None
    event_count: int
    feedback_count: int
    crm_candidate_count: int
    primary_task_id: str | None


@dataclass(frozen=True)
class LeadInboxPagination:
    limit: int
    offset: int
    total: int
    has_more: bool


@dataclass(frozen=True)
class LeadInboxSummary:
    total: int
    by_status: dict[str, int]
    auto_pending: int
    retro: int
    maybe: int


@dataclass(frozen=True)
class LeadClusterQueuePage:
    items: list[LeadClusterQueueRow]
    pagination: LeadInboxPagination
    summary: LeadInboxSummary


@dataclass(frozen=True)
class LeadClusterDetail:
    cluster: LeadClusterQueueRow
    timeline: list[dict[str, Any]]
    events: list[dict[str, Any]]
    matches: list[dict[str, Any]]
    feedback: list[dict[str, Any]]


class LeadInboxService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_cluster_queue(
        self,
        filters: LeadInboxFilters | None = None,
    ) -> list[LeadClusterQueueRow]:
        filters = filters or LeadInboxFilters()
        query = (
            self._filtered_cluster_query(filters)
            .limit(_limit(filters.limit))
            .offset(_offset(filters.offset))
        )

        cluster_rows = self.session.execute(query).mappings().all()
        return self._queue_rows([dict(row) for row in cluster_rows])

    def list_cluster_page(
        self,
        filters: LeadInboxFilters | None = None,
    ) -> LeadClusterQueuePage:
        filters = filters or LeadInboxFilters()
        limit = _limit(filters.limit)
        offset = _offset(filters.offset)
        filters = replace(filters, limit=limit, offset=offset)
        total = self.count_cluster_queue(filters)
        items = self.list_cluster_queue(filters)
        return LeadClusterQueuePage(
            items=items,
            pagination=LeadInboxPagination(
                limit=limit,
                offset=offset,
                total=total,
                has_more=offset + len(items) < total,
            ),
            summary=self.queue_summary(filters, total=total),
        )

    def count_cluster_queue(self, filters: LeadInboxFilters | None = None) -> int:
        filters = filters or LeadInboxFilters()
        query = self._filtered_cluster_query(filters).order_by(None).subquery()
        return self.session.scalar(select(func.count()).select_from(query)) or 0

    def queue_summary(
        self,
        filters: LeadInboxFilters | None = None,
        *,
        total: int | None = None,
    ) -> LeadInboxSummary:
        filters = filters or LeadInboxFilters()
        return LeadInboxSummary(
            total=total if total is not None else self.count_cluster_queue(filters),
            by_status=self._status_counts(filters),
            auto_pending=self.count_cluster_queue(
                replace(filters, auto_pending=True, operator_issues=None)
            ),
            retro=self.count_cluster_queue(replace(filters, retro=True, operator_issues=None)),
            maybe=self.count_cluster_queue(replace(filters, maybe=True, operator_issues=None)),
        )

    def get_cluster_detail(self, cluster_id: str) -> LeadClusterDetail:
        cluster = (
            self.session.execute(
                self._cluster_query().where(lead_clusters_table.c.id == cluster_id)
            )
            .mappings()
            .first()
        )
        if cluster is None:
            raise KeyError(cluster_id)

        row = self._queue_rows([dict(cluster)])[0]
        events = self._event_rows(cluster_id)
        matches = self._match_rows(cluster_id)
        feedback = self._feedback_rows(cluster_id)
        timeline = self._timeline(row, events, feedback)
        return LeadClusterDetail(
            cluster=row,
            timeline=timeline,
            events=events,
            matches=matches,
            feedback=feedback,
        )

    def _cluster_query(self) -> Select[tuple[Any, ...]]:
        return (
            select(
                lead_clusters_table.c.id.label("cluster_id"),
                lead_clusters_table.c.monitored_source_id.label("source_id"),
                lead_clusters_table.c.primary_sender_id,
                lead_clusters_table.c.primary_sender_name,
                lead_clusters_table.c.primary_source_message_id,
                lead_clusters_table.c.cluster_status,
                lead_clusters_table.c.review_status,
                lead_clusters_table.c.work_outcome,
                lead_clusters_table.c.confidence_max,
                lead_clusters_table.c.category_id,
                lead_clusters_table.c.lead_event_count,
                lead_clusters_table.c.last_message_at,
                lead_clusters_table.c.merge_strategy,
                lead_clusters_table.c.merge_reason,
                lead_clusters_table.c.crm_candidate_count,
                lead_clusters_table.c.primary_task_id,
                catalog_categories_table.c.name.label("category_name"),
                source_messages_table.c.telegram_message_id,
                source_messages_table.c.sender_id,
                source_messages_table.c.message_date,
                source_messages_table.c.text,
                source_messages_table.c.caption,
            )
            .select_from(
                lead_clusters_table.outerjoin(
                    catalog_categories_table,
                    lead_clusters_table.c.category_id == catalog_categories_table.c.id,
                ).outerjoin(
                    source_messages_table,
                    lead_clusters_table.c.primary_source_message_id == source_messages_table.c.id,
                )
            )
            .order_by(lead_clusters_table.c.last_message_at.desc())
        )

    def _filtered_cluster_query(
        self,
        filters: LeadInboxFilters,
    ) -> Select[tuple[Any, ...]]:
        query = self._cluster_query()
        if filters.status is not None:
            query = query.where(lead_clusters_table.c.cluster_status == filters.status)
        if filters.source_id is not None:
            query = query.where(lead_clusters_table.c.monitored_source_id == filters.source_id)
        if filters.category_id is not None:
            query = query.where(lead_clusters_table.c.category_id == filters.category_id)
        if filters.min_confidence is not None:
            query = query.where(lead_clusters_table.c.confidence_max >= filters.min_confidence)
        query = _apply_bool_filter(query, filters.retro, _retro_exists_expr())
        query = _apply_bool_filter(query, filters.maybe, _maybe_expr())
        query = _apply_bool_filter(query, filters.auto_pending, _auto_pending_expr())
        query = _apply_bool_filter(query, filters.operator_issues, _operator_issue_expr())
        return query

    def _status_counts(self, filters: LeadInboxFilters) -> dict[str, int]:
        query = self._filtered_cluster_query(replace(filters, status=None)).order_by(None)
        status_query = query.subquery()
        rows = (
            self.session.execute(
                select(status_query.c.cluster_status, func.count().label("count")).group_by(
                    status_query.c.cluster_status
                )
            )
            .mappings()
            .all()
        )
        return {row["cluster_status"]: row["count"] for row in rows}

    def _queue_rows(self, clusters: list[dict[str, Any]]) -> list[LeadClusterQueueRow]:
        cluster_ids = [cluster["cluster_id"] for cluster in clusters]
        if not cluster_ids:
            return []
        event_summaries = self._event_summaries_by_cluster(cluster_ids)
        match_rows = self._raw_match_rows_by_cluster(cluster_ids)
        feedback_counts = self._feedback_counts_by_cluster(
            cluster_ids,
            event_summaries=event_summaries,
            match_rows=match_rows,
        )
        auto_merge_cluster_ids = self._auto_merge_cluster_ids(cluster_ids)
        return [
            self._queue_row(
                cluster,
                event_summary=event_summaries[cluster["cluster_id"]],
                match_rows=match_rows[cluster["cluster_id"]],
                feedback_count=feedback_counts[cluster["cluster_id"]],
                auto_merge_cluster_ids=auto_merge_cluster_ids,
            )
            for cluster in clusters
        ]

    def _queue_row(
        self,
        cluster: dict[str, Any],
        *,
        event_summary: dict[str, Any],
        match_rows: list[dict[str, Any]],
        feedback_count: int,
        auto_merge_cluster_ids: set[str],
    ) -> LeadClusterQueueRow:
        cluster_id = cluster["cluster_id"]
        matched_terms = _unique_dicts(
            [
                {
                    "id": match["catalog_term_id"],
                    "text": match["catalog_term_text"],
                    "matched_text": match["matched_text"],
                    "status_at_detection": match["status_at_detection"],
                }
                for match in match_rows
                if match["catalog_term_id"] is not None
            ],
            key="id",
        )
        matched_items = _unique_dicts(
            [
                {
                    "id": match["catalog_item_id"],
                    "name": match["catalog_item_name"],
                    "status_at_detection": match["item_status_at_detection"],
                }
                for match in match_rows
                if match["catalog_item_id"] is not None
            ],
            key="id",
        )
        is_retro = event_summary["is_retro"]
        is_maybe = cluster["cluster_status"] == "maybe" or event_summary["is_maybe"]
        has_auto_pending = any(
            match["status_at_detection"] == "auto_pending"
            or match["item_status_at_detection"] == "auto_pending"
            for match in match_rows
        )
        return LeadClusterQueueRow(
            cluster_id=cluster_id,
            source_id=cluster["source_id"],
            primary_sender_id=cluster["primary_sender_id"],
            primary_sender_name=cluster["primary_sender_name"],
            primary_message={
                "id": cluster["primary_source_message_id"],
                "telegram_message_id": cluster["telegram_message_id"],
                "sender_id": cluster["sender_id"],
                "message_date": cluster["message_date"],
                "text": _message_text(cluster),
            },
            status=cluster["cluster_status"],
            review_status=cluster["review_status"],
            work_outcome=cluster["work_outcome"],
            confidence=cluster["confidence_max"],
            category=(
                {"id": cluster["category_id"], "name": cluster["category_name"]}
                if cluster["category_id"] is not None
                else None
            ),
            matched_terms=matched_terms,
            matched_items=matched_items,
            is_retro=is_retro,
            is_maybe=is_maybe,
            has_auto_pending=has_auto_pending,
            has_auto_merge_pending=cluster_id in auto_merge_cluster_ids,
            merge_strategy=cluster["merge_strategy"],
            merge_reason=cluster["merge_reason"],
            event_count=len(event_summary["event_ids"]),
            feedback_count=feedback_count,
            crm_candidate_count=cluster["crm_candidate_count"],
            primary_task_id=cluster["primary_task_id"],
        )

    def _event_summaries_by_cluster(self, cluster_ids: list[str]) -> dict[str, dict[str, Any]]:
        summaries: dict[str, dict[str, Any]] = {
            cluster_id: {"event_ids": [], "is_retro": False, "is_maybe": False}
            for cluster_id in cluster_ids
        }
        rows = (
            self.session.execute(
                select(
                    lead_events_table.c.id,
                    lead_events_table.c.lead_cluster_id,
                    lead_events_table.c.is_retro,
                    lead_events_table.c.decision,
                )
                .where(lead_events_table.c.lead_cluster_id.in_(cluster_ids))
                .order_by(lead_events_table.c.created_at)
            )
            .mappings()
            .all()
        )
        for row in rows:
            cluster_id = row["lead_cluster_id"]
            if cluster_id is None or cluster_id not in summaries:
                continue
            summaries[cluster_id]["event_ids"].append(row["id"])
            summaries[cluster_id]["is_retro"] = summaries[cluster_id]["is_retro"] or row["is_retro"]
            summaries[cluster_id]["is_maybe"] = (
                summaries[cluster_id]["is_maybe"] or row["decision"] == "maybe"
            )
        return summaries

    def _raw_match_rows_by_cluster(self, cluster_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        matches_by_cluster: dict[str, list[dict[str, Any]]] = {
            cluster_id: [] for cluster_id in cluster_ids
        }
        rows = (
            self.session.execute(
                self._match_query()
                .add_columns(lead_events_table.c.lead_cluster_id.label("cluster_id"))
                .where(lead_events_table.c.lead_cluster_id.in_(cluster_ids))
                .order_by(
                    lead_events_table.c.lead_cluster_id,
                    lead_matches_table.c.score.desc(),
                    lead_matches_table.c.created_at,
                )
            )
            .mappings()
            .all()
        )
        for row in rows:
            cluster_id = row["cluster_id"]
            if cluster_id is None or cluster_id not in matches_by_cluster:
                continue
            matches_by_cluster[cluster_id].append(_match_payload(dict(row)))
        return matches_by_cluster

    def _feedback_counts_by_cluster(
        self,
        cluster_ids: list[str],
        *,
        event_summaries: dict[str, dict[str, Any]],
        match_rows: dict[str, list[dict[str, Any]]],
    ) -> dict[str, int]:
        counts = {cluster_id: 0 for cluster_id in cluster_ids}
        event_to_cluster = {
            event_id: cluster_id
            for cluster_id, summary in event_summaries.items()
            for event_id in summary["event_ids"]
        }
        match_to_cluster = {
            match["match_id"]: cluster_id
            for cluster_id, matches in match_rows.items()
            for match in matches
            if match["match_id"] is not None
        }
        target_conditions: list[ColumnElement[bool]] = [
            (feedback_events_table.c.target_type == "lead_cluster")
            & feedback_events_table.c.target_id.in_(cluster_ids)
        ]
        if event_to_cluster:
            target_conditions.append(
                (feedback_events_table.c.target_type == "lead_event")
                & feedback_events_table.c.target_id.in_(list(event_to_cluster))
            )
        if match_to_cluster:
            target_conditions.append(
                (feedback_events_table.c.target_type == "lead_match")
                & feedback_events_table.c.target_id.in_(list(match_to_cluster))
            )
        rows = (
            self.session.execute(
                select(
                    feedback_events_table.c.target_type, feedback_events_table.c.target_id
                ).where(or_(*target_conditions))
            )
            .mappings()
            .all()
        )
        for row in rows:
            target_type = row["target_type"]
            target_id = row["target_id"]
            cluster_id: str | None = None
            if target_type == "lead_cluster":
                cluster_id = target_id
            elif target_type == "lead_event":
                cluster_id = event_to_cluster.get(target_id)
            elif target_type == "lead_match":
                cluster_id = match_to_cluster.get(target_id)
            if cluster_id is not None and cluster_id in counts:
                counts[cluster_id] += 1
        return counts

    def _auto_merge_cluster_ids(self, cluster_ids: list[str]) -> set[str]:
        rows = self.session.execute(
            select(lead_cluster_actions_table.c.to_cluster_id)
            .where(
                lead_cluster_actions_table.c.action_type == "auto_merge",
                lead_cluster_actions_table.c.to_cluster_id.in_(cluster_ids),
            )
            .distinct()
        ).all()
        return {row.to_cluster_id for row in rows if row.to_cluster_id is not None}

    def _event_ids(self, cluster_id: str) -> list[str]:
        rows = self.session.execute(
            select(lead_events_table.c.id)
            .where(lead_events_table.c.lead_cluster_id == cluster_id)
            .order_by(lead_events_table.c.created_at)
        ).all()
        return [row.id for row in rows]

    def _event_rows(self, cluster_id: str) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                select(
                    lead_events_table.c.id,
                    lead_events_table.c.source_message_id,
                    lead_events_table.c.message_url,
                    lead_events_table.c.sender_id,
                    lead_events_table.c.sender_name,
                    lead_events_table.c.detected_at,
                    lead_events_table.c.classifier_version_id,
                    lead_events_table.c.decision,
                    lead_events_table.c.detection_mode,
                    lead_events_table.c.confidence,
                    lead_events_table.c.commercial_value_score,
                    lead_events_table.c.notify_reason,
                    lead_events_table.c.reason,
                    lead_events_table.c.is_retro,
                    lead_events_table.c.original_detected_at,
                    lead_events_table.c.created_at,
                )
                .where(lead_events_table.c.lead_cluster_id == cluster_id)
                .order_by(lead_events_table.c.created_at)
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def _match_rows(self, cluster_id: str) -> list[dict[str, Any]]:
        return [_public_match_payload(row) for row in self._raw_match_rows(cluster_id)]

    def _raw_match_rows(self, cluster_id: str) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                self._match_query()
                .where(lead_events_table.c.lead_cluster_id == cluster_id)
                .order_by(lead_matches_table.c.score.desc(), lead_matches_table.c.created_at)
            )
            .mappings()
            .all()
        )
        return [_match_payload(dict(row)) for row in rows]

    def _match_query(self) -> Select[tuple[Any, ...]]:
        return select(
            lead_matches_table.c.id.label("match_id"),
            lead_matches_table.c.lead_event_id.label("event_id"),
            lead_matches_table.c.match_type,
            lead_matches_table.c.matched_text,
            lead_matches_table.c.score,
            lead_matches_table.c.catalog_item_id,
            catalog_items_table.c.name.label("catalog_item_name"),
            lead_matches_table.c.item_status_at_detection,
            lead_matches_table.c.catalog_term_id,
            catalog_terms_table.c.term.label("catalog_term_text"),
            lead_matches_table.c.term_status_at_detection,
            lead_matches_table.c.offer_status_at_detection,
            lead_matches_table.c.category_id,
            catalog_categories_table.c.name.label("category_name"),
        ).select_from(
            lead_matches_table.join(
                lead_events_table,
                lead_matches_table.c.lead_event_id == lead_events_table.c.id,
            )
            .outerjoin(
                catalog_items_table,
                lead_matches_table.c.catalog_item_id == catalog_items_table.c.id,
            )
            .outerjoin(
                catalog_terms_table,
                lead_matches_table.c.catalog_term_id == catalog_terms_table.c.id,
            )
            .outerjoin(
                catalog_categories_table,
                lead_matches_table.c.category_id == catalog_categories_table.c.id,
            )
        )

    def _feedback_rows(self, cluster_id: str) -> list[dict[str, Any]]:
        event_ids = self._event_ids(cluster_id)
        match_ids = self._match_ids(event_ids)
        target_conditions = [
            (feedback_events_table.c.target_type == "lead_cluster")
            & (feedback_events_table.c.target_id == cluster_id)
        ]
        if event_ids:
            target_conditions.append(
                (feedback_events_table.c.target_type == "lead_event")
                & feedback_events_table.c.target_id.in_(event_ids)
            )
        if match_ids:
            target_conditions.append(
                (feedback_events_table.c.target_type == "lead_match")
                & feedback_events_table.c.target_id.in_(match_ids)
            )
        rows = (
            self.session.execute(
                select(
                    feedback_events_table.c.id,
                    feedback_events_table.c.target_type,
                    feedback_events_table.c.target_id,
                    feedback_events_table.c.action,
                    feedback_events_table.c.reason_code,
                    feedback_events_table.c.feedback_scope,
                    feedback_events_table.c.learning_effect,
                    feedback_events_table.c.comment,
                    feedback_events_table.c.created_by,
                    feedback_events_table.c.created_at,
                )
                .where(or_(*target_conditions))
                .order_by(feedback_events_table.c.created_at)
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def _match_ids(self, event_ids: list[str]) -> list[str]:
        if not event_ids:
            return []
        rows = self.session.execute(
            select(lead_matches_table.c.id).where(lead_matches_table.c.lead_event_id.in_(event_ids))
        ).all()
        return [row.id for row in rows]

    def _has_retro_event(self, cluster_id: str) -> bool:
        return self._event_exists(cluster_id, lead_events_table.c.is_retro.is_(True))

    def _has_maybe_event(self, cluster_id: str) -> bool:
        return self._event_exists(cluster_id, lead_events_table.c.decision == "maybe")

    def _event_exists(self, cluster_id: str, condition: Any) -> bool:
        count = self.session.scalar(
            select(func.count())
            .select_from(lead_events_table)
            .where(lead_events_table.c.lead_cluster_id == cluster_id, condition)
        )
        return bool(count)

    def _has_auto_merge_action(self, cluster_id: str) -> bool:
        count = self.session.scalar(
            select(func.count())
            .select_from(lead_cluster_actions_table)
            .where(
                lead_cluster_actions_table.c.action_type == "auto_merge",
                lead_cluster_actions_table.c.to_cluster_id == cluster_id,
            )
        )
        return bool(count)

    def _timeline(
        self,
        cluster: LeadClusterQueueRow,
        events: list[dict[str, Any]],
        feedback: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        member_messages = (
            self.session.execute(
                select(
                    source_messages_table.c.id,
                    source_messages_table.c.telegram_message_id,
                    source_messages_table.c.sender_id,
                    source_messages_table.c.message_date,
                    source_messages_table.c.text,
                    source_messages_table.c.caption,
                    lead_cluster_members_table.c.member_role,
                )
                .select_from(
                    lead_cluster_members_table.join(
                        source_messages_table,
                        lead_cluster_members_table.c.source_message_id
                        == source_messages_table.c.id,
                    )
                )
                .where(lead_cluster_members_table.c.lead_cluster_id == cluster.cluster_id)
                .order_by(source_messages_table.c.message_date)
            )
            .mappings()
            .all()
        )
        timeline = [
            {
                "kind": "message",
                "at": row["message_date"],
                "message": {
                    "id": row["id"],
                    "telegram_message_id": row["telegram_message_id"],
                    "sender_id": row["sender_id"],
                    "text": _message_text(dict(row)),
                    "member_role": row["member_role"],
                },
            }
            for row in member_messages
        ]
        timeline.extend(
            {"kind": "event", "at": event["created_at"], "event": event} for event in events
        )
        timeline.extend(
            {"kind": "feedback", "at": feedback_row["created_at"], "feedback": feedback_row}
            for feedback_row in feedback
        )
        return sorted(timeline, key=lambda entry: entry["at"])


def _match_payload(row: dict[str, Any]) -> dict[str, Any]:
    status_at_detection = (
        row["term_status_at_detection"]
        or row["item_status_at_detection"]
        or row["offer_status_at_detection"]
    )
    return {
        "match_id": row["match_id"],
        "event_id": row["event_id"],
        "match_type": row["match_type"],
        "matched_text": row["matched_text"],
        "score": row["score"],
        "catalog_item_id": row["catalog_item_id"],
        "catalog_item_name": row["catalog_item_name"],
        "item_status_at_detection": row["item_status_at_detection"],
        "catalog_term_id": row["catalog_term_id"],
        "catalog_term_text": row["catalog_term_text"],
        "category_id": row["category_id"],
        "category_name": row["category_name"],
        "status_at_detection": status_at_detection,
    }


def _public_match_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "match_type": row["match_type"],
        "matched_text": row["matched_text"],
        "score": row["score"],
        "catalog_item_id": row["catalog_item_id"],
        "catalog_item_name": row["catalog_item_name"],
        "catalog_term_id": row["catalog_term_id"],
        "catalog_term_text": row["catalog_term_text"],
        "category_id": row["category_id"],
        "category_name": row["category_name"],
        "status_at_detection": row["status_at_detection"],
    }


def _message_text(row: dict[str, Any]) -> str | None:
    parts = [part for part in (row.get("text"), row.get("caption")) if part]
    return "\n".join(parts) if parts else None


def _limit(value: int) -> int:
    return min(max(value, 1), 100)


def _offset(value: int) -> int:
    return max(value, 0)


def _unique_dicts(values: list[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
    seen: set[Any] = set()
    unique_values = []
    for value in values:
        dedupe_value = value[key]
        if dedupe_value in seen:
            continue
        seen.add(dedupe_value)
        unique_values.append(value)
    return unique_values


def _has_operator_issue(row: LeadClusterQueueRow) -> bool:
    return row.has_auto_pending or row.has_auto_merge_pending or row.is_maybe


def _apply_bool_filter(
    query: Select[tuple[Any, ...]],
    expected: bool | None,
    expression: ColumnElement[bool],
) -> Select[tuple[Any, ...]]:
    if expected is None:
        return query
    if expected:
        return query.where(expression)
    return query.where(not_(expression))


def _retro_exists_expr() -> ColumnElement[bool]:
    return (
        select(lead_events_table.c.id)
        .where(
            lead_events_table.c.lead_cluster_id == lead_clusters_table.c.id,
            lead_events_table.c.is_retro.is_(True),
        )
        .exists()
    )


def _maybe_expr() -> ColumnElement[bool]:
    return or_(
        lead_clusters_table.c.cluster_status == "maybe",
        select(lead_events_table.c.id)
        .where(
            lead_events_table.c.lead_cluster_id == lead_clusters_table.c.id,
            lead_events_table.c.decision == "maybe",
        )
        .exists(),
    )


def _auto_pending_expr() -> ColumnElement[bool]:
    return (
        select(lead_matches_table.c.id)
        .select_from(
            lead_matches_table.join(
                lead_events_table,
                lead_matches_table.c.lead_event_id == lead_events_table.c.id,
            )
        )
        .where(
            lead_events_table.c.lead_cluster_id == lead_clusters_table.c.id,
            or_(
                lead_matches_table.c.term_status_at_detection == "auto_pending",
                lead_matches_table.c.item_status_at_detection == "auto_pending",
                lead_matches_table.c.offer_status_at_detection == "auto_pending",
            ),
        )
        .exists()
    )


def _auto_merge_expr() -> ColumnElement[bool]:
    return (
        select(lead_cluster_actions_table.c.id)
        .where(
            lead_cluster_actions_table.c.to_cluster_id == lead_clusters_table.c.id,
            lead_cluster_actions_table.c.action_type == "auto_merge",
        )
        .exists()
    )


def _operator_issue_expr() -> ColumnElement[bool]:
    return or_(_auto_pending_expr(), _auto_merge_expr(), _maybe_expr())
