"""AI-CONTEXT: §10.2's empty state — "Add a load" by rate-con photo.

PRD §108 calls this the PRIMARY way a Load is created and PRD §7.16(b) puts "a test
driver with a parsed rate con" in the Foundation DoD. Every piece existed — F6 stores
`rate_con`, F9 parses documents, `create_load_from_parsed_terms` takes the result —
and the only place the three were ever joined was the Foundation e2e test. The Load
tab shipped a four-field manual form instead.

The load-bearing rule these tests hold is that the import produces a DRAFT and creates
nothing. M4-FR4 specifies a driver-confirm step, and a machine read of a photographed
contract is a proposal: only the driver can see both the paper and the screen.
"""

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f09_ai_gateway import public as ai
from app.main import app
from app.modules.m03_detention import public as m3

RATE_CON = base64.b64encode(b"%PDF-1.4 rate confirmation").decode()
DALLAS = (32.7767, -96.7970)


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


def _with_parse(monkeypatch, parsed):
    monkeypatch.setattr(ai, "resolve_provider", lambda: ai.FakeModelProvider(parsed))


def _import(client, headers):
    return client.post(
        "/load/import",
        json={"content_b64": RATE_CON, "filename": "rc.pdf", "content_type": "application/pdf"},
        headers=headers,
    )


FULL_TERMS = {
    "reference_number": "L-9001",
    "detention_rate_cents_per_hour": 7500,
    "free_time_minutes": 120,
    # AI-CONTEXT: a rate con is a ROUTE (§23 entry 68). The parse used to return one
    # receiver; it now returns the stops table, pickups included.
    "stops": [
        {
            "stop_type": "delivery",
            "name": "ACME Distribution Center",
            "address": None,
            "appointment_start": None,
            "appointment_end": None,
        }
    ],
    "accessorial_terms": {"tonu": "50% of linehaul"},
}


def test_a_photographed_rate_con_becomes_a_draft(client, db, monkeypatch):
    _with_parse(monkeypatch, FULL_TERMS)
    headers = _headers(client, "rc-draft@example.com")

    body = _import(client, headers).json()

    assert body["readable"] is True
    assert body["parsed"]["detention_rate_cents_per_hour"] == 7500
    assert body["parsed"]["reference_number"] == "L-9001"


def test_the_import_creates_no_load(client, db, monkeypatch):
    """The confirm step is the product, not a formality: a parse is a proposal about a
    contract, and the driver is the only one holding both the paper and the phone."""
    _with_parse(monkeypatch, FULL_TERMS)
    headers = _headers(client, "rc-nocreate@example.com")

    _import(client, headers)

    assert client.get("/load/active", headers=headers).json()["stop_id"] is None


def test_the_rate_con_is_filed_to_the_wallet(client, db, monkeypatch):
    """It is the contract the claim will be argued from, so it is worth keeping
    whatever the parse makes of it.

    Kept, but not filed among the driver's credentials: a rate con photographed and
    not yet turned into a load is attached to nothing, and the wallet's job is the
    credential a driver holds now (§23 entry 79)."""
    _with_parse(monkeypatch, FULL_TERMS)
    headers = _headers(client, "rc-filed@example.com")

    doc_id = _import(client, headers).json()["document_id"]

    wallet = client.get("/protection/wallet", headers=headers).json()
    assert wallet["documents"] == []  # the driver has no credentials on file yet
    assert [(d["id"], d["doc_type"]) for d in wallet["unattached"]] == [(doc_id, "rate_con")]


def test_a_rate_con_silent_on_a_term_is_flagged_before_the_driver_accepts(
    client, db, monkeypatch
):
    """M4-FR4's pre-acceptance warning."""
    _with_parse(monkeypatch, {"detention_rate_cents_per_hour": 7500})
    headers = _headers(client, "rc-silent@example.com")

    body = _import(client, headers).json()

    assert set(body["silent_on"]) == {"free_time", "tonu"}


def test_an_unreadable_rate_con_files_the_document_and_invents_nothing(client, db, monkeypatch):
    """With no model configured — the state this stack runs in by default — the parse
    fails. Inventing plausible terms would put a number the contract never contained
    behind a detention claim, so the honest answer is 'type them yourself'."""
    monkeypatch.setattr(ai, "resolve_provider", lambda: ai.FakeModelProvider())
    headers = _headers(client, "rc-unreadable@example.com")

    body = _import(client, headers).json()

    assert body["readable"] is False
    assert body["parsed"] is None
    assert body["document_id"] is not None  # the contract is kept regardless


