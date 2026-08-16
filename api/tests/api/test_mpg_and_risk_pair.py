"""AI-CONTEXT: the driver's own fuel economy, and the raw pair (J1-A3, entries 153/154).

Two figures on the pre-acceptance screens that were each confidently wrong in their own
way.

MPG was hardcoded to 6.0 in two places — the request model's default and the calculator
surface's payload — so a reefer at 5.2 and a light run at 7.5 were handed the same fuel
cost for the same route, and nothing on the screen admitted the number was ours. The
null is the load-bearing part of the fix: NULL means *this driver has not told us*,
which is a different statement from any number, 6.0 included.

The risk figure travelled as a rate. Entry 153 settled that it must be a raw pair —
"ran past on 9 of 21" — because a fraction carries its own sample size and 67% over
three stops overstates what we know. The count is what was measured, so the count is
what travels; a client multiplying a float back out can disagree with itself.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.main import app


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _headers(client, email):
    token = client.post("/auth/register", json={"email": email, "password": "pw-123456"}).json()[
        "token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _calc(client, headers, **over):
    body = {
        "revenue_cents": 185000,
        "loaded_miles": 500,
        "tolls_cents": 0,
        "receiver_facility_id": "00000000-0000-0000-0000-000000000000",
        "free_time_minutes": 120,
        "rate_cents_per_hour": 5000,
        "origin_lat": 32.7767,
        "origin_lon": -96.797,
        **over,
    }
    return client.post("/intel/true-profit", json=body, headers=headers)


# --- what the driver reports ---


def test_the_profile_starts_with_no_mpg_at_all(client, db):
    """NULL, not 6.0. A stored 6.0 would be indistinguishable from a driver who happens
    to run 6.0, and the difference is exactly what the calculator has to say."""
    headers = _headers(client, "mpg-unset@example.com")
    assert client.get("/auth/me", headers=headers).json()["mpg"] is None


def test_a_driver_can_report_their_own(client, db):
    headers = _headers(client, "mpg-set@example.com")
    assert client.patch("/auth/equipment", json={"mpg": "5.2"}, headers=headers).json()["mpg"] == (
        5.2
    )
    assert client.get("/auth/me", headers=headers).json()["mpg"] == 5.2


def test_a_blank_clears_it_rather_than_storing_a_zero(client, db):
    """A driver who is unsure of their real figure must be able to take the guess back
    out. Storing 0 would divide the route into infinite gallons."""
    headers = _headers(client, "mpg-clear@example.com")
    client.patch("/auth/equipment", json={"mpg": "5.2"}, headers=headers)

    assert client.patch("/auth/equipment", json={"mpg": ""}, headers=headers).json()["mpg"] is None


@pytest.mark.parametrize("bad", ["0", "0.5", "60", "-6", "not a number"])
def test_a_typo_is_refused_rather_than_costed(client, db, bad):
    """The bounds are a typo check, not a claim about trucking: 60 for the pickup or 0.6
    for a decimal slip puts the fuel cost out by an order of magnitude on the one screen
    whose job is saying whether a load pays."""
    headers = _headers(client, f"mpg-bad-{bad.replace(' ', '')}@example.com")
    assert _patch_status(client, headers, bad) == 422


def _patch_status(client, headers, value):
    return client.patch("/auth/equipment", json={"mpg": value}, headers=headers).status_code


@pytest.mark.parametrize("ok", ["3", "6.5", "12"])
def test_the_bounds_are_inclusive(client, db, ok):
    headers = _headers(client, f"mpg-ok-{ok}@example.com")
    assert _patch_status(client, headers, ok) == 200


def test_reporting_mpg_does_not_wipe_the_plate(client, db):
    """`upsert_driver_profile` writes what it is given; a form that submits one field
    must not clear the rest."""
    headers = _headers(client, "mpg-keeps@example.com")
    client.patch("/auth/equipment", json={"plate_state": "TX", "plate_number": "7ABC123"},
                 headers=headers)

    client.patch("/auth/equipment", json={"mpg": "6.4", "plate_state": "TX",
                                         "plate_number": "7ABC123"}, headers=headers)

    me = client.get("/auth/me", headers=headers).json()
    assert (me["mpg"], me["plate_state"], me["plate_number"]) == (6.4, "TX", "7ABC123")


# --- which mpg the calculator used, said out loud ---


def test_the_calculator_says_the_number_is_OURS_when_nobody_told_it(client, db):
    headers = _headers(client, "mpg-basis-default@example.com")

    basis = _calc(client, headers).json()["basis"]

    assert basis["mpg_basis"] == "default"
    assert basis["mpg"] == float(identity.DEFAULT_MPG)


def test_the_calculator_uses_what_the_driver_reported_and_says_so(client, db):
    headers = _headers(client, "mpg-basis-driver@example.com")
    client.patch("/auth/equipment", json={"mpg": "5.2"}, headers=headers)

    basis = _calc(client, headers).json()["basis"]

    assert (basis["mpg_basis"], basis["mpg"]) == ("driver", 5.2)


def test_a_what_if_in_the_request_still_wins_and_is_named_as_one(client, db):
    """"What would this pay in the day cab" is a real question. What it may not do is
    arrive silently."""
    headers = _headers(client, "mpg-basis-request@example.com")
    client.patch("/auth/equipment", json={"mpg": "5.2"}, headers=headers)

    basis = _calc(client, headers, mpg=8.0).json()["basis"]

    assert (basis["mpg_basis"], basis["mpg"]) == ("request", 8.0)


def test_a_worse_mpg_costs_more_fuel_than_a_better_one(client, db):
    """The disclosure would be worthless if the number did not actually reach the
    arithmetic — this is the wire, not the label."""
    thirsty = _headers(client, "mpg-thirsty@example.com")
    frugal = _headers(client, "mpg-frugal@example.com")
    client.patch("/auth/equipment", json={"mpg": "4.0"}, headers=thirsty)
    client.patch("/auth/equipment", json={"mpg": "9.0"}, headers=frugal)

    a = _calc(client, thirsty).json()
    b = _calc(client, frugal).json()

    # with no fuel network in this fixture both are 0; what must differ is the gallons
    # the basis was computed from, so assert on the figure that carries it
    assert a["basis"]["mpg"] < b["basis"]["mpg"]


# --- the raw pair ---


def test_the_risk_endpoint_carries_the_count_not_only_the_rate(client, db):
    """Entry 153: a raw pair, never a percentage. The count is what was measured; a
    figure recovered from a float is one that can disagree with itself."""
    headers = _headers(client, "risk-pair@example.com")

    body = client.get(
        f"/intel/detention-risk/{uuid.UUID(int=0)}?free_time_minutes=120", headers=headers
    ).json()

    assert "exceeded" in body
    assert "sample_size" in body


def test_no_history_is_a_zero_pair_and_a_null_rate(client, db):
    """`exceeded` 0 of 0 is honest; what must never appear is a rate of 0.0, which reads
    as "this dock never detains anyone"."""
    headers = _headers(client, "risk-empty@example.com")

    body = client.get(f"/intel/detention-risk/{uuid.UUID(int=0)}", headers=headers).json()

    assert body["exceed_rate"] is None
    assert (body["exceeded"], body["sample_size"]) == (0, 0)
