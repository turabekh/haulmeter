"""AI-CONTEXT: what is INSIDE the Stop Packet — the half A1 is actually about.

`test_stop_packet_send.py` next door asserts the subject line and three absences (no
receivable, no `record_claim`, no demanding words). Every one of them passed while the
document a dispatcher received held ZERO artifacts and ONE row: `send_stop_packet`
composed from a brand-new empty log, so the driver's BOL and cargo photos — the entire
payload of "photograph documents and send them" — were in the database and not in the
packet. Measured on the running stack, not inferred.

Two mechanisms had to be wrong at once for that, and both are asserted here:

  · the packet composed one private log instead of the STOP (compose_stop_pack), and
  · a stop's DOCUMENTS reached no pack anywhere, because F6 holds them and every pack
    composes from F4 records and artifacts.

v2.0 §7 item 1 is "a recipient confirms it arrived usable". A blank page cannot be.
"""

from datetime import UTC, datetime

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f04_evidence import public as evidence
from app.foundation.f05_load import public as loads
from app.foundation.f08_notifications import public as notify
from app.modules.m05_protection import public as m5

NOW = datetime(2026, 8, 1, 14, 0, tzinfo=UTC)
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
SCANNED_CDL = b"%PDF-1.4\n% a scanned licence, not a photograph of a dock\n"


def _account(db, email="contents@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _armed_stop(db, account, reference_number="BL-9001"):
    broker = loads.create_counterparty(
        db, "Bolt Logistics", loads.CounterpartyKind.broker, contact_email="ap@bolt.example"
    )
    load = loads.create_load(
        db, account.id, counterparty_id=broker.id, reference_number=reference_number
    )
    fac = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Dock 4", 41.88, -87.63
    )
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery)
    loads.arm_stop(db, stop)  # opens the stop's evidence log
    return broker, load, stop


def _send(db, account, broker, stop):
    return m5.send_stop_packet(
        db,
        account.id,
        stop_ref=stop.id,
        counterparty_ref=broker.id,
        gateway=notify.RecordingNotificationGateway(),
        now=NOW,
        base_url_required=False,
    )


def test_the_bol_the_driver_photographed_is_IN_the_packet(db):
    """The one that matters. A1's whole burden is the paperwork reaching the broker."""
    account = _account(db)
    broker, _load, stop = _armed_stop(db, account)
    m5.capture_document(db, account.id, "bol", PNG, filename="bol.png", stop_ref=stop.id)

    pack = _send(db, account, broker, stop)["pack"]

    assert pack.artifacts, "the packet contains nothing the driver photographed"
    hashes = {a["content_hash"] for a in pack.artifacts}
    from app.foundation.f06_documents import public as documents

    bol = documents.documents_for_subject(db, "stop", stop.id, doc_type=documents.DocType.bol)[0]
    assert bol.content_hash in hashes, "the BOL is not in the document that was sent"


def test_cargo_condition_photos_travel_with_it(db):
    account = _account(db)
    broker, _load, stop = _armed_stop(db, account)
    capture = m5.start_condition_capture(db, stop, account.id, m5.CapturePhase.delivery)
    log = db.get(evidence.EvidenceLog, capture.evidence_log_ref)
    evidence.attach_artifact(
        db, log, evidence.ArtifactType.photo, PNG, captured_at=NOW
    )

    pack = _send(db, account, broker, stop)["pack"]

    assert len(pack.artifacts) >= 1, "condition photos were composed out of the packet"


def test_a_credential_is_NOT_in_a_packet_sent_to_a_broker(db):
    """The distinction the chaining rests on. A CDL is filed against the ACCOUNT, not
    the stop, and a document going to a counterparty must never carry it."""
    account = _account(db)
    broker, _load, stop = _armed_stop(db, account)
    # distinct bytes on purpose: the hash is the identity here, and two documents
    # carrying the same image would make this assertion pass for the wrong reason
    m5.capture_document(
        db, account.id, "cdl", SCANNED_CDL, filename="cdl.pdf", content_type="application/pdf"
    )  # no stop_ref — a credential is filed against the ACCOUNT
    m5.capture_document(db, account.id, "bol", PNG, filename="bol.png", stop_ref=stop.id)

    pack = _send(db, account, broker, stop)["pack"]

    from app.foundation.f06_documents import public as documents

    cdl = documents.documents_for_account(db, account.id, doc_type=documents.DocType.cdl)[0]
    hashes = {a["content_hash"] for a in pack.artifacts}
    assert cdl.content_hash not in hashes, "the driver's licence was sent to a broker"


def test_it_announces_itself_as_the_handoff_it_is(db):
    """`PackTemplate.stop_packet` existed, was titled "Stop paperwork packet", and
    nothing used it — the handoff arrived calling itself a "Stop record"."""
    account = _account(db)
    broker, _load, stop = _armed_stop(db, account)

    pack = _send(db, account, broker, stop)["pack"]

    assert pack.template is evidence.PackTemplate.stop_packet


def test_the_document_names_the_load_the_dock_and_the_broker(db):
    """§17: the PDF is a screen. It was rendered with NO context at all — no parties,
    no reference, no facility — so an AP clerk received a hash block to file."""
    account = _account(db)
    broker, load, stop = _armed_stop(db, account, reference_number="BL-4242")
    m5.capture_document(db, account.id, "bol", PNG, filename="bol.png", stop_ref=stop.id)

    _send(db, account, broker, stop)
    context = m5.packet_context(db, stop, load)

    assert ("Load", "BL-4242") in context.references
    assert ("Facility", "Dock 4") in context.references
    assert ("Broker", "Bolt Logistics") in context.parties


def test_it_carries_NO_detention_figure(db):
    """A1: "explicitly not a claim and not a dispute". §17 puts the Meter on a claim
    pack's face; putting it here would make the handoff an argument."""
    account = _account(db)
    broker, load, stop = _armed_stop(db, account)

    context = m5.packet_context(db, stop, load)

    assert context.meter == [], "a routine handoff stated a detention figure"


def test_the_packet_renders_to_a_real_pdf(db):
    """The render is where a malformed context or a missing image would surface, and
    §23's own history says the way to find that is to render it and look."""
    account = _account(db)
    broker, load, stop = _armed_stop(db, account)
    m5.capture_document(db, account.id, "bol", PNG, filename="bol.png", stop_ref=stop.id)

    result = _send(db, account, broker, stop)
    content = m5.render_pack(db, result["pack"], m5.packet_context(db, stop, load))

    assert content.startswith(b"%PDF"), "the packet did not render"
    assert len(content) > 1000
