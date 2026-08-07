from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_settings = get_settings()
# AI-CONTEXT: the pool, sized deliberately after it ran out (§23 entry 93).
#
# The default is 5 connections with 10 overflow. A single phone whose map was
# refetching on every GPS fix exhausted it, and an exhausted pool does not degrade —
# requests block for 30 s and then raise, so the API stops answering and the proxy
# returns 502. The CAUSE was the client hammering (fixed there); this is the second
# line of defence, so the next unthrottled caller degrades instead of failing over.
#
# `pool_recycle` matters more here than the size: this runs against a Postgres in a
# sibling container and a connection idle across a restart is a connection that will
# fail on first use. `pool_pre_ping` already catches that; recycling keeps it rare.
engine = create_engine(
    _settings.database_url,
    future=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def violates_constraint(exc: IntegrityError, constraint: str) -> bool:
    # AI-CONTEXT: names the ONE constraint a caller is prepared to handle, so translating
    # an IntegrityError into a domain exception can never widen into "any integrity failure
    # means the thing I expected" — a NOT NULL or FK violation must keep propagating as
    # itself. psycopg reports the constraint in diag; the string fallback covers drivers
    # that do not. Used by F7's DuplicateEntry and M6's SpotUnavailable.
    name = getattr(getattr(exc, "orig", None), "diag", None)
    name = getattr(name, "constraint_name", None)
    if name is not None:
        return name == constraint
    return constraint in str(getattr(exc, "orig", exc))


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
