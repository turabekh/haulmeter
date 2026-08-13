"""AI-CONTEXT: one email per purpose, and the constraint is what makes it true.

Duplicate suppression was five ad-hoc guards across four modules — a claim column, a
`pre_notice_sent_at` beside it, a packet state, per-action dunning columns, and on two
paths nothing at all. Each was written for its own case, which is how the same defect kept
returning: §23 entry 136 found `onSendNotice` "genuinely sent a broker two emails on a
double tap", and moving sends off the request thread re-opened it in
`_existing_start_notice`, where a never-attempted row did not look like an existing notice.

THE APPLICATION CHECK IS NOT THE GUARANTEE. §23 closed the four money races on exactly
this reasoning: an application check reads rows a concurrent transaction has not committed
yet. `test_two_concurrent_sends` is the one that matters — it uses two real sessions on
two real connections, so the `SELECT` in each genuinely cannot see the other's uncommitted
row, which is the only arrangement in which the defect exists.

AND A RE-SEND IS NOT A DUPLICATE. A notice that failed permanently, or one addressed to an
email the driver has since corrected, never reached the broker; replacing it is the FIRST
delivery. The purpose is handed over rather than the key being weakened, so the guarantee
stays absolute and the exception stays explicit.
"""

import pytest
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session as _Session

from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify


@pytest.fixture
def account(db):
    return identity.register_account(db, "dedupe@example.com", "pw-123456")


def _thread(db, account, subject="Detention now accruing"):
    return notify.create_thread(db, account.id, subject=subject)


def _wait_until_blocked(engine, timeout: float = 10.0) -> None:
    """Block until some backend on this database is waiting on a lock.

    AI-CONTEXT: the only way to know the loser has REACHED its INSERT and been refused
    entry by the unique index, rather than being about to run a SELECT that would find a
    committed row. Without this the race is decided by thread scheduling and the test
    passes whether or not the constraint exists.
    """
    import time

    deadline = time.monotonic() + timeout
    watcher = _Session(bind=engine)
    try:
        while time.monotonic() < deadline:
            blocked = watcher.execute(
                sa_text(
                    "select count(*) from pg_stat_activity "
                    "where datname = current_database() and wait_event_type = 'Lock'"
                )
            ).scalar()
            watcher.rollback()  # end the snapshot so the next poll sees fresh state
            if blocked:
                return
            time.sleep(0.05)
        raise AssertionError(
            "the loser never blocked on the index — the race was not exercised"
        )
    finally:
        watcher.close()


class TestOnePurposeOneMessage:
    def test_a_second_send_for_the_same_purpose_returns_the_first(self, db, account):
        thread = _thread(db, account)

        first = notify.send_counterparty_message(
            db, thread, "body", None, "ap@acme.example", dedupe_key="detention_start:c-1"
        )
        second = notify.send_counterparty_message(
            db, thread, "body", None, "ap@acme.example", dedupe_key="detention_start:c-1"
        )

        assert second.id == first.id
        assert len(notify.unsent_messages(db)) == 1, "one purpose, one email"

    def test_a_different_purpose_for_the_same_subject_still_sends(self, db, account):
        # "free time is about to run out" and "it has run out" are two different things to
        # tell a broker, and one claim legitimately produces both
        thread = _thread(db, account)

        warning = notify.send_counterparty_message(
            db, thread, "b", None, "ap@acme.example", dedupe_key="detention_warning:c-1"
        )
        start = notify.send_counterparty_message(
            db, thread, "b", None, "ap@acme.example", dedupe_key="detention_start:c-1"
        )

        assert warning.id != start.id
        assert len(notify.unsent_messages(db)) == 2

    def test_the_same_purpose_for_a_different_claim_still_sends(self, db, account):
        thread = _thread(db, account)

        a = notify.send_counterparty_message(
            db, thread, "b", None, "ap@acme.example", dedupe_key="detention_start:c-1"
        )
        b = notify.send_counterparty_message(
            db, thread, "b", None, "ap@acme.example", dedupe_key="detention_start:c-2"
        )

        assert a.id != b.id

    def test_an_unkeyed_message_is_never_deduplicated(self, db, account):
        # a driver's own approved free text has no natural identity; forcing it into a key
        # would collide on its second legitimate use
        thread = _thread(db, account)

        a = notify.send_counterparty_message(db, thread, "one", None, "ap@acme.example")
        b = notify.send_counterparty_message(db, thread, "two", None, "ap@acme.example")

        assert a.id != b.id
        assert len(notify.unsent_messages(db)) == 2

    def test_a_deduplicated_send_does_not_disturb_the_first(self, db, account):
        thread = _thread(db, account)
        first = notify.send_counterparty_message(
            db, thread, "the real body", None, "right@acme.example", dedupe_key="p:1"
        )

        notify.send_counterparty_message(
            db, thread, "a different body", None, "wrong@acme.example", dedupe_key="p:1"
        )

        db.refresh(first)
        assert first.body == "the real body"
        assert first.to_ref == "right@acme.example", "the winner's recipient must stand"


