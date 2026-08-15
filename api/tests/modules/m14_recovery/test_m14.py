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


# --- FR4: draft, hold, approve ------------------------------------------------------


def _armed_stop(db, driver):
    """A stop armed through the EXISTING path — the same arming M3 rides."""
    from app.foundation.f02_facility import public as facility
    from app.foundation.f05_load import public as loads

    fac = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    load = loads.create_load(
        db,
        driver.id,
        reference_number="M14-T",
        free_time_minutes=60,
        detention_rate_cents_per_hour=7500,
    )
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery, sequence=1)
    loads.arm_stop(db, stop)
    db.flush()
    return fac, stop


def _drive_in(db, connector, driver, fac, *, hours_ago=3, now=None):
    """AI-CONTEXT: a REAL arrival, through the real ingest path — not a synthetic event.

    The first version of these tests hand-built an event object and set `claim.clock_since`,
    and nothing drafted. `m3.clock` derives arrival from GEOFENCE PRESENCE, so a claim with
    no presence behind it is forever `within_free_time` no matter what its columns say. A
    test that fabricates the appearance of an arrival is the shape HANDOFF-122 §5 catalogues
    — *the test arranged the appearance of the condition rather than the condition* — so
    these breadcrumbs walk the truck in for real and let F3 decide.
    """
    from app.foundation.f02_facility import public as facility

    now = now or datetime.now(UTC)
    lat, lon = facility.coordinates(db, fac)
    arrived = now - timedelta(hours=hours_ago)
    crumbs = [
        m14.Breadcrumb("veh-1", lat + 0.01, lon, arrived - timedelta(minutes=5), speed_mps=20.0),
        m14.Breadcrumb("veh-1", lat, lon, arrived, speed_mps=0.0),
        m14.Breadcrumb("veh-1", lat, lon, now - timedelta(minutes=1), speed_mps=0.0),
    ]
    return m14.ingest_breadcrumbs(db, connector, crumbs, now=now)


def test_dwell_past_free_time_drafts_a_HELD_claim(db):
    """The claim is an ORDINARY m03 claim; the hold is M14's own record that nobody has
    approved it. M14 does not fork M3 and does not extend its state machine."""
    from app.modules.m03_detention import public as m3

    driver = _driver(db)
    connector = _connector(db)
    m14.map_vehicle(db, connector, "veh-1", driver.id)
    fac, _stop = _armed_stop(db, driver)
    now = datetime.now(UTC)

    result = _drive_in(db, connector, driver, fac, now=now)
    drafted = m14.draft_holds_for_events(db, connector, result.events, now=now)

    assert len(drafted) == 1
    held = drafted[0]
    assert held.state is m14.HoldState.held
    # the claim itself is untouched M3 — still `open`, not some M14 state
    assert m3.get_claim(db, held.claim_ref).state is m3.ClaimState.open
    # and it is labelled from the SOURCES that actually back it
    assert held.evidence_class == m14.EvidenceClass.eld_derived.value


def test_a_second_poll_does_not_queue_the_same_claim_twice(db):
    """A fleet admin shown one detention twice approves it twice, and `generate_pack`'s
    state guard is the only thing between that and two invoices to one broker."""
    driver = _driver(db)
    connector = _connector(db)
    m14.map_vehicle(db, connector, "veh-1", driver.id)
    fac, _stop = _armed_stop(db, driver)
    now = datetime.now(UTC)

    result = _drive_in(db, connector, driver, fac, now=now)
    first = m14.draft_holds_for_events(db, connector, result.events, now=now)
    second = m14.draft_holds_for_events(db, connector, result.events, now=now)

    assert len(first) == 1
    assert second == []
    assert len(m14.held_claims(db, connector.fleet_id)) == 1


def test_nothing_is_drafted_while_still_inside_free_time(db):
    """A claim queued for a stop that never ran long puts a $0 invoice in front of a
    fleet admin."""
    driver = _driver(db)
    connector = _connector(db)
    m14.map_vehicle(db, connector, "veh-1", driver.id)
    fac, _stop = _armed_stop(db, driver)
    now = datetime.now(UTC)

    # arrived five minutes ago against sixty minutes of free time
    result = _drive_in(db, connector, driver, fac, hours_ago=0.08, now=now)
    drafted = m14.draft_holds_for_events(db, connector, result.events, now=now)
    assert drafted == []


