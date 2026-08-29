"""
Manage the signup allowlist — the stopgap gate on new account creation that
runs until billing exists (see prephase6_addendum_allowlist.md).

Talks to the database directly using DATABASE_URL from .env, so the API server
does not need to be running.

Usage:
    python manage_allowlist.py add someone@example.com
    python manage_allowlist.py remove someone@example.com
    python manage_allowlist.py list

Emails are stored lowercased; the signup check is case-insensitive.
"""
import argparse
import sys

from app.database import Base, SessionLocal, engine
from app.models import SignupAllowlist

# Ensures the signup_allowlist table exists even if the API server has never
# run against this database yet. Creates missing tables only; never drops.
Base.metadata.create_all(bind=engine)


def _normalize(email: str) -> str:
    return email.strip().lower()


def cmd_add(email: str) -> int:
    email = _normalize(email)
    if not email:
        print("error: empty email", file=sys.stderr)
        return 1
    db = SessionLocal()
    try:
        if db.query(SignupAllowlist).filter(SignupAllowlist.email == email).first():
            print(f"already on the allowlist: {email}")
            return 0
        db.add(SignupAllowlist(email=email))
        db.commit()
        print(f"added: {email}")
        return 0
    finally:
        db.close()


def cmd_remove(email: str) -> int:
    email = _normalize(email)
    db = SessionLocal()
    try:
        row = db.query(SignupAllowlist).filter(SignupAllowlist.email == email).first()
        if not row:
            print(f"not on the allowlist: {email}")
            return 0
        db.delete(row)
        db.commit()
        print(f"removed: {email}")
        return 0
    finally:
        db.close()


def cmd_list() -> int:
    db = SessionLocal()
    try:
        rows = db.query(SignupAllowlist).order_by(SignupAllowlist.added_at).all()
        if not rows:
            print("(allowlist is empty)")
            return 0
        for row in rows:
            print(f"{row.email}\t{row.added_at:%Y-%m-%d %H:%M}")
        return 0
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the signup allowlist.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="add an email to the allowlist")
    p_add.add_argument("email")

    p_remove = sub.add_parser("remove", help="remove an email from the allowlist")
    p_remove.add_argument("email")

    sub.add_parser("list", help="list all allowed emails")

    args = parser.parse_args(argv)

    if args.command == "add":
        return cmd_add(args.email)
    if args.command == "remove":
        return cmd_remove(args.email)
    if args.command == "list":
        return cmd_list()
    parser.error(f"unknown command: {args.command}")  # unreachable; argparse guards
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
