"""AI-CONTEXT: the map's query count must not grow with the number of facilities.

Owner report: "facilities not loading instantly." The overlay was N+1 three times over
— a coordinate read, a crowd-status read and a fuel-badge read, each once PER PIN — so
a viewport issued hundreds of round trips to draw a screen whose payload was 14 KB.
Measured before the fix: **2,155 queries** to return a statewide pan, which discarded
every pin it had built and answered with 146 cluster chips.

These tests assert the SHAPE of the cost, not a magic number. A budget like
`assert queries < 40` passes for the wrong reason the moment someone reduces the
fixture; what matters is that doubling the facilities does not double the queries.
That is the property N+1 violates and a batched read preserves.
"""

import pytest
from sqlalchemy import event

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.modules.m01_map import public as m1

DALLAS = (32.7767, -96.7970)


@pytest.fixture
def account(db):
    return identity.register_account(db, "budget@example.com", "pw-123456")


@pytest.fixture
def count_queries(db):
    counter = {"n": 0}
    bind = db.get_bind()

    def _on_execute(*_args, **_kwargs):
        counter["n"] += 1

    event.listen(bind, "before_cursor_execute", _on_execute)
    yield counter
    event.remove(bind, "before_cursor_execute", _on_execute)


def _seed(db, n: int, lat_step: float = 0.001):
    for i in range(n):
        facility.create_facility(
            db,
            facility.FacilityType.truck_stop,
            f"Stop {i}",
            DALLAS[0] + i * lat_step,
            DALLAS[1],
        )
    db.flush()


def _overlay(db, account_id, cap=1000):
    return m1.map_overlay_view(db, account_id, *DALLAS, 60000, cap=cap)


def test_overlay_query_count_does_not_grow_with_facility_count(db, account, count_queries):
    """The N+1 guard. Ten facilities and forty must cost about the same number of
    queries — if the second is four times the first, a per-pin read has come back."""
    _seed(db, 10)
    count_queries["n"] = 0
    _overlay(db, account.id)
    ten = count_queries["n"]

    _seed(db, 30, lat_step=0.0011)
    count_queries["n"] = 0
    view = _overlay(db, account.id)
    forty = count_queries["n"]

    assert view["total"] >= 40  # the fixture really did grow
    assert forty <= ten + 3, f"query count scaled with facilities: {ten} -> {forty}"


def test_a_clustered_answer_does_not_build_the_pins_it_discards(db, account, count_queries):
    """The sharpest half. A clustered response carries counts and centres — never a
    pin — so the expensive per-pin construction must not happen at all. This was the
    2,155-query case: every pin built in full, then thrown away."""
    _seed(db, 40)
    count_queries["n"] = 0
    view = _overlay(db, account.id, cap=5)

    assert view["clustered"] is True
    assert view["pins"] == []
    assert view["total"] >= 40
    assert count_queries["n"] <= 12, f"clustering issued {count_queries['n']} queries"


def test_clustered_and_pinned_answers_agree_on_the_total(db, account):
    """The refactor split one path into two — pins under the cap, clusters over it —
    and the two must still be counting the same facilities."""
    _seed(db, 12)
    pinned = _overlay(db, account.id, cap=1000)
    clustered = _overlay(db, account.id, cap=3)

    assert pinned["clustered"] is False
    assert clustered["clustered"] is True
    assert pinned["total"] == clustered["total"]
    assert sum(c.count for c in clustered["clusters"]) == pinned["total"]
