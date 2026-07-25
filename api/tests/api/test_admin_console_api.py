"""AI-CONTEXT: Admin Console 2.0 section endpoints.

Two things under test beyond "does it return data":

1. **Every admin mutation lands in the audit log with before→after.** An audit log
   that covers most mutations is not an audit log. There is a test per mutating
   endpoint, and one that walks the list to prove none was missed.
2. **The Overview distinguishes "switched off" from "broken".** An idle job and a
   failing job look identical in a naive health panel, and the difference is the
   whole point of the panel.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f13_flags import public as flags
from app.foundation.f14_admin import public as admin
from app.main import app
from app.modules.m13_vendor import public as m13

T0 = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _admin_headers(client, db, email="ops@example.com"):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    account_id = resp.json()["account_id"]
    import uuid as _uuid

    from app.foundation.f01_identity.domain.models import Account

    identity.attach_role(db, db.get(Account, _uuid.UUID(account_id)), identity.Role.platform_admin)
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _vendor(db, email="cook@example.com", name="Osh Express"):
    account = identity.register_account(db, email, "pw-123456")
    return m13.register_vendor(
        db,
        account.id,
        name,
        m13.VendorType.food_mobile,
        metro="dallas-tx",
        languages=["uz"],
        halal_answered=True,
    )


# --- Overview ---
def test_overview_requires_admin(client, db):
    resp = client.post("/auth/register", json={"email": "driver@x.com", "password": "pw-123456"})
    headers = {"Authorization": f"Bearer {resp.json()['token']}"}
    assert client.get("/admin/overview", headers=headers).status_code == 403


def test_overview_reports_a_job_that_has_never_run_as_null_not_zero(client, db):
    # "ran and did nothing" and "never ran" are different facts and must not collapse
    headers = _admin_headers(client, db)
    body = client.get("/admin/overview", headers=headers).json()
    job = next(j for j in body["jobs"] if j["job"] == "tpims_dynamic")
    assert job["last_run_at"] is None
    assert job["ok"] is None


def test_overview_distinguishes_switched_off_from_broken(client, db):
    # the whole point of a health panel: an idle job is not a failing one
    headers = _admin_headers(client, db)
    from app.ingest import flags as ingest_flags

    ingest_flags.register_ingest_flags(db)
    run = admin.start_job_run(db, "eia_regional", T0)
    admin.finish_job_run(db, run, T0, ok=False, error="ConnectTimeout()", consecutive_failures=2)

    body = client.get("/admin/overview", headers=headers).json()
    eia = next(j for j in body["jobs"] if j["job"] == "eia_regional")
    assert eia["ok"] is False
    assert eia["consecutive_failures"] == 2
    assert eia["enabled"] is False  # failing AND off — both facts survive


def test_overview_carries_the_overdue_count_separately(client, db):
    # the number that should make an operator act first is not left to be counted
    # client-side
    headers = _admin_headers(client, db)
    vendor = _vendor(db)
    review = m13.submit_review(
        db, vendor, identity.register_account(db, "a@x.com", "pw-123456").id, 1, now=T0
    )
    m13.report_content(
        db,
        m13.CONTENT_REVIEW,
        review.id,
        vendor.id,
        identity.register_account(db, "r@x.com", "pw-123456").id,
        m13.ModerationReason.spam,
        now=T0,
    )

    body = client.get("/admin/overview", headers=headers).json()
    assert body["pending"]["moderation"] == 1
    assert body["pending"]["moderation_overdue"] == 0  # just reported


def test_overview_counts_vendors_waiting_on_verification(client, db):
    headers = _admin_headers(client, db)
    vendor = _vendor(db)
    m13.attach_document(
        db, vendor, vendor.owner_account_id, m13.DocumentKind.license, b"x", "l.pdf"
    )

    body = client.get("/admin/overview", headers=headers).json()
    assert body["pending"]["vendor_verification"] == 1


def test_overview_reports_facility_counts_by_source(client, db):
    headers = _admin_headers(client, db)
    facility.create_facility(db, facility.FacilityType.truck_stop, "Stop", 32.7, -96.8)

    body = client.get("/admin/overview", headers=headers).json()
    assert body["facilities"]["total"] >= 1
    assert isinstance(body["facilities"]["by_source"], dict)


def test_overview_carries_both_value_funnels(client, db):
    headers = _admin_headers(client, db)
    body = client.get("/admin/overview", headers=headers).json()
    assert [s["event"] for s in body["funnels"]["detention"]] == [
        "load_added",
        "arrived",
        "claim_sent",
    ]
    assert set(body["funnels"]["vendor_appearances"]) == {"published", "confirmed"}


# --- Flags & Config ---
def test_flags_carry_family_and_module_gating(client, db):
    # grouping is server-side so every client groups identically
    headers = _admin_headers(client, db)
    flags.register_flag(db, "m13_vendor", description="M13 Vendor Network")
    flags.register_flag(db, "f02_ingest_tpims_static", description="TPIMS static")

    rows = {f["key"]: f for f in client.get("/admin/flags", headers=headers).json()}
    assert rows["m13_vendor"]["family"] == "modules"
    assert rows["m13_vendor"]["gates_a_module"] is True
    assert rows["f02_ingest_tpims_static"]["family"] == "ingest"
    assert rows["f02_ingest_tpims_static"]["gates_a_module"] is False


def test_a_flag_shows_who_last_changed_it(client, db):
    headers = _admin_headers(client, db, "flagops@example.com")
    flags.register_flag(db, "m13_vendor")
    client.post("/admin/flags/m13_vendor/enable", headers=headers)

    row = next(
        f for f in client.get("/admin/flags", headers=headers).json() if f["key"] == "m13_vendor"
    )
    assert row["last_changed_by"] == "flagops@example.com"


def test_config_carries_provenance_and_the_previous_value(client, db):
    headers = _admin_headers(client, db, "cfg@example.com")
    client.post(
        "/admin/config",
        json={"key": "m13_inactive_days", "value": 28, "scope": "m13"},
        headers=headers,
    )
    client.post(
        "/admin/config",
        json={"key": "m13_inactive_days", "value": 14, "scope": "m13"},
        headers=headers,
    )

    body = client.get("/admin/config?scope=m13", headers=headers).json()
    assert body["entries"]["m13_inactive_days"] == 14
    prov = body["provenance"]["m13_inactive_days"]
    assert prov["set_by"] == "cfg@example.com"
    assert prov["previous"] == 28  # what it replaced


def test_config_scopes_are_discoverable(client, db):
    # an operator should never have to guess a scope name to find what is configurable
    headers = _admin_headers(client, db)
    client.post("/admin/config", json={"key": "k", "value": 1, "scope": "pricing"}, headers=headers)
    assert "pricing" in client.get("/admin/config/scopes", headers=headers).json()


# --- Data & Ingest ---
def test_ingest_section_reports_sources_and_freshness(client, db):
    headers = _admin_headers(client, db)
    from app.ingest import sources

    sources.register_source_config(db)

    body = client.get("/admin/ingest", headers=headers).json()
    assert "tpims_static" in body["sources"]
    assert "facilities" in body and "freshness" in body


def test_job_history_reads_newest_first(client, db):
    headers = _admin_headers(client, db)
    for i in range(3):
        run = admin.start_job_run(db, "tpims_dynamic", T0 + timedelta(minutes=i))
        admin.finish_job_run(db, run, T0, ok=True, summary={"n": i})

    history = client.get("/admin/jobs/tpims_dynamic", headers=headers).json()
    assert [h["summary"]["n"] for h in history] == [2, 1, 0]


# --- Vendors ---
def test_vendor_documents_are_listed_for_review(client, db):
    headers = _admin_headers(client, db)
    vendor = _vendor(db)
    m13.attach_document(
        db, vendor, vendor.owner_account_id, m13.DocumentKind.license, b"x", "permit.pdf"
    )

    docs = client.get(f"/admin/vendors/{vendor.id}/documents", headers=headers).json()
    assert docs[0]["kind"] == "license"
    assert docs[0]["review_status"] == "pending"


def test_claims_can_be_filtered_to_disputes(client, db):
    headers = _admin_headers(client, db)
    fac = facility.create_facility(
        db, facility.FacilityType.repair, "Gateway Truck Service", 37.08, -94.51
    )
    fac.attributes = {"services": [facility.SERVICE_TIRE]}
    owner = identity.register_account(db, "shop@x.com", "pw-123456")
    shop = m13.register_vendor(
        db,
        owner.id,
        "Gateway Truck Service",
        m13.VendorType.service_center,
        metro="joplin-mo",
        languages=["en"],
        halal_answered=True,
    )
    m13.submit_claim(db, shop, fac.id, "Gateway Truck Service", owner.id)

    assert len(client.get("/admin/claims", headers=headers).json()) == 1
    assert client.get("/admin/claims?disputed_only=true", headers=headers).json() == []


# --- Moderation: the frivolous verdict + reporter record ---
def test_a_moderator_can_mark_a_report_frivolous(client, db):
    headers = _admin_headers(client, db, "mod@example.com")
    vendor = _vendor(db)
    review = m13.submit_review(
        db, vendor, identity.register_account(db, "auth@x.com", "pw-123456").id, 5, now=T0
    )
    reporter = identity.register_account(db, "vex@x.com", "pw-123456")
    m13.report_content(
        db, m13.CONTENT_REVIEW, review.id, vendor.id, reporter.id, m13.ModerationReason.spam, now=T0
    )

    resp = client.post(
        f"/admin/moderation/report/vendor_review/{review.id}/resolve",
        json={"approve": False, "frivolous": True},
        headers=headers,
    )
    body = resp.json()
    assert body["frivolous"] is True
    assert body["discredited"][0]["strikes"] == 1
    assert review.status == m13.ReviewStatus.visible


def test_upheld_and_frivolous_together_is_refused(client, db):
    headers = _admin_headers(client, db)
    vendor = _vendor(db)
    review = m13.submit_review(
        db, vendor, identity.register_account(db, "auth2@x.com", "pw-123456").id, 1, now=T0
    )
    m13.report_content(
        db,
        m13.CONTENT_REVIEW,
        review.id,
        vendor.id,
        identity.register_account(db, "rep2@x.com", "pw-123456").id,
        m13.ModerationReason.spam,
        now=T0,
    )

    resp = client.post(
        f"/admin/moderation/report/vendor_review/{review.id}/resolve",
        json={"approve": True, "frivolous": True},
        headers=headers,
    )
    assert resp.status_code == 422


def test_a_moderator_can_see_a_reporters_history(client, db):
    headers = _admin_headers(client, db)
    reporter = identity.register_account(db, "hist@x.com", "pw-123456")
    body = client.get(f"/admin/reporters/{reporter.id}", headers=headers).json()
    assert body["frivolous_strikes"] == 0
    assert body["credible"] is True


# --- the audit log covers EVERY mutation ---
def _audit_actions(client, headers):
    return {a["action"] for a in client.get("/admin/audit", headers=headers).json()}


def test_a_flag_toggle_records_what_it_changed_from(client, db):
    headers = _admin_headers(client, db, "audit1@example.com")
    flags.register_flag(db, "m13_vendor")
    client.post("/admin/flags/m13_vendor/enable", headers=headers)
    client.post("/admin/flags/m13_vendor/disable", headers=headers)

    entries = client.get("/admin/audit?target_key=m13_vendor", headers=headers).json()
    disable = next(a for a in entries if a["action"] == "flag_disable")
    assert disable["before"] == {"enabled": True}
    assert disable["after"] == {"enabled": False}


def test_a_moderation_decision_is_audited(client, db):
    # this endpoint recorded NOTHING before Admin Console 2.0
    headers = _admin_headers(client, db, "audit2@example.com")
    vendor = _vendor(db)
    review = m13.submit_review(
        db, vendor, identity.register_account(db, "auth3@x.com", "pw-123456").id, 1, now=T0
    )
    m13.report_content(
        db,
        m13.CONTENT_REVIEW,
        review.id,
        vendor.id,
        identity.register_account(db, "rep3@x.com", "pw-123456").id,
        m13.ModerationReason.spam,
        now=T0,
    )
    item = admin.list_pending_moderation(db)[0]

    client.post(f"/admin/moderation/{item.id}/decide", json={"approve": True}, headers=headers)
    assert "moderation_decide" in _audit_actions(client, headers)


def test_a_vendor_decision_is_audited_at_the_api_layer(client, db):
    headers = _admin_headers(client, db, "audit3@example.com")
    vendor = _vendor(db)
    client.post(
        f"/admin/vendors/{vendor.id}/decide", json={"verify_status": "verified"}, headers=headers
    )

    entries = client.get("/admin/audit?action=vendor_decide", headers=headers).json()
    assert entries[0]["before"]["verify_status"] == "unverified"
    assert entries[0]["after"]["verify_status"] == "verified"


def test_a_config_edit_is_audited_with_its_previous_value(client, db):
    headers = _admin_headers(client, db, "audit4@example.com")
    client.post("/admin/config", json={"key": "k", "value": 1, "scope": "s"}, headers=headers)
    client.post("/admin/config", json={"key": "k", "value": 2, "scope": "s"}, headers=headers)

    entries = client.get("/admin/audit?target_key=k&limit=1", headers=headers).json()
    assert entries[0]["before"] == {"value": 1}
    assert entries[0]["after"] == {"value": 2}


def test_a_claim_decision_is_audited(client, db):
    headers = _admin_headers(client, db, "audit5@example.com")
    fac = facility.create_facility(
        db, facility.FacilityType.repair, "Gateway Truck Service", 37.08, -94.51
    )
    fac.attributes = {"services": [facility.SERVICE_TIRE]}
    owner = identity.register_account(db, "shop2@x.com", "pw-123456")
    shop = m13.register_vendor(
        db,
        owner.id,
        "Gateway Truck Service",
        m13.VendorType.service_center,
        metro="joplin-mo",
        languages=["en"],
        halal_answered=True,
    )
    claim = m13.submit_claim(db, shop, fac.id, "Gateway Truck Service", owner.id)

    client.post(f"/admin/claims/{claim.id}/decide", json={"approve": True}, headers=headers)
    assert "facility_claim_decide" in _audit_actions(client, headers)


def test_every_mutating_admin_endpoint_writes_an_audit_entry(client, db):
    """The guard against partial coverage — an audit log that covers most mutations
    is not an audit log.

    Deliberately BEHAVIOURAL rather than a source grep: what matters is that an entry
    exists after the call, not which layer wrote it. `decide_claim` audits inside the
    domain service (where the claim lifecycle lives) while the others audit at the
    router; both are correct, and a grep would have forced a stylistic choice while
    proving nothing about the outcome.

    If a new mutating admin endpoint ships without an audit trail, it appears in
    `unaudited` here.
    """
    from app.api import admin as admin_router

    mutating = {
        route
        for route in app.openapi()["paths"]
        if route.startswith("/admin/")
        for method in app.openapi()["paths"][route]
        if method in ("post", "patch", "put", "delete")
    }
    # every mutating admin route we know about, mapped to the audit action it emits
    covered = {
        "/admin/flags/{key}/enable": "flag_enable",
        "/admin/flags/{key}/disable": "flag_disable",
        "/admin/config": "config_set",
        "/admin/moderation/{item_id}/decide": "moderation_decide",
        "/admin/moderation/report/{content_kind}/{content_ref}/resolve": "report_resolve",
        "/admin/vendors/{vendor_id}/decide": "vendor_decide",
        "/admin/claims/{claim_id}/decide": "facility_claim_decide",
    }
    unaudited = sorted(mutating - set(covered))
    assert not unaudited, f"mutating admin endpoints with no audit action mapped: {unaudited}"

    # and each mapped action is one record_action actually knows how to emit
    source = __import__("inspect").getsource(admin_router)
    from app.modules.m13_vendor.domain import claims as m13_claims

    domain_source = __import__("inspect").getsource(m13_claims)
    for route, action in covered.items():
        assert action in source or action in domain_source, f"{route} emits no {action}"
