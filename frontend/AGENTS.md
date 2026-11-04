# Frontend AGENTS.md

These rules apply to files under `frontend/`.

## Stack

Target stack:
- React
- TypeScript
- Vite

## Analyzer UI/UX baseline

For schema/catalog/DB-analysis screens, `ramza2/demis-schema-search-poc`
is the primary visual and interaction baseline. Aim for near-identical
left-sidebar information architecture, page density, labels, layout, navigation
and feature behavior. Preserve the original Table Explorer and interactive
React Flow + ELK ERD experience, including full/focused/category views,
zoom/pan/minimap, search and FK column mappings. Preserve report, Run Diff
and Catalog Package workflows, while integrating all existing DQA functions.

Port compatible React/TypeScript code and CSS from
`demis-schema-search-poc/frontend/erd_component/` after reviewing it.
Remove its Streamlit bridge and use DQA API modules and Catalog revision
guards. Do not fall back to a static three-column relationship list as the
primary ERD. Keep legacy visual parity where safe; record any necessary
differences due to accessibility, security, performance or DQA data contracts.

Every UI migration PR should include a concise old-vs-new feature checklist,
tests for its key interactions, and a visual review with the original screen.
The operational safety, backend authorization and source/version visibility
rules below still apply.

## Design priorities

This is an operational tool, not a marketing site.

Prefer:
- clear status
- explicit source/version
- explicit approval state
- deliberate execution actions
- readable tables
- actionable error messages

Avoid decorative complexity that obscures operational state.

## API usage

Keep API communication in dedicated client modules.

Backend validation is authoritative.
Do not duplicate security policy only in the frontend.

## Required visibility

When relevant, always display:
- active Catalog Package/source
- package version / schema fingerprint
- selected Query Template and version
- approval/enabled status
- target source/schema
- execution status
- row count / truncation state
- audit reference

## Query execution UX

Never make unsafe or unapproved queries appear executable.

Query execution must require an explicit user action after the selected template and parameters are visible.

Do not display credentials or connection secrets.
