"""AI-CONTEXT: M1 Road Intelligence Map (PRD §8.1) — the daily-open surface.

A thin module composing Common Ground services via their public interfaces only
(import-linter enforced): F11 for POI overlay + corridor, F10 for live crowd
belief + contributions, F12 for offline queueing, F1 for the rig profile, F7 for
points (through F10). No module reaches a foundation's internals. Everything the
map shows is honest about freshness (design-prd §11.7); prediction is explicitly
heuristic until M8. Runs behind the F13 flag `m01_map`.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f08_notifications import public as notify
from app.foundation.f10_crowd import public as crowd
from app.foundation.f11_map import public as mapsvc
from app.foundation.f12_offline import public as offline
from app.foundation.f13_flags import public as flags
from app.foundation.f14_admin import public as admin

from .enums import NavProvider, Preset

FLAG_KEY = "m01_map"
MODULE = "m01"
# AI-CONTEXT: E3.1 — the weigh-station layer activates separately from the map
# itself. No NEW ingest source ships (no verified authoritative enforcement dataset
# exists; see HANDOFF-076), so the OSM pull is governed by the existing
# f02_ingest_osm flag and this gates only what a DRIVER sees.
WEIGH_STATION_FLAG = "m01_weigh_stations"
# A5: the Service preset. A KILL switch (`is_switched_off`), like the module routes and
# unlike the weigh-station LAYER above — this ships working and can be switched off,
# because §23 entry 105's rule is that a registry hiccup must never take a shipped
# capability dark.
SERVICE_PRESET_FLAG = "a05_service_preset"
# The world this depends on is ingest coverage, which is exactly what was broken: the
# service rules were starved of their tags for the whole life of the project and
# nothing recorded that anywhere an operator could see. The gate is where that fact
# now lives (v2.0 acceptance criterion 6).
SERVICE_INGEST_GATE = "service_ingest_verified"
# scales are sparse; a corridor stack is for the next few decisions, not a listing
MAX_CORRIDOR_SCALES = 2
# design-prd §11.4 names the size: "a vertical next 3 exits/facilities card stack".
# The cap is the feature — a stack a driver has to scroll at speed is a list, and a
# list is the free exploration corridor mode exists to replace.
MAX_CORRIDOR_ENTRIES = 3

# design-prd §11.3: presets ARE the interface. Each maps to the layers it shows.
PRESET_TYPES: dict[Preset, list] = {
    # Drive is the preset for moving forward, which is exactly when a scale matters,
    # so weigh stations live here rather than behind a new chip (§22: compose).
    Preset.drive: [
        facility.FacilityType.truck_stop,
        facility.FacilityType.rest_area,
        facility.FacilityType.fuel_station,
        facility.FacilityType.weigh_station,
        facility.FacilityType.scale,
    ],
    Preset.tonight: [
        facility.FacilityType.truck_stop,
        facility.FacilityType.rest_area,
        facility.FacilityType.parking_property,
    ],
    Preset.work: [facility.FacilityType.shipper_receiver],
    # E3.3: fuel is a SERVICE, not only a kind. Filed by kind alone this preset asked
    # "which pins are typed fuel_station", and once a fuel island merges into the
    # truck stop it stands in there is no such pin left — the Lebanon Flying J
    # disappeared from the one preset built to find it. The kinds below are the
    # candidate set; `sells_fuel` is what decides, so a truck stop with no pump is
    # still not on the fuel map.
    #
    # The candidate set must name EVERY kind that can host a pump, which is the whole
    # of COLOCATED_HOST_TYPES. Listing only truck_stop cost 168 fuel sites: a pump that
    # merged into a rest area or a parking property surfaced on neither the Fuel nor
    # (for parking) the Drive preset, having been a visible fuel_station pin before the
    # merge. Reported from production as "no facilities except demo ones".
    Preset.fuel: [
        facility.FacilityType.truck_stop,
        facility.FacilityType.rest_area,
        facility.FacilityType.parking_property,
        facility.FacilityType.repair,
        facility.FacilityType.shipper_receiver,
        facility.FacilityType.fuel_station,
    ],
    # A5. The candidate set is the same lesson E3.3 paid for on fuel: a service is a
    # fact about a SITE, not a kind, so the kinds that can host one all belong here.
    # Measured on the Wisconsin pull — 10 of the 65 repair records merged into a
    # truck stop or a parking property, and listing only `repair` would have hidden
    # every TA Truck Service and Love's Truck Care behind the pin it merged into.
    Preset.service: [
        facility.FacilityType.repair,
        facility.FacilityType.truck_stop,
        facility.FacilityType.rest_area,
        facility.FacilityType.parking_property,
        facility.FacilityType.shipper_receiver,
    ],
}

# A5: the services this preset is ABOUT. Deliberately not every SERVICE_KIND — `fuel`
# has its own preset and `scale` rides Drive, and a chip that answered "where can I
# get fixed" with every truck stop that sells diesel would answer nothing at all.
SERVICE_PRESET_KINDS = (
    facility.SERVICE_REPAIR,
    facility.SERVICE_TIRE,
    facility.SERVICE_WASH,
    facility.SERVICE_MOBILE_REPAIR,
    facility.SERVICE_TOWING,
    facility.SERVICE_PARTS,
)


def has_service(facility_type: str, services) -> bool:
    """ONE definition, for the same reason `sells_fuel` is one: the preset that SHOWS
    a pin and the card that lists its services must not be able to disagree about
    whether a site can fix a truck (the §23 entry 94 regression)."""
    return facility_type == facility.FacilityType.repair.value or any(
        s in SERVICE_PRESET_KINDS for s in (services or ())
    )

# E3.3: a parking property is Tonight's layer, not Drive's — EXCEPT when a fuel island
# merged into it, because before that merge it was a fuel_station pin that Drive showed.
# Restoring it is keeping a promise the merge broke, not widening the preset.
_DRIVE_EXTRA_IF_SELLS_FUEL = (facility.FacilityType.parking_property,)


def sells_fuel(facility_type: str, services) -> bool:
    """ONE definition, because the preset that SHOWS a pin and the badge that prices
    it must not be able to disagree about whether a site has diesel."""
    return facility_type == facility.FacilityType.fuel_station.value or facility.SERVICE_FUEL in (
        services or ()
    )

# parking availability ordering for the Tonight preset (best first)
_PARKING_RANK = {"empty": 0, "some": 1, None: 2, "full": 3}


@dataclass
class ParkingPrediction:
    status: str
    basis: str
    note: str


def register_module(db: Session) -> None:
    flags.register_flag(db, FLAG_KEY, description="M1 Road Intelligence Map")
    flags.register_flag(
        db, WEIGH_STATION_FLAG, description="M1 Weigh-station layer (E3.1, OSM-sourced)"
    )
    flags.register_flag(
        db,
        SERVICE_PRESET_FLAG,
        description="A5 Service preset — repair, tire, wash and parts on the map",
    )
    flags.add_gate(
        db,
        SERVICE_PRESET_FLAG,
        SERVICE_INGEST_GATE,
        note=(
            "The OSM extract passes the service tags AND a state has been re-ingested "
            "through them. Nine states of coverage is not this gate being satisfied."
        ),
    )
    admin.register_admin_view(db, "m01.map", MODULE, "Road Intelligence Map", "/admin/m01/map")


def _preset_types(db: Session, preset: Preset) -> list:
    """The weigh-station layer is flag-gated, so an un-activated layer contributes no
    pins rather than being filtered out client-side — a driver never downloads a
    layer they cannot see."""
    if preset == Preset.service and flags.is_switched_off(db, SERVICE_PRESET_FLAG):
        return []
    types = list(PRESET_TYPES[preset])
    if preset == Preset.drive:
        types += [t for t in _DRIVE_EXTRA_IF_SELLS_FUEL if t not in types]
    if not flags.is_enabled(db, WEIGH_STATION_FLAG):
        types = [
            t
            for t in types
            if t not in (facility.FacilityType.weigh_station, facility.FacilityType.scale)
        ]
    return types


def _preset_keeps_kind(preset: Preset, facility_type: str, services) -> bool:
    """The kind list above is a candidate set; this is the decision. Drive gains the
    extra kinds ONLY where they sell fuel, so it does not quietly become Tonight.

    Takes the two fields rather than an object so it can judge a facility row or a
    built pin — the filter runs before pins exist, and the corridor still has entries."""
    if preset == Preset.fuel:
        return sells_fuel(facility_type, services)
    if preset == Preset.service:
        return has_service(facility_type, services)
    if preset == Preset.drive and facility_type in {t.value for t in _DRIVE_EXTRA_IF_SELLS_FUEL}:
        return sells_fuel(facility_type, services)
    return True


def _preset_keeps(preset: Preset, pin) -> bool:
    return _preset_keeps_kind(preset, pin.facility_type, pin.services)


def _kept_facilities(db: Session, facilities, preset: Preset, required_amenities):
    """AI-CONTEXT: both filters run on the facility ROW, before a pin exists.

    They used to run on built pins, which meant every pin in the viewport was fully
    constructed — coordinates, crowd status, badges — and only then thrown away by a
    filter reading two fields the row already carried. `_has_amenities` went further
    and re-fetched the facility it had just been handed."""
    out = []
    for fac in facilities:
        attrs = fac.attributes or {}
        if required_amenities:
            amenities = attrs.get("amenities") or []
            if not all(a in amenities for a in required_amenities):
                continue
        if not _preset_keeps_kind(preset, fac.facility_type.value, attrs.get("services") or []):
            continue
        out.append(fac)
    return out


def map_overlay(
    db: Session,
    account_id,
    center_lat: float,
    center_lon: float,
    radius_m: float,
    preset: Preset = Preset.drive,
    required_amenities: list[str] | None = None,
):
    facilities = _kept_facilities(
        db,
        mapsvc.facilities_in_area(
            db, center_lat, center_lon, radius_m, facility_types=_preset_types(db, preset)
        ),
        preset,
        required_amenities,
    )
    pins = mapsvc.pins_for(db, facilities)
    if preset == Preset.tonight:
        pins = sorted(pins, key=lambda p: _PARKING_RANK.get(p.status, 2))
    return pins


# above this many pins in view, the server clusters (design-prd §11.5) so the map
# payload stays bounded at real national density and the client budget (§20) holds
OVERLAY_PIN_CAP = 300
_METERS_PER_DEGREE = 111_320.0
_CLUSTER_GRID_CELLS = 8  # aim for ~this many cluster cells across the viewport radius


def _cluster_precision_deg(radius_m: float) -> float:
    # zoom-adaptive: cell size scales with the view so a metro clusters finely and a
    # continental view coarsely (a fixed precision over-clusters when zoomed out).
    return max(0.02, (radius_m / _METERS_PER_DEGREE) / _CLUSTER_GRID_CELLS)


def map_overlay_view(
    db: Session,
    account_id,
    center_lat: float,
    center_lon: float,
    radius_m: float,
    preset: Preset = Preset.drive,
    required_amenities: list[str] | None = None,
    cap: int = OVERLAY_PIN_CAP,
):
    # returns individual pins when sparse; server-side clusters when dense. Payload
    # size is bounded either way (≤ cap pins, or the number of cluster cells).
    #
    # The COUNT is decided on filtered facility rows, so a clustered answer never
    # builds the pins it is about to discard (§23 98).
    facilities = _kept_facilities(
        db,
        mapsvc.facilities_in_area(
            db, center_lat, center_lon, radius_m, facility_types=_preset_types(db, preset)
        ),
        preset,
        required_amenities,
    )
    if len(facilities) > cap:
        clusters = mapsvc.clusters_for(
            db, facilities, precision_deg=_cluster_precision_deg(radius_m)
        )
        return {"clustered": True, "pins": [], "clusters": clusters, "total": len(facilities)}
    pins = mapsvc.pins_for(db, facilities)
    if preset == Preset.tonight:
        pins = sorted(pins, key=lambda p: _PARKING_RANK.get(p.status, 2))
    return {"clustered": False, "pins": pins, "clusters": [], "total": len(pins)}


# beyond this viewport area, always cluster — a continental pan never returns pins
MAX_BBOX_DEG2 = 100.0


def _bbox_precision_deg(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> float:
    span_deg = max(abs(max_lat - min_lat), abs(max_lon - min_lon))
    return _cluster_precision_deg(span_deg * _METERS_PER_DEGREE / 2)


def map_overlay_bbox(
    db: Session,
    account_id,
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    preset: Preset = Preset.drive,
    required_amenities: list[str] | None = None,
):
    facilities = _kept_facilities(
        db,
        mapsvc.facilities_in_bbox(
            db, min_lat, min_lon, max_lat, max_lon, facility_types=_preset_types(db, preset)
        ),
        preset,
        required_amenities,
    )
    pins = mapsvc.pins_for(db, facilities)
    if preset == Preset.tonight:
        pins = sorted(pins, key=lambda p: _PARKING_RANK.get(p.status, 2))
    return pins


def map_overlay_view_bbox(
    db: Session,
    account_id,
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    preset: Preset = Preset.drive,
    required_amenities: list[str] | None = None,
    cap: int = OVERLAY_PIN_CAP,
):
    # viewport-driven overlay (the primary map mode). Individual pins when sparse;
    # server-side clusters when dense OR when the viewport spans a huge area (§11.5).
    facilities = _kept_facilities(
        db,
        mapsvc.facilities_in_bbox(
            db, min_lat, min_lon, max_lat, max_lon, facility_types=_preset_types(db, preset)
        ),
        preset,
        required_amenities,
    )
    area = abs(max_lat - min_lat) * abs(max_lon - min_lon)
    if len(facilities) > cap or area > MAX_BBOX_DEG2:
        precision = _bbox_precision_deg(min_lat, min_lon, max_lat, max_lon)
        clusters = mapsvc.clusters_for(db, facilities, precision_deg=precision)
        return {"clustered": True, "pins": [], "clusters": clusters, "total": len(facilities)}
    pins = mapsvc.pins_for(db, facilities)
    if preset == Preset.tonight:
        pins = sorted(pins, key=lambda p: _PARKING_RANK.get(p.status, 2))
    return {"clustered": False, "pins": pins, "clusters": [], "total": len(pins)}


def _has_amenities(db: Session, pin, required: list[str]) -> bool:
    fac = facility.get_facility(db, pin.facility_id)
    amenities = (fac.attributes or {}).get("amenities", []) if fac is not None else []
    return all(a in amenities for a in required)


def corridor_view(
    db: Session,
    account_id,
    origin_lat: float,
    origin_lon: float,
    heading_deg: float,
    max_distance_m: float,
    preset: Preset = Preset.drive,
):
    return mapsvc.corridor(
        db,
        origin_lat,
        origin_lon,
        heading_deg,
        max_distance_m,
        facility_types=_preset_types(db, preset),
    )


def corridor_ahead(
    db: Session,
    account_id,
    origin_lat: float,
    origin_lon: float,
    heading_deg: float,
    max_distance_m: float = 40000,
    preset: Preset = Preset.drive,
    limit: int = MAX_CORRIDOR_ENTRIES,
) -> list[dict]:
    """AI-CONTEXT: §11.4's card stack, carrying the status its own pins carry.

    `corridor_view` returns GEOMETRY alone — name, type, distance — and the Map
    surface rendered a FIXTURE beside it that carried statuses, because the endpoint
    had none to give. So the one screen a driver cannot check anything on showed
    invented parking. A stack that names a truck stop and cannot say whether it is
    full has answered the easy half of the question asked at 65 mph.

    The signal follows the facility KIND, read from f11's own mapping rather than
    re-derived here, so a scale in the stack is asked whether it is open and a truck
    stop how full it is — the corridor and the pin can never disagree about what a
    status means. `corridor_view` is untouched: M7, M8 and M13 consume its entries
    and none of them wants a crowd read.
    """
    entries = mapsvc.corridor(
        db,
        origin_lat,
        origin_lon,
        heading_deg,
        max_distance_m,
        facility_types=_preset_types(db, preset),
    )
    entries = [e for e in entries if _preset_keeps(preset, e)]
    out = []
    for entry in entries[:limit]:
        belief = crowd.get_belief(
            db, entry.facility_id, mapsvc.status_signal_for(entry.facility_type)
        )
        value = (belief.value or {}) if belief is not None else {}
        out.append(
            {
                "facility_id": entry.facility_id,
                "name": entry.name,
                "facility_type": entry.facility_type,
                "lat": entry.lat,
                "lon": entry.lon,
                "distance_m": entry.distance_m,
                # None when nobody has reported recently. §11.7: the stack says so
                # rather than letting silence read as a status somebody gave.
                "status": value.get("status"),
                "reported_at": belief.freshest_at if belief is not None else None,
                "sample_size": belief.sample_size if belief is not None else 0,
                "services": entry.services,
            }
        )
    return out


def scales_ahead(
    db: Session,
    account_id,
    origin_lat: float,
    origin_lon: float,
    heading_deg: float,
    max_distance_m: float = 64000,
    limit: int = MAX_CORRIDOR_SCALES,
) -> list[dict]:
    """E3.1: "scale ahead", with the freshest crowd status. Returns nothing at all
    while the layer is off — an un-activated layer is silent, not empty-shaped."""
    if not flags.is_enabled(db, WEIGH_STATION_FLAG):
        return []
    entries = mapsvc.corridor(
        db,
        origin_lat,
        origin_lon,
        heading_deg,
        max_distance_m,
        facility_types=[facility.FacilityType.weigh_station, facility.FacilityType.scale],
    )
    out = []
    for entry in entries[:limit]:
        belief = crowd.get_belief(db, entry.facility_id, crowd.SignalType.weigh_station_status)
        value = (belief.value or {}) if belief is not None else {}
        out.append(
            {
                "facility_id": entry.facility_id,
                "name": entry.name,
                "facility_type": entry.facility_type,
                "distance_m": entry.distance_m,
                # None when nobody has reported: "unknown" is the honest state for a
                # scale nobody has passed recently, and the UI says so (§11.7)
                "status": value.get("status"),
                "reported_at": belief.freshest_at if belief is not None else None,
                "sample_size": belief.sample_size if belief is not None else 0,
            }
        )
    return out


def predict_parking_fill(db: Session, facility_id, hour_of_day: int) -> ParkingPrediction:
    # AI-CONTEXT: heuristic until M8 upgrades it to a learned model (PRD M1-FR3);
    # basis is always surfaced so the UI never fakes precision (design-prd §11.7).
    if hour_of_day >= 18 or hour_of_day < 4:
        status = "full"
    elif hour_of_day >= 15:
        status = "some"
    else:
        status = "empty"
    return ParkingPrediction(status=status, basis="heuristic", note="usually fills by 6pm")


def submit_status(
    db: Session,
    account_id,
    facility_id,
    signal_type: crowd.SignalType,
    value: dict,
    submitted_at: datetime,
):
    # geofence-presence proof + points are enforced inside F10 (PRD M1-FR7)
    submission = crowd.submit(
        db, account_id, facility_id, signal_type, value, submitted_at=submitted_at
    )
    # refresh the aggregated belief so the pin reflects it immediately
    # (M1 DoD: report -> aggregate -> pin badge under 60s)
    crowd.update_belief(db, facility_id, signal_type, as_of=submitted_at)
    return submission


# --- Asking the driver, instead of waiting to be told (§23 entry 112) ---
#
# AI-CONTEXT: M1-FR7's chip has always been driver-INITIATED and §23 entry 104 made
# status arrive live; neither is a prompt. Nothing in this product had ever asked a
# driver anything. This is the ask.
#
# WHY THE FIRST DWELL_TICK AND NOT `ENTER` — owner-approved. ENTER fires on crossing the
# geofence, which includes a driver who rolled through the lot, turned around, or was
# routed past the pumps; asking them would be asking someone who never stopped. F3's
# `DWELL_TICK_INTERVAL` is already 15 minutes and is the product's existing answer to
# "actually stopped here", so this needs no new threshold to argue about.
#
# 15 rather than RESTING's 20 minutes, which was the owner's open question: aligning
# would mean either inventing a threshold or waiting for the SECOND tick at 30 minutes,
# and a driver who stops for a 20-minute shower would then be asked after they had
# already pulled out. The prompt has to land while they can still see the lot.
#
# NEVER WHILE DRIVING is structural rather than guarded: a dwell tick cannot fire for a
# moving truck, so §13.4's ban on interactive prompts at speed is satisfied by the
# trigger itself and not by a check somebody can forget.
PROMPTABLE_KINDS = frozenset({"truck_stop", "rest_area", "parking_property"})


def _already_reported_today(db: Session, account_id, facility_id, now: datetime) -> bool:
    """A driver who has already told us about this lot must not be asked about it.

    AI-CONTEXT: the class cap (1/day) stops repeat prompting in general; this stops the
    specific insult of being asked for something you volunteered ten minutes ago.
    """
    return crowd.has_recent_submission(
        db, account_id, facility_id, crowd.SignalType.parking_fullness, since=now - PROMPT_LOOKBACK
    )


PROMPT_LOOKBACK = timedelta(hours=12)


def prompt_for_lot_status(db: Session, account_id, facility_id, gateway, now: datetime):
    """Ask a driver who has actually stopped how full the lot is.

    Returns the Notification, or None when there is nothing to ask. Every refusal below
    is a rule rather than an optimisation, so they are separate and readable.
    """
    fac = facility.get_facility(db, facility_id)
    if fac is None:
        return None
    # §11.7 in the ASKING direction: "how full is the lot?" at a grocery warehouse is a
    # question about nothing. A driver dwelling at a shipper_receiver is WORKING, and
    # that dwell is M3's business, not a survey.
    if fac.facility_type.value not in PROMPTABLE_KINDS:
        return None
    if _already_reported_today(db, account_id, facility_id, now):
        return None
    name = fac.name or "this stop"
    return notify.dispatch(
        db,
        account_id,
        notify.NotificationTier.P1,
        notify.LOT_STATUS_PROMPT_CLASS,
        f"How's the lot at {name}?",
        "One tap helps the next driver find a spot.",
        # §13.5: the facility's own screen, where the same question is already a chip
        f"/facility/{facility_id}",
        gateway,
        now=now,
        subject_ref=str(facility_id),
        # the answer must be one tap from a LOCKED phone or it is a task, not a
        # confirmation. These are the exact three values PARKING_STATUS already defines
        # and the map already renders — no new vocabulary anywhere in the system.
        actions=[
            {"action": "lot:empty", "title": "Empty"},
            {"action": "lot:some", "title": "Some"},
            {"action": "lot:full", "title": "Full"},
        ],
    )


# AI-CONTEXT: the trigger, shape (c) — owner-chosen (§23 entry 112).
#
# The geofence could not answer this. Events fire only for ARMED facilities and the one
# caller of `arm_geofence` is `f05_load.arm_stop`, so a driver parked at a truck stop
# for the night is invisible to `evaluate_ping`. Auto-arming was the obvious fix and was
# rejected: armings write presence and event rows that M3's money reads, and §23 entries
# 73, 93 and 107 are all the same story of something adjacent to the clock being changed
# and the money going wrong.
#
# So this reads the ping trail through F3's `stationary_since` and WRITES NOTHING to the
# location tables. It cannot affect a detention claim even if it is completely wrong.
#
# DWELL_MINUTES matches F3's own `DWELL_TICK_INTERVAL` deliberately: the product already
# has one answer to "actually stopped here", and a second number would eventually
# disagree with the first.
DWELL_MINUTES = 15
PROMPT_COOLDOWN = timedelta(hours=20)


def lot_status_prompt_due(db: Session, account_id, lat: float, lon: float, gateway, now: datetime):
    """Ask, if the driver has actually settled somewhere worth asking about.

    Called from the position-ping route on every ping, so the ORDER of these checks is
    load-bearing: the cheapest and most-often-false one runs first. A moving driver
    costs one indexed read and nothing else.
    """
    # 1. Has this class been offered at all today? One row read, and it short-circuits
    #    the whole path for the ~95% of pings that happen after a prompt has been made.
    #    Counting ATTEMPTS not sends is what stops a suppressed row per ping (§23 102
    #    renders suppressed rows, so that would be ninety held prompts in one inbox).
    if notify.has_notification_since(
        db, account_id, notify.LOT_STATUS_PROMPT_CLASS, now - PROMPT_COOLDOWN
    ):
        return None
    # 2. Are they even stopped? False for every ping of a moving truck.
    since = location.stationary_since(db, account_id, now)
    if since is None or (now - since) < timedelta(minutes=DWELL_MINUTES):
        return None
    # 3. Only now is a spatial query worth paying for.
    for fac in facility.nearest(db, lat, lon, radius_m=location.STATIONARY_RADIUS_M):
        if fac.facility_type.value in PROMPTABLE_KINDS:
            return prompt_for_lot_status(db, account_id, fac.id, gateway, now)
    return None


def queue_status_offline(
    db: Session,
    account_id,
    idempotency_key: str,
    facility_id,
    signal_type: crowd.SignalType,
    value: dict,
    submitted_at: datetime,
):
    # PRD M1-FR9: contributions written locally first, synced idempotently via F12;
    # the handler applies the F10 submission exactly once on first sync.
    def apply(_envelope):
        crowd.submit(db, account_id, facility_id, signal_type, value, submitted_at=submitted_at)

    return offline.ingest(
        db,
        account_id,
        idempotency_key,
        "crowd_status",
        {"facility_id": str(facility_id), "signal": signal_type.value, "value": value},
        occurred_at=submitted_at,
        handler=apply,
    )


def nav_deeplink(lat: float, lon: float, provider: NavProvider = NavProvider.google) -> str:
    # PRD M1-FR8: deep-link handoff to external nav — explicitly NO in-house routing.
    if provider == NavProvider.google:
        return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
    if provider == NavProvider.apple:
        return f"https://maps.apple.com/?daddr={lat},{lon}"
    if provider == NavProvider.hammer:
        return f"hammer://navigate?lat={lat}&lon={lon}"
    return f"copilot://navigate?lat={lat}&lon={lon}"


def record_map_open(db: Session, account_id, occurred_at: datetime):
    return admin.emit(db, "map_open", MODULE, occurred_at, account_id=account_id)
