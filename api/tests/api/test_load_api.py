"""AI-CONTEXT: HTTP API tests for the active-load lifecycle behind The Meter.
TestClient with get_db overridden to the transactional test session. Proves
create -> arrive -> meter: before arrival the Meter is pre-arrival; after a
geofence ENTER the detention clock is live.
"""

import uuid
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


def test_active_load_names_the_dock_not_just_the_stop(client, db):
    """§23 entry 82. §11.3's Work preset is "armed stop + its facility intel" and
    §10.1's contextual CTA is "Arm stop" — both need to know WHICH facility the armed
    stop is at, and this route returned an opaque id. So the Map tab could not tell the
    driver's own dock from any other receiver on screen."""
    headers = _auth(client)
    empty = client.get("/load/active", headers=headers).json()
    # the keys are present even with no load: a caller must not have to guess whether
    # absence means "no load" or "this endpoint doesn't answer that"
    assert empty["facility_id"] is None and empty["facility_name"] is None

    _create(client, headers)
    active = client.get("/load/active", headers=headers).json()
    assert active["facility_id"] is not None
    assert active["facility_name"] == "Dallas Receiver"


def test_create_load_keeps_the_rate_and_the_contract_terms(client, db):
    """§23 entry 84 — the sixth and seventh parsed values to reach no field.

    `Load.rate_cents` and `Load.accessorial_terms` are columns F5 has had since it was
    written, and `create_load_from_parsed_terms` has mapped both from a parsed dict
    since the same day — but the only route that creates a load in production never
    accepted them, so every load ever filed carried a null rate and an empty terms map.
    """
    from app.foundation.f05_load import public as loads

    headers = _auth(client)
    body = client.post(
        "/load",
        json={
            "facility_name": "Dallas Receiver",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme Brokerage",
            "rate_cents": 285000,
            "accessorial_terms": {"tonu": "50% of linehaul", "layover": "$150 per night"},
        },
        headers=headers,
    ).json()
    stop = loads.get_stop(db, uuid.UUID(body["stop_id"]))
    load = loads.get_load(db, stop.load_id)
    assert load.rate_cents == 285000
    assert load.accessorial_terms["tonu"] == "50% of linehaul"
    assert load.accessorial_terms["layover"] == "$150 per night"


def test_m04_finally_judges_a_load_against_terms_it_actually_has(client, db):
    """M4-FR4's pre-acceptance check reads `load.accessorial_terms`, and nothing had
    ever filled it — so it reported EVERY load in production as silent on TONU and
    layover, whatever the contract said. The reader was right; its input was empty."""
    from app.foundation.f05_load import public as loads
    from app.modules.m04_accessorial import public as m4

    headers = _auth(client)
    body = client.post(
        "/load",
        json={
            "facility_name": "Dallas Receiver",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme Brokerage",
            "rate_cents_per_hour": 7500,
            "accessorial_terms": {"tonu": "50% of linehaul", "layover": "$150 per night"},
        },
        headers=headers,
    ).json()
    stop = loads.get_stop(db, uuid.UUID(body["stop_id"]))
    check = m4.check_accessorial_terms(loads.get_load(db, stop.load_id))
    assert check["missing"] == [] and check["silent"] is False

    # and a contract that really is silent still says so — the warning is not defanged
    quiet = client.post(
        "/load",
        json={
            "facility_name": "R2",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme",
        },
        headers=headers,
    ).json()
    quiet_stop = loads.get_stop(db, uuid.UUID(quiet["stop_id"]))
    quiet_check = m4.check_accessorial_terms(loads.get_load(db, quiet_stop.load_id))
    assert set(quiet_check["missing"]) == {"tonu", "layover"}


def test_meter_carries_what_the_profit_calculator_needs(client, db):
    """§23 entry 85. M8's calculator asked the driver to retype a Rate the load already
    knew, and defaulted its receiver to the NIL UUID — so every true-profit figure in
    production valued detention at a facility that does not exist."""
    headers = _auth(client)
    stop_id = client.post(
        "/load",
        json={
            "facility_name": "Dallas Receiver",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme Brokerage",
            "rate_cents": 285000,
            "free_time_minutes": 90,
            "rate_cents_per_hour": 6000,
        },
        headers=headers,
    ).json()["stop_id"]
    meter = client.get(f"/load/{stop_id}/meter", headers=headers).json()
    assert meter["rate_cents"] == 285000
    assert meter["facility_id"] is not None
    # the terms the calculator also stops guessing at
    assert meter["free_time_minutes"] == 90 and meter["rate_cents_per_hour"] == 6000


