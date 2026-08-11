"""The broker's address over HTTP, and D2's fresh-send rule.

Two halves of one job. The address becomes recordable (at creation, and on a load the
driver is already looking at), and a notice that could not go before becomes sendable once
the address is fixed — without ever sending twice to a broker who already has it.

Every address here is `@example` or `@*.example`: this session makes real recipients
possible for the first time and dev SMTP points at a live account.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import load as load_api
from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f05_load import public as loads
from app.foundation.f08_notifications import public as notify
from app.main import app
from app.modules.m03_detention import public as m3

DALLAS = (32.7767, -96.7970)


class FailingGateway:
    """A gateway may never fail its caller — the outcome rides back on the ref (F-06)."""

    def __init__(self, kind="SMTPServerDisconnected"):
        self.kind = kind
        self.sent = []

    def send_email(self, to_ref, subject, body):
        self.sent.append(to_ref)
        return f"smtp-failed-{self.kind}"


class CountingGateway:
    def __init__(self):
        self.sent = []

    def send_email(self, to_ref, subject, body):
        self.sent.append(to_ref)
        return f"smtp-ok-{len(self.sent)}"


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client, db, email="oo@example.com"):
    reg = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    account_id = uuid.UUID(reg.json()["account_id"])
    # own authority, so a filed claim actually opens a receivable — an account with no
    # profile files evidence-only, and dunning has nothing to chase
    identity.upsert_driver_profile(
        db, db.get(identity.Account, account_id), authority_type=identity.AuthorityType.own_mc
    )
    return account_id, {"Authorization": f"Bearer {reg.json()['token']}"}


def _create_load(client, headers, email="ap@acme.example"):
    body = {
        "facility_name": "Dock",
        "lat": DALLAS[0],
        "lon": DALLAS[1],
        "counterparty": "Acme",
        "free_time_minutes": 0,  # accrues at once, so a notice is due
    }
    if email is not None:
        body["counterparty_email"] = email
    return client.post("/load", json=body, headers=headers).json()


# --- collecting the address at creation ---
def test_a_load_can_be_created_with_the_brokers_address(client, db):
    _, headers = _auth(client, db)

    created = _create_load(client, headers)
    stop = loads.get_stop(db, uuid.UUID(created["stop_id"]))
    load = loads.get_load(db, stop.load_id)

    assert loads.get_counterparty(db, load.counterparty_id).contact_email == "ap@acme.example"


def test_a_junk_address_at_creation_is_refused_before_the_load_exists(client, db):
    _, headers = _auth(client, db)

    resp = client.post(
        "/load",
        json={
            "facility_name": "Dock", "lat": DALLAS[0], "lon": DALLAS[1],
            "counterparty": "Acme", "counterparty_email": "acme.example",
        },
        headers=headers,
    )

    assert resp.status_code == 422
    assert "@" in resp.json()["detail"]


def test_a_load_created_without_an_address_still_works(client, db):
    """The field is an offer, not a gate — a driver without the AP address must still file."""
    _, headers = _auth(client, db)

    created = _create_load(client, headers, email=None)

    assert created["stop_id"]


# --- PATCH ---
def _load_id(db, created):
    return loads.get_stop(db, uuid.UUID(created["stop_id"])).load_id


def test_the_address_can_be_added_to_a_load_that_had_none(client, db):
    _, headers = _auth(client, db)
    created = _create_load(client, headers, email=None)
    load_id = _load_id(db, created)

    resp = client.patch(
        f"/load/{load_id}/counterparty-email",
        json={"email": "ap@acme.example"},
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.json()["counterparty_email"] == "ap@acme.example"
    assert resp.json()["copied"] is False


def test_patching_another_drivers_load_is_refused(client, db):
    _, mine = _auth(client, db, email="owner@example.com")
    created = _create_load(client, mine)
    load_id = _load_id(db, created)
    _, theirs = _auth(client, db, email="intruder@example.com")

    resp = client.patch(
        f"/load/{load_id}/counterparty-email",
        json={"email": "elsewhere@nope.example"},
        headers=theirs,
    )

    assert resp.status_code == 403
    load = loads.get_load(db, load_id)
    assert loads.get_counterparty(db, load.counterparty_id).contact_email == "ap@acme.example"


def test_patching_a_load_that_does_not_exist_is_404(client, db):
    _, headers = _auth(client, db)

    resp = client.patch(
        f"/load/{uuid.uuid4()}/counterparty-email",
        json={"email": "ap@acme.example"},
        headers=headers,
    )

    assert resp.status_code == 404


def test_a_junk_address_on_the_patch_is_refused(client, db):
    _, headers = _auth(client, db)
    created = _create_load(client, headers, email=None)

    resp = client.patch(
        f"/load/{_load_id(db, created)}/counterparty-email",
        json={"email": "ap acme@example.com"},
        headers=headers,
    )

    assert resp.status_code == 422


def test_the_patch_reports_a_copy_when_the_row_is_shared(client, db):
    """The client cannot infer it: under copy-on-write the load's counterparty id changes."""
    account_id, headers = _auth(client, db)
    created = _create_load(client, headers, email=None)
    load = loads.get_load(db, _load_id(db, created))
    other = identity.register_account(db, "other@example.com", "pw-123456")
    loads.create_load(db, other.id, counterparty_id=load.counterparty_id)
    db.flush()
    before = load.counterparty_id

    resp = client.patch(
        f"/load/{load.id}/counterparty-email",
        json={"email": "ap@acme.example"},
        headers=headers,
    )

    assert resp.json()["copied"] is True
    assert resp.json()["counterparty_id"] != str(before)


