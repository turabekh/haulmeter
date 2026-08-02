"""AI-CONTEXT: §11.3 food filters — "presets over filters, one More-filters sheet".

The load-bearing property is that a filter can only ever show a driver LESS. Filters
run on the output of the §E1.9 quality laws and the Q-3 ranking, never in place of
either, so no combination of them can surface a lapsed appearance, a suspended
vendor, or reorder anything. Several tests below exist only to hold that line.

The halal filter is the delicate one. §23 settled that the platform makes no halal
claim of its own and shows the vendor's words verbatim. Filtering that free text
would have meant parsing a cook's sentence to decide who counts — so the cook answers
a CLOSED question too, and `certified` is unreachable without an approved
certificate. These tests assert both halves: that the filter works, and that it never
promotes anyone.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.foundation.f13_flags import public as flags
from app.main import app
from app.modules.m13_vendor import public as m13

MADISON = (43.0700, -89.4000)
BBOX = {"min_lat": 42.9, "min_lon": -89.6, "max_lat": 43.2, "max_lon": -89.2}


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def active(db):
    m13.register_module(db)
    flags.enable(db, m13.FLAG_KEY)
    # these tests predate the A6 half-split and mean "M13 is on", so they turn
    # on both halves. The split itself is asserted in test_vendor_flag_split.py.
    flags.enable(db, m13.SERVICE_CENTER_FLAG_KEY)
    return db


def _account(client, email):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _cook(client, db, name, languages, halal_claim, dish, price=1200, lat=None, lon=None):
    headers = _account(client, f"{name.replace(' ', '').lower()}@example.com")
    client.post(
        "/vendors/register",
        json={
            "name": name,
            "vendor_type": "food_mobile",
            "metro": "Madison WI",
            "languages": languages,
            "halal_disclosure": "see profile",
            "halal_answered": True,
        },
        headers=headers,
    )
    if halal_claim:
        client.patch("/vendor/profile", json={"halal_claim": halal_claim}, headers=headers)
    client.post("/vendor/menu", json={"name": dish, "price_cents": price}, headers=headers)
    fac = facility.create_facility(
        db, facility.FacilityType.truck_stop, f"{name} stop", lat or MADISON[0], lon or MADISON[1]
    )
    starts = datetime.now(UTC) + timedelta(minutes=30)
    client.post(
        "/vendor/appearances",
        json={
            "facility_id": str(fac.id),
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=4)).isoformat(),
            "menu_item_ids": [],
        },
        headers=headers,
    )
    return headers


@pytest.fixture
def three_cooks(client, active, db):
    """Ana (es/en, no halal claim, tamales) · Yusuf (so/en, vendor-says-halal, sambusa)
    · Gurpreet (pa/en, no claim, samosa)."""
    _cook(client, db, "Anas Tamales", ["es", "en"], None, "Tamales")
    _cook(client, db, "Yusuf Kitchen", ["so", "en"], "self_declared", "Sambusa", lat=43.075)
    _cook(client, db, "Gurpreet Dhaba", ["pa", "en"], None, "Samosa", lat=43.08)
    return _account(client, "driver@example.com")


def _names(resp):
    return sorted(e["name"] for e in resp.json())


def _search(client, driver, **params):
    return client.get("/vendors/appearances", params={**BBOX, **params}, headers=driver)


# --- the unfiltered baseline ---
def test_without_filters_a_driver_sees_everyone_in_view(client, three_cooks):
    assert _names(_search(client, three_cooks)) == [
        "Anas Tamales",
        "Gurpreet Dhaba",
        "Yusuf Kitchen",
    ]


# --- dish search ---
def test_a_driver_searches_the_dish_not_the_cook(client, three_cooks):
    # "tamales" is what a driver types; the cook's name is not what they know
    assert _names(_search(client, three_cooks, q="tamales")) == ["Anas Tamales"]
    assert _names(_search(client, three_cooks, q="sambusa")) == ["Yusuf Kitchen"]


def test_search_also_matches_the_vendors_name(client, three_cooks):
    assert _names(_search(client, three_cooks, q="dhaba")) == ["Gurpreet Dhaba"]


def test_search_ignores_case_and_padding(client, three_cooks):
    assert _names(_search(client, three_cooks, q="  TAMALES ")) == ["Anas Tamales"]


def test_a_search_that_matches_nothing_returns_nothing(client, three_cooks):
    # and the CLIENT says "none in this view" — an empty list is not "none anywhere"
    assert _search(client, three_cooks, q="sushi").json() == []


def test_an_empty_query_is_not_a_filter(client, three_cooks):
    assert len(_search(client, three_cooks, q="").json()) == 3
    assert len(_search(client, three_cooks, q="   ").json()) == 3


# --- language ---
def test_a_driver_finds_someone_who_speaks_their_language(client, three_cooks):
    assert _names(_search(client, three_cooks, language="pa")) == ["Gurpreet Dhaba"]
    assert _names(_search(client, three_cooks, language="so")) == ["Yusuf Kitchen"]


def test_a_language_everyone_speaks_narrows_nothing(client, three_cooks):
    assert len(_search(client, three_cooks, language="en").json()) == 3


# --- halal, and what the platform refuses to assert ---
def test_the_halal_filter_uses_the_vendors_own_closed_answer(client, three_cooks):
    assert _names(_search(client, three_cooks, halal="self_declared")) == ["Yusuf Kitchen"]


def test_a_vendor_who_makes_no_claim_is_never_included(client, three_cooks):
    # the platform must not infer halal from a sentence, a name, or a cuisine
    out = _names(_search(client, three_cooks, halal="self_declared"))
    assert "Anas Tamales" not in out
    assert "Gurpreet Dhaba" not in out


def test_the_entry_carries_the_RUNG_so_the_label_can_be_honest(client, three_cooks):
    entry = next(e for e in _search(client, three_cooks).json() if e["name"] == "Yusuf Kitchen")
    # the client renders "vendor says halal" from this — never a bare "Halal"
    assert entry["halal_claim"] == "self_declared"


def test_certified_cannot_be_self_awarded(client, active, db):
    headers = _account(client, "claimer@example.com")
    client.post(
        "/vendors/register",
        json={
            "name": "Claims Certified",
            "vendor_type": "food_mobile",
            "metro": "Madison WI",
            "languages": ["en"],
            "halal_disclosure": "halal",
            "halal_answered": True,
        },
        headers=headers,
    )
    resp = client.patch("/vendor/profile", json={"halal_claim": "certified"}, headers=headers)

    # downgraded, not refused: "vendor says halal" is still true, and refusing would
    # leave an honest cook unable to say anything at all
    assert resp.status_code == 200
    assert resp.json()["halal_claim"] == "self_declared"


def test_the_portal_only_offers_rungs_the_server_will_honour(client, active, db):
    headers = _account(client, "offered@example.com")
    client.post(
        "/vendors/register",
        json={
            "name": "Offered Rungs",
            "vendor_type": "food_mobile",
            "metro": "Madison WI",
            "languages": ["en"],
            "halal_disclosure": "halal",
            "halal_answered": True,
        },
        headers=headers,
    )
    available = client.get("/vendor/profile", headers=headers).json()["halal_claims_available"]
    assert "certified" not in available
    assert sorted(available) == ["not_claimed", "self_declared"]


def test_an_approved_certificate_unlocks_the_top_rung(client, active, db):
    import base64

    headers = _account(client, "certified@example.com")
    client.post(
        "/vendors/register",
        json={
            "name": "Certified Kitchen",
            "vendor_type": "food_mobile",
            "metro": "Madison WI",
            "languages": ["en"],
            "halal_disclosure": "certified halal",
            "halal_answered": True,
        },
        headers=headers,
    )
    client.post(
        "/vendor/documents",
        json={"kind": "halal_cert", "content_b64": base64.b64encode(b"cert").decode()},
        headers=headers,
    )
    vendor_id = client.get("/vendor/profile", headers=headers).json()["vendor_id"]

    # still pending — an upload is not an approval
    assert (
        client.patch("/vendor/profile", json={"halal_claim": "certified"}, headers=headers).json()[
            "halal_claim"
        ]
        == "self_declared"
    )

    vendor = m13.resolve_vendor(db, vendor_id)
    m13.decide_document(db, vendor.documents[0], approve=True)
    db.flush()

    assert (
        client.patch("/vendor/profile", json={"halal_claim": "certified"}, headers=headers).json()[
            "halal_claim"
        ]
        == "certified"
    )


@dataclass
class _FakeVendor:
    halal_claim: m13.HalalClaim
    name: str = "x"
    languages: list = field(default_factory=list)


@dataclass
class _FakeEntry:
    vendor: _FakeVendor
    offerings: list = field(default_factory=list)


def test_asking_for_halal_includes_the_certified():
    """A driver asking for halal wants both rungs — the LABEL is what distinguishes
    them, not the filter. Asking specifically for a certificate narrows further."""
    entries = [
        _FakeEntry(_FakeVendor(m13.HalalClaim.certified)),
        _FakeEntry(_FakeVendor(m13.HalalClaim.self_declared)),
        _FakeEntry(_FakeVendor(m13.HalalClaim.not_claimed)),
    ]
    assert len(m13.apply_filters(entries, halal="self_declared")) == 2
    assert len(m13.apply_filters(entries, halal="certified")) == 1
    assert len(m13.apply_filters(entries)) == 3  # no filter narrows nothing


# --- a filter can only ever show LESS ---
def test_filters_compose_without_widening(client, three_cooks):
    both = _search(client, three_cooks, language="en", halal="self_declared")
    assert _names(both) == ["Yusuf Kitchen"]


def test_no_filter_can_surface_something_undiscoverable(client, three_cooks, db):
    """The line that matters: the quality laws run FIRST and a filter narrows their
    output. A cancelled appearance must stay gone whatever is asked for."""
    for appearance in db.scalars(__import__("sqlalchemy").select(m13.Appearance)):
        m13.cancel_appearance(db, appearance)
    db.flush()

    for params in ({}, {"q": "tamales"}, {"language": "en"}, {"halal": "self_declared"}):
        assert _search(client, three_cooks, **params).json() == [], params


def test_filters_narrow_the_corridor_too(client, three_cooks):
    """Set while stopped, honoured while moving — which is the point of persisting
    them, since no keyboard is available at speed (§11.4)."""
    ahead = client.get(
        "/vendors/corridor",
        params={"lat": 43.0, "lon": -89.4, "heading_deg": 0, "halal": "self_declared"},
        headers=three_cooks,
    )
    assert ahead.status_code == 200
    assert all(e["halal_claim"] == "self_declared" for e in ahead.json())


def test_the_filters_stay_behind_the_module_flag(client, db):
    driver = _account(client, "nobody@example.com")
    assert _search(client, driver, q="tamales").status_code == 404
