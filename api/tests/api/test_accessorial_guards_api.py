"""M4's filing guards — ownership, amount floor, and once-per-target (D3).

These are the FIRST 403 assertions this router has ever had. Before them any authenticated
driver could file a TONU or a lumper fee against any load in the database: a receivable
invented on someone else's account, and an invoice sent to their broker under their name.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
from app.main import app
from app.modules.m04_accessorial import public as m4
from app.modules.m04_accessorial.domain.models import AccessorialClaim

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _driver(client, db, email="oo@example.com"):
    reg = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    account = db.get(identity.Account, uuid.UUID(reg.json()["account_id"]))
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    return account, {"Authorization": f"Bearer {reg.json()['token']}"}


def _load_for(db, account, name="Dock"):
    broker = loads.create_counterparty(
        db, "Acme", loads.CounterpartyKind.broker, contact_email="ap@acme.example"
    )
    load = loads.create_load(db, account.id, counterparty_id=broker.id)
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, name, *DALLAS)
    return load, dock


def _overnight_stop(db, account, load, dock):
    """A stop the driver was at across two local calendar days — a real layover."""
    arrival = datetime(2026, 7, 20, 23, 0, tzinfo=UTC)
    stop = loads.add_stop(
        db, load, dock.id, loads.StopType.delivery, appointment_start=arrival - timedelta(hours=1)
    )
    # without an armed geofence there is no visit for `visit_window` to find, and layover
    # refuses with NoLayover before it ever reaches the guards under test
    location.arm_geofence(db, account.id, dock.id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=arrival)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=arrival + timedelta(hours=9))
    db.flush()
    return stop


def _claims(db):
    return db.query(AccessorialClaim).count()


# --- ownership: the first 403s this router has had ---
def test_tonu_on_another_drivers_load_is_refused(client, db):
    owner, _ = _driver(client, db, email="owner@example.com")
    load, _ = _load_for(db, owner)
    _, intruder = _driver(client, db, email="intruder@example.com")

    resp = client.post(
        "/accessorial/tonu",
        json={"load_id": str(load.id), "amount_cents": 15000},
        headers=intruder,
    )

    assert resp.status_code == 403
    assert _claims(db) == 0


def test_lumper_on_another_drivers_load_is_refused(client, db):
    owner, _ = _driver(client, db, email="owner@example.com")
    load, _ = _load_for(db, owner)
    _, intruder = _driver(client, db, email="intruder@example.com")

    resp = client.post(
        "/accessorial/lumper",
        json={"load_id": str(load.id), "amount_cents": 9000},
        headers=intruder,
    )

    assert resp.status_code == 403
    assert _claims(db) == 0


def test_layover_on_another_drivers_stop_is_refused(client, db):
    owner, _ = _driver(client, db, email="owner@example.com")
    load, dock = _load_for(db, owner)
    stop = _overnight_stop(db, owner, load, dock)
    _, intruder = _driver(client, db, email="intruder@example.com")

    resp = client.post(
        "/accessorial/layover",
        json={"stop_id": str(stop.id), "layover_rate_cents": 12000},
        headers=intruder,
    )

    assert resp.status_code == 403
    assert _claims(db) == 0


def test_a_load_that_does_not_exist_is_still_404(client, db):
    _, headers = _driver(client, db)

    resp = client.post(
        "/accessorial/tonu",
        json={"load_id": str(uuid.uuid4()), "amount_cents": 15000},
        headers=headers,
    )

    assert resp.status_code == 404


# --- amounts: two layers, tested independently ---
@pytest.mark.parametrize("amount", [0, -1, -15000])
def test_the_route_refuses_a_nonsense_amount(client, db, amount):
    """Asserted as a FIELD-level validation error, which only `gt=0` can produce.

    Both layers answer 422, so a bare status check cannot tell them apart — removing
    `gt=0` left this test green while the service guard silently covered for it. The
    shapes differ: Pydantic returns a list of errors naming the field, the service
    returns a plain string. Pinning the shape is what makes the two layers independently
    testable, which is the whole point of having two.
    """
    account, headers = _driver(client, db)
    load, _ = _load_for(db, account)

    resp = client.post(
        "/accessorial/tonu",
        json={"load_id": str(load.id), "amount_cents": amount},
        headers=headers,
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, list)
    assert any("amount_cents" in str(err.get("loc", "")) for err in detail)
    assert _claims(db) == 0


@pytest.mark.parametrize("amount", [0, -1, None])
def test_the_service_refuses_a_nonsense_amount_too(db, amount):
    """The layer every non-HTTP caller crosses. m03's `generate_pack` set the precedent."""
    account = identity.register_account(db, "svc@example.com", "pw-123456")
    load, _ = _load_for(db, account)

    with pytest.raises(m4.InvalidAmount):
        m4.file_tonu(db, load, amount)

    assert _claims(db) == 0


