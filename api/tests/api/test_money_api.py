"""AI-CONTEXT: HTTP API tests for M9 Driver Money & Tax Tools. TestClient with
get_db overridden to the transactional test session. Proves the settlement
auditor and the earnings/DDD dashboard over HTTP.
"""

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f07_ledger import public as ledger
from app.main import app


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
    return resp.json()["account_id"], {"Authorization": f"Bearer {resp.json()['token']}"}


def test_earnings_requires_auth(client):
    resp = client.get("/money/earnings")
    assert resp.status_code == 401


def test_settlement_audit_flags_missed_pay(client, db):
    account_id, headers = _auth(client)
    # the driver is owed detention $150 (GPS-backed receivable)
    ledger.create_receivable(db, uuid.UUID(account_id), ledger.ReceivableKind.detention, 15000)
    # AI-CONTEXT: the period has to COVER the receivable now (F-23). It used to be a
    # fixed fortnight three weeks before the receivable's own date, and the audit still
    # flagged it — because `owed` was every unsettled receivable ever while `paid` was
    # this one document. The two were never comparable and nothing said so.
    today = date.today()
    resp = client.post(
        "/money/settlements/audit",
        json={
            "carrier": "Acme",
            "period_start": (today - timedelta(days=7)).isoformat(),
            "period_end": today.isoformat(),
            "lines": [{"kind": "detention", "amount_cents": 5000}],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["total_missed_cents"] == 10000
    assert body["discrepancies"][0]["kind"] == "detention"


def test_earnings_ddd_over_http(client, db):
    account_id, headers = _auth(client)
    rec = ledger.create_receivable(db, uuid.UUID(account_id), ledger.ReceivableKind.tonu, 30000)
    ledger.transition_receivable(db, rec, ledger.ReceivableState.recovered)
    resp = client.get("/money/earnings", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["recovered_cents"] == 30000
    assert body["ddd_cents"] == 30000  # no fuel/flagged yet


def test_earnings_carries_what_the_empty_state_needs_to_say(client, db):
    """AI-CONTEXT: §23 entry 215 — the Money tab's empty sentence had one cause and
    there are four. The three facts that tell them apart ride on THIS payload rather
    than a third fetch, because the tab already declares two independent load-states for
    two fetches and a third would buy one sentence at the price of another failure mode
    on the screen that must not look broken while it is right.
    """
    _account_id, headers = _auth(client)

    body = client.get("/money/earnings", headers=headers).json()

    assert body["has_loads"] is False
    assert body["open_claims"] == 0
    assert body["accrued_unfiled_cents"] == 0
