"""AI-CONTEXT: M14 slice 1 — the connector, the ingest, and the gate that holds the send.

WHAT THESE TESTS ARE NOT. They are not the proof that ELD pings produce geofence events.
That proof is `make m14-prove`, run against the real F3 evaluator and the seeded Tampa DEV
shipper, with its output in the handoff — the kickoff is explicit that a green unit test is
not that observation, and it was right: the first run of that probe returned **zero
events** over six correctly-ingested pings, because the coordinates were swapped. Nothing
in this file would have caught it.

What these hold is everything a unit test CAN hold honestly: that the key is never stored
in the clear, that a replayed poll is inert, that an unmapped vehicle is skipped rather
than guessed, that the fake mirrors the provider's nulls, and that the send refuses while
D13 is unanswered.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f03_location import public as location
from app.foundation.f13_flags import public as flags
from app.modules.m14_recovery import public as m14
from app.modules.m14_recovery.domain import crypto

DALLAS = (32.7767, -96.7970)
FLEET = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _connector_key(monkeypatch):
    # a per-test key, so nothing here depends on the box's real one
    monkeypatch.setenv(crypto.SECRET_ENV, "c2VjcmV0LWtleS0zMi1ieXRlcy1sb25nLWVub3VnaCE=")


def _driver(db, email="fleetdriver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _connector(db):
    return m14.connect_fleet(db, FLEET, "mot_live_abcd1234", m14.Provider.motive)


# --- the pasted key ----------------------------------------------------------------


def test_the_key_is_never_stored_in_the_clear(db):
    """The whole reason the column is ciphertext: this database is dumped offsite nightly.

    A12 made the upload a REQUIRED step, so a plaintext column would ship a working
    credential to somebody else's fleet telematics into a bucket every night.
    """
    connector = _connector(db)
    assert "mot_live_abcd1234" not in connector.key_ciphertext
    assert connector.key_last4 == "1234"
    # and it round-trips, because the poller has to present it to Motive
    assert crypto.decrypt_key(connector.key_ciphertext) == "mot_live_abcd1234"


def test_storing_a_key_REFUSES_when_the_secret_is_absent(db, monkeypatch):
    # a silent fallback to plaintext is how a security control becomes decorative —
    # audit F-02's shape. A fleet that cannot connect is a visible problem; a fleet
    # connected with an unprotected key is an invisible one.
    monkeypatch.delenv(crypto.SECRET_ENV, raising=False)
    with pytest.raises(m14.ConnectorKeyUnavailable):
        _connector(db)


def test_re_pasting_a_key_replaces_rather_than_accumulates(db):
    # a second row for one (fleet, provider) is a ROTATION, not a second connector —
    # migration 0077's lesson from one session ago, applied before the defect
    first = _connector(db)
    second = m14.connect_fleet(db, FLEET, "mot_live_wxyz9999", m14.Provider.motive)
    assert first.id == second.id
    assert second.key_last4 == "9999"
    assert crypto.decrypt_key(second.key_ciphertext) == "mot_live_wxyz9999"


# --- the provider's shapes ----------------------------------------------------------


def test_the_parser_survives_the_nulls_the_real_api_emits():
    """HANDOFF-121 §13.7: a stub returning `{}` where the endpoint returns `null` cost a
    debugging round, and the kickoff names that trap for this step. So the fake emits the
    real shapes and the parser has to survive them."""
    when = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    payload = {
        "vehicle_locations": [
            {"vehicle": {"id": "v1"}, "current_location": None},  # no fix at all
            {"vehicle": None, "current_location": {"lat": 1.0, "lon": 2.0}},  # no vehicle
            {"vehicle": {"id": "v2"}, "current_location": {"lat": 1.0, "lon": 2.0}},  # no time
            # AI-CONTEXT: a vehicle and a TIME but no POSITION — added because the
            # sabotage pass found nothing covered it. Every other row here is dropped by
            # the vehicle or the timestamp check, so defaulting a missing lat/lon to 0,0
            # (the Gulf of Guinea) passed the whole suite. A breadcrumb with a guessed
            # position is a false arrival, and this module's output is an invoice.
            {
                "vehicle": {"id": "v4"},
                "current_location": {
                    "lat": None,
                    "lon": None,
                    "located_at": "2026-08-15T12:00:00Z",
                },
            },
            None,
            m14.FakeMotiveClient.row("v3", 32.7, -96.8, when, speed_mph=None),
        ]
    }
    crumbs = m14.parse_vehicle_locations(payload)
    # only the complete record survives — a breadcrumb with a guessed position is a false
    # arrival, and this module's output is an invoice
    assert [c.vehicle_ref for c in crumbs] == ["v3"]
    assert crumbs[0].speed_mps is None


def test_speed_is_converted_from_mph(db):
    # a unit left unconverted is the quietest wrong number available: it never looks
    # absurd, it just makes every movement check wrong by 2.24
    when = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    crumbs = m14.parse_vehicle_locations(
        {"vehicle_locations": [m14.FakeMotiveClient.row("v1", 32.7, -96.8, when, speed_mph=60)]}
    )
    assert crumbs[0].speed_mps == pytest.approx(26.8224, rel=1e-3)


def test_parse_survives_an_empty_or_absent_payload():
    assert m14.parse_vehicle_locations(None) == []
    assert m14.parse_vehicle_locations({}) == []
    assert m14.parse_vehicle_locations({"vehicle_locations": None}) == []


# --- ingest ------------------------------------------------------------------------


def _crumbs(ref, lat, lon, start, count=3, step_minutes=10):
    return [
        m14.Breadcrumb(ref, lat, lon, start + timedelta(minutes=step_minutes * i))
        for i in range(count)
    ]


def test_pings_land_with_the_provider_as_their_source(db):
    driver = _driver(db)
    connector = _connector(db)
    m14.map_vehicle(db, connector, "veh-1", driver.id)
    start = datetime.now(UTC) - timedelta(hours=1)

    result = m14.ingest_breadcrumbs(db, connector, _crumbs("veh-1", *DALLAS, start))
    assert result.imported == 3

    rows = db.query(location.LocationPing).filter_by(account_id=driver.id).all()
    assert {r.source for r in rows} == {"eld:motive"}


def test_a_replayed_poll_is_inert(db):
    """Polling overlaps by construction — the same breadcrumb on consecutive polls is the
    NORMAL case. And a replayed ping is not harmless: it advances dwell state and can
    re-fire an edge, which is a second arrival on one visit."""
    driver = _driver(db)
    connector = _connector(db)
    m14.map_vehicle(db, connector, "veh-1", driver.id)
    start = datetime.now(UTC) - timedelta(hours=1)
    crumbs = _crumbs("veh-1", *DALLAS, start)

    first = m14.ingest_breadcrumbs(db, connector, crumbs)
    again = m14.ingest_breadcrumbs(db, connector, crumbs)

    assert first.imported == 3
    assert again.imported == 0
    assert again.duplicates == 3
    assert db.query(location.LocationPing).filter_by(account_id=driver.id).count() == 3


def test_an_unmapped_vehicle_is_skipped_and_COUNTED(db):
    """Never guessed. Attributing one driver's dwell to another driver's claim is the
    worst failure available here — and the count is what explains a connected fleet
    drafting no claims, so it is reported rather than logged and forgotten."""
    driver = _driver(db)
    connector = _connector(db)
    m14.map_vehicle(db, connector, "veh-1", driver.id)
    start = datetime.now(UTC) - timedelta(hours=1)

    result = m14.ingest_breadcrumbs(
        db,
        connector,
        _crumbs("veh-1", *DALLAS, start) + _crumbs("veh-UNKNOWN", *DALLAS, start),
    )
    assert result.imported == 3
    assert result.skipped_unmapped == 3
    assert result.unmapped_refs == {"veh-UNKNOWN"}
    assert db.query(location.LocationPing).filter_by(account_id=driver.id).count() == 3


def test_a_failing_provider_marks_the_connector_and_keeps_its_words(db):
    """`failing` is not `disabled`. Collapsing them would make a revoked key look like an
    operator's decision — the "never ran / switched off / failing" distinction §11.7
    already applies to the ops health panel."""

    class Boom:
        def vehicle_locations(self, since=None):
            raise RuntimeError("401 Unauthorized: API key revoked")

    connector = _connector(db)
    with pytest.raises(RuntimeError):
        m14.poll_connector(db, connector, client=Boom())

    assert connector.status is m14.ConnectorStatus.failing
    assert "revoked" in connector.health_detail
    assert connector.status is not m14.ConnectorStatus.disabled


def test_a_recovered_provider_clears_the_failure(db):
    connector = _connector(db)
    connector.status = m14.ConnectorStatus.failing
    connector.health_detail = "401 Unauthorized"
    db.flush()

    m14.poll_connector(db, connector, client=m14.FakeMotiveClient([[]]))
    assert connector.status is m14.ConnectorStatus.active
    assert connector.health_detail is None
    assert connector.last_sync_at is not None


# --- FR3: the evidence class is DERIVED --------------------------------------------


def test_evidence_class_is_derived_from_the_sources_not_asserted(db):
    """If a caller could pass the class in, the honest label would depend on the caller
    being right — and the one thing this module must never do is let a pack say
    `phone_verified` over provider timestamps."""
    assert m14.evidence_class_for(["device"]) is m14.EvidenceClass.phone_verified
    assert m14.evidence_class_for(["eld:motive"]) is m14.EvidenceClass.eld_derived
    assert m14.evidence_class_for(["device", "eld:motive"]) is m14.EvidenceClass.mixed
    # no trail at all is the conservative default: every pack before M14 was phone-based,
    # and a pack with no pings says so in its own "trail not available" branch
    assert m14.evidence_class_for([]) is m14.EvidenceClass.phone_verified
    assert m14.evidence_class_for(None) is m14.EvidenceClass.phone_verified


def test_the_provider_is_named_for_a_pack_that_must_name_it(db):
    assert m14.provider_names(["eld:motive", "device"]) == ["motive"]
    assert m14.provider_names(["device"]) == []


# --- the flag and the gates ---------------------------------------------------------


def test_the_flag_declares_nothing_and_lets_its_gates_govern(db):
    """§13.14: a capability that has never shipped declares nothing. `register_flag` has
    had no `enabled` parameter since audit F-02 — a flag born enabled never passes through
    `enable()`, which is the only function that reads a gate."""
    m14.register_module(db)
    flag = db.get(flags.FeatureFlag, m14.FLAG_KEY)
    assert flag.default_on is False
    assert flag.enabled is None  # NULL — no operator decision has been made
    assert flags.is_enabled(db, m14.FLAG_KEY) is False
    # and it cannot be switched on while its gates are unmet, which is the point of
    # declaring nothing: `enable()` is the only writer of `enabled` and the only reader
    # of the gates
    assert flags.can_activate(db, m14.FLAG_KEY) is False


def test_the_send_refuses_while_D13_is_unanswered(db):
    """The owner chose to BUILD the send path and gate it rather than leave it unwired, so
    that the day D13 lands the change is `satisfy_gate(...)` and not a deploy of code
    first exercised in production. It reads the GATE, not a constant, for that reason."""
    m14.register_module(db)
    allowed, blocker = m14.can_send(db)
    assert allowed is False
    assert blocker in m14.GATES

    # M3's own precondition is inherited on purpose: M14 must not launder the claims
    # pipeline past a gate M3 itself has not cleared
    assert "legal_signoff" in m14.GATES
    assert "carrier_invoicing_counsel" in m14.GATES


def test_satisfying_both_gates_is_what_lifts_the_send(db):
    m14.register_module(db)
    for name in m14.GATES:
        flags.satisfy_gate(db, flags.get_gate(db, m14.FLAG_KEY, name), note="test")
    allowed, blocker = m14.can_send(db)
    assert allowed is True
    assert blocker is None


def test_an_absent_gate_is_treated_as_unsatisfied(db):
    # "I could not find the precondition" must never read as "the precondition is met" —
    # audit F-02's exact shape
    allowed, blocker = m14.can_send(db)  # register_module deliberately NOT called
    assert allowed is False
    assert blocker == "legal_signoff"
