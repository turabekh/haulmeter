"""AI-CONTEXT: the 15-minute pilot path — connect a fleet on a phone call (M14 slice 1).

WHY A CLI AND NOT A SCREEN. This was a judgment call and the reasoning is on the record
because the session skipped plan approval. A Fleet Workspace mapping surface needs a
two-column picker — provider vehicles on one side, driver accounts on the other, bound in
pairs — and no such component exists in this system. §22.2 does not let a session invent a
component pattern, and the kickoff names the tell: *"If the surface would need a pattern
that doesn't exist, that's the signal to ship the CLI instead."*

The operational argument points the same way. On a call the owner is already on the box;
a CLI has no session to expire, no portal role to grant first, no browser to share, and it
prints exactly what it did. A half-built portal flow that stalls on a 403 mid-call is the
worst outcome available here.

WHAT IT NEVER DOES: echo the key. It is read from stdin (or `KEY=`), encrypted, and from
that moment only `****last4` is ever printed — including in error paths, which is where
credentials usually leak.

    make m14-onboard                       # guided, one step at a time
    make m14-onboard FLEET=<uuid>          # skip straight to a known fleet
"""

import os
import sys
import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.foundation.f01_identity import public as identity
from app.modules.m14_recovery import public as m14
from app.modules.m14_recovery.domain.crypto import ConnectorKeyUnavailable

RULE = "─" * 64


def _say(step: str, text: str = "") -> None:
    print(f"\n{RULE}\n{step}\n{RULE}")
    if text:
        print(text)


def _ask(prompt: str, default: str = "") -> str:
    if not sys.stdin.isatty():
        return default
    got = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return got or default


def _fleet_id() -> uuid.UUID | None:
    raw = os.environ.get("FLEET", "").strip() or _ask("Fleet id (uuid)")
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        print(f"  '{raw}' is not a uuid")
        return None


