"""AI-CONTEXT: the three constraints E3 calls out, exercised rather than declared.

TRAPS §1.3 is the reason this file exists. The test database is built by
`Base.metadata.create_all`, so a constraint that lives only in the migration is never
touched by a single test — it would hold in production and be invisible to the entire
suite. These tests pass ONLY if the constraints are on the models, which is what makes
them a check on the habit and not just on the schema.

Each one is written as the mistake it prevents, because "unique on (a, b)" says nothing
about why: a second live session for one guest, a second history for one item, a second
grant for one window.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.foundation.f01_identity import public as identity
from app.modules.m15_roadside.domain import models as m


def _scenario(db):
    sv = m.ScenarioVersion(
        version=1,
        difficulty=m.Difficulty.clear,
        allowed_intents=["hours_of_service"],
    )
    db.add(sv)
    db.flush()
    return sv


def _account(db, email):
    return identity.register_account(db, email, "pw-123456")


def test_one_live_session_per_guest_principal(db):
    """A guest cannot have two unfinished sessions.

    Two live sessions for one guest means two sets of turns racing to be the record of one
    sitting, and whichever finished last would silently become the driver's result.
    """
    sv = _scenario(db)
    token = uuid.uuid4()
    db.add(m.Session(guest_token=token, scenario_version_id=sv.id, mode=m.SessionMode.check))
    db.flush()

    db.add(m.Session(guest_token=token, scenario_version_id=sv.id, mode=m.SessionMode.check))
    with pytest.raises(IntegrityError):
        db.flush()


def test_a_finished_session_frees_the_guest_to_start_another(db):
    """The constraint is on the LIVE one — the partial predicate is the point.

    Without `WHERE completed_at IS NULL` this would be a bug that only appears for the
    driver who takes a second check, which is precisely the driver we most want back.
    """
    sv = _scenario(db)
    token = uuid.uuid4()
    first = m.Session(
        guest_token=token,
        scenario_version_id=sv.id,
        mode=m.SessionMode.check,
        completed_at=datetime.now(UTC),
    )
    db.add(first)
    db.flush()

    db.add(m.Session(guest_token=token, scenario_version_id=sv.id, mode=m.SessionMode.check))
    db.flush()  # must not raise


def test_authenticated_sessions_do_not_collide_on_a_null_guest_token(db):
    """Every authed session has guest_token NULL, so the predicate must exclude NULLs.

    Postgres treats NULLs as distinct in a unique index, but the predicate is what keeps
    the index small and the intent legible — and this asserts the behaviour either way,
    because a future edit to that predicate would otherwise break every authed session at
    once.
    """
    sv = _scenario(db)
    a1 = _account(db, "m15-one@example.com")
    a2 = _account(db, "m15-two@example.com")
    db.add(m.Session(account_id=a1.id, scenario_version_id=sv.id, mode=m.SessionMode.practice))
    db.add(m.Session(account_id=a2.id, scenario_version_id=sv.id, mode=m.SessionMode.practice))
    db.flush()  # must not raise


def test_one_skill_state_per_account_and_variant(db):
    """A second row is a second history, and spaced repetition would schedule the item twice."""
    sv = _scenario(db)
    intent = m.Intent(key="hours_of_service", domain="paperwork", canonical_meaning="HOS")
    db.add(intent)
    db.flush()
    variant = m.PhraseVariant(
        intent_id=intent.id, text="How many hours?", difficulty=m.Difficulty.clear
    )
    db.add(variant)
    account = _account(db, "m15-skill@example.com")
    db.flush()

    db.add(m.SkillState(account_id=account.id, variant_id=variant.id))
    db.flush()
    db.add(m.SkillState(account_id=account.id, variant_id=variant.id))
    with pytest.raises(IntegrityError):
        db.flush()
    assert sv is not None


def test_one_entitlement_per_subject_kind_and_window(db):
    """A duplicate grant is what silently extends access nobody granted.

    This test failed the first time it ran, and the schema was what was wrong. A single
    UNIQUE over both subject columns does not fire when one of them is NULL — which it
    always is, because a subject is an account OR an org. Two partial indexes, split by
    subject, are what actually enforce it.
    """
    account = _account(db, "m15-ent@example.com")
    db.flush()
    starts = datetime.now(UTC)
    ends = starts + timedelta(days=30)

    db.add(
        m.Entitlement(
            subject_account_id=account.id,
            kind=m.EntitlementKind.program,
            starts_at=starts,
            ends_at=ends,
        )
    )
    db.flush()
    db.add(
        m.Entitlement(
            subject_account_id=account.id,
            kind=m.EntitlementKind.program,
            starts_at=starts,
            ends_at=ends,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()


def test_no_column_anywhere_in_m15_holds_a_voiceprint(db):
    """E3 §E3.1.4: no voiceprints, no biometric matching, ever — asserted, not assumed.

    `phrase_variant.voice` is the exception that proves the rule and is why this test
    names columns rather than grepping for a substring: it records which of the two
    officer voices synthesized OUR line. Nothing here is derived from a driver.
    """
    suspicious = []
    for table in m.Base.metadata.tables.values():
        if table.schema != m.SCHEMA:
            continue
        for column in table.columns:
            name = column.name.lower()
            if "biometric" in name or "voiceprint" in name or "speaker_id" in name:
                suspicious.append(f"{table.name}.{column.name}")

    assert suspicious == [], f"m15 must never carry a biometric column; found {suspicious}"
    # and the table holding raw driver audio carries no voice-identity column at all
    turn_columns = {c.name for c in m.Turn.__table__.columns}
    assert "voice" not in turn_columns


def test_an_entitlement_has_exactly_one_subject(db):
    """`subject: account_id | org_id` is an exclusive or, and the schema says so.

    A row with neither is an entitlement granted to nobody; a row with both is one that
    two different queries would each claim as theirs.
    """
    starts = datetime.now(UTC)

    db.add(m.Entitlement(kind=m.EntitlementKind.seat, starts_at=starts))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    account = _account(db, "m15-both@example.com")
    org_id = db.execute(
        text("insert into f01.organization (id, name, org_type) "
             "values (gen_random_uuid(), 'Both Co', 'fleet') returning id")
    ).scalar()
    db.flush()
    db.add(
        m.Entitlement(
            subject_account_id=account.id,
            subject_org_id=org_id,
            kind=m.EntitlementKind.seat,
            starts_at=starts,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()


def test_an_open_ended_grant_is_still_unique(db):
    """The regression the first fix missed, found by probing the box rather than the suite.

    An entitlement with no `ends_at` is an ordinary open-ended grant. The first fix split
    the index by subject, which cured the NULL `subject_org_id` — and left `ends_at` NULL
    doing exactly the same thing one column over. Two identical open-ended grants both
    inserted on a live database while this file was green, because the case above happens
    to set an end date.

    That is the whole lesson of the constraint: a unique index over any nullable column is
    not unique for the rows where that column is null, and those rows are usually the
    ordinary ones.
    """
    account = _account(db, "m15-openended@example.com")
    db.flush()
    starts = datetime.now(UTC)

    db.add(
        m.Entitlement(
            subject_account_id=account.id, kind=m.EntitlementKind.seat, starts_at=starts
        )
    )
    db.flush()
    db.add(
        m.Entitlement(
            subject_account_id=account.id, kind=m.EntitlementKind.seat, starts_at=starts
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
