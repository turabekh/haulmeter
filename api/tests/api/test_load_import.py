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

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.foundation.f09_ai_gateway import public as ai
from app.main import app

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
    "receiver_name": "ACME Distribution Center",
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
    whatever the parse makes of it."""
    _with_parse(monkeypatch, FULL_TERMS)
    headers = _headers(client, "rc-filed@example.com")

    doc_id = _import(client, headers).json()["document_id"]

    wallet = client.get("/protection/wallet", headers=headers).json()
    assert [(d["id"], d["doc_type"]) for d in wallet["documents"]] == [(doc_id, "rate_con")]


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

    assert [c["facility_id"] for c in body["facility_candidates"]] == [str(known.id)]


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
    headers = _headers(client, "money-history@example.com")
    stop_id = _run_load(client, headers, "Slow Dock")
    client.post(f"/load/{stop_id}/arrive", headers=headers)
    client.post(f"/load/{stop_id}/claim", headers=headers)

    [row] = client.get("/load/history", headers=headers).json()["loads"]

    assert row["detention_cents"] is not None
    assert row["claim_state"] is not None


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
