"""AI-CONTEXT: what a driver needs to ACT on money they are owed (§23 entry 142).

The Money tab listed "Detention · Invoiced · $187.50 · 12d". It could not say who was
sitting on it, where it came from, or whether anyone had chased it — so the one screen in
this product about being paid named neither the person who had not paid nor what had
already been tried. That is the whole difference between "wait" and "do something".

The chasers were the sharpest part: `run_dunning` records each one as a timestamp on the
claim, and until this those columns were read by NOTHING but the job that writes them.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
from app.modules.m03_detention import public as m3
from app.modules.m04_accessorial import public as m4

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
FILED = T0 + timedelta(minutes=240)


def _invoiced_detention(db, dock_name="Dallas Cold Storage", broker="Acme Brokerage"):
    """A detention claim with real money on it, so a receivable actually opens."""
    account = identity.register_account(db, "oo-owed@example.com", "pw-12345")
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, dock_name, *DALLAS)
    cp = loads.create_counterparty(
        db, broker, loads.CounterpartyKind.broker, contact_email="ap@acme.com"
    )
    load = loads.create_load(
        db, account.id, counterparty_id=cp.id, reference_number="BL-77",
        detention_rate_cents_per_hour=7500, free_time_minutes=120,
    )
    stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery, appointment_start=T0)
    claim = m3.start_claim(db, stop, started_at=T0)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=FILED)
    result = m3.generate_pack(db, claim, now=FILED)
    # `created_at` is `now()` — TRANSACTION time — so without this the invoice is stamped
    # today and lands AFTER chasers dated last month, which is the dunning fixture's own
    # warning. In production the invoice always precedes its chasers; anchoring it here
    # is what makes this test measure the ordering rather than the clock.
    result["receivable"].created_at = FILED
    db.flush()
    return account, claim, result["receivable"]


def test_the_row_names_who_owes_it_and_which_dock(db):
    account, _, receivable = _invoiced_detention(db)
    assert receivable is not None, "the fixture produced no receivable to report on"

    row = next(r for r in m4.money_owed(db, account.id) if r["kind"] == "detention")

    assert row["counterparty_name"] == "Acme Brokerage"
    assert row["facility_name"] == "Dallas Cold Storage"


def test_the_row_carries_the_chasers_that_actually_went_out(db):
    """`run_dunning` sets these at dispatch. Reading them is what lets a driver tell a
    claim chased twice from one nobody has touched."""
    account, claim, _ = _invoiced_detention(db)
    claim.dunning_nudge_sent_at = FILED + timedelta(days=3)
    claim.dunning_firm_sent_at = FILED + timedelta(days=10)
    db.flush()

    row = next(r for r in m4.money_owed(db, account.id) if r["kind"] == "detention")

    assert [e["event"] for e in row["history"]] == ["invoiced", "nudged", "firmed"]
    assert [e["at"] for e in row["history"]] == sorted(e["at"] for e in row["history"])


def test_a_claim_nobody_chased_INVENTS_NOTHING(db):
    """Absent columns mean absent chasers. A history that padded itself would tell a
    driver their claim was being worked while it sat still — the worst available lie on
    a screen about getting paid (§11.7)."""
    account, _, _ = _invoiced_detention(db)

    row = next(r for r in m4.money_owed(db, account.id) if r["kind"] == "detention")

    assert [e["event"] for e in row["history"]] == ["invoiced"]


def test_a_receivable_with_no_counterparty_reports_NONE_rather_than_a_guess(db):
    """HANDOFF-122 §3's shape, one table over: a name invented to fill a hole is worse
    than the hole, because a driver would chase the wrong company."""
    account = identity.register_account(db, "solo@example.com", "pw-12345")
    ledger.create_receivable(db, account.id, ledger.ReceivableKind.layover, 5000)
    db.flush()

    row = m4.money_owed(db, account.id)[0]

    assert row["counterparty_name"] is None
    assert row["facility_name"] is None
    assert [e["event"] for e in row["history"]] == ["invoiced"]
