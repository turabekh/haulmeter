"""AI-CONTEXT: M5 Protection & Document Wallet (PRD §8.5) — the shield to M3/M4's
sword. The same evidence engine pointed at protecting the driver: on-time proof
before anyone accuses them of being late, cargo condition before/after every
load, credentials one tap away and never silently expired. Composes foundation
publics only (F4 evidence, F5 stop, F6 documents, F8 notices); M5 owns its own
F4 logs so it never writes F5's tables. Runs behind the F13 flag m05_protection.
This is the App Store narrative for background location: continuous, visible
benefit.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility
from app.foundation.f04_evidence import public as evidence
from app.foundation.f05_load import public as loads
from app.foundation.f06_documents import public as documents
from app.foundation.f08_notifications import public as notify

from .enums import CONDITION_SEQUENCE, INSPECTION_DOC_TYPES, CapturePhase, StopPacketState
from .models import ConditionCapture, Incident, OnTimeConsent, OnTimeProof, StopPacket

FLAG_KEY = "m05_protection"
MODULE = "m05"
DEFAULT_PHOTO_CONTENT_TYPE = "image/jpeg"


def _persist_photo_bytes(
    log_id, content: bytes, content_type: str | None
) -> tuple[str, str] | None:
    # store the captured image bytes in F6 object storage (MinIO in dev) so the
    # Evidence view can serve a real thumbnail. Returns (storage_key, content_type)
    # or None if the store fails — capture never blocks on storage (the hash and
    # chain still record; the image is simply unavailable to serve).
    content_type = content_type or DEFAULT_PHOTO_CONTENT_TYPE
    key = f"evidence/{log_id}/{uuid.uuid4()}"
    try:
        documents.default_storage().put(key, content, content_type)
    except Exception:
        return None
    return key, content_type


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags
    from app.foundation.f14_admin import public as admin

    flags.register_flag(db, FLAG_KEY, description="M5 Protection & Document Wallet")
    admin.register_admin_view(db, "m05.protection", MODULE, "Protection", "/admin/m05/protection")


# --- On-time arrival proof (M5-FR1) ---
def file_on_time_proof(
    db: Session,
    stop,
    account_id,
    checked_in_at: datetime,
    notify_counterparty: bool = False,
    counterparty_ref=None,
    counterparty_email: str | None = None,
    gateway=None,
) -> OnTimeProof:
    deadline = stop.appointment_end or stop.appointment_start
    within = deadline is None or _as_utc(checked_in_at) <= _as_utc(deadline)

    log = evidence.create_log(db, account_id, stop_ref=stop.id, label="on-time-proof")
    evidence.append_record(
        db,
        log,
        evidence.RecordType.SYSTEM,
        {"event": "on_time_check", "within_window": within},
        occurred_at=checked_in_at,
    )

    notice_sent = False
    if notify_counterparty and within and gateway is not None:
        hhmm = _as_utc(checked_in_at).strftime("%H:%M")
        thread = notify.create_thread(
            db, account_id, subject="On-time arrival", counterparty_ref=counterparty_ref
        )
        notify.send_counterparty_message(
            db,
            thread,
            f"Driver checked in on time at {hhmm} per the appointment.",
            gateway,
            counterparty_email or "counterparty@unknown",
            now=checked_in_at,
        )
        notice_sent = True

    proof = OnTimeProof(
        account_id=account_id,
        stop_ref=stop.id,
        checked_in_at=checked_in_at,
        within_window=within,
        notice_sent=notice_sent,
        evidence_log_ref=log.id,
    )
    db.add(proof)
    db.flush()
    return proof


# --- Cargo-condition protocol (M5-FR2) ---
def condition_sequence() -> list[str]:
    return list(CONDITION_SEQUENCE)


def start_condition_capture(db: Session, stop, account_id, phase: CapturePhase) -> ConditionCapture:
    log = evidence.create_log(db, account_id, stop_ref=stop.id, label=f"condition-{phase.value}")
    capture = ConditionCapture(
        account_id=account_id, stop_ref=stop.id, phase=phase, evidence_log_ref=log.id
    )
    db.add(capture)
    db.flush()
    return capture


def condition_photo_count(db: Session, stop_ref) -> int:
    # total cargo-condition photos captured for a stop (across capture sessions) —
    # so the Load tab can confirm "Photos captured" instead of a static label
    total = db.scalar(
        select(func.coalesce(func.sum(ConditionCapture.photo_count), 0)).where(
            ConditionCapture.stop_ref == stop_ref
        )
    )
    return int(total or 0)


def add_condition_photo(
    db: Session,
    capture: ConditionCapture,
    prompt: str,
    content: bytes | None = None,
    content_hash: str | None = None,
    exif: dict | None = None,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    captured_at: datetime | None = None,
    content_type: str | None = None,
):
    log = db.get(evidence.EvidenceLog, capture.evidence_log_ref)
    meta = {**(exif or {}), "prompt": prompt}
    storage_key = None
    if content is not None:
        stored = _persist_photo_bytes(log.id, content, content_type)
        if stored is not None:
            storage_key, meta["content_type"] = stored
    artifact = evidence.attach_artifact(
        db,
        log,
        evidence.ArtifactType.photo,
        content=content,
        content_hash=content_hash,
        exif=meta,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        captured_at=captured_at,
        storage_key=storage_key,
    )
    capture.photo_count += 1
    db.flush()
    return artifact


# --- Document wallet + expiry (M5-FR3) ---
# AI-CONTEXT: paperwork a LOAD produces, as opposed to a credential the DRIVER holds
# (§23 entry 79). The wallet returned every document on the account and grouped them by
# type, so a driver's CDL sat between rate cons: measured on a real account, 40
# documents of which 5 were theirs. `documents_for_account` filters by account and
# ignores `subject_kind` entirely, while its own docstring says the wallet's job is "to
# produce the credential a driver holds now".
#
# Grouping by TYPE is right for a credential and wrong for paperwork: a BOL matters
# because of which load it belongs to, not because it is a BOL.
LOAD_DOC_TYPES = {
    documents.DocType.rate_con,
    documents.DocType.bol,
    documents.DocType.pod,
    documents.DocType.lumper_receipt,
}


def _paperwork_row(doc) -> dict:
    return {
        "id": str(doc.id),
        "doc_type": doc.doc_type.value,
        "uploaded_at": doc.uploaded_at.isoformat(),
        "content_type": doc.content_type,
    }


def _load_paperwork(db: Session, stop_docs: list) -> list[dict]:
    """Load paperwork, grouped by the load it belongs to and named by its route."""
    by_load: dict = {}
    for doc in stop_docs:
        stop = loads.get_stop(db, doc.subject_ref)
        if stop is None:
            continue
        load = loads.get_load(db, stop.load_id)
        if load is None:
            continue
        group = by_load.setdefault(
            load.id,
            {"load": load, "stop_id": str(stop.id), "docs": []},
        )
        group["docs"].append(doc)
    rows = []
    for group in by_load.values():
        load = group["load"]
        stops = loads.list_stops(db, load)
        origin = facility.get_facility(db, stops[0].facility_id) if stops else None
        destination = (
            facility.get_facility(db, stops[-1].facility_id) if len(stops) > 1 else None
        )
        rows.append(
            {
                "load_id": str(load.id),
                "stop_id": group["stop_id"],
                "reference_number": load.reference_number,
                "created_at": load.created_at.isoformat(),
                "facility_name": origin.name if origin else None,
                "destination_name": destination.name if destination else None,
                # DISTINCT types: a two-stop load has a BOL at each dock, and a row
                # reading "BOL · BOL" says less than "BOL" does. The documents
                # themselves are listed per stop on the load's evidence screen, which
                # is where they mean something.
                "doc_types": sorted({d.doc_type.value for d in group["docs"]}),
                "document_count": len(group["docs"]),
            }
        )
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows


def wallet(db: Session, account_id, as_of: date | None = None) -> dict:
    as_of = as_of or datetime.now(UTC).date()
    docs, expiring = [], []
    stop_docs, unattached = [], []
    for doc in documents.documents_for_account(db, account_id):
        if doc.subject_kind == "stop" and doc.subject_ref is not None:
            stop_docs.append(doc)
            continue
        if doc.doc_type in LOAD_DOC_TYPES:
            # photographed, parsed, and never turned into a load. Indistinguishable
            # from a real document until it is said plainly, and 10 of them on the
            # account that reported this.
            unattached.append(doc)
            continue
        status = "ok"
        if doc.expires_on is not None:
            if doc.expires_on < as_of:
                status = "expired"
            elif documents.active_reminder_offset(doc.expires_on, as_of) is not None:
                status = "expiring"
        row = {
            "id": str(doc.id),
            "doc_type": doc.doc_type.value,
            "expires_on": doc.expires_on.isoformat() if doc.expires_on else None,
            "status": status,
            # AI-CONTEXT: how to RENDER it (§23 entry 80). The viewer has always
            # carried a PDF branch — its own header comment says "some credentials are
            # filed as PDFs, which an <img> cannot render" — and keyed it off a
            # `content_type` the wallet has never sent. So the branch could not
            # execute, and every PDF opened as a broken image with its label as alt
            # text. A capability with nothing reaching it.
            "content_type": doc.content_type,
        }
        docs.append(row)
        if status in ("expiring", "expired"):
            expiring.append(row)
    # the count travels with the wallet so the archive control can state how many are
    # in there without a second request — a driver on a fuel-desk connection should
    # not pay a round trip to learn whether it is worth opening
    return {
        "documents": docs,
        "expiring": expiring,
        "archived_count": archived_count(db, account_id),
        "load_paperwork": _load_paperwork(db, stop_docs),
        "unattached": sorted(
            (_paperwork_row(d) for d in unattached),
            key=lambda r: r["uploaded_at"],
            reverse=True,
        ),
    }


def inspection_mode(db: Session, account_id, as_of: date | None = None) -> list[dict]:
    return [
        d
        for d in wallet(db, account_id, as_of)["documents"]
        if d["doc_type"] in INSPECTION_DOC_TYPES
    ]


# --- Incident capture (M5-FR4) ---
def capture_incident(
    db: Session, account_id, kind: str, note: str | None = None, load_ref=None
) -> Incident:
    log = evidence.create_log(db, account_id, label=f"incident-{kind}")
    incident = Incident(
        account_id=account_id, load_ref=load_ref, kind=kind, note=note, evidence_log_ref=log.id
    )
    db.add(incident)
    db.flush()
    return incident


def add_incident_photo(
    db: Session,
    incident: Incident,
    content: bytes,
    captured_at=None,
    content_type: str | None = None,
):
    log = db.get(evidence.EvidenceLog, incident.evidence_log_ref)
    meta: dict = {}
    storage_key = None
    stored = _persist_photo_bytes(log.id, content, content_type)
    if stored is not None:
        storage_key, meta["content_type"] = stored
    return evidence.attach_artifact(
        db,
        log,
        evidence.ArtifactType.photo,
        content=content,
        captured_at=captured_at,
        exif=meta,
        storage_key=storage_key,
    )


def incident_pack(db: Session, incident: Incident):
    log = db.get(evidence.EvidenceLog, incident.evidence_log_ref)
    # an accident, a damage discovery or a dispute is not a cargo condition report,
    # and the template decides the title a clerk reads first
    return evidence.compose_pack(db, log, evidence.PackTemplate.incident)


def has_bol(db: Session, stop_ref) -> bool:
    """§10.2's checklist opens with "BOL ✓". The row rendered an unconditional tick,
    so it said yes before anyone had photographed anything — and a checklist that
    always says yes is decoration. This answers it honestly, which for most stops
    today means NO, which is the point: FR5 exists to make a gap visible while the
    driver is still standing where it can be closed."""
    return bool(
        documents.documents_for_subject(db, "stop", stop_ref, doc_type=documents.DocType.bol)
    )


# --- Protection summary per stop (M5-FR5) ---
def protection_summary(db: Session, stop) -> dict:
    on_time = db.scalar(select(OnTimeProof).where(OnTimeProof.stop_ref == stop.id)) is not None
    captures = list(
        db.scalars(select(ConditionCapture).where(ConditionCapture.stop_ref == stop.id))
    )
    pickup = any(c.phase == CapturePhase.pickup and c.photo_count > 0 for c in captures)
    delivery = any(c.phase == CapturePhase.delivery and c.photo_count > 0 for c in captures)
    documented = {
        "on_time_proof": on_time,
        "pickup_photos": pickup,
        "delivery_photos": delivery,
        "bol": has_bol(db, stop.id),
    }
    missing = [k for k, ok in documented.items() if not ok]
    return {"documented": documented, "missing": missing}


# AI-CONTEXT: M5-FR5's EXIT carve-out — "nudges before gaps become risks", at the one
# moment the gap stops being fixable.
#
# Not everything missing is urgent, and the difference is whether LEAVING closes the
# door on it. A trailer photograph and a signed BOL can only be taken at that dock:
# once the driver is on the highway the evidence does not exist and never will. On-time
# proof is different — F5 files it from the arrival record at `/arrive`, so it is
# either already there or was never going to be, and driving away changes nothing
# about it. Warning about the second kind at EXIT would be a nag, which is exactly what
# §13.1's budget exists to prevent.
IRRECOVERABLE_ON_EXIT = ("bol", "pickup_photos", "delivery_photos")


def on_time_proof_for_stop(db: Session, stop_ref) -> OnTimeProof | None:
    """The filed arrival proof, or None before the driver has arrived.

    AI-CONTEXT: `within_window` has been computed and stored on EVERY arrival since
    FR1 shipped — in or out of the window, opted in or not — and reached no screen.
    The only place the API ever exposed it was the `/arrive` response, which the Load
    tab discards, so after a reload the verdict was unrecoverable from the app. A
    proof the driver cannot see is one they will not think to produce.
    """
    return db.scalar(select(OnTimeProof).where(OnTimeProof.stop_ref == stop_ref))


def irrecoverable_gaps(db: Session, stop) -> list[str]:
    """What this stop can no longer be documented for, now that the driver has left."""
    missing = protection_summary(db, stop)["missing"]
    return [k for k in IRRECOVERABLE_ON_EXIT if k in missing]


def notify_protection_gap(
    db: Session,
    stop,
    account_id,
    gateway,
    now: datetime | None = None,
    driver_state=None,
    facility_name: str | None = None,
):
    """Fire the EXIT deadline, or return None when there is nothing unrecoverable.

    §23 entry 56 settles the class: P1, exempt from §13.1's 2/day budget because a
    deadline must not lose to two softer nudges already spent, capped at one a day,
    and still silent in quiet hours and while RESTING. The driver is almost certainly
    DRIVING when this fires — they have just pulled off the dock — so it carries no
    interactive prompt (Forbidden #11); F8 renders it as an audio line plus a tray
    entry, and the deep link is what they act on when they stop.
    """
    gaps = irrecoverable_gaps(db, stop)
    if not gaps:
        return None
    now = now or datetime.now(UTC)
    where = f" {facility_name}" if facility_name else " the facility"
    # §12.2: lead with the fact, name the consequence, one action. Never scold — the
    # driver did not forget on purpose, and most of the time they were rushed off.
    labels = ", ".join(_GAP_LABELS.get(g, g) for g in gaps)
    return notify.dispatch(
        db,
        account_id,
        notify.NotificationTier.P1,
        notify.PROTECTION_GAP_CLASS,
        f"Missing: {labels}",
        f"You've left{where}. This can't be captured there now — check the record.",
        f"/load/{stop.id}/evidence",
        gateway,
        now=now,
        driver_state=driver_state or notify.DriverState.driving,
        subject_ref=str(stop.id),
    )


_GAP_LABELS = {
    "bol": "BOL",
    "pickup_photos": "pickup photos",
    "delivery_photos": "delivery photos",
}


# --- FR2/FR4 export + share (design-prd §17) ---
def stop_pack(db: Session, stop_ref):
    """Everything recorded at one stop, as one document (§23 entry 71).

    The Evidence surface is a STOP's record — timeline, documents, photos — and its
    only export rendered the cargo-condition capture alone, which 404'd for any stop
    without photos. So the pack that argues a detention claim, the product's whole
    reason for existing, had no way out of the phone."""
    return evidence.compose_stop_pack(db, stop_ref, evidence.PackTemplate.stop_record)


def load_pack(db: Session, load_ref):
    """Everything recorded across a LOAD, as one document (§23 entry 78).

    AI-CONTEXT: the reachability half of the same defect. A driver who ran a pickup
    and a delivery and photographed both ends had eight photos in the system, four in
    each stop's log, and every export produced one stop's four — whichever stop the
    row they tapped happened to point at. The other four were hash-verified, intact,
    and unreachable from any screen.

    Each section is labelled with the stop's place in the route and its facility,
    because a broker looking at eight photos needs to know which dock each came from.
    """
    load = loads.get_load(db, load_ref)
    if load is None:
        return None
    groups = []
    for stop in loads.list_stops(db, load):
        fac = facility.get_facility(db, stop.facility_id)
        name = fac.name if fac is not None else "Unknown facility"
        groups.append((f"{stop.sequence + 1} · {stop.stop_type.value.title()} · {name}", stop.id))
    if not groups:
        return None
    return evidence.compose_grouped_pack(
        db, groups, evidence.PackTemplate.load_record, label=load.reference_number
    )


def condition_pack(db: Session, stop_ref, phase: CapturePhase | None = None):
    """FR2's "one-tap condition report". A stop's condition captures share one
    subject, so the export is per-STOP rather than per-capture session: a clerk
    asking "what did the trailer look like" wants pickup and delivery in one
    document, not two files to reconcile."""
    captures = list(
        db.scalars(
            select(ConditionCapture)
            .where(ConditionCapture.stop_ref == stop_ref)
            .order_by(ConditionCapture.created_at)
        )
    )
    if phase is not None:
        captures = [c for c in captures if c.phase == phase]
    if not captures:
        return None
    # one log per capture session; the newest carries the fullest picture of the
    # phase being exported, and every photo in it is chained to the same head
    log = db.get(evidence.EvidenceLog, captures[-1].evidence_log_ref)
    return evidence.compose_pack(db, log, evidence.PackTemplate.cargo_condition)


def _pack_images(db: Session, pack) -> dict:
    """Thumbnail bytes for the renderer, fetched HERE rather than inside F4 — the
    evidence engine does not reach into object storage mid-render, so a storage miss
    degrades to a labelled placeholder instead of taking the document down."""
    images = {}
    storage = documents.default_storage()
    for artifact in pack.artifacts:
        key = artifact.get("storage_key")
        if not key:
            continue
        try:
            images[artifact["content_hash"]] = storage.get(key)
        except Exception:
            continue
    return images


def render_pack(db: Session, pack, context=None):
    context = context or evidence.PackContext()
    if not context.images:
        context.images = _pack_images(db, pack)
    return evidence.render_pack_pdf(pack, context)


def share_pack(db: Session, log_ref, pack, account_id, recipient=None, now=None, context=None):
    """Render, pin, and hand back the record. The share is the moment the document
    stops being a view of the chain and becomes a thing that was SENT."""
    log = db.get(evidence.EvidenceLog, log_ref)
    content = render_pack(db, pack, context)
    return evidence.share_pack(
        db, log, pack.template, content, account_id, recipient=recipient, now=now
    )


# --- A1: draft on EXIT, send when the DRIVER says so (v2.0 §3 A1 req 3 and 5) ---
def draft_stop_packet_on_exit(db: Session, account_id, facility_id, now: datetime):
    """AI-CONTEXT: A1 requirement 5 is the whole design of this function.

    "The driver reviews before it sends. Nothing leaves silently. A packet the driver
    did not see is a document they cannot vouch for."

    The obvious build — EXIT fires, packet sends — is the one A1 forbids, and the rest
    of the product agrees with it: M3-FR6 has the driver approve before send, M11-FR3's
    ghostwriter does, M5-FR1 is per-load opt-in. A document going to a broker under a
    driver's name, describing a stop they have not looked at, is the one thing none of
    those would allow.

    So this DRAFTS and returns. Sending is `send_drafted_packet`, and the gap between
    them is a person.

    Scoped to `shipper_receiver` because that is where paperwork happens. A draft per
    fuel stop would train a driver to dismiss the queue, and a review step that is
    always dismissed is a rubber stamp with extra taps.
    """
    fac = facility.get_facility(db, facility_id)
    if fac is None or fac.facility_type is not facility.FacilityType.shipper_receiver:
        return None
    # the driver's current ARMED stop, and it must be the one they just left. F3 only
    # emits events for armed facilities, so an EXIT elsewhere is not this driver's dock.
    stop = loads.active_stop_for_account(db, account_id)
    if stop is None or stop.facility_id != facility_id:
        return None
    existing = db.scalar(select(StopPacket).where(StopPacket.stop_ref == stop.id))
    if existing is not None:
        # geofences bounce; one stop is one document
        return existing
    load = loads.get_load(db, stop.load_id)
    packet = StopPacket(
        account_id=account_id,
        stop_ref=stop.id,
        counterparty_ref=getattr(load, "counterparty_id", None),
        state=StopPacketState.draft,
        drafted_at=now,
    )
    db.add(packet)
    db.flush()
    return packet


def send_drafted_packet(db: Session, packet, gateway, now=None, base_url_required: bool = True):
    """The driver's act. Idempotent: a retried tap must not put a second document in a
    dispatcher's inbox."""
    if packet.state is StopPacketState.sent:
        return packet
    result = send_stop_packet(
        db,
        packet.account_id,
        stop_ref=packet.stop_ref,
        counterparty_ref=packet.counterparty_ref,
        gateway=gateway,
        now=now,
        base_url_required=base_url_required,
    )
    packet.state = StopPacketState.sent
    packet.sent_at = now or datetime.now(UTC)
    packet.shared_pack_ref = result["shared"].id
    db.flush()
    return packet


# --- A1: the Stop Packet, a routine handoff (v2.0 §3 A1) ---
def send_stop_packet(
    db: Session,
    account_id,
    stop_ref,
    counterparty_ref,
    gateway,
    now: datetime | None = None,
    recipient: str | None = None,
    base_url_required: bool = True,
):
    """AI-CONTEXT: A1 — the paperwork a driver photographs after loading, sent for them.

    Composed from two things that already worked and had never been put together: M5's
    on-time notice (a counterparty message that opens NO receivable) and the pack link
    M3 gained an hour ago. What A1 adds is the document.

    WHAT THIS DELIBERATELY DOES NOT DO, and it is most of the requirement. The only
    existing path from a pack to a counterparty is M3's `open_receivable`, which also:

      · opens a RECEIVABLE in F7 — money the driver is claiming, and
      · calls `record_claim` on the counterparty, incrementing the claim history that
        feeds M8 pricing and M12 analytics.

    A1 says the Stop Packet is "explicitly not a claim and not a dispute". A broker whose
    claim count rose because a driver sent their paperwork would be a quiet, compounding
    lie about that broker — and PRD §15 names driver fear of blacklisting as a top risk,
    which is precisely the fear a spurious claim record would justify. Neither is called
    here, and the tests assert the absences as hard as the presence.
    """
    now = now or datetime.now(UTC)
    stop = loads.get_stop(db, stop_ref)
    load = loads.get_load(db, stop.load_id) if stop is not None else None

    log = evidence.create_log(db, account_id, stop_ref=stop_ref, label="stop-packet")
    evidence.append_record(
        db,
        log,
        evidence.RecordType.SYSTEM,
        {"event": "stop_packet", "stop_ref": str(stop_ref)},
        occurred_at=now,
    )
    evidence.anchor_chain(db, log)
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.stop_record)
    shared = evidence.share_pack(
        db, log, pack.template, render_pack(db, pack), account_id, recipient=recipient, now=now
    )

    # A1 requirement 4: the reference an accounts-payable clerk files by, in the SUBJECT,
    # so they never have to open it to know what it belongs to.
    reference = getattr(load, "reference_number", None) if load is not None else None
    subject = f"Stop paperwork · {reference}" if reference else "Stop paperwork"

    link = evidence.share_link(shared)
    if link is None and base_url_required:
        raise ValueError("PUBLIC_BASE_URL is unset; a packet with no link reaches nobody")
    where = (
        f"The stop paperwork is here: {link}"
        if link
        else "The stop paperwork is available on request."
    )
    cp = loads.get_counterparty(db, counterparty_ref) if counterparty_ref is not None else None
    to_ref = recipient or (cp.contact_email if cp is not None else None) or "counterparty@unknown"
    thread = notify.create_thread(
        db, account_id, subject=subject, counterparty_ref=counterparty_ref
    )
    notify.send_counterparty_message(db, thread, where, gateway, to_ref, now=now)
    return {"pack": pack, "shared": shared, "thread": thread}


