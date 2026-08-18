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


def require_object_storage(role: str = "script") -> None:
    """Wire real object storage or refuse to run. For SCRIPTS and one-off jobs.

    AI-CONTEXT: THE FAILURE THIS EXISTS FOR IS SILENT AND COST A PRODUCTION OUTAGE. The
    long-running processes call `wire_object_storage` at startup; a `docker compose exec
    ... python -m scripts.x` does NOT — it imports the app and runs, and `default_storage()`
    is still the in-memory fallback. Anything that writes a document from such a process
    therefore writes the bytes into that process's memory and they die with it, while the
    database row survives pointing at a storage key that was never written.

    It reports success the whole way. The job printed `{'synthesized': 25, 'failed': 0}`,
    every row got an `audio_ref`, and every play button on production 404'd — 31 audio
    objects, all of them, with nothing red anywhere. Falling back is right for a SERVER
    (a driver's session should not die because MinIO is down); it is wrong for a script,
    whose entire purpose is to leave something behind.
    """
    if not wire_object_storage(role):
        raise SystemExit(
            f"[{role}] refusing to run: object storage is unavailable, so anything this "
            "writes would go to memory and vanish when the process exits — while leaving "
            "database rows pointing at bytes that never existed. Check MINIO_* in "
            "infra/.env and that the minio service is up."
        )


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
