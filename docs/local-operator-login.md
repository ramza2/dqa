# DQA local operator login foundation (2026-11-04)

## Scope and safety

This slice adds interactive human accounts without trusting the old
`X-DQA-Dev-*` headers in production. No clinical approval, DEMIS access,
Inspector authorization, Catalog activation, MCPFlow integration or service
client authentication is granted by simply logging in. All existing
`require_permission` checks remain authoritative. The production Compose
configuration remains `APP_ENV=production` and `DQA_AUTH_PROVIDER=disabled`.
**Do not enable this slice on a military production network without HTTPS,
identity policy/MFA and security approval.**

## Endpoints

| Endpoint | Behavior |
| --- | --- |
| `GET /api/v1/auth/capabilities` | Public, secret-free login availability |
| `POST /api/v1/auth/login` | JSON `{username,password}`, exact trusted Origin; opaque HttpOnly session cookie |
| `GET /api/v1/auth/me` | Verified identity, roles and ephemeral session-bound CSRF header value |
| `POST /api/v1/auth/logout` | Origin + `X-DQA-CSRF`, server-side session revocation, cookie deletion |

The token has 256 bits of entropy and only its SHA-256 digest is stored.
Cookies are HttpOnly, SameSite=Strict, host-only and scoped to `/api/v1`.
Sessions expire after 8 hours (absolute); there is no silent renewal.
CSRF values are derived with an operator-provisioned distinct secret and
returned only to the same-origin authenticated page. All unsafe authenticated
API calls require exact `Origin` and CSRF header. A user is locked for
15 minutes after five failed attempts; no identity/role can be supplied in
the login body. Changing a password or disabling a user revokes sessions.
No automatic user bootstrap, self-registration or default passwords exist.

## Development-only trial (isolated synthetic data)

1. Apply migration **in an isolated disposable development database**:
   `cd backend && alembic upgrade head`. Never run integration test fixtures
   against a valuable live DB: `tests/conftest.py` may truncate catalog tables.
2. Provision a user on the backend console (password prompted twice):
   `python -m app.cli.local_users create --username admin1 --role administrator`.
   For a limited user, use e.g. `--role viewer`. No password in argv/logs.
3. Set backend environment **only on the isolated test stack**:
   `APP_ENV=development`, `DQA_AUTH_PROVIDER=local_session`,
   `DQA_LOCAL_AUTH_ORIGIN=http://127.0.0.1:8080`,
   `DQA_LOCAL_AUTH_COOKIE_SECURE=false`, and a unique secret of at least
   32 bytes in `DQA_LOCAL_AUTH_CSRF_KEY` (secret manager, never commit).
4. For Vite development, set `VITE_DQA_LOCAL_LOGIN_ENABLED=true` and use the
   exact frontend origin configured above. Backend and browser should be
   same-origin via the existing `/api` proxy. The normal on-prem dev overlay
   remains `dev_headers` and is not silently modified by this change.
5. Confirm an unauthenticated API request is 401, missing/invalid CSRF is 403,
   viewer cannot manage Connection Profiles (403), logout invalidates the
   server session, and disabled/expired accounts are denied.

Console-only password rotation and disable:

```
python -m app.cli.local_users set-password --username admin1
python -m app.cli.local_users disable --username viewer1
```

The CLI refuses to disable an administrator in this initial slice; there is
no browser-based user/role management yet. Do not delete or manually edit
production accounts to circumvent this guard.

## Unresolved production gates / next PR

- Approved TLS ingress, secure cookie, exact HTTPS Origin, secret rotation and
  backup/restore policy; on-prem production Compose remains disabled.
- Institutional user provisioning/role-change audit, accountable administrator
  lifecycle, MFA or approved federation/SSO requirement, login rate limits at
  the trusted reverse proxy, session retention cleanup and incident response.
- Browser login UX e2e against disposable PostgreSQL and reverse proxy before
  deployment. Tests currently use **only isolated SQLite** plus mocked UI.
- Native React replacement of the legacy Analyzer's Table/ERD/Preflight/
  Report/Run Diff screens, governed by the separate parity PR #178.