# --- FR1: the per-load opt-in and the automatic filing ---
def set_on_time_consent(
    db: Session, account_id, load_ref, enabled: bool, counterparty_email: str | None = None
) -> OnTimeConsent:
    consent = db.scalar(select(OnTimeConsent).where(OnTimeConsent.load_ref == load_ref))
    if consent is None:
        consent = OnTimeConsent(account_id=account_id, load_ref=load_ref)
        db.add(consent)
    consent.enabled = enabled
    if counterparty_email is not None:
        consent.counterparty_email = counterparty_email
    db.flush()
    return consent


def on_time_consent(db: Session, load_ref) -> OnTimeConsent | None:
    return db.scalar(select(OnTimeConsent).where(OnTimeConsent.load_ref == load_ref))


def auto_file_on_arrival(db: Session, stop, account_id, arrived_at=None, gateway=None):
    """PRD §8.5 FR1: geofence ENTER inside the appointment window auto-fires the
    notice and files the proof. Runs on M3's existing arming — no new geofence
    machinery, because the arrival that starts the detention clock IS the arrival
    that proves you were on time.

    Two rules the wording of the FR implies and this makes explicit:

    · **The proof is filed on every arrival**, in or out of the window and opted in
      or not. It is the driver's own protection; someone who declined to notify the
      broker still wants to be able to prove when they got there.
    · **A late arrival notifies nobody.** The only notice this FR can send says the
      driver was on time, and sending that when they were not is the single thing it
      must never do. Silence is the honest outcome, and the artifact still exists.
    """
    arrived_at = arrived_at or datetime.now(UTC)
    existing = db.scalar(select(OnTimeProof).where(OnTimeProof.stop_ref == stop.id))
    if existing is not None:
        return existing  # one proof per stop; a re-arm is not a second arrival

    consent = on_time_consent(db, stop.load_id)
    wants_notice = bool(consent and consent.enabled)
    return file_on_time_proof(
        db,
        stop,
        account_id,
        checked_in_at=arrived_at,
        notify_counterparty=wants_notice,
        counterparty_email=consent.counterparty_email if consent else None,
        gateway=gateway if wants_notice else None,
    )


