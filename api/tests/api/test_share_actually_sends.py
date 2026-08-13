"""AI-CONTEXT: the endpoint two screens called "Send" and which emailed nobody.

`POST /protection/{kind}/{ref}/share` pinned a pack, minted a token, stored a `recipient`
**that nothing ever read**, and returned a link. Measured on the running stack before the
fix: a share left `f08.outbound_message` at exactly the count it started with, and no
thread for a shared pack existed anywhere in the database.

Both callers reported otherwise. `LoadRecordSurface` — the whole-load send added by §23
entry 137, which called the gap it was closing "the eighth built-and-inert mechanism" —
said **"Sent. The broker has the link."** Offline it said "This sends when you're back
online." `EvidenceSurface`'s own copy promised "They get one link to this record" and "the
link goes out when you have one". `share_pack`'s docstring said the share is "the moment
the document stops being a view of the chain and becomes a thing that was SENT."

None of it was true, and a driver who believes a broker holds their evidence does not
chase it. That is worse than inert: it is inert with a confirmation on top.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
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


def _driver(client, db, email="share@example.com"):
    token = client.post("/auth/register", json={"email": email, "password": "pw-123456"}).json()[
        "token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _arrived_stop(client, headers, broker="ap@broker.example"):
    body = {
        "facility_name": "Dock",
        "lat": DALLAS[0],
        "lon": DALLAS[1],
        "counterparty": "Acme",
        "counterparty_email": broker,
        # accrue immediately, so `/notice` is the START notice rather than the
        # free-time warning — the warning is a different message with its own rules
        "free_time_minutes": 0,
    }
    created = client.post("/load", json=body, headers=headers).json()
    stop_id = created.get("stop_id") or created["stop_ids"][0]
    client.post(f"/load/{stop_id}/arrive", json={}, headers=headers)
    return stop_id


def _outbound(db):
    return len(db.query(notify.OutboundMessage).all())


class TestItActuallySendsNow:
    def test_sharing_with_a_recipient_puts_a_message_on_the_wire(self, client, db):
        headers = _driver(client, db)
        stop = _arrived_stop(client, headers)
        before = _outbound(db)

        res = client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example"},
            headers=headers,
        )

        assert res.status_code == 201, res.text
        assert res.json()["sent"] is True
        assert _outbound(db) == before + 1, "the whole point: a message must exist"

    def test_the_message_carries_the_link_the_broker_needs(self, client, db):
        headers = _driver(client, db, "link@example.com")
        stop = _arrived_stop(client, headers)

        client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example"},
            headers=headers,
        )

        message = db.query(notify.OutboundMessage).order_by(
            notify.OutboundMessage.created_at.desc()
        ).first()
        assert message.to_ref == "ap@broker.example"
        assert "/pack/s/" in message.body or "on request" in message.body

    def test_a_share_with_no_recipient_sends_nothing_and_says_so(self, client, db):
        # a legitimate use of the same control: a driver wanting a link to paste
        # somewhere themselves. What it must never do is claim a delivery.
        headers = _driver(client, db, "linkonly@example.com")
        stop = _arrived_stop(client, headers)
        before = _outbound(db)

        res = client.post(f"/protection/stop/{stop}/share", json={}, headers=headers)

        assert res.json()["sent"] is False
        assert res.json()["already_sent"] is False
        assert res.json()["url"].startswith("/pack/s/"), "the link is still the point"
        assert _outbound(db) == before


class TestOneRecordOneBroker:
    def test_the_same_record_to_the_same_broker_does_not_send_twice(self, client, db):
        headers = _driver(client, db, "dupe@example.com")
        stop = _arrived_stop(client, headers)

        first = client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example"},
            headers=headers,
        ).json()
        before = _outbound(db)
        second = client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example"},
            headers=headers,
        ).json()

        assert first["sent"] is True
        # AI-CONTEXT: `already_sent`, not a silent success. Returning `sent: True` here
        # would make the control a dead one — it runs, nothing happens, and the screen
        # shows what a real send shows (§23 entry 72).
        assert second["sent"] is False
        assert second["already_sent"] is True
        assert _outbound(db) == before

    def test_a_different_broker_is_a_different_purpose(self, client, db):
        headers = _driver(client, db, "twobrokers@example.com")
        stop = _arrived_stop(client, headers)
        client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example"},
            headers=headers,
        )
        before = _outbound(db)

        res = client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "other@broker.example"},
            headers=headers,
        ).json()

        assert res["sent"] is True
        assert _outbound(db) == before + 1

    def test_the_key_could_not_be_the_content_hash(self, client, db):
        """AI-CONTEXT: the first version of this keyed on `content_hash` and deduplicated
        NOTHING — measured, two taps produced two emails with the dedupe in place.

        Sharing is itself an evidence event: `f04.sharing` appends to the chain, so the
        pack rendered for the second share legitimately contains the first one and hashes
        differently. `render.py` is right that a regenerated pack is byte-identical — the
        INPUT had changed. This test pins the reason so the key is not "simplified" back.
        """
        headers = _driver(client, db, "hashes@example.com")
        stop = _arrived_stop(client, headers)

        a = client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example"},
            headers=headers,
        ).json()
        b = client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example", "force": True},
            headers=headers,
        ).json()

        assert a["content_hash"] != b["content_hash"], (
            "sharing appends to the chain, so the pack changes — a content key cannot dedupe"
        )


class TestForceIsDeliberate:
    def test_force_sends_a_second_copy(self, client, db):
        headers = _driver(client, db, "force@example.com")
        stop = _arrived_stop(client, headers)
        client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example"},
            headers=headers,
        )
        before = _outbound(db)

        res = client.post(
            f"/protection/stop/{stop}/share",
            json={"recipient": "ap@broker.example", "force": True},
            headers=headers,
        ).json()

        assert res["sent"] is True
        assert res["already_sent"] is False
        assert _outbound(db) == before + 1

    def test_force_can_be_used_more_than_once(self, client, db):
        # a forced send carries NO dedupe key: a deliberate duplicate is not a duplicate,
        # and keying it would make the second forced send a silent no-op
        headers = _driver(client, db, "twice@example.com")
        stop = _arrived_stop(client, headers)
        payload = {"recipient": "ap@broker.example", "force": True}
        client.post(f"/protection/stop/{stop}/share", json=payload, headers=headers)
        before = _outbound(db)

        client.post(f"/protection/stop/{stop}/share", json=payload, headers=headers)

        assert _outbound(db) == before + 1


class TestTheDetentionNoticeKeepsItsAnchor:
    def test_a_forced_notice_does_not_move_the_dispute_anchor(self, client, db, flush_outbox):
        """AI-CONTEXT: the rule §23 recorded — a delivered notice "may not be re-anchored".

        `start_notice_sent_at` is the timestamp a detention dispute turns on. A driver
        re-sending because the broker says they never got it is asking for a COPY, not for
        a new claim, so the anchor stays on the first real delivery and the pack goes on
        arguing from when the broker was actually told.
        """
        from app.modules.m03_detention import public as m3

        headers = _driver(client, db, "anchor@example.com")
        stop = _arrived_stop(client, headers)
        client.post(f"/load/{stop}/notice", headers=headers)
        flush_outbox()
        claim = m3.claim_for_stop(db, uuid.UUID(stop))
        anchor_ref, anchor_at = claim.start_notice_message_ref, claim.start_notice_sent_at
        assert anchor_at is not None
        before = _outbound(db)

        res = client.post(f"/load/{stop}/notice", json={"force": True}, headers=headers).json()

        assert res["forced"] is True
        assert _outbound(db) == before + 1, "a second copy really goes"
        db.refresh(claim)
        assert claim.start_notice_message_ref == anchor_ref, "the anchor must not move"
        assert claim.start_notice_sent_at == anchor_at

    def test_without_force_a_delivered_notice_says_already_sent(self, client, db, flush_outbox):
        headers = _driver(client, db, "already@example.com")
        stop = _arrived_stop(client, headers)
        client.post(f"/load/{stop}/notice", headers=headers)
        flush_outbox()
        before = _outbound(db)

        res = client.post(f"/load/{stop}/notice", headers=headers).json()

        # the control used to report exactly what a real send reports
        assert res["already_sent"] is True
        assert res["forced"] is False
        assert _outbound(db) == before
