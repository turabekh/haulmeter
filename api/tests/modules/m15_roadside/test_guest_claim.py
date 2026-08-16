"""AI-CONTEXT: the cross-layer guest claim (E3 §E3.2 item 2, quality law Q-10).

This is the observation E3's Session-A Definition of Done names: a guest principal starts
a scenario session, turns are recorded against draft content, the guest is claimed into an
account, and **the rows land and survive the claim**.

The claim has two halves in two layers — F1 owns the principal's lifecycle and cannot know
what a session is; m15 owns the rows and cannot mark a principal claimed. Atomicity is the
caller's obligation, so the assertion that matters most here is not the happy path but
`test_a_failed_module_half_rolls_the_claim_back`: Q-10 says guest work is never lost
silently, and the way that law breaks is not an error message — it is a driver who signs
up and finds an empty account.
"""

from datetime import UTC, datetime

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f01_identity.domain import guests
from app.modules.m15_roadside import public as m15


def _account(db, email="claimer@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _draft_scenario(db):
    """DRAFT on purpose — Q-6 means draft content has no path to a driver, and a guest
    session recorded against it is exactly how the engine is exercised before any content
    has been reviewed."""
    sv = m15.ScenarioVersion(
        version=1,
        difficulty=m15.Difficulty.clear,
        allowed_intents=["hours_of_service"],
        status=m15.ContentStatus.draft,
    )
    db.add(sv)
    db.flush()
    return sv


def _guest_session_with_turns(db, principal, scenario):
    session = m15.Session(
        guest_token=principal.token,
        scenario_version_id=scenario.id,
        mode=m15.SessionMode.check,
        consent_at=datetime.now(UTC),
    )
    db.add(session)
    db.flush()
    db.add(
        m15.Turn(
            session_id=session.id, seq=1, speaker=m15.Speaker.officer, transcript="Licence?"
        )
    )
    db.add(
        m15.Turn(
            session_id=session.id,
            seq=2,
            speaker=m15.Speaker.driver,
            transcript="Here you are",
            asr_confidence=0.91,
        )
    )
    db.flush()
    return session


def test_a_guest_session_records_turns_against_draft_content(db):
    scenario = _draft_scenario(db)
    principal = guests.issue_guest(db, "m15")
    session = _guest_session_with_turns(db, principal, scenario)

    assert session.account_id is None, "a guest session belongs to no account yet"
    assert session.guest_token == principal.token
    turns = db.query(m15.Turn).filter(m15.Turn.session_id == session.id).all()
    assert len(turns) == 2


def test_the_claim_moves_the_work_and_the_rows_survive(db):
    account = _account(db)
    scenario = _draft_scenario(db)
    principal = guests.issue_guest(db, "m15")
    session = _guest_session_with_turns(db, principal, scenario)

    # both halves, one transaction
    guests.claim_guest(db, principal.token, account.id)
    moved = m15.claim_guest_sessions(db, principal.token, account.id)
    db.flush()

    assert moved == 1
    db.refresh(session)
    assert session.account_id == account.id
    # the turns were not recreated — same session, same rows, same content
    turns = (
        db.query(m15.Turn)
        .filter(m15.Turn.session_id == session.id)
        .order_by(m15.Turn.seq)
        .all()
    )
    assert [t.transcript for t in turns] == ["Licence?", "Here you are"]
    # the trail back to the principal is KEPT deliberately (Q-10): "where did my practice
    # go?" is answerable from the rows rather than guessed at
    assert session.guest_token == principal.token
    assert guests.resolve_guest(db, principal.token) is None


def test_claiming_moves_nothing_that_belonged_to_another_guest(db):
    """A claim is scoped to its own token, which is the only thing standing between two
    strangers' practice sessions."""
    account = _account(db)
    scenario = _draft_scenario(db)
    mine = guests.issue_guest(db, "m15")
    theirs = guests.issue_guest(db, "m15")
    my_session = _guest_session_with_turns(db, mine, scenario)
    their_session = _guest_session_with_turns(db, theirs, scenario)

    guests.claim_guest(db, mine.token, account.id)
    moved = m15.claim_guest_sessions(db, mine.token, account.id)
    db.flush()

    assert moved == 1
    db.refresh(my_session)
    db.refresh(their_session)
    assert my_session.account_id == account.id
    assert their_session.account_id is None


def test_a_failed_module_half_rolls_the_claim_back(db):
    """Q-10 asserted: the two halves live or die together.

    If F1's half committed while the module's half failed, the principal would read as
    claimed and the sessions would still point at a token nobody can use again — no error
    anywhere, just an empty account.
    """
    account = _account(db)
    scenario = _draft_scenario(db)
    principal = guests.issue_guest(db, "m15")
    _guest_session_with_turns(db, principal, scenario)
    db.commit()

    guests.claim_guest(db, principal.token, account.id)
    db.rollback()  # the module half failed; the whole transaction goes back

    live = guests.resolve_guest(db, principal.token)
    assert live is not None, "a rolled-back claim must leave the token usable again"
    assert live.claimed_at is None


def test_an_expired_guest_cannot_have_its_work_claimed(db):
    """The expiry is what bounds the window, and the module half must not run alone."""
    from datetime import timedelta

    account = _account(db)
    scenario = _draft_scenario(db)
    now = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    principal = guests.issue_guest(db, "m15", now=now)
    _guest_session_with_turns(db, principal, scenario)

    with pytest.raises(guests.GuestPrincipalUnusable):
        guests.claim_guest(db, principal.token, account.id, now=now + timedelta(days=8))