def test_the_draft_offers_a_facility_we_already_know(client, db, monkeypatch):
    _with_parse(monkeypatch, FULL_TERMS)
    known = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "ACME Distribution Center", *DALLAS
    )
    headers = _headers(client, "rc-match@example.com")

    body = _import(client, headers).json()

    # candidates now hang off the STOP they belong to: a route is two different docks,
    # and the delivery's matches are no use to the pickup (§23 entry 68)
    assert [c["facility_id"] for c in body["stops"][0]["facility_candidates"]] == [str(known.id)]


# --- The duplicate-facility defect the import surfaced ---
def test_a_confirmed_match_reuses_the_facility_instead_of_creating_one(client, db):
    known = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "ACME Distribution Center", *DALLAS
    )
    headers = _headers(client, "reuse@example.com")

    resp = client.post(
        "/load",
        json={
            "facility_name": "ACME Distribution Center",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme Brokerage",
            "facility_id": str(known.id),
        },
        headers=headers,
    )

    assert resp.status_code == 201
    meter = client.get(f"/load/{resp.json()['stop_id']}/meter", headers=headers).json()
    assert meter["facility_name"] == "ACME Distribution Center"
    assert len(facility.search_by_name(db, "ACME Distribution Center")) == 1


def test_two_loads_at_the_same_dock_do_not_create_two_facilities(client, db):
    """Before this, POST /load called create_facility unconditionally — so a driver
    who ran the same lane twice put two rows in the registry for one dock, and M2's
    dwell history aggregated over both halves."""
    headers = _headers(client, "dupes@example.com")
    payload = {
        "facility_name": "Fort Worth Receiving",
        "lat": DALLAS[0],
        "lon": DALLAS[1],
        "counterparty": "Acme Brokerage",
    }

    client.post("/load", json=payload, headers=headers)
    client.post("/load", json=payload, headers=headers)

    assert len(facility.search_by_name(db, "Fort Worth Receiving")) == 1


def test_a_load_built_from_a_rate_con_records_that_it_was_read(client, db, monkeypatch):
    """M5-FR1 shows the driver whether a machine read their appointment window or they
    typed it — the two carry different confidence, and only the driver knows which is
    right."""
    _with_parse(monkeypatch, FULL_TERMS)
    headers = _headers(client, "rc-source@example.com")
    doc_id = _import(client, headers).json()["document_id"]

    stop_id = client.post(
        "/load",
        json={
            "facility_name": "ACME Distribution Center",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme Brokerage",
            "rate_con_document_id": doc_id,
            "reference_number": "L-9001",
        },
        headers=headers,
    ).json()["stop_id"]

    meter = client.get(f"/load/{stop_id}/meter", headers=headers).json()
    # AI-CONTEXT: this asserted `appointment_source == "rate_con_parse"` for a load
    # created WITHOUT an appointment, and that was the defect (§23 entry 62): the
    # provenance was read off `load.source` — how the LOAD was made — so the Meter
    # credited a parse for a window that did not exist. Provenance now belongs to the
    # window, and a null window states no source.
    assert meter["appointment"] is None
    assert meter["appointment_source"] is None
    # the load itself still records that it came from a contract
    assert meter["facility_name"] == "ACME Distribution Center"


def test_rejecting_every_candidate_creates_rather_than_matching(client, db):
    """"None of these" is an ANSWER, and this route used to ignore it (§23 entry 66).

    A driver who rejected every candidate sent exactly what a driver who never answered
    sent — no facility id — so the name+geohash fallback ran anyway and could attach the
    load to a dock they had just looked at and refused. Every load created in the import
    sheet also shares one pair of coordinates, so the geohash half of that rule matches
    far more often than it should.
    """
    headers = _headers(client, "reject@example.com")
    body = {
        "facility_name": "Metro Market Warehouse",
        "lat": DALLAS[0],
        "lon": DALLAS[1],
        "counterparty": "Acme",
    }

    first = client.post("/load", json=body, headers=headers).json()["stop_id"]
    first_facility = client.get(f"/load/{first}/meter", headers=headers).json()["facility_name"]

    # silence still matches — right when nothing was ever asked (an unreadable rate con
    # offers no candidates at all)
    second = client.post("/load", json=body, headers=headers).json()["stop_id"]
    assert client.get(f"/load/{second}/meter", headers=headers).json()["facility_name"] == (
        first_facility
    )

    # ...but an explicit rejection creates a distinct dock rather than reusing that one
    third = client.post(
        "/load", json={**body, "create_new_facility": True}, headers=headers
    ).json()["stop_id"]
    assert client.get(f"/load/{third}/meter", headers=headers).status_code == 200

    from app.foundation.f02_facility import public as facility

    rows = facility.find_duplicate_candidates(db, "Metro Market Warehouse", *DALLAS)
    assert len(rows) >= 2  # the rejection produced its own record


