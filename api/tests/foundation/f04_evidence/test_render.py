"""AI-CONTEXT: the §17 artifact — "the PDF is a screen".

`render_pack_pdf` was a seam that raised `RenderNotEnabled` while PRD §7.16(b)
asked the Foundation e2e for a "hash-chain-valid evidence pack **PDF** offline" and
the certifying test had quietly dropped the word. These tests are what stop that
drifting again.

What they defend, in order of what it would cost to get wrong:

· **Determinism.** PRD §11 requires packs "verifiable by a third party". If the
  bytes change on every render, the pack's own hash cannot identify it and nobody
  can confirm they hold what was sent. The creation date therefore comes from the
  CHAIN, never the clock.
· **A broken chain says so.** An evidence pack that hid its own failure is worse
  than no pack, because someone would rely on it.
· **The fonts are embedded.** A PDF cannot fall back to a system stack on the
  reader's machine, so §6.2's "no other families, ever" is only true if the faces
  actually travel inside the file.
· **Missing data omits a section rather than printing an empty one.** "Broker: —"
  tells a clerk we do not know who they are.
"""

import re
from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f04_evidence import public as evidence

T0 = datetime(2026, 7, 20, 7, 58, tzinfo=UTC)
DALLAS = (32.7767, -96.7970)


def _account(db, email="pack@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _chain(db, account, points=True):
    log = evidence.create_log(db, account.id, label="Load 4471 · Dallas")
    evidence.append_record(
        db,
        log,
        evidence.RecordType.GEOFENCE,
        {"event": "enter", "lat": DALLAS[0], "lon": DALLAS[1]},
        occurred_at=T0,
    )
    if points:
        evidence.append_record(
            db,
            log,
            evidence.RecordType.GEOFENCE,
            {"event": "exit", "lat": 32.7800, "lon": -96.7900},
            occurred_at=T0 + timedelta(hours=3, minutes=26),
        )
    evidence.attach_artifact(
        db,
        log,
        evidence.ArtifactType.photo,
        content=b"trailer-exterior-photo",
        gps_lat=DALLAS[0],
        gps_lon=DALLAS[1],
        captured_at=T0 + timedelta(minutes=2),
    )
    return log


def _pack(db, account, template=None):
    log = _chain(db, account)
    return evidence.compose_pack(db, log, template or evidence.PackTemplate.detention_claim)


def test_a_real_pdf_comes_out(db):
    pack = _pack(db, _account(db))
    data = evidence.render_pack_pdf(pack)

    assert data[:5] == b"%PDF-"
    assert data.rstrip().endswith(b"%%EOF")
    assert len(data) > 2000


def test_the_same_chain_renders_the_same_bytes(db):
    """PRD §11: verifiable by a third party. Two renders of one chain must be
    indistinguishable, or the artifact's hash means nothing."""
    pack = _pack(db, _account(db, "determinism@example.com"))

    first = evidence.render_pack_pdf(pack)
    second = evidence.render_pack_pdf(pack)

    assert first == second


def test_the_creation_date_comes_from_the_chain_not_the_clock(db):
    """The date that matters on an evidence pack is when the events happened. Taking
    it from `now` would also break byte-identity on every regeneration."""
    pack = _pack(db, _account(db, "clock@example.com"))
    data = evidence.render_pack_pdf(pack)

    # the latest record is T0 + 3h26m -> 2026-07-20
    assert b"D:20260720" in data
    # ...and specifically NOT today. Comparing the year would prove nothing whenever
    # the chain happens to fall in the current year, which is most of the time.
    today = datetime.now(UTC).strftime("D:%Y%m%d").encode()
    if today != b"D:20260720":
        assert today not in data


def test_the_plex_faces_travel_inside_the_file(db):
    """§6.2 permits no other family. A PDF has no fallback stack on the reader's
    machine, so the faces must be embedded, not merely named."""
    pack = _pack(db, _account(db, "fonts@example.com"))
    data = evidence.render_pack_pdf(pack)

    assert b"IBMPlexSans" in data
    assert b"IBMPlexMono" in data
    # embedded, not merely referenced: /FontFile2 is the TrueType program itself
    assert b"/FontFile2" in data


def test_a_broken_chain_is_stated_on_the_document(db):
    from sqlalchemy import select

    from app.foundation.f04_evidence.domain.models import EvidenceRecord

    account = _account(db, "broken@example.com")
    log = _chain(db, account)
    record = db.scalars(
        select(EvidenceRecord).where(EvidenceRecord.log_id == log.id).order_by(EvidenceRecord.seq)
    ).first()
    record.payload = {"event": "tampered"}
    db.flush()

    pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)
    assert pack.verification["chain_valid"] is False
    data = evidence.render_pack_pdf(pack)

    # said in words, not only in colour (C-1) — and said loudly
    assert b"HASH CHAIN BROKEN" in data


