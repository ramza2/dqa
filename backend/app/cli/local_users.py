"""Console-only local operator provisioning; no public bootstrap endpoint.

Usage (after Alembic migration):
  python -m app.cli.local_users create --username admin1 --role administrator
  python -m app.cli.local_users set-password --username admin1
  python -m app.cli.local_users disable --username employee1

Passwords are always prompted, never accepted as argv or environment values.
"""

from __future__ import annotations

import argparse
from getpass import getpass
import sys

from sqlalchemy import select, update

from app.adapters.db.session import session_scope
from app.auth.local_session import hash_password, normalize_username, utcnow
from app.auth.models import Role
from app.models.local_auth import LocalSession, LocalUser


def _password_prompt() -> str:
    password = getpass("New password (12-128 chars): ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("password confirmation mismatch")
    return hash_password(password)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DQA local user operator provisioning")
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("create")
    create.add_argument("--username", required=True)
    create.add_argument("--display-name", default=None)
    create.add_argument("--role", action="append", choices=[role.value for role in Role], required=True)
    set_password = sub.add_parser("set-password")
    set_password.add_argument("--username", required=True)
    disable = sub.add_parser("disable")
    disable.add_argument("--username", required=True)
    args = parser.parse_args(argv)

    try:
        username = normalize_username(args.username)
        password_hash = _password_prompt() if args.action in {"create", "set-password"} else None
        with session_scope() as session:
            user = session.scalar(select(LocalUser).where(LocalUser.username == username).with_for_update())
            if args.action == "create":
                if user is not None:
                    raise ValueError("user already exists")
                roles = sorted(set(args.role))
                display_name = args.display_name or username
                if not display_name.strip() or len(display_name) > 128:
                    raise ValueError("invalid display name")
                session.add(LocalUser(
                    username=username, display_name=display_name.strip(),
                    password_hash=password_hash, roles=roles,
                    is_active=True, failed_login_count=0,
                ))
            else:
                if user is None:
                    raise ValueError("user not found")
                if args.action == "disable":
                    if Role.ADMINISTRATOR.value in user.roles:
                        raise ValueError("administrator cannot be disabled by this CLI")
                    user.is_active = False
                else:
                    user.password_hash = password_hash
                    user.failed_login_count = 0
                    user.locked_until = None
                session.execute(
                    update(LocalSession).where(
                        LocalSession.user_id == user.id, LocalSession.revoked_at.is_(None),
                    ).values(revoked_at=utcnow())
                )
    except ValueError as exc:
        print(f"Local user update rejected: {exc}", file=sys.stderr)
        return 2
    print(f"Local user {args.action} complete: {username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