def test_meter_states_no_rate_when_the_contract_did_not(client, db):
    # §11.7: a rate con silent on the linehaul must not become a confident zero
    headers = _auth(client)
    stop_id = _create(client, headers)
    assert client.get(f"/load/{stop_id}/meter", headers=headers).json()["rate_cents"] is None


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
            # finding F4: this test used to omit the address and pass anyway, because the
            # notice was addressed to the literal `counterparty@unknown`. A notice with no
            # recipient is not a sent notice, so the address is what the case needs.
            "counterparty_email": "ap@broker.example",
            "free_time_minutes": 0,  # accrues immediately
        },
        headers=headers,
    ).json()["stop_id"]
    client.post(f"/load/{stop_id}/arrive", headers=headers)

    assert client.get(f"/load/{stop_id}/meter", headers=headers).json()["notice_sent"] is False
    sent = client.post(f"/load/{stop_id}/notice", headers=headers)
    assert sent.status_code == 201 and sent.json()["sent"] is True
    assert sent.json()["delivery"] == "sent"
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
    # AI-CONTEXT: the arrival is in the pack — as what it ACTUALLY WAS (§23 entry 138).
    #
    # This used to assert a GEOFENCE record, and one was always there because `arrive`
    # synthesised a ping AT THE FACILITY'S COORDINATES: the geofence "observation" was
    # manufactured from the very location it claimed to observe. With no device fix
    # there is no geofence observation to record, and the honest artifact is the
    # driver's own attestation. `test_a_device_fix_puts_a_real_GEOFENCE_in_the_pack`
    # below covers the case where a reading genuinely exists.
    assert any(e.get("event") == "arrived" for e in d["timeline"]), "the arrival is not in the pack"
    # and the claim screen can NAME it: `claim_evidence` dropped `event` until entry 138,
    # so this timeline could only ever render "Action recorded" (§23 entry 70's fix,
    # which never reached this projection).
    assert not any(e["type"] == "GEOFENCE" for e in d["timeline"]), (
        "a geofence observation was recorded for an arrival no sensor observed"
    )


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


class TestEvidenceTimelineSaysWhatHappened:
    """§23 entry 70 — the pack said an event occurred and not which.

    A stop that had been armed, arrived at, notified on and departed produced ONE
    record: the on-time proof check. Geofence ENTER/EXIT are F3 events and nothing
    bridged them into F4; the notice and the departure were never recorded. And the API
    then dropped each record's payload, so the only label available was the RecordType
    — which is how a broker came to receive a timeline reading "Event recorded 03:14".
    """

    def _run_a_stop(self, client, headers):
        stop_id = client.post(
            "/load",
            json={
                "facility_name": "Dispute Dock",
                "lat": DALLAS[0],
                "lon": DALLAS[1],
                "counterparty": "Broker",
                # without an address there is no notice and no `notice_sent` record —
                # which is finding F5's fix, asserted separately below
                "counterparty_email": "ap@broker.example",
                "free_time_minutes": 0,  # detention accrues at once, so a notice sends
            },
            headers=headers,
        ).json()["stop_id"]
        client.post(f"/load/{stop_id}/arrive", headers=headers)
        client.post(f"/load/{stop_id}/notice", headers=headers)
        client.post(f"/load/{stop_id}/end", headers=headers)
        return stop_id

    def test_the_three_moments_a_dispute_turns_on_are_recorded(self, client, db):
        headers = _auth(client)
        stop_id = self._run_a_stop(client, headers)

        body = client.get(f"/load/{stop_id}/evidence", headers=headers).json()
        events = [e["event"] for e in body["timeline"]]

        assert "arrived" in events
        assert "notice_sent" in events
        assert "departed" in events
        assert body["chain_valid"] is True

    def test_every_entry_says_what_it_was(self, client, db):
        """The label is the point: a timeline of unnamed events proves nothing."""
        headers = _auth(client)
        stop_id = self._run_a_stop(client, headers)

        timeline = client.get(f"/load/{stop_id}/evidence", headers=headers).json()["timeline"]

        assert timeline, "a run stop must produce a timeline"
        assert all(e["event"] for e in timeline), (
            f"unnamed entries: {[e for e in timeline if not e['event']]}"
        )

    def test_the_timeline_is_in_the_order_it_happened(self, client, db):
        headers = _auth(client)
        stop_id = self._run_a_stop(client, headers)

        timeline = client.get(f"/load/{stop_id}/evidence", headers=headers).json()["timeline"]
        events = [e["event"] for e in timeline]

        assert events.index("arrived") < events.index("departed")

    def test_a_notice_that_did_not_send_is_not_recorded(self, client, db):
        """"We told them at 10:05" is the fact a dispute turns on, so logging an attempt
        that no-oped inside free time would assert it falsely."""
        headers = _auth(client)
        stop_id = client.post(
            "/load",
            json={
                "facility_name": "Quiet Dock",
                "lat": DALLAS[0],
                "lon": DALLAS[1],
                "counterparty": "Broker",
                "free_time_minutes": 240,  # nothing owed yet, so no notice goes out
            },
            headers=headers,
        ).json()["stop_id"]
        client.post(f"/load/{stop_id}/arrive", headers=headers)

        assert client.post(f"/load/{stop_id}/notice", headers=headers).json()["sent"] is False

        events = [
            e["event"]
            for e in client.get(f"/load/{stop_id}/evidence", headers=headers).json()["timeline"]
        ]
        assert "notice_sent" not in events