# --- D2, the five cases ---
def _accrued_claim(client, db, headers, email="ap@acme.example"):
    created = _create_load(client, headers, email=email)
    stop_id = created["stop_id"]
    client.post(f"/load/{stop_id}/arrive", headers=headers)
    return stop_id, m3.claim_for_stop(db, uuid.UUID(stop_id))


def test_case_1_no_linked_message_sends(client, db, monkeypatch):
    _, headers = _auth(client, db)
    stop_id, claim = _accrued_claim(client, db, headers)
    gateway = CountingGateway()
    monkeypatch.setattr(load_api, "_GATEWAY", gateway)

    resp = client.post(f"/load/{stop_id}/notice", headers=headers)

    assert resp.json()["delivery"] == "sent"
    assert gateway.sent == ["ap@acme.example"]


def test_case_2_a_delivered_notice_is_never_sent_again(client, db, monkeypatch):
    """The dispute anchor may not be re-anchored — and it WAS resent before this rule."""
    _, headers = _auth(client, db)
    stop_id, claim = _accrued_claim(client, db, headers)
    gateway = CountingGateway()
    monkeypatch.setattr(load_api, "_GATEWAY", gateway)
    client.post(f"/load/{stop_id}/notice", headers=headers)

    second = client.post(f"/load/{stop_id}/notice", headers=headers)

    assert len(gateway.sent) == 1
    assert second.json()["delivery"] == "sent"
    # and the evidence log carries exactly ONE notice_sent, not two
    timeline = client.get(f"/load/{stop_id}/evidence", headers=headers).json()["timeline"]
    assert [e["event"] for e in timeline].count("notice_sent") == 1


def test_case_3_a_retryable_failure_to_the_same_address_is_left_to_the_sweep(
    client, db, monkeypatch
):
    _, headers = _auth(client, db)
    stop_id, claim = _accrued_claim(client, db, headers)
    gateway = FailingGateway()
    monkeypatch.setattr(load_api, "_GATEWAY", gateway)
    client.post(f"/load/{stop_id}/notice", headers=headers)

    second = client.post(f"/load/{stop_id}/notice", headers=headers)

    assert len(gateway.sent) == 1
    assert second.json()["delivery"] == "retrying"
    assert len(notify.unsent_messages(db)) == 1


def test_case_4_a_permanent_failure_sends_fresh(client, db, monkeypatch):
    _, headers = _auth(client, db)
    stop_id, claim = _accrued_claim(client, db, headers)
    monkeypatch.setattr(load_api, "_GATEWAY", FailingGateway("SMTPAuthenticationError"))
    client.post(f"/load/{stop_id}/notice", headers=headers)
    failed_ref = claim.start_notice_message_ref
    good = CountingGateway()
    monkeypatch.setattr(load_api, "_GATEWAY", good)

    resp = client.post(f"/load/{stop_id}/notice", headers=headers)

    assert resp.json()["delivery"] == "sent"
    assert len(good.sent) == 1
    assert claim.start_notice_message_ref != failed_ref  # relinked
    # the failed row stays as history rather than being rewritten
    assert db.get(notify.OutboundMessage, failed_ref) is not None


