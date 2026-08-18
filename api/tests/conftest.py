# Tests are hermetic: never use the real F9 provider. Clear the key BEFORE any app
# import so get_settings() (and each module's resolve_provider()) sees no key and
# falls back to the deterministic FakeModelProvider — no network, no cost, no flake.
# (Only affects this pytest process; the running app container keeps its key.)
import os

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("FMCSA_WEBKEY", None)  # -> deterministic FakeAuthorityVerifier
os.environ.pop("VOYAGE_API_KEY", None)  # -> deterministic Fake embeddings
# ...and never send REAL email from the suite. Blanking the host makes
# `counterparty_gateway()` resolve to the recording gateway, so the threading,
# provider-ref and tiering logic are all exercised and nothing reaches an SMTP server.
# A test run that filled Mailpit would be slow AND a lie about what was actually sent.
os.environ["SMTP_HOST"] = ""

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import Base
from db_registry import import_all_models

SCHEMAS = [
    "f01",
    "f02",
    "f03",
    "f04",
    "f05",
    "f06",
    "f07",
    "f08",
    "f09",
    "f10",
    "f12",
    "f13",
    "f14",
    "f15",
    "m02",
    "m03",
    "m04",
    "m05",
    "m06",
    "m07",
    "m09",
    "m10",
    "m12",
    "m13",
    "m14",
    # AI-CONTEXT: m15 (E3, D14). This list is the sibling of `MODEL_MODULES` and is just
    # as load-bearing: `create_all` will not invent a schema, so omitting a module here
    # fails at `CREATE TYPE m15.difficulty` — before any table — and every test in the
    # module errors at fixture setup rather than failing on an assertion.
    "m15",
]
TEST_DB = "longhaul_test"


def _admin_url(settings) -> str:
    return (
        f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/postgres"
    )


def _test_url(settings) -> str:
    return (
        f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{TEST_DB}"
    )


@pytest.fixture(scope="session")
def engine():
    import_all_models()
    settings = get_settings()

    admin = create_engine(_admin_url(settings), future=True, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin.dispose()

    eng = create_engine(_test_url(settings), future=True)
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # btree_gist backs m06.booking's ex_booking_no_overlap (the `spot_id WITH =`
        # operand). Migration 0060 installs it on a real database; this schema is built
        # by create_all, so without it every m06 test fails at CREATE TABLE.
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        for schema in SCHEMAS:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Session:
    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session = factory()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def flush_outbox(db):
    """Run the `outbound_mail` sweep, the way the worker does.

    AI-CONTEXT: counterparty email is no longer sent on the request path. It was 2.5 s of
    connect/STARTTLS/AUTH inside the handler before a byte of a notice moved, with a 10 s
    timeout, holding a POOLED DATABASE CONNECTION and a threadpool slot for the whole
    round trip — §23 records that exact outage ("QueuePool limit of size 5 overflow 10
    reached"). `send_counterparty_message` records the row; this sweep delivers it.

    So a test that asserts a broker RECEIVED something has to run the sweep, and that is
    not ceremony — it is the system. A test asserting delivery without it would be
    asserting the old architecture.

    It reconciles too, because the real job does: M3 stamps `start_notice_sent_at` and
    appends the `notice_sent` evidence record when a notice actually lands, which is what
    keeps the detention pack's "we notified the broker at 10:05" line from quietly
    disappearing now that every notice goes out asynchronously.
    """
    from app.foundation.f08_notifications import public as notify
    from app.modules.m03_detention import public as m3
    from app.modules.m05_protection import public as m5

    def _flush(gateway=None, now=None):
        gateway = gateway if gateway is not None else notify.counterparty_gateway()
        summary = notify.retry_unsent_messages(db, gateway, now=now)
        delivered = summary.pop("delivered", [])
        summary["reconciled_notices"] = m3.reconcile_delivered_notices(db, delivered)
        summary["reconciled_on_time"] = m5.reconcile_on_time_notices(db, delivered)
        db.flush()
        return summary

    return _flush


@pytest.fixture
def flush_push(db):
    """Run the `push_delivery` sweep, the way the worker does.

    AI-CONTEXT: driver push is no longer sent on the request path. `dispatch` called
    `send_push` inline — a POST per subscription with a ten-second timeout, once per
    browser, inside the request handler and holding a pooled database connection on a
    third party (§23's QueuePool outage). It now records a `queued` notification and this
    sweep hands it over.

    So a test that asserts a driver's browser RECEIVED something has to run the sweep.
    That is not ceremony — it is the system. Tests that assert F8's DECISION laws
    (tiering, quiet hours, the interruption budget, opt-in) correctly assert `queued` and
    need none of this: those laws are all applied at dispatch time, where they belong,
    because they are facts about the moment a driver would be interrupted.
    """
    from app.foundation.f08_notifications import public as notify

    def _flush(gateway=None, now=None):
        factory = (lambda _account_id: gateway) if gateway is not None else None
        summary = notify.deliver_queued_notifications(db, factory, now=now)
        db.flush()
        return summary

    return _flush


@pytest.fixture(autouse=True)
def _no_live_model_calls(monkeypatch):
    """NO TEST EVER TALKS TO A REAL MODEL PROVIDER.

    AI-CONTEXT: added after a change made it possible without anyone deciding to. The
    roadside socket started answering an `answer` frame with the officer's next line in the
    same handler — correct, and it meant every test that sent an answer now reached
    `conversational_officer`, which resolves the LIVE provider. On a developer box with a
    real key in `infra/.env` that is an HTTP call with a 60-second timeout, so the suite did
    not fail: it HUNG, one minute per test, and looked like a wedged container.

    Two properties this holds, and the second is why it is autouse rather than opt-in:
      · **CI parity** — CI has no key, so `resolve_provider` returns the fake there and the
        same suite behaves differently on the two boxes. A test that passes only where no
        credentials exist is not a test anyone can trust.
      · **live-fire discipline** — this repo's rule is that activated transports are real in
        every environment. A suite that can spend money and reach a vendor by accident is
        the same class of mistake as a mail test that can reach a stranger's inbox.

    A test that genuinely wants a provider monkeypatches its own, exactly as before; this
    only removes the DEFAULT path to the network.
    """
    from app.foundation.f09_ai_gateway import public as _ai
    from app.foundation.f09_ai_gateway.domain import provider as _provider

    def _fake():
        return _provider.FakeModelProvider()


    # ONLY the public binding, which is the one every real caller holds — `public.py`
    # re-exports by value, so a module patch would not reach them anyway. Deliberately NOT
    # patching `provider.resolve_provider`: that function is itself under test in
    # `test_ai_gateway.py`, and a guard that rewrites the subject of a test is not a guard,
    # it is a false pass waiting to happen.
    monkeypatch.setattr(_ai, "resolve_provider", _fake)
