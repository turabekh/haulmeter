"""AI-CONTEXT: ingestion runners + belief precedence (PRD §12, condition A). TPIMS
dynamic flows into the M1 belief pipeline with real feed timestamps driving the
freshness badge; trustData=false readings are never recorded; and authoritative vs
crowd precedence is: fresh authoritative > fresh crowd > stale authoritative > stale
crowd. Live fetch is monkeypatched to committed fixtures — no network in CI.
"""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.foundation.f02_facility import public as facility
from app.foundation.f10_crowd import public as crowd

FIX = Path(__file__).parents[1] / "fixtures" / "ingest"


def _load(name: str):
    return json.loads((FIX / name).read_text())


def test_tpims_dynamic_writes_authoritative_belief_with_real_freshness(db, monkeypatch):
    import app.ingest.runners as runners

    monkeypatch.setattr(facility.ingest, "fetch_tpims", lambda _url: _load("tpims_static.json"))
    static_stats = runners.run_tpims_static(db, commit=False)
    assert static_stats.created == 3  # three WI sites become facilities

    monkeypatch.setattr(facility.ingest, "fetch_tpims", lambda _url: _load("tpims_dynamic.json"))
    now = datetime(2026, 7, 22, 3, 40, tzinfo=UTC)
    res = runners.run_tpims_dynamic(db, now=now, commit=False)
    assert res == {"applied": 2, "skipped": 1}  # site3 trustData=false is skipped

    site1 = facility.facility_for_source(db, facility.SourceKind.tpims, "WI00094IS0024700ERSTARE01")
    belief = crowd.get_belief(db, site1.id, crowd.SignalType.parking_fullness)
    assert belief is not None
    assert belief.value["status"] == "some"
    # the badge's freshness is the REAL TPIMS timestamp, not ingest time (§11.7)
    assert belief.freshest_at == datetime(2026, 7, 22, 3, 35, tzinfo=UTC)

    site3 = facility.facility_for_source(db, facility.SourceKind.tpims, "WI00090IS0012000WRSTARE03")
    # trustData=false -> never recorded, never presented as fresh truth (condition A)
    assert crowd.get_belief(db, site3.id, crowd.SignalType.parking_fullness) is None


def test_tpims_il_unknown_untrusted_produce_no_belief(db, monkeypatch):
    # real IL rows: 2 usable (full + Low->some) become beliefs; 3 "Unknown" rows —
    # including one with trustData=true — produce NO belief (§11.7 / condition A).
    import app.ingest.runners as runners

    monkeypatch.setattr(facility.ingest, "fetch_tpims", lambda _u: _load("tpims_il_static.json"))
    static_stats = runners.run_tpims_static(db, commit=False)
    assert static_stats.created == 5  # five IL sites (no NTAD in the test db -> no dedupe here)

    monkeypatch.setattr(facility.ingest, "fetch_tpims", lambda _u: _load("tpims_il_dynamic.json"))
    now = datetime(2026, 7, 23, 9, 0, tzinfo=UTC)
    res = runners.run_tpims_dynamic(db, now=now, commit=False)
    assert res == {"applied": 2, "skipped": 3}

    full = facility.facility_for_source(db, facility.SourceKind.tpims, "IL00074IW006200004")
    fb = crowd.get_belief(db, full.id, crowd.SignalType.parking_fullness)
    assert fb.value["status"] == "full"
    # freshness is the REAL feed timestamp, not ingest time (§11.7)
    assert fb.freshest_at == datetime(2026, 7, 23, 8, 52, 25, tzinfo=UTC)

    low = facility.facility_for_source(db, facility.SourceKind.tpims, "IL00074IE006200001")
    lb = crowd.get_belief(db, low.id, crowd.SignalType.parking_fullness)
    assert lb.value["status"] == "some" and lb.value["available"] == facility.LOW  # never a number

    for sid in ("IL00074IE011400005", "IL00074IE015600037", "IL00055IS010400024"):
        fac = facility.facility_for_source(db, facility.SourceKind.tpims, sid)
        assert crowd.get_belief(db, fac.id, crowd.SignalType.parking_fullness) is None