def test_case_5_fixing_the_address_makes_a_refused_notice_sendable(client, db, monkeypatch):
    """The case this whole session exists for.

    A wrong address produces SMTPRecipientsRefused, which is PERMANENT and correctly never
    retried. Without an address-aware rule, correcting it would leave the notice unsendable
    for good.
    """
    _, headers = _auth(client, db)
    stop_id, claim = _accrued_claim(client, db, headers, email="wrong@acme.example")
    monkeypatch.setattr(load_api, "_GATEWAY", FailingGateway("SMTPRecipientsRefused"))
    client.post(f"/load/{stop_id}/notice", headers=headers)
    assert m3.notice_delivery(db, claim) == "failed"

    client.patch(
        f"/load/{loads.get_stop(db, uuid.UUID(stop_id)).load_id}/counterparty-email",
        json={"email": "right@acme.example"},
        headers=headers,
    )
    good = CountingGateway()
    monkeypatch.setattr(load_api, "_GATEWAY", good)
    resp = client.post(f"/load/{stop_id}/notice", headers=headers)

    assert resp.json()["delivery"] == "sent"
    assert good.sent == ["right@acme.example"]


def test_a_retryable_failure_to_a_STALE_address_sends_fresh(client, db, monkeypatch):
    """Retryable, but queued against an address the driver has since corrected.

    Leaving it to the sweep would re-present the OLD address forever.
    """
    _, headers = _auth(client, db)
    stop_id, claim = _accrued_claim(client, db, headers, email="wrong@acme.example")
    monkeypatch.setattr(load_api, "_GATEWAY", FailingGateway())
    client.post(f"/load/{stop_id}/notice", headers=headers)
    assert m3.notice_delivery(db, claim) == "retrying"

    client.patch(
        f"/load/{loads.get_stop(db, uuid.UUID(stop_id)).load_id}/counterparty-email",
        json={"email": "right@acme.example"},
        headers=headers,
    )
    good = CountingGateway()
    monkeypatch.setattr(load_api, "_GATEWAY", good)
    resp = client.post(f"/load/{stop_id}/notice", headers=headers)

    assert resp.json()["delivery"] == "sent"
    assert good.sent == ["right@acme.example"]


def test_a_no_email_claim_becomes_sendable_once_the_address_is_added(client, db, monkeypatch):
    _, headers = _auth(client, db)
    stop_id, claim = _accrued_claim(client, db, headers, email=None)
    gateway = CountingGateway()
    monkeypatch.setattr(load_api, "_GATEWAY", gateway)
    refused = client.post(f"/load/{stop_id}/notice", headers=headers)
    assert refused.json()["delivery"] == "no_email"
    assert gateway.sent == []

    client.patch(
        f"/load/{loads.get_stop(db, uuid.UUID(stop_id)).load_id}/counterparty-email",
        json={"email": "ap@acme.example"},
        headers=headers,
    )
    resp = client.post(f"/load/{stop_id}/notice", headers=headers)

    assert resp.json()["delivery"] == "sent"
    assert gateway.sent == ["ap@acme.example"]


# --- dunning inherits the fix with no code change ---
def test_a_claim_skipped_for_no_email_dunned_once_the_address_exists(client, db, monkeypatch):
    """No dunning code changes for this — it reads the address at send time, as it should."""
    account_id, headers = _auth(client, db)
    stop_id, claim = _accrued_claim(client, db, headers, email=None)
    from app.foundation.f07_ledger import public as ledger

    # filed through the service with an explicit `now`, because four hours of detention is
    # what makes a receivable exist at all (`amount_cents > 0`), and the route files at
    # wall-clock now
    m3.generate_pack(db, claim, now=datetime.now(UTC) + timedelta(hours=4))
    receivable = db.get(ledger.Receivable, claim.receivable_ref)
    receivable.created_at = datetime.now(UTC) - timedelta(days=3, hours=1)
    db.flush()
    gateway = CountingGateway()

    before = m3.run_dunning(db, gateway, now=datetime.now(UTC))
    assert before["skipped_no_email"] == 1
    assert gateway.sent == []

    client.patch(
        f"/load/{loads.get_stop(db, uuid.UUID(stop_id)).load_id}/counterparty-email",
        json={"email": "ap@acme.example"},
        headers=headers,
    )
    after = m3.run_dunning(db, gateway, now=datetime.now(UTC))

    assert after["nudged"] == 1
    assert gateway.sent == ["ap@acme.example"]
