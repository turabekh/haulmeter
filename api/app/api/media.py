"""AI-CONTEXT: image bytes a browser can load from an `<img>` tag, which is the whole
reason the read path was slow.

`fetchEvidencePhoto` fetches with an Authorization header, reads a Blob and hands back an
object URL. It has to: an `<img src>` cannot carry a header. Everything expensive about
the contact sheets follows from that one constraint —

  · no `loading="lazy"`, because there is no `src` for the browser to defer
  · no progressive decode; the whole image lands in JS memory before a pixel is drawn
  · the fetches were written as `await` in a `for` loop, so a four-stop load fetched
    twenty-four full-size photographs one after another

So the URL carries its own authority: the server mints a short-lived signature for a
driver who is already authenticated and already owns the row, and the browser then treats
it as an ordinary image. That is a bearer capability until it expires, which is the
trade-off the owner accepted.

WHY THIS IS SIGNED BY THE API AND NOT BY MINIO. The owner chose presigned MinIO URLs. A
presigned URL points at the object store's own endpoint, and in the deployed topology
MinIO publishes NO port and the Caddyfile has no route to it — "nothing but the proxy
publishes a port" (§23 entry 92). Such a URL is unreachable from a phone. Routing the
edge to the object store is an infrastructure and exposure decision that belongs to the
owner, so the capability is terminated here instead: identical for the client (a plain
`src`, native lazy-load, the browser's own HTTP cache) with the object store left
private. Swapping in real presigning later is this module and nothing else.
"""

import hashlib
import hmac
import secrets
import sys
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.foundation.f04_evidence import public as evidence
from app.foundation.f06_documents import public as documents
from app.foundation.f06_documents.domain import audio as audio_media

router = APIRouter(prefix="/media", tags=["media"])

KIND_DOCUMENT = "document"
KIND_EVIDENCE = "evidence"
SIZE_FULL = "full"
SIZE_THUMB = "thumb"

_process_secret: str | None = None


def _signing_secret() -> str:
    """AI-CONTEXT: configured, or random per process — and the fallback is deliberate.

    Secrets are generated ON the box and never shipped (rule 9, §23 entry 92), so a
    deployment that has not been given one must still work. A per-process key means URLs
    do not survive a restart, which for a one-hour image capability is a non-event: the
    surface re-mints them on its next render and a stale `<img>` simply falls back to its
    pending block. It degrades to a refetch, never to a wrong image.
    """
    global _process_secret
    configured = get_settings().media_signing_secret
    if configured:
        return configured
    if _process_secret is None:
        _process_secret = secrets.token_urlsafe(48)
        print(
            "NOTE: MEDIA_SIGNING_SECRET unset — image URLs are signed with a per-process "
            "key and stop working after a restart. Set it to keep them stable.",
            file=sys.stderr,
            flush=True,
        )
    return _process_secret


def _sign(kind: str, ref: str, size: str, expires: int) -> str:
    payload = f"{kind}:{ref}:{size}:{expires}".encode()
    return hmac.new(_signing_secret().encode(), payload, hashlib.sha256).hexdigest()[:32]


def media_url(kind: str, ref, size: str = SIZE_THUMB, ttl: int | None = None) -> str:
    """The URL a surface hands to an `<img src>`. Relative, because the deployment serves
    the UI and the API on ONE origin and an absolute URL would have to know the domain."""
    expires = int(time.time()) + (ttl or get_settings().media_url_ttl_seconds)
    ref = str(ref)
    sig = _sign(kind, ref, size, expires)
    return f"/media/{kind}/{ref}?size={size}&exp={expires}&sig={sig}"


