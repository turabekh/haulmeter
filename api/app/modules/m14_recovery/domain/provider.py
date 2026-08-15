"""AI-CONTEXT: the Motive client, behind an interface, with a fake that lies the way the
real API lies (M14-FR2).

THE FAKE MUST MIRROR THE REAL API'S NULLS. HANDOFF-121 §13.7 records a debugging round
lost to a stub that returned `{}` where the endpoint returns `null`, and the kickoff names
that trap explicitly for this step. So `FakeMotiveClient` emits breadcrumbs with genuinely
absent fields — a vehicle with no location fix, a location with no speed — and the parser
below is what has to survive them. A fake that only ever produces complete records tests a
provider we do not have.

READ-ONLY, AND THAT IS A LEGAL BOUNDARY RATHER THAN A DESIGN PREFERENCE. D8 narrowed v1.0
§16: building, branding or registering an ELD stays excluded permanently; consuming a
fleet's own provider API read-only is what was permitted. There is no write method here and
there must never be one.

NO HISTORY BACKFILL. The kickoff excludes it and the exclusion is load-bearing: pulling a
fleet's past locations would manufacture arrivals for stops whose claims are already
settled, and a claim drafted from history nobody was watching is the opposite of the
`occurred_at` discipline this codebase keeps. Forward polling only; history is a later
decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Breadcrumb:
    """One provider-reported position. `recorded_at` is THEIR clock, deliberately.

    Comparing our clock against their breadcrumbs would drop records whenever the two
    disagree — and the disagreement is exactly what F12 records rather than hides
    elsewhere in this codebase. The watermark and the pack both use the provider's time,
    and the pack says whose it is.
    """

    vehicle_ref: str
    lat: float
    lon: float
    recorded_at: datetime
    speed_mps: float | None = None


class MotiveClient:
    """The real one. Not exercised by CI — see `make m14-poll-once`.

    The F-01 lesson is that a connector ships with an end-to-end proof against the real
    provider, OBSERVED, before its flag is eligible: F8 recorded every detention notice as
    sent while every one of them went to a container. A green suite over a faked provider
    is the same shape, so the make target exists to be run by hand with a real key and its
    output pasted into a handoff.
    """

    BASE = "https://api.gomotive.com"
    # v3 is what carries Vehicle Gateway positions
    PATH = "/v3/vehicle_locations"

    def __init__(self, api_key: str, *, timeout_s: float = 20.0) -> None:
        self._key = api_key
        self._timeout = timeout_s

    def vehicle_locations(self, since: datetime | None = None) -> list[Breadcrumb]:
        import httpx

        params = {"per_page": 100}
        if since is not None:
            params["start_time"] = since.astimezone(UTC).isoformat()
        resp = httpx.get(
            f"{self.BASE}{self.PATH}",
            headers={"X-Api-Key": self._key, "Accept": "application/json"},
            params=params,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return parse_vehicle_locations(resp.json())


def parse_vehicle_locations(payload: dict | list | None) -> list[Breadcrumb]:
    """Tolerant by design: every field below has been seen absent or null.

    A provider response is not ours to assume the shape of. Anything without the three
    facts a ping needs — which vehicle, where, and when — is DROPPED rather than
    defaulted, because a breadcrumb with a guessed position is a false arrival and this
    module's output is an invoice.
    """
    if not payload:
        return []
    rows = payload.get("vehicle_locations", []) if isinstance(payload, dict) else payload
    out: list[Breadcrumb] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        vehicle = (row.get("vehicle") or {}) if isinstance(row.get("vehicle"), dict) else {}
        ref = vehicle.get("id") or row.get("vehicle_id")
        loc = (
            (row.get("current_location") or {})
            if isinstance(row.get("current_location"), dict)
            else {}
        )
        lat, lon = loc.get("lat"), loc.get("lon")
        stamp = loc.get("located_at") or row.get("located_at")
        if ref is None or lat is None or lon is None or not stamp:
            continue
        try:
            when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        speed = loc.get("speed")
        out.append(
            Breadcrumb(
                vehicle_ref=str(ref),
                lat=float(lat),
                lon=float(lon),
                recorded_at=when,
                # Motive reports mph; F3 speaks m/s. A unit left unconverted is the
                # quietest wrong number available — it never looks absurd, it just makes
                # every movement check wrong by 2.24.
                speed_mps=(float(speed) * 0.44704) if speed is not None else None,
            )
        )
    return out


class FakeMotiveClient:
    """The test double, and it is deliberately awkward.

    It emits the shapes the real endpoint emits: a row whose `current_location` is null,
    a row with no vehicle, a location with no speed. `parse_vehicle_locations` has to
    survive all of them, because the day it does not is a poll that crashes a worker
    against a real fleet.
    """

    def __init__(self, pages: list[list[dict]] | None = None) -> None:
        self._pages = list(pages or [])
        self.calls: list[datetime | None] = []

    def vehicle_locations(self, since: datetime | None = None) -> list[Breadcrumb]:
        self.calls.append(since)
        payload = self._pages.pop(0) if self._pages else []
        return parse_vehicle_locations({"vehicle_locations": payload})

    @staticmethod
    def row(vehicle_ref: str, lat: float, lon: float, when: datetime, speed_mph=None) -> dict:
        return {
            "vehicle": {"id": vehicle_ref},
            "current_location": {
                "lat": lat,
                "lon": lon,
                "located_at": when.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                "speed": speed_mph,
            },
        }