def test_a_chosen_match_still_wins_over_the_rejection_flag(client, db):
    """The three cases are ordered: a chosen id is the strongest statement there is."""
    headers = _headers(client, "chosen@example.com")
    from app.foundation.f02_facility import public as facility

    fac = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Chosen Dock", *DALLAS
    )

    stop_id = client.post(
        "/load",
        json={
            "facility_name": "Something Else Entirely",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme",
            "facility_id": str(fac.id),
            "create_new_facility": True,  # contradictory; the explicit id wins
        },
        headers=headers,
    ).json()["stop_id"]

    assert (
        client.get(f"/load/{stop_id}/meter", headers=headers).json()["facility_name"]
        == "Chosen Dock"
    )


def test_a_facility_id_that_is_not_ours_to_use_404s(client, db):
    headers = _headers(client, "badfac@example.com")

    resp = client.post(
        "/load",
        json={
            "facility_name": "Nowhere",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme",
            "facility_id": "11111111-2222-3333-4444-555555555555",
        },
        headers=headers,
    )

    assert resp.status_code == 404


def test_a_form_of_nulls_is_not_a_read(client, db, monkeypatch):
    """A model handed something it cannot read answers with every key present and
    every value null — and F9's required-keys check tests for the KEY, so it passes.
    Without this the screen printed "Read from your rate con" over an empty form,
    which is the product asserting it did something it did not."""
    _with_parse(
        monkeypatch,
        {"detention_rate_cents_per_hour": None, "free_time_minutes": None, "rate_cents": None},
    )
    headers = _headers(client, "rc-nulls@example.com")

    body = _import(client, headers).json()

    assert body["readable"] is False
    assert body["parsed"] is None


def test_the_document_itself_is_sent_to_the_model_not_its_hash(client, db, monkeypatch):
    """The first version passed `document.content_hash` — copied from the Foundation
    e2e, where a fake provider made it irrelevant — so the live model was handed a
    SHA-256 string and answered, correctly, that it could read nothing."""
    seen = {}

    class _Recorder(ai.FakeModelProvider):
        def parse_structured(self, prompt, context):
            seen.update(context)
            return super().parse_structured(prompt, context)

    monkeypatch.setattr(ai, "resolve_provider", lambda: _Recorder(FULL_TERMS))
    headers = _headers(client, "rc-bytes@example.com")

    _import(client, headers)

    assert seen["document_b64"] == RATE_CON
    assert seen["document_media_type"] == "application/pdf"


# --- §10.2's anatomy: the next-stop preview ---
def test_the_meter_previews_the_next_stop(client, db):
    """§10.2's anatomy ends with a next-stop preview and this tab never had one.
    `list_stops` has been ordered by sequence since F5 was written and nothing asked
    it what comes after the dock the driver is standing at."""
    from app.foundation.f05_load import public as loads

    headers = _headers(client, "nextstop@example.com")
    stop_id = client.post(
        "/load",
        json={
            "facility_name": "First Dock",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme Brokerage",
        },
        headers=headers,
    ).json()["stop_id"]

    stop = loads.get_stop(db, __import__("uuid").UUID(stop_id))
    load = loads.get_load(db, stop.load_id)
    second = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Second Dock", 35.05, -89.87
    )
    loads.add_stop(db, load, second.id, loads.StopType.delivery)

    meter = client.get(f"/load/{stop_id}/meter", headers=headers).json()

    assert meter["next_stop"]["facility_name"] == "Second Dock"
    assert meter["next_stop"]["stop_type"] == "delivery"


