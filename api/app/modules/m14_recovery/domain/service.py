"""AI-CONTEXT: M14 Fleet Recovery Overlay — slice 1 (PRD Extension E2, owner decision D8).

Authorized scope is one slice and no more: evidence classes (FR3), one Motive connector
with a pasted key and polling (FR2), and ELD dwell drafting the EXISTING M3 claim, held
for a fleet admin (FR4). FR1, FR5 beyond hold-all, and FR6–FR9 are PROPOSED and absent.

**M14 DOES NOT FORK M3.** It feeds it. An ELD-derived claim moves through the same states,
the same templates, the same dunning and the same ledger as a phone-verified one; the pack
declares its basis and nothing else differs. Everything M3 does is reached through
`m03.public` — never past it — and the import-linter contract holds that.

THE WHOLE TRICK, in one sentence: `f03.evaluate_ping` is ACCOUNT-centric — it locks a
cursor for one account and walks that account's active armings — so a provider breadcrumb
becomes a first-class F3 ping the moment it can name an account, and the geofence engine,
the dwell ticks and M3's arming consume it without knowing a phone was not involved. There
is no second geofence path and there must never be one.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f13_flags import public as flags
from app.modules.m03_detention import public as m3

from .crypto import decrypt_key, encrypt_key, last4
from .enums import ConnectorStatus, EvidenceClass, HoldState, Provider
from .models import Connector, HeldClaim, TraceImport, VehicleMap
from .provider import Breadcrumb, MotiveClient

FLAG_KEY = "m14_overlay"
MODULE = "m14"

# AI-CONTEXT: the gates, and the first one is INHERITED on purpose (E2 §E2.6).
#
# `legal_signoff` is M3's own precondition and it is unsatisfied today — every boot says
# so. M14 drafting into M3's pipeline must not launder the claims path past a gate M3
# itself has not cleared; a module that reaches its predecessor's money while skipping its
# predecessor's precondition is exactly the kind of quiet widening §E2.6 forbids.
#
# `carrier_invoicing_counsel` is D13: fleet-originated claims invoice in the CARRIER's
# name, which is a different legal posture from the driver-name billing agent v1.0 §13
# describes. D13 is OPEN, so this gate is unsatisfied and `can_send` below refuses.
GATES = ["legal_signoff", "carrier_invoicing_counsel"]

# what `source` an ELD ping carries into F3. Namespaced by provider so a second connector
# is distinguishable in the trail rather than merged into an anonymous "eld".
SOURCE_PREFIX = "eld:"


def register_module(db: Session) -> None:
    """AI-CONTEXT: NO `default_on`, and that is §13.14 rather than caution.

    A capability that has never shipped declares nothing and lets its gates govern.
    `register_flag` has no `enabled` parameter at all since audit F-02 — a flag born
    enabled never passes through `enable()`, which is the only function that reads a
    validation gate, and that is how six gates across M3, M6 and M7 came to have never
    been read while their modules ran.
    """
    flags.register_flag(db, FLAG_KEY, description="M14 Fleet Recovery Overlay")
    for gate in GATES:
        flags.add_gate(db, FLAG_KEY, gate)


def is_enabled(db: Session) -> bool:
    return flags.is_enabled(db, FLAG_KEY)


# --- FR2: the connector ------------------------------------------------------------


class UnmappedVehicle(Exception):
    pass


def connect_fleet(
    db: Session, fleet_id, api_key: str, provider: Provider = Provider.motive
) -> Connector:
    """Store a fleet's pasted key, encrypted. Re-pasting REPLACES.

    A second row for the same (fleet, provider) is a re-paste — a rotated or corrected
    key — not a second connector, and the unique constraint says so in Postgres. This is
    migration 0077's lesson from one session ago applied before the defect rather than
    after it.
    """
    key = (api_key or "").strip()
    if not key:
        raise ValueError("an empty key is not a connector")
    ciphertext = encrypt_key(key)  # refuses loudly if M14_CONNECTOR_KEY is unset

    row = db.scalar(
        select(Connector).where(
            Connector.fleet_id == fleet_id, Connector.provider == provider
        )
    )
    if row is None:
        row = Connector(fleet_id=fleet_id, provider=provider)
        db.add(row)
    row.key_ciphertext = ciphertext
    row.key_last4 = last4(key)
    row.status = ConnectorStatus.active
    row.health_detail = None
    db.flush()
    return row


def map_vehicle(db: Session, connector: Connector, provider_vehicle_ref: str, account_id):
    ref = str(provider_vehicle_ref)
    row = db.scalar(
        select(VehicleMap).where(
            VehicleMap.connector_id == connector.id,
            VehicleMap.provider_vehicle_ref == ref,
        )
    )
    if row is None:
        row = VehicleMap(
            connector_id=connector.id, provider_vehicle_ref=ref, account_id=account_id
        )
        db.add(row)
    else:
        row.account_id = account_id
    db.flush()
    return row


def _account_for(db: Session, connector: Connector, vehicle_ref: str):
    row = db.scalar(
        select(VehicleMap).where(
            VehicleMap.connector_id == connector.id,
            VehicleMap.provider_vehicle_ref == vehicle_ref,
        )
    )
    return row.account_id if row else None


def _watermark(db: Session, connector: Connector, vehicle_ref: str) -> TraceImport:
    row = db.scalar(
        select(TraceImport).where(
            TraceImport.connector_id == connector.id,
            TraceImport.provider_vehicle_ref == vehicle_ref,
        )
    )
    if row is None:
        row = TraceImport(connector_id=connector.id, provider_vehicle_ref=vehicle_ref)
        db.add(row)
        db.flush()
    return row


@dataclass
class IngestResult:
    """What a poll DID, in terms an operator can act on.

    AI-CONTEXT: `skipped_unmapped` is counted rather than logged and forgotten, because
    it is the number that explains a fleet reporting "no claims" — every truck they
    added since the mapping was made is invisible until somebody maps it. A silent skip
    would make a half-connected fleet look like a quiet one.
    """

    imported: int = 0
    duplicates: int = 0
    skipped_unmapped: int = 0
    unmapped_refs: set = field(default_factory=set)
    events: list = field(default_factory=list)


def ingest_breadcrumbs(
    db: Session, connector: Connector, crumbs: list[Breadcrumb], *, now: datetime | None = None
) -> IngestResult:
    """Feed provider breadcrumbs through F3's own evaluator. The heart of the slice.

    IDEMPOTENT BY WATERMARK. Polling overlaps by construction — the same breadcrumb
    arrives on consecutive polls as the normal case, not an edge one — and a replayed
    ping is NOT inert: it advances dwell state and can re-fire an edge. So anything at or
    before the per-vehicle watermark is dropped before `evaluate_ping` sees it.

    The watermark compares the PROVIDER's clock, never ours. Using our clock would drop
    records whenever the two disagree, and that disagreement is precisely what this
    codebase records rather than hides elsewhere (F12's `occurred_at` vs `received_at`).
    """
    result = IngestResult()
    if not crumbs:
        return result

    # grouped per vehicle so one watermark read serves a whole vehicle's window, and so a
    # lagging truck cannot hold back the others (the `_enrich` lesson: 191 queries for 263
    # pins is what per-row round-trips look like when they arrive)
    by_vehicle: dict[str, list[Breadcrumb]] = {}
    for crumb in crumbs:
        by_vehicle.setdefault(crumb.vehicle_ref, []).append(crumb)

    for vehicle_ref, vehicle_crumbs in by_vehicle.items():
        account_id = _account_for(db, connector, vehicle_ref)
        if account_id is None:
            # SKIPPED AND COUNTED, never guessed. Attributing one driver's dwell to
            # another driver's claim is the worst failure available in a module whose
            # output is an invoice.
            result.skipped_unmapped += len(vehicle_crumbs)
            result.unmapped_refs.add(vehicle_ref)
            continue

        mark = _watermark(db, connector, vehicle_ref)
        seen = mark.last_seen_at
        fresh = sorted(vehicle_crumbs, key=lambda c: c.recorded_at)
        newest = seen

        for crumb in fresh:
            if seen is not None and crumb.recorded_at <= seen:
                result.duplicates += 1
                continue
            outcome = location.evaluate_ping(
                db,
                account_id,
                crumb.lat,
                crumb.lon,
                occurred_at=crumb.recorded_at,
                speed_mps=crumb.speed_mps,
                source=f"{SOURCE_PREFIX}{connector.provider.value}",
                now=now,
            )
            result.imported += 1
            result.events.extend(list(outcome))
            newest = crumb.recorded_at if newest is None else max(newest, crumb.recorded_at)

        mark.last_seen_at = newest
        mark.pings_imported = (mark.pings_imported or 0) + result.imported

    db.flush()
    return result


def poll_connector(db: Session, connector: Connector, client=None, *, now=None) -> IngestResult:
    """One provider round trip for one fleet, with the failure recorded on the row.

    A provider refusing us (revoked key, rate limit) marks the connector `failing` and
    keeps the reason. It does NOT mark it `disabled`: that is an operator's decision, and
    collapsing the two would make a revoked key look like somebody's choice — the
    "never ran / switched off / failing" distinction §11.7 already applies to the ops
    health panel.
    """
    if client is None:
        client = MotiveClient(decrypt_key(connector.key_ciphertext))
    since = db.scalar(
        select(TraceImport.last_seen_at)
        .where(TraceImport.connector_id == connector.id)
        .order_by(TraceImport.last_seen_at.desc())
        .limit(1)
    )
    try:
        crumbs = client.vehicle_locations(since=since)
    except Exception as exc:  # noqa: BLE001 — every provider failure is the same posture
        connector.status = ConnectorStatus.failing
        connector.health_detail = str(exc)[:500]
        db.flush()
        raise

    result = ingest_breadcrumbs(db, connector, crumbs, now=now)
    # FR4: an arrival the ELD saw becomes a HELD claim. Drafting lives here rather than
    # inside `ingest_breadcrumbs` so that the ingest path stays usable on its own — the
    # step-4 probe exercises exactly that, traces without a claim path.
    draft_holds_for_events(db, connector, result.events, now=now)
    connector.status = ConnectorStatus.active
    connector.health_detail = None
    connector.last_sync_at = now or datetime.now(UTC)
    db.flush()
    return result


def active_connectors(db: Session) -> list[Connector]:
    return list(
        db.scalars(select(Connector).where(Connector.status != ConnectorStatus.disabled))
    )


# --- FR3: evidence class -----------------------------------------------------------


def evidence_class_for(sources: set[str] | list[str] | None) -> EvidenceClass:
    """What a pack may claim, derived from the ping sources that actually back it.

    AI-CONTEXT: DERIVED, never asserted by a caller. If a caller could pass the class in,
    the honest label would depend on the caller being right — and the one thing this
    module must never do is let a pack say `phone_verified` over provider timestamps. The
    input is the set of `source` values on the pings in the claim's window; the output is
    a fact about them.

    No sources at all is `phone_verified`, and that is the correct conservative default
    rather than a shrug: every pack that existed before this module was phone-based, the
    migration backfills exactly that, and a pack with no location trail says so in its own
    "position trail not available" branch rather than through this label.
    """
    values = {s for s in (sources or []) if s}
    eld = {s for s in values if s.startswith(SOURCE_PREFIX)}
    phone = values - eld
    if eld and phone:
        return EvidenceClass.mixed
    if eld:
        return EvidenceClass.eld_derived
    return EvidenceClass.phone_verified


def provider_names(sources: set[str] | list[str] | None) -> list[str]:
    """The providers a pack must NAME. §11.7: state who said what."""
    out = sorted(
        {
            s[len(SOURCE_PREFIX) :]
            for s in (sources or [])
            if s and s.startswith(SOURCE_PREFIX)
        }
    )
    return out


# --- FR4: draft, and hold ----------------------------------------------------------


def can_send(db: Session) -> tuple[bool, str | None]:
    """Whether an approved claim may actually leave the box.

    AI-CONTEXT: D13 IS THE GATE, IN CODE (owner decision, 2026-08-15). Fleet-originated
    claims invoice in the carrier's name — a different legal posture from v1.0 §13's
    driver-name billing agent — and counsel has not touched the templates. The owner chose
    to build the send path and gate it rather than leave it unwired, so that the day D13
    lands the change is `satisfy_gate(...)` and not a deploy of code first exercised in
    production.

    Reads the GATE, not a constant, for exactly that reason.
    """
    for name in GATES:
        gate = flags.get_gate(db, FLAG_KEY, name)
        # an ABSENT gate is unsatisfied, deliberately. `register_module` creates all of
        # them, so a missing row means the module was never registered on this box — and
        # treating "I could not find the precondition" as "the precondition is met" is
        # the exact shape of audit F-02.
        if gate is None or not gate.satisfied:
            return False, name
    return True, None


# --- FR4: draft from ELD dwell, and HOLD ---------------------------------------------


class NotHeld(Exception):
    """A decision was asked of a hold that has already been decided."""


def _sources_for_window(db: Session, account_id, since: datetime, until: datetime) -> set[str]:
    """Which ping sources back this claim's window — the input to the evidence class.

    AI-CONTEXT: read from the PINGS rather than from what drafted the claim. A stop the
    ELD saw and the driver also photographed is `mixed`, and the only way to know that is
    to look at what is actually there.

    THE WINDOW MUST START AT THE ARRIVAL, and getting that wrong is not a cosmetic bug.
    The first version anchored on `claim.clock_since`, which is NULL at draft time — so
    the window began at `now`, found no pings at all, and `evidence_class_for([])`
    returned its conservative default. The result was an ELD-only claim labelled
    **`phone_verified`**: a pack that would have told a broker a driver's device produced
    readings a telematics API produced. Caught by the test, not by reading it.
    """
    return location.ping_sources(db, account_id, since, until)


def draft_holds_for_events(db: Session, connector: Connector, events, *, now=None) -> list:
    """Turn ELD-derived arrivals into HELD M3 claims. The FR4 path, and nothing more.

    AI-CONTEXT: THE CLAIM IS AN ORDINARY M3 CLAIM. `m03.start_claim` is get-or-create and
    is the same call the driver-app path makes; the pipeline, templates and ledger that
    follow are M3's, untouched. What M14 adds is a row saying no human has approved it.

    HOLD-ALL IS THE RULES ENGINE FOR THIS SLICE and the fleet admin is the rule. There is
    deliberately no threshold, no timer and no auto-send: FR5's engine is PROPOSED, and
    inventing one here is the "drift" the kickoff forbids by name.

    Only ENTER matters for drafting. A DWELL_TICK on an already-drafted stop must not
    queue a second claim, and `uq_held_claim_claim` makes that a database fact rather
    than a loop invariant — a fleet admin shown one detention twice approves it twice.
    """
    now = now or datetime.now(UTC)
    drafted = []
    seen: set = set()

    for event in events:
        account_id = getattr(event, "account_id", None)
        facility_id = getattr(event, "facility_id", None)
        if account_id is None or facility_id is None:
            continue
        key = (account_id, facility_id)
        if key in seen:
            continue
        seen.add(key)

        # the stop this arrival belongs to, through F5's own accessor — M14 does not
        # reimplement "which stop is live", and a stop at a DIFFERENT facility is not
        # this event's stop
        stop = loads.active_stop_for_account(db, account_id)
        if stop is None or stop.facility_id != facility_id:
            continue

        # AI-CONTEXT: `started_at` is the ARRIVAL, not the moment the poller ran.
        # `start_claim` defaults `clock_since` to `datetime.now()`, and a claim drafted
        # from a three-hour-old breadcrumb would otherwise record the detention clock as
        # starting when we happened to poll — understating the driver's own detention and,
        # because the evidence window is anchored on it, finding no pings and labelling an
        # ELD-only pack `phone_verified`. Both were real; the second is the one that would
        # have put a false custody claim in front of a broker.
        arrived_at = getattr(event, "occurred_at", None) or now
        claim = m3.start_claim(
            db, stop, trigger=m3.DetentionTrigger.arrival, started_at=arrived_at
        )
        state = m3.clock(db, claim, now)
        # nothing is drafted until the meter is actually running. Within free time there
        # is no money owed, and a claim queued for a stop that never ran long would put a
        # $0 invoice in front of a fleet admin.
        if state.phase is m3.DetentionPhase.within_free_time:
            continue

        existing = db.scalar(select(HeldClaim).where(HeldClaim.claim_ref == claim.id))
        if existing is not None:
            continue

        held = HeldClaim(
            fleet_id=connector.fleet_id,
            claim_ref=claim.id,
            stop_ref=stop.id,
            account_id=account_id,
            # anchored on the ARRIVAL this event represents — see `_sources_for_window`
            evidence_class=evidence_class_for(
                _sources_for_window(db, account_id, arrived_at, now)
            ).value,
        )
        db.add(held)
        drafted.append(held)
    db.flush()
    return drafted


def held_claims(db: Session, fleet_id, state: HoldState = HoldState.held) -> list[HeldClaim]:
    return list(
        db.scalars(
            select(HeldClaim)
            .where(HeldClaim.fleet_id == fleet_id, HeldClaim.state == state)
            .order_by(HeldClaim.created_at)
        )
    )


def approve(db: Session, held: HeldClaim, account_id, gateway=None, *, now=None) -> HeldClaim:
    """A fleet admin says yes. Whether it LEAVES is a separate question, deliberately.

    AI-CONTEXT: the approval is recorded UNCONDITIONALLY and the send is gated — the
    owner's decision (2026-08-15), taken over leaving the send path unwired, so that the
    day D13 lands the change is `satisfy_gate(...)` rather than a deploy of code first
    exercised in production.

    The two facts are kept apart because collapsing them is F-01 exactly: F8 wrote
    `sent_at` for notices that reached a container on the VM and everything downstream
    believed them. An approved-but-blocked claim says `approved` with `send_blocked_by`
    naming the gate, and the screen can therefore say WHY rather than going quiet.
    """
    if held.state is not HoldState.held:
        raise NotHeld(f"hold {held.id} is {held.state.value}")
    now = now or datetime.now(UTC)

    held.state = HoldState.approved
    held.decided_by = account_id
    held.decided_at = now

    allowed, blocker = can_send(db)
    if not allowed:
        held.send_blocked_by = blocker
        db.flush()
        return held

    # M3's own filing and send. Reached through `public` only.
    claim = m3.get_claim(db, held.claim_ref)
    if claim is not None:
        m3.generate_pack(db, claim, now, gateway=gateway)
        m3.send_detention_start_notice(db, claim, gateway, now)
    held.state = HoldState.sent
    held.send_blocked_by = None
    db.flush()
    return held


def reject(db: Session, held: HeldClaim, account_id, *, now=None) -> HeldClaim:
    """A fleet admin says no, and the claim stays exactly where it is.

    Rejecting the HOLD does not touch the M3 claim: the detention happened, the clock ran
    and the receivable question is the driver's own. What this records is that the fleet
    is not invoicing for it in the carrier's name.
    """
    if held.state is not HoldState.held:
        raise NotHeld(f"hold {held.id} is {held.state.value}")
    held.state = HoldState.rejected
    held.decided_by = account_id
    held.decided_at = now or datetime.now(UTC)
    db.flush()
    return held
