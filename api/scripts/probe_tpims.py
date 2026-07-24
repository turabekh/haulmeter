"""AI-CONTEXT: probe the MAASTO TPIMS state feeds (PRD §12) — `make probe-tpims`.
Reports reachability + whether each URL returns spec-shaped JSON (a MAASTO V2.2 row
carries siteId). The endpoint registry below is transcribed from the authoritative
WisDOT/TOPS-Lab developer page (single source of truth):
  https://transportal.cee.wisc.edu/tpims/parking-data-devs.html
Only 4 of the 8 non-IL states publish a public feed URL (IN/KY/MN/OH); the other
four (IA/KS/MI/WI) are registration-gated (email/form) and expose NO public URL, so
they can't be probed — they're listed here so the gap is visible, not forgotten.
http:// is fetched fine by httpx; the real "allowlist" is the data_sources config
registry (only admin-set URLs are ingested), so add a feed to config ONLY when this
probe reports LIVE spec-shaped. Not run in CI. No DB writes.
"""

import httpx

# State -> {feed: url} for every state that publishes a PUBLIC feed URL. IL is
# already live (Travel Midwest) and omitted; these are the expansion candidates.
PROBES = {
    "IN": {
        "dynamic": "https://content.trafficwise.org/json/tpims.json",
        "static": "https://content.trafficwise.org/json/rest_area.json",
    },
    "KY": {
        "dynamic": "http://www.trimarc.org/dat/tpims/TPIMS_Dynamic.json",
        "static": "http://www.trimarc.org/dat/tpims/TPIMS_Static.json",
    },
    "MN": {
        "dynamic": "http://iris.dot.state.mn.us/iris/TPIMS_dynamic",
        "static": "http://iris.dot.state.mn.us/iris/TPIMS_static",
    },
    "OH": {
        "dynamic": "http://ipsens.webhop.biz/ODOT/MaastoDataFeeds/TPIMS/Dynamic",
        "static": "http://ipsens.webhop.biz/ODOT/MaastoDataFeeds/TPIMS/Static",
    },
}

# States that gate their feed behind registration — no public URL to probe. Kept
# here so a future session knows exactly how to obtain them (contact per dev page).
REGISTRATION_GATED = {
    "IA": "email dev@tsps.io to register",
    "KS": "registration form https://tpims.ksdot.gov/",
    "MI": "email GormanJ4@michigan.gov to register",
    "WI": "email Michael.Vanness@dot.wi.gov to register",
}


def _rows(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("sites") or []
    return []


def probe(name: str, url: str) -> None:
    try:
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
    except Exception as exc:  # noqa: BLE001 — a probe reports every failure mode
        print(f"  {name}: ERROR {type(exc).__name__}: {str(exc)[:60]} -> unreachable")
        return
    ct = resp.headers.get("content-type", "")[:30]
    try:
        rows = _rows(resp.json())
    except Exception:  # noqa: BLE001
        print(f"  {name}: HTTP {resp.status_code} ct={ct} -> not JSON, skip")
        return
    spec = bool(rows) and isinstance(rows[0], dict) and "siteId" in rows[0]
    verdict = "LIVE spec-shaped (config it)" if spec else "JSON but not spec-shaped, skip"
    print(f"  {name}: HTTP {resp.status_code} ct={ct} rows={len(rows)} -> {verdict}")


def main() -> None:
    print("TPIMS probe (config a feed only when it reports LIVE spec-shaped):")
    for state, feeds in PROBES.items():
        for feed, url in feeds.items():
            probe(f"{state} {feed:7}", url)
    print("Registration-gated states (no public URL — obtain then re-probe):")
    for state, how in REGISTRATION_GATED.items():
        print(f"  {state}: {how}")


if __name__ == "__main__":
    main()
