"""AI-CONTEXT: A9 §5 — dedupe at density, measured on the nine-state registry.

§5 predicts "geohash-7 blocking with 0.4 name similarity will produce more false merges
once metros are dense". **The fear is right and the stated cause is wrong**, which the
data says plainly:

· NOT ONE of the 1,078 merges in the registry happened beyond the 150 m co-location
  radius. A geohash-7 cell is ~153 m, so the name path was already bounded by its own
  blocking and could never merge two Pilots a kilometre apart.
· What it does instead is MISS. 191 pairs of live facilities sit within 60 m of each
  other with similar names and were never merged — "Flying J Travel Center" twice at
  3 m, "Blue Beacon Truck Wash #74" twice at 20 m — because a cell boundary runs
  between them. Every sampled pair was in a different block. Density makes that worse,
  not better: more sites, more boundaries.

So the blocking becomes a geography predicate (indexed since 0056). And because that
widens what is reachable, two guards come with it, both derived from the same audit:

· A PLACEHOLDER IS NOT EVIDENCE. 69 of those 191 pairs are two facilities both named
  "Rest Area" — a name this code wrote. Merging on `similarity('Rest Area','Rest Area')
  = 1.0` is merging on our own invention, the same defect `host_should_adopt_name`
  carried until this session.
· OPPOSITE CARRIAGEWAYS ARE NOT ONE PLACE. "Turnout Eastbound" and "Turnout Westbound"
  are 32 m apart at similarity 0.64; "Haywood County Rest Area, Ebl" and "…Wbl" are
  28 m at 0.81. Neither distance nor similarity separates them — the direction token
  does. And it is not hypothetical at the old radius: "I-80 EB (trucks Only)" and
  "I-80 WB (trucks Only)" sit 149 m apart at 0.74.
"""

from app.foundation.f02_facility import public as facility
from app.foundation.f02_facility.domain import service as svc

# AI-CONTEXT: these offsets are MEASURED against the real geohash, not chosen. At
# (43.0731, -89.4012) a geohash-7 boundary falls exactly 20 m north — `dp8mj9h` becomes
# `dp8mj9k`. So SAME_CELL_M sits inside one cell and STRADDLE_M crosses a boundary, and
# each test below exercises the path it names instead of passing by accident. The first
# draft used 3 m for the boundary case and went green against the OLD code, proving
# nothing — a straddling pair has to actually straddle.
MADISON = (43.0731, -89.4012)
SAME_CELL_M = 10
STRADDLE_M = 20


def _at(db, name, lat, lon, ftype=None):
    return facility.create_facility(
        db, ftype or facility.FacilityType.truck_stop, name, lat, lon
    )


def _metres_north(lat, lon, m):
    return (lat + m / 111_320.0, lon)


def test_a_geohash_boundary_no_longer_hides_a_duplicate(db):
    """The measured defect: 191 live pairs within 60 m with similar names, unmerged,
    every sampled one in a different geohash cell. "Flying J Travel Center" twice, 3 m
    apart, is two pins for one place on a driver's map."""
    _at(db, "Flying J Travel Center", *MADISON)
    lat, lon = _metres_north(*MADISON, STRADDLE_M)  # different cell, 20 m away
    found = facility.find_duplicate_candidates(db, "Flying J Travel Center", lat, lon)
    assert [f.name for f in found] == ["Flying J Travel Center"]


def test_two_placeholder_names_are_not_evidence_of_anything(db):
    """69 of the 191 are two facilities both called "Rest Area" — a name this code
    wrote. `similarity` says 1.0 and it means nothing."""
    _at(db, "Rest Area", *MADISON, ftype=facility.FacilityType.rest_area)
    lat, lon = _metres_north(*MADISON, SAME_CELL_M)  # same cell: today this MERGES
    assert facility.find_duplicate_candidates(db, "Rest Area", lat, lon) == []


def test_an_unnamed_feature_still_merges_into_a_NAMED_one(db):
    """The other half of that rule, so it does not overreach: only when NEITHER side
    has a real name is there no evidence. A nameless feature beside a named one is the
    case `host_should_adopt_name` exists for."""
    _at(db, "Lyndon Station Rest Area", *MADISON, ftype=facility.FacilityType.rest_area)
    lat, lon = _metres_north(*MADISON, SAME_CELL_M)
    found = facility.find_duplicate_candidates(db, "Lyndon Station Rest Area 9", lat, lon)
    assert [f.name for f in found] == ["Lyndon Station Rest Area"]


def test_opposite_carriageways_are_two_places(db):
    """Real rows, real distance, real similarity: "Turnout Eastbound" and "Turnout
    Westbound" are 32 m apart at 0.64. Merging them takes a rest area off the map for
    every driver heading the other way."""
    _at(db, "Turnout Eastbound", *MADISON, ftype=facility.FacilityType.rest_area)
    lat, lon = _metres_north(*MADISON, SAME_CELL_M)  # same cell: today this MERGES
    assert facility.find_duplicate_candidates(db, "Turnout Westbound", lat, lon) == []


