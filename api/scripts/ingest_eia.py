"""AI-CONTEXT: manual EIA regional diesel ingest (PRD §12, M1-FR5) — `make
ingest-eia`. Pulls EIA's free weekly On-Highway Diesel retail average per PADD
region (national + PADD1..5) and upserts the M7 regional baseline that backs the
map's fuel badge until a network feed or a crowd report (M7-FR5) gives a real
per-station price. Not run in CI. Needs a free EIA API key (https://www.eia.gov/
opendata/ -> "Register") in infra/.env as EIA_API_KEY. Pass a JSON file path to
ingest a saved/fixture payload instead of calling the API (works with no key).
Run: make ingest-eia   (or python -m scripts.ingest_eia path/to/payload.json)
"""

import json
import os
import sys

import db_registry

db_registry.import_all_models()

from app.core.db import SessionLocal  # noqa: E402
from app.modules.m07_fuel import public as m7  # noqa: E402

EIA_URL = "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
DUOAREAS = ["NUS", "R10", "R20", "R30", "R40", "R50"]  # US + PADD1..5
PRODUCT = "EPD2D"  # No. 2 Diesel (on-highway retail)


def fetch(api_key: str) -> dict:
    import httpx

    params = [
        ("api_key", api_key),
        ("frequency", "weekly"),
        ("data[0]", "value"),
        ("facets[product][]", PRODUCT),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "desc"),
        ("length", "300"),
    ]
    params += [("facets[duoarea][]", area) for area in DUOAREAS]
    resp = httpx.get(EIA_URL, params=params, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    if len(sys.argv) > 1:
        payload = json.loads(open(sys.argv[1]).read())
    else:
        key = os.environ.get("EIA_API_KEY")
        if not key:
            print(
                "EIA_API_KEY not set — get a free key at https://www.eia.gov/opendata/ "
                "and add it to infra/.env, or pass a JSON payload path."
            )
            return
        payload = fetch(key)

    db = SessionLocal()
    try:
        n = m7.ingest_eia_prices(db, payload)
        db.commit()
        print(f"EIA ingest — {n} regional diesel prices updated")
    finally:
        db.close()


if __name__ == "__main__":
    main()
