"""AI-CONTEXT: decision 7 — console-native facility management.

The rule that makes this safe: **an admin edit is another SOURCE, not an overwrite.**
It goes through the same F2 pipeline every ingest uses, so what NTAD/OSM/TPIMS
recorded keeps its provenance and the existing priority and union rules decide the
canonical value.

That matters because the alternative is quietly corrosive: an operator fixing a
typo would silently destroy a feed's claim, the next ingest would restore it, and
nobody would understand why the correction kept reverting. Routing the edit through
the pipeline means the two facts coexist and the rules — already written, already
tested — arbitrate.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f01_identity.domain.models import Account
from app.foundation.f02_facility import public as facility
from app.main import app

JOPLIN = (37.084, -94.513)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _admin(client, db, email="ops@example.com"):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    identity.attach_role(
        db, db.get(Account, uuid.UUID(resp.json()["account_id"])), identity.Role.platform_admin
    )
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _ingested(db, name="Gateway Truck Service", services=None, capacity=None):
    """A facility as ingestion would have created it — an OSM source with its own
    claim on the attributes."""
    record = facility.StagedRecord(
        source_kind=facility.SourceKind.osm,
        external_ref=f"node/{name}",
        name=name,
        lat=JOPLIN[0],
        lon=JOPLIN[1],
        facility_type=facility.FacilityType.repair,
        attributes={"services": services or [facility.SERVICE_TIRE], "capacity": capacity},
    )
    fac, _ = facility.upsert_record(db, record, batch_id="osm-test")
    return fac


# --- the provenance rule ---
def test_an_admin_edit_adds_a_source_rather_than_replacing_one(client, db):
    headers = _admin(client, db)
    fac = _ingested(db)
    assert "osm" in _sources(db, fac)

    client.patch(
        f"/admin/facilities/{fac.id}",
        json={"services": [facility.SERVICE_TOWING]},
        headers=headers,
    )

    # both claims survive; the admin edit is a source alongside the feed
    assert {"osm", "admin"} <= set(_sources(db, fac))


def _sources(db, fac) -> list[str]:
    db.refresh(fac)
    return [s.source_kind.value for s in fac.sources]


def test_an_admin_edit_cannot_erase_what_a_feed_recorded(client, db):
    # services union across sources (E3.2), so the ingested fact survives
    headers = _admin(client, db)
    fac = _ingested(db, services=[facility.SERVICE_TIRE, facility.SERVICE_WASH])

    resp = client.patch(
        f"/admin/facilities/{fac.id}",
        json={"services": [facility.SERVICE_TOWING]},
        headers=headers,
    )

    services = set(resp.json()["attributes"]["services"])
    assert services == {facility.SERVICE_TIRE, facility.SERVICE_WASH, facility.SERVICE_TOWING}


def test_the_editor_shows_which_feeds_already_claim_a_facility(client, db):
    # an operator about to edit should see who else has a claim on it
    headers = _admin(client, db)
    _ingested(db)
    body = client.get("/admin/facilities?q=Gateway", headers=headers).json()[0]
    assert "osm" in body["sources"]


# --- create ---
def test_creating_a_facility_records_it_as_an_admin_source(client, db):
    headers = _admin(client, db)
    resp = client.post(
        "/admin/facilities",
        json={
            "name": "Manual Truck Stop",
            "facility_type": "truck_stop",
            "lat": 32.7,
            "lon": -96.8,
            "services": ["tire"],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["sources"] == ["admin"]
    assert resp.json()["attributes"]["services"] == ["tire"]


def test_a_facility_can_be_marked_dev_so_purge_demo_can_reach_it(client, db):
    headers = _admin(client, db)
    resp = client.post(
        "/admin/facilities",
        json={
            "name": "DEV — Test Stop",
            "facility_type": "truck_stop",
            "lat": 32.7,
            "lon": -96.8,
            "is_dev": True,
        },
        headers=headers,
    )
    assert resp.json()["is_dev"] is True


def test_an_unknown_facility_type_is_refused(client, db):
    headers = _admin(client, db)
    resp = client.post(
        "/admin/facilities",
        json={"name": "X", "facility_type": "spaceport", "lat": 0, "lon": 0},
        headers=headers,
    )
    assert resp.status_code == 422


# --- merge ---
def test_merging_moves_the_duplicates_sources_and_keeps_it_resolvable(client, db):
    # the duplicate is marked merged, never deleted, so a stale reference still
    # resolves to the canonical record
    headers = _admin(client, db)
    canonical = _ingested(db, "Gateway Truck Service")
    duplicate = facility.create_facility(
        db, facility.FacilityType.repair, "Gateway Truck Svc", 37.0841, -94.5131
    )

    resp = client.post(
        f"/admin/facilities/{canonical.id}/merge",
        json={"duplicate_id": str(duplicate.id)},
        headers=headers,
    )

    assert resp.status_code == 200
    assert duplicate.status == facility.FacilityStatus.merged
    assert facility.resolve_canonical(db, duplicate.id).id == canonical.id


def test_a_facility_cannot_be_merged_into_itself(client, db):
    headers = _admin(client, db)
    fac = _ingested(db)
    resp = client.post(
        f"/admin/facilities/{fac.id}/merge",
        json={"duplicate_id": str(fac.id)},
        headers=headers,
    )
    assert resp.status_code == 422


def test_duplicate_candidates_use_the_same_rules_the_pipeline_uses(client, db):
    # what an operator is shown is what the pipeline itself would have matched
    headers = _admin(client, db)
    canonical = _ingested(db, "Gateway Truck Service")
    facility.create_facility(
        db, facility.FacilityType.repair, "Gateway Truck Service", 37.0841, -94.5131
    )

    candidates = client.get(f"/admin/facilities/{canonical.id}/duplicates", headers=headers).json()
    assert candidates
    assert canonical.id not in [uuid.UUID(c["facility_id"]) for c in candidates]


# --- audit + access ---
def test_every_facility_mutation_is_audited_with_before_and_after(client, db):
    headers = _admin(client, db)
    fac = _ingested(db)
    client.patch(
        f"/admin/facilities/{fac.id}", json={"name": "Gateway Truck Centre"}, headers=headers
    )

    entries = client.get("/admin/audit?action=facility_edit", headers=headers).json()
    assert entries[0]["before"]["name"] == "Gateway Truck Service"
    assert entries[0]["after"]["name"] == "Gateway Truck Centre"


def test_the_facility_editor_requires_admin(client, db):
    resp = client.post("/auth/register", json={"email": "driver@x.com", "password": "pw-123456"})
    headers = {"Authorization": f"Bearer {resp.json()['token']}"}
    assert client.get("/admin/facilities", headers=headers).status_code == 403
    assert (
        client.post(
            "/admin/facilities",
            json={"name": "X", "facility_type": "truck_stop", "lat": 0, "lon": 0},
            headers=headers,
        ).status_code
        == 403
    )


def test_there_is_no_facility_delete_endpoint():
    # facilities are referenced by claims, evidence and beliefs; merging is the
    # answer to a duplicate, deletion is not
    spec = app.openapi()["paths"]
    for path, methods in spec.items():
        if path.startswith("/admin/facilities"):
            assert "delete" not in {m.lower() for m in methods}