def test_the_same_carriageway_spelled_differently_is_one_place(db):
    """The guard must not become "any direction token blocks a merge". "Wood I-75 NB"
    and "Wood Interstate 75 NB" are 49 m apart and are one rest area."""
    _at(db, "Wood I-75 NB", *MADISON, ftype=facility.FacilityType.rest_area)
    lat, lon = _metres_north(*MADISON, 49)  # different cell — the miss AND the guard
    found = facility.find_duplicate_candidates(db, "Wood Interstate 75 NB", lat, lon)
    assert [f.name for f in found] == ["Wood I-75 NB"]


def test_one_side_naming_a_direction_is_not_a_conflict(db):
    """"Homestead SB" and "Homestead" are 18 m apart. One says which way, the other
    does not; that is not a disagreement."""
    _at(db, "Homestead", *MADISON, ftype=facility.FacilityType.rest_area)
    lat, lon = _metres_north(*MADISON, SAME_CELL_M)
    assert [f.name for f in facility.find_duplicate_candidates(db, "Homestead SB", lat, lon)] == [
        "Homestead"
    ]


def test_direction_is_read_from_the_forms_the_data_actually_uses():
    # every form in the sampled registry rows: bare, bounded, and the DOT "bl" suffix
    assert svc.direction_of("Turnout Eastbound") == "E"
    assert svc.direction_of("Haywood County Rest Area, Ebl") == "E"
    assert svc.direction_of("Wood I-75 NB") == "N"
    assert svc.direction_of("I-80 WB (trucks Only)") == "W"
    assert svc.direction_of("Ladysmith Safety Rest Area Southbound") == "S"
    assert svc.direction_of("Flying J Travel Center") is None
    # a direction must be a WORD, not a letter inside one — "Sbarro" is not southbound
    assert svc.direction_of("Sbarro Truck Plaza") is None


def test_a_distant_lookalike_is_still_two_places(db):
    """The old blocking bounded the name path to a ~153 m cell by accident. The radius
    is explicit now and TIGHTER, because the audit showed identical-name pairs collapse
    from 91% of candidates within 30 m to 22% beyond 90 m."""
    _at(db, "Pilot Travel Center", *MADISON)
    lat, lon = _metres_north(*MADISON, 140)
    assert facility.find_duplicate_candidates(db, "Pilot Travel Center", lat, lon) == []


def test_a_bare_direction_word_still_separates_two_carriageways(db):
    """Caught by DRY-RUNNING the repair over the real registry, not by a test: the first
    version of this rule was about to merge "Dale City Truck-Only Safety Rest Area
    South" into "…North".

    `direction_of` deliberately ignores a bare "North"/"South", because "North Platte
    Truck Stop" is a place and not a carriageway. That is right on ONE name and wrong on
    a PAIR: when two names are identical apart from the direction word, the word is
    doing the distinguishing, whatever form it takes."""
    _at(db, "Dale City Truck-Only Safety Rest Area North", *MADISON,
        ftype=facility.FacilityType.rest_area)
    lat, lon = _metres_north(*MADISON, SAME_CELL_M)
    assert (
        facility.find_duplicate_candidates(
            db, "Dale City Truck-Only Safety Rest Area South", lat, lon
        )
        == []
    )


def test_a_shared_direction_word_is_not_a_disagreement(db):
    # the guard must not fire on two rows that agree — "North Platte" twice is one place
    _at(db, "North Platte Truck Stop", *MADISON)
    lat, lon = _metres_north(*MADISON, SAME_CELL_M)
    found = facility.find_duplicate_candidates(db, "North Platte Truck Stop", lat, lon)
    assert [f.name for f in found] == ["North Platte Truck Stop"]


def test_two_numbered_facilities_are_two_places(db):
    """Also from the dry run: "Nhs Rest Stop Or Truck Facility 7" was about to merge into
    "…17". A number in a facility name is an identifier, and 7 is not 17 — trigram
    similarity cannot see that, because it is one character of difference in a long
    string."""
    _at(db, "Nhs Rest Stop Or Truck Facility 17", *MADISON,
        ftype=facility.FacilityType.rest_area)
    lat, lon = _metres_north(*MADISON, SAME_CELL_M)
    assert (
        facility.find_duplicate_candidates(db, "Nhs Rest Stop Or Truck Facility 7", lat, lon)
        == []
    )


def test_the_same_number_written_differently_is_one_place(db):
    # "Hurley Rest Area 103" and "Rest Area #103" are one rest area, and the number is
    # what says so — the guard is about DISAGREEMENT, not about the presence of digits
    _at(db, "Rest Area #103", *MADISON, ftype=facility.FacilityType.rest_area)
    lat, lon = _metres_north(*MADISON, SAME_CELL_M)
    found = facility.find_duplicate_candidates(db, "Hurley Rest Area 103", lat, lon)
    assert [f.name for f in found] == ["Rest Area #103"]
