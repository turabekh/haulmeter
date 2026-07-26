"""AI-CONTEXT: put a realistic document wallet on an account so the Docs tab (§10.4)
can be looked at with real data — `make seed-wallet EMAIL=you@example.com`.

Dev convenience only, never CI. It writes through F6's public interface, so the
documents it creates are the same shape the product creates: typed, subject-scoped,
with real expiry dates. Two of them are deliberately close to expiry so the
expiring-soon strip and the 30/14/3 reminder offsets have something to render.

Defaults to the most recently registered account, which is almost always the one the
person running this just signed up with in the browser.
"""

import sys
from datetime import UTC, datetime, timedelta

import db_registry

db_registry.import_all_models()

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.foundation.f01_identity import public as identity  # noqa: E402
from app.foundation.f06_documents import public as documents  # noqa: E402

TODAY = datetime.now(UTC).date()

# a plausible wallet: two healthy, one expiring inside the 30/14/3 window, one lapsed
WALLET = [
    ("cdl", "CDL — Class A", TODAY + timedelta(days=540)),
    ("med_card", "DOT medical card", TODAY + timedelta(days=9)),
    ("insurance", "Liability certificate", TODAY + timedelta(days=210)),
    ("permit", "IFTA licence", TODAY - timedelta(days=3)),
    ("rate_con", "Rate confirmation 4471", None),
]


def main() -> None:
    email = None
    for arg in sys.argv[1:]:
        if arg and "@" in arg:
            email = arg
    db = SessionLocal()
    try:
        if email:
            account = db.scalar(select(identity.Account).where(identity.Account.email == email))
            if account is None:
                print(f"FAIL: no account for {email}")
                print("Register in the browser first, then re-run with that address.")
                sys.exit(1)
        else:
            account = db.scalars(
                select(identity.Account).order_by(identity.Account.created_at.desc()).limit(1)
            ).first()
            if account is None:
                print("FAIL: no accounts exist yet — register in the browser first.")
                sys.exit(1)

        existing = {d.doc_type.value for d in documents.documents_for_account(db, account.id)}
        made = 0
        for doc_type, label, expires_on in WALLET:
            if doc_type in existing:
                continue  # idempotent: re-running does not pile up duplicates
            documents.store_document(
                db,
                account.id,
                documents.DocType(doc_type),
                f"%PDF-1.4 {label}".encode(),
                filename=f"{doc_type}.pdf",
                content_type="application/pdf",
                expires_on=expires_on,
                subject_kind="account",
                subject_ref=account.id,
            )
            made += 1
        db.commit()

        print(f"wallet seeded for {account.email}: {made} new, {len(existing)} already there")
        for doc in documents.documents_for_account(db, account.id):
            status = "—"
            if doc.expires_on:
                days = (doc.expires_on - TODAY).days
                status = "EXPIRED" if days < 0 else f"{days}d"
            when = str(doc.expires_on) if doc.expires_on else "never"
            print(f"   {doc.doc_type.value:12} expires {when:<12} {status}")
        print("\nOpen http://localhost:9008 → Docs. Inspection mode shows the credentials.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
