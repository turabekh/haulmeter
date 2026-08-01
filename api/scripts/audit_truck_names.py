"""AI-CONTEXT: what the NAME rule alone would admit from an extract, for eyeballing
before you load a state. `python -m scripts.audit_truck_names /app/data/osm/iowa.geojson`

`osm_serves_trucks` has three signals. Two are tags and cannot really be wrong. The
third is "trucks are named in the business name", and it carries about two thirds of
the genuine finds — so it cannot be dropped, and it is the only one that can admit
something absurd.

It already has: `fleet` reads like the strongest possible term and was the weakest one
measured, because 13 of its 14 Wisconsin matches are "Fleet Farm", a regional retail
chain whose CAR WASH would have entered the registry as a truck repair facility. A
term that is right in one state can be a shopping centre in another, and A9 takes this
to fifty of them.

This prints the list a human reads in thirty seconds. It asserts nothing and decides
nothing — the point is that the check is cheap enough to actually happen, because the
alternative is trusting a term list against 49 states nobody looked at.
"""

import collections
import json
import sys

import db_registry

db_registry.import_all_models()

from app.foundation.f02_facility import public as facility  # noqa: E402
from app.foundation.f02_facility.domain.ingest import adapters  # noqa: E402


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "/app/data/osm/wisconsin.geojson"
    records = facility.parse_osm(json.load(open(path)))
    repair = [r for r in records if r.facility_type is facility.FacilityType.repair]
    # a record admitted by a TAG is not interesting here — `shop=truck_repair` means
    # what it says. Only the name-only admits can be a garden centre.
    by_name = [
        r
        for r in repair
        if not adapters._osm_truck_explicit(r.raw_payload)
        and not adapters._osm_hgv(r.raw_payload)
    ]
    terms = collections.Counter()
    for rec in by_name:
        lowered = rec.name.lower()
        for term in adapters._TRUCK_NAME_TERMS:
            if term in lowered:
                terms[term] += 1

    print(f"{path}")
    print(f"  parsed {len(records)} · repair {len(repair)} · admitted by NAME alone {len(by_name)}")
    print(f"  terms firing: {dict(terms.most_common())}")
    print("  --- names to eyeball (a retail chain here is a defect) ---")
    for rec in sorted({r.name for r in by_name}):
        print(f"    {rec}")


if __name__ == "__main__":
    main()
