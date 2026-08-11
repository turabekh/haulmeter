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
from app.foundation.f04_evidence import public as evidence
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


# --- FR3: producing the credential, not a claim about it ---
def _file_doc(client, headers, doc_type="cdl", expires="2028-01-17"):
    return client.post(
        "/protection/documents",
        json={
            "doc_type": doc_type,
            "content_b64": base64.b64encode(b"\x89PNG\r\n\x1a\n-cdl-scan").decode(),
            "filename": f"{doc_type}.png",
            "content_type": "image/png",
            "expires_on": expires,
        },
        headers=headers,
    ).json()["document_id"]


def test_a_driver_can_see_the_document_they_filed(client, db):
    """Inspection mode exists to PRODUCE a credential. A row reading "CDL ·
    2028-01-17" is our claim that the driver holds one, not the document — and
    asserting on their behalf to a police officer is the worst possible audience for
    that."""
    headers = _headers(client, "viewdoc@example.com")
    doc_id = _file_doc(client, headers)

    resp = client.get(f"/protection/documents/{doc_id}", headers=headers)

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content.startswith(b"\x89PNG")


def test_the_bytes_are_cached_hard_because_a_scale_house_is_a_dead_zone(client, db):
    """A document that needs the network to render is a document you cannot produce
    when you are asked for it. The bytes are immutable — a document is replaced,
    never edited — so a long cache is safe as well as necessary."""
    headers = _headers(client, "cachedoc@example.com")
    doc_id = _file_doc(client, headers)

    resp = client.get(f"/protection/documents/{doc_id}", headers=headers)

    assert "immutable" in resp.headers.get("cache-control", "")
    assert "private" in resp.headers.get("cache-control", "")


def test_another_driver_cannot_read_your_credential(client, db):
    """A CDL is the most identifying document a driver carries."""
    mine = _headers(client, "mydoc@example.com")
    theirs = _headers(client, "theirdoc@example.com")
    doc_id = _file_doc(client, mine)

    assert client.get(f"/protection/documents/{doc_id}", headers=theirs).status_code == 404


def test_a_stranger_id_is_indistinguishable_from_a_missing_one(client, db):
    """Both 404, so a caller cannot probe ids to learn which documents exist."""
    headers = _headers(client, "probedoc@example.com")
    missing = "11111111-2222-3333-4444-555555555555"

    assert client.get(f"/protection/documents/{missing}", headers=headers).status_code == 404


# --- FR3: removal that is not a delete, and the archive it goes to ---
def test_removing_a_document_takes_it_out_of_the_wallet_and_into_the_archive(client, db):
    """The driver's "delete". §17 Q16 forbids destroying it, so what changes is which
    document the wallet PRODUCES — and it says why it is in the archive."""
    headers = _headers(client, "rm-doc@example.com")
    doc_id = _file_doc(client, headers, doc_type="permit")

    resp = client.post(f"/protection/documents/{doc_id}/archive", headers=headers)
    assert resp.status_code == 200

    wallet = client.get("/protection/wallet", headers=headers).json()
    assert wallet["documents"] == []
    assert wallet["archived_count"] == 1
    archived = client.get("/protection/documents/archive", headers=headers).json()["documents"]
    assert [(r["id"], r["reason"]) for r in archived] == [(doc_id, "removed_by_driver")]


def test_a_removed_document_still_opens(client, db):
    """It is still the answer to "what were you carrying at that inspection in March".
    A record kept forever that its owner cannot read is not kept for their benefit."""
    headers = _headers(client, "rm-open@example.com")
    doc_id = _file_doc(client, headers, doc_type="permit")
    client.post(f"/protection/documents/{doc_id}/archive", headers=headers)

    resp = client.get(f"/protection/documents/{doc_id}", headers=headers)

    assert resp.status_code == 200
    assert resp.content.startswith(b"\x89PNG")


def test_restoring_a_removed_document_puts_it_back(client, db):
    headers = _headers(client, "restore-doc@example.com")
    doc_id = _file_doc(client, headers, doc_type="permit")
    client.post(f"/protection/documents/{doc_id}/archive", headers=headers)

    resp = client.post(f"/protection/documents/{doc_id}/restore", headers=headers)
    assert resp.status_code == 200

    wallet = client.get("/protection/wallet", headers=headers).json()
    assert [d["id"] for d in wallet["documents"]] == [doc_id]
    assert wallet["archived_count"] == 0


