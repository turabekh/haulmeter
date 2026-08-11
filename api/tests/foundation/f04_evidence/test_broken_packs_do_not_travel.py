"""F4-3 and D7 — a pack that fails its own check does not travel, and the words match it.

The render has printed "HASH CHAIN BROKEN — do not rely on this pack" since it was written,
and nothing stopped that PDF being pinned, given a link, and emailed to a broker under the
driver's name. The document said do not rely on me and the product sent it anyway.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f04_evidence import public as evidence
from app.foundation.f04_evidence.domain.models import EvidenceRecord, SharedPack
from app.foundation.f05_load import public as loads
from app.modules.m03_detention import public as m3
from app.modules.m03_detention.domain import service as m3_service

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
FILED = T0 + timedelta(minutes=240)


class CountingGateway:
    def __init__(self):
        self.sent = []

    def send_email(self, to_ref, subject, body):
        self.sent.append((to_ref, subject, body))
        return f"smtp-ok-{len(self.sent)}"


def _claim(db, email="oo@example.com"):
    account = identity.register_account(db, email, "pw-123456")
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    broker = loads.create_counterparty(
        db, "Acme", loads.CounterpartyKind.broker, contact_email="ap@acme.example"
    )
    load = loads.create_load(
        db, account.id, counterparty_id=broker.id, reference_number="BL-1",
        detention_rate_cents_per_hour=7500, free_time_minutes=120,
    )
    stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery, appointment_start=T0)
    claim = m3.start_claim(db, stop, started_at=T0)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0, now=T0)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=FILED, now=FILED)
    return account, claim


def _break_the_chain(db, claim):
    """Doctor a payload WITHOUT re-hashing — the plain `tampered` shape."""
    log = db.get(evidence.EvidenceLog, claim.evidence_log_ref)
    record = (
        db.query(EvidenceRecord).filter_by(log_id=log.id).order_by(EvidenceRecord.seq).first()
    )
    record.payload = {"event": "doctored"}
    db.flush()
    return log


def test_a_broken_chain_is_not_pinned_linked_or_emailed(db):
    account, claim = _claim(db)
    m3.accrue_events(db, claim)
    log = _break_the_chain(db, claim)
    gateway = CountingGateway()
    shares_before = db.query(SharedPack).count()

    with pytest.raises(m3.EvidenceCheckFailed):
        m3.generate_pack(db, claim, now=FILED, gateway=gateway)

    assert gateway.sent == []  # nothing reached the broker
    assert db.query(SharedPack).filter_by(log_id=log.id).count() == shares_before
    # ...and the claim stays claimable rather than being marked filed over nothing
    assert claim.state == m3.ClaimState.open
    assert claim.receivable_ref is None


def test_the_refusal_says_why(db):
    _, claim = _claim(db)
    m3.accrue_events(db, claim)
    _break_the_chain(db, claim)

    with pytest.raises(m3.EvidenceCheckFailed) as caught:
        m3.generate_pack(db, claim, now=FILED)

    assert caught.value.verification.reason == "tampered"


def test_an_anchor_mismatch_also_stops_the_pack(db):
    """The new failure mode from T2 flows through the same gate."""
    from app.foundation.f04_evidence.domain import hashing

    _, claim = _claim(db)
    m3.accrue_events(db, claim)
    log = db.get(evidence.EvidenceLog, claim.evidence_log_ref)
    evidence.anchor_chain(db, log)
    records = db.query(EvidenceRecord).filter_by(log_id=log.id).order_by(EvidenceRecord.seq).all()
    prev = records[0].record_hash
    records[1].payload = {"event": "rewritten"}
    for record in records[1:]:
        record.prev_hash = prev
        record.record_hash = hashing.compute_record_hash(
            prev, record.seq, record.record_type.value, record.payload, record.occurred_at
        )
        prev = record.record_hash
    db.flush()
    gateway = CountingGateway()

    with pytest.raises(m3.EvidenceCheckFailed) as caught:
        m3.generate_pack(db, claim, now=FILED, gateway=gateway)

    assert caught.value.verification.reason == "anchor_mismatch"
    assert gateway.sent == []


def test_a_healthy_chain_travels_exactly_as_before(db):
    """The other half: the gate must not have made the ordinary path conditional."""
    account, claim = _claim(db)
    gateway = CountingGateway()

    result = m3.generate_pack(db, claim, now=FILED, gateway=gateway)

    assert result["shared"] is not None
    assert claim.state == m3.ClaimState.invoiced
    assert len(gateway.sent) == 1


# --- D7: the words match the proof ---
COUNTERPARTY_BODY_SOURCES = [
    "app/modules/m03_detention/domain/service.py",
    "app/modules/m05_protection/domain/service.py",
]


def test_no_counterparty_body_claims_gps_is_verified():
    """A grep, in the token-discipline shape already in this tree.

    "GPS-verified" is a claim about the DATA, and the pack cannot back it: the coordinates
    are whatever the driver's handset reported, with nothing gating accuracy, flagging a
    mock provider, or surfacing `gps_time_divergent`. The chain proves the reading has not
    been altered SINCE it was recorded; it proves nothing about how it was produced. The
    Location basis section is what makes the remaining language defensible.

    The whole FILE is checked, docstrings and comments included: the module's own summary
    said "GPS-verified detention" too, and a phrase the code repeats to its next reader is
    how it gets back into a string a broker sees.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[3]
    # assembled so this file does not contain the thing it forbids
    needle = re.compile("GPS" + "-verified", re.IGNORECASE)
    offenders = [
        f"{rel}:{n}: {line.strip()}"
        for rel in COUNTERPARTY_BODY_SOURCES
        for n, line in enumerate((root / rel).read_text().splitlines(), 1)
        if needle.search(line)
    ]

    assert offenders == [], "counterparty copy claims verification it cannot support:\n" + "\n".join(
        offenders
    )


