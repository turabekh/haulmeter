"""AI-CONTEXT: address → coordinates, which F2 has never had (§23 entry 67).

The rate-con parser extracts `receiver_address` — "8450 Lakeside Ave, Columbus, OH
43228" on a real contract — and the import sheet discarded it and filed the dock at a
**hardcoded Dallas coordinate**. Every load created that way therefore armed its
geofence 1,500 km from the dock, so ENTER could never fire for a real delivery: no
arrival, no on-time proof, no detention clock, no ON_SITE. It is also why the dedup
rule over-matched, since every sheet-created facility shared one geohash block and only
name similarity separated them.

Mapbox rather than a new vendor: the project already depends on it for map tiles and
already carries a token, so this adds a call, not a dependency.

The transport is a MODULE-LEVEL function on purpose — the same seam F9 uses — so tests
monkeypatch `_mapbox_forward` and never touch the network. A geocoder in a test suite
that reaches the internet is a test suite that fails on a train.
"""

from dataclasses import dataclass

from app.core.config import get_settings

_MAPBOX_URL = "https://api.mapbox.com/search/geocode/v6/forward"


@dataclass(frozen=True)
class GeocodedPlace:
    """One candidate location, with the geocoder's OWN wording for it.

    `label` is what Mapbox matched, not what the driver typed. §11.7's discipline
    applies to a geocoder exactly as it does to a crowd report: the screen shows who
    said what, so a driver can see that "8450 Lakeside Ave" resolved to something
    different before they accept it.
    """

    lat: float
    lon: float
    label: str


def _mapbox_forward(query: str, token: str, limit: int) -> dict:
    import httpx

    resp = httpx.get(
        _MAPBOX_URL,
        # AI-CONTEXT: no `types` filter. v6 rejected the v5 spelling with a 422 —
        # `poi` does not exist in this API — and narrowing it buys nothing anyway: a
        # dock may resolve as a street address, a place or a locality depending on how
        # the contract wrote it, and any of those is a better coordinate than none.
        params={"q": query, "access_token": token, "limit": limit},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


_MAPBOX_REVERSE_URL = "https://api.mapbox.com/search/geocode/v6/reverse"


def _mapbox_reverse(lat: float, lon: float, token: str) -> dict:
    import httpx

    resp = httpx.get(
        _MAPBOX_REVERSE_URL,
        params={"latitude": lat, "longitude": lon, "access_token": token, "limit": 1},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def locality(lat: float, lon: float) -> str | None:
    """Where a coordinate is, in the words a driver uses — "Columbus, OH" (§23 entry 76).

    AI-CONTEXT: the registry can hold two facilities with the SAME NAME, legitimately —
    a chain with a warehouse in two cities, or a duplicate left by an earlier defect.
    The confirm sheet asks "is this the same place?" and rendered candidates by name
    alone, so a real driver was offered "Metro Market Warehouse" twice with nothing to
    choose between. A question with two indistinguishable answers cannot be answered.

    Best-effort like `geocode`: no token, no network, or nothing recognisable returns
    None and the row simply shows what it always did.
    """
    token = get_settings().mapbox_token
    if not token:
        return None
    try:
        payload = _mapbox_reverse(lat, lon, token)
    except Exception:
        return None
    for feature in (payload or {}).get("features", []) or []:
        context = (feature.get("properties") or {}).get("context") or {}
        place = (context.get("place") or {}).get("name")
        region = (context.get("region") or {}).get("region_code") or (
            context.get("region") or {}
        ).get("name")
        if place and region:
            return f"{place}, {region}"
        if place:
            return str(place)
    return None


def geocode(address: str, limit: int = 3) -> list[GeocodedPlace]:
    """Best-effort. Returns [] rather than raising — an address we cannot place is a
    fact to show the driver, not an error that loses their rate con."""
    query = (address or "").strip()
    if not query:
        return []
    token = get_settings().mapbox_token
    if not token:
        # dev without a token, and CI. Saying "we could not place it" is honest; a
        # fabricated coordinate is what this module exists to stop.
        return []
    try:
        payload = _mapbox_forward(query, token, limit)
    except Exception:
        return []

    places: list[GeocodedPlace] = []
    for feature in (payload or {}).get("features", []) or []:
        props = feature.get("properties") or {}
        coords = props.get("coordinates") or {}
        lon, lat = coords.get("longitude"), coords.get("latitude")
        if lon is None or lat is None:
            geometry = feature.get("geometry") or {}
            pair = geometry.get("coordinates") or []
            if len(pair) == 2:
                lon, lat = pair[0], pair[1]
        if lon is None or lat is None:
            continue
        label = props.get("full_address") or props.get("name") or query
        places.append(GeocodedPlace(lat=float(lat), lon=float(lon), label=str(label)))
    return places
