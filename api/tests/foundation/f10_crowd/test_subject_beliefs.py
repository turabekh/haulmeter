"""AI-CONTEXT: F10 subject-scoped beliefs (added for M13-FR4).

A belief was keyed (facility, signal). That is right for a facility-wide reading —
how full is this lot, what does diesel cost here — and wrong the moment a signal is
about something INSIDE the facility: two cooks at one truck stop would tally against
each other over a single row.

`subject_ref` names the subject. These tests defend both halves of the change: the
new scoping works, and every pre-existing facility-wide signal behaves EXACTLY as
before (it passes the empty subject, and one belief per facility+signal still holds).
"""

from datetime import UTC, datetime

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f10_crowd import public as crowd

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)


def _account(db, email):
    return identity.register_account(db, email, "pw-123456")


def _facility(db, name="Loves 212"):
    return facility.create_facility(db, facility.FacilityType.truck_stop, name, *DALLAS)


def _present(db, account, fac):
    location.arm_geofence(db, account.id, fac.id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)


def test_two_subjects_at_one_facility_do_not_collide(db):
    # the defect this column exists to prevent: "vendor A is here" and "vendor B is
    # not" must be two separate truths about the same lot, not one contested row
    fac = _facility(db)
    a, b = _account(db, "a@x.com"), _account(db, "b@x.com")
    _present(db, a, fac)
    _present(db, b, fac)

    crowd.submit(
        db,
        a.id,
        fac.id,
        crowd.SignalType.vendor_present,
        {"present": True},
        T0,
        subject_ref="vendor-1",
    )
    crowd.submit(
        db,
        b.id,
        fac.id,
        crowd.SignalType.vendor_present,
        {"present": False},
        T0,
        subject_ref="vendor-2",
    )
    crowd.update_belief(db, fac.id, crowd.SignalType.vendor_present, T0, subject_ref="vendor-1")
    crowd.update_belief(db, fac.id, crowd.SignalType.vendor_present, T0, subject_ref="vendor-2")

    one = crowd.get_belief(db, fac.id, crowd.SignalType.vendor_present, subject_ref="vendor-1")
    two = crowd.get_belief(db, fac.id, crowd.SignalType.vendor_present, subject_ref="vendor-2")
    assert one.value == {"present": True} and one.sample_size == 1
    assert two.value == {"present": False} and two.sample_size == 1


def test_distinct_driver_counting_still_applies_per_subject(db):
    # the standard pipeline is unchanged — one contributor contributes once, and the
    # same driver re-reporting cannot inflate "N drivers" for that vendor
    fac = _facility(db)
    a, b = _account(db, "c@x.com"), _account(db, "d@x.com")
    for driver in (a, b):
        _present(db, driver, fac)
        crowd.submit(
            db,
            driver.id,
            fac.id,
            crowd.SignalType.vendor_present,
            {"present": True},
            T0,
            subject_ref="v9",
        )
    crowd.submit(
        db, a.id, fac.id, crowd.SignalType.vendor_present, {"present": True}, T0, subject_ref="v9"
    )

    belief = crowd.update_belief(db, fac.id, crowd.SignalType.vendor_present, T0, subject_ref="v9")
    assert belief.sample_size == 2  # two distinct drivers, not three submissions


def test_facility_wide_signals_are_untouched(db):
    # regression guard: parking has no subject, so it must aggregate exactly as it
    # always has and land on the empty-subject belief
    fac = _facility(db, "Rest Area")
    driver = _account(db, "e@x.com")
    _present(db, driver, fac)
    crowd.submit(db, driver.id, fac.id, crowd.SignalType.parking_fullness, {"status": "some"}, T0)
    belief = crowd.update_belief(db, fac.id, crowd.SignalType.parking_fullness, T0)

    assert belief.subject_ref == ""
    assert crowd.get_belief(db, fac.id, crowd.SignalType.parking_fullness).value == {
        "status": "some"
    }


def test_a_subject_belief_is_invisible_to_the_facility_wide_read(db):
    # asking for the facility's parking belief must never surface a vendor's
    fac = _facility(db, "Petro")
    driver = _account(db, "f@x.com")
    _present(db, driver, fac)
    crowd.submit(
        db,
        driver.id,
        fac.id,
        crowd.SignalType.vendor_present,
        {"present": True},
        T0,
        subject_ref="v1",
    )
    crowd.update_belief(db, fac.id, crowd.SignalType.vendor_present, T0, subject_ref="v1")

    assert crowd.get_belief(db, fac.id, crowd.SignalType.vendor_present) is None


def test_award_cooldown_is_scoped_per_subject(db):
    # confirming cook A then cook B at the same stop are two different contributions;
    # the anti-farming cooldown must not treat the second as a repeat of the first
    fac = _facility(db, "Flying J")
    driver = _account(db, "g@x.com")
    _present(db, driver, fac)

    first = crowd.submit(
        db,
        driver.id,
        fac.id,
        crowd.SignalType.vendor_present,
        {"present": True},
        T0,
        subject_ref="v1",
    )
    second = crowd.submit(
        db,
        driver.id,
        fac.id,
        crowd.SignalType.vendor_present,
        {"present": True},
        T0,
        subject_ref="v2",
    )
    repeat = crowd.submit(
        db,
        driver.id,
        fac.id,
        crowd.SignalType.vendor_present,
        {"present": True},
        T0,
        subject_ref="v1",
    )

    assert first.awarded is True
    assert second.awarded is True  # a different cook, not farming
    assert repeat.awarded is False  # the same cook again, inside the cooldown


def test_beliefs_for_signal_returns_every_subject(db):
    # the map overlay asks "which vendors are believed present across these lots"
    # in one query rather than N+1 per facility
    fac1, fac2 = _facility(db, "Stop One"), _facility(db, "Stop Two")
    driver = _account(db, "h@x.com")
    for fac, subject in ((fac1, "v1"), (fac1, "v2"), (fac2, "v3")):
        _present(db, driver, fac)
        crowd.submit(
            db,
            driver.id,
            fac.id,
            crowd.SignalType.vendor_present,
            {"present": True},
            T0,
            subject_ref=subject,
        )
        crowd.update_belief(db, fac.id, crowd.SignalType.vendor_present, T0, subject_ref=subject)

    found = crowd.beliefs_for_signal(db, [fac1.id, fac2.id], crowd.SignalType.vendor_present)
    assert {b.subject_ref for b in found} == {"v1", "v2", "v3"}
    assert crowd.beliefs_for_signal(db, [], crowd.SignalType.vendor_present) == []


def test_vendor_signals_have_decay_and_freshness_entries(db):
    # every SignalType must appear in all four keyed tables or aggregation KeyErrors
    for signal in (crowd.SignalType.vendor_present, crowd.SignalType.vendor_sold_out):
        assert signal in crowd.HALF_LIFE_SECONDS
        assert signal in crowd.POINTS_PER_SIGNAL
