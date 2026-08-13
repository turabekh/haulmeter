"""AI-CONTEXT: object-storage wiring, in ONE place, because it was in the API's lifespan
and the worker is a different process.

It lives at the app root beside `main.py` and `worker.py`, NOT in `core/`: the
architecture spine forbids `app.core` from importing `app.foundation`, and this has to
reach F6 to install the adapter. import-linter caught the first attempt.

`main._wire_object_storage` runs from the FastAPI lifespan. The worker never calls it, so
`default_storage()` there is the in-memory dict every process starts with — and the first
worker job to reach for a driver's photograph found nothing, for every row, forever. It
reported that as a failure count and healed nothing, which is this codebase's recurring
shape: a mechanism built, registered, running, and unable to do its work.

Found by running the derivative job against the real 197 stored objects and reading the
summary instead of the exit code — `{'made': 0, 'skipped': 0, 'failed': 197}` on a box
where every one of those objects is present in MinIO.

The fallback stays and so does the warning: a capture must never crash on storage, and a
backend that cannot store bytes has to say so out loud (§23 — the SignatureDoesNotMatch
that was swallowed for the life of the project).
"""

import sys

from app.core.config import get_settings


def wire_object_storage(role: str = "api") -> bool:
    """True when real object storage is in place. `role` names the process in the
    warning, because "which one of them lost the photograph" is the first question."""
    from app.foundation.f06_documents import public as documents

    settings = get_settings()
    try:
        storage = documents.MinioObjectStorage(
            settings.minio_endpoint,
            settings.minio_access_key,
            settings.minio_secret_key,
            settings.minio_bucket,
        )
        documents.set_default_storage(storage)
        # prove the credentials actually work rather than trusting construction: the
        # client is lazy, so a bad secret only surfaces on first use, which used to be a
        # driver's photo hours later
        storage.put("_wiring/probe", b"ok", "text/plain")
        return True
    except Exception as exc:  # MinIO down / misconfigured -> keep the in-memory default
        print(
            f"WARNING [{role}]: object storage unavailable ({type(exc).__name__}: {exc}). "
            "Falling back to IN-MEMORY storage — uploaded bytes will NOT survive a "
            "restart. Check MINIO_* in infra/.env.",
            file=sys.stderr,
            flush=True,
        )
        return False
