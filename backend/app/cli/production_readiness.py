"""CLI entrypoint for Production Readiness Report (read-only).

Usage (from backend working directory / migrate image):

  python -m app.cli.production_readiness \\
    --source-name oracle_demis_mock \\
    --environment development

Exit codes:
  0 — report generated and overall_status == READY
  1 — NOT_READY, inspection failure, or invalid arguments

Never prints credentials, DSN, SQL text, or DEMIS probe row data.
Never opens DEMIS connections or resolves DEMIS credentials.
"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="DQA Production Readiness Report (read-only preflight)",
    )
    parser.add_argument("--source-name", required=True, help="Catalog source name")
    parser.add_argument(
        "--environment",
        required=True,
        help="Connection Profile environment name",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON (sanitized report only)",
    )
    args = parser.parse_args(argv)

    source_name = args.source_name.strip()
    environment = args.environment.strip()
    if not source_name or not environment:
        print("error: --source-name and --environment are required", file=sys.stderr)
        return 1

    try:
        from app.adapters.db.session import get_session_factory
        from app.services.production_readiness import build_production_readiness_report
    except Exception as exc:  # noqa: BLE001 — sanitized import failure
        print(
            f"error: readiness inspection failed ({exc.__class__.__name__})",
            file=sys.stderr,
        )
        return 1

    session = get_session_factory()()
    try:
        report = build_production_readiness_report(
            session,
            source_name=source_name,
            environment=environment,
        )
    except Exception as exc:  # noqa: BLE001 — never echo DB/URL details
        print(
            f"error: readiness inspection failed ({exc.__class__.__name__})",
            file=sys.stderr,
        )
        return 1
    finally:
        session.close()

    payload = report.model_dump()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human_summary(payload)

    return 0 if report.overall_status == "READY" else 1


def _print_human_summary(payload: dict) -> None:
    print("DQA Production Readiness Report")
    print(f"source_name: {payload['source_name']}")
    print(f"environment: {payload['environment']}")
    print(f"overall_status: {payload['overall_status']}")
    print("checks:")
    for item in payload["checks"]:
        print(f"  - {item['code']}: {item['status']} — {item['message']}")
    if payload["overall_status"] != "READY":
        print(
            "note: LIVE_CONNECTIVITY and EXTERNAL_READONLY_PRIVILEGE remain "
            "ACTION_REQUIRED until externally resolved; they are never auto-PASS."
        )


if __name__ == "__main__":
    raise SystemExit(main())