class TestTheRaceTheIndexExistsFor:
    def test_two_concurrent_sends_produce_one_message(self, engine):
        """AI-CONTEXT: two real threads, on two real connections, at the isolation level
        the application actually runs at. Three arrangements were tried before this one
        and two of them proved nothing:

        · Running the sends one after another: the second `SELECT` sees a committed row,
          takes the fast path, and never reaches the index. Measured — the unique index
          could be DROPPED and every test still passed.
        · Forcing the loser to REPEATABLE READ: its check correctly misses and the
          constraint correctly fires, but then its recovery `SELECT` cannot see the winner
          either, so it raises. That is stricter than production, which is READ COMMITTED,
          and it was testing a situation the app never has.

        The real interleaving is the only honest one: both transactions check while
        neither has committed, both insert, and the loser is refused by the index and
        recovers by re-reading the now-committed winner. That is what a double tap and an
        offline-queue replay actually do.
        """
        import threading

        setup = _Session(bind=engine)
        try:
            account = identity.register_account(setup, "race@example.com", "pw-123456")
            thread_row = notify.create_thread(setup, account.id, subject="Detention now accruing")
            setup.commit()
            thread_id, account_id = thread_row.id, account.id
        finally:
            setup.close()

        inserted = threading.Event()   # winner has INSERTed, not yet committed
        checked = threading.Event()    # loser has run its check and seen nothing
        results, errors = {}, []

        def winner():
            s = _Session(bind=engine)
            try:
                t = s.get(notify.OutboundThread, thread_id)
                msg = notify.send_counterparty_message(
                    s, t, "body", None, "ap@acme.example", dedupe_key="race:1"
                )
                inserted.set()
                checked.wait(timeout=10)  # hold the row uncommitted until the loser looks
                # AI-CONTEXT: and hold it until the loser is genuinely BLOCKED inside its
                # INSERT, waiting on the index's lock. Committing merely "after the loser
                # checked" is not enough — the loser's own internal SELECT would then find
                # the committed row and take the fast path, so the constraint is never
                # exercised. Measured: written that way, the index could be removed from
                # the model and this test still passed.
                #
                # `pg_stat_activity` is what makes it observable rather than timed. A
                # sleep would make this flaky in exactly the direction that proves nothing.
                _wait_until_blocked(engine)
                s.commit()
                results["winner"] = msg.id
            except Exception as exc:  # noqa: BLE001 — reported through `errors`
                errors.append(("winner", exc))
                inserted.set()
            finally:
                s.close()

        def loser():
            s = _Session(bind=engine)
            try:
                inserted.wait(timeout=10)
                # READ COMMITTED and the winner has not committed, so this genuinely
                # misses — exactly as a concurrent request's check does
                assert notify.existing_by_dedupe_key(s, "race:1") is None
                checked.set()
                t = s.get(notify.OutboundThread, thread_id)
                msg = notify.send_counterparty_message(
                    s, t, "body", None, "ap@acme.example", dedupe_key="race:1"
                )
                s.commit()
                results["loser"] = msg.id
            except Exception as exc:  # noqa: BLE001
                errors.append(("loser", exc))
                checked.set()
            finally:
                s.close()

        try:
            threads = [threading.Thread(target=winner), threading.Thread(target=loser)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

            assert not errors, f"neither caller may fail: {errors}"
            assert results["winner"] == results["loser"], (
                "both callers must be handed the SAME message, or the broker gets two emails"
            )

            check = _Session(bind=engine)
            try:
                rows = check.query(notify.OutboundMessage).filter_by(dedupe_key="race:1").all()
                assert len(rows) == 1, "the index must refuse the second row"
            finally:
                check.close()
        finally:
            cleanup = _Session(bind=engine)
            try:
                cleanup.query(notify.OutboundMessage).filter_by(thread_id=thread_id).delete()
                cleanup.query(notify.OutboundThread).filter_by(id=thread_id).delete()
                cleanup.execute(
                    sa_text("delete from f01.account where id = :i"), {"i": account_id}
                )
                cleanup.commit()
            finally:
                cleanup.close()


class TestTheVoicePathHasNoNaturalIdentity:
    """AI-CONTEXT: the last unkeyed send, and why its key is shaped differently.

    Every other purpose names a thing — a claim, a receivable, a stop. A driver's own
    ghostwritten message names nothing, and they may legitimately write to the same
    counterparty twice about different matters, so keying on the thread alone would
    silence the second one. The same approved WORDS to the same thread is the duplicate:
    a second tap, a replayed request, or a driver who did not see the first one land.
    """

    def test_the_same_approved_words_twice_send_once(self, db, account):
        from app.modules.m11_voice import public as m11

        thread = _thread(db, account, subject="Where is my BOL?")
        body = "Please confirm receipt of the paperwork for load L-9001."

        first = m11.approve_and_send(db, thread, body, None, "ap@acme.example")
        second = m11.approve_and_send(db, thread, body, None, "ap@acme.example")

        assert second.id == first.id
        assert len(notify.unsent_messages(db)) == 1

    def test_a_different_message_in_the_same_thread_still_sends(self, db, account):
        from app.modules.m11_voice import public as m11

        thread = _thread(db, account, subject="Where is my BOL?")

        a = m11.approve_and_send(db, thread, "Please confirm receipt.", None, "ap@acme.example")
        b = m11.approve_and_send(db, thread, "Also, the lumper receipt.", None, "ap@acme.example")

        assert a.id != b.id, "a driver may write twice about different things"


class TestAReSendIsNotADuplicate:
    def test_releasing_the_purpose_lets_a_fresh_message_take_it(self, db, account):
        # a permanent failure, or an address the driver has since corrected: the broker
        # never got it, so the replacement is the FIRST delivery rather than a second one
        thread = _thread(db, account)
        dead = notify.send_counterparty_message(
            db, thread, "b", None, "wrong@acme.example", dedupe_key="detention_start:c-9"
        )

        notify.release_dedupe_key(db, dead)
        fresh = notify.send_counterparty_message(
            db, thread, "b", None, "right@acme.example", dedupe_key="detention_start:c-9"
        )

        assert fresh.id != dead.id
        assert fresh.to_ref == "right@acme.example"

    def test_the_released_row_survives_as_history(self, db, account):
        # "we tried this address and it bounced" is history a dispute may need, and the
        # address-aware rule exists precisely so it is not rewritten
        thread = _thread(db, account)
        dead = notify.send_counterparty_message(
            db, thread, "the original wording", None, "wrong@acme.example", dedupe_key="p:9"
        )

        notify.release_dedupe_key(db, dead)

        db.refresh(dead)
        assert dead.body == "the original wording"
        assert dead.to_ref == "wrong@acme.example"
        assert dead.dedupe_key is None
