"""AI-CONTEXT: M5-FR2's "one-tap condition report export" and FR4's "shareable pack".

Both FRs used the word and neither had an HTTP surface: `incident_pack` returned a
dataclass and a test called it shareable. These are the endpoints that make the words
true, and the distinction they encode is the important part:

**EXPORT is a view. SHARE is a record.** Export regenerates from the chain and is
always current, which is right for the driver's own copy. Share pins the bytes,
because in a dispute nobody asks what the pack says now — they ask what was sent.
"""

import base64
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.foundation.f05_load import public as loads
from app.main import app

T0 = datetime(2026, 7, 20, 7, 58, tzinfo=UTC)
DALLAS = (32.7767, -96.7970)
PHOTO = base64.b64encode(b"a-trailer-photo").decode()


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


def _stop(db, account_id):
    fac = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Dallas Receiving", *DALLAS
    )
    load = loads.create_load(db, account_id, reference_number="4471")
    return loads.add_stop(
        db,
        load,
        fac.id,
        loads.StopType.delivery,
        sequence=1,
        appointment_start=T0,
        appointment_end=T0 + timedelta(hours=1),
    )


def _capture(client, db, headers, stop, photos=2):
    capture_id = client.post(
        "/protection/condition/start",
        json={"stop_id": str(stop.id), "phase": "pickup"},
        headers=headers,
    ).json()["capture_id"]
    for prompt in ("trailer_exterior", "seals")[:photos]:
        client.post(
            f"/protection/condition/{capture_id}/photo",
            json={"prompt": prompt, "content_b64": PHOTO, "content_type": "image/jpeg"},
            headers=headers,
        )
    return capture_id


def test_a_condition_report_exports_as_a_real_pdf(client, db):
    headers = _headers(client, "export-a@example.com")
    account_id = client.get("/auth/me", headers=headers).json()["account_id"]
    stop = _stop(db, account_id)
    _capture(client, db, headers, stop)

    resp = client.get(f"/protection/condition/{stop.id}/export", headers=headers)

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"
    assert b"Cargo condition report" in resp.content


def test_an_incident_pack_calls_itself_an_incident(client, db):
    """It composed `cargo_condition`, so a pack about an accident announced itself as
    a cargo condition report — wrong on the first line a clerk reads."""
    headers = _headers(client, "export-b@example.com")
    incident_id = client.post(
        "/protection/incident",
        json={"kind": "cargo_damage", "note": "corner crushed on arrival"},
        headers=headers,
    ).json()["incident_id"]

    resp = client.get(f"/protection/incident/{incident_id}/export", headers=headers)

    assert resp.content[:5] == b"%PDF-"
    assert b"Incident report" in resp.content
    assert b"Cargo condition report" not in resp.content


def test_a_stop_with_no_capture_has_nothing_to_export(client, db):
    headers = _headers(client, "export-c@example.com")
    account_id = client.get("/auth/me", headers=headers).json()["account_id"]
    stop = _stop(db, account_id)

    assert client.get(f"/protection/condition/{stop.id}/export", headers=headers).status_code == 404


def test_another_driver_cannot_export_your_incident(client, db):
    mine = _headers(client, "export-d@example.com")
    theirs = _headers(client, "export-e@example.com")
    incident_id = client.post(
        "/protection/incident", json={"kind": "dispute"}, headers=mine
    ).json()["incident_id"]

    assert (
        client.get(f"/protection/incident/{incident_id}/export", headers=theirs).status_code == 404
    )


def test_sharing_returns_one_link_and_it_opens_without_a_session(client, db):
    """§17: counterparty mail is plain, short, professional, ONE link, no images. An
    AP clerk will not create an account to read what a driver sent them."""
    headers = _headers(client, "share-a@example.com")
    incident_id = client.post(
        "/protection/incident", json={"kind": "cargo_damage"}, headers=headers
    ).json()["incident_id"]

    shared = client.post(
        f"/protection/incident/{incident_id}/share",
        json={"recipient": "ap@acme.example"},
        headers=headers,
    )
    assert shared.status_code == 201
    body = shared.json()
    assert body["url"].startswith("/pack/s/")
    assert len(body["content_hash"]) == 64

    # no Authorization header at all
    opened = client.get(body["url"])
    assert opened.status_code == 200
    assert opened.content[:5] == b"%PDF-"


