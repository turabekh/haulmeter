"""AI-CONTEXT: the pack rides WITH the email now, and these are the tests that can tell.

Owner request: "when we send the package to brokers, can we send actual pdf instead of
url". Resolved as BOTH, which is the version that loses nothing.

§17 specifies "plain, short, professional; one link; no images", and §23's outbound-artifacts
entry chose the link for a reason worth keeping: *"The **first** open is written into the
chain because 'they opened it on the 12th' is evidence."* An attachment cannot be tracked,
expired or revoked — replacing the link would trade a fact a dispute can use for a
convenience. Keeping both means a clerk opens the document from their inbox AND the product
still records that they did.

WHY THE RECORDING GATEWAY HAD TO LEARN ABOUT ATTACHMENTS. It accepted `send_email(to, subject,
body)` and would have gone on accepting it — so "we attach the pack" could have passed in
every existing test while nothing was ever attached, which is this codebase's most familiar
shape of green.
"""


import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.core.config import get_settings
from app.foundation.f08_notifications import public as notify
from app.main import app

DALLAS = (32.7767, -96.7970)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _driver(client, email):
    token = client.post("/auth/register", json={"email": email, "password": "pw-123456"}).json()[
        "token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _arrived_stop(client, headers):
    created = client.post(
        "/load",
        json={
            "facility_name": "Dock",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme",
            "counterparty_email": "ap@broker.example",
            "free_time_minutes": 0,
        },
        headers=headers,
    ).json()
    stop_id = created.get("stop_id") or created["stop_ids"][0]
    client.post(f"/load/{stop_id}/arrive", json={}, headers=headers)
    return stop_id


def _newest(db):
    return (
        db.query(notify.OutboundMessage)
        .order_by(notify.OutboundMessage.created_at.desc())
        .first()
    )


class TestTheRecordCarriesItsDocument:
    def test_a_share_records_the_pack_as_its_attachment(self, client, db):
        headers = _driver(client, "attach@example.com")
        stop = _arrived_stop(client, headers)

        client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example"},
            headers=headers,
        )

        message = _newest(db)
        assert message.attachment_key, "the row must name where the document lives"
        assert message.attachment_key.startswith("packs/")
        assert message.attachment_name.endswith(".pdf")

    def test_the_link_is_still_in_the_body(self, client, db):
        # §17's one link, and §23's reason for it: the link is the half that can record
        # that the broker opened it. An attachment produces no such evidence.
        headers = _driver(client, "both@example.com")
        stop = _arrived_stop(client, headers)

        client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example"},
            headers=headers,
        )

        assert "/pack/s/" in _newest(db).body


class TestTheDocumentReachesTheGateway:
    def test_the_sweep_hands_the_pdf_over(self, client, db):
        headers = _driver(client, "sweep@example.com")
        stop = _arrived_stop(client, headers)
        client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example"},
            headers=headers,
        )
        gateway = notify.RecordingNotificationGateway()

        notify.retry_unsent_messages(db, gateway)

        assert gateway.attachments, "the gateway was handed no attachment list at all"
        name, data = gateway.attachments[-1][0]
        assert name.endswith(".pdf")
        assert data[:5] == b"%PDF-", "what arrives must be a real PDF, not a link or a stub"

    def test_the_attached_bytes_are_the_ones_the_link_serves(self, client, db):
        """One document, one place. The pack the broker opens from their inbox and the
        pack the link serves must never be able to differ — that is the whole argument
        for keying the attachment to F4's pinned copy rather than re-rendering."""
        headers = _driver(client, "same@example.com")
        stop = _arrived_stop(client, headers)
        res = client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example"},
            headers=headers,
        ).json()
        gateway = notify.RecordingNotificationGateway()
        notify.retry_unsent_messages(db, gateway)

        _, attached = gateway.attachments[-1][0]
        served = client.get(res["url"]).content

        assert attached == served

    def test_mail_with_no_pack_carries_no_attachment(self, client, db):
        # most counterparty mail has no document; an empty list, never a stub
        headers = _driver(client, "nopack@example.com")
        stop = _arrived_stop(client, headers)
        client.post(f"/load/{stop}/notice", headers=headers)
        gateway = notify.RecordingNotificationGateway()

        notify.retry_unsent_messages(db, gateway)

        assert gateway.attachments[-1] == []


