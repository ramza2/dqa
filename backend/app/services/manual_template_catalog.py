"""Model-independent listing of eligible Query Templates for manual forms.

Only metadata already allowed by Query Assistant is returned. Any execution
still requires independent form/preview/execute safety and authorization gates.
"""
from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.adapters.catalog.activation_errors import CatalogActivationError
from app.adapters.demis.types import MAX_SQL_TEXT_LENGTH
from app.adapters.execution.errors import ExecutionPreviewError, ExecutionPreviewErrorCode
from app.repositories.query_template import QueryTemplateRepository
from app.schemas.manual_template_catalog import ManualTemplateListResponse
from app.schemas.query_template import QueryTemplateParameter
from app.schemas.recommendation import RecommendedTemplate
from app.services.catalog_active import get_active_catalog
from app.services.sql_safety import validate_sql_safety


def list_manual_template_catalog(
    session: Session, *, source_name: str, limit: int, offset: int
) -> ManualTemplateListResponse:
    """Return deterministic, source-scoped, bounded preview metadata.

    Does not call an LLM, resolve database credentials or execute any SQL.
    """
    source = source_name.strip()
    if not source:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE,
            "source_name must not be blank",
        )
    try:
        active = get_active_catalog(session, source)
    except CatalogActivationError:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.ACTIVE_CATALOG_NOT_FOUND,
            "active catalog revision not found for source",
        ) from None

    eligible: list[RecommendedTemplate] = []
    for template, version in QueryTemplateRepository(
        session
    ).list_approved_enabled_current_versions(source_name=source):
        if (
            version.catalog_revision_id != active.revision_id
            or version.catalog_fingerprint_constraint != active.schema_fingerprint
            or not isinstance(version.sql_text, str)
            or len(version.sql_text) > MAX_SQL_TEXT_LENGTH
            or not isinstance(version.parameter_schema, list)
        ):
            continue
        try:
            parameters = [
                QueryTemplateParameter.model_validate(item)
                for item in version.parameter_schema
            ]
            if not validate_sql_safety(
                version.sql_text, version.parameter_schema
            ).safe:
                continue
        except (ValidationError, TypeError, ValueError):
            # Corrupt/incompatible legacy versions must not enter manual forms.
            continue

        eligible.append(RecommendedTemplate(
            template_id=template.id,
            version_id=version.id,
            version=version.version,
            stable_key=template.stable_key,
            name=template.name,
            description=template.description,
            target_schemas=[str(item) for item in (template.target_schemas or [])],
            parameter_names=[param.name for param in parameters],
            parameter_count=len(parameters),
        ))

    # Repository already orders by stable_key + id; do not use LLM ranking.
    total = len(eligible)
    return ManualTemplateListResponse(
        source_name=source,
        catalog_revision_id=active.revision_id,
        schema_fingerprint=active.schema_fingerprint,
        total=total,
        limit=limit,
        offset=offset,
        items=eligible[offset:offset + limit],
    )
