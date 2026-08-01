"""AI-CONTEXT: HTTP API tests for M1 + auth. Uses FastAPI TestClient with the
get_db dependency overridden to the transactional test session (so requests
share the isolated test DB and roll back). Proves the live status pipeline over
HTTP: register → report → the next overlay reflects the new belief.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.main import app
from app.modules.m07_fuel import public as m7

DALLAS = (32.7767, -96.7970)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client):
    resp = client.post(
        "/auth/register", json={"email": "driver@example.com", "password": "pw-123456"}
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_overlay_requires_auth(client):
    resp = client.get("/map/overlay", params={"lat": DALLAS[0], "lon": DALLAS[1]})
    assert resp.status_code == 401


def test_register_login_and_overlay(client, db):
    headers = _auth(client)
    facility.create_facility(db, facility.FacilityType.truck_stop, "Stop", *DALLAS)
    resp = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "drive"},
        headers=headers,
    )
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()["pins"]]
    assert "Stop" in names


def test_overlay_enriches_bookable_and_fuel_badges(client, db):
    # M1 can't import M6/M7, so the overlay endpoint attaches the marketplace
    # badges that drive the map's Book / Fuel-here actions (NAV-5)
    from app.foundation.f01_identity import public as identity
    from app.modules.m06_parking import public as m6
    from app.modules.m07_fuel import public as m7

    headers = _auth(client)
    owner = identity.register_account(db, "lotowner@example.com", "pw-123456")
    prop = m6.create_property(db, owner.id, "Yardline", *DALLAS, vetted=True)
    m6.add_spot(db, prop, "A1", price_cents_per_night=2400)
    station = facility.create_facility(db, facility.FacilityType.fuel_station, "QuikFuel", *DALLAS)
    merchant = m7.register_merchant(db, "TripFuel")
    m7.set_station_pricing(
        db, station.id, gross_cents_per_gal=419, discount_cents_per_gal=25, merchant_id=merchant.id
    )

    pins = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "tonight"},
        headers=headers,
    ).json()["pins"]
    yardline = next(p for p in pins if p["name"] == "Yardline")
    book = next(b for b in yardline["badges"] if b["kind"] == "bookable")
    assert book["value"] == 2400 and book["spot_id"]  # cheapest active spot + price

    fuel_pins = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "fuel"},
        headers=headers,
    ).json()["pins"]
    quik = next(p for p in fuel_pins if p["name"] == "QuikFuel")
    net = next(b for b in quik["badges"] if b["kind"] == "fuel_net")
    assert net["net"] == 394 and net["savings"] == 25  # $4.19 gross − 25¢ discount
    assert net["is_network"] is True  # network station -> the card leads with "Fuel here"


def test_login_wrong_password(client):
    client.post("/auth/register", json={"email": "x@example.com", "password": "right-pw"})
    resp = client.post("/auth/login", json={"email": "x@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_report_updates_belief_reflected_in_overlay(client, db):
    headers = _auth(client)
    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "Reported Stop", *DALLAS)

    report = client.post(
        "/map/report",
        json={
            "facility_id": str(fac.id),
            "signal_type": "parking_fullness",
            "value": {"status": "full"},
        },
        headers=headers,
    )
    assert report.status_code == 200
    assert report.json()["presence_proven"] is False  # not geofenced here

    overlay = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "drive"},
        headers=headers,
    )
    pin = next(p for p in overlay.json()["pins"] if p["facility_id"] == str(fac.id))
    assert pin["status"] == "full"  # report -> aggregate -> pin, live over HTTP


def test_overlay_fuel_badge_carries_regional_baseline(client, db):
    # M1-FR5: a real fuel station with no per-station price shows the EIA regional
    # average, tagged as indicative so the card can label it honestly.
    from datetime import date

    from app.modules.m07_fuel import public as m7

    headers = _auth(client)
    m7.upsert_regional_price(db, "PADD3", 362, date(2026, 7, 14))  # Dallas (TX) -> PADD3
    facility.create_facility(db, facility.FacilityType.fuel_station, "Kwik Trip", *DALLAS)
    pins = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "fuel"},
        headers=headers,
    ).json()["pins"]
    quik = next(p for p in pins if p["name"] == "Kwik Trip")
    net = next(b for b in quik["badges"] if b["kind"] == "fuel_net")
    assert net["net"] == 362 and net["source"] == "regional" and net["indicative"] is True


def test_a_truck_stop_that_sells_diesel_carries_the_price(client, db):
    """E3.3. The regression this whole change turns on: once a fuel island merges into
    its host, the surviving pin is a TRUCK STOP. A badge gated on facility_type would
    have deleted the price rather than moved it, leaving the driver worse off than
    before the duplicate pin was removed."""
    from datetime import date

    headers = _auth(client)
    m7.upsert_regional_price(db, "PADD3", 362, date(2026, 7, 14))
    facility.create_facility(
        db,
        facility.FacilityType.truck_stop,
        "Flying J Travel Center",
        *DALLAS,
        attributes={"services": [facility.SERVICE_FUEL]},
    )
    pins = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "drive"},
        headers=headers,
    ).json()["pins"]
    stop = next(p for p in pins if p["name"] == "Flying J Travel Center")
    net = next(b for b in stop["badges"] if b["kind"] == "fuel_net")
    assert net["net"] == 362 and net["indicative"] is True


def test_the_fuel_preset_finds_a_truck_stop_that_sells_diesel(client, db):
    """E3.3, and a regression caught only by re-running the original repro through the
    API. Fixing the duplicate pin re-typed the Flying J to truck_stop, and because the
    Fuel preset was `[fuel_station]` the site then vanished from the fuel map
    altogether — strictly worse than the duplicate it replaced. The preset asks what a
    site SELLS, not what kind it is filed under."""
    headers = _auth(client)
    facility.create_facility(
        db,
        facility.FacilityType.truck_stop,
        "Flying J Travel Center",
        *DALLAS,
        attributes={"services": [facility.SERVICE_FUEL]},
    )
    facility.create_facility(db, facility.FacilityType.truck_stop, "Dry Lot", *DALLAS)
    pins = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "fuel"},
        headers=headers,
    ).json()["pins"]

    names = {p["name"] for p in pins}
    assert "Flying J Travel Center" in names
    assert "Dry Lot" not in names  # a truck stop with no pump is not on the fuel map


def test_every_kind_that_can_host_a_pump_reaches_the_fuel_preset(client, db):
    """Reported from production as "no facilities showing up except demo ones".

    A pump merges into whatever kind hosts it — a rest area or a parking property as
    readily as a truck stop — and the surviving pin takes the HOST's kind. The Fuel
    preset's candidate list named only truck_stop and fuel_station, so 168 sites that
    had been visible fuel_station pins before the merge appeared on no fuel map at all.
    The candidate set has to cover every host kind and let `sells_fuel` decide."""
    headers = _auth(client)
    for kind, name in [
        (facility.FacilityType.rest_area, "Merged Into Rest Area"),
        (facility.FacilityType.parking_property, "Merged Into Parking"),
        (facility.FacilityType.truck_stop, "Merged Into Truck Stop"),
    ]:
        facility.create_facility(
            db, kind, name, *DALLAS, attributes={"services": [facility.SERVICE_FUEL]}
        )
    facility.create_facility(db, facility.FacilityType.parking_property, "Dry Parking", *DALLAS)

    names = {
        p["name"]
        for p in client.get(
            "/map/overlay",
            params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "fuel"},
            headers=headers,
        ).json()["pins"]
    }
    assert {"Merged Into Rest Area", "Merged Into Parking", "Merged Into Truck Stop"} <= names
    assert "Dry Parking" not in names


def test_drive_gains_a_fuel_parking_property_but_not_a_dry_one(client, db):
    """Drive is not Tonight. A parking property earns a place there only because a
    pump merged into it — before that merge it WAS a fuel_station pin Drive showed, so
    this restores a promise the merge broke rather than widening the preset."""
    headers = _auth(client)
    facility.create_facility(
        db,
        facility.FacilityType.parking_property,
        "Flying J #695",
        *DALLAS,
        attributes={"services": [facility.SERVICE_FUEL]},
    )
    facility.create_facility(db, facility.FacilityType.parking_property, "Dry Parking", *DALLAS)

    names = {
        p["name"]
        for p in client.get(
            "/map/overlay",
            params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "drive"},
            headers=headers,
        ).json()["pins"]
    }
    assert "Flying J #695" in names
    assert "Dry Parking" not in names


def test_a_truck_stop_without_fuel_carries_no_price(client, db):
    """The other half, and the reason the gate is the SERVICE and not the kind. The
    regional baseline answers for any coordinate on earth, so widening the badge to
    `truck_stop` would paint an indicative figure on every truck stop in the country
    whether or not it has a pump — a data-COVERAGE badge, which is exactly what
    §11.1 keeps off the map."""
    from datetime import date

    headers = _auth(client)
    m7.upsert_regional_price(db, "PADD3", 362, date(2026, 7, 14))
    facility.create_facility(db, facility.FacilityType.truck_stop, "Dry Lot", *DALLAS)
    pins = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "drive"},
        headers=headers,
    ).json()["pins"]
    lot = next(p for p in pins if p["name"] == "Dry Lot")
    assert [b for b in lot["badges"] if b["kind"] == "fuel_net"] == []


def test_a_report_against_a_merged_facility_reaches_the_pin_that_renders(client, db):
    """The sharpest form of the stale-id defect, found by driving the API after the
    E3.3 merge. A merge does not delete the duplicate — deliberately, so an id a
    driver already holds keeps working — but nothing resolved it on the way in, so
    this returned a submission_id and wrote the belief onto a facility that no longer
    renders. The driver was told their "lot is full" landed; nobody would ever see it.
    §11.7 forbids an absence dressed as a result."""
    headers = _auth(client)
    host = facility.create_facility(
        db, facility.FacilityType.truck_stop, "Flying J Travel Center", *DALLAS
    )
    pump = facility.create_facility(db, facility.FacilityType.fuel_station, "Pilot", *DALLAS)
    facility.merge_facilities(db, host, pump)

    resp = client.post(
        "/map/report",
        json={
            "facility_id": str(pump.id),
            "signal_type": "parking_fullness",
            "value": {"status": "full"},
        },
        headers=headers,
    )
    assert resp.status_code == 200

    pins = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "drive"},
        headers=headers,
    ).json()["pins"]
    stop = next(p for p in pins if p["name"] == "Flying J Travel Center")
    assert stop["status"] == "full"  # the report reached the pin a driver can see


def test_a_merged_facility_id_reads_as_the_site_it_belongs_to(client, db):
    """`GET /public/facility/<merged>` answered 200 with the ABSORBED pump — the right
    status code carrying the wrong place. A saved lot, a deep link or a notification
    holding a pre-merge id must land on the site, not on its shadow."""
    host = facility.create_facility(
        db, facility.FacilityType.truck_stop, "Flying J Travel Center", *DALLAS
    )
    pump = facility.create_facility(db, facility.FacilityType.fuel_station, "Pilot", *DALLAS)
    facility.merge_facilities(db, host, pump)

    body = client.get(f"/public/facility/{pump.id}").json()
    assert body["name"] == "Flying J Travel Center"
    assert body["facility_type"] == "truck_stop"


def test_an_unknown_facility_id_still_404s(client, db):
    """Resolution is not existence. The resolver passes an unknown id straight
    through so each route keeps answering 404 in its own words."""
    import uuid as _uuid

    assert client.get(f"/public/facility/{_uuid.uuid4()}").status_code == 404


def test_overlay_freshness_carries_feed_source_for_tpims(client, db):
    # a TPIMS (authoritative) reading tags the pin's freshness with its source, so the
    # card attributes it to the feed — not "N drivers" (§11.7 honesty)
    from datetime import UTC, datetime

    from app.foundation.f10_crowd import public as crowd

    headers = _auth(client)
    fac = facility.create_facility(db, facility.FacilityType.rest_area, "IL Rest", *DALLAS)
    now = datetime.now(UTC)
    crowd.submit_authoritative(
        db,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "some", "available": "Low", "trend": None, "source": "tpims"},
        submitted_at=now,
        source="tpims",
        trust_data=True,
    )
    crowd.update_belief(db, fac.id, crowd.SignalType.parking_fullness, as_of=now)
    pins = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "tonight"},
        headers=headers,
    ).json()["pins"]
    pin = next(p for p in pins if p["name"] == "IL Rest")
    assert pin["freshness"]["source"] == "tpims"  # feed provenance surfaced
    assert pin["availability"] == "Low" and pin["status"] == "some"  # Low category kept


def test_overlay_bbox_is_the_primary_mode(client, db):
    # the map fetches by viewport bbox (min/max lat/lon), not a fixed point+radius
    headers = _auth(client)
    facility.create_facility(db, facility.FacilityType.truck_stop, "InView", *DALLAS)
    facility.create_facility(db, facility.FacilityType.truck_stop, "Chicago", 41.88, -87.63)
    resp = client.get(
        "/map/overlay",
        params={"min_lat": 32.70, "min_lon": -96.90, "max_lat": 32.90, "max_lon": -96.70},
        headers=headers,
    )
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()["pins"]]
    assert names == ["InView"]  # the Chicago stop is outside the Texas viewport


def test_overlay_without_bbox_or_point_is_422(client):
    headers = _auth(client)
    resp = client.get("/map/overlay", headers=headers)
    assert resp.status_code == 422


def test_corridor_endpoint(client, db):
    headers = _auth(client)
    facility.create_facility(db, facility.FacilityType.truck_stop, "Ahead", 32.90, -96.7970)
    resp = client.get(
        "/map/corridor",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "heading_deg": 0, "max_distance_m": 40000},
        headers=headers,
    )
    assert resp.status_code == 200
    assert [e["name"] for e in resp.json()] == ["Ahead"]


def test_corridor_carries_what_the_stack_renders(client, db):
    """§23 entry 81. CorridorStack renders a status pill and §11.4's price, and this
    route returned neither — which is why the surface kept a fixture that did. The
    contract is asserted here so the next person to wire a component to this endpoint
    finds out at test time, not by reading a hardcoded truck stop at 65 mph."""
    headers = _auth(client)
    facility.create_facility(db, facility.FacilityType.truck_stop, "Ahead", 32.90, -96.7970)
    resp = client.get(
        "/map/corridor",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "heading_deg": 0, "max_distance_m": 40000},
        headers=headers,
    )
    assert resp.status_code == 200
    entry = resp.json()[0]
    # every key the component reads, present even when there is nothing to say
    assert set(entry) >= {
        "facility_id",
        "name",
        "facility_type",
        "distance_m",
        "status",
        "reported_at",
        "sample_size",
        "badges",
    }
    assert entry["status"] is None  # nobody has reported: said, not guessed
    assert entry["badges"] == []
    # §23 entry 86: WHERE it is. §11.4's saved queue offers a Navigate, and without
    # coordinates that button can only route through a page to look them up.
    assert entry["lat"] is not None and entry["lon"] is not None


def test_corridor_quotes_a_station_the_same_price_the_pin_does(client, db):
    """One pump, one figure, whichever screen the driver is reading. The badge comes
    from the same `_fuel_badge` the overlay uses, so the two cannot drift."""
    headers = _auth(client)
    station = facility.create_facility(
        db, facility.FacilityType.fuel_station, "Pump", 32.90, -96.7970
    )
    m7.set_station_pricing(db, station.id, gross_cents_per_gal=419, discount_cents_per_gal=32)
    corridor = client.get(
        "/map/corridor",
        params={
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "heading_deg": 0,
            "max_distance_m": 40000,
            "preset": "fuel",
        },
        headers=headers,
    ).json()
    overlay = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 40000, "preset": "fuel"},
        headers=headers,
    ).json()
    corridor_badge = next(
        (b for b in corridor[0]["badges"] if b["kind"] == "fuel_net"),
        None,
    )
    pin_badge = next(
        (b for b in overlay["pins"][0]["badges"] if b["kind"] == "fuel_net"),
        None,
    )
    # both-None would pass this vacuously, which is the shape §23 entry 42 keeps
    # catching: a test that asserts agreement between two absences
    assert pin_badge is not None
    assert corridor_badge == pin_badge


# --- §11.2's clock slot, finally fed (M2-FR3 / §23 entry 87) ---
def _detained_dock(db, account_id, name, visits, free_time_minutes=120):
    """`visits` is a list of (arrival, departure). Each becomes its own claim."""

    from app.foundation.f03_location import public as location
    from app.foundation.f05_load import public as loads
    from app.modules.m03_detention import public as m3

    far = (32.9000, -96.8000)
    dock = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, name, *DALLAS
    )
    load = loads.create_load(db, account_id, free_time_minutes=free_time_minutes)
    for arrival, departure in visits:
        stop = loads.add_stop(
            db, load, dock.id, loads.StopType.delivery,
            free_time_minutes=free_time_minutes,
        )
        m3.start_claim(db, stop, started_at=arrival)
        location.evaluate_ping(db, account_id, *DALLAS, occurred_at=arrival)
        location.evaluate_ping(db, account_id, *far, occurred_at=departure)
    return dock


def _account_id(db, headers):
    from app.foundation.f01_identity import public as identity

    return identity.resolve_session(db, headers["Authorization"].split(" ", 1)[1]).id


def test_overlay_marks_a_dock_that_runs_long(client, db):
    """§11.2 names a "clock (dwell risk)" badge slot and it had no signal behind it —
    `m02.detention_risk` was a stub. Three visits, all over the contracted free time."""
    from datetime import UTC, datetime, timedelta

    headers = _auth(client)
    account_id = _account_id(db, headers)
    t0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
    _detained_dock(db, account_id, "Slow Dock", [
        (t0 + timedelta(days=i), t0 + timedelta(days=i, hours=5)) for i in range(3)
    ])
    pins = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "work"},
        headers=headers,
    ).json()["pins"]
    pin = next(p for p in pins if p["name"] == "Slow Dock")
    badge = next(b for b in pin["badges"] if b["kind"] == "dwell_risk")
    assert badge["value"] == 1.0
    # §11.7: the sample travels with the rate, so the card never shows one without it
    assert badge["sample_size"] == 3


def test_overlay_does_not_mark_a_dock_that_keeps_its_terms(client, db):
    from datetime import UTC, datetime, timedelta

    headers = _auth(client)
    account_id = _account_id(db, headers)
    t0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
    _detained_dock(db, account_id, "Quick Dock", [
        (t0 + timedelta(days=i), t0 + timedelta(days=i, minutes=45)) for i in range(3)
    ])
    pins = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "work"},
        headers=headers,
    ).json()["pins"]
    pin = next(p for p in pins if p["name"] == "Quick Dock")
    assert [b for b in pin["badges"] if b["kind"] == "dwell_risk"] == []


def test_overlay_stays_quiet_below_the_sample_floor(client, db):
    """§11.7 / §11.1. Two bad visits is a rumour, not a record — and a badge on every
    receiver we happen to have data for would be a coverage indicator, not a risk one."""
    from datetime import UTC, datetime, timedelta

    headers = _auth(client)
    account_id = _account_id(db, headers)
    t0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
    _detained_dock(db, account_id, "Barely Seen", [
        (t0 + timedelta(days=i), t0 + timedelta(days=i, hours=6)) for i in range(2)
    ])
    pins = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "work"},
        headers=headers,
    ).json()["pins"]
    pin = next(p for p in pins if p["name"] == "Barely Seen")
    assert [b for b in pin["badges"] if b["kind"] == "dwell_risk"] == []


def test_overlay_carries_the_service_list_and_the_phone_a_driver_taps(client, db):
    """A5: the card's call action and service rows render from the OVERLAY payload.
    `services` reached the Pin object and stopped there — the serializer never sent
    it — so a rule proved at three layers still could not put a repair shop's phone
    on a screen. One layer short is the whole distance."""
    headers = _auth(client)
    shop = facility.create_facility(
        db, facility.FacilityType.repair, "Portage Diesel Repair", *DALLAS
    )
    shop.attributes = {
        "services": ["truck_repair", "tire"],
        "phone": "+1-608-555-0199",
        "opening_hours": "Mo-Fr 07:00-18:00",
    }
    db.flush()

    pins = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "service"},
        headers=headers,
    ).json()["pins"]
    pin = next(p for p in pins if p["name"] == "Portage Diesel Repair")
    assert pin["services"] == ["truck_repair", "tire"]
    assert pin["phone"] == "+1-608-555-0199"
    assert pin["opening_hours"] == "Mo-Fr 07:00-18:00"
