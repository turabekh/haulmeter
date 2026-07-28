from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
from app.foundation.f08_notifications import public as notify
from app.modules.m03_detention import public as m3

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


# --- the money core: pure clock math ---
def test_within_free_time_counts_down():
    s = m3.compute_detention(T0, 120, 7500, now=T0 + timedelta(minutes=60))
    assert s.phase == m3.DetentionPhase.within_free_time
    assert s.free_time_remaining_seconds == 3600
    assert s.amount_cents == 0


def test_accruing_after_free_time():
    s = m3.compute_detention(T0, 120, 7500, now=T0 + timedelta(minutes=180))
    assert s.phase == m3.DetentionPhase.accruing
    assert s.detention_seconds == 3600
    assert s.amount_cents == 7500  # 1h * $75


def test_ended_computes_total():
    s = m3.compute_detention(
        T0, 120, 7500, now=T0 + timedelta(hours=6), departed_at=T0 + timedelta(minutes=240)
    )
    assert s.phase == m3.DetentionPhase.ended
    assert s.amount_cents == 15000  # 2h * $75


def _setup(db, authority=identity.AuthorityType.own_mc, email="oo@example.com"):
    account = identity.register_account(db, email, "pw-123456")
    identity.upsert_driver_profile(db, account, authority_type=authority)
    receiver = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    broker = loads.create_counterparty(
        db, "Acme", loads.CounterpartyKind.broker, contact_email="ap@acme.com"
    )
    load = loads.create_load(
        db,
        account.id,
        counterparty_id=broker.id,
        detention_rate_cents_per_hour=7500,
        free_time_minutes=120,
    )
    stop = loads.add_stop(db, load, receiver.id, loads.StopType.delivery, appointment_start=T0)
    return account, broker, load, stop


def _arrive_and_leave(db, account, arrival, departure):
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=arrival)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=departure)


def test_start_claim_arms_and_sets_invoice_mode(db):
    account, broker, load, stop = _setup(db)
    claim = m3.start_claim(db, stop, started_at=T0)
    assert stop.geofence_armed is True
    assert claim.mode == m3.ClaimMode.invoice  # own authority can invoice
    assert claim.evidence_log_ref is not None


def test_company_driver_is_evidence_only(db):
    account, broker, load, stop = _setup(db, authority=identity.AuthorityType.company)
    claim = m3.start_claim(db, stop, started_at=T0)
    assert claim.mode == m3.ClaimMode.evidence_only


def test_accrue_events_is_idempotent_and_chain_valid(db):
    account, broker, load, stop = _setup(db)
    claim = m3.start_claim(db, stop, started_at=T0)
    _arrive_and_leave(db, account, T0, T0 + timedelta(minutes=240))
    assert m3.accrue_events(db, claim) == 2  # ENTER + EXIT
    assert m3.accrue_events(db, claim) == 0  # idempotent
    from app.foundation.f04_evidence import public as evidence

    log = db.get(evidence.EvidenceLog, claim.evidence_log_ref)
    assert evidence.verify_chain(db, log).valid is True


def test_generate_pack_invoice_opens_receivable_and_notifies(db):
    account, broker, load, stop = _setup(db)
    claim = m3.start_claim(db, stop, started_at=T0)
    _arrive_and_leave(db, account, T0, T0 + timedelta(minutes=240))
    gateway = notify.RecordingNotificationGateway()

    result = m3.generate_pack(db, claim, now=T0 + timedelta(minutes=240), gateway=gateway)
    assert result["pack"].verification["chain_valid"] is True
    assert claim.amount_cents == 15000
    assert claim.state == m3.ClaimState.invoiced

    receivable = result["receivable"]
    assert receivable.state == ledger.ReceivableState.invoiced
    assert receivable.amount_cents == 15000
    db.refresh(broker)
    assert broker.claim_count == 1
    assert gateway.sent[0].channel == "email"


def test_generate_pack_company_mode_no_invoice(db):
    account, broker, load, stop = _setup(db, authority=identity.AuthorityType.company)
    claim = m3.start_claim(db, stop, started_at=T0)
    _arrive_and_leave(db, account, T0, T0 + timedelta(minutes=240))
    result = m3.generate_pack(db, claim, now=T0 + timedelta(minutes=240))
    assert result["receivable"] is None
    assert claim.state == m3.ClaimState.exported
    assert result["pack"].verification["chain_valid"] is True


def test_pre_detention_notice_within_threshold(db):
    account, broker, load, stop = _setup(db)
    claim = m3.start_claim(db, stop, started_at=T0)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)  # arrival
    gateway = notify.RecordingNotificationGateway()
    # 100 min after arrival: 20 min of free time left (< 30 min threshold)
    msg = m3.send_pre_detention_notice(db, claim, gateway, now=T0 + timedelta(minutes=100))
    assert msg is not None
    # 30 min after arrival: 90 min left -> no notice
    assert m3.send_pre_detention_notice(db, claim, gateway, now=T0 + timedelta(minutes=30)) is None


def test_dunning_schedule(db):
    schedule = m3.dunning_schedule(T0)
    assert [s["day"] for s in schedule] == [3, 10, 21]
    assert schedule[0]["action"] == "nudge"
    assert schedule[2]["at"] == T0 + timedelta(days=21)


def test_flag_gated_on_activation_preconditions(db):
    from app.foundation.f13_flags import public as flags

    m3.register_module(db)
    assert flags.can_activate(db, "m03_detention") is False  # legal + partner gates unmet
    with pytest.raises(flags.GateNotSatisfied):
        flags.enable(db, "m03_detention")