def test_the_last_stop_previews_nothing(client, db):
    """Rather than an empty row that reads as a missing value."""
    headers = _headers(client, "laststop@example.com")
    stop_id = client.post(
        "/load",
        json={
            "facility_name": "Only Dock",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme Brokerage",
        },
        headers=headers,
    ).json()["stop_id"]

    assert client.get(f"/load/{stop_id}/meter", headers=headers).json()["next_stop"] is None


def test_the_rate_con_parse_is_schema_constrained_not_asked_nicely(client, db, monkeypatch):
    """F9 used to ask the model to "return ONLY a single valid JSON object" and then
    hunt for braces in whatever came back — a parser that works until it doesn't, on
    the document a detention claim is argued from."""
    from app.foundation.f05_load import public as loads

    seen = {}

    class _Recorder(ai.FakeModelProvider):
        def parse_structured(self, prompt, context):
            seen.update(context)
            return super().parse_structured(prompt, context)

    monkeypatch.setattr(ai, "resolve_provider", lambda: _Recorder(FULL_TERMS))
    headers = _headers(client, "rc-schema@example.com")

    _import(client, headers)

    assert seen["json_schema"] == loads.RATE_CON_SCHEMA
    # every object in the schema closes to additionalProperties: false, which the
    # format requires — and is why accessorial terms are a list, not an open map
    assert seen["json_schema"]["additionalProperties"] is False
    assert seen["json_schema"]["properties"]["accessorial_terms"]["type"] == "array"


def test_accessorial_terms_come_back_as_a_map_whatever_the_schema_had_to_say(
    client, db, monkeypatch
):
    """The schema has to express them as a list; callers keep the map they expect."""
    _with_parse(
        monkeypatch,
        {
            "detention_rate_cents_per_hour": 7500,
            "accessorial_terms": [{"term": "tonu", "wording": "50% of linehaul"}],
        },
    )
    headers = _headers(client, "rc-terms@example.com")

    body = _import(client, headers).json()

    assert body["parsed"]["accessorial_terms"] == {"tonu": "50% of linehaul"}
    assert "tonu" not in body["silent_on"]  # the contract does state it


# --- Load history: where a finished load goes ---
def _run_load(client, headers, name, lat=32.7767, lon=-96.7970, **extra):
    return client.post(
        "/load",
        json={
            "facility_name": name,
            "lat": lat,
            "lon": lon,
            "counterparty": "Acme Brokerage",
            **extra,
        },
        headers=headers,
    ).json()["stop_id"]


def test_a_finished_load_is_still_reachable(client, db):
    """Before this, ending a load left no way back to it. Its evidence log, condition
    captures and stop-scoped BOL were all still in the database with no route reaching
    them — and an evidence pack is worth having precisely because it can be produced
    weeks later when a broker disputes it."""
    headers = _headers(client, "history@example.com")
    stop_id = _run_load(client, headers, "ACME Distribution Center")
    client.post(f"/load/{stop_id}/end", headers=headers)

    assert client.get("/load/active", headers=headers).json()["stop_id"] is None  # gone from now
    [row] = client.get("/load/history", headers=headers).json()["loads"]
    assert row["facility_name"] == "ACME Distribution Center"
    assert row["stop_id"] == stop_id  # the evidence surface has its id back
    # what the log CONTAINS, not whether one exists: arm_stop opens a log for every
    # stop, so "a log exists" is an indicator that can never say no
    assert row["evidence_count"] == 0  # armed, but nothing captured yet


def test_ending_a_load_completes_it(client, db):
    """`LoadStatus` has carried draft/active/completed/canceled since F5 was written
    and `set_load_status` was never called from anywhere — so every load ever created
    sat in `draft`, and "completed" could not be listed even by something that wanted
    to."""
    headers = _headers(client, "completes@example.com")
    stop_id = _run_load(client, headers, "Only Dock")

    before = client.get("/load/history", headers=headers).json()["loads"][0]["status"]
    resp = client.post(f"/load/{stop_id}/end", headers=headers).json()

    assert before == "draft"
    assert resp["load_status"] == "completed"


def test_a_load_with_stops_still_running_is_not_completed(client, db):
    """A multi-stop load ends when its LAST stop departs, not its first."""
    from app.foundation.f05_load import public as loads

    headers = _headers(client, "multistop@example.com")
    stop_id = _run_load(client, headers, "First Dock")
    stop = loads.get_stop(db, uuid.UUID(stop_id))
    load = loads.get_load(db, stop.load_id)
    second = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Second Dock", 35.05, -89.87
    )
    loads.add_stop(db, load, second.id, loads.StopType.delivery)

    resp = client.post(f"/load/{stop_id}/end", headers=headers).json()

    assert resp["load_status"] == "draft"  # the second stop is still pending