def test_the_link_serves_what_was_sent_even_after_more_evidence_lands(client, db):
    headers = _headers(client, "share-b@example.com")
    account_id = client.get("/auth/me", headers=headers).json()["account_id"]
    stop = _stop(db, account_id)
    capture_id = _capture(client, db, headers, stop)

    url = client.post(f"/protection/condition/{stop.id}/share", json={}, headers=headers).json()[
        "url"
    ]
    sent = client.get(url).content

    # another photo arrives afterwards
    client.post(
        f"/protection/condition/{capture_id}/photo",
        json={"prompt": "load_blocking", "content_b64": PHOTO, "content_type": "image/jpeg"},
        headers=headers,
    )
    regenerated = client.get(f"/protection/condition/{stop.id}/export", headers=headers).content

    assert regenerated != sent, "the export really did change"
    assert client.get(url).content == sent, "the share must not have"


def test_revoking_closes_the_link(client, db):
    headers = _headers(client, "share-c@example.com")
    incident_id = client.post(
        "/protection/incident", json={"kind": "dispute"}, headers=headers
    ).json()["incident_id"]
    shared = client.post(
        f"/protection/incident/{incident_id}/share", json={}, headers=headers
    ).json()
    assert client.get(shared["url"]).status_code == 200

    revoked = client.delete(f"/protection/share/{shared['share_id']}", headers=headers)

    assert revoked.status_code == 200
    # the record of what was sent survives the decision to stop hosting it
    assert revoked.json()["content_hash"] == shared["content_hash"]
    assert client.get(shared["url"]).status_code == 404


def test_a_stranger_cannot_revoke_your_share(client, db):
    mine = _headers(client, "share-d@example.com")
    theirs = _headers(client, "share-e@example.com")
    incident_id = client.post(
        "/protection/incident", json={"kind": "dispute"}, headers=mine
    ).json()["incident_id"]
    shared = client.post(f"/protection/incident/{incident_id}/share", json={}, headers=mine).json()

    assert (
        client.delete(f"/protection/share/{shared['share_id']}", headers=theirs).status_code == 404
    )
    assert client.get(shared["url"]).status_code == 200


def test_an_unknown_token_is_the_same_404_as_a_revoked_one(client, db):
    assert client.get("/pack/s/never-existed-at-all").status_code == 404


def test_the_report_names_which_shot_each_photo_is(client, db):
    """Caught by opening the document. A guided sequence exists so a clerk can tell
    whether the SEALS were photographed; the report read "Photo · Photo · Photo"
    because the prompt lived in the artifact's exif and never reached the chained
    record. A claim about what an image shows belongs in the chain with it."""
    headers = _headers(client, "prompts@example.com")
    account_id = client.get("/auth/me", headers=headers).json()["account_id"]
    stop = _stop(db, account_id)
    _capture(client, db, headers, stop)

    content = client.get(f"/protection/condition/{stop.id}/export", headers=headers).content

    assert b"trailer exterior" in content
    assert b"seals" in content


def test_the_report_names_the_facility_and_the_load(client, db):
    """Also caught by opening it: a condition report with no parties on it is a photo
    album. The reader did not take the pictures."""
    headers = _headers(client, "context@example.com")
    account_id = client.get("/auth/me", headers=headers).json()["account_id"]
    stop = _stop(db, account_id)
    _capture(client, db, headers, stop)

    content = client.get(f"/protection/condition/{stop.id}/export", headers=headers).content

    assert b"Dallas Receiving" in content
    assert b"4471" in content