# AI-CONTEXT: the load RECORD — what a finished load contains, before it is downloaded
# or sent (owner request, 2026-08-11).
#
# Past loads offered two things: open ONE stop's evidence, or "Export whole load", a
# blind PDF download. There was no way to see what the document held without first
# putting it on the phone, and no way to send it to anybody — while
# `/protection/load/{id}/share` has accepted `kind="load"` since the whole-route pack
# was written, called by nothing.
#
# The load-bearing property is that this endpoint and `load_pack` read the SAME source
# in the SAME order. A screen that disagrees with the document is worse than no screen:
# it tells a driver they are sending something they are not.
def _multi_stop_load(client, headers, db):
    """A pickup and a delivery, because every read built before §23 entry 78 assumed
    one stop and this is the shape that catches that."""
    from app.foundation.f02_facility import public as facility
    from app.foundation.f05_load import public as loads

    stop_id = _create(client, headers)
    stop = loads.get_stop(db, uuid.UUID(stop_id))
    load = loads.get_load(db, stop.load_id)
    second = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Kroger DC", 41.8, -87.6
    )
    loads.add_stop(db, load, second.id, loads.StopType.delivery)
    return load, stop


def test_the_record_reports_the_WHOLE_route(db, client):
    headers = _auth(client)
    load, _ = _multi_stop_load(client, headers, db)

    body = client.get(f"/load/{load.id}/record", headers=headers).json()

    assert body["stop_count"] == 2
    assert len(body["stops"]) == 2, "a two-stop load reported one stop"
    assert body["destination_name"] == "Kroger DC", "the far end of the route was dropped"
    assert [s["sequence"] for s in body["stops"]] == [0, 1], "stops out of route order"