def test_the_meter_and_parties_render_when_supplied(db):
    pack = _pack(db, _account(db, "context@example.com"))
    context = evidence.PackContext(
        parties=[("Carrier", "Owner Operator LLC"), ("Broker", "Acme Logistics")],
        references=[("Load", "4471"), ("BOL", "BOL-88213")],
        meter=[("Total detention", "3:26:00"), ("Amount", "$172.00")],
        facility_name="Dallas Receiving",
    )
    data = evidence.render_pack_pdf(pack, context)

    for expected in (b"Acme Logistics", b"BOL-88213", b"3:26:00", b"$172.00"):
        assert expected in data


def test_a_section_with_no_data_is_omitted_not_left_blank(db):
    """ "Broker: —" tells a clerk we do not know who they are, which is worse than
    not asking. An absent section is silent."""
    pack = _pack(db, _account(db, "empty@example.com"))
    data = evidence.render_pack_pdf(pack)

    assert b"Parties" not in data
    assert b"References" not in data
    # the sections that DO have data are still there
    assert b"Event timeline" in data
    assert b"Verification" in data


def test_every_template_renders(db):
    for i, template in enumerate(evidence.PackTemplate):
        pack = _pack(db, _account(db, f"tpl{i}@example.com"), template)
        data = evidence.render_pack_pdf(pack)
        assert data[:5] == b"%PDF-"


def test_a_pack_with_no_located_records_still_renders(db):
    """The trace is drawn from located evidence. A chain with none is ordinary — an
    incident captured indoors, say — and must not take the document down with it."""
    account = _account(db, "notrace@example.com")
    log = evidence.create_log(db, account.id, label="no-gps")
    evidence.append_record(db, log, evidence.RecordType.USER_ACTION, {"event": "noted"}, T0)
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.cargo_condition)

    data = evidence.render_pack_pdf(pack)
    assert data[:5] == b"%PDF-"
    assert b"Location trace" not in data


def test_a_thumbnail_that_cannot_be_loaded_degrades_to_its_hash(db):
    """The hash is the evidence; the image is the convenience. A storage miss must
    not cost a clerk the record."""
    pack = _pack(db, _account(db, "badimage@example.com"))
    content_hash = pack.artifacts[0]["content_hash"]
    context = evidence.PackContext(images={content_hash: b"not-actually-an-image"})

    data = evidence.render_pack_pdf(pack, context)
    assert data[:5] == b"%PDF-"
    assert content_hash[:12].encode() in data


def test_the_timeline_reads_in_time_order_not_chain_order(db):
    """Caught by opening the document, not by any byte assertion.

    Records are chained in INSERTION order, so a photo attached after the fact but
    stamped with its capture time sits late in the chain and early in the day. The
    first real render produced timestamps running 07:58, 08:04, 09:58, 08:58 — which
    a clerk reads as sloppy at best. The evidence is unchanged; only the reading
    order is fixed.
    """
    account = _account(db, "ordering@example.com")
    log = evidence.create_log(db, account.id, label="out-of-order")
    # appended late, happened first
    evidence.append_record(
        db, log, evidence.RecordType.SYSTEM, {"event": "third"}, T0 + timedelta(hours=2)
    )
    evidence.append_record(db, log, evidence.RecordType.SYSTEM, {"event": "first"}, T0)
    evidence.append_record(
        db, log, evidence.RecordType.SYSTEM, {"event": "second"}, T0 + timedelta(hours=1)
    )
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)

    # the chain itself keeps insertion order — that is what the hashes commit to
    assert [r["payload"]["event"] for r in pack.timeline] == ["third", "first", "second"]

    data = evidence.render_pack_pdf(pack)
    stamps = re.findall(rb"\(([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} UTC)\)", data)
    assert stamps == sorted(stamps), "the rendered timeline must read in time order"


