"""AI-CONTEXT: E3.1 weigh stations on the map and the corridor.

Three things under test:

· **The layer is flag-gated and silent when off.** An un-activated layer contributes
  no pins, server-side — a driver never downloads a layer they have not been given,
  and the client is not left filtering something it should never have received.
· **A pin's status follows what the facility IS.** Reading parking fullness off a
  weigh station would render a status that means nothing about it.
· **"Unknown" is an honest state.** A scale nobody has passed recently reports no
  status rather than a guess (§11.7).
"""

from datetime import UTC, datetime

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f10_crowd import public as crowd
from app.foundation.f11_map import public as mapsvc
from app.foundation.f13_flags import public as flags
from app.modules.m01_map import public as m1

MADISON = (43.0700, -89.4000)
AHEAD = (43.2500, -89.4000)  # due north
T0 = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def _driver(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _scale(db, name="I-90 Weigh Station EB", coords=AHEAD, kind=None):
    return facility.create_facility(
        db, kind or facility.FacilityType.weigh_station, name, *coords
    )


def _activate(db):
    m1.register_module(db)
    flags.enable(db, m1.FLAG_KEY)
    flags.enable(db, m1.WEIGH_STATION_FLAG)


def _report(db, driver, fac, status, now=T0):
    location.arm_geofence(db, driver.id, fac.id)
    location.evaluate_ping(db, driver.id, *AHEAD, occurred_at=now)
    m1.submit_status(
        db, driver.id, fac.id, crowd.SignalType.weigh_station_status, {"status": status}, now
    )


# --- the flag gates the layer ---
def test_the_layer_is_silent_until_it_is_activated(db):
    m1.register_module(db)
    _scale(db)
    driver = _driver(db)

    pins = m1.map_overlay(db, driver.id, *MADISON, 50000, preset=m1.Preset.drive)
    assert [p for p in pins if p.facility_type == "weigh_station"] == []


def test_activating_the_flag_puts_scales_on_the_drive_preset(db):
    # Drive is the preset for moving forward, which is exactly when a scale matters
    _activate(db)
    _scale(db)
    driver = _driver(db)

    pins = m1.map_overlay(db, driver.id, *MADISON, 50000, preset=m1.Preset.drive)
    assert [p.facility_type for p in pins] == ["weigh_station"]


def test_the_flag_does_not_disturb_the_other_presets(db):
    _activate(db)
    _scale(db)
    facility.create_facility(db, facility.FacilityType.truck_stop, "Loves", *MADISON)
    driver = _driver(db)

    tonight = m1.map_overlay(db, driver.id, *MADISON, 50000, preset=m1.Preset.tonight)
    assert all(p.facility_type != "weigh_station" for p in tonight)


def test_a_commercial_scale_rides_the_same_layer(db):
    _activate(db)
    _scale(db, "CAT Scale at Pilot", kind=facility.FacilityType.scale)
    driver = _driver(db)

    pins = m1.map_overlay(db, driver.id, *MADISON, 50000, preset=m1.Preset.drive)
    assert [p.facility_type for p in pins] == ["scale"]


# --- a pin's status follows the facility kind ---
def test_a_weigh_station_pin_reads_the_weigh_station_signal(db):
    _activate(db)
    fac = _scale(db)
    driver = _driver(db)
    _report(db, driver, fac, "closed")
    crowd.update_belief(db, fac.id, crowd.SignalType.weigh_station_status, as_of=T0)

    pins = m1.map_overlay(db, driver.id, *MADISON, 50000, preset=m1.Preset.drive)
    assert pins[0].status == "closed"
    assert pins[0].freshness.sample_size == 1


def test_a_truck_stop_still_reads_parking_fullness(db):
    # the generalisation must not disturb what every other pin already does
    assert mapsvc.status_signal_for("truck_stop") == crowd.SignalType.parking_fullness
    assert mapsvc.status_signal_for("weigh_station") == crowd.SignalType.weigh_station_status
    assert mapsvc.status_signal_for("scale") == crowd.SignalType.weigh_station_status


def test_a_scale_nobody_has_passed_has_no_status_rather_than_a_guess(db):
    _activate(db)
    _scale(db)
    driver = _driver(db)

    pins = m1.map_overlay(db, driver.id, *MADISON, 50000, preset=m1.Preset.drive)
    assert pins[0].status is None
    assert pins[0].freshness is None


# --- the corridor line ---
def test_scales_ahead_reports_distance_and_the_freshest_status(db):
    _activate(db)
    fac = _scale(db)
    driver = _driver(db)
    _report(db, driver, fac, "open")
    crowd.update_belief(db, fac.id, crowd.SignalType.weigh_station_status, as_of=T0)

    ahead = m1.scales_ahead(db, driver.id, *MADISON, heading_deg=0)
    assert len(ahead) == 1
    assert ahead[0]["status"] == "open"
    assert ahead[0]["sample_size"] == 1
    assert ahead[0]["distance_m"] > 0


def test_the_corridor_only_looks_ahead(db):
    _activate(db)
    _scale(db, "Behind Scale", coords=(42.8000, -89.4000))  # south of the origin
    driver = _driver(db)

    assert m1.scales_ahead(db, driver.id, *MADISON, heading_deg=0) == []


def test_the_corridor_is_capped(db):
    # scales are sparse; a corridor stack is for the next few decisions, not a listing
    _activate(db)
    for i in range(4):
        _scale(db, f"Scale {i}", coords=(AHEAD[0] + i * 0.01, AHEAD[1]))
    driver = _driver(db)

    ahead = m1.scales_ahead(db, driver.id, *MADISON, heading_deg=0)
    assert len(ahead) == m1.MAX_CORRIDOR_SCALES == 2


def test_the_corridor_is_silent_while_the_layer_is_off(db):
    m1.register_module(db)
    _scale(db)
    driver = _driver(db)
    assert m1.scales_ahead(db, driver.id, *MADISON, heading_deg=0) == []


def test_an_unreported_scale_appears_with_an_unknown_status(db):
    # it still belongs on the corridor — "there is a scale ahead" is useful even
    # when nobody has said whether it is open
    _activate(db)
    _scale(db)
    driver = _driver(db)

    ahead = m1.scales_ahead(db, driver.id, *MADISON, heading_deg=0)
    assert ahead[0]["status"] is None
    assert ahead[0]["sample_size"] == 0


# --- the report path is the standard F10 one ---
def test_a_report_runs_the_standard_crowd_pipeline(db):
    _activate(db)
    fac = _scale(db)
    first, second = _driver(db, "a@x.com"), _driver(db, "b@x.com")
    _report(db, first, fac, "closed")
    _report(db, second, fac, "closed")

    belief = crowd.update_belief(
        db, fac.id, crowd.SignalType.weigh_station_status, as_of=T0
    )
    assert belief.value == {"status": "closed"}
    assert belief.sample_size == 2  # distinct drivers, as everywhere else


def test_the_two_hour_decay_already_tuned_in_f10_is_untouched(db):
    # E3.1 explicitly does not retune these; asserting them stops a silent drift
    assert crowd.HALF_LIFE_SECONDS[crowd.SignalType.weigh_station_status] == 7200
    assert crowd.POINTS_PER_SIGNAL[crowd.SignalType.weigh_station_status] == 5