# --- FR3: the driver's own documents, in and out ---
# Which types a DRIVER files themselves. The rest of F6's vocabulary belongs to
# flows that create documents as a side effect — a lumper receipt comes from M4's
# claim, a settlement from M9 — and offering them here would invite a driver to file
# a receipt in the wrong place.
DRIVER_DOC_TYPES = ["cdl", "med_card", "insurance", "permit", "rate_con", "bol", "pod", "other"]
# the credentials an expiry date is meaningful for. A BOL does not expire.
EXPIRING_DOC_TYPES = ["cdl", "med_card", "insurance", "permit"]
# AI-CONTEXT: types a driver holds exactly ONE of at a time, so filing a new one
# replaces the old rather than sitting beside it.
#
# `permit` is deliberately NOT here even though it expires. A driver carries several
# at once — IFTA, oversize, a state permit — and we do not collect anything that
# distinguishes them, so superseding on type alone would archive the wrong one. Two
# permits in the wallet is correct; two CDLs is a question about which is current,
# asked at a roadside inspection, which is the worst moment to be asking it.
SUPERSEDING_DOC_TYPES = ["cdl", "med_card", "insurance"]


def superseded_by_capturing(db: Session, account_id, doc_type: str):
    """What filing this type would archive — asked BEFORE the capture, so the driver
    is told what is about to happen rather than informed after it has."""
    if doc_type not in SUPERSEDING_DOC_TYPES:
        return None
    existing = documents.documents_for_account(db, account_id, doc_type=documents.DocType(doc_type))
    return existing[0] if existing else None