def test_crowd_report_still_applies_over_an_unknown_tpims_site(db, monkeypatch):
    # B6 precedence: an "Unknown" TPIMS row leaves no belief; a driver's later crowd
    # report must still form one (no phantom authoritative belief blocks it).
    import app.ingest.runners as runners
    from app.foundation.f01_identity import public as identity

    monkeypatch.setattr(facility.ingest, "fetch_tpims", lambda _u: _load("tpims_il_static.json"))
    runners.run_tpims_static(db, commit=False)
    monkeypatch.setattr(facility.ingest, "fetch_tpims", lambda _u: _load("tpims_il_dynamic.json"))
    runners.run_tpims_dynamic(db, now=datetime(2026, 7, 23, 9, 0, tzinfo=UTC), commit=False)

    # an "Unknown" TPIMS row leaves no belief
    fac = facility.facility_for_source(db, facility.SourceKind.tpims, "IL00074IE015600037")
    assert crowd.get_belief(db, fac.id, crowd.SignalType.parking_fullness) is None

    drv = identity.register_account(db, "il-driver@example.com", "pw-123456")
    now = datetime(2026, 7, 23, 9, 5, tzinfo=UTC)
    crowd.submit(
        db,
        drv.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "empty"},
        submitted_at=now,
        award=False,
    )
    crowd.update_belief(db, fac.id, crowd.SignalType.parking_fullness, as_of=now)
    b = crowd.get_belief(db, fac.id, crowd.SignalType.parking_fullness)
    assert b is not None and b.value["status"] == "empty"  # crowd works over an Unknown site


def _sub(db, fac_id, status, minutes_ago, authoritative, now):
    db.add(
        crowd.Submission(
            facility_id=fac_id,
            account_id=None,
            signal_type=crowd.SignalType.parking_fullness,
            value={"status": status},
            presence_proven=True,
            authoritative=authoritative,
            trust_weight=5.0 if authoritative else 1.0,
            submitted_at=now - timedelta(minutes=minutes_ago),
        )
    )
    db.flush()


def test_fresh_authoritative_beats_fresh_crowd(db):
    now = datetime(2026, 7, 22, 4, 0, tzinfo=UTC)
    fac = facility.create_facility(db, facility.FacilityType.rest_area, "Site", 43.0, -89.0)
    _sub(db, fac.id, "empty", 2, True, now)  # fresh authoritative
    _sub(db, fac.id, "full", 3, False, now)  # fresh crowd
    result = crowd.aggregate_belief(db, fac.id, crowd.SignalType.parking_fullness, now)
    assert result.value["status"] == "empty"  # authoritative wins at equal freshness


def test_fresh_crowd_beats_stale_authoritative(db):
    now = datetime(2026, 7, 22, 4, 0, tzinfo=UTC)
    fac = facility.create_facility(db, facility.FacilityType.rest_area, "Site2", 44.0, -90.0)
    _sub(db, fac.id, "empty", 120, True, now)  # stale authoritative (2h > 30m fresh cutoff)
    _sub(db, fac.id, "full", 2, False, now)  # fresh crowd
    result = crowd.aggregate_belief(db, fac.id, crowd.SignalType.parking_fullness, now)
    assert result.value["status"] == "full"  # freshness dominates across the boundary


def test_osm_runner_ingests_from_geojson_file(db, tmp_path):
    import app.ingest.runners as runners

    path = tmp_path / "osm.geojson"
    path.write_text(json.dumps(_load("osm_filtered.geojson")))
    stats = runners.run_osm(db, str(path), commit=False)
    assert stats.created == 3  # rest area + hgv parking lot + hgv fuel


def test_eia_runner_upserts_regional_prices_from_fixture(db, monkeypatch):
    # the weekly worker job path — live fetch monkeypatched to the committed fixture
    import app.ingest.runners as runners
    from app.modules.m07_fuel import public as m7

    monkeypatch.setattr(runners.m7, "fetch_eia", lambda _key: _load("eia_diesel.json"))
    res = runners.run_eia(db, commit=False)
    assert res == {"regions": 6}  # US + PADD1..5 (California + gasoline rows dropped)
    padd2 = db.get(m7.RegionalFuelPrice, "PADD2")
    assert padd2.gross_cents_per_gal == 378 and padd2.week_of == date(2026, 7, 14)