def test_a_restore_that_would_show_two_current_licences_is_refused_by_name(client, db):
    """Two live CDLs is a question about which is current, asked at a roadside
    inspection. The refusal names what is in the way rather than saying no."""
    headers = _headers(client, "two-cdl-api@example.com")
    old_id = _file_doc(client, headers, doc_type="cdl", expires="2027-01-17")
    _file_doc(client, headers, doc_type="cdl", expires="2031-01-17")

    resp = client.post(f"/protection/documents/{old_id}/restore", headers=headers)

    assert resp.status_code == 409
    assert "cdl" in resp.json()["detail"]


def test_a_replayed_removal_from_a_dead_zone_succeeds_twice(client, db):
    """F12 replays a write made with no signal. A second archive must not fail."""
    headers = _headers(client, "replay-api@example.com")
    doc_id = _file_doc(client, headers, doc_type="permit")

    first = client.post(f"/protection/documents/{doc_id}/archive", headers=headers)
    second = client.post(f"/protection/documents/{doc_id}/archive", headers=headers)

    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json()["archived_at"] == second.json()["archived_at"]


def test_another_driver_cannot_remove_your_credential(client, db):
    """And a stranger's id 404s exactly like a missing one, so ids cannot be probed."""
    mine = _headers(client, "mine-api@example.com")
    theirs = _headers(client, "theirs-api@example.com")
    doc_id = _file_doc(client, mine)

    assert client.post(f"/protection/documents/{doc_id}/archive", headers=theirs).status_code == 404
    assert client.get("/protection/wallet", headers=mine).json()["archived_count"] == 0


def test_the_archive_route_is_not_swallowed_by_the_document_id_route(client, db):
    """FastAPI matches in declaration order and `{document_id}` is a UUID, so a later
    /documents/archive would be rejected as a malformed id instead of served."""
    headers = _headers(client, "route-order@example.com")

    resp = client.get("/protection/documents/archive", headers=headers)

    assert resp.status_code == 200
    assert resp.json() == {"documents": []}


# --- D8: the driver can see what they have handed out ---
def _shared_incident(client, headers):
    incident_id = client.post(
        "/protection/incident", json={"kind": "dispute"}, headers=headers
    ).json()["incident_id"]
    shared = client.post(
        f"/protection/incident/{incident_id}/share", json={}, headers=headers
    ).json()
    return shared


def _log_of(db, share_id):
    import uuid as _uuid

    return db.get(evidence.SharedPack, _uuid.UUID(share_id)).log_id


def test_a_driver_can_list_the_links_for_one_log(client, db):
    """Extend and revoke existed since sharing shipped; nothing could LIST them.

    So the controls were reachable only by someone already holding a share id, which no
    screen ever showed — a driver could send a broker a link to their own evidence and
    then have no way to see that they had.
    """
    headers = _headers(client, "list-a@example.com")
    shared = _shared_incident(client, headers)
    log_ref = _log_of(db, shared["share_id"])

    listed = client.get("/protection/share", params={"log_ref": str(log_ref)}, headers=headers)

    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["share_id"] == shared["share_id"]
    assert rows[0]["revoked"] is False
    assert rows[0]["opened_count"] == 0
    assert rows[0]["expires_at"] is not None


def test_the_list_is_scoped_to_the_caller(client, db):
    headers = _headers(client, "list-b@example.com")
    shared = _shared_incident(client, headers)
    log_ref = _log_of(db, shared["share_id"])
    theirs = _headers(client, "nosy@example.com")

    rows = client.get(
        "/protection/share", params={"log_ref": str(log_ref)}, headers=theirs
    ).json()

    assert rows == []


def test_a_revoked_link_is_listed_as_revoked_not_hidden(client, db):
    """Revocation is a fact about a document that was sent; it is not an undo."""
    headers = _headers(client, "list-c@example.com")
    shared = _shared_incident(client, headers)
    log_ref = _log_of(db, shared["share_id"])

    client.delete(f"/protection/share/{shared['share_id']}", headers=headers)
    rows = client.get(
        "/protection/share", params={"log_ref": str(log_ref)}, headers=headers
    ).json()

    assert len(rows) == 1
    assert rows[0]["revoked"] is True
    assert rows[0]["revoked_at"] is not None


def test_the_open_count_is_reported_for_the_screen_to_caveat(client, db):
    """The number is honest; the SCREEN says a scanner may be part of it (F4-1)."""
    headers = _headers(client, "list-d@example.com")
    shared = _shared_incident(client, headers)
    log_ref = _log_of(db, shared["share_id"])

    client.get(shared["url"])
    client.get(shared["url"])
    rows = client.get(
        "/protection/share", params={"log_ref": str(log_ref)}, headers=headers
    ).json()

    assert rows[0]["opened_count"] == 2
    assert rows[0]["last_opened_at"] is not None
