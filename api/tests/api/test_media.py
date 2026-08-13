"""AI-CONTEXT: image bytes an `<img src>` can load, and what that had to buy.

`fetchEvidencePhoto` fetched with an Authorization header, read a Blob and built an object
URL — it had to, because an `<img>` cannot carry a header. Every expensive thing about the
contact sheets followed from that one constraint: no `loading="lazy"` (there is no `src`
to defer), no progressive decode, every byte through JS memory, and — because the natural
way to write it is a loop — `await`ed one full-size photograph at a time. The nested
version in `LoadRecordSurface` fetched stops × photos in series.

So the URL carries its own authority. These tests hold the three things that makes safe:
the signature is checked, it expires, and a URL minted for one image cannot be edited into
another. Plus the cache header the evidence route never had — it set NONE, so every scroll
past a contact sheet re-downloaded every photograph.
"""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api import media
from app.api.deps import get_db
from app.foundation.f06_documents import public as documents
from app.main import app


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def account(db):
    from app.foundation.f01_identity import public as identity

    return identity.register_account(db, "media@example.com", "pw-123456")


@pytest.fixture
def doc(db, account):
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (900, 600), (40, 80, 160)).save(buf, format="JPEG")
    document = documents.store_document(
        db,
        account_id=account.id,
        doc_type=documents.DocType.bol,
        content=buf.getvalue(),
        filename="bol.jpg",
        content_type="image/jpeg",
    )
    db.commit()
    return document


class TestTheUrlIsALoadableImage:
    def test_it_serves_the_bytes_with_no_session_at_all(self, client, doc):
        # the whole point: an <img> sends no Authorization header, and this has to work
        # anyway or nothing about the read path improves
        url = media.media_url(media.KIND_DOCUMENT, doc.id, media.SIZE_FULL)

        res = client.get(url)

        assert res.status_code == 200, res.text
        assert res.headers["content-type"].startswith("image/")
        assert len(res.content) > 0

    def test_it_is_cached_hard_because_the_bytes_never_change(self, client, doc):
        # the evidence photo route set NO cache header at all, so every scroll past a
        # contact sheet re-downloaded every photograph. An artifact is appended to a hash
        # chain and never edited, so an immutable year is correct — and `private`,
        # because these are one driver's evidence and must not sit in a shared proxy.
        res = client.get(media.media_url(media.KIND_DOCUMENT, doc.id, media.SIZE_FULL))

        cache = res.headers["cache-control"]
        assert "immutable" in cache
        assert "private" in cache
        assert "max-age=31536000" in cache

    def test_the_thumb_falls_back_to_the_original_until_the_job_has_run(self, client, doc):
        # the derivative job runs every five minutes; a photograph taken thirty seconds
        # ago has no thumbnail yet. Falling back is what makes this safe to ship ahead of
        # the backfill — a contact sheet is briefly as slow as it always was, not empty.
        res = client.get(media.media_url(media.KIND_DOCUMENT, doc.id, media.SIZE_THUMB))

        assert res.status_code == 200
        assert len(res.content) > 0

    def test_the_thumb_is_served_once_the_derivative_exists(self, client, db, doc):
        from app.ingest import runners

        runners.run_image_thumbnails(db)

        full = client.get(media.media_url(media.KIND_DOCUMENT, doc.id, media.SIZE_FULL))
        thumb = client.get(media.media_url(media.KIND_DOCUMENT, doc.id, media.SIZE_THUMB))

        assert thumb.status_code == 200
        # the reason any of this exists
        assert len(thumb.content) < len(full.content)


class TestTheCapabilityHasEdges:
    def test_an_unsigned_url_is_refused(self, client, doc):
        res = client.get(f"/media/document/{doc.id}?size=full&exp={int(time.time()) + 60}&sig=nope")

        assert res.status_code == 403

    def test_an_expired_url_is_refused(self, client, doc):
        url = media.media_url(media.KIND_DOCUMENT, doc.id, media.SIZE_FULL, ttl=-10)

        res = client.get(url)

        # 403 rather than 404 so the client can tell "ask for a fresh link" from
        # "there is no such image"
        assert res.status_code == 403

    def test_a_signature_cannot_be_moved_to_another_image(self, client, doc):
        # the signature covers the ref, so a driver cannot edit the id in a URL they
        # legitimately hold and read somebody else's evidence
        url = media.media_url(media.KIND_DOCUMENT, doc.id, media.SIZE_FULL)
        other = uuid.uuid4()
        tampered = url.replace(str(doc.id), str(other))

        assert client.get(tampered).status_code == 403

    def test_a_signature_cannot_be_moved_to_another_size(self, client, doc):
        # size is in the payload too: a thumb capability must not become a full-resolution
        # one by editing a query parameter
        url = media.media_url(media.KIND_DOCUMENT, doc.id, media.SIZE_THUMB)

        assert client.get(url.replace("size=thumb", "size=full")).status_code == 403

    def test_an_unknown_size_is_refused(self, client, doc):
        url = media.media_url(media.KIND_DOCUMENT, doc.id, media.SIZE_FULL)

        assert client.get(url.replace("size=full", "size=enormous")).status_code in (400, 403)

    def test_a_valid_signature_for_a_missing_image_is_a_404(self, client):
        url = media.media_url(media.KIND_DOCUMENT, uuid.uuid4(), media.SIZE_FULL)

        assert client.get(url).status_code == 404


class TestTheContactSheetsAreHandedUrls:
    def test_the_evidence_payload_carries_a_thumb_url_per_photo(self, client, db, account):
        from app.foundation.f02_facility import public as facility
        from app.foundation.f05_load import public as loads

        token = client.post(
            "/auth/login", json={"email": "media@example.com", "password": "pw-123456"}
        ).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        fac = facility.create_facility(
            db, facility.FacilityType.shipper_receiver, "Dock", 32.7767, -96.797
        )
        load = loads.create_load(db, account.id)
        stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery)
        capture = client.post(
            "/protection/condition/start",
            headers=headers,
            json={"stop_id": str(stop.id), "phase": "delivery"},
        ).json()
        import base64
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (400, 300), (10, 10, 10)).save(buf, format="JPEG")
        client.post(
            f"/protection/condition/{capture['capture_id']}/photo",
            headers=headers,
            json={
                "prompt": "trailer_exterior",
                "content_b64": base64.b64encode(buf.getvalue()).decode(),
                "content_type": "image/jpeg",
            },
        )

        res = client.get(f"/load/{stop.id}/evidence", headers=headers)

        photos = res.json()["photos"]
        assert photos, "the stop must report its photographs"
        assert photos[0]["thumb_url"].startswith("/media/evidence/")
        # and the URL it hands over actually works, with no session
        assert client.get(photos[0]["thumb_url"]).status_code == 200