def test_the_record_names_the_photos_it_will_send(db, client):
    """Not a COUNT. The screen shows what was captured, so the read has to carry the
    artifact ids the existing photo route serves."""
    from app.foundation.f05_load import public as loads
    from app.modules.m05_protection import public as m5

    headers = _auth(client)
    load, stop = _multi_stop_load(client, headers, db)
    loads.arm_stop(db, stop)
    cap = m5.start_condition_capture(db, stop, load.account_id, m5.CapturePhase.pickup)
    m5.add_condition_photo(db, cap, "trailer_exterior", content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    body = client.get(f"/load/{load.id}/record", headers=headers).json()

    first = next(s for s in body["stops"] if s["stop_id"] == str(stop.id))
    assert first["photos"], "a captured photo did not reach the record"
    assert first["photos"][0]["artifact_id"], "no artifact id — the screen cannot show it"
    assert body["photo_count"] == 1


def test_the_record_carries_the_recipient_so_the_screen_can_say_there_is_none(db, client):
    """HANDOFF-122 §3: nothing in this product had ever written `contact_email`, so on
    most real loads there is nobody to send to — and a driver must learn that BEFORE
    tapping Send, not from a refusal afterwards."""
    headers = _auth(client)
    load, _ = _multi_stop_load(client, headers, db)

    body = client.get(f"/load/{load.id}/record", headers=headers).json()

    assert "counterparty_email" in body
    assert body["counterparty_name"] == "Acme Brokerage"


def test_the_record_agrees_with_the_DOCUMENT_it_describes(db, client):
    """The one that matters. `load_pack` groups by stop over `stop_evidence`; so does
    this. If they diverge the screen is lying about what the broker receives."""
    from app.foundation.f05_load import public as loads
    from app.modules.m05_protection import public as m5

    headers = _auth(client)
    load, stop = _multi_stop_load(client, headers, db)
    loads.arm_stop(db, stop)
    cap = m5.start_condition_capture(db, stop, load.account_id, m5.CapturePhase.pickup)
    m5.add_condition_photo(db, cap, "seals", content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    body = client.get(f"/load/{load.id}/record", headers=headers).json()
    pack = m5.load_pack(db, load.id)

    # the pack's artifacts are the photos it will print; the screen's count is the same
    # photos counted one layer up. An unconditional assertion, not a guarded one — a
    # comparison that can skip itself proves nothing (HANDOFF-122's revert-check lesson).
    assert body["photo_count"] == len(pack.artifacts), "the screen and the document disagree"
    assert body["chain_valid"] == pack.verification["chain_valid"]


def test_one_driver_cannot_read_anothers_record(db, client):
    headers = _auth(client)
    load, _ = _multi_stop_load(client, headers, db)
    other = client.post(
        "/auth/register", json={"email": "thief@example.com", "password": "pw-123456"}
    )
    theirs = {"Authorization": f"Bearer {other.json()['token']}"}

    assert client.get(f"/load/{load.id}/record", headers=theirs).status_code == 403


def test_the_record_requires_auth(db, client):
    headers = _auth(client)
    load, _ = _multi_stop_load(client, headers, db)
    assert client.get(f"/load/{load.id}/record").status_code == 401


def test_an_unknown_load_is_404_not_500(client):
    headers = _auth(client)
    assert client.get(f"/load/{uuid.uuid4()}/record", headers=headers).status_code == 404


# AI-CONTEXT: the manual arrival, told the truth about (§23 entry 138).
#
# THE DEFECT. `POST /load/{stop}/arrive` called `evaluate_ping` with the FACILITY'S own
# coordinates, so the position fix a detention claim rests on — on the path a driver
# takes precisely when the background sensor did not fire — was a reading of where the
# warehouse is, written into `location_ping` and counted by the pack's Location basis
# section among the driver's device fixes. That section tells a broker those records are
# "as reported by the driver's device", and for this one it was not true.
#
# The arrival still counts from anywhere: detention frequently starts in a gate queue
# half a mile from the dock, and refusing it would strand the driver this button exists
# for. What changed is that the record says what actually happened.
DOCK_LAT, DOCK_LON = DALLAS
FAR_LAT, FAR_LON = 32.9000, -96.7970  # ~13.7 km due north of the dock


def _arrival_record(db, stop_id):
    """The `arrived` record out of the stop's own hash chain."""
    from app.foundation.f04_evidence import public as evidence
    from app.foundation.f05_load import public as loads

    stop = loads.get_stop(db, uuid.UUID(stop_id))
    rows = evidence.stop_evidence(db, stop.id)["timeline"]
    assert rows, "the stop chain is empty"
    return stop, rows


def test_arriving_records_NO_ping_at_the_facilitys_own_coordinates(client, db):
    """The defect, asserted directly: nothing may write a position the device never
    produced. This is the test that fails if the old `evaluate_ping` call comes back."""
    from app.foundation.f03_location.domain.models import LocationPing

    headers = _auth(client)
    stop_id = _create(client, headers)

    assert client.post(f"/load/{stop_id}/arrive", headers=headers).status_code == 201

    pings = db.query(LocationPing).count()
    assert pings == 0, "a position fix was invented for a device that reported none"


def test_arriving_with_no_fix_still_starts_the_clock(client, db):
    """The fallback's whole reason to exist. A phone with no fix must still be able to
    say "I am here" — recording no position, never the facility's."""
    headers = _auth(client)
    stop_id = _create(client, headers)

    resp = client.post(f"/load/{stop_id}/arrive", headers=headers)

    assert resp.status_code == 201
    assert resp.json()["arrived"] is True
    assert client.get(f"/load/{stop_id}/meter", headers=headers).json()["phase"] != "not_arrived"
    _, rows = _arrival_record(db, stop_id)
    arrived = next(r for r in rows if r.get("event") == "arrived")
    assert arrived is not None


def test_the_device_fix_and_its_distance_go_into_the_chain(client, db):
    """The owner's ask: record where the driver actually said they were, when it differs
    from the load's address. It rides in the hash-chained record, so a broker arguing
    about it is arguing with the evidence rather than with a number nobody wrote down."""
    from app.foundation.f04_evidence import public as evidence
    from app.foundation.f05_load import public as loads

    headers = _auth(client)
    stop_id = _create(client, headers)

    resp = client.post(
        f"/load/{stop_id}/arrive",
        headers=headers,
        json={"lat": DOCK_LAT + 0.001, "lon": DOCK_LON, "accuracy_m": 12.5},
    )
    assert resp.status_code == 201

    stop = loads.get_stop(db, uuid.UUID(stop_id))
    log = db.get(evidence.EvidenceLog, stop.evidence_log_id)
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)
    payload = next(
        r["payload"] for r in pack.timeline if (r.get("payload") or {}).get("event") == "arrived"
    )

    assert payload["presence_basis"] == "device_fix"
    assert payload["arrival_lat"] == DOCK_LAT + 0.001
    assert payload["arrival_accuracy_m"] == 12.5
    assert 100 < payload["distance_from_facility_m"] < 130, payload["distance_from_facility_m"]
    assert payload["far_from_facility"] is False


def test_no_fix_is_recorded_as_NO_FIX_rather_than_filled_in(client, db):
    """The half that matters most. An absent reading is a fact; substituting the
    facility's coordinates for it is the defect this entry removes."""
    from app.foundation.f04_evidence import public as evidence
    from app.foundation.f05_load import public as loads

    headers = _auth(client)
    stop_id = _create(client, headers)
    client.post(f"/load/{stop_id}/arrive", headers=headers)

    stop = loads.get_stop(db, uuid.UUID(stop_id))
    log = db.get(evidence.EvidenceLog, stop.evidence_log_id)
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)
    payload = next(
        r["payload"] for r in pack.timeline if (r.get("payload") or {}).get("event") == "arrived"
    )

    assert payload["presence_basis"] == "no_fix"
    assert payload["arrival_lat"] is None
    assert payload["arrival_lon"] is None
    assert payload["distance_from_facility_m"] is None


