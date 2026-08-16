import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    auth,
    events,
    load,
    location,
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
    m14_recovery,
    m15_roadside,
    media,
    notifications,
    owner,
    public,
    share,
    vendor_portal,
)
from app.core.config import get_settings

settings = get_settings()


def _wire_object_storage() -> None:
    # AI-CONTEXT: moved to `app/wiring.py` so the WORKER can call it too. It lived here,
    # in the API's lifespan, and the worker is a separate process — so `default_storage()`
    # there was the in-memory dict and the first job to reach for a driver's photograph
    # failed on every row. It sits at the app root rather than in `core/` because core is
    # forbidden from importing foundation (import-linter caught exactly that). Tests keep
    # the in-memory default (lifespan does not run).
    from app.wiring import wire_object_storage

    wire_object_storage("api")


def _register_module_flags() -> None:
    """§23 entry 105: PRD §6 requires every module behind its own flag, and twelve had
    none registered — so `is_enabled` answered False for all of them and there was no
    kill switch to reach. Idempotent, and it runs before the first request so a gate
    can never see a flag that has not been registered yet."""
    from app.core.db import SessionLocal
    from app.module_registry import register_all

    db = SessionLocal()
    try:
        register_all(db)
        db.commit()
        _report_ungated_activations(db)
    except Exception:  # noqa: BLE001 — a registry failure must not stop the API booting
        db.rollback()
        print(
            "WARNING: module flag registration failed — every gated module will "
            "answer 404 until this is fixed",
            file=sys.stderr,
            flush=True,
        )
    finally:
        db.close()


def _report_ungated_activations(db) -> None:
    """Say out loud which capabilities are running ahead of their own preconditions.

    AI-CONTEXT: audit F-02's honest half (§23 entry 133). Three modules carry validation
    gates and all six were unsatisfied while all three flags read enabled — M3 detention
    without `legal_signoff`, M6 parking without a `refund_policy`, M7 fuel without a
    `merchant_agreement`. Those encode business facts a deploy cannot decide, and blocking
    the default on them would have taken the detention clock down, so the 29 July decision
    to preserve live behaviour stands.

    What the gate can honestly do is refuse to be silent. This prints at every boot, which
    is where an operator will actually see it, and `/admin/flags` carries the same list for
    the console. §11.7 says never assert what you do not know; this is that rule aimed at
    the operator rather than the driver.
    """
    from app.foundation.f13_flags import public as flags

    ahead = flags.running_ahead_of_gates(db)
    if not ahead:
        return
    for key, unsatisfied in ahead:
        print(
            f"WARNING: {key} is ON with unsatisfied validation gates: "
            f"{', '.join(unsatisfied)} — the capability is live and its preconditions "
            f"are not recorded as met",
            file=sys.stderr,
            flush=True,
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _wire_object_storage()
    _register_module_flags()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# AI-CONTEXT: the driver frontend (Quasar/Vue dev) runs on the LOCKED UI ports
# 9008 / 3008 fallback (HANDOFF §2). Dev CORS is scoped to those origins.
app.add_middleware(
    CORSMiddleware,
    # AI-CONTEXT: a deployment serves the UI and the API on ONE origin (the proxy
    # routes /api to here), so CORS does not apply there at all. This list stays for
    # local development, where Vite is on 9008 and the API on 8008 — two origins.
    # `CORS_ORIGINS` exists for a deployment that ever splits them again; leaving it
    # unset is the correct state for the same-origin arrangement.
    allow_origins=[
        o
        for o in [
            "http://localhost:9008",
            "http://localhost:3008",
            *(x.strip() for x in (settings.cors_origins or "").split(",")),
        ]
        if o
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
app.include_router(location.router)
app.include_router(media.router)
app.include_router(notifications.router)
app.include_router(events.router)
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
app.include_router(m14_recovery.router)
app.include_router(m15_roadside.router)
app.include_router(m13_vendor.router)
app.include_router(vendor_portal.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
