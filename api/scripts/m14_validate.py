"""AI-CONTEXT: `make m14-validate` — the ±3-minute check, one command (M14-FR2).

Ground truth is entered per stop with a REQUIRED source, and a provider-derived source is
refused in code rather than in a comment: Motive validating Motive proves only that the
poller copies faithfully, which unit tests already cover. See `domain/validation.py`.

Reads the ELD-derived arrival/departure from F3's own visit window — the same call M3's
clock uses — so what is being compared is exactly what a claim would argue from, not a
re-derivation that could agree with the truth for the wrong reason.

    make m14-validate FLEET=<uuid>          # guided entry, then the report
    make m14-validate FLEET=<uuid> FILE=gt.csv
        stop_ref,arrived_at,departed_at,source,note      (ISO-8601 timestamps)
"""

import csv
import os
import sys
import uuid
from datetime import UTC, datetime

from app.core.db import SessionLocal
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.modules.m14_recovery.domain import validation as V


def _parse_dt(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _from_file(path: str) -> list[V.GroundTruth]:
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out.append(
                V.GroundTruth(
                    stop_ref=row["stop_ref"].strip(),
                    arrived_at=_parse_dt(row["arrived_at"]),
                    departed_at=_parse_dt(row.get("departed_at", "")),
                    source=row["source"].strip(),
                    note=(row.get("note") or "").strip(),
                )
            )
    return out


def _interactive() -> list[V.GroundTruth]:
    print("\nGround truth, one stop at a time. Blank stop id ends entry.")
    print("Sources: " + ", ".join(f"{k} ({v})" for k, v in V.SOURCE_KINDS.items()))
    print("A source naming the provider is REFUSED — it would validate nothing.\n")
    out = []
    while True:
        stop_ref = input("  stop id (blank to finish): ").strip()
        if not stop_ref:
            return out
        try:
            out.append(
                V.GroundTruth(
                    stop_ref=stop_ref,
                    arrived_at=_parse_dt(input("    arrived  (ISO, e.g. 2026-08-15T09:04:00Z): ")),
                    departed_at=_parse_dt(input("    departed (ISO, blank if still there): ")),
                    source=input(f"    source   ({'/'.join(V.SOURCE_KINDS)}): "),
                    note=input("    note     (optional): "),
                )
            )
            print("    recorded\n")
        except V.CircularGroundTruth as exc:
            print(f"    REFUSED: {exc}\n")
        except Exception as exc:  # noqa: BLE001
            print(f"    could not read that: {exc}\n")


def main() -> int:
    fleet_raw = os.environ.get("FLEET", "").strip()
    if not fleet_raw:
        print("usage: make m14-validate FLEET=<uuid> [FILE=ground-truth.csv]")
        return 1
    fleet = uuid.UUID(fleet_raw)

    path = os.environ.get("FILE", "").strip()
    try:
        truths = _from_file(path) if path else _interactive()
    except V.CircularGroundTruth as exc:
        print(f"REFUSED: {exc}")
        return 2
    if not truths:
        print("no ground truth entered — nothing to compare")
        return 1

    with SessionLocal() as db:
        comparisons = []
        for truth in truths:
            stop = loads.get_stop(db, uuid.UUID(truth.stop_ref))
            if stop is None:
                print(f"  stop {truth.stop_ref[:8]} not found — skipped")
                continue
            account_id = loads.stop_account_id(db, stop)
            # the SAME window M3's clock argues from, not a re-derivation that could
            # agree with the truth for the wrong reason
            arrival, departure = location.visit_window(
                db, account_id, stop.facility_id, truth.arrived_at
            )
            comparisons.append(V.compare(truth, arrival, departure))

        # which sources actually backed these stops — a validation run over phone-derived
        # traces would prove nothing about the ELD path, so it is stated rather than assumed
        sources = set()
        for truth in truths:
            stop = loads.get_stop(db, uuid.UUID(truth.stop_ref))
            if stop is not None:
                sources |= location.ping_sources(
                    db, loads.stop_account_id(db, stop), truth.arrived_at,
                    truth.departed_at or datetime.now(UTC),
                )

    print("\n" + "=" * 68)
    print(f"M14 slice 1 — ±{V.TARGET_MINUTES:.0f} min validation · fleet {fleet}")
    print(f"generated {datetime.now(UTC).isoformat(timespec='seconds')}")
    print("=" * 68 + "\n")
    print(V.report(comparisons))
    eld = sorted(s for s in sources if s.startswith("eld:"))
    print(f"\n> Trace sources behind these stops: {sorted(sources) or 'none'}")
    if not eld:
        print("> **NO ELD-SOURCED TRACES.** This run validates the phone path, not FR2's.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