def test_history_shows_only_what_the_load_produced(client, db, monkeypatch):
    """A load that captured nothing says so. Rendering an empty money row or a dead
    evidence link would read as data we lost rather than a quiet week."""
    _with_parse(monkeypatch, FULL_TERMS)
    headers = _headers(client, "produced@example.com")
    doc_id = _import(client, headers).json()["document_id"]
    _run_load(client, headers, "Papered Dock", rate_con_document_id=doc_id)

    [row] = client.get("/load/history", headers=headers).json()["loads"]

    # the contract it was built from is attached to the stop, so history can show it
    assert row["documents"] == ["rate_con"]
    # no claim was filed, so there is no money to state
    assert row["detention_cents"] is None
    assert row["claim_state"] is None


def test_history_states_money_when_a_claim_was_filed(client, db):
    """This asserted `is not None` against an amount that was always ZERO — the driver
    arrived and claimed in the same millisecond, so nothing accrued. It passed because
    the endpoint returned a literal 0, which the row renders as "no money". A test that
    can only be satisfied by the value the screen ignores is not testing the screen.
    The driver now waits three hours at the dock, which is what a claim is FOR."""
    headers = _headers(client, "money-history@example.com")
    stop_id = _run_load(client, headers, "Slow Dock")
    client.post(f"/load/{stop_id}/arrive", headers=headers)

    waited = datetime.now(UTC) - timedelta(hours=3)
    presence = db.scalars(select(location.GeofencePresence)).one()
    presence.entered_at = waited
    db.flush()

    client.post(f"/load/{stop_id}/claim", headers=headers)

    [row] = client.get("/load/history", headers=headers).json()["loads"]

    assert row["detention_cents"] > 0
    # a company driver's claim ends `exported` — a pack for their carrier, no invoice.
    # The row renders `money.state.<state>` and that key existed for three of the five
    # states a claim can hold, so this, the commonest outcome for a driver without their
    # own authority, printed the raw key at them.
    assert row["claim_state"] == "exported"


def test_history_is_yours_only(client, db):
    mine = _headers(client, "mine-hist@example.com")
    theirs = _headers(client, "theirs-hist@example.com")
    _run_load(client, mine, "My Dock")

    assert client.get("/load/history", headers=theirs).json()["loads"] == []


def test_history_counts_what_was_captured_not_whether_a_log_exists(client, db):
    """`arm_stop` opens an evidence log for every stop, so "a log exists" is true for
    every load ever created — an indicator that always says yes. The first live run
    showed "evidence pack" against a load where nothing had been captured."""
    headers = _headers(client, "evcount@example.com")
    quiet = _run_load(client, headers, "Quiet Dock")
    client.post(f"/load/{quiet}/end", headers=headers)

    busy = _run_load(client, headers, "Busy Dock", lat=35.05, lon=-89.87)
    client.post(f"/load/{busy}/arrive", headers=headers)  # a real capture lands here
    client.post(f"/load/{busy}/end", headers=headers)

    history = client.get("/load/history", headers=headers).json()["loads"]
    rows = {r["facility_name"]: r for r in history}

    assert rows["Quiet Dock"]["evidence_count"] == 0
    assert rows["Busy Dock"]["evidence_count"] > 0


# --- A rate con is a ROUTE (§23 entry 68) ---
TWO_STOPS = {
    "reference_number": "BRL-78426",
    "broker_name": "Blue Road Logistics LLC",
    "detention_rate_cents_per_hour": 5000,
    "free_time_minutes": 120,
    "stops": [
        {
            "stop_type": "pickup",
            "name": "Harvest Foods DC",
            "address": "1200 Commerce Pkwy, Dallas, TX 75212",
            "appointment_start": "2026-08-03T08:00:00",
            "appointment_end": "2026-08-03T10:00:00",
        },
        {
            "stop_type": "delivery",
            "name": "Metro Market Warehouse",
            "address": "8450 Lakeside Ave, Columbus, OH 43228",
            "appointment_start": "2026-08-05T07:30:00",
            "appointment_end": None,
        },
    ],
    "accessorial_terms": {},
}