def capture_document(
    db: Session,
    account_id,
    doc_type: str,
    content: bytes,
    filename: str | None = None,
    content_type: str | None = None,
    expires_on: date | None = None,
    stop_ref=None,
):
    """AI-CONTEXT: the wallet's missing WRITER.

    The Docs tab has always been a reader: `/protection/wallet` and
    `/protection/inspection` are both GETs, and no driver-facing endpoint has ever
    created a document. A cook could upload a business licence through the vendor
    portal; a driver could not upload their own CDL. That is why the tab was empty,
    and why the expiry engine had nothing to warn about — F6 counts down from
    `expires_on`, and nothing a driver did could ever set one.
    """
    if doc_type not in DRIVER_DOC_TYPES:
        raise ValueError(doc_type)
    previous = superseded_by_capturing(db, account_id, doc_type)
    document = documents.store_document(
        db,
        account_id,
        documents.DocType(doc_type),
        content,
        filename=filename,
        content_type=content_type or "image/jpeg",
        expires_on=expires_on,
        # scoped to the stop when one is in play (a BOL belongs to a delivery), and
        # to the account when it is a credential the driver carries everywhere
        subject_kind="stop" if stop_ref is not None else "account",
        subject_ref=stop_ref if stop_ref is not None else account_id,
    )
    if previous is not None:
        # archived, never deleted (§17 Q16): the old card is still the answer to
        # "what were you carrying at that inspection in March"
        documents.supersede_document(db, previous, document)
    return document


