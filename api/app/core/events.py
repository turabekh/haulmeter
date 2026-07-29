"""AI-CONTEXT: the live event bus (§23 entry 103) — Redis pub/sub, and the reason it
is Redis rather than a database poll.

A live channel exists to tell a driver something the moment it happens. The obvious
implementation — an SSE endpoint that queries Postgres on a timer — moves the polling
from the client to the server and makes the load WORSE: the same queries, now once per
connected driver, held open for the life of the connection. §23 entry 93 is the
cautionary tale in this exact codebase: a single phone's position stream exhausted
`QueuePool limit of size 5 overflow 10` and the API answered 502 for everyone.

So the rule this module exists to enforce: **a stream holds a Redis subscription, never
a database session.** Writers publish once, at the moment of the write; readers hold a
socket to Redis, which is designed for tens of thousands of idle subscribers on
hardware where Postgres would be at thirty.

Degrading is deliberate and silent. Redis is not a system of record here — every event
it carries is ALSO a row that the ordinary REST path already returns. If Redis is
absent, unreachable or slow, `publish` swallows it and the product keeps working
exactly as it did before this module existed: the client refetches on its own schedule
and is at most one interval behind. A live channel that took the write path down with
it when it failed would be a worse product than no live channel at all.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.config import get_settings

log = logging.getLogger(__name__)

# design-prd §11.5's grid is a display concern; this is a FAN-OUT concern. Precision 4
# is roughly a 40 km cell — big enough that a driver near a boundary still hears about
# the lot they could reach, small enough that a broadcast in Ohio never wakes a stream
# in Texas. It is deliberately coarser than the 150 m co-location radius: this decides
# who is TOLD, and the client still filters by its own viewport.
CELL_PRECISION = 4

# a stream is not a session. Capped so a forgotten tab cannot hold a subscriber slot
# for a week; the client reconnects, which EventSource does by itself.
MAX_STREAM_SECONDS = 1800
# how often a comment frame goes out to keep proxies and phones from judging the
# connection dead. Caddy and most mobile networks drop a silent socket well inside 60 s.
HEARTBEAT_SECONDS = 20


# AI-CONTEXT: the CELL is passed in, never computed here — `core` may not import
# `foundation` (import-linter's spine contract), and the geohash implementation lives
# in F2. Duplicating it to satisfy the boundary would put two encoders in the tree and
# make the channel a driver publishes to differ from the one they subscribe to the
# first time either drifted. The composition layer above owns the conversion.
def channel_for(kind: str, cell: str) -> str:
    return f"longhaul:{kind}:{cell}"


def _client():
    """A client per call site. Redis clients are cheap and a module-level singleton
    shared between the publishing request threads and a long-lived subscriber is how
    pub/sub connections end up in a state neither side expects."""
    import redis

    settings = get_settings()
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )


def publish(kind: str, cell: str, payload: dict) -> bool:
    """Announce something that just happened. Returns whether it went out, which
    callers are free to ignore — and every current caller does, because the write it
    accompanies has already been committed and is already readable over REST."""
    try:
        body = json.dumps({"kind": kind, **payload})
        _client().publish(channel_for(kind, cell), body)
        return True
    except Exception:  # noqa: BLE001 — a telemetry channel may never break a write
        log.warning("event publish failed (kind=%s) — REST path unaffected", kind, exc_info=False)
        return False


@contextmanager
def subscription(kind: str, cell: str) -> Iterator:
    """Subscribe to one cell. The caller iterates; this owns the socket's lifetime so a
    dropped client cannot leak it."""
    client = _client()
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    try:
        pubsub.subscribe(channel_for(kind, cell))
        yield pubsub
    finally:
        try:
            pubsub.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass
