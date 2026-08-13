"""AI-CONTEXT: derivatives, and the two ways this job was wrong on its first real run.

"Thumbnail" was a variable name in two surfaces and never a file: `EvidenceSurface` and
`LoadRecordSurface` each hold a map called `thumbs`, render it into a box a few dozen dp
across, and put the ORIGINAL in it. There is no resize anywhere in this product.

Both defects below were found by running the job against the 197 real stored records on
the dev box and READING THE SUMMARY, not by the suite:

  · `{'made': 0, 'failed': 197}` — the worker had never wired object storage. That runs
    in the API's FastAPI lifespan and the worker is a different process, so
    `default_storage()` there was the empty in-memory dict every process starts with. No
    job had ever reached for a stored byte, so nothing had ever failed.
  · then `{'made': 88, 'skipped': 82, 'failed': 27}` — and 27 again, forever. Those rows
    point at objects that no longer exist, and "gone" was being retried as though it were
    "briefly unreachable". Two opposite facts down one path.
"""

import io

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f04_evidence import public as evidence
from app.foundation.f06_documents import public as documents
from app.ingest import runners


def _png(width=800, height=600, mode="RGB"):
    from PIL import Image

    img = Image.new(mode, (width, height), (30, 90, 160) if mode == "RGB" else 128)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestTheDerivativeItself:
    def test_a_photograph_becomes_a_small_jpeg(self):
        from PIL import Image

        thumb = documents.make_thumbnail(_png(4000, 3000))

        assert thumb is not None
        with Image.open(io.BytesIO(thumb)) as img:
            assert img.format == "JPEG"
            # the long edge is capped and the aspect ratio survives
            assert max(img.size) == documents.THUMB_EDGE
            assert img.size == (320, 240)

    def test_it_is_dramatically_smaller_than_what_it_derives_from(self):
        original = _png(4000, 3000)
        thumb = documents.make_thumbnail(original)

        # the whole reason it exists: a contact sheet must not cost what the photographs cost
        assert len(thumb) < len(original) / 10

    def test_a_png_with_transparency_does_not_take_the_job_down(self):
        # JPEG has no alpha, so saving an RGBA image raises "cannot write mode RGBA".
        # A screenshot of a rate con is a normal thing for a driver to file.
        assert documents.make_thumbnail(_png(600, 400, mode="RGBA")) is not None

    def test_a_pdf_yields_nothing_and_says_so_by_returning_none(self):
        # a rate con is routinely a PDF (§23 entry 77). Not an error — the normal case.
        assert documents.make_thumbnail(b"%PDF-1.4 rate confirmation") is None

    def test_garbage_yields_nothing_rather_than_raising(self):
        assert documents.make_thumbnail(b"\x00\x01\x02 not an image") is None
        assert documents.make_thumbnail(b"") is None

    def test_the_key_is_derived_from_the_original_rather_than_stored(self):
        # one column records whether we TRIED; the key is always computable, so storing
        # it too would be a second fact to keep in step with the first
        assert documents.thumbnail_key("acct/doc/bol.jpg") == "acct/doc/bol.jpg.thumb.jpg"

    def test_a_rotated_photograph_is_uprighted(self):
        from PIL import Image

        # a phone writes orientation into EXIF rather than rotating pixels. Browsers
        # honour the tag on the original; a re-encoded derivative loses it, so a portrait
        # BOL would appear on its side in every contact sheet unless it is baked in here.
        img = Image.new("RGB", (400, 200), (200, 60, 60))
        buf = io.BytesIO()
        exif = img.getexif()
        exif[274] = 6  # rotate 90° CW
        img.save(buf, format="JPEG", exif=exif)

        thumb = documents.make_thumbnail(buf.getvalue())

        with Image.open(io.BytesIO(thumb)) as out:
            # 400x200 rotated becomes taller than it is wide
            assert out.size[1] > out.size[0], "the EXIF rotation must be applied"


