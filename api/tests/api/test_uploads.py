"""AI-CONTEXT: the upload seam — both wire formats, and the ceiling that never existed.

Six endpoints each built their own `base64.b64decode(body.content_b64)`, and not one of
them checked a size. `f06_documents.service` has recorded `byte_size=len(content)` since
it was written and nothing anywhere compared it to anything, so the limit on a document
was whatever the box could decode into memory — and a base64 body is decoded before any
handler runs.

Two formats are supported on purpose and only one is the future. The app sends multipart
now, because base64 inflates a photograph by a third over the LTE of a truck stop. But a
phone that queued a capture under an OLDER build still holds that row in localStorage, and
its opId is the F12 idempotency key that makes the replay exactly-once — refusing it would
discard a driver's evidence for having been captured before a deploy.
"""

import base64
import io
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.core.config import get_settings
from app.foundation.f06_documents import public as documents
from app.main import app

JPEG = b"\xff\xd8\xff\xe0" + b"longhaul test frame " * 64


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


def _multipart(fields: dict, content: bytes, filename="bol.jpg", content_type="image/jpeg"):
    import json

    return {
        "data": {"fields": json.dumps(fields)},
        "files": {"file": (filename, io.BytesIO(content), content_type)},
    }


class TestTheAppSendsBytes:
    def test_a_document_uploaded_as_multipart_is_stored_byte_for_byte(self, client, db):
        headers = _headers(client, "multipart@example.com")
        part = _multipart({"doc_type": "bol"}, JPEG)

        res = client.post("/protection/documents", headers=headers, **part)

        assert res.status_code == 201, res.text
        doc = db.get(documents.Document, uuid.UUID(res.json()["document_id"]))
        # the whole point: what the camera produced is what F6 holds. A truncated or
        # re-encoded evidence photo is a detention claim argued from the wrong document.
        assert documents.get_document_bytes(db, doc) == JPEG

    def test_the_browsers_content_type_and_filename_survive_the_trip(self, client, db):
        headers = _headers(client, "meta@example.com")
        part = _multipart({"doc_type": "bol"}, JPEG, filename="dock-7.jpg")

        res = client.post("/protection/documents", headers=headers, **part)

        doc = db.get(documents.Document, uuid.UUID(res.json()["document_id"]))
        # F6 serves this value straight back to an <img>, so a wrong one renders as a
        # broken image on the screen an officer is being shown
        assert doc.content_type == "image/jpeg"
        assert doc.filename == "dock-7.jpg"

    def test_a_condition_photo_arrives_as_bytes_too(self, client, db):
        # the sharpest of the six upload sites: a guided SEQUENCE, so every byte saved
        # is paid back once per shot rather than once per stop
        from app.foundation.f02_facility import public as facility
        from app.foundation.f05_load import public as loads

        register = client.post(
            "/auth/register", json={"email": "cond@example.com", "password": "pw-123456"}
        ).json()
        headers = {"Authorization": f"Bearer {register['token']}"}
        fac = facility.create_facility(
            db, facility.FacilityType.shipper_receiver, "Receiver", 32.7767, -96.797
        )
        load = loads.create_load(db, uuid.UUID(register["account_id"]))
        stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery)

        capture = client.post(
            "/protection/condition/start",
            headers=headers,
            json={"stop_id": str(stop.id), "phase": "delivery"},
        ).json()

        res = client.post(
            f"/protection/condition/{capture['capture_id']}/photo",
            headers=headers,
            **_multipart({"prompt": "trailer_exterior"}, JPEG),
        )

        assert res.status_code == 201, res.text


class TestAReplayFromAnOlderBuildStillLands:
    def test_the_base64_json_body_is_still_accepted(self, client, db):
        # a capture queued before the deploy. Its bytes are in localStorage as base64 and
        # nothing on the phone can turn that row into a multipart request.
        headers = _headers(client, "legacy@example.com")

        res = client.post(
            "/protection/documents",
            headers=headers,
            json={"doc_type": "bol", "content_b64": base64.b64encode(JPEG).decode()},
        )

        assert res.status_code == 201, res.text
        doc = db.get(documents.Document, uuid.UUID(res.json()["document_id"]))
        assert documents.get_document_bytes(db, doc) == JPEG

    def test_both_formats_are_validated_by_the_same_model(self, client):
        # the two paths must not drift into meaning different things. A missing
        # `doc_type` is a 422 whichever way it arrives.
        headers = _headers(client, "sameshape@example.com")

        as_json = client.post(
            "/protection/documents",
            headers=headers,
            json={"content_b64": base64.b64encode(JPEG).decode()},
        )
        as_form = client.post("/protection/documents", headers=headers, **_multipart({}, JPEG))

        assert as_json.status_code == 422
        assert as_form.status_code == 422


@pytest.fixture
def small_ceiling(monkeypatch):
    """AI-CONTEXT: `get_settings` is `lru_cache`d, so `monkeypatch.setenv` alone changes
    nothing — and clearing the cache only on the way OUT leaks a 1 MB ceiling into every
    later test in the session the moment one of these fails. Cleared on both sides."""
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    yield 1 * 1024 * 1024
    monkeypatch.undo()
    get_settings.cache_clear()


class TestTheCeilingThatNeverExisted:
    def test_an_oversize_multipart_upload_is_refused_with_413(self, client, small_ceiling):
        headers = _headers(client, "big@example.com")

        huge = b"x" * (2 * small_ceiling)
        res = client.post(
            "/protection/documents", headers=headers, **_multipart({"doc_type": "bol"}, huge)
        )

        # 413 rather than 400: a driver can act on "this file is too big" and cannot act
        # on "this request is malformed"
        assert res.status_code == 413, res.text

    def test_an_oversize_base64_body_is_refused_before_it_is_decoded(self, client, small_ceiling):
        headers = _headers(client, "bigb64@example.com")

        # the check is on the ENCODED length, so an oversize upload never has to be
        # materialised in memory to be rejected — which is the half that answers the
        # denial of service rather than only the tidiness
        payload = base64.b64encode(b"x" * (2 * small_ceiling)).decode()
        res = client.post(
            "/protection/documents",
            headers=headers,
            json={"doc_type": "bol", "content_b64": payload},
        )

        assert res.status_code == 413, res.text

    def test_a_document_within_the_ceiling_is_untouched(self, client, small_ceiling):
        headers = _headers(client, "ok@example.com")

        res = client.post(
            "/protection/documents", headers=headers, **_multipart({"doc_type": "bol"}, JPEG)
        )

        assert res.status_code == 201, res.text


class TestMalformedInputSaysWhichThingIsWrong:
    def test_garbage_base64_is_a_400_not_a_500(self, client):
        headers = _headers(client, "garbage@example.com")

        res = client.post(
            "/protection/documents",
            headers=headers,
            json={"doc_type": "bol", "content_b64": "not base64 at all!!"},
        )

        assert res.status_code == 400, res.text

    def test_a_document_with_no_content_is_refused(self, client):
        # an empty capture must not become a document row with no bytes, which would
        # read as filed evidence and produce nothing when an officer asks for it
        headers = _headers(client, "empty@example.com")

        res = client.post("/protection/documents", headers=headers, json={"doc_type": "bol"})

        assert res.status_code == 422, res.text