def test_the_trace_follows_time_not_the_order_points_were_recorded(db):
    """Same root cause as the timeline: joining located points in chain order drew a
    zig-zag between coordinates that no one actually drove."""
    from app.foundation.f04_evidence.domain.render import _located_points

    account = _account(db, "tracepath@example.com")
    log = evidence.create_log(db, account.id, label="path")
    evidence.append_record(
        db,
        log,
        evidence.RecordType.GEOFENCE,
        {"event": "exit", "lat": 32.79, "lon": -96.78},
        occurred_at=T0 + timedelta(hours=3),
    )
    evidence.append_record(
        db,
        log,
        evidence.RecordType.GEOFENCE,
        {"event": "enter", "lat": 32.77, "lon": -96.80},
        occurred_at=T0,
    )
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)

    points = _located_points(pack)
    assert points[0] == (32.77, -96.80), "the trace must start where the driver started"
    assert points[-1] == (32.79, -96.78)


def test_a_late_filed_record_discloses_both_clocks(db):
    """Sorting by capture time was right and not sufficient. The chain's hashes
    commit to SEQ — filing order — so a counterparty holding the chain can show the
    rendered order differs from the order the hashes cover. F12 records both clocks
    precisely so the gap can be disclosed; recording it and hiding it wastes it."""
    from sqlalchemy import select

    from app.foundation.f04_evidence.domain.models import EvidenceRecord

    account = _account(db, "divergence@example.com")
    log = evidence.create_log(db, account.id, label="dead zone")
    evidence.append_record(db, log, evidence.RecordType.PHOTO, {"event": "seal"}, T0)
    # captured at the dock with no signal, synced six hours later
    record = db.scalars(select(EvidenceRecord).where(EvidenceRecord.log_id == log.id)).one()
    record.received_at = T0 + timedelta(hours=6, minutes=24)
    db.flush()

    pack = evidence.compose_pack(db, log, evidence.PackTemplate.cargo_condition)
    assert pack.timeline[0]["received_at"] is not None
    data = evidence.render_pack_pdf(pack)

    assert b"filed 14:22" in data


def test_ordinary_drift_is_not_announced_on_every_row(db):
    """Sub-threshold jitter is clock drift and sync latency, not evidence. Disclosing
    it everywhere would bury the rows where the gap means something."""
    from sqlalchemy import select

    from app.foundation.f04_evidence.domain.models import EvidenceRecord

    account = _account(db, "drift@example.com")
    log = evidence.create_log(db, account.id, label="online")
    evidence.append_record(db, log, evidence.RecordType.PHOTO, {"event": "seal"}, T0)
    record = db.scalars(select(EvidenceRecord).where(EvidenceRecord.log_id == log.id)).one()
    record.received_at = T0 + timedelta(seconds=90)
    db.flush()

    pack = evidence.compose_pack(db, log, evidence.PackTemplate.cargo_condition)
    data = evidence.render_pack_pdf(pack)

    assert b"filed" not in data


def test_a_prompt_is_attributed_never_asserted(db):
    """`Photo  seals` reads, to a clerk, as *this photograph shows the seals* — the
    platform asserting image content in its own voice. If the driver photographed a
    mud flap at step two, the document states something false and we said it. What
    happened is that we prompted for seals and this is what arrived.

    Same discipline as "Vendor says halal" never being a bare "Halal"."""
    account = _account(db, "attribution@example.com")
    log = evidence.create_log(db, account.id, label="condition-pickup")
    evidence.attach_artifact(
        db,
        log,
        evidence.ArtifactType.photo,
        content=b"a-photo",
        exif={"prompt": "seals"},
        captured_at=T0,
    )
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.cargo_condition)
    data = evidence.render_pack_pdf(pack)

    assert b"prompted: seals" in data
    # the bare form must never appear: it is the assertion we are refusing to make
    assert b"(seals)" not in data