class TestItDeclinesRatherThanFailing:
    def test_an_oversize_pack_still_sends_with_its_link(self, client, db, monkeypatch):
        """AI-CONTEXT: the cap exists because a bounced notice is worse than a linked one.

        A whole-load record with two dozen photographs approaches the size many corporate
        filters reject outright. Over the ceiling the mail goes anyway — the link is in the
        body regardless, so this costs a broker one click and never a delivery.
        """
        headers = _driver(client, "big@example.com")
        stop = _arrived_stop(client, headers)
        client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example"},
            headers=headers,
        )
        monkeypatch.setenv("MAX_EMAIL_ATTACHMENT_MB", "0")
        get_settings.cache_clear()
        gateway = notify.RecordingNotificationGateway()
        try:
            summary = notify.retry_unsent_messages(db, gateway)
        finally:
            monkeypatch.undo()
            get_settings.cache_clear()

        assert summary["sent"] == 1, "the notice must still go"
        assert gateway.attachments[-1] == [], "but without the document"
        assert "/pack/s/" in gateway.sent[-1].body, "and the link is what carries it"

    def test_a_missing_object_does_not_lose_the_notice(self, client, db):
        # the bytes are gone, or storage is briefly unwell. Attaching nothing is right;
        # failing the send would lose the notice as well as the document.
        headers = _driver(client, "gone@example.com")
        stop = _arrived_stop(client, headers)
        client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example"},
            headers=headers,
        )
        message = _newest(db)
        message.attachment_key = "packs/does-not-exist/nope.pdf"
        db.flush()
        gateway = notify.RecordingNotificationGateway()

        summary = notify.retry_unsent_messages(db, gateway)

        assert summary["sent"] == 1
        assert gateway.attachments[-1] == []


class TestTheClaimPackToo:
    def test_the_detention_invoice_attaches_its_evidence(self, db):
        """AI-CONTEXT: built through the services rather than the route, and for two
        reasons the route cannot satisfy — an invoice needs OWN AUTHORITY (a company
        driver's claim is notify-only, §M3), and it needs detention to have actually
        accrued, which the route cannot do because it files at wall-clock now.

        The body has said "Please find attached the GPS evidence and invoice" since it was
        written, and nothing was ever attached.
        """
        from datetime import UTC, datetime, timedelta

        from app.foundation.f01_identity import public as identity
        from app.foundation.f02_facility import public as facility
        from app.foundation.f03_location import public as location
        from app.foundation.f05_load import public as loads
        from app.modules.m03_detention import public as m3

        t0 = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)
        account = identity.register_account(db, "claimpack@example.com", "pw-123456")
        identity.upsert_driver_profile(
            db, account, authority_type=identity.AuthorityType.own_mc
        )
        dock = facility.create_facility(
            db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS
        )
        cp = loads.create_counterparty(
            db, "Acme", loads.CounterpartyKind.broker, contact_email="ap@broker.example"
        )
        load = loads.create_load(
            db,
            account.id,
            counterparty_id=cp.id,
            detention_rate_cents_per_hour=7500,
            free_time_minutes=0,
        )
        stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery, appointment_start=t0)
        claim = m3.start_claim(db, stop, started_at=t0)
        # AI-CONTEXT: TWO pings, arrival and departure, with an explicit `now` on each —
        # copied from `test_broken_packs_do_not_travel._claim`. One ping leaves the chain
        # with nothing to anchor and `compose_pack` refuses an empty log. The pack is the
        # thing under test here; its evidence has to be real.
        filed = t0 + timedelta(hours=4)
        location.evaluate_ping(db, account.id, *DALLAS, occurred_at=t0, now=t0)
        location.evaluate_ping(db, account.id, 32.9000, -96.8000, occurred_at=filed, now=filed)
        gateway = notify.RecordingNotificationGateway()

        m3.generate_pack(db, claim, now=filed, gateway=gateway)

        invoice = (
            db.query(notify.OutboundMessage)
            .filter(notify.OutboundMessage.dedupe_key.like("detention_invoice:%"))
            .first()
        )
        assert invoice is not None, "filing a claim must raise an invoice message"
        assert invoice.attachment_key.startswith("packs/"), "and carry the evidence pack"
        assert invoice.attachment_name == "detention-evidence.pdf"

        notify.retry_unsent_messages(db, gateway)
        _, data = gateway.attachments[-1][0]
        assert data[:5] == b"%PDF-"
