"""AI-CONTEXT: the one seam every image upload passes through, and it exists because
this product had six of them.

Documents, condition photos, rate cons, load documents and two vendor-portal writers each
built their own `base64.b64decode(body.content_b64)`. Six copies of one decision is how
half of them end up with a size limit and half do not — and until this module, ALL of them
did not: `f06_documents.service` records `byte_size=len(content)` and nothing anywhere
compared it to anything. An unbounded base64 string in a JSON body is decoded into memory
before any handler sees it, so the ceiling was the machine.

Two wire formats, deliberately, and only one of them is the future:

  · multipart/form-data — what the app sends now. The bytes travel as bytes.
  · application/json with `content_b64` — what a REPLAY sends. A phone that queued a
    capture under an older build still has that row in localStorage, and its opId is the
    F12 idempotency key that makes the replay exactly-once. Refusing it would discard a
    driver's evidence for the crime of having been captured before a deploy.

The +33% is the reason the app moved: base64 inflates every photograph by a third, over
the LTE of a truck stop, on the one payload in this product that is already the largest
thing it sends.
"""

import base64
import binascii
import json

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings


def max_upload_bytes() -> int:
    return get_settings().max_upload_mb * 1024 * 1024


def _too_large() -> HTTPException:
    # 413 rather than 400: the client can tell "this file is too big" from "this request
    # is malformed", and only one of those is worth asking a driver to act on.
    mb = get_settings().max_upload_mb
    return HTTPException(
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        f"upload exceeds {mb} MB",
    )


def decode_b64(content_b64: str | None) -> bytes | None:
    """The legacy path, with the ceiling the six hand-rolled copies never had."""
    if not content_b64:
        return None
    # checked BEFORE decoding: a base64 string is 4/3 of its payload, so this rejects an
    # oversize upload without ever materialising it.
    if len(content_b64) > (max_upload_bytes() * 4) // 3 + 4:
        raise _too_large()
    try:
        content = base64.b64decode(content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "content is not valid base64") from exc
    if len(content) > max_upload_bytes():
        raise _too_large()
    return content


async def read_upload[ModelT: BaseModel](
    request: Request, model: type[ModelT]
) -> tuple[ModelT, bytes | None]:
    """Parse either wire format into (validated fields, bytes).

    The handler that calls this stops caring which format arrived, which is the point:
    a second code path per endpoint is how one of them silently keeps the old bug.
    """
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()

    if content_type == "multipart/form-data":
        form = await request.form()
        upload = form.get("file")
        content: bytes | None = None
        if upload is not None and hasattr(upload, "read"):
            content = await upload.read()
            if len(content) > max_upload_bytes():
                raise _too_large()

        # every non-file part is a field. `fields` carries the JSON object the model
        # expects, so a caller can send the same shape either way.
        raw = form.get("fields")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "fields is not valid JSON") from exc
        if not isinstance(data, dict):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "fields must be an object")

        if content is not None and hasattr(upload, "content_type"):
            # the browser knows what it encoded; trust it over anything the form claims,
            # but never let it be absent — F6 serves this value straight back.
            data.setdefault("content_type", upload.content_type)
        if content is not None and getattr(upload, "filename", None):
            data.setdefault("filename", upload.filename)

        try:
            parsed = model.model_validate(data)
        except ValidationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.errors()) from exc
        return parsed, content

    body = await request.body()
    if len(body) > (max_upload_bytes() * 4) // 3 + 4096:
        raise _too_large()
    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "body is not valid JSON") from exc
    try:
        parsed = model.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.errors()) from exc
    return parsed, decode_b64(getattr(parsed, "content_b64", None))
