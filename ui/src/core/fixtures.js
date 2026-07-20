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
    badges: [{ kind: "bookable", value: 2400, spot_id: "spot-f3-a1" }],
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

// AI-CONTEXT: fixture facility profile (M2) for the profile surface pending auth.
// Shape matches GET /facility/{id}/profile exactly.
export function sampleProfile(facilityId) {
  const pin = SAMPLE_PINS.find((p) => p.facility_id === facilityId) ?? SAMPLE_PINS[0];
  return {
    facility_id: pin.facility_id,
    name: pin.name,
    check_in_procedure: "Check in at guard shack; keep PPE on in the yard.",
    overnight_parking: true,
    restrooms: true,
    dwell: {
      overall: { median_seconds: 8100, p90_seconds: 15300, sample_size: 12 },
      by_hour: { 6: { median_seconds: 5400, sample_size: 4 }, 14: { median_seconds: 12600, sample_size: 5 } },
    },
    ratings: { overall: 3.8, review_count: 2, per_aspect: {} },
    detention_risk: { rate: null, sample_size: 0, basis: "m3_pending" },
    reviews: [
      { id: "r-1", ratings: { would_return: 4 }, text: "Quick unload at 6am, slow by afternoon.", created_at: new Date().toISOString() },
      { id: "r-2", ratings: { would_return: 3 }, text: "Tight backing but staff were helpful.", created_at: new Date().toISOString() },
    ],
  };
}

// AI-CONTEXT: fixture ACTIVE stop for the Load tab / The Meter, pending the
// active-load API. Arrived 150 min ago with 120 min free time -> detention is
// accruing (the signature "money ticking up" moment).
export const SAMPLE_STOP = {
  facility_name: "Dallas Receiver",
  counterparty: "Acme Brokerage",
  appointment: "07:00",
  arrival_offset_min: 150,
  free_time_minutes: 120,
  rate_cents_per_hour: 7500,
  evidence: { bol: true, photos_taken: 2, photos_total: 4, notice_sent: false },
};

// AI-CONTEXT: fixture "Money Owed" rows (M3+M4 receivables), pending the live
// /accessorial/owed API. Shape matches money_owed() exactly.
export const SAMPLE_OWED = [
  { receivable_id: "r-1", kind: "detention", amount_cents: 15000, state: "invoiced", aging_days: 3, is_reimbursement: false },
  { receivable_id: "r-2", kind: "tonu", amount_cents: 30000, state: "disputed", aging_days: 11, is_reimbursement: false },
  { receivable_id: "r-3", kind: "lumper", amount_cents: 12500, state: "recovered", aging_days: 21, is_reimbursement: true },
];

// AI-CONTEXT: fixture document wallet (M5), pending live /protection/wallet.
export const SAMPLE_WALLET = {
  documents: [
    { id: "d-1", doc_type: "cdl", expires_on: "2027-03-01", status: "ok" },
    { id: "d-2", doc_type: "med_card", expires_on: "2026-08-01", status: "expiring" },
    { id: "d-3", doc_type: "insurance", expires_on: "2026-01-01", status: "expired" },
    { id: "d-4", doc_type: "permit", expires_on: null, status: "ok" },
  ],
  expiring: [
    { id: "d-2", doc_type: "med_card", expires_on: "2026-08-01", status: "expiring" },
    { id: "d-3", doc_type: "insurance", expires_on: "2026-01-01", status: "expired" },
  ],
};

export const SAMPLE_CORRIDOR = [
  { facility_id: "f-2", name: "Pilot #77", facility_type: "truck_stop", distance_m: 5400, status: "full" },
  { facility_id: "f-3", name: "Yardline Secured Parking", facility_type: "parking_property", distance_m: 9200, status: "empty" },
  { facility_id: "f-4", name: "Rest Area — I-35 NB", facility_type: "rest_area", distance_m: 14800, status: null },
];
