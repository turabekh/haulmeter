from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    auth,
    load,
    m01_map,
    m02_facility_intel,
    m03_detention,
    m04_accessorial,
    m05_protection,
    m06_parking,
    m07_fuel,
    m08_intelligence,
    m09_money,
    m10_community,
    m11_voice,
    m12_fleet,
    m13_vendor,
    owner,
    public,
    share,
    vendor_portal,
)
from app.core.config import get_settings

settings = get_settings()


def _wire_object_storage() -> None:
    # AI-CONTEXT: put MinIO (already in the compose topology, 9018) in the F6
    # object-storage path so evidence photo bytes persist and serve across
    # processes. Falls back to the in-memory default if MinIO is unreachable —
    # capture never breaks (the hash/chain still records; the image is just
    # unavailable). Tests keep the in-memory default (lifespan doesn't run).
    from app.foundation.f06_documents import public as documents

    try:
        storage = documents.MinioObjectStorage(
            settings.minio_endpoint,
            settings.minio_access_key,
            settings.minio_secret_key,
            settings.minio_bucket,
        )
        documents.set_default_storage(storage)
        # prove the credentials actually work rather than trusting construction:
        # the client is lazy, so a bad secret only surfaces on first use, which used
        # to be a driver's photo hours later
        storage.put("_wiring/probe", b"ok", "text/plain")
    except Exception as exc:  # MinIO down / misconfigured -> keep the in-memory default
        # AI-CONTEXT: the fallback stays — a capture must never crash on storage —
        # but the SILENCE does not. This swallowed a SignatureDoesNotMatch for the
        # whole life of the project: the compose file passed no MinIO credentials to
        # this service, so it used its own defaults, whose secret did not match
        # MINIO_ROOT_PASSWORD. Every document and every evidence photo went into an
        # in-process dict and evaporated on the next restart, while the UI reported
        # success. A backend that cannot store bytes has to say so out loud.
        import sys

        print(
            f"WARNING: object storage unavailable ({type(exc).__name__}: {exc}). "
            "Falling back to IN-MEMORY storage — uploaded bytes will NOT survive a "
            "restart. Check MINIO_* in infra/.env.",
            file=sys.stderr,
            flush=True,
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _wire_object_storage()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# AI-CONTEXT: the driver frontend (Quasar/Vue dev) runs on the LOCKED UI ports
# 9008 / 3008 fallback (HANDOFF §2). Dev CORS is scoped to those origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:9008",
        "http://localhost:3008",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(public.router)
app.include_router(share.router)
app.include_router(owner.router)
app.include_router(load.router)
app.include_router(m01_map.router)
app.include_router(m02_facility_intel.router)
app.include_router(m03_detention.router)
app.include_router(m04_accessorial.router)
app.include_router(m05_protection.router)
app.include_router(m06_parking.router)
app.include_router(m07_fuel.router)
app.include_router(m08_intelligence.router)
app.include_router(m09_money.router)
app.include_router(m10_community.router)
app.include_router(m11_voice.router)
app.include_router(m12_fleet.router)
app.include_router(m13_vendor.router)
app.include_router(vendor_portal.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
