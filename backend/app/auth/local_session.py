"""Opt-in, first-party operator identity with revocable server-side sessions.

The session token is an opaque browser cookie. The database stores only its
SHA-256 digest, and an Origin + per-session CSRF check protects unsafe API
requests. This identity never grants clinical/DB authority by itself.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets
from urllib.parse import urlsplit

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.db.session import session_scope
from app.auth.errors import AuthError, AuthErrorCode
from app.auth.models import AuthenticatedActor, Role
from app.core.config import Settings
from app.models.local_auth import LocalSession, LocalUser

COOKIE_NAME = "dqa_session"
CSRF_HEADER = "X-DQA-CSRF"
SESSION_TTL = timedelta(hours=8)
MAX_FAILED_LOGINS = 5
LOGIN_LOCK_DURATION = timedelta(minutes=15)
_USERNAME_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,63}$")
_COOKIE_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_DUMMY_PASSWORD_HASH: str | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    # PostgreSQL TIMESTAMPTZ is aware; SQLite in isolated unit tests is naive.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def validate_local_auth_settings(settings: Settings) -> None:
    """Reject incomplete or unsafe deployment, before accepting credentials."""
    origin = (settings.dqa_local_auth_origin or "").strip()
    parts = urlsplit(origin)
    if (
        not origin
        or parts.scheme not in {"http", "https"}
        or not parts.netloc
        or parts.username is not None
        or parts.password is not None
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
        or origin != f"{parts.scheme}://{parts.netloc}"
    ):
        raise AuthError(AuthErrorCode.PROVIDER_UNAVAILABLE, "local login configuration unavailable")
    key = settings.dqa_local_auth_csrf_key
    if key is None or len(key.get_secret_value().encode("utf-8")) < 32:
        raise AuthError(AuthErrorCode.PROVIDER_UNAVAILABLE, "local login configuration unavailable")
    if settings.app_env not in {"development", "test"}:
        if parts.scheme != "https" or not settings.dqa_local_auth_cookie_secure:
            raise AuthError(AuthErrorCode.PROVIDER_UNAVAILABLE, "local login configuration unavailable")
    elif settings.dqa_local_auth_cookie_secure != (parts.scheme == "https"):
        raise AuthError(AuthErrorCode.PROVIDER_UNAVAILABLE, "local login configuration unavailable")


def validate_origin(request: Request, settings: Settings) -> None:
    """Forbid cross-origin browser mutations and missing Origin assertions."""
    if request.headers.get("origin") != settings.dqa_local_auth_origin:
        raise AuthError(AuthErrorCode.AUTH_CSRF_INVALID, "request origin rejected")


def normalize_username(username: str) -> str:
    value = username.strip().lower()
    if not _USERNAME_RE.fullmatch(value):
        raise ValueError("invalid username")
    return value


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if not 12 <= len(password) <= 128 or "\x00" in password:
        raise ValueError("password must be 12-128 characters")
    salt_bytes = salt if salt is not None else secrets.token_bytes(16)
    if len(salt_bytes) != 16:
        raise ValueError("invalid salt")
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt_bytes, n=2**15, r=8, p=1,
        dklen=32, maxmem=64 * 1024 * 1024,
    )
    return f"scrypt-v1${salt_bytes.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        name, salt_hex, digest_hex = encoded.split("$")
        if name != "scrypt-v1" or len(salt_hex) != 32 or len(digest_hex) != 64:
            return False
        salt_bytes = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt_bytes, n=2**15, r=8, p=1,
            dklen=32, maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(actual, expected)
    except (UnicodeError, ValueError, TypeError):
        return False


def _verify_unknown_user(password: str) -> None:
    global _DUMMY_PASSWORD_HASH
    if _DUMMY_PASSWORD_HASH is None:
        _DUMMY_PASSWORD_HASH = hash_password("not-an-actual-dqa-password")
    verify_password(password, _DUMMY_PASSWORD_HASH)


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def csrf_for_token(token: str, settings: Settings) -> str:
    key = settings.dqa_local_auth_csrf_key
    if key is None:
        raise AuthError(AuthErrorCode.PROVIDER_UNAVAILABLE, "local login configuration unavailable")
    return hmac.new(
        key.get_secret_value().encode("utf-8"), f"dqa-csrf-v1:{token}".encode("ascii"), hashlib.sha256,
    ).hexdigest()


def _roles_for_user(user: LocalUser) -> frozenset[Role]:
    try:
        if not isinstance(user.roles, list) or not user.roles:
            raise ValueError("missing roles")
        roles = frozenset(Role(role) for role in user.roles)
        if len(roles) != len(user.roles):
            raise ValueError("duplicated roles")
        return roles
    except (TypeError, ValueError) as exc:
        raise AuthError(AuthErrorCode.AUTHENTICATION_INVALID, "invalid session") from exc


def login_with_password(username: str, password: str) -> str:
    """Authenticate and issue one opaque token, with DB-backed lockout."""
    try:
        normalized = normalize_username(username)
    except ValueError:
        normalized = None

    with session_scope() as session:
        user = session.scalar(
            select(LocalUser).where(LocalUser.username == normalized).with_for_update()
        ) if normalized else None
        if user is None:
            _verify_unknown_user(password)
            raise AuthError(AuthErrorCode.AUTHENTICATION_INVALID, "invalid username or password")

        now = utcnow()
        if user.locked_until and _as_utc(user.locked_until) > now:
            raise AuthError(AuthErrorCode.AUTHENTICATION_INVALID, "invalid username or password")
        if not user.is_active:
            _verify_unknown_user(password)
            raise AuthError(AuthErrorCode.AUTHENTICATION_INVALID, "invalid username or password")
        if not verify_password(password, user.password_hash):
            user.failed_login_count += 1
            if user.failed_login_count >= MAX_FAILED_LOGINS:
                user.locked_until = now + LOGIN_LOCK_DURATION
            # The context manager commits this failed-attempt update only if
            # we leave without raising inside its transaction boundary.
            invalid = True
        else:
            invalid = False

        if invalid:
            session.flush()
        else:
            _roles_for_user(user)
            user.failed_login_count = 0
            user.locked_until = None
            token = secrets.token_urlsafe(32)
            session.add(LocalSession(
                user_id=user.id, token_sha256=_token_digest(token), expires_at=now + SESSION_TTL,
            ))
    if invalid:
        raise AuthError(AuthErrorCode.AUTHENTICATION_INVALID, "invalid username or password")
    return token


def get_active_session(token: str, session: Session) -> tuple[LocalUser, LocalSession]:
    if not _COOKIE_RE.fullmatch(token):
        raise AuthError(AuthErrorCode.AUTHENTICATION_INVALID, "invalid session")
    row = session.execute(
        select(LocalUser, LocalSession)
        .join(LocalSession, LocalSession.user_id == LocalUser.id)
        .where(LocalSession.token_sha256 == _token_digest(token))
    ).one_or_none()
    if row is None:
        raise AuthError(AuthErrorCode.AUTHENTICATION_INVALID, "invalid session")
    user, active_session = row
    if (not user.is_active or active_session.revoked_at is not None
            or _as_utc(active_session.expires_at) <= utcnow()):
        raise AuthError(AuthErrorCode.AUTHENTICATION_INVALID, "invalid session")
    _roles_for_user(user)
    return user, active_session


def revoke_session(token: str) -> None:
    with session_scope() as session:
        _, active_session = get_active_session(token, session)
        active_session.revoked_at = utcnow()


class LocalSessionIdentityProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def authenticate(self, request: Request) -> AuthenticatedActor:
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise AuthError(AuthErrorCode.AUTHENTICATION_REQUIRED, "authentication required")
        with session_scope() as session:
            user, _ = get_active_session(token, session)
            actor = AuthenticatedActor(
                actor_id=user.username, roles=_roles_for_user(user),
                provider="local_session", display_name=user.display_name,
            )
        if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            validate_origin(request, self.settings)
            expected = csrf_for_token(token, self.settings)
            presented = request.headers.get(CSRF_HEADER, "")
            if not hmac.compare_digest(presented, expected):
                raise AuthError(AuthErrorCode.AUTH_CSRF_INVALID, "CSRF validation failed")
        return actor