def test_the_counterparty_body_still_names_the_evidence(db):
    """Removing the overclaim must not remove the offer — the link is the point."""
    account, claim = _claim(db)
    gateway = CountingGateway()

    m3.generate_pack(db, claim, now=FILED, gateway=gateway)
    body = gateway.sent[0][2]

    assert "GPS evidence" in body
    assert "/pack/s/" in body or "available on request" in body


# --- D6: the basis section in a rendered pack ---
def _drawn(pdf: bytes) -> str:
    """The text drawn into the page, read the way this suite already reads a PDF.

    `test_render.py` asserts on raw bytes; reportlab writes the drawn strings literally
    (no stream compression is enabled here), so a decode with errors ignored is enough to
    check that a label reached the page.
    """
    return pdf.decode("latin-1", errors="ignore")


def test_a_pack_states_what_its_location_data_is(db):
    account, claim = _claim(db, email="basis@example.com")
    # a trail with a known shape: one vague fix, one divergent clock, one teleport
    location.record_ping(db, account.id, *DALLAS, occurred_at=T0, accuracy_m=8.0)
    location.record_ping(
        db, account.id, *DALLAS, occurred_at=T0 + timedelta(minutes=20), accuracy_m=120.0,
        gps_time=T0 + timedelta(minutes=45),
    )
    location.record_ping(db, account.id, 35.0, -99.0, occurred_at=T0 + timedelta(minutes=40))
    m3.accrue_events(db, claim)
    pack = evidence.compose_pack(db, claim_log(db, claim), evidence.PackTemplate.detention_claim)

    text = _drawn(m3_service.render_pack_bytes(db, pack, claim))

    assert "Location basis" in text
    assert "as reported by the driver" in text
    assert "Position fixes" in text
    assert "Device clock disagreed" in text
    assert "Implausible movements" in text


def test_a_pack_with_no_trail_says_so_and_asserts_nothing(db):
    """Purged or never recorded — the section must not render zeros as a clean bill."""
    account, claim = _claim(db, email="notrail@example.com")
    m3.accrue_events(db, claim)
    # the visit's pings are what `_claim` recorded; drop them the way retention would
    from app.foundation.f03_location.domain.models import LocationPing

    db.query(LocationPing).filter_by(account_id=account.id).delete()
    db.flush()
    pack = evidence.compose_pack(db, claim_log(db, claim), evidence.PackTemplate.detention_claim)

    text = _drawn(m3_service.render_pack_bytes(db, pack, claim))

    assert "Location basis" in text
    assert "not available for this period" in text
    assert "Implausible movements" not in text  # no figure is asserted


def claim_log(db, claim):
    return db.get(evidence.EvidenceLog, claim.evidence_log_ref)