class RestoreBlocked(Exception):
    """A restore that would put two current credentials of one type in front of an
    officer. Carries the document already holding the slot so the refusal can name it
    rather than saying no without saying why."""

    def __init__(self, blocker):
        self.blocker = blocker
        super().__init__(str(blocker.id))


def _own_document(db: Session, account_id, document_id):
    doc = db.get(documents.Document, document_id)
    if doc is None or doc.account_id != account_id:
        # a stranger's id must be indistinguishable from a missing one, exactly as the
        # viewer route already treats it — otherwise ids can be probed for existence
        return None
    return doc


def restore_blocked_by(db: Session, doc):
    """What stands in the way of restoring this document, or None.

    Only the one-at-a-time credentials can be blocked, and the reason is the same one
    that makes them supersede in the first place: two live CDLs is a question about
    which is current, asked at a roadside inspection. A driver who removed the new
    card by mistake restores it, and the old one is then free to come back too.

    Permits never block. A driver legitimately carries several at once, which is why
    they do not supersede either — the two rules are the same rule.
    """
    if doc.doc_type.value not in SUPERSEDING_DOC_TYPES:
        return None
    live = documents.documents_for_account(db, doc.account_id, doc_type=doc.doc_type)
    return live[0] if live else None


def archive_own_document(db: Session, account_id, document_id, now=None):
    """The driver's own removal — what "delete" means in a product that may not delete.

    It leaves the wallet, leaves inspection mode and stops the expiry ladder, and it
    is recoverable, which is what makes offering it honest. The bytes are untouched:
    §17 Q16 forbids hard delete, and a CDL removed today is still the answer to what
    the driver was carrying at an inspection last March.
    """
    doc = _own_document(db, account_id, document_id)
    if doc is None:
        return None
    return documents.archive_document(db, doc, documents.ARCHIVE_REMOVED, now=now)


