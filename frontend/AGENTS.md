# Frontend AGENTS.md

These rules apply to files under `frontend/`.

## Stack

Target stack:
- React
- TypeScript
- Vite

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
