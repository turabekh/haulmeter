"""F4-5 — does a float survive the JSONB round trip that verification depends on?

THE DEPENDENCY, stated because it is invisible at both ends. `compute_record_hash` hashes
the payload through `json.dumps(..., default=str)`, which serialises a Python float with
`repr`. The record is then stored in JSONB, and `verify_chain` recomputes the hash from the
payload READ BACK OUT. If Postgres's numeric normalisation returned a float whose `repr`
differed from the one hashed — 32.77670000000001 for 32.7767, say — verification would
report `tampered` on a record nobody touched, and the pack would print "HASH CHAIN BROKEN"
over honest evidence.

Nothing in the review found a value that does this. That is exactly why the probe exists
rather than a fix: the corpus below is adversarial on purpose, and it runs against the real
Postgres, so the day a driver, a dependency upgrade or a column-type change breaks the
assumption, this goes red instead of a claim going out with a scary PDF.

The corpus is real GPS shapes plus the classic float hazards: long fractions, exponent
forms, negative zero, subnormals, and the values that print differently in different
languages.
"""

import json

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f04_evidence import public as evidence
from app.foundation.f04_evidence.domain import hashing

# every one of these is hashed as a Python float and read back through JSONB
ADVERSARIAL_FLOATS = [
    32.7767,  # a real dock, as F3 records it
    -96.79699999999998,  # the long-fraction shape a subtraction produces
    41.87811111111111,
    -87.62980000000001,
    0.1 + 0.2,  # 0.30000000000000004 — the canonical example
    1e-7,
    1.0e16,
    1.7976931348623157e308,  # float max
    5e-324,  # smallest subnormal
    -0.0,  # negative zero: `repr` keeps the sign, some encoders do not
    0.0,
    123456789.123456789,  # more digits than a double can hold
    2.675,  # the classic rounding-demo value
    -1.5e-10,
    99.999999999999999,
]


def _log(db, label="probe"):
    account = identity.register_account(db, f"{label}@example.com", "pw-123456")
    return evidence.create_log(db, account.id, label=label)


@pytest.mark.parametrize("value", ADVERSARIAL_FLOATS, ids=lambda v: repr(v))
def test_a_float_survives_the_round_trip_verification_depends_on(db, value):
    """Write it through the real database, read it back, and verify the chain."""
    log = _log(db, label=f"probe-{abs(hash(value)) % 10000}")
    evidence.append_record(
        db, log, evidence.RecordType.GEOFENCE, {"lat": value, "lon": value, "acc": [value]}
    )
    db.flush()
    db.expire_all()  # force the payload to come back FROM Postgres, not the identity map

    assert evidence.verify_chain(db, log).valid is True


def test_a_whole_gps_trail_of_them_verifies_together(db):
    """One record per value on one chain — the shape a real visit produces."""
    log = _log(db, label="probe-trail")
    for value in ADVERSARIAL_FLOATS:
        evidence.append_record(
            db, log, evidence.RecordType.GEOFENCE, {"lat": value, "lon": -value}
        )
    db.flush()
    db.expire_all()

    result = evidence.verify_chain(db, log)

    assert result.valid is True
    assert result.record_count == len(ADVERSARIAL_FLOATS)


def test_the_probe_is_not_vacuous(db):
    """Proves the round trip actually happens — without this the file is decoration.

    `expire_all()` is NOT enough on its own, which a revert-check showed: delete it and
    every test above still passes, because SQLAlchemy can serve the payload from the
    identity map and never ask Postgres at all. So this reads the stored JSONB back with
    RAW SQL, bypassing the ORM entirely, and asserts the property the hash depends on —
    that the value Postgres holds still `repr`s to exactly what was hashed.
    """
    from sqlalchemy import text as sql_text

    log = _log(db, label="probe-vacuity")
    value = -96.79699999999998
    record_id = evidence.append_record(
        db, log, evidence.RecordType.GEOFENCE, {"lat": value}
    ).id
    db.flush()

    stored = db.execute(
        sql_text("SELECT payload->>'lat' AS lat FROM f04.evidence_record WHERE id = :id"),
        {"id": record_id},
    ).one()

    assert repr(float(stored.lat)) == repr(value)


def test_the_canonical_encoder_is_what_makes_this_work(db):
    """Pins the mechanism, so a change to `_canonical` cannot silently break the above.

    `default=str` means a float is encoded by `repr`, and Python's `repr` is the shortest
    string that round-trips to the same double. That is the property the whole scheme
    leans on; if it were `float(...)`-formatted or locale-aware, this would be fragile.
    """
    for value in ADVERSARIAL_FLOATS:
        encoded = hashing._canonical({"v": value})
        assert json.loads(encoded)["v"] == value
