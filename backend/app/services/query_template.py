"""Query Template draft registry: create/list/get/update/delete (no execution)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.catalog.activation_errors import (
    CatalogActivationError,
    CatalogActivationErrorCode,
)
from app.adapters.catalog.query_errors import CatalogQueryError
from app.adapters.catalog.query_template_errors import (
    QueryTemplateError,
    QueryTemplateErrorCode,
)
from app.models.query_template import QueryTemplate, QueryTemplateVersion
from app.repositories.query_template import QueryTemplateRepository
from app.schemas.query_template import (
    QueryTemplateCompatibilityView,
    QueryTemplateCreateRequest,
    QueryTemplateDetail,
    QueryTemplateListResponse,
    QueryTemplateParameter,
    QueryTemplateSummary,
    QueryTemplateUpdateRequest,
    QueryTemplateVersionView,
)
from app.services.catalog_active import ActiveCatalogView, get_active_catalog
from app.services.catalog_query import resolve_active_revision

APPROVAL_DRAFT = "DRAFT"
COMPATIBILITY_EXACT = "EXACT_FINGERPRINT"


@dataclass(frozen=True)
class _CurrentActive:
    revision_id: int | None
    schema_fingerprint: str | None


def create_query_template(
    session: Session,
    request: QueryTemplateCreateRequest,
) -> QueryTemplateDetail:
    """Create a template + version 1 DRAFT pinned to the current Active Catalog."""
    active = _require_active_catalog(session, request.source_name)
    _assert_target_schemas(session, request.source_name, request.target_schemas)

    repo = QueryTemplateRepository(session)
    if repo.get_by_source_and_stable_key(request.source_name, request.stable_key) is not None:
        raise QueryTemplateError(
            QueryTemplateErrorCode.DUPLICATE_STABLE_KEY,
            "stable_key already exists for this source",
        )

    now = datetime.now(timezone.utc)
    template = QueryTemplate(
        stable_key=request.stable_key,
        name=request.name,
        description=request.description,
        source_name=request.source_name,
        target_schemas=list(request.target_schemas),
        enabled=False,
        current_version_id=None,
        created_at=now,
        updated_at=now,
    )
    try:
        repo.add_template(template)
    except IntegrityError as exc:
        raise QueryTemplateError(
            QueryTemplateErrorCode.DUPLICATE_STABLE_KEY,
            "stable_key already exists for this source",
        ) from exc

    version = QueryTemplateVersion(
        template_id=template.id,
        version=1,
        sql_text=request.sql_text,
        parameter_schema=_dump_parameters(request.parameter_schema),
        row_limit=request.row_limit,
        timeout_seconds=request.timeout_seconds,
        compatibility_mode=COMPATIBILITY_EXACT,
        catalog_revision_id=active.revision_id,
        catalog_fingerprint_constraint=active.schema_fingerprint,
        approval_status=APPROVAL_DRAFT,
        created_by=None,
        created_at=now,
        approved_by=None,
        approved_at=None,
        approval_note=None,
    )
    repo.add_version(version)
    template.current_version_id = version.id
    template.updated_at = now
    session.flush()
    session.refresh(template)

    return _to_detail(session, template, version)


def list_query_templates(
    session: Session,
    *,
    source_name: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> QueryTemplateListResponse:
    repo = QueryTemplateRepository(session)
    rows = repo.list_templates(source_name=source_name, limit=limit, offset=offset)
    total = repo.count_templates(source_name=source_name)
    return QueryTemplateListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[_to_summary(session, row) for row in rows],
    )


def get_query_template(session: Session, template_id: int) -> QueryTemplateDetail:
    template, version = _require_template_with_current(session, template_id)
    return _to_detail(session, template, version)


def update_query_template(
    session: Session,
    template_id: int,
    request: QueryTemplateUpdateRequest,
) -> QueryTemplateDetail:
    template, version = _require_template_with_current(session, template_id)
    _assert_draft_mutable(template, version)

    if request.target_schemas is not None:
        _assert_target_schemas(session, template.source_name, request.target_schemas)
        template.target_schemas = list(request.target_schemas)

    if request.name is not None:
        template.name = request.name
    if "description" in request.model_fields_set:
        template.description = request.description
    if request.sql_text is not None:
        version.sql_text = request.sql_text
    if request.parameter_schema is not None:
        version.parameter_schema = _dump_parameters(request.parameter_schema)
    if request.row_limit is not None:
        version.row_limit = request.row_limit
    if request.timeout_seconds is not None:
        version.timeout_seconds = request.timeout_seconds

    # Pinned catalog identity is never rewritten on draft edits.
    template.updated_at = datetime.now(timezone.utc)
    session.flush()
    session.refresh(template)
    session.refresh(version)
    return _to_detail(session, template, version)


def delete_query_template(session: Session, template_id: int) -> None:
    template, version = _require_template_with_current(session, template_id)
    _assert_draft_deletable(template, version)
    QueryTemplateRepository(session).delete_template(template)


def _require_active_catalog(session: Session, source_name: str) -> ActiveCatalogView:
    try:
        return get_active_catalog(session, source_name)
    except CatalogActivationError as exc:
        if exc.code == CatalogActivationErrorCode.ACTIVE_REVISION_NOT_FOUND:
            raise QueryTemplateError(
                QueryTemplateErrorCode.ACTIVE_CATALOG_NOT_FOUND,
                "active catalog revision not found for source",
            ) from exc
        raise QueryTemplateError(
            QueryTemplateErrorCode.ACTIVE_CATALOG_NOT_FOUND,
            "active catalog revision not found for source",
        ) from exc


def _assert_target_schemas(
    session: Session,
    source_name: str,
    target_schemas: list[str],
) -> None:
    try:
        resolved = resolve_active_revision(session, source_name)
    except CatalogQueryError as exc:
        raise QueryTemplateError(
            QueryTemplateErrorCode.ACTIVE_CATALOG_NOT_FOUND,
            "active catalog revision not found for source",
        ) from exc
    available = _schema_names_from_revision(resolved.revision.tables_json)
    # Also accept the catalog default_schema when tables are empty / sparse.
    if resolved.revision.default_schema:
        available.add(resolved.revision.default_schema)

    missing = [name for name in target_schemas if name not in available]
    if missing:
        raise QueryTemplateError(
            QueryTemplateErrorCode.INVALID_TARGET_SCHEMA,
            f"target schema(s) not present in active catalog: {', '.join(missing)}",
        )


def _schema_names_from_revision(tables_json: dict[str, Any] | list[Any] | Any) -> set[str]:
    """Reuse stored Active Catalog tables JSON; do not invent schema names."""
    raw_list: list[Any]
    if isinstance(tables_json, dict):
        maybe = tables_json.get("tables")
        raw_list = maybe if isinstance(maybe, list) else []
    elif isinstance(tables_json, list):
        raw_list = tables_json
    else:
        raw_list = []

    names: set[str] = set()
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        schema = raw.get("schema_name") or raw.get("schema")
        if isinstance(schema, str) and schema:
            names.add(schema)
            continue
        table_key = raw.get("table_key")
        if isinstance(table_key, str) and "." in table_key:
            names.add(table_key.split(".", 1)[0])
    return names


def _require_template_with_current(
    session: Session, template_id: int
) -> tuple[QueryTemplate, QueryTemplateVersion]:
    template = QueryTemplateRepository(session).get_by_id(template_id)
    if template is None:
        raise QueryTemplateError(
            QueryTemplateErrorCode.TEMPLATE_NOT_FOUND,
            "query template not found",
        )
    version = _current_version(template)
    if version is None:
        raise QueryTemplateError(
            QueryTemplateErrorCode.TEMPLATE_NOT_FOUND,
            "query template current version not found",
        )
    return template, version


def _current_version(template: QueryTemplate) -> QueryTemplateVersion | None:
    if template.current_version_id is None:
        return None
    for version in template.versions:
        if version.id == template.current_version_id:
            return version
    return None


def _assert_draft_mutable(template: QueryTemplate, version: QueryTemplateVersion) -> None:
    if template.enabled:
        raise QueryTemplateError(
            QueryTemplateErrorCode.NOT_DRAFT,
            "enabled templates cannot be mutated via draft registry APIs",
        )
    if version.approval_status != APPROVAL_DRAFT:
        raise QueryTemplateError(
            QueryTemplateErrorCode.NOT_DRAFT,
            "only DRAFT versions can be updated",
        )


def _assert_draft_deletable(template: QueryTemplate, version: QueryTemplateVersion) -> None:
    if template.enabled:
        raise QueryTemplateError(
            QueryTemplateErrorCode.NOT_DRAFT,
            "enabled templates cannot be deleted via draft registry APIs",
        )
    # Future approval PR: refuse when any non-DRAFT / APPROVED version exists.
    for item in template.versions:
        if item.approval_status != APPROVAL_DRAFT:
            raise QueryTemplateError(
                QueryTemplateErrorCode.NOT_DRAFT,
                "templates with non-DRAFT versions cannot be deleted",
            )
    if version.approval_status != APPROVAL_DRAFT:
        raise QueryTemplateError(
            QueryTemplateErrorCode.NOT_DRAFT,
            "only DRAFT templates can be deleted",
        )


def _dump_parameters(params: list[QueryTemplateParameter]) -> list[dict[str, Any]]:
    return [param.model_dump(mode="json") for param in params]


def _load_parameters(raw: list[Any] | Any) -> list[QueryTemplateParameter]:
    if not isinstance(raw, list):
        return []
    return [QueryTemplateParameter.model_validate(item) for item in raw]


def _lookup_current_active(session: Session, source_name: str) -> _CurrentActive:
    try:
        view = get_active_catalog(session, source_name)
    except CatalogActivationError:
        return _CurrentActive(revision_id=None, schema_fingerprint=None)
    return _CurrentActive(
        revision_id=view.revision_id,
        schema_fingerprint=view.schema_fingerprint,
    )


def _compatibility_view(
    session: Session,
    *,
    source_name: str,
    version: QueryTemplateVersion,
) -> QueryTemplateCompatibilityView:
    current = _lookup_current_active(session, source_name)
    # EXACT_FINGERPRINT: pin is immutable; compare against current active fingerprint only.
    compatible = (
        version.compatibility_mode == COMPATIBILITY_EXACT
        and current.schema_fingerprint is not None
        and current.schema_fingerprint == version.catalog_fingerprint_constraint
    )
    return QueryTemplateCompatibilityView(
        mode="EXACT_FINGERPRINT",
        compatible=compatible,
        pinned_revision_id=version.catalog_revision_id,
        pinned_schema_fingerprint=version.catalog_fingerprint_constraint,
        current_revision_id=current.revision_id,
        current_schema_fingerprint=current.schema_fingerprint,
    )


def _to_version_view(
    session: Session,
    *,
    source_name: str,
    version: QueryTemplateVersion,
) -> QueryTemplateVersionView:
    return QueryTemplateVersionView(
        id=version.id,
        version=version.version,
        sql_text=version.sql_text,
        parameter_schema=_load_parameters(version.parameter_schema),
        row_limit=version.row_limit,
        timeout_seconds=version.timeout_seconds,
        approval_status=version.approval_status,  # type: ignore[arg-type]
        compatibility=_compatibility_view(session, source_name=source_name, version=version),
        created_by=version.created_by,
        created_at=version.created_at,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
        approval_note=version.approval_note,
    )


def _to_summary(session: Session, template: QueryTemplate) -> QueryTemplateSummary:
    version = _current_version(template)
    compatibility = None
    approval_status = None
    current_version_number = None
    if version is not None:
        compatibility = _compatibility_view(
            session, source_name=template.source_name, version=version
        )
        approval_status = version.approval_status  # type: ignore[assignment]
        current_version_number = version.version
    return QueryTemplateSummary(
        id=template.id,
        stable_key=template.stable_key,
        name=template.name,
        description=template.description,
        source_name=template.source_name,
        target_schemas=list(template.target_schemas or []),
        enabled=bool(template.enabled),
        current_version_id=template.current_version_id,
        current_version=current_version_number,
        approval_status=approval_status,
        compatibility=compatibility,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def _to_detail(
    session: Session,
    template: QueryTemplate,
    version: QueryTemplateVersion,
) -> QueryTemplateDetail:
    summary = _to_summary(session, template)
    return QueryTemplateDetail(
        **summary.model_dump(),
        version=_to_version_view(
            session, source_name=template.source_name, version=version
        ),
    )
