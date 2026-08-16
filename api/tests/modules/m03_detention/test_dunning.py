"""Finding F6 — M3-FR6's follow-up cadence, which had never run.

`dunning_schedule` computed day 3 / 10 / 21 correctly and had exactly one caller in the
tree: its own unit test. So the arithmetic was right, the tests were green, and no broker
had ever been chased. The FIRST test here is the wiring one, deliberately — a job that
exists and is not scheduled is this same bug wearing a different hat.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
from app.foundation.f08_notifications import public as notify
from app.foundation.f13_flags import public as flags
from app.modules.m03_detention import public as m3

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
FILED = T0 + timedelta(minutes=240)


# --- the wiring, first ---
def test_the_dunning_job_is_actually_scheduled():
    """MANDATORY. F6 is not "the cadence was wrong", it is "nothing ever called it"."""
    from app.worker import _jobs

    jobs = {job.name: job for job in _jobs()}

    assert "dunning" in jobs, "the dunning job exists but nothing schedules it — F6 reborn"
    assert jobs["dunning"].run is not None
    assert jobs["dunning"].flag_key == m3.FLAG_KEY  # behind M3's own activation flag
    assert jobs["dunning"].interval_seconds == 86400


def _invoiced(db, email="ap@acme.com", invoiced_at=FILED, amount_email=True):
    account = identity.register_account(db, f"oo-{invoiced_at.isoformat()}@example.com", "pw-12345")
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    broker = loads.create_counterparty(
        db, "Acme", loads.CounterpartyKind.broker,
        contact_email=email if amount_email else None,
    )
    load = loads.create_load(
        db, account.id, counterparty_id=broker.id, reference_number="BL-77",
        detention_rate_cents_per_hour=7500, free_time_minutes=120,
    )
    stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery, appointment_start=T0)
    claim = m3.start_claim(db, stop, started_at=T0)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=FILED)
    result = m3.generate_pack(db, claim, now=FILED)
    # `created_at` is `now()` — transaction time — so the schedule is anchored to whatever
    # instant the test transaction opened at. Set it explicitly, or "day 3" is unreadable.
    result["receivable"].created_at = invoiced_at
    db.flush()
    return account, claim, result["receivable"]


def _register_gates(db):
    """Unit tests do not boot the app, so M3's flag and gates are not registered."""
    flags.register_flag(db, m3.FLAG_KEY, description="M3", default_on=True)
    for gate in m3.GATES:
        flags.add_gate(db, m3.FLAG_KEY, gate)


def _satisfy_escalation_gate(db):
    _register_gates(db)
    flags.satisfy_gate(db, flags.get_gate(db, m3.FLAG_KEY, m3.ESCALATION_GATE), note="test")


# --- the cadence ---
def test_a_nudge_goes_out_on_day_three_and_only_once(db):
    _, claim, _ = _invoiced(db)
    gateway = notify.RecordingNotificationGateway()
    day3 = FILED + timedelta(days=3, hours=1)

    first = m3.run_dunning(db, gateway, now=day3)
    second = m3.run_dunning(db, gateway, now=day3 + timedelta(hours=2))

    assert first["nudged"] == 1
    assert claim.dunning_nudge_sent_at is not None
    assert second["nudged"] == 0  # the column is the once-only record
    # delivery is the `outbound_mail` sweep's job now, not the request path's
    notify.retry_unsent_messages(db, gateway)
    assert len(gateway.sent) == 1


def test_nothing_goes_out_before_day_three(db):
    _, claim, _ = _invoiced(db)
    gateway = notify.RecordingNotificationGateway()

    summary = m3.run_dunning(db, gateway, now=FILED + timedelta(days=2))

    assert summary["nudged"] == 0
    assert gateway.sent == []
    assert claim.dunning_nudge_sent_at is None


