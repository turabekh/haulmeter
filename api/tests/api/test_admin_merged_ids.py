"""AI-CONTEXT: an admin URL and a driver URL for the same id must answer about the
same place. Carried debt since the first merge repair, named by A9 §5, and this
session made it 95 rows larger.

`canonical_facility_id` has existed since §23's merged-id fix and is applied to every
driver-facing route. It was never carried across to `/admin/facilities/*` — the eighth
instance this session of a mechanism fixed in one place and not the others.

The cost is not theoretical. An admin editing a merged id edits the SHADOW: the patch
is recorded, the audit log says it happened, and the map shows the old value forever,
because the row they edited is one nothing renders.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.main import app

SEATTLE = (47.6062, -122.3321)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _admin_headers(client, db):
    import uuid

    from app.foundation.f01_identity.domain.models import Account

    resp = client.post(
        "/auth/register", json={"email": "ops@example.com", "password": "pw-123456"}
    )
    account = db.get(Account, uuid.UUID(resp.json()["account_id"]))
    identity.attach_role(db, account, identity.Role.platform_admin)
    db.flush()
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _merged_pair(db):
    canonical = facility.create_facility(
        db, facility.FacilityType.truck_stop, "Flying J Travel Center", *SEATTLE
    )
    shadow = facility.create_facility(
        db, facility.FacilityType.fuel_station, "Pilot", SEATTLE[0] + 0.0005, SEATTLE[1]
    )
    facility.merge_facilities(db, canonical, shadow)
    return canonical, shadow


def test_editing_a_merged_id_edits_the_site_that_still_renders(db, client):
    canonical, shadow = _merged_pair(db)
    headers = _admin_headers(client, db)

    resp = client.patch(
        f"/admin/facilities/{shadow.id}", json={"address": "1 Dock Road"}, headers=headers
    )
    assert resp.status_code == 200
    db.refresh(canonical)
    db.refresh(shadow)
    assert canonical.address == "1 Dock Road", "the edit landed on a row nothing renders"
    assert shadow.address is None


def test_asking_a_merged_id_for_duplicates_asks_about_the_real_site(db, client):
    """The first version of this asserted only that the shadow is absent from its own
    suggestions — which is true whether or not the id resolves, because merged rows are
    never candidates. It passed against the broken code and proved nothing.

    The property is that BOTH ids answer about the same place: the suggestions are
    computed from the facility's name and coordinates, and a shadow has different ones."""
    canonical, shadow = _merged_pair(db)
    facility.create_facility(
        db, facility.FacilityType.truck_stop, "Flying J Travel Center", SEATTLE[0] + 0.0002,
        SEATTLE[1],
    )
    headers = _admin_headers(client, db)

    via_shadow = client.get(f"/admin/facilities/{shadow.id}/duplicates", headers=headers)
    via_canonical = client.get(f"/admin/facilities/{canonical.id}/duplicates", headers=headers)
    assert via_shadow.status_code == 200
    assert [r["facility_id"] for r in via_shadow.json()] == [
        r["facility_id"] for r in via_canonical.json()
    ]
    assert via_canonical.json(), "the fixture must actually have a duplicate to find"


def test_merging_into_a_merged_id_lands_on_the_canonical(db, client):
    canonical, shadow = _merged_pair(db)
    other = facility.create_facility(
        db, facility.FacilityType.truck_stop, "Roadside Diesel", SEATTLE[0] + 0.002, SEATTLE[1]
    )
    headers = _admin_headers(client, db)

    resp = client.post(
        f"/admin/facilities/{shadow.id}/merge",
        json={"duplicate_id": str(other.id)},
        headers=headers,
    )
    assert resp.status_code == 200
    db.refresh(other)
    # NOTE: `merge_facilities` also resolves, so this holds even without the route's
    # dependency — it is defence in depth, not the route's proof. The route's own proof
    # is the response BODY naming the canonical site.
    assert other.merged_into_id == canonical.id, "a merge must not chain onto a shadow"
    assert resp.json()["name"] == "Flying J Travel Center"
