"""AI-CONTEXT: HTTP API tests for the Public Scorecard — the only unauthenticated
surface. Proves no-auth access, name search, and the aggregate/min-sample
privacy floor on dwell (§13).
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.main import app

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
T0 = datetime(2026, 7, 21, 6, 0, tzinfo=UTC)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _dwell(db, fac_id, i):
    driver = identity.register_account(db, f"d{i}@x.com", "pw-123456")
    location.arm_geofence(db, driver.id, fac_id)
    location.evaluate_ping(db, driver.id, *DALLAS, occurred_at=T0)
    location.evaluate_ping(db, driver.id, *FAR, occurred_at=T0 + timedelta(hours=2))
    location.disarm_geofence(db, driver.id, fac_id, occurred_at=T0 + timedelta(hours=2))


def test_scorecard_needs_no_auth(client, db):
    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "Loves #212", *DALLAS)
    # no Authorization header at all
    listing = client.get("/public/facilities", params={"q": "Loves"})
    assert listing.status_code == 200
    assert any(f["name"] == "Loves #212" for f in listing.json())
    assert str(fac.id) in [f["id"] for f in listing.json()]


def test_dwell_suppressed_below_min_sample_then_published(client, db):
    fac = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Receiver", *DALLAS)
    _dwell(db, fac.id, 0)  # one tracked stop — below the public floor

    below = client.get(f"/public/facility/{fac.id}")
    assert below.status_code == 200
    assert below.json()["dwell"] is None  # suppressed, never a small-n figure

    _dwell(db, fac.id, 1)
    _dwell(db, fac.id, 2)  # now 3 tracked stops -> at/above the floor
    ok = client.get(f"/public/facility/{fac.id}")
    body = ok.json()
    assert body["dwell"] is not None
    assert body["dwell"]["sample_size"] == 3
    assert body["dwell"]["median_seconds"] == 2 * 3600


def test_scorecard_shows_only_approved_deidentified_snippets(client, db):
    from app.modules.m02_facility_intel import public as m2

    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "TA #7", *DALLAS)
    driver = identity.register_account(db, "reviewer@x.com", "pw-123456")

    approved = m2.submit_review(
        db, fac.id, driver.id, {"check_in_speed": 5}, text="Quick in and out."
    )
    m2.moderate_review(db, approved, approve=True)
    # AI-CONTEXT: a LEGACY pending row, forced rather than submitted (§23 entry 153).
    #
    # Submission publishes now, so nothing in the product creates this state any more —
    # but rows created under the old policy still exist (measured: 8 on the dev box) and
    # they must stay hidden, which is exactly what this test is for. Forcing the status is
    # the only way to construct a state the code no longer produces, and testing it still
    # matters because the rows are real.
    pending = m2.submit_review(
        db, fac.id, driver.id, {"check_in_speed": 2}, text="Pending, not shown."
    )
    pending.status = m2.ReviewStatus.pending
    db.flush()
    rejected = m2.submit_review(
        db, fac.id, driver.id, {"check_in_speed": 1}, text="Rejected, not shown."
    )
    m2.moderate_review(db, rejected, approve=False)

    body = client.get(f"/public/facility/{fac.id}").json()  # no auth
    assert body["reviews"] == ["Quick in and out."]  # approved only
    assert "Pending, not shown." not in body["reviews"]
    assert "Rejected, not shown." not in body["reviews"]
    # de-identified: the payload carries text strings only, nothing identifying
    assert all(isinstance(r, str) for r in body["reviews"])
    assert str(driver.id) not in str(body)
    assert str(pending.id) not in str(body)


def test_scorecard_snippets_capped_at_three(client, db):
    from app.modules.m02_facility_intel import public as m2

    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "Pilot", *DALLAS)
    driver = identity.register_account(db, "many@x.com", "pw-123456")
    for i in range(5):
        r = m2.submit_review(db, fac.id, driver.id, {"check_in_speed": 4}, text=f"Review {i}")
        m2.moderate_review(db, r, approve=True)

    assert len(client.get(f"/public/facility/{fac.id}").json()["reviews"]) == 3  # capped


def test_scorecard_404_for_unknown(client):
    resp = client.get("/public/facility/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