def test_arriving_from_far_away_ASKS_before_it_records(client, db):
    """409, with the distance, so the client can put the question to the driver."""
    headers = _auth(client)
    stop_id = _create(client, headers)

    resp = client.post(
        f"/load/{stop_id}/arrive", headers=headers, json={"lat": FAR_LAT, "lon": FAR_LON}
    )

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["reason"] == "too_far"
    assert detail["distance_m"] > 10000
    assert detail["facility_name"] == "Dallas Receiver"
    # and NOTHING was recorded: a question is not an arrival
    assert client.get(f"/load/{stop_id}/meter", headers=headers).json()["phase"] == "not_arrived"


def test_a_confirmed_far_arrival_PROCEEDS_and_says_so_in_the_record(client, db):
    """The warning is a question, never a gate. A driver in a gate queue is legitimately
    arriving, and the recorded distance is what a broker can argue with later."""
    from app.foundation.f04_evidence import public as evidence
    from app.foundation.f05_load import public as loads

    headers = _auth(client)
    stop_id = _create(client, headers)

    resp = client.post(
        f"/load/{stop_id}/arrive",
        headers=headers,
        json={"lat": FAR_LAT, "lon": FAR_LON, "confirmed": True},
    )

    assert resp.status_code == 201, "a confirmed arrival was refused"
    assert client.get(f"/load/{stop_id}/meter", headers=headers).json()["phase"] != "not_arrived"

    stop = loads.get_stop(db, uuid.UUID(stop_id))
    log = db.get(evidence.EvidenceLog, stop.evidence_log_id)
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)
    payload = next(
        r["payload"] for r in pack.timeline if (r.get("payload") or {}).get("event") == "arrived"
    )
    assert payload["far_from_facility"] is True, "the distance was not recorded as unusual"
    assert payload["distance_from_facility_m"] > 10000


def test_a_nearby_arrival_is_never_questioned(client, db):
    """A yard is not a warning. The threshold sits far above F3's 150 m radius on
    purpose — a warning that fires on ordinary days is one drivers learn to tap through,
    and a confirmation that means nothing is worse than none."""
    headers = _auth(client)
    stop_id = _create(client, headers)

    resp = client.post(
        f"/load/{stop_id}/arrive",
        headers=headers,
        json={"lat": DOCK_LAT + 0.004, "lon": DOCK_LON},  # ~440 m — a gate queue
    )

    assert resp.status_code == 201


def test_a_device_fix_puts_a_real_GEOFENCE_in_the_pack(client, db):
    """When there IS a reading, it is recorded as an observation — which is exactly what
    the old code faked when there was none."""
    headers = _auth(client)
    stop_id = _create(client, headers)
    client.post(
        f"/load/{stop_id}/arrive",
        headers=headers,
        json={"lat": DOCK_LAT, "lon": DOCK_LON},
    )
    client.post(f"/load/{stop_id}/claim", headers=headers)

    d = client.get(f"/load/{stop_id}/claim", headers=headers).json()
    assert any(e["type"] == "GEOFENCE" for e in d["timeline"])