def test_each_action_has_its_own_subject_and_its_own_column(db):
    _, claim, _ = _invoiced(db)
    gateway = notify.RecordingNotificationGateway()

    m3.run_dunning(db, gateway, now=FILED + timedelta(days=3, hours=1))
    m3.run_dunning(db, gateway, now=FILED + timedelta(days=10, hours=1))
    m3.run_dunning(db, gateway, now=FILED + timedelta(days=21, hours=1))

    assert claim.dunning_nudge_sent_at is not None
    assert claim.dunning_firm_sent_at is not None
    assert claim.dunning_final_notice_sent_at is not None
    # delivery is the `outbound_mail` sweep's job now, not the request path's
    notify.retry_unsent_messages(db, gateway)
    assert len(gateway.sent) == 3
    subjects = {m3.DUNNING_SUBJECT[a] for a in m3.DUNNING_ACTIONS}
    assert len(subjects) == 3  # distinct and greppable


# --- the three bounds ---
def test_switching_this_on_over_a_backlog_does_not_spray_the_missed_ones(db):
    """The first run of a job like this meets a backlog, not a steady state.

    Day 25 on a claim nobody has ever chased: the day-3 nudge is 22 days late and the
    day-10 firm is 15, both far outside the grace window, so neither is sent. The day-21
    final notice is 4 days late — inside it — so that one, and only that one, goes out.
    The broker gets the follow-up that is still current instead of three at once.
    """
    _, claim, _ = _invoiced(db)
    gateway = notify.RecordingNotificationGateway()

    summary = m3.run_dunning(db, gateway, now=FILED + timedelta(days=25))

    assert summary["skipped_stale"] == 2
    assert summary["nudged"] == 0 and summary["firmed"] == 0
    # delivery is the `outbound_mail` sweep's job now, not the request path's
    notify.retry_unsent_messages(db, gateway)
    assert len(gateway.sent) == 1
    assert gateway.sent[0].subject == m3.DUNNING_SUBJECT["final_notice"]
    # not suppressed — a stale action never had a send to make, so nothing is recorded
    assert claim.dunning_nudge_sent_at is None
    assert claim.dunning_firm_sent_at is None


def test_the_scan_window_gives_every_action_its_full_grace_and_no_more(db):
    """28 = 21 + 7 by construction, and the two numbers must stay in that relationship.

    If the window were shorter than the last action's day plus its grace, the escalation
    offer could fall out of the scan set while still current — a follow-up that silently
    never sends, which is the shape of F6 itself.
    """
    assert m3.DUNNING_WINDOW == timedelta(days=max(m3.DUNNING_DAYS)) + m3.DUNNING_GRACE


def test_a_receivable_older_than_the_scan_window_is_not_scanned_at_all(db):
    _, _, _ = _invoiced(db, invoiced_at=FILED - timedelta(days=40))
    gateway = notify.RecordingNotificationGateway()

    summary = m3.run_dunning(db, gateway, now=FILED)

    assert summary["scanned"] == 0
    assert gateway.sent == []


def test_day_twenty_one_sends_the_firm_follow_up_with_no_partner_agreement(db):
    """R2. The escalation offer this replaces was gated on `collection_partner_agreement`,
    that gate has been unsatisfied since 0066, and the rung it guarded was never built —
    so what day 21 DID, on every claim that ever reached it, was nothing. A broker who
    ignored day 3 and day 10 heard nothing further, ever.

    The gate was right; the silence was the defect. Day 21 now says the strongest TRUE
    thing available, which is what the rate confirmation already obliges.
    """
    _, claim, _ = _invoiced(db)
    _register_gates(db)  # registered, and deliberately NOT satisfied
    gateway = notify.RecordingNotificationGateway()

    m3.run_dunning(db, gateway, now=FILED + timedelta(days=3, hours=1))
    m3.run_dunning(db, gateway, now=FILED + timedelta(days=10, hours=1))
    summary = m3.run_dunning(db, gateway, now=FILED + timedelta(days=21, hours=1))

    assert summary["final_notice"] == 1
    assert claim.dunning_final_notice_sent_at is not None
    assert claim.dunning_nudge_sent_at is not None
    assert claim.dunning_firm_sent_at is not None


def test_the_partner_gate_still_exists_and_is_still_unsatisfied(db):
    """Retiring the SEND that consulted it must not quietly retire the gate. It is what a
    future escalation rung has to satisfy; nothing about that changed."""
    from app.foundation.f13_flags import public as flags

    _register_gates(db)

    gate = flags.get_gate(db, m3.FLAG_KEY, "collection_partner_agreement")
    assert gate is not None
    assert gate.satisfied is False


