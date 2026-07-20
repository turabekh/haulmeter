// AI-CONTEXT: TEMPORARY client fixtures for the Map surface, pending the real
// HTTP API. Shape matches F11/M1 `overlay_pins` output exactly (facility_id,
// name, facility_type, shape, lat, lon, status, badges, freshness). When the
// api exposes M1 endpoints (+ F1 session auth + CORS), swap this module for a
// fetch client behind the same interface — components stay unchanged.
function minsAgo(mins) {
  return new Date(Date.now() - mins * 60000).toISOString();
}

export const SAMPLE_PINS = [
  {
    facility_id: "f-1",
    name: "Loves Travel Stop #212",
    facility_type: "truck_stop",
    shape: "circle",
    lat: 32.78,
    lon: -96.8,
    status: "some",
    badges: [{ kind: "fuel_price", value: 4.19 }],
    freshness: { reported_at: minsAgo(40), sample_size: 3 },
  },
  {
    facility_id: "f-2",
    name: "Pilot #77",
    facility_type: "truck_stop",
    shape: "circle",
    lat: 32.83,
    lon: -96.84,
    status: "full",
    badges: [{ kind: "fuel_price", value: 4.09 }],
    freshness: { reported_at: minsAgo(12), sample_size: 6 },
  },
  {
    facility_id: "f-3",
    name: "Yardline Secured Parking",
    facility_type: "parking_property",
    shape: "square",
    lat: 32.86,
    lon: -96.79,
    status: "empty",
    badges: [{ kind: "bookable", value: 2400 }],
    freshness: { reported_at: minsAgo(3), sample_size: 1 },
  },
  {
    facility_id: "f-4",
    name: "Rest Area — I-35 NB",
    facility_type: "rest_area",
    shape: "circle",
    lat: 32.9,
    lon: -96.79,
    status: null,
    badges: [],
    freshness: null,
  },
];

export const SAMPLE_CORRIDOR = [
  { facility_id: "f-2", name: "Pilot #77", facility_type: "truck_stop", distance_m: 5400, status: "full" },
  { facility_id: "f-3", name: "Yardline Secured Parking", facility_type: "parking_property", distance_m: 9200, status: "empty" },
  { facility_id: "f-4", name: "Rest Area — I-35 NB", facility_type: "rest_area", distance_m: 14800, status: null },
];
