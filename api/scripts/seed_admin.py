"""AI-CONTEXT: Dev-only admin seed (outside the `app` package, like db_registry).

Creates (idempotently) a platform_admin account in the dev database via the F1
public interface. Credentials come from env (ADMIN_EMAIL / ADMIN_PASSWORD) with
dev defaults — NOT for any real deployment. There is no admin UI yet (F14 Admin
Console is later in the foundation order); this seeds the account so it exists
the moment auth endpoints / F14 land.
"""
import os
import sys

from sqlalchemy import select

from app.core.db import SessionLocal
from app.foundation.f01_identity import public as identity
from app.foundation.f01_identity.domain.models import Account

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@longhaul.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "longhaul-admin-dev")


def main() -> None:
    session = SessionLocal()
    try:
        existing = session.scalar(
            select(Account).where(Account.email == ADMIN_EMAIL.strip().lower())
        )
        if existing is not None:
            sys.stdout.write(f"admin already exists: {ADMIN_EMAIL}\n")
            return
        account = identity.register_account(session, ADMIN_EMAIL, ADMIN_PASSWORD)
        identity.attach_role(session, account, identity.Role.platform_admin)
        session.commit()
        sys.stdout.write(
            f"created platform_admin: {ADMIN_EMAIL} (id={account.id})\n"
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
