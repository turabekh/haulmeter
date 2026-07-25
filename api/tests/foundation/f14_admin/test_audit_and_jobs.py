"""AI-CONTEXT: F14 audit before/after + worker job telemetry (Admin Console 2.0).

The audit log existed already; what it could not answer was the question actually
asked after an incident. "Was the flag toggled?" was answerable. "What was it
toggled FROM, by whom, and what else did they touch that day?" was not. `before`,
`after`, `target_key` and the filters are what close that.

Job telemetry answers the operator's other morning question — "did the feeds run,
and is anything stuck?" — which previously required reading container logs.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f14_admin import public as admin

T0 = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)


def _actor(db, email="ops@example.com"):
    return identity.register_account(db, email, "pw-123456")


# --- audit: what changed, not merely that something changed ---
def test_an_entry_records_what_the_value_was_before(db):
    actor = _actor(db)
    entry = admin.record_action(
        db,
        "flag_disable",
        actor_account_id=actor.id,
        target_kind="flag",
        target_key="m13_vendor",
        before={"enabled": True},
        after={"enabled": False},
    )
    assert entry.before == {"enabled": True}
    assert entry.after == {"enabled": False}
    assert entry.target_key == "m13_vendor"


def test_the_log_filters_to_one_subject(db):
    # the point of target_key: "what happened to THIS flag" without reading everything
    actor = _actor(db)
    for key in ("m13_vendor", "m07_fuel", "m13_vendor"):
        admin.record_action(db, "flag_enable", actor_account_id=actor.id, target_key=key)

    assert len(admin.list_actions(db, target_key="m13_vendor")) == 2
    assert len(admin.list_actions(db, target_key="m07_fuel")) == 1


def test_the_log_filters_by_actor(db):
    # with more than one admin, "who did this" has to be answerable
    first, second = _actor(db, "a@x.com"), _actor(db, "b@x.com")
    admin.record_action(db, "config_set", actor_account_id=first.id, target_key="k1")
    admin.record_action(db, "config_set", actor_account_id=second.id, target_key="k2")

    mine = admin.list_actions(db, actor_account_id=first.id)
    assert [a.target_key for a in mine] == ["k1"]


def test_the_log_filters_by_kind_and_action(db):
    actor = _actor(db)
    admin.record_action(db, "flag_enable", actor_account_id=actor.id, target_kind="flag")
    admin.record_action(db, "vendor_verify", actor_account_id=actor.id, target_kind="vendor")

    assert len(admin.list_actions(db, target_kind="vendor")) == 1
    assert len(admin.list_actions(db, action="flag_enable")) == 1


def test_a_limited_read_returns_the_most_recent_first(db):
    # an operator opening the log wants what just happened
    actor = _actor(db)
    for i in range(5):
        admin.record_action(db, "config_set", actor_account_id=actor.id, target_key=f"k{i}")

    recent = admin.list_actions(db, limit=2)
    assert [a.target_key for a in recent] == ["k4", "k3"]


def test_an_unlimited_read_stays_a_chronology(db):
    # existing callers read the log oldest-first; that contract is preserved
    actor = _actor(db)
    for i in range(3):
        admin.record_action(db, "config_set", actor_account_id=actor.id, target_key=f"k{i}")
    assert [a.target_key for a in admin.list_actions(db)] == ["k0", "k1", "k2"]


def test_last_action_for_gives_config_its_provenance(db):
    # config provenance is built on the log rather than a column, so no table has to
    # carry an actor it does not otherwise need
    first, second = _actor(db, "old@x.com"), _actor(db, "new@x.com")
    admin.record_action(db, "config_set", actor_account_id=first.id, target_key="m13_inactive_days")
    admin.record_action(
        db, "config_set", actor_account_id=second.id, target_key="m13_inactive_days"
    )

    latest = admin.last_action_for(db, "config_set", "m13_inactive_days")
    assert latest.actor_account_id == second.id


def test_provenance_is_none_for_a_value_nobody_has_set(db):
    assert admin.last_action_for(db, "config_set", "never_touched") is None


# --- job telemetry ---
def test_a_successful_run_records_its_summary(db):
    run = admin.start_job_run(db, "tpims_dynamic", T0)
    admin.finish_job_run(
        db, run, T0 + timedelta(seconds=4), ok=True, summary={"applied": 17, "skipped": 3}
    )
    assert run.ok is True
    assert run.summary["applied"] == 17
    assert run.consecutive_failures == 0


def test_a_failed_run_records_the_error_and_the_streak(db):
    run = admin.start_job_run(db, "eia_regional", T0)
    admin.finish_job_run(
        db,
        run,
        T0 + timedelta(seconds=2),
        ok=False,
        error="ConnectTimeout()",
        consecutive_failures=3,
        next_run_at=T0 + timedelta(hours=1),
    )
    assert run.ok is False
    assert "ConnectTimeout" in run.error
    assert run.consecutive_failures == 3
    # the backoff is legible rather than mysterious
    assert run.next_run_at == T0 + timedelta(hours=1)


def test_an_unbounded_error_is_truncated_rather_than_stored_whole(db):
    # a telemetry row must not quietly become a log file
    run = admin.start_job_run(db, "tpims_static", T0)
    admin.finish_job_run(db, run, T0, ok=False, error="x" * 5000)
    assert len(run.error) == 500


def test_the_latest_run_is_the_latest_attempt_not_the_latest_success(db):
    # a job whose last attempt failed must not look healthy because an older
    # success is still on file
    ok_run = admin.start_job_run(db, "tpims_dynamic", T0)
    admin.finish_job_run(db, ok_run, T0, ok=True, summary={"applied": 5})
    bad_run = admin.start_job_run(db, "tpims_dynamic", T0 + timedelta(minutes=3))
    admin.finish_job_run(db, bad_run, T0 + timedelta(minutes=3), ok=False, error="boom")

    latest = admin.latest_job_runs(db)["tpims_dynamic"]
    assert latest.ok is False


def test_latest_runs_covers_every_job_independently(db):
    for name in ("tpims_dynamic", "tpims_static", "eia_regional"):
        run = admin.start_job_run(db, name, T0)
        admin.finish_job_run(db, run, T0, ok=True)

    latest = admin.latest_job_runs(db)
    assert set(latest) == {"tpims_dynamic", "tpims_static", "eia_regional"}


def test_history_reads_newest_first_and_is_bounded(db):
    for i in range(5):
        run = admin.start_job_run(db, "tpims_dynamic", T0 + timedelta(minutes=i))
        admin.finish_job_run(db, run, T0 + timedelta(minutes=i), ok=True, summary={"n": i})

    history = admin.job_history(db, "tpims_dynamic", limit=3)
    assert [h.summary["n"] for h in history] == [4, 3, 2]


def test_a_job_that_never_ran_is_simply_absent(db):
    # absence is the honest signal for "never ran"; a fabricated zero row would read
    # as "ran and did nothing"
    assert "never_scheduled" not in admin.latest_job_runs(db)
