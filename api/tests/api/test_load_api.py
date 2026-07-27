"""AI-CONTEXT: HTTP API tests for the active-load lifecycle behind The Meter.
TestClient with get_db overridden to the transactional test session. Proves
create -> arrive -> meter: before arrival the Meter is pre-arrival; after a
geofence ENTER the detention clock is live.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app

DALLAS = (32.7767, -96.7970)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client):
    resp = client.post(
        "/auth/register", json={"email": "driver@example.com", "password": "pw-123456"}
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _create(client, headers):
    resp = client.post(
        "/load",
        json={
            "facility_name": "Dallas Receiver",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme Brokerage",
            "free_time_minutes": 120,
            "rate_cents_per_hour": 7500,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["stop_id"]


def test_create_requires_auth(client):
    assert client.post("/load", json={}).status_code == 401


def test_active_load_requires_auth(client):
    assert client.get("/load/active").status_code == 401


def test_active_load_resumes_the_current_stop(client, db):
    headers = _auth(client)
    # nothing armed yet -> null
    assert client.get("/load/active", headers=headers).json()["stop_id"] is None

    stop_id = _create(client, headers)  # arms the stop
    active = client.get("/load/active", headers=headers)
    assert active.status_code == 200
    assert active.json()["stop_id"] == stop_id  # a fresh device can resume here


def test_end_load_departs_the_stop_and_clears_active(client, db):
    headers = _auth(client)
    stop_id = _create(client, headers)
    assert client.get("/load/active", headers=headers).json()["stop_id"] == stop_id

    ended = client.post(f"/load/{stop_id}/end", headers=headers)
    assert ended.status_code == 201
    assert ended.json()["status"] == "departed"
    # ending is durable: the resume query no longer surfaces it
    assert client.get("/load/active", headers=headers).json()["stop_id"] is None


def test_end_load_rejects_another_owner(client, db):
    a = _auth(client)
    stop_id = _create(client, a)
    b = client.post("/auth/register", json={"email": "b@example.com", "password": "pw-123456"})
    b_headers = {"Authorization": f"Bearer {b.json()['token']}"}
    assert client.post(f"/load/{stop_id}/end", headers=b_headers).status_code == 403


def test_stop_scoped_endpoints_reject_another_owner(client, db):
    # every stop-scoped action is gated to the load's owner (403 for anyone else)
    a = _auth(client)
    stop_id = _create(client, a)
    b = client.post(
        "/auth/register", json={"email": "intruder@example.com", "password": "pw-123456"}
    )
    hb = {"Authorization": f"Bearer {b.json()['token']}"}
    assert client.get(f"/load/{stop_id}/meter", headers=hb).status_code == 403
    assert client.get(f"/load/{stop_id}/evidence", headers=hb).status_code == 403
    assert client.post(f"/load/{stop_id}/arrive", headers=hb).status_code == 403
    assert client.post(f"/load/{stop_id}/notice", headers=hb).status_code == 403
    assert client.post(f"/load/{stop_id}/claim", headers=hb).status_code == 403
    # the real owner is still allowed through (arrive succeeds)
    assert client.post(f"/load/{stop_id}/arrive", headers=a).status_code == 201


def test_active_load_is_per_account(client, db):
    # one driver's armed stop is never another's active load
    a = _auth(client)
    stop_id = _create(client, a)
    b = client.post("/auth/register", json={"email": "other@example.com", "password": "pw-123456"})
    b_headers = {"Authorization": f"Bearer {b.json()['token']}"}
    assert client.get("/load/active", headers=a).json()["stop_id"] == stop_id
    assert client.get("/load/active", headers=b_headers).json()["stop_id"] is None


def test_new_load_terms_read_f13_config_default(client, db):
    from app.foundation.f13_flags import public as flags
    from app.modules.m03_detention import public as m3

    headers = _auth(client)
    # unset -> the compiled default (2h free)
    stop_id = client.post(
        "/load",
        json={"facility_name": "R", "lat": DALLAS[0], "lon": DALLAS[1], "counterparty": "Acme"},
        headers=headers,
    ).json()["stop_id"]
    assert client.get(f"/load/{stop_id}/meter", headers=headers).json()["free_time_minutes"] == 120

    # an operator lowers the platform default via F13 config -> the next load uses it
    flags.set_config(db, m3.CONFIG_FREE_TIME_KEY, 60, scope="detention")
    flags.set_config(db, m3.CONFIG_RATE_KEY, 9000, scope="detention")
    stop2 = client.post(
        "/load",
        json={"facility_name": "R2", "lat": DALLAS[0], "lon": DALLAS[1], "counterparty": "Acme"},
        headers=headers,
    ).json()["stop_id"]
    meter = client.get(f"/load/{stop2}/meter", headers=headers).json()
    assert meter["free_time_minutes"] == 60
    assert meter["rate_cents_per_hour"] == 9000

    # an explicit value in the request still overrides the config default
    stop3 = client.post(
        "/load",
        json={
            "facility_name": "R3",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme",
            "free_time_minutes": 180,
        },
        headers=headers,
    ).json()["stop_id"]
    assert client.get(f"/load/{stop3}/meter", headers=headers).json()["free_time_minutes"] == 180


def test_meter_pre_arrival_then_live_after_arrive(client, db):
    headers = _auth(client)
    stop_id = _create(client, headers)

    # before arrival: the Meter is pre-arrival, clock not running
    pre = client.get(f"/load/{stop_id}/meter", headers=headers)
    assert pre.status_code == 200
    body = pre.json()
    assert body["facility_name"] == "Dallas Receiver"
    assert body["counterparty"] == "Acme Brokerage"
    assert body["phase"] == "not_arrived"
    assert body["free_time_minutes"] == 120

    # arrive -> geofence ENTER starts the detention clock
    arrived = client.post(f"/load/{stop_id}/arrive", headers=headers)
    assert arrived.status_code == 201
    assert arrived.json()["arrived"] is True

    live = client.get(f"/load/{stop_id}/meter", headers=headers)
    assert live.status_code == 200
    lbody = live.json()
    assert lbody["arrived"] is True
    # just arrived -> within free time, clock live
    assert lbody["phase"] == "within_free_time"
    assert lbody["free_time_remaining_seconds"] is not None


def test_meter_carries_the_on_time_verdict(client, db):
    """M5-FR1's verdict had no route to a screen.

    `within_window` is filed on every arrival — in or out of the window — and the only
    place the API exposed it was the `/arrive` response, which the Load tab discards.
    After a reload the driver could not learn whether their own arrival counted as on
    time. FR5's protection summary counts four documented items; §10.2's checklist
    rendered three, and this is the fourth.
    """
    headers = _auth(client)
    # an appointment an hour ago -> arriving now is LATE
    late_appt = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    stop_id = client.post(
        "/load",
        json={
            "facility_name": "Late Dock",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Broker",
            "appointment": late_appt,
        },
        headers=headers,
    ).json()["stop_id"]

    # before arrival there is no verdict to give, and `null` says so
    pre = client.get(f"/load/{stop_id}/meter", headers=headers).json()
    assert pre["on_time"] is None
    assert pre["arrived_at"] is None

    client.post(f"/load/{stop_id}/arrive", headers=headers)

    body = client.get(f"/load/{stop_id}/meter", headers=headers).json()
    assert body["on_time"] is False  # the verdict survives the reload
    assert body["arrived_at"] is not None


def test_meter_reports_an_on_time_arrival(client, db):
    headers = _auth(client)
    soon = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    stop_id = client.post(
        "/load",
        json={
            "facility_name": "Punctual Dock",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Broker",
            "appointment": soon,
        },
        headers=headers,
    ).json()["stop_id"]
    client.post(f"/load/{stop_id}/arrive", headers=headers)

    assert client.get(f"/load/{stop_id}/meter", headers=headers).json()["on_time"] is True


class TestAppointmentProvenanceAndCorrection:
    """M5-FR1's window: whose value it is, and the fact that it can now be fixed.

    The Meter reported provenance from `load.source` — how the LOAD was created — which
    is a different fact about a different object. A rate-con import claimed "read from
    your rate con" for an appointment the confirm sheet never sent, and a correction
    could not have changed the claim because nothing could write the field at all.
    """

    def _stop(self, client, headers, **extra):
        return client.post(
            "/load",
            json={
                "facility_name": "Appt Dock",
                "lat": DALLAS[0],
                "lon": DALLAS[1],
                "counterparty": "Broker",
                **extra,
            },
            headers=headers,
        ).json()["stop_id"]

    def test_a_window_with_no_value_claims_no_source(self, client, db):
        """A null appointment has no provenance to state, and claiming one would be
        the same defect this field exists to fix, one layer down."""
        headers = _auth(client)
        stop_id = self._stop(client, headers, appointment_source="rate_con_parse")

        body = client.get(f"/load/{stop_id}/meter", headers=headers).json()
        assert body["appointment"] is None
        assert body["appointment_source"] is None

    def test_provenance_belongs_to_the_window_not_the_load(self, client, db):
        headers = _auth(client)
        appt = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
        stop_id = self._stop(
            client, headers, appointment=appt, appointment_source="rate_con_parse"
        )

        assert (
            client.get(f"/load/{stop_id}/meter", headers=headers).json()["appointment_source"]
            == "rate_con_parse"
        )

    def test_correcting_the_window_moves_the_credit_to_the_driver(self, client, db):
        """FR1 exists so a driver can catch a mis-parse while it still matters. Once
        they have typed their own time, the parse must stop taking the credit."""
        headers = _auth(client)
        appt = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
        stop_id = self._stop(
            client, headers, appointment=appt, appointment_source="rate_con_parse"
        )
        corrected = (datetime.now(UTC) + timedelta(hours=5)).replace(microsecond=0)

        resp = client.patch(
            f"/load/{stop_id}/appointment",
            json={"appointment": corrected.isoformat()},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["appointment_source"] == "manual"
        meter = client.get(f"/load/{stop_id}/meter", headers=headers).json()
        assert meter["appointment_source"] == "manual"
        assert meter["appointment"].startswith(corrected.isoformat()[:16])

    def test_a_correction_carries_the_window_end_too(self, client, db):
        headers = _auth(client)
        stop_id = self._stop(client, headers)
        start = (datetime.now(UTC) + timedelta(hours=2)).replace(microsecond=0)
        end = start + timedelta(hours=1)

        client.patch(
            f"/load/{stop_id}/appointment",
            json={"appointment": start.isoformat(), "appointment_end": end.isoformat()},
            headers=headers,
        )

        meter = client.get(f"/load/{stop_id}/meter", headers=headers).json()
        assert meter["appointment_end"].startswith(end.isoformat()[:16])

    def test_correction_is_gated_to_the_owner(self, client, db):
        headers = _auth(client)
        stop_id = self._stop(client, headers)
        other = client.post(
            "/auth/register", json={"email": "nosy@example.com", "password": "pw-123456"}
        )
        theirs = {"Authorization": f"Bearer {other.json()['token']}"}

        resp = client.patch(
            f"/load/{stop_id}/appointment",
            json={"appointment": datetime.now(UTC).isoformat()},
            headers=theirs,
        )

        assert resp.status_code == 403


def test_notice_flags_notice_sent_on_the_meter(client, db):
    # a detention-start notice, once detention is accruing, is recorded so the
    # Meter/evidence show "notice sent" (was a broken proxy on claim.state)
    headers = _auth(client)
    stop_id = client.post(
        "/load",
        json={
            "facility_name": "R",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Broker",
            "free_time_minutes": 0,  # accrues immediately
        },
        headers=headers,
    ).json()["stop_id"]
    client.post(f"/load/{stop_id}/arrive", headers=headers)

    assert client.get(f"/load/{stop_id}/meter", headers=headers).json()["notice_sent"] is False
    sent = client.post(f"/load/{stop_id}/notice", headers=headers)
    assert sent.status_code == 201 and sent.json()["sent"] is True
    assert client.get(f"/load/{stop_id}/meter", headers=headers).json()["notice_sent"] is True


def test_claim_detail_shows_contents_and_evidence(client, db):
    headers = _auth(client)
    stop_id = _create(client, headers)
    # no claim generated yet -> 404
    assert client.get(f"/load/{stop_id}/claim", headers=headers).status_code == 404

    client.post(f"/load/{stop_id}/arrive", headers=headers)
    client.post(f"/load/{stop_id}/claim", headers=headers)

    d = client.get(f"/load/{stop_id}/claim", headers=headers).json()
    assert d["filed"] is True
    assert d["facility"] == "Dallas Receiver"
    assert d["counterparty"] == "Acme Brokerage"
    assert d["chain_valid"] is True  # the GPS evidence chain verifies
    assert d["record_count"] >= 1
    assert any(e["type"] == "GEOFENCE" for e in d["timeline"])  # the arrival is in the pack


def test_meter_reports_condition_photo_count(client, db):
    # the Load tab's Evidence "Photos" reflects real captures, not a static label
    headers = _auth(client)
    stop_id = _create(client, headers)
    client.post(f"/load/{stop_id}/arrive", headers=headers)
    assert client.get(f"/load/{stop_id}/meter", headers=headers).json()["photos_captured"] == 0

    cap = client.post(
        "/protection/condition/start", json={"stop_id": stop_id}, headers=headers
    ).json()["capture_id"]
    client.post(f"/protection/condition/{cap}/photo", json={"prompt": "seals"}, headers=headers)
    assert client.get(f"/load/{stop_id}/meter", headers=headers).json()["photos_captured"] == 1


def test_evidence_detail_aggregates_photos_and_timeline(client, db):
    # the consolidated Evidence view: every F4 log for the stop in one place —
    # cargo-condition photos (with their guided prompt) + the GPS-verified timeline
    headers = _auth(client)
    stop_id = _create(client, headers)
    client.post(f"/load/{stop_id}/arrive", headers=headers)

    # capture two guided condition photos
    cap = client.post(
        "/protection/condition/start", json={"stop_id": stop_id}, headers=headers
    ).json()["capture_id"]
    client.post(f"/protection/condition/{cap}/photo", json={"prompt": "seals"}, headers=headers)
    client.post(
        f"/protection/condition/{cap}/photo",
        json={"prompt": "trailer_exterior"},
        headers=headers,
    )

    ev = client.get(f"/load/{stop_id}/evidence", headers=headers)
    assert ev.status_code == 200
    body = ev.json()
    assert body["facility"] == "Dallas Receiver"
    assert body["chain_valid"] is True
    assert body["photo_count"] == 2
    prompts = {p["prompt"] for p in body["photos"]}
    assert prompts == {"seals", "trailer_exterior"}
    assert all(p["content_hash"] for p in body["photos"])  # a verified hash per photo
    assert body["record_count"] >= 2
    assert any(e["type"] == "PHOTO" for e in body["timeline"])


def test_evidence_photo_serves_the_captured_image_bytes(client, db):
    # F6 image serving: a captured condition photo's real bytes are stored and
    # served back (owner-gated), so the Evidence view shows a true thumbnail.
    import base64

    headers = _auth(client)
    stop_id = _create(client, headers)
    client.post(f"/load/{stop_id}/arrive", headers=headers)

    png = b"\x89PNG\r\n\x1a\nFAKE-IMAGE-BYTES"
    cap = client.post(
        "/protection/condition/start", json={"stop_id": stop_id}, headers=headers
    ).json()["capture_id"]
    client.post(
        f"/protection/condition/{cap}/photo",
        json={"prompt": "seals", "content_b64": base64.b64encode(png).decode()},
        headers=headers,
    )

    body = client.get(f"/load/{stop_id}/evidence", headers=headers).json()
    photo = body["photos"][0]
    assert photo["has_image"] is True
    assert photo["artifact_id"]

    img = client.get(f"/load/{stop_id}/evidence/photo/{photo['artifact_id']}", headers=headers)
    assert img.status_code == 200
    assert img.content == png  # the exact bytes round-trip

    # another driver can never fetch it
    intruder = client.post(
        "/auth/register", json={"email": "peeker@example.com", "password": "pw-123456"}
    ).json()["token"]
    hi = {"Authorization": f"Bearer {intruder}"}
    assert (
        client.get(f"/load/{stop_id}/evidence/photo/{photo['artifact_id']}", headers=hi).status_code
        == 403
    )


def test_evidence_photo_404_for_unknown_artifact(client, db):
    headers = _auth(client)
    stop_id = _create(client, headers)
    zero = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/load/{stop_id}/evidence/photo/{zero}", headers=headers).status_code == 404


def test_meter_404_for_unknown_stop(client):
    headers = _auth(client)
    resp = client.get("/load/00000000-0000-0000-0000-000000000000/meter", headers=headers)
    assert resp.status_code == 404


def test_notice_and_claim_require_arrival(client, db):
    headers = _auth(client)
    stop_id = _create(client, headers)
    # before arrival there is no claim -> 409
    assert client.post(f"/load/{stop_id}/notice", headers=headers).status_code == 409
    assert client.post(f"/load/{stop_id}/claim", headers=headers).status_code == 409


def test_generate_claim_closes_the_loop(client, db):
    headers = _auth(client)
    stop_id = _create(client, headers)
    client.post(f"/load/{stop_id}/arrive", headers=headers)

    # within free time: nothing to notify yet, but a pack still files (amount 0)
    notice = client.post(f"/load/{stop_id}/notice", headers=headers)
    assert notice.status_code == 201
    assert notice.json()["sent"] is False

    claim = client.post(f"/load/{stop_id}/claim", headers=headers)
    assert claim.status_code == 201
    body = claim.json()
    assert body["chain_valid"] is True  # GPS-backed evidence chain
    assert body["state"] in ("packaged", "invoiced", "exported")  # a pack was filed

    # the Meter now reports filed=True -> the UI freezes and stays frozen across
    # tab switches (the flag is on the claim, not client state)
    m = client.get(f"/load/{stop_id}/meter", headers=headers).json()
    assert m["filed"] is True
    assert m["detention_cents"] == body["amount_cents"]  # frozen at the filed amount