def test_the_invoice_reproduces_from_the_figures_printed_on_it():
    """Found by reading a claim screen: "0:00:38 · $120/h · $1.29", where 38 seconds
    at $120/h is $1.27. The amount was rounded off the float behind the clock (38.7s)
    while the time was truncated to the second — so the two figures on the face of the
    invoice did not agree.

    A claim is a document a third party verifies, and the clerk checking it does the
    only arithmetic available to them: the time and the rate printed on it. The gap is
    pennies; the credibility cost is not."""
    from datetime import UTC, datetime, timedelta

    from app.modules.m03_detention.domain.service import compute_detention

    arrived = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
    # 38.7s past free time — the fractional case the screen exposed
    state = compute_detention(
        arrived, 1, 12000, arrived + timedelta(minutes=1, seconds=38, milliseconds=700)
    )

    assert state.detention_seconds == 38
    assert state.amount_cents == round(38 / 3600 * 12000)  # 127, not 129
    # and the reader's own arithmetic lands on the same number
    assert state.amount_cents == 127


# --- the visit, not the facility's history (§23 entry 73) ---
def test_an_earlier_visit_to_the_same_dock_does_not_start_this_claim(db):
    """The money defect, reproduced.

    The clock replayed EVERY geofence event ever recorded for the account at this
    facility and took the earliest ENTER. A driver returning to a dock they had
    visited before therefore billed from the FIRST visit. Measured on a real
    two-stop load: a delivery the driver stood at for 53 seconds billed 2h20m —
    $187.76 against $0.00 owed."""
    account, broker, load, stop = _setup(db)

    # yesterday's load to the same dock: armed, arrived, left, disarmed. Events only
    # exist while a geofence is armed, so this has to be a real prior load — an
    # unarmed "visit" records nothing and would prove the opposite of the point.
    yesterday = T0 - timedelta(days=1)
    location.arm_geofence(db, account.id, stop.facility_id)
    _arrive_and_leave(db, account, yesterday, yesterday + timedelta(hours=4))
    location.disarm_geofence(db, account.id, stop.facility_id, yesterday + timedelta(hours=4))

    # today's visit: 30 minutes, well inside the 2h free time
    claim = m3.start_claim(db, stop, started_at=T0)
    _arrive_and_leave(db, account, T0 + timedelta(minutes=5), T0 + timedelta(minutes=35))

    state = m3.clock(db, claim, now=T0 + timedelta(minutes=40))
    assert state.detention_seconds == 0
    assert state.amount_cents == 0


def test_departure_is_this_visits_exit_not_the_latest_ever(db):
    """`departure` took the LAST EXIT on file, which need not belong to this visit —
    and a departure lifted from a later visit runs the clock through the gap between
    them, billing for hours the truck spent somewhere else entirely."""
    account, broker, load, stop = _setup(db)
    claim = m3.start_claim(db, stop, started_at=T0)

    # this visit: arrive, wait 3h (1h past free time), leave
    _arrive_and_leave(db, account, T0, T0 + timedelta(hours=3))
    # and a later, unrelated visit to the same dock
    _arrive_and_leave(db, account, T0 + timedelta(days=2), T0 + timedelta(days=2, hours=1))

    state = m3.clock(db, claim, now=T0 + timedelta(days=3))
    assert state.detention_seconds == 3600
    assert state.amount_cents == 7500  # 1h @ $75 — not two days of it


def test_a_driver_already_at_the_dock_keeps_their_real_arrival(db):
    """Scoping the clock to the claim must not clip a visit that was already under
    way. The driver who is standing at the dock when the claim starts arrived
    BEFORE it — and that earlier moment is the honest one to bill from."""
    account, broker, load, stop = _setup(db)

    loads.arm_stop(db, stop)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)  # already inside
    claim = m3.start_claim(db, stop, started_at=T0 + timedelta(minutes=10))
    location.evaluate_ping(db, account.id, *FAR, occurred_at=T0 + timedelta(hours=3))

    state = m3.clock(db, claim, now=T0 + timedelta(hours=4))
    # billed from T0, the real arrival, not from the claim's own start
    assert state.detention_seconds == 3600
    assert state.amount_cents == 7500


def test_only_this_visits_events_reach_the_stops_chain(db):
    """The pack a broker reads must describe THIS stop.

    `accrue_events` made the same unscoped read as the clock did, three lines above
    it, and was missed while that one was fixed — so every geofence event ever
    recorded at the dock was filed into this stop's hash-chained log. Seen in a real
    pack: four ENTER records for a stop the driver arrived at once."""
    from app.foundation.f04_evidence import public as evidence

    account, broker, load, stop = _setup(db)

    # a previous load to the same dock
    yesterday = T0 - timedelta(days=1)
    location.arm_geofence(db, account.id, stop.facility_id)
    _arrive_and_leave(db, account, yesterday, yesterday + timedelta(hours=4))
    location.disarm_geofence(db, account.id, stop.facility_id, yesterday + timedelta(hours=4))

    claim = m3.start_claim(db, stop, started_at=T0)
    _arrive_and_leave(db, account, T0 + timedelta(minutes=5), T0 + timedelta(hours=3))

    assert m3.accrue_events(db, claim) == 2  # this visit's ENTER + EXIT, and no others

    log = db.get(evidence.EvidenceLog, claim.evidence_log_ref)
    geofenced = [r for r in log.records if (r.payload or {}).get("event") in ("ENTER", "EXIT")]
    assert len(geofenced) == 2
    assert all(r.occurred_at >= T0 for r in geofenced)
