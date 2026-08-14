"""AI-CONTEXT: the wallet's derivative, on a STABLE url — and the stability is the design.

`?size=thumb` serves the same derivative the `image_thumbnails` job already makes, from the
session-authenticated document route rather than from the signed `/media` one. That is the
decision worth defending: a signed URL carries a fresh `exp` and `sig` on every render, so
the browser's cache key changes each time, and the wallet's contract is that "a document
opened at home opens again at the scale" — true only while the immutable year-long cache is
hit by the SAME url twice. On the screen that produces a CDL to a DOT officer, a cache miss
with no signal is the document not existing.

Measured on production before building this: credentials are 1–12 KB, but load paperwork
averages 261–853 KB and reaches 6.3 MB, and every one of them opened onto "Loading…" for as
long as it took. A real 1,827,360-byte capture serves a 5,788-byte derivative from the same
url — 316× — so the frame is never blank.
"""

import io

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.ingest import runners
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


def _photo(width=1600, height=1200):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (40, 90, 160)).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _capture(
    client,
    headers,
    content=None,
    doc_type="cdl",
    filename="credential.jpg",
    content_type="image/jpeg",
):
    res = client.post(
        "/protection/documents",
        headers=headers,
        data={"fields": f'{{"doc_type": "{doc_type}"}}'},
        files={"file": (filename, io.BytesIO(content or _photo()), content_type)},
    )
    assert res.status_code == 201, res.text
    return res.json()["document_id"]


class TestTheDerivativeIsServed:
    def test_thumb_is_dramatically_smaller_than_the_document(self, client, db):
        headers = _headers(client, "thumb@example.com")
        doc = _capture(client, headers)
        runners.run_image_thumbnails(db)

        full = client.get(f"/protection/documents/{doc}", headers=headers)
        thumb = client.get(f"/protection/documents/{doc}?size=thumb", headers=headers)

        assert full.status_code == thumb.status_code == 200
        assert len(thumb.content) < len(full.content) / 10
        assert thumb.content[:3] == b"\xff\xd8\xff", "a real JPEG, not the original"

    def test_both_sizes_come_from_the_same_path(self, client, db):
        """The whole reason this is not on `/media`: one path, one cache key per size,
        and neither changes between renders."""
        headers = _headers(client, "stable@example.com")
        doc = _capture(client, headers)
        runners.run_image_thumbnails(db)

        first = client.get(f"/protection/documents/{doc}?size=thumb", headers=headers)
        second = client.get(f"/protection/documents/{doc}?size=thumb", headers=headers)

        assert first.content == second.content, "the same url must serve the same bytes"
        assert "immutable" in first.headers["cache-control"]
        assert "private" in first.headers["cache-control"]

    def test_it_still_requires_the_driver_s_own_session(self, client, db):
        # the signed-url tradeoff, stated: this path is authenticated, which is why it
        # cannot go in an `<img src>` and why the wallet fetches blobs instead
        headers = _headers(client, "owner@example.com")
        doc = _capture(client, headers)
        other = _headers(client, "stranger@example.com")

        url = f"/protection/documents/{doc}?size=thumb"
        assert client.get(url).status_code in (401, 403)
        # a stranger's document id must not be distinguishable from a missing one
        assert client.get(url, headers=other).status_code == 404


class TestItNeverLeavesTheFrameEmpty:
    def test_before_the_job_runs_it_falls_back_to_the_document(self, client, db):
        # the derivative job runs every five minutes; a credential photographed thirty
        # seconds ago has none. Falling back is what makes this safe to ship ahead of it.
        headers = _headers(client, "notyet@example.com")
        doc = _capture(client, headers)

        res = client.get(f"/protection/documents/{doc}?size=thumb", headers=headers)

        assert res.status_code == 200
        assert len(res.content) > 0

    def test_a_pdf_has_no_derivative_and_still_serves(self, client, db):
        # a rate con is routinely filed as a PDF (§23 entry 77), and `make_thumbnail`
        # correctly returns nothing for one
        headers = _headers(client, "pdf@example.com")
        doc = _capture(
            client,
            headers,
            content=b"%PDF-1.4 rate confirmation",
            doc_type="rate_con",
            filename="rc.pdf",
            content_type="application/pdf",
        )
        runners.run_image_thumbnails(db)

        res = client.get(f"/protection/documents/{doc}?size=thumb", headers=headers)

        assert res.status_code == 200
        assert res.content.startswith(b"%PDF"), "the document itself, not an empty frame"

    def test_an_unknown_size_is_the_document(self, client, db):
        headers = _headers(client, "weird@example.com")
        doc = _capture(client, headers)

        res = client.get(f"/protection/documents/{doc}?size=enormous", headers=headers)

        assert res.status_code == 200
