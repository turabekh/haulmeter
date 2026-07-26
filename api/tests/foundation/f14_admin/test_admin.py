import uuid
from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f14_admin import public as admin

T0 = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def test_emit_and_count_events(db):
    account = _account(db)
    admin.emit(db, "map_open", "m01", T0, account_id=account.id)
    admin.emit(db, "map_open", "m01", T0 + timedelta(hours=1), account_id=account.id)
    admin.emit(db, "claim_sent", "m03", T0, account_id=account.id)
    assert admin.count_events(db, "map_open") == 2
    assert admin.count_events(db, "map_open", module="m01") == 2
    assert admin.count_events(db, "map_open", since=T0 + timedelta(minutes=30)) == 1


def test_funnel_counts_accounts_progressing(db):
    a = _account(db, "a@example.com")
    b = _account(db, "b@example.com")
    steps = ["load_added", "stop_armed", "claim_sent"]
    # a completes all three in order
    admin.emit(db, "load_added", "m03", T0, account_id=a.id)
    admin.emit(db, "stop_armed", "m03", T0 + timedelta(hours=1), account_id=a.id)
    admin.emit(db, "claim_sent", "m03", T0 + timedelta(hours=2), account_id=a.id)
    # b stops after step two
    admin.emit(db, "load_added", "m03", T0, account_id=b.id)
    admin.emit(db, "stop_armed", "m03", T0 + timedelta(hours=1), account_id=b.id)
    assert admin.funnel(db, steps) == [2, 2, 1]


def test_admin_audit_log(db):
    admin_user = _account(db, "admin@example.com")
    admin.record_action(
        db,
        "facility_merge",
        actor_account_id=admin_user.id,
        target_kind="facility",
        target_ref=uuid.uuid4(),
        detail={"merged": 2},
    )
    admin.record_action(db, "refund", actor_account_id=admin_user.id)
    assert len(admin.list_actions(db)) == 2
    assert len(admin.list_actions(db, action="facility_merge")) == 1


def test_moderation_queue_flow(db):
    author = _account(db, "author@example.com")
    moderator = _account(db, "mod@example.com")
    review_ref = uuid.uuid4()
    item = admin.enqueue_moderation(db, "review", review_ref, submitted_by=author.id)
    assert item.status == admin.ModerationStatus.pending
    assert len(admin.list_pending_moderation(db)) == 1

    admin.decide_moderation(
        db, item, admin.ModerationStatus.approved, moderator_account_id=moderator.id
    )
    assert item.status == admin.ModerationStatus.approved
    assert item.decided_at is not None
    assert admin.list_pending_moderation(db) == []


def test_admin_view_registry(db):
    admin.register_admin_view(
        db, "m02.scorecard", "m02", "Facility Scorecard", "/admin/m02/scorecard"
    )
    admin.register_admin_view(db, "m03.claims", "m03", "Claims Pipeline", "/admin/m03/claims")
    # idempotent upsert by key
    admin.register_admin_view(db, "m03.claims", "m03", "Claims Desk", "/admin/m03/claims")
    views = admin.list_admin_views(db)
    assert len(views) == 2
    m03 = admin.list_admin_views(db, module="m03")
    assert m03[0].title == "Claims Desk"


def test_the_injected_clock_reaches_the_row_it_dates(db):
    """The 72h moderation SLA is measured from this row's `created_at`. Without the
    clock reaching it, the item took the database time while its caller passed an
    injected `now` — so the SLA was computed between two clocks, and the queue test
    went red on its own hours later with no code change. An injected clock that does
    not reach the record it is meant to date is not an injected clock."""
    from datetime import UTC, datetime

    when = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)

    item = admin.enqueue_moderation(db, "review", uuid.uuid4(), now=when)

    assert item.created_at == when