def test_no_message_at_any_rung_offers_collection(db):
    """R2's template-level assertion, made against the RENDERED output rather than the
    source: a subject or body that offers to hand the claim to a collection partner would
    be promising a path this product does not have. Checked at every rung, because the
    wording only had to survive in one of them to reach a broker.
    """
    _, _, _ = _invoiced(db)
    gateway = notify.RecordingNotificationGateway()
    for day in (3, 10, 21):
        m3.run_dunning(db, gateway, now=FILED + timedelta(days=day, hours=1))
    notify.retry_unsent_messages(db, gateway)

    assert len(gateway.sent) == 3
    for message in gateway.sent:
        blob = f"{message.subject} {message.body}".lower()
        for banned in ("collection", "collections", "escalat", "debt", "agency"):
            assert banned not in blob, f"{banned!r} reached a broker in: {message.subject}"


def test_the_final_notice_cites_the_contract_rather_than_a_threat(db):
    """Firmer means citing what they already agreed to. The strongest honest lever this
    product holds is the rate confirmation itself."""
    _, _, _ = _invoiced(db)
    gateway = notify.RecordingNotificationGateway()
    for day in (3, 10, 21):
        m3.run_dunning(db, gateway, now=FILED + timedelta(days=day, hours=1))
    notify.retry_unsent_messages(db, gateway)

    final = [m for m in gateway.sent if m.subject == m3.DUNNING_SUBJECT["final_notice"]][0]
    assert "rate confirmation" in final.body.lower()
    assert "previous two messages" in final.body.lower()
    # and it is genuinely different from the earlier rungs rather than a relabelled repeat
    earlier = [m for m in gateway.sent if m.subject != m3.DUNNING_SUBJECT["final_notice"]]
    assert all(m.body != final.body for m in earlier)


# --- who is left out ---
def test_a_claim_with_no_broker_email_is_skipped_never_faked(db):
    _, claim, _ = _invoiced(db, amount_email=False)
    gateway = notify.RecordingNotificationGateway()

    summary = m3.run_dunning(db, gateway, now=FILED + timedelta(days=3, hours=1))

    assert summary["skipped_no_email"] == 1
    assert gateway.sent == []
    assert claim.dunning_nudge_sent_at is None


def test_a_paid_receivable_is_not_chased(db):
    account, claim, receivable = _invoiced(db)
    ledger.transition_receivable(db, receivable, ledger.ReceivableState.recovered)
    gateway = notify.RecordingNotificationGateway()

    summary = m3.run_dunning(db, gateway, now=FILED + timedelta(days=3, hours=1))

    assert summary["scanned"] == 0
    assert gateway.sent == []


# --- the notice itself ---
def test_each_notice_stands_on_its_own(db):
    """It must never presume an earlier email arrived — that is why it is being sent."""
    _, claim, _ = _invoiced(db)
    gateway = notify.RecordingNotificationGateway()

    m3.run_dunning(db, gateway, now=FILED + timedelta(days=3, hours=1))
    # delivery is the `outbound_mail` sweep's job now, not the request path's
    notify.retry_unsent_messages(db, gateway)
    body = gateway.sent[0].body

    assert "$150.00" in body  # the amount
    assert "BL-77" in body  # the reference an AP clerk files by
    assert "2026-07-20" in body  # the service date
    assert "evidence" in body.lower()  # and where the proof is


# --- the escalation seam (F6's other half) ---
def test_escalate_keeps_the_partner_reference_it_used_to_discard(db):
    _, claim, _ = _invoiced(db)

    m3.escalate(db, claim, external_ref="PARTNER-4471")

    assert claim.state == m3.ClaimState.escalated
    assert claim.escalation_ref == "PARTNER-4471"


def test_escalating_again_without_a_ref_does_not_erase_the_one_on_file(db):
    _, claim, _ = _invoiced(db)
    m3.escalate(db, claim, external_ref="PARTNER-4471")

    m3.escalate(db, claim)

    assert claim.escalation_ref == "PARTNER-4471"
