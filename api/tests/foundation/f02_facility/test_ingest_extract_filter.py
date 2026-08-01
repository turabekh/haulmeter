"""AI-CONTEXT: the link between what the osmium extract PASSES and what the ingest
rules READ. Nothing tied the two together, and the gap was total: six of the eight
`_OSM_SERVICE_RULES` read tags the filter never let into the extract, so they had
never fired once. Measured before this was written — across the filtered Wisconsin
and Texas extracts on disk, `shop=tyres`, `shop=truck_repair`, `shop=truck_parts`
and `service:vehicle:*` appear ZERO times, and `amenity=car_wash` four times in all
of Texas.

A rule whose tag never reaches it is not a rule, it is a comment. These tests are
the mechanism that makes that state fail out loud: the keys are DISCOVERED by
running each rule against probe tags that record every lookup, so a rule that
starts reading a new tag tomorrow fails here rather than silently going dead.
"""

from app.foundation.f02_facility.domain.ingest import adapters


class _Probe:
    """Stands in for one tag's value and records what the rule compares it against —
    so the probe yields (key, value) PAIRS, not just keys. Comparing keys alone is
    not enough and the first draft of this file proved it: `amenity=car_wash` read as
    covered because the filter passed `amenity=truck_stop`, and the starved wash rule
    went unreported. A selector is a key AND a value."""

    def __init__(self, key: str, sink: set, matches: bool):
        self._key = key
        self._sink = sink
        self._matches = matches

    def __eq__(self, other):
        if isinstance(other, str):
            self._sink.add((self._key, other))
        return self._matches

    def __hash__(self):
        return 0

    def __str__(self):
        return ""


class _RecordingTags(dict):
    """Two probes are needed, not one: with a value that matches nothing an `or`
    chain evaluates every branch while an `and` chain stops at the first; with a
    value that matches everything it is the other way round. The union is what a
    rule actually reads."""

    def __init__(self, matches: bool, sink: set):
        super().__init__()
        self._matches = matches
        self._sink = sink
        self.keys_seen: set[str] = set()

    def get(self, key, default=None):
        self.keys_seen.add(key)
        return _Probe(key, self._sink, self._matches)


def _selectors_read_by(rule) -> tuple[set, set]:
    pairs: set = set()
    keys: set[str] = set()
    for matches in (True, False):
        probe = _RecordingTags(matches, pairs)
        try:
            rule(probe)
        except Exception:  # a probe a rule cannot handle still leaves its lookups
            pass
        keys |= probe.keys_seen
    return pairs, keys


def _filter_covers(key: str, value: str | None = None) -> bool:
    for k, values in adapters.OSM_EXTRACT_TAGS:
        if k != key:
            continue
        if not values or value is None or value in values:
            return True
    return False


def _rule_reaches_the_extract(rule) -> tuple[bool, list]:
    """A rule is fed if ANY selector it tests can arrive in the extract. Refinement
    lookups (a scale's `operator`/`brand`) are deliberately not required to be
    filter tags — they narrow a match the gating tag already made."""
    pairs, keys = _selectors_read_by(rule)
    if any(_filter_covers(k, v) for k, v in pairs):
        return True, sorted(pairs)
    if not pairs and any(_filter_covers(k) for k in keys):
        return True, sorted(keys)
    return False, sorted(pairs or keys)


def test_every_service_rule_reads_a_tag_the_extract_passes():
    """The defect that made this file exist. Six rules read tags the filter dropped,
    so a tire shop, a repair yard and a parts store could not enter the registry by
    any path — and every test of those rules passed, because a fixture hands the
    rule tags the extract would never have delivered."""
    uncovered = {}
    for rule, name in adapters._OSM_SERVICE_RULES:
        reached, selectors = _rule_reaches_the_extract(rule)
        if not reached:
            uncovered[name] = selectors
    assert uncovered == {}, f"service rules the extract starves: {uncovered}"


def test_every_type_rule_reads_a_tag_the_extract_passes():
    uncovered = {}
    for rule, ftype in adapters._OSM_TYPE_RULES:
        reached, selectors = _rule_reaches_the_extract(rule)
        if not reached:
            uncovered[ftype.value] = selectors
    assert uncovered == {}, f"type rules the extract starves: {uncovered}"


def test_hgv_gate_tags_all_reach_the_extract():
    """`_osm_hgv` reads `truck=yes` as well as `hgv` and `access=hgv`. The hand-kept
    filter passed the first two and not the third."""
    pairs, keys = _selectors_read_by(adapters._osm_hgv)
    for key, value in pairs:
        assert _filter_covers(key, value), f"_osm_hgv reads {key}={value}, which the extract drops"


def test_filter_args_render_as_osmium_selectors():
    args = adapters.osm_extract_filter_args()
    assert "nwr/highway=rest_area,services" in args
    assert "nwr/hgv" in args  # bare key: any value
    assert "nwr/shop=tyres,truck_repair,car_repair,truck_parts" in args
    assert all(a.startswith("nwr/") for a in args)


def test_makefile_delegates_to_the_rendered_list():
    """The Makefile must not carry its own copy of the tags. It had one, and that copy
    is what drifted from the rules — the whole failure this file exists to prevent.

    Mounted read-only at /repo by compose. A missing file FAILS rather than skips: a
    check that quietly reports nothing is the shape of defect this file is about."""
    from pathlib import Path

    path = Path("/repo/Makefile")
    assert path.exists(), "Makefile not mounted — this check cannot silently pass"
    extract = path.read_text().split("osm-extract:")[1].split("\n\n")[0]
    assert "osm_filter_args" in extract, "osm-extract must render the tag list, not hardcode it"
    assert "nwr/" not in extract, "a hand-kept tag list in the Makefile is the defect"
