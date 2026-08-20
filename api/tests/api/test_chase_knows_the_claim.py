"""AI-CONTEXT: the chase draft is TOLD the claim it is about (§23 entry 235).

The owner's question: "since we know which load we are talking about, why do we have to
ask filling brackets from a user?"

They were right, and the cause was two lines apart. The v1 prompt was
`"Write a {tone} {kind} to the counterparty in ENGLISH. Facts: {facts}"` — the model got
four words and whatever the driver typed, with no counterparty, dock, hours, rate or
money. Every draft came back studded with `[Counterparty Company Name]`, `[RC #_____]`
and `[$XX.00]`, which were the only honest output available to something that had been
told nothing. Meanwhile `onSheetChase` opened the sheet FROM the claim and dropped it:
`<GhostwriterSheet />`, no props.

These hold the two properties that make the fix trustworthy rather than merely richer:
the facts come from OUR records and not from the request body, and a stop that is not
the caller's contributes nothing.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f09_ai_gateway import public as ai
from app.main import app
from app.modules.m11_voice import public as m11
from app.modules.m11_voice.domain import service as m11_service


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_shipped_prompt_has_a_slot_for_what_we_know(db):
    m11.register_module(db)
    prompt = ai.get_active_prompt(db, m11_service.GHOSTWRITER_PROMPT)

    assert prompt.version == m11_service.GHOSTWRITER_PROMPT_VERSION
    assert "{claim_facts}" in prompt.template
    assert "{facts}" in prompt.template, "the driver's own words still travel"
    assert "ENGLISH" in prompt.template, "F15: outbound is English whatever they speak"


def test_a_box_already_holding_v1_is_upgraded(db):
    """THE TRAP THIS AVOIDS. `register_module` used to register the prompt only when
    `get_active_prompt` returned None, so editing the template in code changed nothing on
    a box that already had one — and production has carried v1 since M11 shipped. The
    version is what makes the new template win."""
    ai.register_prompt(
        db,
        m11_service.GHOSTWRITER_PROMPT,
        ai.AiTask.drafting,
        "Write a {tone} {kind} to the counterparty in ENGLISH. Facts: {facts}",
        version=1,
    )

    m11.register_module(db)

    active = ai.get_active_prompt(db, m11_service.GHOSTWRITER_PROMPT)
    assert active.version == 2
    assert "{claim_facts}" in active.template


def test_the_prompt_forbids_inventing_what_it_was_not_told(db):
    m11.register_module(db)
    template = ai.get_active_prompt(db, m11_service.GHOSTWRITER_PROMPT).template

    assert "NEVER replace one with a placeholder" in template
    assert "LEAVE IT OUT" in template


def _stop_with_claim(db, account, *, rate_cents=7500, hours=3):
    from app.foundation.f02_facility import public as facility
    from app.foundation.f05_load import public as loads
    from app.modules.m03_detention import public as m3

    fac = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Midwest Distribution Center", 32.77, -96.79
    )
    cp = loads.create_counterparty(db, "Bolt Logistics LLC", loads.CounterpartyKind.broker)
    load = loads.create_load(
        db, account.id, counterparty_id=cp.id, reference_number="4471",
        detention_rate_cents_per_hour=rate_cents, free_time_minutes=120,
    )
    started = datetime.now(UTC) - timedelta(hours=hours + 2)
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery, appointment_start=started)
    claim = m3.start_claim(db, stop, started_at=started)
    claim.detention_seconds = hours * 3600
    claim.amount_cents = int(rate_cents * hours)
    claim.detention_rate_cents_per_hour = rate_cents
    claim.free_time_minutes = 120
    db.flush()
    return stop


def test_the_facts_reach_the_model_without_the_driver_typing_them(client, db, monkeypatch):
    seen = {}

    def fake_complete(_db, _provider, _module, _key, values, account_id=None):
        seen.update(values)
        return "drafted"

    monkeypatch.setattr(m11_service.ai, "complete", fake_complete)
    reg = client.post(
        "/auth/register", json={"email": "chase@example.com", "password": "pw-123456"}
    )
    token = reg.json()["token"]
    account = db.get(identity.Account, uuid.UUID(reg.json()["account_id"]))
    stop = _stop_with_claim(db, account)

    r = client.post(
        "/voice/draft",
        json={"kind": "detention notice", "facts": "", "tone": "firm", "stop_id": str(stop.id)},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 200, r.text
    facts = seen["claim_facts"]
    assert "Bolt Logistics LLC" in facts
    assert "Midwest Distribution Center" in facts
    assert "$75.00 per hour" in facts
    assert "$225.00" in facts
    assert "3h 00m" in facts
    assert "4471" in facts
    # and the driver typed NOTHING — which is the owner's whole point
    assert seen["facts"] == m11_service.NO_DRIVER_FACTS


def test_someone_elses_claim_contributes_nothing(client, db, monkeypatch):
    """Ownership, checked before the record is read. A stop that is not the caller's
    yields no facts and no error — the draft is still written from what they typed, and
    nothing about another driver's claim leaks into it."""
    seen = {}
    monkeypatch.setattr(
        m11_service.ai, "complete",
        lambda _d, _p, _m, _k, values, account_id=None: (seen.update(values), "drafted")[1],
    )
    owner = identity.register_account(db, "owner@example.com", "pw-123456")
    stop = _stop_with_claim(db, owner)
    reg = client.post(
        "/auth/register", json={"email": "stranger@example.com", "password": "pw-123456"}
    )

    r = client.post(
        "/voice/draft",
        json={"kind": "detention notice", "facts": "held all day", "stop_id": str(stop.id)},
        headers={"Authorization": f"Bearer {reg.json()['token']}"},
    )

    assert r.status_code == 200
    assert seen["claim_facts"] == m11_service.NO_CLAIM_FACTS
    assert "Bolt Logistics" not in seen["claim_facts"]


def test_no_stop_still_drafts_from_what_the_driver_said(client, db, monkeypatch):
    # a lumper receivable has no stop_id at all — the sheet must still work
    seen = {}
    monkeypatch.setattr(
        m11_service.ai, "complete",
        lambda _d, _p, _m, _k, values, account_id=None: (seen.update(values), "drafted")[1],
    )
    reg = client.post(
        "/auth/register", json={"email": "nostop@example.com", "password": "pw-123456"}
    )

    r = client.post(
        "/voice/draft",
        json={"kind": "lumper reimbursement", "facts": "paid $150 at the dock"},
        headers={"Authorization": f"Bearer {reg.json()['token']}"},
    )

    assert r.status_code == 200
    assert seen["claim_facts"] == m11_service.NO_CLAIM_FACTS
    assert seen["facts"] == "paid $150 at the dock"