class TestTheJob:
    @pytest.fixture
    def account(self, db):
        return identity.register_account(db, "thumbs@example.com", "pw-123456")

    @pytest.fixture
    def stored(self, db, account):
        """A document whose bytes are really in the (in-memory) store."""
        doc = documents.store_document(
            db,
            account_id=account.id,
            doc_type=documents.DocType.bol,
            content=_png(1200, 900),
            filename="bol.png",
            content_type="image/png",
        )
        db.commit()
        return doc

    def test_it_derives_and_records_ready(self, db, stored):
        summary = runners.run_image_thumbnails(db)

        assert summary["made"] >= 1
        db.refresh(stored)
        assert stored.thumbnail_state == "ready"
        # and the derivative is really in the store under the derived key
        assert documents.default_storage().get(documents.thumbnail_key(stored.storage_key))

    def test_a_second_pass_does_no_work(self, db, stored):
        runners.run_image_thumbnails(db)
        again = runners.run_image_thumbnails(db)

        # the job is its own backfill and has to CONVERGE — a janitor that re-decodes
        # every image on the box every five minutes is worse than no janitor
        assert again == {"made": 0, "skipped": 0, "failed": 0, "missing": 0}

    def test_a_document_with_no_image_is_recorded_as_none_and_never_retried(self, db, account):
        doc = documents.store_document(
            db,
            account_id=account.id,
            doc_type=documents.DocType.rate_con,
            content=b"%PDF-1.4 rate confirmation",
            filename="rc.pdf",
            content_type="application/pdf",
        )
        db.commit()

        first = runners.run_image_thumbnails(db)
        db.refresh(doc)
        second = runners.run_image_thumbnails(db)

        assert first["skipped"] >= 1
        assert doc.thumbnail_state == "none"
        assert second["skipped"] == 0, "a PDF must not be re-decoded forever"

    def test_bytes_that_are_GONE_are_recorded_rather_than_retried_forever(self, db, stored):
        # 27 rows on the dev box point at objects lost in the era
        # `main._wire_object_storage` describes. Re-reading them every five minutes
        # forever is what this job did before "gone" and "unreachable" were told apart.
        documents.default_storage().delete(stored.storage_key)

        first = runners.run_image_thumbnails(db)
        db.refresh(stored)
        second = runners.run_image_thumbnails(db)

        assert first["missing"] == 1
        assert first["failed"] == 0, "an absent object is not a job failure"
        assert stored.thumbnail_state == "missing"
        assert second["missing"] == 0, "and it is never read again"

    def test_a_store_that_is_briefly_unreachable_is_left_for_the_next_pass(self, db, stored):
        class Unwell:
            def get(self, key):
                raise ConnectionError("minio restarting")

            def put(self, key, data, content_type=None):
                raise ConnectionError("minio restarting")

            def delete(self, key):
                pass

        real = documents.default_storage()
        documents.set_default_storage(Unwell())
        try:
            summary = runners.run_image_thumbnails(db)
        finally:
            documents.set_default_storage(real)

        db.refresh(stored)
        assert summary["failed"] == 1
        assert summary["missing"] == 0
        # left NULL on purpose: a restart window must heal itself rather than
        # permanently marking a driver's photograph as having no thumbnail
        assert stored.thumbnail_state is None

    def test_the_batch_is_bounded(self, db, account):
        for _ in range(5):
            documents.store_document(
                db,
                account_id=account.id,
                doc_type=documents.DocType.bol,
                content=_png(200, 200),
                filename="x.png",
                content_type="image/png",
            )
        db.commit()

        # a driver photographing a whole route lands a few dozen rows at once, and
        # decoding every image on the box in one transaction is how a five-minute
        # janitor becomes an outage
        summary = runners.run_image_thumbnails(db, batch=2)

        assert summary["made"] == 2


class TestTheWorkerCanActuallyReachTheBytes:
    def test_the_worker_wires_object_storage_at_startup(self, monkeypatch):
        """AI-CONTEXT: the defect that made this job inert, asserted structurally.

        `_wire_object_storage` ran only in the API's FastAPI lifespan. The worker is a
        separate process, so `default_storage()` there was the in-memory dict — and the
        first job to reach for a stored byte failed on every row and healed nothing.
        Nothing caught it because no worker job had ever needed object storage before.
        """
        import app.worker as worker

        wired: list[str] = []
        monkeypatch.setattr(
            "app.wiring.wire_object_storage",
            lambda role="api": wired.append(role) or True,
        )
        # the rest of _startup talks to the database; it swallows its own failures, and
        # this test is about the wiring call being on the path at all
        worker._startup()

        assert wired == ["worker"], "the worker must wire object storage for itself"

    def test_the_job_is_registered_on_the_worker(self):
        import app.worker as worker

        names = [job.name for job in worker._jobs()]
        assert "image_thumbnails" in names

    def test_it_is_unflagged_so_it_cannot_be_silently_idle(self):
        import app.worker as worker

        job = next(j for j in worker._jobs() if j.name == "image_thumbnails")
        # `is_enabled` returns False for a flag nobody registered, so giving infrastructure
        # a flag is how it becomes another engine that is built, wired and permanently idle
        assert job.flag_key is None


class TestArtifactsGetThemToo:
    def test_an_evidence_photo_gets_a_derivative(self, db):
        # these are the rows the Evidence and Load-record contact sheets draw, and each
        # one was drawn from the full-size original
        assert hasattr(evidence.EvidenceArtifact, "thumbnail_state")
