"""AI-CONTEXT: Q-6's operator surface (E3 §E3.1.5), and the refusals it must inherit.

`mark_reviewed` and `release` had no caller anywhere in the product. Nothing could reach
`released`, so every M15 driver surface would have rendered its empty state forever — on
production and on the owner's own machine. These routes are how a named human reaches the
transitions.

WHAT THESE TESTS ARE ACTUALLY FOR: an operator surface over a guarded transition is the
classic place a guard gets re-decided. The endpoint could accept a `reviewer` string, or a
`previous_version`, and either would hand the caller the thing the law exists to withhold
— the same shape as the client-set `allow_draft` (entry 180). So the assertions below are
mostly about what the route DOES NOT let anyone do.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.main import app
from app.modules.m15_roadside.domain import models as m


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _register(client, email):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    assert resp.status_code == 201
    return resp.json()["account_id"], {"Authorization": f"Bearer {resp.json()['token']}"}


def _auth(db, client, *, admin=True):
    from app.foundation.f01_identity.domain.models import Account

    email = f"m15-admin-{uuid.uuid4().hex[:8]}@example.com"
    account_id, headers = _register(client, email)
    if admin:
        account = db.get(Account, uuid.UUID(account_id))
        identity.attach_role(db, account, identity.Role.platform_admin)
    client.headers.update(headers)
    return email


def _intent(db, key="hos_hours_driven"):
    intent = m.Intent(key=key, domain="paperwork", canonical_meaning="hours driven")
    db.add(intent)
    db.flush()
    return intent


def _variant(db, intent, text="How many hours have you driven?", *, version=1, holdout=False):
    variant = m.PhraseVariant(
        intent_id=intent.id,
        text=text,
        difficulty=m.Difficulty.clear,
        status=m.ContentStatus.draft,
        version=version,
        holdout=holdout,
    )
    db.add(variant)
    db.flush()
    return variant


def test_the_queue_shows_what_is_waiting_and_what_is_a_holdout(client, db):
    """A reviewer releasing blind is how Q-5's holdout integrity gets broken by someone
    acting in good faith, so the flag is on the row."""
    _auth(db, client)
    intent = _intent(db)
    _variant(db, intent, "ordinary line")
    _variant(db, intent, "held-out line", version=2, holdout=True)

    body = client.get("/admin/roadside/content").json()

    rows = [i for i in body["intents"] if i["key"] == "hos_hours_driven"][0]["variants"]
    assert [v["status"] for v in rows] == ["draft", "draft"]
    assert [v["holdout"] for v in rows] == [False, True]


def test_release_straight_from_draft_is_refused(client, db):
    """The transition rule, reached through HTTP. F9 drafts this text — a route that let
    draft jump to released would put unreviewed machine output in front of a driver."""
    _auth(db, client)
    variant = _variant(db, _intent(db))

    resp = client.post(f"/admin/roadside/content/variant/{variant.id}/release")

    assert resp.status_code == 422
    assert variant.status is m.ContentStatus.draft


def test_the_reviewer_is_the_signed_in_admin_not_a_field(client, db):
    """`mark_reviewed` demands a named human. The name is the account that clicked —
    a free-text field would let 'reviewed' mean whatever the operator typed."""
    email = _auth(db, client)
    variant = _variant(db, _intent(db))

    body = client.post(f"/admin/roadside/content/variant/{variant.id}/review").json()

    assert body["reviewer"] == email
    assert variant.status is m.ContentStatus.reviewed


def test_the_full_path_makes_content_reachable(client, db):
    """The point of the whole surface: after this, a driver could actually be served it."""
    _auth(db, client)
    intent = _intent(db)
    variant = _variant(db, intent)

    client.post(f"/admin/roadside/content/variant/{variant.id}/review")
    resp = client.post(f"/admin/roadside/content/variant/{variant.id}/release")

    assert resp.status_code == 200
    assert variant.status is m.ContentStatus.released

    from app.modules.m15_roadside.domain import content

    assert content.teachable_variants(db, intent.id) == [variant]


def test_two_phrasings_of_one_question_can_both_be_released(client, db):
    """THE POOL, and the reason this endpoint does not compute a bump from siblings.

    An intent is meant to hold several released variants at once — `teachable_variants`
    returns a pool and Q-5 needs holdouts beside taught lines. The first version of this
    endpoint took `previous_version` to be the highest released version among siblings,
    which made two alternative phrasings mutually exclusive at version 1 and would have
    left every intent with exactly one line. Found by trying to release the seeded
    scenario, not by reading the code.
    """
    _auth(db, client)
    intent = _intent(db)
    first = _variant(db, intent, "How many hours have you driven?")
    second = _variant(db, intent, "How long have you been driving today?")

    for variant in (first, second):
        client.post(f"/admin/roadside/content/variant/{variant.id}/review")
        resp = client.post(f"/admin/roadside/content/variant/{variant.id}/release")
        assert resp.status_code == 200

    from app.modules.m15_roadside.domain import content

    assert set(content.teachable_variants(db, intent.id)) == {first, second}


def test_a_scenario_moves_through_the_same_pipeline(client, db):
    """Scenario versions carry `status` and `version` and were never able to move,
    because nothing exposed the transitions. They obey the same two refusals."""
    _auth(db, client)
    scenario = m.ScenarioVersion(
        version=1,
        difficulty=m.Difficulty.clear,
        allowed_intents=["hos_hours_driven"],
        status=m.ContentStatus.draft,
    )
    db.add(scenario)
    db.flush()

    assert client.post(f"/admin/roadside/content/scenario/{scenario.id}/release").status_code == 422
    client.post(f"/admin/roadside/content/scenario/{scenario.id}/review")
    assert client.post(f"/admin/roadside/content/scenario/{scenario.id}/release").status_code == 200
    assert scenario.status is m.ContentStatus.released


def test_the_pipeline_is_platform_admin_only(client, db):
    """It publishes what drivers are scored against; a driver session must not reach it."""
    _auth(db, client, admin=False)

    assert client.get("/admin/roadside/content").status_code == 403


def test_the_review_is_recorded_against_a_name(client, db):
    """AI-CONTEXT: the audit entry IS the review record, and this asserts it BEHAVIOURALLY.

    `test_every_mutating_admin_endpoint_writes_an_audit_entry` proves the route is mapped
    to an action and that the action name appears in the source — which a misspelled
    `record_action` call in a branch that never runs would also satisfy. Q-6 wants "a named
    human said this was fit for a driver" to stay answerable after the fact, and that is a
    row, not a string in a file.
    """
    from app.foundation.f14_admin import public as admin

    email = _auth(db, client)
    variant = _variant(db, _intent(db))

    client.post(f"/admin/roadside/content/variant/{variant.id}/review")

    entry = admin.last_action_for(db, "roadside_content_review", str(variant.id))
    assert entry is not None, "the reviewer's name survives only if the action was recorded"
    assert entry.detail["reviewer"] == email
    assert entry.before["status"] == "draft"
    assert entry.after["status"] == "reviewed"
