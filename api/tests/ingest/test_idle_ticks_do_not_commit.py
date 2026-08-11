"""Finding F11 — a no-op tick used to commit an empty transaction.

`run_detention_clock` runs every 60 seconds and normally finds nothing due, so the worker
opened and committed roughly a thousand empty transactions a day. Harmless, and still
worth not doing: an empty commit is a write-ahead log entry, a replication event and a
line in every transaction-rate view, all of it reporting that something happened.

Cheaply observable, so it is pinned rather than only commented: the runners take
`commit`, and a counting stand-in for the session is enough to see whether they used it.
"""

from app.ingest import runners


class CountingSession:
    """Only what the runners touch on an idle tick: a commit counter."""

    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


def test_did_work_ignores_a_scan_that_decided_nothing():
    """`scanned` is not work — the whole point of the summary is that a scan is not an event."""
    assert runners._did_work({"scanned": 12, "started": 0, "warned": 0, "delivered": 0}) is False
    assert runners._did_work({"considered": 40, "delivered": 0}) is False
    assert runners._did_work({"scanned": 0}) is False


def test_did_work_sees_anything_that_actually_happened():
    assert runners._did_work({"scanned": 12, "started": 1, "warned": 0}) is True
    assert runners._did_work({"scanned": 99, "nudged": 0, "skipped_stale": 3}) is True


def test_an_idle_detention_clock_tick_does_not_commit(monkeypatch):
    session = CountingSession()
    monkeypatch.setattr(
        "app.modules.m03_detention.public.dispatch_clock_alerts",
        lambda db, gateway: {"scanned": 7, "started": 0, "warned": 0, "delivered": 0},
    )

    summary = runners.run_detention_clock(session, commit=True)

    assert summary["started"] == 0
    assert session.commits == 0


def test_a_tick_that_dispatched_something_does_commit(monkeypatch):
    session = CountingSession()
    monkeypatch.setattr(
        "app.modules.m03_detention.public.dispatch_clock_alerts",
        lambda db, gateway: {"scanned": 7, "started": 1, "warned": 0, "delivered": 1},
    )

    runners.run_detention_clock(session, commit=True)

    assert session.commits == 1


def test_an_idle_dunning_tick_does_not_commit(monkeypatch):
    session = CountingSession()
    monkeypatch.setattr(
        "app.modules.m03_detention.public.run_dunning",
        lambda db, gateway: {"scanned": 3, "nudged": 0, "firmed": 0, "offered": 0,
                             "skipped_no_email": 0, "skipped_stale": 0, "skipped_ungated": 0},
    )

    runners.run_dunning(session, commit=True)

    assert session.commits == 0


def test_a_dunning_tick_that_skipped_something_DOES_commit(monkeypatch):
    """A skip is a decision the summary reports; only a pure scan is nothing."""
    session = CountingSession()
    monkeypatch.setattr(
        "app.modules.m03_detention.public.run_dunning",
        lambda db, gateway: {"scanned": 3, "nudged": 0, "skipped_stale": 2},
    )

    runners.run_dunning(session, commit=True)

    assert session.commits == 1