def main() -> int:  # noqa: C901 — a guided script is a sequence, not a branchy function
    print("\nM14 pilot onboarding — connect one fleet's telematics, read-only.")
    print("Nothing here sends anything to anybody. Ctrl-C is safe at every step.")

    fleet = _fleet_id()
    if fleet is None:
        print("\nNo fleet id — stopping. (`make m14-onboard FLEET=<uuid>`)")
        return 1

    with SessionLocal() as db:
        # --- 1. the key -----------------------------------------------------------
        _say(
            "STEP 1 of 5 — paste the fleet's Motive API key",
            "Ask the admin to read it out, or paste it yourself. It is encrypted before\n"
            "it touches the database and is never printed back.",
        )
        key = os.environ.get("KEY", "").strip() or _ask("API key (input is not echoed back)")
        if not key:
            print("  no key — stopping")
            return 1
        try:
            connector = m14.connect_fleet(db, fleet, key, m14.Provider.motive)
        except ConnectorKeyUnavailable as exc:
            print(f"  REFUSED: {exc}")
            print("  M14_CONNECTOR_KEY is not set on this box. A key must never be stored")
            print("  unencrypted, so onboarding stops here rather than falling back.")
            return 2
        db.commit()
        key_shown = f"****{connector.key_last4}"
        print(f"  stored, encrypted. Key is {key_shown} from here on.")

        # --- 2. the vehicles ------------------------------------------------------
        _say("STEP 2 of 5 — ask Motive which vehicles this key can see")
        client = m14.MotiveClient(key)
        vehicles: list[dict] = []
        try:
            vehicles = client.vehicles()
            print(f"  /v1/vehicles returned {len(vehicles)}")
        except Exception as exc:  # noqa: BLE001
            print(f"  /v1/vehicles failed: {type(exc).__name__}: {exc}")
            print("  falling back to the endpoint the POLLER is known to work against")
        if not vehicles:
            try:
                crumbs = client.vehicle_locations()
                seen = {c.vehicle_ref for c in crumbs}
                vehicles = [{"ref": r, "number": "", "vin": ""} for r in sorted(seen)]
                print(f"  /v3/vehicle_locations knows {len(vehicles)} vehicle(s)")
            except Exception as exc:  # noqa: BLE001
                # AI-CONTEXT: mark the row, the way `poll_connector` does. The first
                # walkthrough printed "connector marked active" immediately after the
                # provider refused us — because step 2 calls the client directly and only
                # `poll_connector` sets `failing`. A screen saying `active` about a
                # connector that just got a 401 is the same species of lie this module is
                # built to avoid; it is one line, and it was found by running the script
                # rather than by reading it.
                connector.status = m14.ConnectorStatus.failing
                connector.health_detail = str(exc)[:500]
                db.commit()
                print(f"  REFUSED by the provider: {type(exc).__name__}: {exc}")
                print(f"  connector marked {connector.status.value}; the key ({key_shown}) may")
                print("  be wrong, revoked, or lack the fleet scope. Nothing else to do here.")
                return 3
        for v in vehicles:
            label = " ".join(x for x in (v.get("number"), v.get("vin")) if x)
            print(f"    {v['ref']:<24} {label}")

        # --- 3. the mapping -------------------------------------------------------
        _say(
            "STEP 3 of 5 — map each truck to the driver who drives it",
            "AN UNMAPPED VEHICLE IS SKIPPED, NEVER GUESSED. Attributing one driver's dwell\n"
            "to another driver's claim is the worst mistake this module can make, so a\n"
            "truck you skip here simply produces no claims until somebody maps it.",
        )
        drivers = list(db.scalars(select(identity.Account).order_by(identity.Account.email)))
        for i, d in enumerate(drivers[:40], 1):
            print(f"    {i:>3}. {d.email}")
        if len(drivers) > 40:
            print(f"    … and {len(drivers) - 40} more (use the email directly)")

        mapped = 0
        for v in vehicles:
            who = _ask(f"  driver for vehicle {v['ref']} (email, number, or blank to skip)")
            if not who:
                continue
            account = None
            if who.isdigit() and 1 <= int(who) <= len(drivers):
                account = drivers[int(who) - 1]
            else:
                account = db.scalar(
                    select(identity.Account).where(identity.Account.email == who)
                )
            if account is None:
                print(f"    no account '{who}' — skipped, map it later")
                continue
            m14.map_vehicle(db, connector, v["ref"], account.id)
            mapped += 1
            print(f"    {v['ref']} → {account.email}")
        db.commit()
        print(f"  {mapped} of {len(vehicles)} vehicle(s) mapped")

        # --- 4. one poll ----------------------------------------------------------
        _say("STEP 4 of 5 — one real poll, right now")
        try:
            result = m14.poll_connector(db, connector)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            print(f"  poll failed: {type(exc).__name__}: {exc}")
            print(f"  connector marked {connector.status.value} with the reason recorded")
            db.commit()
            return 4
        print(f"  imported          : {result.imported}")
        print(f"  duplicates        : {result.duplicates}")
        print(f"  skipped (unmapped): {result.skipped_unmapped} {sorted(result.unmapped_refs)}")
        print(f"  geofence events   : {[getattr(e, 'event_type', e) for e in result.events]}")

        # --- 5. where it stands ---------------------------------------------------
        _say("STEP 5 of 5 — where this fleet now stands")
        allowed, blocker = m14.can_send(db)
        enabled = m14.is_enabled(db)
        print(f"  connector          : {connector.status.value}, key {key_shown}")
        print(f"  vehicles mapped    : {mapped}")
        print(f"  traces imported    : {result.imported}")
        print(f"  m14_overlay ON     : {enabled}")
        print(f"  claims may SEND    : {allowed}" + ("" if allowed else f"  (blocked: {blocker})"))
        print("")
        if not enabled:
            print("  The overlay is OFF, so the worker will not poll on its own yet and no")
            print("  claim will draft. That is an owner decision (a flag), not this script's.")
        if not allowed:
            print("  Claims will DRAFT and HOLD. Approving one records the decision and sends")
            print("  nothing while the gate above is unsatisfied — which is D13, an owner call.")
        print("\n  Next: `make m14-validate` once this fleet has run some stops.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
