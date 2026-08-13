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