def restore_own_document(db: Session, account_id, document_id):
    doc = _own_document(db, account_id, document_id)
    if doc is None:
        return None
    blocker = restore_blocked_by(db, doc) if doc.archived_at is not None else None
    if blocker is not None:
        raise RestoreBlocked(blocker)
    return documents.restore_document(db, doc)


def archived_count(db: Session, account_id) -> int:
    return len(
        [
            d
            for d in documents.documents_for_account(db, account_id, include_archived=True)
            if d.archived_at is not None
        ]
    )


def archived_documents(db: Session, account_id) -> list[dict]:
    """The wallet's other half, which has existed in the database since 0049 and has
    never been reachable: `documents_for_account` has taken `include_archived` from
    the day it was written and no route ever passed it.

    Every row says WHY it is here, because "replaced by the CDL you filed on 26 Jul"
    and "you removed this" are different facts and lead to different decisions. And
    every row says whether restoring it will actually work — a Restore control that
    exists only to fail is the dead-control pattern this surface has already been
    caught by twice.
    """
    rows = []
    for doc in documents.documents_for_account(db, account_id, include_archived=True):
        if doc.archived_at is None:
            continue
        replacement = (
            db.get(documents.Document, doc.superseded_by_id)
            if doc.superseded_by_id is not None
            else None
        )
        blocker = restore_blocked_by(db, doc)
        rows.append(
            {
                "id": str(doc.id),
                "doc_type": doc.doc_type.value,
                "expires_on": doc.expires_on.isoformat() if doc.expires_on else None,
                "archived_at": doc.archived_at.isoformat(),
                # the archive opens the same viewer, so it needs the same field
                "content_type": doc.content_type,
                "reason": doc.archive_reason or documents.ARCHIVE_SUPERSEDED,
                "replaced_by": None
                if replacement is None
                else {
                    "id": str(replacement.id),
                    "doc_type": replacement.doc_type.value,
                    "uploaded_at": replacement.uploaded_at.isoformat(),
                },
                "restorable": blocker is None,
                "blocked_by_doc_type": None if blocker is None else blocker.doc_type.value,
            }
        )
    return sorted(rows, key=lambda r: r["archived_at"], reverse=True)