def test_an_event_at_a_DIFFERENT_facility_is_not_this_stops_arrival(db):
    from app.foundation.f02_facility import public as facility

    driver = _driver(db)
    connector = _connector(db)
    m14.map_vehicle(db, connector, "veh-1", driver.id)
    _fac, _stop = _armed_stop(db, driver)
    elsewhere = facility.create_facility(
        db, facility.FacilityType.truck_stop, "Somewhere else", 30.0, -90.0
    )

    class _E:
        account_id = driver.id
        facility_id = elsewhere.id

    assert m14.draft_holds_for_events(db, connector, [_E()]) == []


# --- approve, and the gate that holds the send --------------------------------------


def _held(db, driver, connector):
    m14.map_vehicle(db, connector, "veh-1", driver.id)
    fac, _stop = _armed_stop(db, driver)
    now = datetime.now(UTC)
    result = _drive_in(db, connector, driver, fac, now=now)
    return m14.draft_holds_for_events(db, connector, result.events, now=now)[0]


def test_approving_records_the_decision_and_REFUSES_the_send_while_D13_is_open(db):
    """The two facts are kept apart because collapsing them is F-01 exactly: F8 wrote
    `sent_at` for notices that reached a container, and everything downstream believed
    them. An approved-but-blocked claim says so, and names the gate."""
    m14.register_module(db)
    driver = _driver(db)
    connector = _connector(db)
    held = _held(db, driver, connector)

    m14.approve(db, held, driver.id)

    assert held.state is m14.HoldState.approved  # a human genuinely decided
    assert held.state is not m14.HoldState.sent  # and it genuinely did not go
    assert held.send_blocked_by in m14.GATES
    assert held.decided_by == driver.id
    assert held.decided_at is not None


def test_the_send_runs_once_both_gates_are_satisfied(db):
    """The point of gating in code rather than leaving the path unwired: the day D13
    lands, the change is `satisfy_gate(...)` and not a deploy of code first exercised in
    production."""
    from app.foundation.f08_notifications import public as notify

    m14.register_module(db)
    for name in m14.GATES:
        flags.satisfy_gate(db, flags.get_gate(db, m14.FLAG_KEY, name), note="test")
    driver = _driver(db)
    connector = _connector(db)
    held = _held(db, driver, connector)

    m14.approve(db, held, driver.id, gateway=notify.RecordingNotificationGateway())

    assert held.state is m14.HoldState.sent
    assert held.send_blocked_by is None


def test_a_hold_cannot_be_decided_twice(db):
    m14.register_module(db)
    driver = _driver(db)
    connector = _connector(db)
    held = _held(db, driver, connector)

    m14.approve(db, held, driver.id)
    with pytest.raises(m14.NotHeld):
        m14.approve(db, held, driver.id)
    with pytest.raises(m14.NotHeld):
        m14.reject(db, held, driver.id)


def test_rejecting_records_the_decision_and_sends_nothing(db):
    m14.register_module(db)
    driver = _driver(db)
    connector = _connector(db)
    held = _held(db, driver, connector)

    m14.reject(db, held, driver.id)
    assert held.state is m14.HoldState.rejected
    assert held.decided_by == driver.id
    # and it leaves the queue
    assert m14.held_claims(db, connector.fleet_id) == []


# --- FR3 wiring: the pack must be LABELLED from what actually backs it ---------------


def test_a_pack_backed_by_ELD_pings_is_labelled_eld_derived(db):
    """AI-CONTEXT: THE WIRE, not the wording. A sabotage pass made M3's derivation return
    `phone_verified` for every pack and the entire suite stayed green — the wording
    function was covered, the derivation was covered, and nothing asserted that one
    reached the other. That is the "built and reached by nothing" shape one layer up.

    A pack labelled `phone_verified` over provider timestamps tells a broker a driver's
    device recorded something a telematics API recorded. It is the worst artifact this
    module can produce, so the wire has a test.
    """
    from app.modules.m03_detention.domain import service as m3_service

    driver = _driver(db)
    connector = _connector(db)
    m14.map_vehicle(db, connector, "veh-1", driver.id)
    fac, _stop = _armed_stop(db, driver)
    now = datetime.now(UTC)
    result = _drive_in(db, connector, driver, fac, now=now)
    held = m14.draft_holds_for_events(db, connector, result.events, now=now)[0]

    from app.modules.m03_detention import public as m3

    claim = m3.get_claim(db, held.claim_ref)
    context = m3_service.pack_context_for(db, claim)

    assert context.evidence_class == m14.EvidenceClass.eld_derived.value
    assert context.evidence_providers == ["motive"]

    # and the sentence that reaches the broker follows from it
    from app.foundation.f04_evidence.domain import render

    text = render.location_basis_text(context)
    assert "Motive" in text
    assert "as reported by the driver's device" not in text