def test_the_layover_route_refuses_a_nonsense_rate(client, db):
    account, headers = _driver(client, db)
    load, dock = _load_for(db, account)
    stop = _overnight_stop(db, account, load, dock)

    resp = client.post(
        "/accessorial/layover",
        json={"stop_id": str(stop.id), "layover_rate_cents": 0},
        headers=headers,
    )

    assert resp.status_code == 422


def test_the_lumper_route_refuses_a_nonsense_amount(client, db):
    account, headers = _driver(client, db)
    load, _ = _load_for(db, account)

    resp = client.post(
        "/accessorial/lumper",
        json={"load_id": str(load.id), "amount_cents": -1},
        headers=headers,
    )

    assert resp.status_code == 422


# --- D3: once per target ---
def test_filing_tonu_twice_answers_409_with_the_first_filings_refs(client, db):
    account, headers = _driver(client, db)
    load, _ = _load_for(db, account)
    body = {"load_id": str(load.id), "amount_cents": 15000}

    first = client.post("/accessorial/tonu", json=body, headers=headers)
    second = client.post("/accessorial/tonu", json=body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["error"] == "already_filed"
    assert detail["claim_id"] == first.json()["claim_id"]
    assert detail["receivable_ref"] == first.json()["receivable_ref"]
    assert _claims(db) == 1
    assert len(ledger.list_receivables(db, account.id)) == 1


def test_filing_layover_twice_answers_409_with_the_first_filings_refs(client, db):
    account, headers = _driver(client, db)
    load, dock = _load_for(db, account)
    stop = _overnight_stop(db, account, load, dock)
    body = {"stop_id": str(stop.id), "layover_rate_cents": 12000}

    first = client.post("/accessorial/layover", json=body, headers=headers)
    second = client.post("/accessorial/layover", json=body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"]["receivable_ref"] == first.json()["receivable_ref"]
    assert _claims(db) == 1
    assert len(ledger.list_receivables(db, account.id)) == 1


def test_a_second_stop_gets_its_own_layover(client, db):
    """The key is the STOP, not the load — two overnights on one route are two claims."""
    account, headers = _driver(client, db)
    load, dock = _load_for(db, account)
    first_stop = _overnight_stop(db, account, load, dock)
    other_dock = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Second Dock", 32.80, -96.81
    )
    second_stop = loads.add_stop(
        db, load, other_dock.id, loads.StopType.delivery,
        appointment_start=datetime(2026, 7, 22, 22, 0, tzinfo=UTC),
    )
    location.arm_geofence(db, account.id, other_dock.id)
    location.evaluate_ping(
        db, account.id, 32.80, -96.81, occurred_at=datetime(2026, 7, 22, 23, 0, tzinfo=UTC)
    )
    location.evaluate_ping(db, account.id, *FAR, occurred_at=datetime(2026, 7, 23, 8, 0, tzinfo=UTC))
    db.flush()

    a = client.post(
        "/accessorial/layover",
        json={"stop_id": str(first_stop.id), "layover_rate_cents": 12000}, headers=headers,
    )
    b = client.post(
        "/accessorial/layover",
        json={"stop_id": str(second_stop.id), "layover_rate_cents": 12000}, headers=headers,
    )

    assert a.status_code == 201 and b.status_code == 201
    assert _claims(db) == 2


def test_no_orphan_claim_survives_a_conflict(client, db):
    """The savepoint's whole job: a losing filing must leave NOTHING behind.

    Without it the claim row is inserted, the receivable insert violates the unique index,
    and the claim survives the failed request — a filed-looking accessorial with no
    receivable, sitting on the driver's own money screen.
    """
    account, headers = _driver(client, db)
    load, _ = _load_for(db, account)
    body = {"load_id": str(load.id), "amount_cents": 15000}
    client.post("/accessorial/tonu", json=body, headers=headers)

    for _ in range(3):
        assert client.post("/accessorial/tonu", json=body, headers=headers).status_code == 409

    assert _claims(db) == 1
    assert db.query(AccessorialClaim).filter(AccessorialClaim.receivable_ref.is_(None)).count() == 0


def test_lumper_is_deliberately_not_deduped(client, db):
    """A DECISION, pinned so it cannot become an accident.

    Multiple lumper fees per load are legitimate — one per stop — and this route carries no
    stop to key on. A key built on the load alone would silently refuse a driver's second
    real receipt. The per-stop shape is a recorded follow-up.
    """
    account, headers = _driver(client, db)
    load, _ = _load_for(db, account)
    body = {"load_id": str(load.id), "amount_cents": 9000}

    first = client.post("/accessorial/lumper", json=body, headers=headers)
    second = client.post("/accessorial/lumper", json=body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["claim_id"] != second.json()["claim_id"]
    assert _claims(db) == 2
