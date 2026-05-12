#!/usr/bin/env python3
"""Read-only account and authentication database audit.

This script is safe to run during production checks. It only opens auth.db in
read-only mode and never verifies passwords, writes users, or mutates login
state.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DATA_DIR = Path(os.environ.get("GAME_VIDEO_DATA_DIR", "/home/deploy/game-video-data"))


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def normalize_ip_list(value: str) -> list[str]:
    return [item.strip() for item in (value or "").replace("，", ",").split(",") if item.strip()]


def audit_accounts(data_dir: Path, expected_admin: str | None, expected_users: list[str]) -> dict:
    auth_db = data_dir / "auth.db"
    report: dict = {
        "action": "auth_account_audit",
        "readonly": True,
        "created_at": now_iso(),
        "data_dir": str(data_dir),
        "auth_db": str(auth_db),
        "auth_db_exists": auth_db.exists(),
        "errors": [],
        "warnings": [],
        "recommendations": [],
    }
    if not auth_db.exists():
        report["errors"].append("auth.db does not exist")
        return report

    conn = connect_readonly(auth_db)
    try:
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if not table_exists:
            report["errors"].append("users table does not exist")
            return report

        columns = table_columns(conn, "users")
        required = {"id", "username", "display_name", "role", "is_active", "created_at"}
        missing = sorted(required - columns)
        if missing:
            report["errors"].append(f"users table missing columns: {', '.join(missing)}")
            return report

        optional_columns = [
            "team",
            "allowed_ips",
            "must_change_password",
            "last_login",
        ]
        select_columns = [
            "id",
            "username",
            "display_name",
            "role",
            "is_active",
            "created_at",
        ] + [col for col in optional_columns if col in columns]
        rows = [
            dict(row)
            for row in conn.execute(
                f"SELECT {', '.join(select_columns)} FROM users ORDER BY created_at, username"
            ).fetchall()
        ]
    finally:
        conn.close()

    active_rows = [row for row in rows if int(row.get("is_active") or 0) == 1]
    active_admins = [row for row in active_rows if row.get("role") == "admin"]
    usernames = [row.get("username") or "" for row in rows]
    username_counts = Counter(usernames)
    duplicate_usernames = sorted([name for name, count in username_counts.items() if count > 1])
    legacy_admin = [row for row in active_admins if row.get("username") == "admin"]

    link_local_ip_users = []
    empty_username_users = []
    inactive_admins = []
    for row in rows:
        username = row.get("username") or ""
        if not username:
            empty_username_users.append(row.get("id"))
        if row.get("role") == "admin" and int(row.get("is_active") or 0) != 1:
            inactive_admins.append(username or row.get("id"))
        ips = normalize_ip_list(row.get("allowed_ips", ""))
        if any(ip.startswith("169.254.") for ip in ips):
            link_local_ip_users.append({
                "username": username,
                "display_name": row.get("display_name", ""),
                "allowed_ips": row.get("allowed_ips", ""),
            })

    expected_user_results = []
    row_by_username = {row.get("username"): row for row in rows}
    for username in expected_users:
        row = row_by_username.get(username)
        expected_user_results.append({
            "username": username,
            "exists": row is not None,
            "is_active": bool(row and int(row.get("is_active") or 0) == 1),
            "role": row.get("role") if row else None,
            "team": row.get("team", "") if row else "",
            "allowed_ips": row.get("allowed_ips", "") if row else "",
            "must_change_password": int(row.get("must_change_password") or 0) if row else None,
            "last_login": row.get("last_login", "") if row else "",
        })
        if not row:
            report["errors"].append(f"expected user missing: {username}")
        elif int(row.get("is_active") or 0) != 1:
            report["errors"].append(f"expected user inactive: {username}")

    if not active_admins:
        report["errors"].append("no active admin user found")
    if len(active_admins) > 1:
        report["warnings"].append("more than one active admin user exists")
    if duplicate_usernames:
        report["errors"].append(f"duplicate usernames found: {', '.join(duplicate_usernames)}")
    if empty_username_users:
        report["errors"].append("users with empty username found")
    if inactive_admins:
        report["warnings"].append(f"inactive admin users exist: {', '.join(inactive_admins)}")
    if legacy_admin:
        report["warnings"].append("active admin still uses legacy username 'admin'")
    if link_local_ip_users:
        report["warnings"].append("some users are restricted to 169.254.x.x link-local IPs")
        report["recommendations"].append(
            "If those users cannot log in from the browser, replace 169.254.x.x with their real client IP."
        )

    if expected_admin:
        admin_row = row_by_username.get(expected_admin)
        if not admin_row:
            report["errors"].append(f"expected admin username missing: {expected_admin}")
        elif admin_row.get("role") != "admin" or int(admin_row.get("is_active") or 0) != 1:
            report["errors"].append(f"expected admin is not an active admin: {expected_admin}")

    report.update({
        "user_count": len(rows),
        "active_user_count": len(active_rows),
        "inactive_user_count": len(rows) - len(active_rows),
        "active_admin_count": len(active_admins),
        "active_admins": [
            {
                "username": row.get("username"),
                "display_name": row.get("display_name", ""),
                "last_login": row.get("last_login", ""),
            }
            for row in active_admins
        ],
        "role_counts": dict(Counter(row.get("role", "") for row in rows)),
        "must_change_password_count": sum(
            1 for row in active_rows if int(row.get("must_change_password") or 0) == 1
        ),
        "link_local_ip_users": link_local_ip_users,
        "expected_users": expected_user_results,
    })
    if not report["errors"]:
        report["recommendations"].append("Account audit completed without blocking errors.")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only audit for game-video-tool auth accounts.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--expected-admin", default="")
    parser.add_argument(
        "--expected-user",
        action="append",
        default=[],
        help="Expected active username. Repeat for multiple users.",
    )
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    report = audit_accounts(
        data_dir=args.data_dir,
        expected_admin=args.expected_admin or None,
        expected_users=args.expected_user,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.json_only:
        print("SUMMARY")
        print(f"readonly: {report.get('readonly')}")
        print(f"user_count: {report.get('user_count', 0)} active: {report.get('active_user_count', 0)}")
        print(f"active_admin_count: {report.get('active_admin_count', 0)}")
        print(f"errors: {len(report.get('errors', []))} warnings: {len(report.get('warnings', []))}")
        for message in report.get("errors", []):
            print(f"ERROR: {message}")
        for message in report.get("warnings", []):
            print(f"WARN: {message}")
        for message in report.get("recommendations", []):
            print(f"- {message}")
    return 1 if report.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
