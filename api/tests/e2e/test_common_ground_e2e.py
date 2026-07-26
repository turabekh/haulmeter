"""AI-CONTEXT: Foundation Definition of Done §7.16(b) — the synthetic end-to-end.

One flow, exercising F1–F9 + F12 through their public interfaces only: a test
driver with a parsed rate con is geofence-armed at a seeded facility, generates
a hash-chain-valid evidence pack PDF offline, syncs it idempotently, and triggers
a templated (English) counterparty email with a ledger receivable opened. If this
stays green, the Common Ground holds together as a product, not just as parts.

The word PDF in that sentence is load-bearing and was missing for a while. §7.16(b)
has always asked for the artifact, not for the dataclass behind it; the assertion
had relaxed to `chain_valid` on a composed structure, which meant the Foundation
DoD was signed off against something a broker could not open. It renders again, and
this docstring says so, so the next person to relax it has to do it in writing.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f04_evidence import public as evidence
from app.foundation.f05_load import public as loads
from app.foundation.f06_documents import public as documents
from app.foundation.f07_ledger import public as ledger
from app.foundation.f08_notifications import public as notify
from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f12_offline import public as offline

RECEIVER = (32.7767, -96.7970)
AWAY = (32.9000, -96.8000)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


def test_common_ground_synthetic_end_to_end(db):
    # F1 — driver onboarding: email/password, NO activation step; own authority can invoice
    account = identity.register_account(db, "owneroperator@example.com", "pw-123456")
    identity.attach_role(db, account, identity.Role.driver)
    profile = identity.upsert_driver_profile(
        db, account, authority_type=identity.AuthorityType.own_mc, home_timezone="America/Chicago"
    )
    assert identity.authenticate(db, "owneroperator@example.com", "pw-123456") is not None
    assert identity.can_invoice(profile) is True

    # F2 — seed the canonical receiver facility
    receiver = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Dallas Receiver", *RECEIVER
    )

    # F6 — store the rate con document
    storage = documents.InMemoryObjectStorage()
    rate_con = documents.store_document(
        db,
        account.id,
        documents.DocType.rate_con,
        b"%PDF rate confirmation",
        filename="ratecon.pdf",
        storage=storage,
    )

    # F9 — parse the rate con through the AI gateway (fake provider -> structured terms)
    ai.register_prompt(db, "rate_con_parse", ai.AiTask.document_parse, "parse {doc}")
    provider = ai.FakeModelProvider(
        structured_output={
            "rate_cents": 250000,
            "detention_rate_cents_per_hour": 7500,
            "free_time_minutes": 120,
            "reference_number": "L-9001",
        }
    )
    parsed = ai.parse_structured(
        db,
        provider,
        "m03",
        "rate_con_parse",
        {"doc": rate_con.content_hash},
        required_keys=["rate_cents", "detention_rate_cents_per_hour"],
    )
    documents.apply_extraction(db, rate_con, parsed)

    # F5 — load + counterparty + stop from the parsed terms
    broker = loads.create_counterparty(
        db, "Acme Brokerage", loads.CounterpartyKind.broker, contact_email="ap@acme.com"
    )
    load = loads.create_load_from_parsed_terms(
        db, account.id, {**parsed, "counterparty_id": broker.id}
    )
    stop = loads.add_stop(db, load, receiver.id, loads.StopType.delivery, appointment_start=T0)

    # F5 arm_stop wires F3 geofence + F4 evidence log
    loads.arm_stop(db, stop)
    assert stop.evidence_log_id is not None
    log = db.get(evidence.EvidenceLog, stop.evidence_log_id)
    assert log.stop_ref == stop.id

    # F3 — geofence-verified arrival, then departure after 3h of dwell
    enter = location.evaluate_ping(db, account.id, *RECEIVER, occurred_at=T0)
    assert [e.event_type for e in enter] == [location.GeofenceEventType.ENTER]
    leave = location.evaluate_ping(db, account.id, *AWAY, occurred_at=T0 + timedelta(hours=3))
    assert [e.event_type for e in leave] == [location.GeofenceEventType.EXIT]

    # F4 — accrue the geofence events + a BOL photo into the hash-chained log, anchor, compose
    for event in enter + leave:
        evidence.append_record(
            db,
            log,
            evidence.RecordType.GEOFENCE,
            {"event": event.event_type.value},
            occurred_at=event.occurred_at,
        )
    evidence.attach_artifact(
        db, log, evidence.ArtifactType.photo, content=b"bol-photo-bytes", captured_at=T0
    )
    evidence.anchor_chain(db, log, external_ref="tsa-stub-receipt")
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)
    assert pack.verification["chain_valid"] is True
    assert pack.verification["anchored"] is True

    # ...and §7.16(b) asks for a PDF, so render the real artifact (design-prd §17).
    # No network, no fonts fetched, no tile server: it renders from the chain alone,
    # which is what "offline" in the DoD sentence has to mean.
    artifact = evidence.render_pack_pdf(
        pack,
        evidence.PackContext(
            parties=[("Carrier", "Owner Operator LLC"), ("Broker", "Acme Logistics")],
            references=[("Load", str(load.id)[:8]), ("Stop", str(stop.id)[:8])],
            meter=[("Total detention", "3:00:00"), ("Amount", "$225.00")],
            facility_name="Dallas Receiving",
        ),
    )
    assert artifact[:5] == b"%PDF-"
    assert artifact.rstrip().endswith(b"%%EOF")
    # the verification block a third party acts on, and the parties they check
    assert b"Hash chain intact" in artifact
    assert b"Acme Logistics" in artifact
    # rendering is deterministic: the same chain is the same document (PRD §11)
    assert evidence.render_pack_pdf(pack) == evidence.render_pack_pdf(pack)

    # F12 — the claim pack is captured offline and synced idempotently (once)
    key = f"claim-pack-{stop.id}"
    first = offline.ingest(
        db, account.id, key, "claim_pack", {"log_id": str(log.id)}, occurred_at=T0
    )
    retry = offline.ingest(
        db, account.id, key, "claim_pack", {"log_id": str(log.id)}, occurred_at=T0
    )
    assert first.applied is True
    assert retry.applied is False

    # F7 — a ledger receivable is opened for the detention claim (invoiced)
    free_time, rate = loads.effective_detention_terms(db, stop)
    assert (free_time, rate) == (120, 7500)
    receivable = ledger.create_receivable(
        db, account.id, ledger.ReceivableKind.detention, 15000, counterparty_ref=broker.id
    )
    assert receivable.state == ledger.ReceivableState.invoiced

    # F8 + F15 — templated counterparty email, ALWAYS English, on a tracked thread
    notify.register_template(
        db,
        "detention_invoice",
        "Detention owed on load {ref}: {amount}",
        notify.TemplateAudience.counterparty,
        notify.NotificationChannel.email,
        locale="en",
    )
    template = notify.get_active_template(db, "detention_invoice")
    _, body = notify.render_template(template, {"ref": load.reference_number, "amount": "$150.00"})
    assert body == "Detention owed on load L-9001: $150.00"

    gateway = notify.RecordingNotificationGateway()
    thread = notify.create_thread(
        db, account.id, subject="Detention notice — L-9001", counterparty_ref=broker.id
    )
    message = notify.send_counterparty_message(db, thread, body, gateway, "ap@acme.com", now=T0)
    assert message.sent_at is not None
    assert gateway.sent[0].channel == "email"
