"""AI-CONTEXT: probe unverified TPIMS state feeds (PRD §12) — `make probe-tpims`.
Reports reachability + whether each URL returns spec-shaped JSON (a MAASTO V2.2 row
carries siteId). Both KY and MN publish over http://, which httpx fetches fine — the
"allowlist" is the data_sources config registry (only admin-set URLs are fetched), so
add a feed to config ONLY when this probe reports LIVE. Not run in CI. No DB writes.
"""

import httpx

PROBES = {
    "KY dynamic": "http://www.trimarc.org/dat/tpims/TPIMS_Dynamic.json",
    "KY static ": "http://www.trimarc.org/dat/tpims/TPIMS_Static.json",
    "MN dynamic": "http://iris.dot.state.mn.us/iris/TPIMS_dynamic",
    "MN static ": "http://iris.dot.state.mn.us/iris/TPIMS_static",
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
        print(f"  {name}: ERROR {type(exc).__name__}: {str(exc)[:70]} -> unreachable")
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
    print("TPIMS probe (http:// is fetched by httpx; config a feed only when LIVE):")
    for name, url in PROBES.items():
        probe(name, url)


if __name__ == "__main__":
    main()