def expiry_reminders_due(db: Session, as_of: date | None = None) -> list:
    """What F6 says is due, ordered by PROXIMITY TO EXPIRY.

    The ordering is the whole design. §13.1 allows two unprompted notifications per
    driver per day; a driver with five credentials at 30/14/3 generates fifteen
    events, so on a bad day most of them lose. When something has to lose, the thing
    that survives should be the most urgent — the medical card expiring in three days
    beats the permit expiring in thirty. Same reasoning settled for vendor alerts in
    HANDOFF-081: where the cap bites, the nearest wins.
    """
    as_of = as_of or datetime.now(UTC).date()
    due = documents.due_reminders(db, as_of)
    return sorted(due, key=lambda pair: ((pair[0].expires_on - as_of).days, pair[1]))


def dispatch_expiry_reminders(db: Session, gateway, as_of: date | None = None, now=None) -> list:
    """§13.2 names "doc expires this week" as a P1 example, so these ride the ordinary
    tier rules — no new notification class, and therefore no §22.2 stop. Every §13
    law still applies: quiet hours, RESTING, and the two-per-day budget.

    A reminder is marked sent when it is DISPATCHED, not when it is delivered. F8 may
    suppress it for quiet hours or budget, and re-offering the same 30-day warning
    every morning until one gets through would be exactly the nagging §13 exists to
    prevent. The next rung (14, then 3) still comes.
    """
    as_of = as_of or datetime.now(UTC).date()
    now = now or datetime.now(UTC)
    if gateway is None:
        return []
    sent = []
    for document, offset in expiry_reminders_due(db, as_of):
        label = document.doc_type.value.replace("_", " ")
        sent.append(
            notify.dispatch(
                db,
                document.account_id,
                notify.NotificationTier.P1,
                "document_expiry",
                f"{label} expires in {offset} days",
                f"Renew it before {document.expires_on:%d %b} to stay road-legal.",
                "/docs",
                gateway,
                now=now,
                subject_ref=str(document.id),
            )
        )
        documents.mark_reminder_sent(db, document, offset)
    return sent
