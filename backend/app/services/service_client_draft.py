"""Application service for non-authorizing external service policy drafts.

No client credential is issued, no service principal is authenticated, and no
policy is connected to DQA REST/MCP execution. All callers remain denied.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.service_client_draft import ServiceClientDraft, ServiceClientDraftEvent
from app.schemas.service_client_draft import ServiceClientDraftCreate, ServiceClientDraftPatch


class ServiceClientDraftError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _policy_fingerprint(draft: ServiceClientDraft) -> str:
    data = {
        "client_id": draft.client_id,
        "service_name": draft.service_name,
        "organization": draft.organization,
        "owner_contact": draft.owner_contact,
        "purpose": draft.purpose,
        "environment": draft.environment,
        "requested_scopes": sorted(draft.requested_scopes),
        "proposed_ip_cidrs": sorted(draft.proposed_ip_cidrs),
        "status": draft.status,
    }
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _record_event(
    session: Session, draft: ServiceClientDraft, action: str, actor_id: str, fields: list[str]
) -> None:
    session.add(
        ServiceClientDraftEvent(
            client_draft_id=draft.id,
            action=action,
            actor_id=actor_id,
            changed_fields=sorted(fields),
            policy_sha256=_policy_fingerprint(draft),
        )
    )
    session.flush()


def create_client_draft(
    session: Session, body: ServiceClientDraftCreate, *, actor_id: str
) -> ServiceClientDraft:
    if session.scalar(select(ServiceClientDraft.id).where(ServiceClientDraft.client_id == body.client_id)):
        raise ServiceClientDraftError("SERVICE_CLIENT_ID_EXISTS")
    now = datetime.now(timezone.utc)
    draft = ServiceClientDraft(
        **body.model_dump(),
        status="DRAFT",
        created_by=actor_id,
        updated_by=actor_id,
        created_at=now,
        updated_at=now,
    )
    session.add(draft)
    try:
        session.flush()
        _record_event(session, draft, "CREATED", actor_id, list(body.model_fields_set))
    except IntegrityError as exc:
        raise ServiceClientDraftError("SERVICE_CLIENT_ID_EXISTS") from exc
    return draft


def get_client_draft(session: Session, draft_id: int, *, for_update: bool = False) -> ServiceClientDraft:
    stmt = select(ServiceClientDraft).where(ServiceClientDraft.id == draft_id)
    if for_update:
        stmt = stmt.with_for_update()
    draft = session.scalar(stmt)
    if draft is None:
        raise ServiceClientDraftError("SERVICE_CLIENT_NOT_FOUND")
    return draft


def list_client_drafts(session: Session, *, limit: int, offset: int) -> tuple[int, list[ServiceClientDraft]]:
    total = int(session.scalar(select(func.count()).select_from(ServiceClientDraft)) or 0)
    rows = list(
        session.scalars(
            select(ServiceClientDraft)
            .order_by(ServiceClientDraft.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    return total, rows


def patch_client_draft(
    session: Session, draft_id: int, body: ServiceClientDraftPatch, *, actor_id: str
) -> ServiceClientDraft:
    draft = get_client_draft(session, draft_id, for_update=True)
    if draft.status != "DRAFT":
        raise ServiceClientDraftError("SERVICE_CLIENT_REVOKED")
    for name in body.model_fields_set:
        setattr(draft, name, getattr(body, name))
    draft.updated_by = actor_id
    draft.updated_at = datetime.now(timezone.utc)
    session.flush()
    _record_event(session, draft, "UPDATED", actor_id, list(body.model_fields_set))
    return draft


def revoke_client_draft(session: Session, draft_id: int, *, actor_id: str) -> ServiceClientDraft:
    draft = get_client_draft(session, draft_id, for_update=True)
    if draft.status == "REVOKED":
        raise ServiceClientDraftError("SERVICE_CLIENT_REVOKED")
    draft.status = "REVOKED"
    draft.updated_by = actor_id
    draft.updated_at = datetime.now(timezone.utc)
    draft.revoked_at = draft.updated_at
    session.flush()
    _record_event(session, draft, "REVOKED", actor_id, ["status"])
    return draft


def list_client_draft_events(
    session: Session, draft_id: int, *, limit: int = 100
) -> list[ServiceClientDraftEvent]:
    get_client_draft(session, draft_id)
    return list(
        session.scalars(
            select(ServiceClientDraftEvent)
            .where(ServiceClientDraftEvent.client_draft_id == draft_id)
            .order_by(ServiceClientDraftEvent.id.desc())
            .limit(limit)
        ).all()
    )
