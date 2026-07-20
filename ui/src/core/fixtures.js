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
  {
    // M7: a fuel-network station — the badge carries gross/net/savings (cents)
    facility_id: "f-5",
    name: "TA Travel Center",
    facility_type: "fuel_station",
    shape: "circle",
    lat: 32.82,
    lon: -96.81,
    status: null,
    badges: [
      { kind: "fuel_net", gross: 419, net: 394, savings: 25, is_network: true, station_ref: "station-f5" },
    ],
    freshness: { reported_at: minsAgo(20), sample_size: 4 },
  },
];

// AI-CONTEXT: fixture Fleet Workspace data (M12), pending live /fleet/*. The
// web-first portal (§18); recovered/owed/fuel + per-member + counterparty rates.
export const SAMPLE_FLEET = {
  report: {
    driver_count: 4,
    recovered_cents: 184000,
    owed_cents: 92500,
    fuel_saved_cents: 213400,
    members: [
      { driver_account_id: "Marcus D.", recovered_cents: 75000, owed_cents: 15000, fuel_saved_cents: 68200 },
      { driver_account_id: "Rosa V.", recovered_cents: 45000, owed_cents: 30000, fuel_saved_cents: 51100 },
      { driver_account_id: "Danny K.", recovered_cents: 39000, owed_cents: 17500, fuel_saved_cents: 49900 },
      { driver_account_id: "Priya S.", recovered_cents: 25000, owed_cents: 30000, fuel_saved_cents: 44200 },
    ],
  },
  claims: {
    owed_cents: 92500,
    recovered_cents: 184000,
    by_counterparty: {
      "Sunbelt Logistics": { total: 120000, recovered: 108000, owed: 12000, recovery_rate: 0.9 },
      "Range Freight": { total: 96500, recovered: 52000, owed: 44500, recovery_rate: 0.539 },
      "Delta 3PL": { total: 60000, recovered: 24000, owed: 36000, recovery_rate: 0.4 },
    },
  },
};

// AI-CONTEXT: fixture points/reputation (M10), pending live /community/points.
export const SAMPLE_POINTS = {
  balance: 340,
  points_earned: 485,
  contribution_count: 32,
  trust_score: 1.4,
  level: "regular",
};

// AI-CONTEXT: fixture facility Q&A (M10-FR4), pending live /community/questions.
// presence_proven answers (on-site) rank first and carry the badge.
export function sampleQuestions() {
  return [
    {
      question_id: "q-1",
      text: "Is the north entrance still closed?",
      answers: [
        { text: "Open as of this morning — go around the fuel island.", presence_proven: true },
        { text: "Was closed last week.", presence_proven: false },
      ],
    },
    { question_id: "q-2", text: "Any overnight parking after 8pm?", answers: [] },
  ];
}

// AI-CONTEXT: fixture settlement-audit result (M9-FR1), pending live
// /money/settlements/audit. A flagged discrepancy = evidence-backed pay the
// carrier didn't pay; "review with your carrier", never legal advice.
export function sampleAudit() {
  return {
    discrepancies: [
      { kind: "detention", owed_cents: 15000, paid_cents: 5000, missed_cents: 10000, status: "flagged" },
    ],
    total_missed_cents: 10000,
  };
}

// AI-CONTEXT: fixture Driver Dollars Delivered (M9-FR4 / North Star), pending
// live /money/earnings. recovered (M3/M4) + fuel saved (M7) + audit-flagged.
export const SAMPLE_EARNINGS = {
  recovered_cents: 12500,
  fuel_saved_cents: 36250,
  flagged_cents: 10000,
  ddd_cents: 58750,
};

// AI-CONTEXT: fixture fuel savings-to-date (M7-FR4), pending live /fuel/analytics.
// Shape matches driver_analytics() exactly (gallons in thousandths, money cents).
export const SAMPLE_FUEL_ANALYTICS = {
  gallons_milli: 1450000,
  spend_cents: 571300,
  savings_cents: 36250,
  txn_count: 9,
};

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

// AI-CONTEXT: fixture M8 decision-intel for the facility scorecard, pending live
// /intel/detention-risk + /intel/appointment-hours. Basis (sample size) always
// present so the UI can show it and never fake precision (M8-FR5).
export function sampleFacilityIntel() {
  return {
    risk: { exceed_rate: 0.43, sample_size: 14, confidence: "high", basis: "tracked_stops" },
    best_hour: { hour: 6, median_seconds: 2400, sample_size: 9, confidence: "medium" },
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
