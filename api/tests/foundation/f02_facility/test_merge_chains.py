"""AI-CONTEXT: a merge must always land on the CANONICAL row, never on a shadow.

Measured: 146 rows locally and 149 on the box are merged into a facility that is
itself merged. Reads survive it because `resolve_canonical` walks the chain — and the
fact that it carries a `seen` set means somebody already knew a CYCLE was reachable
from here. Nothing prevented either; `merge_facilities` wrote whatever it was handed.

A chain is not fatal, it is a tax: every read of one of those ids walks it. A cycle IS
fatal, and the only thing standing between the two is that nobody has yet merged A into
B and then B into A — which `/admin/facilities/{id}/merge` accepts today.

Fixed in `merge_facilities` rather than in its callers, because there are four of them
(the ingest pipeline, the admin route, and two repair scripts) and a rule enforced in
three places out of four is the defect this project keeps paying for.
"""

import pytest

from app.foundation.f02_facility import public as facility

SEATTLE = (47.6062, -122.3321)


def _fac(db, name, lat_offset=0.0):
    return facility.create_facility(
        db, facility.FacilityType.truck_stop, name, SEATTLE[0] + lat_offset, SEATTLE[1]
    )


def test_merging_into_a_shadow_lands_on_the_real_site(db):
    """A merged into B, then C merged into A. C must point at B — the site that still
    renders — not at A, which is a row nothing shows."""
    b = _fac(db, "Flying J Travel Center")
    a = _fac(db, "Pilot Travel Center", 0.001)
    c = _fac(db, "Roadside Diesel", 0.002)
    facility.merge_facilities(db, b, a)

    facility.merge_facilities(db, a, c)  # asked to merge into the shadow

    assert c.merged_into_id == b.id, "a merge must land on the canonical row"
    assert facility.resolve_canonical(db, c.id).id == b.id


def test_a_cycle_is_refused_rather_than_written(db):
    """A into B, then B into A. `resolve_canonical` has a `seen` guard, so a cycle
    would not hang — it would answer with whichever row the loop broke on, which is
    worse: a wrong answer delivered confidently."""
    a = _fac(db, "Speedco")
    b = _fac(db, "Speedco Truck Lube", 0.001)
    facility.merge_facilities(db, b, a)

    with pytest.raises(ValueError):
        facility.merge_facilities(db, a, b)


def test_merging_a_row_into_itself_is_refused(db):
    a = _fac(db, "Loves Travel Stop")
    with pytest.raises(ValueError):
        facility.merge_facilities(db, a, a)


def test_an_existing_chain_can_be_flattened(db):
    """The 149 rows already on the box. Flattening is not cosmetic: every read of a
    chained id walks it, and the walk is the thing that grows as A9 makes more merges."""
    b = _fac(db, "Ta Travel Center")
    a = _fac(db, "Ta", 0.001)
    c = _fac(db, "Ta Truck Service", 0.002)
    facility.merge_facilities(db, b, a)
    c.merged_into_id = a.id  # written the old way, before the rule existed
    c.status = facility.FacilityStatus.merged
    db.flush()

    assert facility.flatten_merge_chains(db) == 1
    assert c.merged_into_id == b.id
    assert facility.flatten_merge_chains(db) == 0  # idempotent
