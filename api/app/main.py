from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    auth,
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
)
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
