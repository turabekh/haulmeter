"""AI-CONTEXT: one real poll against the real provider, by hand (M14-FR2, E2 slice 1).

WHY THIS TARGET EXISTS AT ALL. F-01 is the whole argument: for the life of this product
F8 recorded every detention notice as `sent` while every one of them went to a container
on the VM, and the suite was green throughout because it asserted against the gateway it
faked. A connector is the same shape with a different third party — a poller that never
fires, a fake that hides a null, a provider whose response shape moved. So the kickoff's
rule is that **a connector ships with an end-to-end proof against the real provider,
OBSERVED, before its flag is eligible**, and this is how that observation happens.

CI NEVER CALLS MOTIVE. This is a make target run by a human with a real key, and its
output is pasted into a handoff. It is not imported by any test.

READ-ONLY. D8 narrowed v1.0 §16 to permit exactly this and nothing more: consuming a
fleet's own provider API. There is no write path here and there must never be one.

Usage:
    make m14-poll-once FLEET=<fleet_uuid>
"""

import os
import sys

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.m14_recovery import public as m14
from app.modules.m14_recovery.domain.crypto import decrypt_key


def main() -> int:
    fleet = os.environ.get("FLEET", "").strip()
    with SessionLocal() as db:
        stmt = select(m14.Connector)
        if fleet:
            stmt = stmt.where(m14.Connector.fleet_id == fleet)
        connectors = list(db.scalars(stmt))
        if not connectors:
            print("no connector rows — connect a fleet first (paste its key)")
            return 1

        for connector in connectors:
            print(f"\n=== connector {connector.id} · {connector.provider.value} ===")
            print(f"    fleet      : {connector.fleet_id}")
            # the ONLY part of a key that is ever printed
            print(f"    key        : ****{connector.key_last4}")
            print(f"    status     : {connector.status.value}")
            print(f"    last sync  : {connector.last_sync_at}")
            try:
                # decrypt here only to prove the secret is installed; `poll_connector`
                # does its own and the plaintext never leaves that call
                decrypt_key(connector.key_ciphertext)
            except Exception as exc:  # noqa: BLE001
                print(f"    KEY UNREADABLE: {exc}")
                print("    (is M14_CONNECTOR_KEY set on this box?)")
                return 2

            try:
                result = m14.poll_connector(db, connector)
            except Exception as exc:  # noqa: BLE001
                print(f"    POLL FAILED: {type(exc).__name__}: {exc}")
                print(f"    connector marked: {connector.status.value}")
                db.commit()  # the failure is recorded on the row and worth keeping
                return 3

            db.commit()
            print(f"    imported   : {result.imported}")
            print(f"    duplicates : {result.duplicates}")
            print(f"    unmapped   : {result.skipped_unmapped} {sorted(result.unmapped_refs)}")
            print(f"    events     : {[getattr(e, 'event_type', e) for e in result.events]}")
            if result.skipped_unmapped:
                print("    NOTE: unmapped vehicles are SKIPPED, never guessed — map them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
