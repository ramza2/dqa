"""Medical terminology expansion for Data Discovery keyword search."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TerminologyExpansion:
    matched_concepts: list[str]
    expanded_terms: list[str]


@dataclass(frozen=True)
class _Concept:
    concept_id: str
    triggers: tuple[str, ...]
    expansion_terms: tuple[str, ...]


def expand_medical_terms(
    normalized_query: str,
    *,
    terms_path: str | None = None,
) -> TerminologyExpansion:
    """Expand clinical synonyms. Never maps to physical DEMIS table/column names."""
    concepts = _load_concepts(terms_path)
    matched: list[str] = []
    expanded: list[str] = []
    seen_terms: set[str] = set()

    for concept in concepts:
        if not _concept_matches(normalized_query, concept.triggers):
            continue
        matched.append(concept.concept_id)
        for term in concept.expansion_terms:
            key = term.casefold()
            if key in seen_terms:
                continue
            seen_terms.add(key)
            expanded.append(term)

    return TerminologyExpansion(
        matched_concepts=matched,
        expanded_terms=expanded,
    )


def _concept_matches(normalized_query: str, triggers: tuple[str, ...]) -> bool:
    for trigger in triggers:
        trig = trigger.casefold().strip()
        if not trig:
            continue
        if _is_latin_token(trig):
            if re.search(rf"(?<![a-z0-9_]){re.escape(trig)}(?![a-z0-9_])", normalized_query):
                return True
        elif trig in normalized_query:
            return True
    return False


def _is_latin_token(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9_\-]{0,31}", value))


@lru_cache(maxsize=4)
def _load_concepts(terms_path: str | None) -> tuple[_Concept, ...]:
    payload = _read_dictionary(terms_path)
    concepts_raw = payload.get("concepts")
    if not isinstance(concepts_raw, list):
        return ()
    concepts: list[_Concept] = []
    for raw in concepts_raw:
        if not isinstance(raw, dict):
            continue
        concept_id = str(raw.get("id") or "").strip()
        if not concept_id:
            continue
        triggers = tuple(
            str(item).strip()
            for item in (raw.get("triggers") or [])
            if str(item).strip()
        )
        expansion_terms = tuple(
            str(item).strip()
            for item in (raw.get("expansion_terms") or [])
            if str(item).strip()
        )
        concepts.append(
            _Concept(
                concept_id=concept_id,
                triggers=triggers,
                expansion_terms=expansion_terms,
            )
        )
    concepts.sort(key=lambda c: c.concept_id)
    return tuple(concepts)


def _read_dictionary(terms_path: str | None) -> dict[str, Any]:
    if terms_path:
        path = Path(terms_path)
        return json.loads(path.read_text(encoding="utf-8"))
    package_files = resources.files("app.resources")
    data = package_files.joinpath("medical_terms.json").read_text(encoding="utf-8")
    return json.loads(data)