@router.get("/{kind}/{ref}")
def serve_media(
    request: Request,
    kind: str,
    ref: uuid.UUID,
    exp: int,
    sig: str,
    size: str = SIZE_THUMB,
    db: Session = Depends(get_db),
) -> Response:
    """AI-CONTEXT: no session dependency, on purpose — an `<img>` cannot send one.

    The signature IS the authorisation: it was minted for a driver who was authenticated
    and who owned this row at the time. Ownership is therefore checked when the URL is
    made, not here, which is what lets the browser fetch it like any other image.
    """
    if size not in (SIZE_FULL, SIZE_THUMB):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown size")
    if exp < int(time.time()):
        # 403 rather than 404: the client can tell "this link aged out, ask again" from
        # "there is no such image", and only the first is worth re-rendering for
        raise HTTPException(status.HTTP_403_FORBIDDEN, "link expired")
    # constant-time: a signature check that leaks its comparison position leaks the
    # signature one byte at a time
    if not hmac.compare_digest(sig, _sign(kind, str(ref), size, exp)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "bad signature")

    storage_key, content_type = _locate(db, kind, ref)
    if storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no image")

    # AI-CONTEXT: retained-then-deleted is a DIFFERENT answer from never-existed, and a
    # player deserves to be told which (E3 §E3.4.3). 410 Gone rather than 404: the object
    # was here, its retention window closed, and it is not coming back — so a client
    # should stop asking rather than retry. Without this the driver would get a 500 from
    # a read against bytes the sweep removed, which reads as a broken product rather than
    # as a promise being kept.
    if kind == KIND_DOCUMENT:
        doc = db.get(documents.Document, ref)
        if doc is not None and doc.bytes_deleted_at is not None:
            raise HTTPException(
                status.HTTP_410_GONE,
                "this recording passed its 30-day retention window and was deleted",
            )

    if size == SIZE_THUMB:
        try:
            data = documents.default_storage().get(documents.thumbnail_key(storage_key))
            content_type = documents.THUMB_CONTENT_TYPE
        except Exception:
            # AI-CONTEXT: the derivative may not exist yet — the job runs every five
            # minutes and a photograph taken thirty seconds ago has not been reached.
            # Falling back to the original is what makes the whole feature safe to ship
            # ahead of the backfill: a contact sheet is briefly as slow as it always was,
            # rather than empty.
            data = _read_or_404(storage_key)
    else:
        data = _read_or_404(storage_key)

    headers = {
        # AI-CONTEXT: the evidence photo route had NO cache header at all, so every
        # scroll past a contact sheet re-downloaded every photograph. The bytes are
        # immutable — an artifact is appended to a hash chain, never edited — so the
        # long immutable cache the document route has always had is correct here too.
        # `private` because these are one driver's evidence and must not sit in a
        # shared proxy.
        "Cache-Control": "private, max-age=31536000, immutable",
    }

    # AI-CONTEXT: RANGE, and only for audio (E3 §E3.4.3).
    #
    # An `<audio>` element issues a Range request before it will show a duration or let
    # anyone scrub. A server that answers 200-with-everything makes the element download a
    # whole recording to play the last four seconds — on a driver's data plan, in a truck
    # stop. Images do not do this, which is why `Accept-Ranges` is advertised only where
    # it is true: claiming range support and then ignoring the header is worse than not
    # claiming it, because a player believes the claim.
    #
    # The Range header is NOT part of the signature, deliberately. The signature
    # authorises the object; which slice of it the browser wants is a transport concern,
    # and folding it in would mint a URL that works once and fails on the first seek.
    if not audio_media.is_audio(content_type):
        return Response(
            content=data, media_type=content_type or "application/octet-stream", headers=headers
        )

    headers["Accept-Ranges"] = "bytes"
    try:
        window = audio_media.parse_range(request.headers.get("range"), len(data))
    except audio_media.InvalidRange as exc:
        # 416 rather than 400: a player reads this as "ask differently", and the
        # Content-Range tells it what the object's real size is so it can.
        raise HTTPException(
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            str(exc),
            headers={"Content-Range": f"bytes */{len(data)}"},
        ) from exc

    if window is None:
        return Response(content=data, media_type=content_type, headers=headers)

    start, end = window
    headers["Content-Range"] = audio_media.content_range_header(start, end, len(data))
    return Response(
        content=data[start : end + 1],  # inclusive on both ends, unlike a Python slice
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=content_type,
        headers=headers,
    )


def _read_or_404(storage_key: str) -> bytes:
    try:
        return documents.default_storage().get(storage_key)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no image") from exc


def _locate(db: Session, kind: str, ref: uuid.UUID) -> tuple[str | None, str | None]:
    if kind == KIND_DOCUMENT:
        doc = db.get(documents.Document, ref)
        return (doc.storage_key, doc.content_type) if doc is not None else (None, None)
    if kind == KIND_EVIDENCE:
        artifact = evidence.get_artifact(db, ref)
        if artifact is None:
            return (None, None)
        return artifact.storage_key, (artifact.exif or {}).get("content_type") or "image/jpeg"
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown media kind")
