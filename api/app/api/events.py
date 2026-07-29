"""AI-CONTEXT: the live stream (§23 entry 103) — SSE, and the one rule it must never break.

**No database session survives into the stream.** FastAPI's `Depends(get_db)` yields a
session for the lifetime of the REQUEST, and an SSE request lives for minutes. Wired
that way, every connected driver pins one pooled connection: `pool_size=10,
max_overflow=20` means the thirty-first driver takes the API down for everyone. §23
entry 93 already did exactly this to this codebase with a single phone's GPS stream,
and a stream endpoint is that failure mode by construction rather than by accident.

So authentication opens a session, resolves the account, and CLOSES it before the
generator starts. Inside the generator there is Redis and nothing else. The events it
carries are ALSO rows the ordinary REST endpoints return, so a driver whose stream
fails is exactly as well served as they were before this existed — one refetch behind.

SSE rather than WebSockets because every event here travels server→client only. SSE is
plain HTTP: it survives Caddy without a second protocol path, reconnects itself with
no client code, and degrades to nothing on a network that eats long-lived sockets —
which §15.1 already treats as a normal condition rather than an error.
"""

import time
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core import events
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility.domain import geohash

router = APIRouter(prefix="/events", tags=["events"])


def cell_for(lat: float, lon: float) -> str:
    """lat/lon -> the fan-out cell. Lives HERE because `core` may not import
    `foundation`, and F2's geohash is the one encoder in the tree — a second one would
    eventually publish to a channel nobody was subscribed to."""
    return geohash.encode(lat, lon, precision=events.CELL_PRECISION)

# what a driver may listen to. An allowlist rather than a free-form channel name, so a
# client cannot subscribe to something the product never meant to broadcast.
STREAMABLE = ("handoff",)


def _stream(kind: str, lat: float, lon: float) -> Iterator[str]:
    started = time.monotonic()
    last_beat = started
    # `retry` tells EventSource how long to wait before reconnecting; stating it means
    # a fleet that all drop together does not all return in the same instant
    yield "retry: 5000\n\n"
    try:
        subscription = events.subscription(kind, cell_for(lat, lon))
    except Exception:  # noqa: BLE001
        # Redis unreachable. The stream is an ACCELERATOR, never a source of truth —
        # every event it would carry is already a row the REST path returns. So it
        # closes politely and the client falls back to its own refresh, exactly as it
        # behaved before this endpoint existed. Erroring here would turn a degraded
        # nicety into a visible failure on the driver's map.
        yield "event: bye\ndata: {}\n\n"
        return
    with subscription as pubsub:
        while True:
            now = time.monotonic()
            if now - started > events.MAX_STREAM_SECONDS:
                # the client reconnects on its own; a capped stream is what stops a
                # forgotten tab holding a subscriber slot for a week
                yield "event: bye\ndata: {}\n\n"
                return
            try:
                message = pubsub.get_message(timeout=1.0)
            except Exception:  # noqa: BLE001 — Redis went away mid-stream
                yield "event: bye\ndata: {}\n\n"
                return
            if message and message.get("type") == "message":
                yield f"event: {kind}\ndata: {message['data']}\n\n"
                last_beat = now
                continue
            if now - last_beat >= events.HEARTBEAT_SECONDS:
                # a comment frame: keeps proxies and mobile networks from judging a
                # silent socket dead, and costs two bytes on the wire
                yield ": beat\n\n"
                last_beat = now


@router.get("/stream")
def stream(
    kind: str = Query(default="handoff"),
    lat: float = Query(...),
    lon: float = Query(...),
    # AI-CONTEXT: the session travels in the QUERY here, and only here. EventSource
    # cannot set a header — that is a limitation of the browser API, not a choice —
    # so the alternatives were a query token or a second short-lived ticket endpoint.
    # The cost is real and is logged rather than hidden: a query string reaches access
    # logs where a header does not. It rides the same TLS, to the same origin, and is
    # the same token the REST calls already send. If this ever leaves a testing
    # environment, a single-use stream ticket is the upgrade (§23 entry 103).
    access_token: str = Query(default=""),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    token = access_token or (
        authorization[len("Bearer ") :] if authorization.startswith("Bearer ") else ""
    )
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing session")
    if kind not in STREAMABLE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"cannot stream {kind!r}")
    # AI-CONTEXT: resolved HERE, inside the request, and then the session is done with.
    # `db` is released when this function returns — before a single byte of the body is
    # generated — which is the whole reason the account is resolved eagerly rather than
    # inside the generator where it would be convenient.
    account = identity.resolve_session(db, token)
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired session")

    return StreamingResponse(
        _stream(kind, lat, lon),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Caddy streams `text/event-stream` unbuffered, but an intermediate proxy a
            # driver's carrier inserts may not. This is the conventional ask.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def publish_handoff(handoff, lat: float, lon: float) -> None:
    """Announce a relay the moment it is broadcast. Called from the write path AFTER
    the row is committed, so nothing is announced that a refetch would not confirm."""
    events.publish(
        "handoff",
        cell_for(lat, lon),
        {
            "handoff_id": str(handoff.id),
            "facility_id": str(handoff.facility_ref),
            "leaving_at": handoff.leaving_at.isoformat() if handoff.leaving_at else None,
        },
    )