def test_the_draft_carries_every_stop_in_order(client, db, monkeypatch):
    """The parse used to return one receiver, so a two-stop contract lost its pickup —
    and with it any detention claim at the shipper, which detains drivers as often as a
    receiver does."""
    _with_parse(monkeypatch, TWO_STOPS)
    headers = _headers(client, "route-draft@example.com")

    stops = _import(client, headers).json()["stops"]

    assert [s["stop_type"] for s in stops] == ["pickup", "delivery"]
    assert [s["name"] for s in stops] == ["Harvest Foods DC", "Metro Market Warehouse"]
    # the pickup's WINDOW survives: "08:00 - 10:00" is two times, and collapsing it to
    # one loses the half a driver is judged on
    assert stops[0]["appointment_start"].startswith("2026-08-03T08:00")
    assert stops[0]["appointment_end"].startswith("2026-08-03T10:00")
    # each stop gets its own candidates — the delivery's matches are no use to a pickup
    assert "facility_candidates" in stops[0]
    assert "facility_candidates" in stops[1]


def test_confirming_a_route_creates_a_stop_for_each(client, db):
    headers = _headers(client, "route-create@example.com")

    resp = client.post(
        "/load",
        json={
            "facility_name": "unused when stops are given",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Blue Road Logistics LLC",
            "stops": [
                {
                    "facility_name": "Harvest Foods DC",
                    "lat": 32.7767,
                    "lon": -96.797,
                    "stop_type": "pickup",
                    "appointment": "2026-08-03T08:00:00Z",
                    "appointment_end": "2026-08-03T10:00:00Z",
                    "create_new_facility": True,
                },
                {
                    "facility_name": "Metro Market Warehouse",
                    "lat": 39.9612,
                    "lon": -83.0907,
                    "stop_type": "delivery",
                    "appointment": "2026-08-05T07:30:00Z",
                    "create_new_facility": True,
                },
            ],
        },
        headers=headers,
    )

    assert resp.status_code == 201
    assert len(resp.json()["stop_ids"]) == 2

    from app.foundation.f05_load import public as loads

    load = loads.get_load(db, uuid.UUID(resp.json()["load_id"]))
    stops = loads.list_stops(db, load)
    assert [s.stop_type.value for s in stops] == ["pickup", "delivery"]
    # each dock is filed where it actually is — the delivery is in Ohio, not Texas
    assert stops[0].facility_id != stops[1].facility_id

    # §10.2's next-stop preview finally has something to preview: it could never
    # render for an imported load, because there was never a second stop
    meter = client.get(f"/load/{stops[0].id}/meter", headers=headers).json()
    assert meter["next_stop"]["facility_name"] == "Metro Market Warehouse"


def test_only_the_first_stop_is_armed(client, db):
    """Arming opens an F4 evidence log and a live geofence, and a driver is at one dock
    at a time."""
    headers = _headers(client, "route-arm@example.com")
    resp = client.post(
        "/load",
        json={
            "facility_name": "x",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Broker",
            "stops": [
                {"facility_name": "First Dock", "lat": 32.7767, "lon": -96.797,
                 "stop_type": "pickup", "create_new_facility": True},
                {"facility_name": "Second Dock", "lat": 39.9612, "lon": -83.0907,
                 "stop_type": "delivery", "create_new_facility": True},
            ],
        },
        headers=headers,
    )

    active = client.get("/load/active", headers=headers).json()["stop_id"]
    assert active == resp.json()["stop_ids"][0]


def test_leaving_a_stop_advances_to_the_next_one(client, db):
    """§23 entry 69 — the delivery existed and no screen could reach it.

    Multi-stop loads arm only their first stop, and nothing armed the next: departing
    the pickup left zero armed stops, so `/load/active` answered null and the Load tab
    fell back to its empty state while the delivery sat `pending` in the database.
    """
    headers = _headers(client, "advance@example.com")
    created = client.post(
        "/load",
        json={
            "facility_name": "x",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Blue Road",
            "stops": [
                {"facility_name": "Harvest Foods DC", "lat": 32.7767, "lon": -96.797,
                 "stop_type": "pickup", "create_new_facility": True},
                {"facility_name": "Metro Market Warehouse", "lat": 39.9612, "lon": -83.0907,
                 "stop_type": "delivery", "create_new_facility": True},
            ],
        },
        headers=headers,
    ).json()
    pickup, delivery = created["stop_ids"]
    assert client.get("/load/active", headers=headers).json()["stop_id"] == pickup

    ended = client.post(f"/load/{pickup}/end", headers=headers).json()

    # the route moves on rather than the load disappearing
    assert ended["next_stop_id"] == delivery
    assert ended["load_status"] != "completed"  # a pickup is not the end of a load
    assert client.get("/load/active", headers=headers).json()["stop_id"] == delivery
    meter = client.get(f"/load/{delivery}/meter", headers=headers).json()
    assert meter["facility_name"] == "Metro Market Warehouse"


def test_leaving_the_last_stop_ends_the_load(client, db):
    headers = _headers(client, "advance-last@example.com")
    created = client.post(
        "/load",
        json={
            "facility_name": "x",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Blue Road",
            "stops": [
                {"facility_name": "Only Dock", "lat": 32.7767, "lon": -96.797,
                 "stop_type": "delivery", "create_new_facility": True},
            ],
        },
        headers=headers,
    ).json()

    ended = client.post(f"/load/{created['stop_ids'][0]}/end", headers=headers).json()

    assert ended["next_stop_id"] is None
    assert ended["load_status"] == "completed"
    assert client.get("/load/active", headers=headers).json()["stop_id"] is None


def test_history_reports_the_whole_route_not_its_first_stop(client, db):
    """Every figure on a history row was read off `stops[0]`.

    A pickup-and-delivery load showed the PICKUP's facility name, the PICKUP's claim
    and the PICKUP's documents, with nothing saying a second stop existed. Measured on
    a real two-stop load the owner ran: $83.67 shown against $271.43 actually claimed —
    the delivery's money simply absent, and no way to tell from the row.
    """
    from app.foundation.f05_load import public as loads

    headers = _headers(client, "route-history@example.com")
    pickup_id = _run_load(client, headers, "Harvest Foods DC")
    pickup = loads.get_stop(db, uuid.UUID(pickup_id))
    load = loads.get_load(db, pickup.load_id)
    dest = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Metro Market Warehouse", 39.96, -83.09
    )
    loads.add_stop(db, load, dest.id, loads.StopType.delivery)

    # detention at BOTH ends: three hours at each dock
    for stop_id in (pickup_id, None):
        if stop_id is None:
            stop_id = client.post(f"/load/{pickup_id}/end", headers=headers).json()["next_stop_id"]
        client.post(f"/load/{stop_id}/arrive", headers=headers)
        presence = db.scalars(
            select(location.GeofencePresence).where(location.GeofencePresence.active.is_(True))
        ).one()
        presence.entered_at = datetime.now(UTC) - timedelta(hours=3)
        db.flush()
        client.post(f"/load/{stop_id}/claim", headers=headers)

    [row] = client.get("/load/history", headers=headers).json()["loads"]

    assert row["stop_count"] == 2
    assert row["facility_name"] == "Harvest Foods DC"
    assert row["destination_name"] == "Metro Market Warehouse"
    # both claims, summed — not the pickup's alone
    claims = [
        m3.claim_for_stop(db, s.id) for s in loads.list_stops(db, loads.get_load(db, load.id))
    ]
    assert row["detention_cents"] == sum(c.amount_cents for c in claims)
    assert row["detention_cents"] > max(c.amount_cents for c in claims)


def test_history_names_no_destination_for_a_single_stop_load(client, db):
    """A one-stop load has no far end, and "Dock -> Dock" would invent a route it
    never had."""
    headers = _headers(client, "one-stop-history@example.com")
    _run_load(client, headers, "Only Dock")

    [row] = client.get("/load/history", headers=headers).json()["loads"]

    assert row["stop_count"] == 1
    assert row["destination_name"] is None


def test_the_confirmed_address_is_kept_on_a_new_facility(client, db):
    """The sheet collected an address, geocoded it, and threw the string away — so
    every facility this route created had `address` NULL. Seventh parsed value found
    reaching no field, and the reason two same-named docks could not be told apart on
    the screen that asks "is this the same place?"."""
    headers = _headers(client, "kept-address@example.com")
    stop_id = _run_load(
        client,
        headers,
        "Metro Market Warehouse",
        lat=39.96,
        lon=-83.09,
        address="8450 Lakeside Ave, Columbus, OH 43228",
    )

    from app.foundation.f05_load import public as loads

    stop = loads.get_stop(db, uuid.UUID(stop_id))
    fac = facility.get_facility(db, stop.facility_id)
    assert fac.address == "8450 Lakeside Ave, Columbus, OH 43228"


def test_same_named_candidates_say_which_is_which(client, db):
    """A real driver was offered "Metro Market Warehouse" twice, identical, on the
    screen that asks whether it is the same place. Both were real — one in Columbus,
    one in Dallas — and a question whose answers cannot be told apart cannot be
    answered."""
    from app.foundation.f05_load.domain import ratecon

    facility.create_facility(
        db,
        facility.FacilityType.shipper_receiver,
        "Metro Market Warehouse",
        39.96,
        -83.09,
        address="8450 Lakeside Ave, Columbus, OH 43228",
    )
    facility.create_facility(
        db,
        facility.FacilityType.shipper_receiver,
        "Metro Market Warehouse",
        32.7767,
        -96.797,
        address="1200 Commerce St, Dallas, TX 75208",
    )

    candidates = ratecon.facility_candidates_for(db, "Metro Market Warehouse")

    assert len(candidates) >= 2
    localities = {c["locality"] for c in candidates}
    assert "Columbus, OH" in localities
    assert "Dallas, TX" in localities
    # and the thing that made them indistinguishable is still true, which is the point
    assert len({c["name"] for c in candidates}) == 1


def test_a_load_pack_holds_every_stops_photos(client, db):
    """Entry 71 found a per-LOG export could only show a fragment of a stop. This is
    the same sentence one layer up: a per-STOP export can only show a fragment of a
    ROUTE. A driver who photographed a pickup and a delivery had eight photos in the
    system and no document holding more than four."""
    from app.foundation.f04_evidence import public as evidence
    from app.foundation.f05_load import public as loads
    from app.modules.m05_protection import public as m5

    headers = _headers(client, "load-pack@example.com")
    pickup_id = _run_load(client, headers, "Harvest Foods DC")
    pickup = loads.get_stop(db, uuid.UUID(pickup_id))
    load = loads.get_load(db, pickup.load_id)
    dest = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Metro Market Warehouse", 39.96, -83.09
    )
    delivery = loads.add_stop(db, load, dest.id, loads.StopType.delivery)
    loads.arm_stop(db, delivery)

    # two photos at each dock, in each stop's own log
    for stop, dock in ((pickup, b"pickup"), (delivery, b"delivery")):
        log = db.get(evidence.EvidenceLog, stop.evidence_log_id)
        for prompt in (b"trailer", b"seals"):
            evidence.append_record(
                db, log, evidence.RecordType.PHOTO, {"prompt": prompt.decode()}
            )
            evidence.attach_artifact(
                db, log, evidence.ArtifactType.photo, content=dock + prompt
            )
    db.flush()

    pack = m5.load_pack(db, load.id)

    assert pack is not None
    assert len(pack.artifacts) == 4  # both docks, not whichever one a row pointed at
    groups = []
    for record in pack.timeline:
        if record["group"] not in groups:
            groups.append(record["group"])
    # `_run_load` files a delivery; what matters is that each section names its own
    # dock and its place in the route, in route order
    assert groups == [
        "1 · Delivery · Harvest Foods DC",
        "2 · Delivery · Metro Market Warehouse",
    ]
    # the document is captioned with the LOAD, not one stop's log label
    assert pack.label == load.reference_number
    assert pack.verification["chain_valid"] is True


def test_the_pack_says_which_stop_and_who_it_is_against(client, db):
    """`Parties` carried one row, the facility — and a detention claim is against the
    BROKER, who was never named on the document making the claim. Nothing said whether
    a stop was a pickup or a delivery either, so two packs from one load could not be
    ordered by a clerk holding both."""
    from app.api.m05_protection import _context_for
    from app.foundation.f05_load import public as loads

    headers = _headers(client, "pack-context@example.com")
    stop_id = _run_load(client, headers, "Harvest Foods DC")
    stop = loads.get_stop(db, uuid.UUID(stop_id))

    context = _context_for(db, "stop", stop.id)

    assert ("Broker", "Acme Brokerage") in context.parties
    assert ("Stop", "Delivery · 1 of 1") in context.references
    assert ("Facility", "Harvest Foods DC") in context.references
