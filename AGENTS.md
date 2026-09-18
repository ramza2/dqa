# AGENTS.md

# DEMIS Query Assistant (DQA)

## 1. Purpose

DEMIS Query Assistant is a separate application from DEMIS Schema Analyzer.

DEMIS Schema Analyzer produces a validated Catalog Package.
DQA consumes that package and provides safe catalog exploration, approved Query Template discovery, parameter extraction, read-only execution, result review, and auditability.

This repository must not duplicate Schema Analyzer crawling or metadata-inspection functions.

## 2. Core boundary

Producer:
- DEMIS Schema Analyzer

Consumer:
- DEMIS Query Assistant

Primary input:
- finalized DEMIS Catalog Package v2
- package_format: `demis-catalog-package`
- package_version: `2.x`

Do not hard-code mock DEMIS schema knowledge into production logic.
The current Oracle mock schema is development/test data only.

## 3. Source of truth

The activated Catalog Package is authoritative for:
- schema
- tables
- columns
- PK / UK
- FK
- indexes
- DB comments
- categories
- physical schema snapshot
- schema fingerprint
- package validation/readiness metadata

Never invent tables, columns, relationships, comments, or medical meaning that are not supported by the active package.

## 4. Package import rules

Every package must be validated before activation.

Validate at minimum:
1. ZIP structure and root
2. package_format
3. package_version compatibility
4. manifest file list
5. SHA-256 for each manifest-managed file
6. source identity
7. schema fingerprint
8. package readiness
9. JSON parseability and required fields

Activation policy for the initial implementation:
- READY: may be activated
- WARNING: may be imported for inspection but must not be activated for query execution
- BLOCKED: must not be activated

Any future WARNING override requires an explicit reviewed design change and audit policy.

Never silently repair, rewrite, or partially accept a corrupt package.

## 5. Query execution safety

The application is read-only.

Never implement executable:
- INSERT
- UPDATE
- DELETE
- MERGE
- UPSERT
- CREATE
- ALTER
- DROP
- TRUNCATE
- GRANT
- REVOKE
- procedural/anonymous blocks
- arbitrary DDL/DML
- multi-statement execution

The LLM must never directly generate SQL that is immediately executed.

Allowed runtime path:

Natural language request
-> active Catalog retrieval
-> approved Query Template recommendation
-> parameter extraction
-> type/constraint validation
-> SQL safety validation
-> preview
-> approved read-only execution
-> result handling
-> audit log

Executable SQL must originate from an APPROVED and ENABLED Query Template.

Defense in depth:
- read-only DEMIS account
- SELECT-only SQL validation
- one statement only
- bound parameters
- statement timeout
- maximum row limit
- database read-only session/transaction where supported
- result-size controls
- audit logging

## 6. Query Template rules

Query Templates are managed first-class objects.

A template should contain at least:
- template_id
- name
- description
- source/catalog compatibility
- target schemas
- SQL template
- parameter definitions
- parameter types
- required/optional rules
- allowed value constraints when applicable
- maximum row count
- timeout
- enabled flag
- approval status
- version
- created_at
- updated_at
- approval/audit metadata

Only APPROVED + ENABLED templates may be executed.

LLM/search may recommend a template but cannot bypass approval.

## 7. LLM responsibilities

The LLM may:
- interpret user intent
- retrieve relevant catalog objects
- rank approved Query Templates
- extract parameters
- explain catalog metadata
- summarize query results only when an approved data-egress policy explicitly permits it

The LLM must not:
- execute arbitrary generated SQL
- fabricate schema facts
- fabricate unsupported medical meaning
- bypass Query Template approval
- expose credentials or infrastructure secrets
- change the active Catalog Package

Use a provider abstraction for all LLM calls.
Do not bind domain code to one model vendor.

By default, query result rows, patient identifiers, and other sensitive medical data must not be sent to an LLM.
Result summarization is disabled until an explicit provider/data-egress policy is approved and implemented.

## 8. Security

Never commit, log, return, or embed:
- database passwords
- encrypted credentials
- API keys
- access tokens
- private certificates
- production host secrets

Secrets come from environment variables or an approved secret store.

Mask secrets and connection details in errors.

Audit metadata should be sufficient to reconstruct:
- who requested execution
- which active catalog version was used
- which template/version was selected
- which parameter names were used
- execution timing/status
- row count
- failure category

Do not log sensitive result rows by default.

## 9. Architecture

Recommended backend layering:

API
-> application/service
-> domain
-> repository/adapter
-> external DB / LLM / persistence

Rules:
- keep FastAPI routes thin
- keep SQL safety logic outside route handlers
- keep DEMIS DB access behind a dedicated read-only adapter
- keep Catalog Package parsing independent of live DB connectivity
- keep LLM provider access behind an interface
- keep import/activation separate from query runtime

## 10. Development workflow

Before coding:
1. read this file and relevant nested AGENTS.md files
2. inspect existing implementation patterns
3. state the minimal implementation plan
4. avoid unrelated refactoring

For feature work:
- create a feature branch
- use focused commits
- add/update tests
- run focused tests first
- run relevant regression tests
- report runtime validation separately
- open a PR
- do not merge automatically

Do not delete working functionality merely to simplify a change.
Prefer backward-compatible changes unless explicitly instructed otherwise.

## 11. Git / PR policy

Never push feature work directly to main.

Never merge a PR without explicit user approval.

Before asking for merge approval, report:
- branch
- PR number
- changed scope
- tests run and results
- deployment/runtime validation
- known limitations or follow-up items

## 12. Deployment target

Target production pattern:
- Docker Compose
- external Traefik network
- Traefik labels
- `.env.production`
- `./scripts/deploy.sh`

When implemented, the deploy script should:
- validate required environment variables
- validate Compose configuration
- verify external Traefik network
- build required images
- deploy with `--remove-orphans`
- wait for backend health
- print service status

Do not expose application ports directly in production when routed through Traefik.

## 13. Testing expectations

Backend behavior changes require pytest coverage.

At minimum test:
- success path
- invalid input
- unknown resource
- security boundary
- approval boundary
- package tamper detection where relevant
- SQL rejection paths for unsafe statements

Package import tests must verify checksums and reject tampered files.

Do not claim work complete based on static inspection only.

## 14. Initial implementation order

Unless explicitly changed, implement in this order:

1. bootstrap/project structure
2. Catalog Package v2 import and validation
3. active Catalog management
4. Catalog/Table/Column explorer and search
5. Query Template registry
6. Query Template approval/versioning
7. natural language -> Query Template recommendation
8. parameter extraction and validation
9. read-only DEMIS adapter
10. execution preview and read-only query execution
11. result presentation
12. audit log
13. deployment and operational hardening

Do not jump directly to arbitrary LLM-generated SQL execution.
