// AI-CONTEXT: the LAW 0 harness — the first mechanical check of the product's first law.
//
// design-prd §22.3 has twelve boxes and most of them are layout claims: complete at
// 360×800, targets ≥48 dp, nothing clipped, 200% reflow, renders under xx-XL. None of
// them could ever be checked. vitest runs in jsdom/happy-dom, which has no layout
// engine — getBoundingClientRect returns zeros — so every assertion of that kind
// would pass on an empty page. Contrast is genuinely tested because it is computable
// from tokens; the rest, including LAW 0 itself, has been honour system.
//
// This is deliberately FOUR assertions, not a visual-regression suite. Screenshot
// diffing would fail on every intentional change and teach everyone to re-baseline
// without looking, which is worse than no check. These four are the ones that are
// objectively true or false, that a human reviewer reliably misses, and that map
// directly onto rules the constitution already states:
//
//   1. no horizontal overflow at 360 dp      — LAW 0 / MF-2
//   2. no computed font below the 13 dp floor — §6.2 ("Nothing smaller exists")
//   3. every interactive element ≥ 48 dp      — §6.5 the glove spec
//   4. all of the above again under xx-XL     — §12.5 (+40% length)
//
// It runs as `make ui-layout`, NOT inside `make test`: the unit suite finishes in
// seconds and putting a browser on that path would cost the tight loop this codebase
// depends on. `make ci` runs both.
import { test, expect } from "@playwright/test";

const BASE = process.env.UI_BASE || "http://ui:9008";

// every driver-app surface, plus the two §18 portals — see the note on PORTAL_SURFACES.
//
// Portals are exempt from LAW 0, which is about mobile-FIRST design. They are NOT exempt
// from §6, and that distinction is what put them in this file (§23 entry 132).
//
// The last three were added when the theme dimension came out: the evidence surface
// is where the newest and largest UI in the project landed (export, share, the §15.1
// queue, the DRIVING guard) and had never been checked, which is the opposite of
// where a harness should be spending its time. The parameterised routes render their
// empty/loading states here, and an empty state is layout too — §15.3 gives it a
// spec, so it gets checked like anything else.

// AI-CONTEXT: `load` here is the EMPTY state, and for four sessions it was the only
// Load tab this harness had ever rendered. The surface falls back to its no-load
// state whenever `GET /load/{stop}/meter` fails, and it always failed here: the
// planted token is a string, not a session, so the API answers 401. Everything that
// only exists on a live load — the CTA ladder, the evidence link, the stop context
// row, the next-stop preview — was therefore never measured, and 136/136 green said
// nothing about any of it. It hid a `.card__link` at 18 dp against §6.5's 48.
//
// `load-live` is that state, mocked. The mock is CANNED rather than seeded through
// the API, which keeps the rule this file was written on: a failing backend must not
// read as a layout defect. Its payload is copied from the endpoint's own return
// shape (api/app/api/load.py::meter) — a fixture whose shape drifts from its
// endpoint is exactly the defect that put a raw ISO timestamp on this screen.

// AI-CONTEXT: every Load surface below also renders §15.5's degraded-location card,
// and that is worth knowing rather than rediscovering. Playwright denies geolocation
// unless a context grants it, so `watchPosition` fails with PERMISSION_DENIED and
// core/location.js flips to "denied" — which is the card's condition. It is real
// coverage at 360 dp under all three locales.
//
// It is also IMPLICIT: granting geolocation in a context option here would silently
// stop measuring the card without failing anything. If that ever happens, give the
// card its own surface rather than letting the coverage evaporate.

// where the app sends its requests (ui/src/core/api.js). The mock has to intercept
// that exact origin; if it drifts, the surface's `ready` selector fails rather than
// quietly measuring the empty state again.
const API_BASE = "http://localhost:8008";
const LIVE_STOP = "00000000-0000-0000-0000-0000000000cc";
const LIVE_MOCKS = {
  "/load/active": {
    stop_id: LIVE_STOP,
    // §23 entry 82 — this route names the dock now, not just the stop
    facility_id: "00000000-0000-0000-0000-0000000000b3",
    facility_name: "Dallas Cold Storage",
  },
  [`/load/${LIVE_STOP}/meter`]: {
    stop_id: LIVE_STOP,
    claim_id: "00000000-0000-0000-0000-0000000000dd",
    facility_name: "Dallas Cold Storage",
    // AI-CONTEXT: shape-matched to the endpoint (§23 entries 84/85). The meter now
    // carries the facility id and the load's linehaul rate, and a mock missing them
    // would render the profit calculator with no prefill — measuring the screen
    // without the thing that was just added to it.
    facility_id: "00000000-0000-0000-0000-0000000000b3",
    rate_cents: 285000,
    counterparty: "Coyote Logistics",
    appointment: "2026-07-27T04:10:50.993277+00:00",
    arrived: true,
    free_time_minutes: 120,
    rate_cents_per_hour: 7500,
    phase: "accruing",
    free_time_remaining_seconds: 0,
    detention_seconds: 4200,
    detention_cents: 8750,
    notice_sent: false,
    filed: false,
    photos_captured: 0,
    photos_required: 4,
    bol_captured: false,
    // AI-CONTEXT: A1 req 1's checklist, shape-matched for the same reason as the two
    // fields above (§23 entries 84/85). The meter carries it now, and a mock without it
    // renders the single-row fallback — measuring the screen without the thing that was
    // just added to it. A DELIVERY: five configured items, four of them rows, and the
    // longest label in the set (lumper receipt) is the one that has to survive +40%.
    checklist: [
      { item: "bol", kind: "document", captured: true, required: true },
      { item: "pod", kind: "document", captured: false, required: true },
      { item: "cargo_condition", kind: "condition_photo", captured: false, required: true },
      { item: "lumper_receipt", kind: "document", captured: false, required: true },
      { item: "damage", kind: "document", captured: false, required: false },
    ],
    appointment_end: "2026-07-27T06:10:50.993277+00:00",
    appointment_source: "rate_con_parse",
    next_stop: {
      facility_name: "Fort Worth Cross-dock",
      stop_type: "delivery",
      appointment: "2026-07-27T14:00:00+00:00",
    },
  },
  "/load/history": {
    loads: [
      {
        load_id: "l-1",
        stop_id: "00000000-0000-0000-0000-0000000000ee",
        facility_name: "ACME Distribution Center",
        reference_number: "L-9001",
        created_at: "2026-07-24T14:00:00+00:00",
        status: "completed",
        stop_count: 2,
        detention_cents: 8750,
        claim_state: "invoiced",
        evidence_count: 6,
        documents: ["bol", "rate_con"],
      },
      {
        load_id: "l-2",
        stop_id: "00000000-0000-0000-0000-0000000000ef",
        facility_name: "Quiet Dock",
        reference_number: null,
        created_at: "2026-07-20T09:00:00+00:00",
        status: "completed",
        stop_count: 1,
        detention_cents: null,
        claim_state: null,
        evidence_count: 0,
        documents: [],
      },
    ],
  },
};

// AI-CONTEXT: the FACILITY CARD, which this harness had never opened (§10.1).
//
// It is the map's whole payload — tap a pin, get the card — and it carries §10.1's
// contextual CTA ladder: Book / Fuel here / Report price / Navigate / "This is your
// stop". Five different screens behind one component, none of them ever measured at
// 360 dp, and the one with the LONGEST label ("Book spot — $24.00") interpolates a
// price, which is exactly where +40% under xx-XL bites.
//
// One pin per state, so `open: [".pin"]` is unambiguous, and each `ready` is the
// ladder modifier that only that state produces — without those, a mock that drifted
// would fall back to SAMPLE_PINS, open a fixture's card and go green having measured
// the wrong screen.
// AI-CONTEXT: click the MOCKED pin, not whichever pin happens to exist.
//
// `open: [".pin"]` looked fine and failed under load: the surface falls back to
// SAMPLE_PINS while `/map/overlay` is still in flight, so the step clicked a FIXTURE
// pin, opened the wrong card, and the `ready` selector timed out. Worse, had the two
// cards shared a lead rung it would have gone green having measured the wrong screen.
// Targeting the facility id makes the step wait for the mocked overlay to land, and a
// mock that ever stops matching fails here rather than silently.
//
// A data attribute rather than the aria-label, because the label is composed text and
// this file's steps are CSS-only for a reason: every surface is measured under en,
// xx-XL and pa.
const pinOf = (pin) => `.pin[data-facility="${pin.facility_id}"]`;

const PIN_FRESHNESS = {
  reported_at: new Date(Date.now() - 40 * 60 * 1000).toISOString(),
  sample_size: 3,
  source: null,
};
function mapMocks(pin, extra = {}) {
  return {
    ...NO_LOAD_MOCKS,
    "/map/overlay": { clustered: false, total: 1, clusters: [], pins: [pin] },
    // the chip row asks the server what is live (§21.3). Unmocked, this 404s and the
    // row falls back to four chips — which is HANDOFF-105 §9's warning exactly: the
    // harness would go green having measured a row that is not the one shipping. All
    // six are returned so the row is measured at its WIDEST, which is what 360 dp and
    // the +40% pseudo-locale need to survive.
    "/map/presets": { presets: ["drive", "tonight", "work", "fuel", "food", "service"] },
    "/community/handoff/nearby": [],
    ...extra,
  };
}
const TRUCK_STOP_PIN = {
  facility_id: "00000000-0000-0000-0000-0000000000a1",
  name: "Love's Travel Stop #212",
  facility_type: "truck_stop",
  shape: "circle",
  lat: 32.78,
  lon: -96.8,
  status: "some",
  availability: "Low",
  capacity: 62,
  badges: [],
  freshness: PIN_FRESHNESS,
};
const BOOKABLE_PIN = {
  ...TRUCK_STOP_PIN,
  facility_id: "00000000-0000-0000-0000-0000000000a2",
  name: "Yardline Secured Parking",
  facility_type: "parking_property",
  shape: "square",
  availability: null,
  capacity: null,
  badges: [{ kind: "bookable", value: 2400, spot_id: "00000000-0000-0000-0000-0000000000a9" }],
};
// A5: a repair shop with everything a broken-down driver needs from it — the service
// list, the hours, and a number to call. 17 of the 45 repair facilities in the real
// registry carry a phone, so this is the GOOD case; the state below it is the common
// one, and both have to fit at 360 dp.
const REPAIR_PIN = {
  ...TRUCK_STOP_PIN,
  facility_id: "00000000-0000-0000-0000-0000000000a5",
  name: "Portage Diesel Repair",
  facility_type: "repair",
  status: null,
  availability: null,
  capacity: null,
  freshness: null,
  badges: [],
  services: ["truck_repair", "tire", "wash"],
  phone: "+1-608-555-0199",
  opening_hours: "Mo-Fr 07:00-18:00",
};
const REPAIR_PIN_NO_CONTACT = {
  ...REPAIR_PIN,
  facility_id: "00000000-0000-0000-0000-0000000000a6",
  name: "Badger Truck Services",
  services: ["truck_repair"],
  phone: null,
  opening_hours: null,
};
const REPAIR_PIN_CLAIMED = {
  ...REPAIR_PIN,
  facility_id: "00000000-0000-0000-0000-0000000000a7",
  name: "Gateway Truck Service",
  // A6: what a CLAIM changes on this card. The shop's own number and hours win over
  // the ingested ones, it added the towing OSM could not tell us about, and the
  // attribution line names who is speaking — a fourth caption row on a card that was
  // already the densest thing the Service preset renders.
  services: ["truck_repair", "tire", "towing", "parts"],
  phone: "+1-417-555-1212",
  opening_hours: "24/7 roadside callout",
  claimed_by: { name: "Gateway Truck Service", verify_status: "verified" },
};
const FUEL_PIN = {
  ...TRUCK_STOP_PIN,
  facility_id: "00000000-0000-0000-0000-0000000000a3",
  name: "QuikFuel Dallas",
  facility_type: "fuel_station",
  status: null,
  availability: null,
  capacity: null,
  freshness: null,
  badges: [{
    kind: "fuel_net", value: 394, net: 394, gross: 419, savings: 25,
    is_network: true, source: "feed", indicative: false,
    as_of: PIN_FRESHNESS.reported_at, sample_size: null,
    station_ref: "00000000-0000-0000-0000-0000000000a3",
  }],
};
// the driver's OWN dock: its facility_id is the one `/load/active` names, which is
// what makes §23 entry 82's rung render
const ARMED_DOCK_PIN = {
  ...TRUCK_STOP_PIN,
  facility_id: "00000000-0000-0000-0000-0000000000b3",
  name: "Dallas Cold Storage",
  facility_type: "shipper_receiver",
  shape: "diamond",
  status: null,
  availability: null,
  capacity: null,
  freshness: null,
};

// the same tab with NO load. `/load/active` has to answer null here: the surface asks
// it on mount for fresh-device resume, so a mock that always names a stop puts every
// Load-tab surface into the live state and the empty-state sheets never open.
const NO_LOAD_MOCKS = { ...LIVE_MOCKS, "/load/active": { stop_id: null } };

// AI-CONTEXT: the SHEETS. §8 calls the bottom sheet "the workhorse (NAV-3)" and this
// harness had never opened one — it measured nine base surfaces, so the archive, the
// viewer, the capture sheet, the rate-con import, "More for this stop", past loads
// and inspection mode were all unmeasured at 360 dp. That is where the newest and
// densest UI in the project lives, and a sheet is exactly where a 48 dp target or a
// +40% label is most likely to break: it opens into a fraction of the viewport.
//
// `open` is a list of CSS selectors clicked in order. They are CSS and never text,
// because every surface is measured under en, xx-XL and pa — a step that clicked a
// label would silently stop finding it in two locales out of three, and the surface
// would go green having opened nothing. `ready` is what makes that impossible.
// a 1×1 PNG. The viewer fetches BYTES and builds an object URL from the blob, so a
// JSON stand-in would render a broken <img> — and a broken image has no intrinsic
// size, which means the harness would skip it and report the viewer as measured.
const PNG_1PX =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
const binary = (contentType, base64) => ({ __binary: { contentType, base64 } });

// the parse result the confirm screen renders (F5 ratecon.draft + the route's
// document_id). Terms the contract is silent on are said as SILENCE, never as zero.
const RATE_CON_DRAFT = {
  document_id: "00000000-0000-0000-0000-00000000000f",
  readable: true,
  parsed: {
    broker_name: "Coyote Logistics",
    reference_number: "L-9001",
    // AI-CONTEXT: this said `linehaul_cents` and the API has always returned
    // `rate_cents` — a key that existed nowhere but in this fixture, so the harness
    // measured the rate-con sheet with the money field permanently blank. Entry 52's
    // rule inside the harness itself: a fixture whose shape does not match its
    // endpoint hides the endpoint. Found while wiring §23 entry 84.
    rate_cents: 250000,
    free_time_minutes: 120,
    detention_rate_cents_per_hour: 7500,
    // the terms M4-FR4's confirm step quotes. Long wording on purpose: this block is
    // the widest thing on the sheet, and 360 dp is where it has to survive.
    accessorial_terms: {
      layover: "$150 per night after 24 hours, pre-approval required in writing",
      lumper: "Reimbursed at cost with receipt attached to the POD",
    },
  },
  silent_on: ["tonu"],
  // AI-CONTEXT: a ROUTE (§23 entry 68) — two stops, so the confirm screen is measured
  // the way a real contract renders it rather than at its shortest.
  stops: [
    {
      sequence: 0,
      stop_type: "pickup",
      name: "Harvest Foods DC",
      address: "1200 Commerce Pkwy, Dallas, TX 75212",
      appointment_start: "2026-08-03T08:00:00",
      appointment_end: "2026-08-03T10:00:00",
      location: { lat: 32.7767, lon: -96.797, label: "1200 Commerce Street, Dallas, Texas 75208" },
      facility_candidates: [
        { facility_id: "00000000-0000-0000-0000-0000000000b3", name: "Harvest Foods DC", address: null, score: 0.91 },
      ],
    },
    {
      sequence: 1,
      stop_type: "delivery",
      name: "Metro Market Warehouse",
      address: "8450 Lakeside Ave, Columbus, OH 43228",
      appointment_start: "2026-08-05T07:30:00",
      appointment_end: null,
      location: { lat: 39.9612, lon: -83.0907, label: "Columbus, Ohio 43228, United States" },
      facility_candidates: [
        { facility_id: "00000000-0000-0000-0000-0000000000b1", name: "ACME Distribution Ctr", address: "1 Dock Rd, Dallas TX", score: 0.68 },
        { facility_id: "00000000-0000-0000-0000-0000000000b2", name: "Dallas Distribution Center", address: "9 Loop 12, Dallas TX", score: 0.65 },
      ],
    },
  ],
};
const MONEY_MOCKS = {
  "/accessorial/owed": [
    { receivable_id: "r-1", kind: "detention", amount_cents: 8750, state: "invoiced", aging_days: 12, is_reimbursement: false },
    { receivable_id: "r-2", kind: "lumper", amount_cents: 12500, state: "disputed", aging_days: 31, is_reimbursement: true },
  ],
  "/money/earnings": {
    recovered_cents: 42500,
    fuel_saved_cents: 18600,
    flagged_cents: 7500,
    ddd_cents: 61100,
  },
  "/auth/me": { email: "driver@example.com", verified: true, authority: "owner_operator" },
};

const EVIDENCE_STOP = "00000000-0000-0000-0000-0000000000aa";
const EVIDENCE_MOCKS = {
  [`/load/${EVIDENCE_STOP}/evidence`]: {
    stop_id: EVIDENCE_STOP,
    facility: "Dallas Cold Storage",
    documents: [{ doc_type: "bol", uploaded_at: "2026-07-24T15:00:00+00:00" }],
    chain_valid: true,
    record_count: 3,
    photo_count: 2,
    timeline: [
      { type: "geofence_enter", occurred_at: "2026-07-24T13:58:00+00:00" },
      { type: "arrival_confirmed", occurred_at: "2026-07-24T14:02:00+00:00" },
      { type: "geofence_exit", occurred_at: "2026-07-24T17:31:00+00:00" },
    ],
    photos: [
      { artifact_id: "a-1", prompt: "trailer_corner", content_hash: "a".repeat(64), captured_at: "2026-07-24T14:05:00+00:00", has_image: true },
      { artifact_id: "a-2", prompt: "seal", content_hash: "b".repeat(64), captured_at: "2026-07-24T14:06:00+00:00", has_image: true },
    ],
  },
};

const DOC_ID = "00000000-0000-0000-0000-00000000000a";
const WALLET_MOCKS = {
  "/protection/wallet": {
    documents: [
      { id: DOC_ID, doc_type: "cdl", expires_on: "2027-03-01", status: "ok" },
      { id: "00000000-0000-0000-0000-00000000000b", doc_type: "med_card", expires_on: "2026-08-10", status: "expiring" },
      { id: "00000000-0000-0000-0000-00000000000c", doc_type: "bol", expires_on: null, status: "ok" },
    ],
    expiring: [
      { id: "00000000-0000-0000-0000-00000000000b", doc_type: "med_card", expires_on: "2026-08-10", status: "expiring" },
    ],
    archived_count: 2,
    load_paperwork: [
      {
        load_id: "00000000-0000-0000-0000-0000000000f1",
        stop_id: "00000000-0000-0000-0000-0000000000f2",
        reference_number: "BRL-78426",
        created_at: "2026-07-28T04:00:00+00:00",
        facility_name: "Harvest Foods DC",
        destination_name: "Metro Market Warehouse",
        doc_types: ["bol", "rate_con"],
        document_count: 3,
      },
    ],
    unattached: [
      {
        id: "00000000-0000-0000-0000-0000000000f3",
        doc_type: "rate_con",
        uploaded_at: "2026-07-28T12:41:00+00:00",
        content_type: "application/pdf",
      },
    ],
  },
  "/protection/documents/types": {
    types: ["cdl", "med_card", "insurance", "permit", "rate_con", "bol", "pod", "other"],
    expiring: ["cdl", "med_card", "insurance", "permit"],
    superseding: ["cdl", "med_card", "insurance"],
  },
  "/protection/documents/archive": {
    documents: [
      {
        id: "00000000-0000-0000-0000-00000000000d",
        doc_type: "cdl",
        expires_on: "2026-01-01",
        archived_at: "2026-07-19T10:00:00+00:00",
        reason: "superseded",
        replaced_by: { id: DOC_ID, doc_type: "cdl", uploaded_at: "2026-07-19T10:00:00+00:00" },
        restorable: false,
        blocked_by_doc_type: "cdl",
      },
      {
        id: "00000000-0000-0000-0000-00000000000e",
        doc_type: "permit",
        expires_on: null,
        archived_at: "2026-07-11T08:00:00+00:00",
        reason: "removed",
        replaced_by: null,
        restorable: true,
        blocked_by_doc_type: null,
      },
    ],
  },
  [`/protection/documents/${DOC_ID}`]: binary("image/png", PNG_1PX),
};

// AI-CONTEXT: shape-matched to the endpoint (api/m05_protection.py::stop_packets).
// `contents` and `claim` were added the day the review card shipped; a mock missing
// them renders the sheet with no contents list and no claim section — measuring the
// screen without the thing it was added to measure, which is §23 entry 84's defect and
// HANDOFF-105 §9's warning in one.
const PACKET_ROW = {
  id: "11111111-1111-1111-1111-111111111111",
  state: "draft",
  drafted_at: "2026-08-01T12:00:00+00:00",
  reference: "BL-77421",
  recipient: "accountspayable@boltlogistics.example",
  counterparty_name: "Bolt Logistics",
  facility_name: "Midwest Distribution Center — Dock 4",
  contents: ["bol", "pod", "cargo_condition", "lumper_receipt"],
  claim: null,
};

// AI-CONTEXT: audit U-04 — ClaimSurface's two modes. Shape-matched to
// `GET /load/{stop_id}/claim` (api/app/api/load.py) including the `claim_evidence`
// spread, because a mock missing `timeline` would render the evidence card empty and
// measure the screen without the thing the claim is FOR.
const CLAIM_TIMELINE = [
  { type: "GEOFENCE", occurred_at: "2026-07-27T04:10:00+00:00" },
  { type: "PHOTO", occurred_at: "2026-07-27T04:12:00+00:00" },
  { type: "DOCUMENT", occurred_at: "2026-07-27T04:15:00+00:00" },
  { type: "NOTIFICATION", occurred_at: "2026-07-27T06:20:00+00:00" },
];
const CLAIM_BASE = {
  claim_id: "00000000-0000-0000-0000-0000000000dd",
  amount_cents: 18750,
  detention_seconds: 9000,
  free_time_minutes: 120,
  rate_cents_per_hour: 7500,
  state: "invoiced",
  facility: "Dallas Cold Storage",
  counterparty: "Coyote Logistics",
  notice_sent: true,
  filed: true,
  created_at: "2026-07-27T06:20:00+00:00",
  chain_valid: true,
  record_count: 12,
  artifact_count: 3,
  timeline: CLAIM_TIMELINE,
};
const CLAIM_OWED = { ...CLAIM_BASE, mode: "invoice" };
const CLAIM_EXPORT = { ...CLAIM_BASE, mode: "evidence_only", state: "exported" };
// the MC# pill renders only for a VERIFIED invoicing driver (F1), and it is the
// longest single line on the surface — which is the reason to measure it.
const VERIFIED_ME = { verified: true, mc_number: "1234567", authority_type: "own_mc" };

const FACILITY_ID = "00000000-0000-0000-0000-0000000000bb";
// AI-CONTEXT: the facility profile, which four states used to get from a FIXTURE
// (§23 entry 131). Their own comment said so — "deliberately renders from fixtures …
// the surface falls back to its fixtures exactly as it does today" — so for the life of
// this harness `facility`, `facility-prompt-mute`, `sheet-ask` and `sheet-review`
// measured an invented facility with an invented dock-time median. Removing the fixture
// turned all four into §15.4's failed line, which is what surfaced it.
//
// Shape copied from GET /facility/{id}/profile. `service-center` is explicitly NULL and
// not `{}`: an unclaimed facility returns null (M13-FR7), and a truthy object with no
// `services` array makes the surface's render THROW, which collapses every branch below
// it. That cost a debugging round in this session's unit tests; it is written down here
// so it does not cost another.
const FACILITY_PROFILE = {
  facility_id: FACILITY_ID,
  name: "Dallas Cold Storage",
  check_in_procedure: "Check in at guard shack; keep PPE on in the yard.",
  overnight_parking: true,
  restrooms: true,
  dwell: {
    overall: { median_seconds: 8100, p90_seconds: 15300, sample_size: 12 },
    by_hour: { 6: { median_seconds: 5400, sample_size: 4 } },
  },
  ratings: { overall: 3.8, review_count: 2, per_aspect: {} },
  detention_risk: { rate: null, sample_size: 0, basis: "m3_pending" },
  reviews: [
    { id: "r-1", ratings: { would_return: 4 }, text: "Quick unload at 6am, slow by afternoon.", created_at: "2026-08-01T10:00:00+00:00" },
  ],
};
const FACILITY_MOCKS = {
  [`/facility/${FACILITY_ID}/profile`]: FACILITY_PROFILE,
  [`/intel/detention-risk/${FACILITY_ID}`]: { exceed_rate: 0.43, sample_size: 14, confidence: "high", basis: "tracked_stops" },
  [`/intel/appointment-hours/${FACILITY_ID}`]: [{ hour: 6, median_seconds: 2400, sample_size: 9, confidence: "medium" }],
  [`/community/questions/${FACILITY_ID}`]: [
    { question_id: "q-1", text: "Is the north entrance still closed?",
      answers: [{ text: "Open as of this morning.", presence_proven: true }] },
  ],
  [`/vendors/service-center/${FACILITY_ID}`]: null,
};
// M10-FR2's relay feed, which came from `sampleHandoffs()`. Without it the banner never
// renders and `sheet-map-relay` has nothing to click — the sheet would have gone
// unmeasured rather than failing, had the state not carried an `open` step.
const HANDOFF_MOCKS = {
  "/community/handoff/nearby": [
    { handoff_id: "h-1", facility_name: "Love's Travel Stop #212", leaving_at: "2099-01-01T00:12:00+00:00", mine: false },
    { handoff_id: "h-2", facility_name: "Rest Area — I-35 NB", leaving_at: "2099-01-01T00:25:00+00:00", mine: false },
  ],
};

// AI-CONTEXT: the §18 portals, and why a LAW 0 harness measures them at 360 dp
// (§23 entry 132, audit U-04 + U-05).
//
// This file used to say "Portals are §18 and deliberately exempt from LAW 0 — they are
// not driver screens", and both halves of that are true. It does not follow that nothing
// here applies to them, and reading §18 closely is what settled it:
//
//   · LAW 0 is mobile-FIRST — design and build at 360 first, widen later. §18 exempts
//     portals from that ORDER, and nothing below tests order.
//   · §18's own text says portals are "responsive down to tablet/phone". So an owner
//     opening their board on a phone is a case §18 SPECIFIES, and "no horizontal
//     overflow at 360 dp" is that specification, checked.
//   · §6.2's type floor and §6.5's 48 dp target floor are in §6 and carry no portal
//     exemption. §18's only exemption sentence points the other way — it protects the
//     driver app FROM §18 ("Nothing in Section 18 ever justifies desktop-first thinking
//     in the driver app"), not the portals from §6.
//
// So all four checks are §6/§18 claims rather than LAW 0 claims, and the portals were
// simply the two surfaces where nobody had run them. That is exactly what U-04 found.
//
// They need mocks because both are on the four-state model now (§23 entry 131) — an
// unmocked portal renders §15.4's one error line, which would measure nothing.
const FLEET_ID = "00000000-0000-0000-0000-0000000000f1";
const FLEET_MOCKS = {
  "/fleet/mine": [{ fleet_id: FLEET_ID, name: "Cross-Country Freight", role: "owner" }],
  [`/fleet/${FLEET_ID}/report`]: {
    driver_count: 3,
    recovered_cents: 184000,
    owed_cents: 92500,
    fuel_saved_cents: 36250,
    // the longest member row the table can carry, because that is what overflows
    members: [
      { driver_account_id: "acc-1111-2222-3333", recovered_cents: 120000, owed_cents: 45000, fuel_saved_cents: 20000 },
      { driver_account_id: "acc-4444-5555-6666", recovered_cents: 64000, owed_cents: 47500, fuel_saved_cents: 16250 },
    ],
  },
  [`/fleet/${FLEET_ID}/claims`]: {
    owed_cents: 92500,
    recovered_cents: 184000,
    by_counterparty: { "Bolt Logistics": 52500, "Coyote Logistics": 40000 },
  },
};
const OWNER_MOCKS = {
  "/owner/dashboard": {
    payout_cents: 39600,
    properties: [
      {
        id: "p1",
        name: "Riverside Secured Parking",
        vetted: true,
        spots: [
          { id: "s1", label: "A1", price_cents_per_night: 2400, active: true },
          { id: "s2", label: "B2", price_cents_per_night: 2800, active: false },
        ],
      },
    ],
    bookings: [
      { id: "b1", nights: 2, price_cents: 4800, owner_payout_cents: 3960, state: "checked_out" },
      { id: "b2", nights: 1, price_cents: 2400, owner_payout_cents: 1980, state: "booked" },
    ],
  },
};

const SURFACES = [
  ["map", "/"],
  ["load", "/load"],
  // AI-CONTEXT: `/load/calc` had NO harness state at all — a full-screen form with five
  // number inputs and a Meter-treatment headline, never measured at 360 dp. Two states,
  // because the surface has two genuinely different shapes: opened with no load it shows
  // its own defaults, and opened from a load it prefills and gains a provenance caption
  // (§23 entry 85). `ready` proves the prefill rendered rather than measuring the empty
  // form twice under two names.
  ["load-calc", "/load/calc", { mocks: NO_LOAD_MOCKS, ready: ".cta" }],
  ["load-calc-prefilled", "/load/calc", {
    stop: LIVE_STOP, mocks: LIVE_MOCKS, ready: ".field__from",
  }],
  // `ready` is the selector that PROVES the mocked state rendered. Without it a
  // mock that stops matching turns this surface back into a second copy of `load`,
  // and the harness goes green over the screen it was added to measure — the same
  // failure as the run that measured Vite's error page six times.
  ["load-live", "/load", { stop: LIVE_STOP, mocks: LIVE_MOCKS, ready: ".rungs__item" }],
  ["money", "/money"],
  // AI-CONTEXT: the three SKELETON shapes, measured at 360 dp in the commit that
  // introduced them (§23 entry 131, v2.0 acceptance #3). A skeleton the harness cannot
  // render is a skeleton that ships unmeasured — and these are the first thing a driver
  // sees on every cold open, so "unmeasured" would mean the app's first frame at 360 dp
  // was the one frame nothing checked.
  //
  // `hang` holds the fetch open so the state persists; see the route handler. Each
  // `ready` selector names the SHAPE it is there to prove, so a state that stops
  // rendering its skeleton fails loudly instead of quietly measuring the loaded screen
  // under the loading state's name — the failure this file's fourth comment is about.
  //
  // Money covers TWO shapes in one load: the Meter card is replaced by SkeletonCard
  // while `/money/earnings` is in flight, and the receivables list by SkeletonRow while
  // `/accessorial/owed` is. `ready` is the card, because it is the one above the fold.
  ["money-loading", "/money", {
    hang: ["/money/earnings", "/accessorial/owed"],
    ready: ".skel__card",
  }],
  ["docs-loading", "/docs", { hang: ["/protection/wallet"], ready: ".skel__row" }],
  ["map-loading", "/", { hang: ["/map/overlay"], ready: ".skel__pin" }],
  // AI-CONTEXT: §11.5's CLUSTER bubbles, which no state had ever rendered (audit U-05).
  //
  // They only appear when the server clusters at density, and every map state here mocks
  // pins — so `.cluster` shipped unmeasured, and 119 found it at 36 dp by hand. It is the
  // first thing a driver sees at national span, which is where the app opens before GPS
  // resolves. Four counts including a four-digit one, because the bubble grows with its
  // number and the widest is the one that can overflow.
  ["map-clusters", "/", {
    mocks: {
      ...NO_LOAD_MOCKS,
      "/map/overlay": {
        clustered: true,
        total: 4821,
        pins: [],
        clusters: [
          { count: 7, lat: 32.9, lon: -96.9, status: "empty" },
          { count: 84, lat: 33.1, lon: -96.5, status: "some" },
          { count: 312, lat: 32.6, lon: -97.2, status: "full" },
          { count: 4821, lat: 33.4, lon: -97.6, status: null },
        ],
      },
      "/map/presets": { presets: ["drive", "tonight", "work", "fuel", "food", "service"] },
      "/community/handoff/nearby": [],
    },
    ready: ".cluster",
  }],
  // the two §18 portals — see the note above PORTAL mocks
  // AI-CONTEXT: the ACTIVE FLEET has to be planted or `init()` lands on the picker
  // instead of the workspace — `myFleets.find(f => f.fleet_id === activeFleetId)` is what
  // chooses between them, and `activeFleetId` is read from storage at module load. The
  // key lives under CACHE_PREFIX (U-02), so logout sweeps it. Without this the state
  // measures a two-row list under the workspace's name, which is the failure this file
  // keeps catching.
  ["fleet-portal", "/fleet", {
    mocks: FLEET_MOCKS,
    storage: { "longhaul.cache.active_fleet": FLEET_ID },
    ready: ".kpi__figure",
  }],
  ["owner-portal", "/owner", { mocks: OWNER_MOCKS, ready: ".payout__figure" }],
  // §23 entry 80: the sections collapse and start collapsed, so the grid is behind a
  // disclosure. Every state that reaches a document opens its section first —
  // otherwise the harness would measure three headings and report the surface covered.
  ["docs", "/docs", { mocks: WALLET_MOCKS, open: [".group__head"], ready: ".doc" }],
  // AI-CONTEXT: §13.5's landing state for the 30/14/3 expiry reminder. The deep link
  // opens the grid section and marks one document, so the marked row is measured at 360
  // dp under +40% — the mark is a border, which must not push the 88 dp tile's contents
  // into a reflow the unmarked tiles do not have.
  ["docs-reminder", "/docs?doc=00000000-0000-0000-0000-00000000000b", {
    mocks: WALLET_MOCKS,
    ready: ".doc--marked",
  }],
  // the two sections the wallet grew, measured in their own right
  ["docs-paperwork", "/docs", {
    mocks: WALLET_MOCKS,
    open: [{ click: ".group__head", nth: 1 }, { click: ".group__head", nth: 2 }],
    ready: ".paper__row",
  }],
  ["more", "/more"],
  // §23 entry 102: F8's inbox, the first surface that renders anything the
  // notification system decided. New sheet, so it gets measured at 360 dp with the
  // rest rather than shipping unseen. Mocked empty AND populated is overkill here —
  // the populated rows are what can overflow, so that is what is measured.
  ["sheet-notifications", "/more", {
    mocks: {
      "/notifications": {
        notifications: [
          {
            id: "n1", tier: "P0", category: "detention_started",
            title: "Detention started · $75/h", body: "Notice ready to send",
            deep_link: "/load", status: "sent", suppressed_reason: null,
            created_at: "2026-07-29T11:40:00Z", read_at: null,
          },
          {
            id: "n2", tier: "P1", category: "free_time_warning",
            title: "30 minutes of free time left", body: "Arrived 09:12",
            deep_link: "/load", status: "suppressed", suppressed_reason: "quiet_hours",
            created_at: "2026-07-29T09:00:00Z", read_at: "2026-07-29T09:05:00Z",
          },
        ],
        unread: 1,
      },
      // §23 entry 114: the class switch, which is the only way a driver can turn the
      // lot-status prompt on. It renders ONLY once the server has answered — an
      // unmocked route 404s here, and this state passed while measuring a sheet with no
      // switch in it before this mock existed.
      "/notifications/classes": {
        classes: [
          {
            key: "lot_status_prompt", opted_in: false, opt_in_default: false,
            max_per_day: 1, tier: "P1",
          },
        ],
      },
      // §23 entry 115: quiet hours. Same rule as the class switch above — the row
      // renders only once the server answers, and an unmocked route 404s here.
      "/notifications/prefs": {
        timezone: "America/Denver", quiet_start: "22:00", quiet_end: "06:00",
      },
    },
    open: [".alerts--link"],
    // the CONTROLS, not a row: the rows render from the inbox mock either way, and the
    // newly built things are what is worth proving present before anything is measured.
    // `:has()` twice, so this cannot go green with one of the two missing — which is
    // exactly how both shipped unmeasured in entry 114.
    ready: ".notif:has(.prompt-class):has(.quiet)",
  }],
  // `anon` because the door is only a door to someone who has no key — signed in, the
  // guard sends this state to the map and it measured the map (see prepare()).
  ["login", "/login", { anon: true, ready: ".auth__brand" }],
  // §23 entry 125 — the language chooser at the door. A new sheet, so it is measured
  // at 360 dp with the rest rather than shipping unseen, and this is the one list in
  // the product whose rows are NOT translated: ਪੰਜਾਬੀ and Русский render in their own
  // scripts whatever locale the sweep is running, which is exactly the row height and
  // glyph coverage that has to survive the +40% pseudo-locale.
  ["sheet-login-language", "/login", { anon: true, open: [".lang-btn"], ready: ".lang" }],
  ["evidence", "/load/00000000-0000-0000-0000-0000000000aa/evidence"],
  ["condition", "/protection/condition"],
  // `ready` is NEW. This state had none, so when the fixture went it kept passing while
  // measuring §15.4's one-line error instead of the facility — a silent coverage loss of
  // exactly the kind the note at the top of this file is about.
  ["facility", `/facility/${FACILITY_ID}`, { mocks: FACILITY_MOCKS, ready: ".dwell__figure" }],
  // §23 entry 114 — "don't ask about this lot". A separate state rather than mocks on
  // `facility` above, which deliberately renders from fixtures: this row appears only
  // after the server answers, so it needs an intercepted route to exist at all. Every
  // other call 404s and the surface falls back to its fixtures exactly as it does today.
  ["facility-prompt-mute", `/facility/${FACILITY_ID}`, {
    mocks: {
      ...FACILITY_MOCKS,
      [`/map/facility/${FACILITY_ID}/prompt-pref`]: { facility_id: FACILITY_ID, muted: false },
    },
    ready: ".prompt-mute",
  }],

  // the seven sheets (§8 NAV-3), each opened and measured where it actually renders
  ["sheet-more", "/load", {
    stop: LIVE_STOP, mocks: LIVE_MOCKS, open: [".rungs__item--more"], ready: ".more__item",
  }],
  ["sheet-history", "/load", {
    mocks: NO_LOAD_MOCKS, open: [".cta--text"], ready: ".hist__row",
  }],
  ["sheet-import", "/load", {
    mocks: NO_LOAD_MOCKS, open: [".cta:not(.cta--text)"], ready: ".rc__cta",
  }],
  ["sheet-bol", "/load", {
    stop: LIVE_STOP, mocks: LIVE_MOCKS, open: [".cta:not(.cta--text)"], ready: ".cap__input",
  }],
  ["sheet-inspection", "/docs", {
    mocks: WALLET_MOCKS, open: [".inspect"], ready: ".doc--inspect",
  }],
  ["sheet-capture", "/docs", {
    mocks: WALLET_MOCKS, open: [".capture"], ready: ".cap__chip",
  }],
  ["sheet-archive", "/docs", {
    mocks: WALLET_MOCKS, open: [".archive"], ready: ".arch__row",
  }],
  ["sheet-viewer", "/docs", {
    mocks: WALLET_MOCKS, open: [".group__head", ".doc"], ready: ".viewer__frame",
  }],
  // the rate-con CONFIRM step — the densest screen in the app and the one M4-FR4
  // exists for. Reaching it needs a file on the input before the read, so the step
  // list carries an upload as well as clicks.
  ["sheet-confirm", "/load", {
    mocks: { ...NO_LOAD_MOCKS, "/load/import": RATE_CON_DRAFT },
    open: [".cta:not(.cta--text)", { upload: ".rc__input" }, ".rc__cta"],
    ready: ".rc__match",
  }],
  // the OTHER half of the import: a rate con the parse could not read. It is a
  // different screen — no match list, no "read from your rate con", the manual form
  // carrying the whole load — and §12.4 gives it copy to get right at 360 dp.
  ["sheet-unreadable", "/load", {
    mocks: {
      ...NO_LOAD_MOCKS,
      "/load/import": { document_id: RATE_CON_DRAFT.document_id, parsed: null, silent_on: [], stops: [], readable: false },
    },
    open: [".cta:not(.cta--text)", { upload: ".rc__input" }, ".rc__cta"],
    ready: ".rc__unread",
  }],
  ["sheet-viewer-edit", "/docs", {
    mocks: WALLET_MOCKS, open: [".group__head", ".doc", ".viewer__edit"], ready: ".viewer__form",
  }],
  // removing a document is destructive-adjacent (§17 Q16 makes it reversible), and
  // §8 gives destructive actions their own confirm sheet — this is that sheet
  ["sheet-remove", "/docs", {
    mocks: WALLET_MOCKS, open: [".group__head", ".doc", ".viewer__remove"], ready: ".rm__go",
  }],
  ["sheet-incident", "/load", {
    stop: LIVE_STOP, mocks: LIVE_MOCKS,
    open: [".rungs__item--more", { click: ".more__item", nth: 1 }],
    ready: ".chips",
  }],
  ["sheet-ghostwriter", "/money", {
    // TWO controls carry `.audit-cta` — the settlement auditor routes away, the
    // ghostwriter opens the sheet. First-match would have measured /money/audit.
    mocks: MONEY_MOCKS, open: [{ click: ".audit-cta", nth: 1 }], ready: ".tone",
  }],
  // AI-CONTEXT: the mark-paid sheet is the THIRD `.audit-cta` on /money and renders
  // only when something is payable — both mocked receivables above are, so nth:2 is
  // stable. Measured here because a list of money figures at 200% is exactly the
  // T-5/T-6 reflow case, and 360 dp is where a two-column row runs out of width.
  ["bookings", "/bookings", {
    mocks: {
      "/parking/bookings": { bookings: [
        { id: "bk-1", property_name: "Riverside Secured Parking", spot_label: "A1", spot_id: "s-1",
          nights: 1, start_at: "2026-08-02T00:00:00+00:00", end_at: "2026-08-03T00:00:00+00:00",
          price_cents: 2400, state: "booked", refunded: false },
        { id: "bk-2", property_name: "Depot Overnight Lot", spot_label: "B2", spot_id: "s-2",
          nights: 2, start_at: "2026-07-10T00:00:00+00:00", end_at: "2026-07-12T00:00:00+00:00",
          price_cents: 4800, state: "refunded", refunded: true },
      ] },
    },
    ready: ".row",
  }],
  ["sheet-mark-paid", "/money", {
    mocks: MONEY_MOCKS, open: [{ click: ".audit-cta", nth: 2 }], ready: ".paid__submit",
  }],
  ["sheet-share", `/load/${EVIDENCE_STOP}/evidence`, {
    mocks: EVIDENCE_MOCKS, open: [".cta--secondary"], ready: "input[type='email']",
  }],
  ["sheet-ask", `/facility/${FACILITY_ID}`, {
    mocks: FACILITY_MOCKS, open: [".cta--ghost"], ready: ".sheet__body",
  }],
  ["sheet-review", `/facility/${FACILITY_ID}`, {
    mocks: FACILITY_MOCKS, open: [".add-review"], ready: ".sheet__body",
  }],
  ["sheet-map-report", "/", { mocks: {}, open: [".report-chip"], ready: ".sheet__body" }],
  ["sheet-map-voice", "/", { mocks: {}, open: [".voice-chip"], ready: ".sheet__body" }],
  // the sleep solver hangs off the Tonight preset, so the preset chip is step one
  ["sheet-map-sleep", "/", {
    mocks: {}, open: [{ click: ".chip", nth: 1 }, ".sleep-cta"], ready: ".sheet__body",
  }],
  ["sheet-map-relay", "/", { mocks: HANDOFF_MOCKS, open: [".relay-banner"], ready: ".sheet__body" }],
  // §10.1's contextual CTA ladder, one state per rung it can land on
  ["sheet-facility", "/", {
    mocks: mapMocks(TRUCK_STOP_PIN), open: [pinOf(TRUCK_STOP_PIN)], ready: ".cta--nav",
  }],
  ["sheet-facility-book", "/", {
    mocks: mapMocks(BOOKABLE_PIN), open: [pinOf(BOOKABLE_PIN)], ready: ".cta--book",
  }],
  ["sheet-facility-fuel", "/", {
    mocks: mapMocks(FUEL_PIN), open: [pinOf(FUEL_PIN)], ready: ".cta--fuel",
  }],
  // the rung §23 entry 82 added: this pin IS the armed stop, so the card leads with it
  ["sheet-facility-stop", "/", {
    mocks: mapMocks(ARMED_DOCK_PIN, { "/load/active": LIVE_MOCKS["/load/active"] }),
    open: [pinOf(ARMED_DOCK_PIN)],
    ready: ".cta--stop",
  }],
  // §11.4's saved-for-stop queue (§23 entry 83) — a new sheet, so it gets measured at
  // 360 dp with the rest rather than shipping unseen. Its state is client-side by
  // design (the tap that fills it happens where there may be no signal), so it is
  // seeded through `storage` rather than a mocked endpoint.
  ["sheet-map-saved", "/", {
    mocks: {},
    storage: {
      "longhaul.saved_for_stop": JSON.stringify([
        {
          id: "11111111-1111-1111-1111-111111111111",
          kind: "facility",
          label: "Yardline Secured Parking",
          payload: { facility_type: "parking_property", lat: 32.9, lon: -96.8 },
          at: 1753700000000,
        },
      ]),
    },
    open: [".saved-chip"],
    ready: ".saved__row",
  }],
  // A5: the Service preset's card, both halves. The second is not an edge case —
  // 28 of the 45 repair facilities have no phone number, so a card with no call
  // action is what most drivers will see, and it must not leave a hole in the layout.
  ["sheet-facility-service", "/", {
    mocks: mapMocks(REPAIR_PIN), open: [pinOf(REPAIR_PIN)], ready: ".fac__call",
  }],
  ["sheet-facility-service-nocontact", "/", {
    mocks: mapMocks(REPAIR_PIN_NO_CONTACT),
    open: [pinOf(REPAIR_PIN_NO_CONTACT)],
    ready: ".fac__services",
  }],
  // A6: the claimed card carries one more row than the A5 states above, and the name
  // it renders is a business's, not a token we chose — a long one is the realistic
  // case, so the pseudo-locale sweep measures the row that names it.
  ["sheet-facility-service-claimed", "/", {
    mocks: mapMocks(REPAIR_PIN_CLAIMED),
    open: [pinOf(REPAIR_PIN_CLAIMED)],
    ready: ".fac__claimed",
  }],
  // the sixth chip has to survive the +40% pseudo-locale in a row that already holds
  // five — the chips are icons, but the row's geometry is what this measures
  ["map-preset-service", "/", {
    mocks: mapMocks(REPAIR_PIN), open: [{ click: ".chip", nth: 5 }], ready: ".chip[aria-selected='true']",
  }],
  // AI-CONTEXT: A1's review CARD on the Load tab, and the sheet it opens.
  //
  // Measured because this lands on the densest driver screen in the product — §10.2 is
  // the Meter plus the stop context plus the evidence checklist — and because the card
  // is now a CARD rather than the one-line link it replaced, so it has real height to
  // earn at 360 dp before anything else on the tab gets its space back.
  //
  // The mock carries the worst realistic strings on purpose: a long facility name, a
  // long AP address, and the full contents list. At +40% under xx-XL that headline is
  // what wraps, and a review sheet is the last place a driver should meet clipped text.
  ["load-packet-ready", "/load", {
    mocks: { ...LIVE_MOCKS, "/protection/stop-packets": [PACKET_ROW] },
    stop: LIVE_STOP,
    ready: ".packet-card__cta",
  }],
  // the sheet, bundled: two labelled sections and one Send (owner decision 2026-08-02).
  // The CLAIM section is the taller of the two shapes — it adds a Mono figure — so the
  // bundled state is the one measured rather than the packet-only one.
  ["load-packet-review", "/load", {
    mocks: {
      ...LIVE_MOCKS,
      "/protection/stop-packets": [
        { ...PACKET_ROW, claim: { id: "c-1", state: "filed", amount_cents: 128750 } },
      ],
    },
    stop: LIVE_STOP,
    open: [".packet-card__cta"],
    ready: ".review__send",
  }],
  // AI-CONTEXT: the WORST-CASE Load stack, which is the densest screen this product can
  // put in front of a driver (audit U-04-adjacent, PRD v2.0 §8 criterion 3).
  //
  // `LoadSurface` renders up to six independent blocks, each behind its own `v-if`:
  // the packet card, the degraded-location banner, the hint, the context row, the Meter
  // card and the evidence checklist. The states above register those SEPARATELY, and a
  // surface measured one block at a time is not the same as a surface measured with
  // every block on at once — a driver with an active stop, waiting paperwork and denied
  // location gets all of them, stacked above the Meter, on a 360 dp screen.
  //
  // TWO THINGS THIS FOUND, both worth more than the state itself:
  //
  // 1. The combination was ALREADY being rendered, by `load-packet-ready` — because
  //    Playwright denies geolocation, so `locationDenied` is true in every Load state
  //    (see the note at the top of this file). The coverage was real and ACCIDENTAL:
  //    nothing in that state's name, definition or `ready` selector said the degraded
  //    banner was on screen, so the day someone grants geolocation in a context option
  //    the stack silently loses a card and every assertion still passes. That is the
  //    exact evaporation this file's own comment predicted.
  //
  // 2. Which is why this `ready` proves ALL THREE cards with one `:has()` chain rather
  //    than waiting on any single one. A state that can go green having rendered two of
  //    the three is a second copy of `load-packet-ready` wearing a different name.
  ["load-worst-case", "/load", {
    mocks: { ...LIVE_MOCKS, "/protection/stop-packets": [PACKET_ROW] },
    stop: LIVE_STOP,
    ready: ".load:has(.packet-card):has(.degraded):has(.meter-card):has(.checklist__snap)",
  }],
  // A1 req 1: the capture sheet reached from a checklist ROW rather than the Snap BOL
  // CTA. The row is a 48 dp target inside §10.2's densest card, and the sheet it opens
  // is type-fixed — the state exists to measure both at 360 with the glove spec.
  ["load-checklist-capture", "/load", {
    mocks: LIVE_MOCKS,
    stop: LIVE_STOP,
    open: [".checklist__snap"],
    ready: ".cap__field",
  }],
  // A1 req 5's review screen — a new surface, so it is measured at 360 dp with the rest
  // rather than shipping unseen. Two states because the EMPTY one is what most drivers
  // see most days, and §15.3 gives it a sentence rather than a blank page.
  ["packets-review", "/protection/packets", {
    mocks: {
      "/protection/stop-packets": [
        {
          id: "11111111-1111-1111-1111-111111111111",
          state: "draft",
          drafted_at: "2026-08-01T12:00:00+00:00",
          reference: "BL-77421",
          recipient: "accountspayable@boltlogistics.example",
          counterparty_name: "Bolt Logistics",
          facility_name: "Midwest Distribution Center — Dock 4",
        },
      ],
    },
    ready: ".packet__send",
  }],
  ["packets-review-empty", "/protection/packets", {
    mocks: { "/protection/stop-packets": [] },
    ready: ".packets__empty",
  }],
  // §23 entry 99's "somewhere else" sheet — a new sheet, so it gets measured at
  // 360 dp with the rest rather than shipping unseen. The chip that opens it renders
  // only when NOT driving (Forbidden #11), which is the default state here.
  ["sheet-map-place", "/", {
    mocks: {},
    open: [".place-chip"],
    ready: ".place__input",
  }],
  // M5-FR1's correction (§23 entry 62) — a new sheet, so it gets measured with the
  // rest rather than shipping unseen at 360 dp
  ["sheet-appointment", "/load", {
    stop: LIVE_STOP, mocks: LIVE_MOCKS, open: [".context__fix"], ready: ".appt__input",
  }],

  // AI-CONTEXT: audit U-04 — six surfaces had no harness entry at all. PRD v2.0 §8
  // acceptance 3 requires every surface registered "in the same commit that creates
  // it", and these predate the rule.
  //
  // CLAIMSURFACE IS THE ONE THAT MATTERS, and it is first for that reason. §13.5
  // forbids a notification deep-linking to a tab root and `dispatch` refuses to send
  // without one, so EVERY detention alert this product sends lands here — on a screen
  // that had never been measured at 360 × 800 under +40% type, while the surfaces a
  // driver navigates to themselves have been, some in four separate states.
  //
  // Two states, because the two modes are genuinely different screens rather than one
  // screen with a different word in it: `invoice` shows money owed and the verified
  // MC# pill, `evidence_only` shows an exported pack and no pill at all (M3-FR9 — a
  // company driver cannot bill anyone). The `ready` selectors prove WHICH one rendered,
  // so a mock that stops matching cannot quietly measure the same state twice.
  ["claim-owed", `/claim/${LIVE_STOP}`, {
    mocks: { ...LIVE_MOCKS, [`/load/${LIVE_STOP}/claim`]: CLAIM_OWED, "/auth/me": VERIFIED_ME },
    ready: ".hero--owed .authpill",
  }],
  ["claim-evidence-only", `/claim/${LIVE_STOP}`, {
    mocks: { ...LIVE_MOCKS, [`/load/${LIVE_STOP}/claim`]: CLAIM_EXPORT, "/auth/me": VERIFIED_ME },
    ready: ".hero--export",
  }],
  // §15.3: a stop with no claim is the common case for this route, and it must be a
  // sentence rather than a blank screen. Measured because "absent, never empty" is a
  // layout claim as much as a copy one.
  ["claim-none", `/claim/${LIVE_STOP}`, {
    // NOT a `__status` key — the harness already 404s any path it has no body for
    // (see the route handler below), and a `{__status:404}` object would be fulfilled
    // as a 200 carrying that object, rendering a claim with undefined fields under the
    // name of the empty state.
    mocks: { ...LIVE_MOCKS, "/auth/me": VERIFIED_ME },
    ready: ".claim .muted",
  }],

  // M9's settlement audit and M7/M6's two action screens. All three read their subject
  // from the ROUTE rather than from a fetch, so they need no mock — which is also why
  // nothing was stopping them being measured, and why they were not.
  ["money-audit", "/money/audit", { mocks: {}, ready: ".fields .field__input" }],
  ["fuel-code", "/fuel/00000000-0000-0000-0000-0000000000f1?name=Pilot%20%23412&gross=419&net=394&savings=25", {
    mocks: {}, ready: ".fuel__head",
  }],
  ["booking", "/book/00000000-0000-0000-0000-0000000000c1?name=Yardline%20Lot&nightly=2400", {
    mocks: {}, ready: ".book__head",
  }],
  // The public scorecard is §18 web-first and LAW 0 still has no portal exemption
  // written into it, so it is measured at 360 like everything else. It passes as it
  // stands — it carries no target under 48 dp.
  //
  // FleetWorkspaceSurface and OwnerPortalSurface are DELIBERATELY still absent, and
  // this is the reason: both carry 40 dp controls, which are precisely the two targets
  // HANDOFF-119 §5.1 item 3 put to the owner — "applying the glove floor to a desktop
  // form is a design decision, not a fix". Adding them here would either fail CI or
  // decide that question by writing CSS, so they wait on the decision rather than
  // pre-empting it. U-04 is closed to the extent an agent can close it.
  ["scorecard", "/scorecard", { mocks: {}, ready: ".score__title" }],
];
const CAPTION_FLOOR_PX = 13; // §6.2: "Nothing smaller exists."
const TOUCH_MIN_PX = 48; // §6.5 glove spec
const MAP_TARGET_MIN_PX = 44; // §11.2, the deliberate map exemption — and its FLOOR
// the map markers §11.2 governs, held to 44 by the check above rather than merely
// excused from 48 by TARGET_EXEMPT below
const MAP_TARGET = /(^|\s)(pin|cluster)(\s|$)/;
// The tab bar is a fixed 5-across strip: at 360 dp each tab is 72 dp wide and the
// spec sets its own height. Individual icons inside it are not separate targets.
const TARGET_SELECTOR = "button, a[href], [role='button'], input, select";

// AI-CONTEXT: two documented exemptions, both established by reading the
// constitution AFTER the harness flagged them — neither is a defect being waved
// through.
//
// · MAP PINS: §11.2 sets them at "44 dp hit areas regardless of visual size",
//   deliberately and against §6.5's general 48. A denser tap grid is the point of a
//   map. The specific rule wins over the general one.
// · CLUSTER BUBBLES: the same rule and the same reason (audit U-05, §23 entry 133). A
//   cluster is a map marker; §11.2 governs it. It was 36 dp with NO expanded hit area —
//   below even the exemption — and is a 44 dp button around a 36 dp bubble now, which is
//   the shape `.pin` already had. The `map-clusters` state renders them so this is
//   measured rather than asserted.
// · MAPBOX CONTROLS: `mapboxgl-ctrl-*` is third-party furniture injected by the map
//   library, and the attribution button and logo are required by Mapbox's terms —
//   they are not ours to resize, and hiding them would breach the licence.
const TARGET_EXEMPT = /(^|\s)(pin|cluster|mapboxgl-ctrl[\w-]*|mapboxgl-ctrl-logo)(\s|$)/;

// AI-CONTEXT: the harness has to be SIGNED IN, and finding that out was the first
// thing it taught us. Unauthenticated, the router guard sends every route to /login,
// so the first run tested the login screen six times and reported it as six
// surfaces. A layout harness that silently checks one page while naming six is worse
// than none — it would have gone green over anything.
//
// The session is planted directly in storage rather than driven through the form:
// this suite is testing LAYOUT, and making it depend on a live API would mean a
// failing backend reads as a layout defect.
async function prepare(page, { theme, pseudo, live }) {
  // a surface that needs server state gets it CANNED, never from the API — see the
  // note on LIVE_MOCKS. Anything the surface asks for that is not mocked 404s, so a
  // route the mock forgot shows up as a missing element rather than as live data.
  if (live) {
    await page.route(`${API_BASE}/**`, (route) => {
      const path = new URL(route.request().url()).pathname;
      // AI-CONTEXT: `hang` is how a LOADING state gets measured (§23 entry 131).
      //
      // A skeleton only exists while a fetch is in flight, so the only way to put one
      // in front of these assertions is to never answer. The request is left PENDING —
      // not delayed, because a delay resolves and the skeleton then vanishes before the
      // checks run, and not a 404, because that is the FAILED state and a different
      // screen. `settle()` knows to skip its networkidle wait for these states, since a
      // pending request means the network is never idle by construction.
      if (live.hang?.some((frag) => path.includes(frag))) return; // never fulfilled
      const body = live.mocks?.[path];
      if (!body) return route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
      if (body.__binary) {
        return route.fulfill({
          status: 200,
          contentType: body.__binary.contentType,
          body: Buffer.from(body.__binary.base64, "base64"),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    });
  }
  // AI-CONTEXT: ...and the session the note above plants is why `login` was never
  // measured (§23 entry 125). The guard sends a SIGNED-IN visitor away from /login —
  // `to.name === "login" && isAuthenticated` returns `{name: "map"}` — so the state
  // called "login" loaded the MAP and reported it under the login screen's name, in
  // all three locales, for the life of this harness. Measured, not deduced: with the
  // planted session `/login` resolves to `/map`, `.auth__brand` count 0, map canvas
  // count 1; without it, `.auth__brand` count 1.
  //
  // The same shape as the note above it, one turn later: that fix made five surfaces
  // reachable and made this one unreachable, and nothing failed either way. A state
  // may now opt OUT of the session, which is the only way to measure the door.
  await page.addInitScript(
    ([t, p, stop, storage, anon]) => {
      try {
        localStorage.setItem("longhaul.theme", t);
        // U-02: this key moved under `longhaul.cache.` so that logout's clearCache()
        // sweeps it — a phone passed between team drivers was handing the next one the
        // previous driver's active stop. The harness plants it directly, so it has to
        // move with api.js or every `stop:` state below quietly measures the EMPTY Load
        // tab again, which is the four-session failure this file was written to end.
        if (stop) localStorage.setItem("longhaul.cache.active_stop", stop);
        if (p === "xx-XL") localStorage.setItem("longhaul.locale", "xx-XL");
        else if (p) localStorage.setItem("longhaul.locale", p);
        // AI-CONTEXT: some states live in storage rather than behind an endpoint —
        // §11.4's saved-for-stop queue is client-side by design, because the tap that
        // fills it happens where there may be no signal. Without this the sheet could
        // not be OPENED by the harness, and a sheet the harness cannot open is a sheet
        // that ships unmeasured at 360 dp.
        for (const [k, v] of Object.entries(storage || {})) localStorage.setItem(k, v);
        if (anon) localStorage.removeItem("longhaul.session");
        else
          localStorage.setItem(
            "longhaul.session",
            JSON.stringify({
              token: "layout-harness",
              account_id: "00000000-0000-0000-0000-000000000001",
              email: "harness@example.com",
            }),
          );
      } catch {
        /* storage unavailable */
      }
    },
    [theme, pseudo, live ? live.stop : null, live ? live.storage : null, live ? !!live.anon : false],
  );
}

async function settle(page, live) {
  // a state that deliberately holds a request open never reaches networkidle, so
  // waiting for it would burn the timeout on every such state and then proceed anyway.
  // The `ready` selector is what proves the skeleton rendered.
  if (!live?.hang) await page.waitForLoadState("networkidle").catch(() => {});
  // the map canvas initialises asynchronously and has no layout contribution here.
  // 250 ms also clears the skeleton's own 200 ms delay (core/skeleton.js), which is
  // why a hanging state needs no extra wait of its own.
  await page.waitForTimeout(250);
  // drive the surface into the state it names — opening a sheet, usually. CSS only,
  // never labels: three locales run per surface and a text step would stop matching
  // in two of them.
  for (const step of (live && live.open) || []) {
    if (step.upload) {
      await page.locator(step.upload).first().setInputFiles({
        name: "rate-con.png",
        mimeType: "image/png",
        buffer: Buffer.from(PNG_1PX, "base64"),
      });
    } else if (step.click) {
      // `nth` for rows in a list that share a class — index, not label, for the
      // same locale reason the steps are CSS in the first place
      await page.locator(step.click).nth(step.nth ?? 0).click();
    } else {
      await page.locator(step).first().click();
    }
    await page.waitForTimeout(150);
  }
  // a mocked surface must PROVE it rendered the state it names before anything is
  // measured against it. Silence here is the failure mode that kept the live Load
  // tab unmeasured for four sessions.
  if (live && live.ready) {
    // 15 s is a BACKSTOP, not a tolerance, and the difference is the whole point.
    //
    // MEASURED, across a full 181-state sweep at four workers: the slowest `ready`
    // in the suite resolves in 80 ms, and the map states everyone suspects — the
    // ones that "timed out" — sit at 29-39 ms. The budget is ~190x the worst wait
    // ever observed. Nothing here is marginal.
    //
    // So a timeout at 15 s does NOT mean "the machine was busy". A wait that is
    // normally 39 ms does not become 15 000 ms under load; it becomes 80 ms. It
    // means the selector NEVER ATTACHED — the app did not mount, or an `open` step
    // clicked something whose handler was not wired, or the surface is genuinely
    // broken. HANDOFF-108 §5 proposed raising this budget again; raising it would
    // only make the same failure take twice as long to report, which is why the
    // number is unchanged and this comment replaced the reasoning instead.
    //
    // What DID change: the failure now says which of those it was. A check that
    // cannot explain itself is a check people learn to ignore, and two sessions
    // guessing at "flake" is what that looks like.
    try {
      await page.waitForSelector(live.ready, { state: "attached", timeout: 15_000 });
    } catch {
      throw new Error(await readyDiagnosis(page, live));
    }
  }
}

// AI-CONTEXT: turns a `ready` timeout from a guess into a finding.
//
// Only two verdicts, because only two are supported by what the DOM can show. An
// unmounted #app is unambiguous: the dev server or a boot error, never load. Anything
// else means the app booted and the named surface still did not open, which is a
// defect — the same wait is tens of milliseconds in a healthy run.
//
// The open-step census is reported as EVIDENCE, never as a third verdict. A step
// target missing at diagnosis time proves nothing on its own: `click()` would already
// have thrown its own error had the target been absent when it mattered, and a chip
// that is legitimately replaced by the sheet it opens is absent here for an innocent
// reason. Naming that "the surface changed under the harness" would be the same
// confident-and-unchecked reasoning §5 already cost two sessions.
async function readyDiagnosis(page, live) {
  const steps = (live.open || []).map((s) => s.click || s.upload || s);
  const seen = await page.evaluate(
    ([sels, readySel]) => {
      const root = document.querySelector("#app");
      return {
        url: location.href,
        mounted: !!(root && root.childElementCount),
        bodyEls: document.querySelectorAll("body *").length,
        steps: sels.map((s) => [s, document.querySelectorAll(s).length]),
        ready: document.querySelectorAll(readySel).length,
      };
    },
    [steps, live.ready],
  );
  if (!seen.mounted) {
    return `ready "${live.ready}" never attached and #app NEVER MOUNTED (${seen.bodyEls} elements on ${seen.url}) — the app did not boot. Suspect the dev server or a runtime error, NOT load.`;
  }
  const census = seen.steps.length
    ? seen.steps.map(([s, n]) => `${s}=${n}`).join(", ")
    : "(no open steps)";
  return `ready "${live.ready}" never attached (count ${seen.ready}) though #app mounted with ${seen.bodyEls} elements on ${seen.url}. The named surface did not open. This is a DEFECT, not load: the slowest ready in the whole sweep is 80 ms against a 15 s budget. Open-step targets at failure: ${census}.`;
}

// AI-CONTEXT: the theme dimension was REMOVED on evidence, not on a hunch.
//
// It was also broken: `theme.js` keeps the mode in a ref and never persists it, so
// the `longhaul.theme` key this harness had been setting for two sessions was read
// by nothing, and only one of four assertions ever stamped `data-theme` itself. The
// dimension had been running the same theme twice.
//
// Then, measured properly across all six surfaces under a correctly applied dark and
// light: geometry was IDENTICAL on five, and the single difference was a font size
// inside Mapbox's own attribution furniture, which is exempt anyway. That matches
// §23's light-theme entry exactly — "Only the 12 color tokens change;
// type/space/radius/motion/touch are theme-invariant" — so none of these assertions
// CAN vary by theme, by constitutional decision rather than by luck. Contrast, the
// genuinely theme-sensitive property, is computed from tokens in contrast.test.js.
//
// The budget went to surfaces instead, which is the dimension that finds bugs.
// AI-CONTEXT: ONE PAGE LOAD PER STATE, not one per assertion.
//
// This ran five `test()` blocks per surface-variant and every one of them did its own
// `prepare` + `goto` + `settle` — five identical page loads to ask five questions of
// the same screen. 40 states x 3 locales x 5 = 600 navigations, plus 80 more at 200%,
// for a suite that measures 40 screens. It took eleven minutes, and a check that slow
// stops being run, which costs more than any assertion in it can pay back.
//
// The rules are unchanged and so is their number. They are `expect.soft`, so a screen
// that breaks three of them still reports all three from a single load rather than
// hiding the second and third behind the first.
const CHECKS = [
  {
    name: "no horizontal overflow at 360 dp",
    async run(page) {
      const overflow = await page.evaluate(() => {
        const doc = document.documentElement;
        const offenders = [];
        for (const el of document.querySelectorAll("body *")) {
          const r = el.getBoundingClientRect();
          if (r.width === 0 || r.height === 0) continue;
          // 1 px of tolerance: sub-pixel rounding is not a layout defect
          if (r.right > doc.clientWidth + 1 || r.left < -1) {
            // an element that scrolls its own overflow is doing so ON PURPOSE
            // (the preset chip row, the portal rail) — that is a pattern the
            // constitution approves, not a break.
            //
            // AI-CONTEXT: this walks ANCESTORS now, and used to check only the
            // immediate parent (§23 entry 132). The comment above states the intent
            // correctly; the one-level implementation was an incomplete expression of
            // it. It happened to work for the cases it was written against — a chip
            // row is `.row > .chip`, one level — and could not work for a TABLE, which
            // is `table > thead > tr > th`: wrapping the table in a scroller exempted
            // the table and still reported every cell inside it.
            //
            // This cannot hide a real MF-2 break, and that is the load-bearing part:
            // the `doc.scrollWidth > doc.clientWidth` assertion below is untouched, so
            // a page that actually scrolls sideways still fails whatever any element
            // declares. What changed is only whether a cell INSIDE a deliberate
            // scroller is reported as a page-level defect.
            let inScroller = false;
            for (let n = el; n && n !== document.body; n = n.parentElement) {
              if (["auto", "scroll"].includes(getComputedStyle(n).overflowX)) {
                inScroller = true;
                break;
              }
            }
            if (!inScroller) {
              offenders.push(`${el.tagName.toLowerCase()}.${el.className} @${Math.round(r.right)}`);
            }
          }
        }
        if (doc.scrollWidth > doc.clientWidth + 1) {
          offenders.push(`document scrolls ${doc.scrollWidth}>${doc.clientWidth}`);
        }
        return offenders;
      });
      return [overflow, `elements past 360 dp: ${overflow.join(" | ")}`];
    },
  },
  {
    name: "nothing below the 13 dp type floor",
    async run(page) {
      const small = await page.evaluate((floor) => {
        const found = [];
        for (const el of document.querySelectorAll("body *")) {
          if (!el.textContent || !el.textContent.trim()) continue;
          // AI-CONTEXT: Mapbox's own furniture is not our type scale.
          //
          // Every OTHER check here already skips `mapboxgl-*`; this one never did, so
          // `mapboxgl-map` and the compact attribution — all 12px, all injected by the
          // library — failed §6.2 the moment GL got far enough to render them. It was
          // LATENT: WebGL init is unreliable in the container, so it passed four
          // consecutive runs before failing the fifth with nothing changed. A harness
          // that fails on a coin flip teaches everyone to re-run rather than look.
          //
          // `.mapboxgl-map` is the container the library takes over; our own pins are
          // siblings of it inside `.canvas`, so nothing of ours is exempted.
          if (el.closest(".mapboxgl-map")) continue;
          const r = el.getBoundingClientRect();
          if (r.width === 0 || r.height === 0) continue;
          const size = parseFloat(getComputedStyle(el).fontSize);
          if (size && size < floor) {
            found.push(`${el.tagName.toLowerCase()}.${el.className} @${size}px`);
          }
        }
        return found;
      }, CAPTION_FLOOR_PX);
      return [small, `§6.2 says nothing smaller than 13 dp exists: ${small.join(" | ")}`];
    },
  },
  {
    name: "text is not clipped by its line box",
    async run(page) {
      await page.evaluate(() => document.fonts && document.fonts.ready);
      const clipped = await page.evaluate(() => {
        const found = [];
        for (const el of document.querySelectorAll("body *")) {
          if (!el.childElementCount && el.textContent && el.textContent.trim()) {
            const style = getComputedStyle(el);
            if (style.overflow === "visible") continue; // nothing to clip against
            if (el.scrollHeight > el.clientHeight + 1) {
              found.push(`${el.tagName.toLowerCase()}.${el.className} ${el.scrollHeight}>${el.clientHeight}`);
            }
          }
        }
        return found;
      });
      return [clipped, `clipped text: ${clipped.join(" | ")}`];
    },
  },
  {
    // AI-CONTEXT: the assertion with the best odds of paying for its runtime. A
    // <button> with no handler is the FIFTH instance of one bug class in this project:
    // the "suggest a cook" control with no destination, `categories` collected and
    // never read, `portions` carried through three API layers to nowhere,
    // `followers_notified` returned and rendered nowhere, and the Docs capture chip.
    // The near side of a seam gets built, the far side does not, and every one of
    // those passes review — the code looks finished from whichever side you read it.
    //
    // A control that reports nothing when pressed is worse than an absent one: it
    // spends the driver's trust. §23 settled the principle for the module registry —
    // a capability whose destination does not exist is LABELLED, never linked — and
    // this is that rule, enforced. `disabled` is an acceptable answer: saying "not
    // yet" is honest; saying nothing is not.
    name: "every control does something, or says it cannot",
    async run(page) {
      const inert = await page.evaluate(() => {
        const found = [];
        for (const el of document.querySelectorAll("button")) {
          const r = el.getBoundingClientRect();
          if (!r.width || !r.height) continue;
          if (el.disabled || el.getAttribute("aria-disabled") === "true") continue;
          // a <button type=submit> inside a form acts through the form
          if (el.type === "submit" && el.closest("form")) continue;
          // Vue compiles @click to a listener; getEventListeners is devtools-only, so
          // the reliable signal is the framework's own bookkeeping on the node
          const vue = el.__vnode || el.__vueParentComponent;
          const props = vue && vue.props;
          const hasVueHandler = !!(
            props &&
            Object.keys(props).some((k) => /^on[A-Z]/.test(k) && typeof props[k] === "function")
          );
          const hasDomHandler = typeof el.onclick === "function";
          // Mapbox attaches its listeners imperatively, so neither Vue's bookkeeping
          // nor `onclick` can see them. Same exemption, same reason: not our furniture.
          if (el.closest(".mapboxgl-ctrl") || /mapboxgl/.test(el.className)) continue;
          if (!hasVueHandler && !hasDomHandler && !el.closest("a[href]")) {
            found.push(`${el.className || el.tagName.toLowerCase()}: "${(el.textContent || "").trim().slice(0, 32)}"`);
          }
        }
        return found;
      });
      return [inert, `controls that do nothing when pressed: ${inert.join(" | ")}`];
    },
  },
  {
    // AI-CONTEXT: the exemption above needed a FLOOR, and without one it was a hole
    // (§23 entry 133). `pin` and `cluster` are exempt from §6.5's 48 dp because §11.2
    // sets map markers at "44 dp hit areas regardless of visual size" — but nothing
    // then checked the 44, so the exemption was really "map markers are unmeasured".
    // Audit U-05 is the proof: `.cluster` sat at 36 dp, below even its own exemption,
    // and no automated check could see it.
    //
    // Written the moment `cluster` joined the exempt list, because adding a name to
    // that regex is exactly how a target stops being measured.
    name: "map markers meet §11.2's 44 dp hit area",
    async run(page) {
      const tooSmall = await page.evaluate(
        ([selector, min, exempt]) => {
          const found = [];
          for (const el of document.querySelectorAll(selector)) {
            if (!new RegExp(exempt).test(el.className)) continue; // not a map marker
            if (el.closest(".mapboxgl-ctrl")) continue; // third-party furniture
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            if (getComputedStyle(el).visibility === "hidden") continue;
            if (r.height < min - 0.5 || r.width < min - 0.5) {
              found.push(
                `${el.tagName.toLowerCase()}.${el.className} ${Math.round(r.width)}x${Math.round(r.height)}`,
              );
            }
          }
          return found;
        },
        [TARGET_SELECTOR, MAP_TARGET_MIN_PX, MAP_TARGET.source],
      );
      return [tooSmall, `§11.2 map hit area — under 44 dp: ${tooSmall.join(" | ")}`];
    },
  },
  {
    name: "interactive targets meet the glove spec",
    async run(page) {
      const tooSmall = await page.evaluate(
        ([selector, min, exempt]) => {
          const found = [];
          for (const el of document.querySelectorAll(selector)) {
            let r = el.getBoundingClientRect();
            // AI-CONTEXT: a radio or checkbox is a GLYPH inside its target. The browser
            // delivers the tap to the enclosing <label>, so that is what §6.5 governs —
            // the rate-con facility radios render 13x13 inside labels measuring 328x48,
            // and reporting the glyph would have sent someone to inflate a control that
            // is already reachable.
            //
            // Narrowed to radio/checkbox deliberately. NOT a general "labels count"
            // rule: a text input inside a label would borrow the caption's height and a
            // genuinely short field would pass. A radio with no label, or one in an
            // undersized label, still fails here.
            if (el.tagName === "INPUT" && (el.type === "radio" || el.type === "checkbox")) {
              const label = el.closest("label");
              if (label) r = label.getBoundingClientRect();
            }
            if (r.width === 0 || r.height === 0) continue; // not rendered
            if (getComputedStyle(el).visibility === "hidden") continue;
            if (new RegExp(exempt).test(el.className) || el.closest(".mapboxgl-ctrl")) continue;
            if (r.height < min - 0.5 || r.width < min - 0.5) {
              found.push(
                `${el.tagName.toLowerCase()}.${el.className} ${Math.round(r.width)}x${Math.round(r.height)}`,
              );
            }
          }
          return found;
        },
        [TARGET_SELECTOR, TOUCH_MIN_PX, TARGET_EXEMPT.source],
      );
      return [tooSmall, `§6.5 glove spec — under 48 dp: ${tooSmall.join(" | ")}`];
    },
  },
];

for (const [name, path, live] of SURFACES) {
  const theme = "dark";
  // `pa` joins the matrix because §6.2's "metrics-compatible line-height tokens
  // verified" is a LAYOUT claim, and this harness is the only thing that can answer
  // it. Gurmukhi carries matras above AND below the baseline, so a line height tuned
  // for Latin is exactly the kind of thing that clips silently — and "verified" was
  // asserted in the constitution without anyone rendering it.
  for (const pseudo of [false, "xx-XL", "pa"]) {
    const label = `${name}${pseudo ? ` · ${pseudo}` : ""}`;

    test(`${label} — §22.3 layout rules`, async ({ page }) => {
      await prepare(page, { theme, pseudo, live });
      await page.setViewportSize({ width: 360, height: 800 });
      await page.goto(`${BASE}${path}`);
      await settle(page, live);
      // stamped once for the whole load. It used to be stamped inside the first
      // assertion only, so the other four measured whatever the system happened to
      // prefer — harmless, because §23 makes type/space/radius theme-invariant, but
      // it was never the intent.
      await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);

      for (const check of CHECKS) {
        const [offenders, message] = await check.run(page);
        expect.soft(offenders, `${check.name} — ${message}`).toEqual([]);
      }
    });
  }
}

// AI-CONTEXT: T-5 / §16 — user font-scaling honored to 200%, "layouts reflow, rows
// grow, nothing clips or truncates."
//
// This box on the §22.3 checklist was ticked for months and could not have been true:
// every type token was declared in `px`, and px is immune to OS and browser
// font-scaling. A driver who set their phone to large text got the same 13 dp captions
// as everyone else. The tokens are `rem` now (§23 entry 63), which is what makes this
// assertion mean something instead of passing vacuously.
//
// Deliberately TWO assertions rather than the full five-per-locale matrix: T-5 and T-6
// promise reflow and no clipping, and those are the two that can actually break when
// the type doubles. Running all five across three locales again would triple the
// runtime of the slowest thing in CI to re-answer questions the 100% pass already
// answered.
const ROOT_200_PERCENT = "32px"; // the 16 px default, doubled — what the OS knob does

async function at200(page, path, live) {
  await prepare(page, { theme: "dark", pseudo: false, live });
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto(`${BASE}${path}`);
  await settle(page, live);
  await page.evaluate((size) => {
    document.documentElement.style.fontSize = size;
  }, ROOT_200_PERCENT);
  await page.waitForTimeout(150); // let the reflow settle before measuring it
}

for (const [name, path, live] of SURFACES) {
  test(`${name} · 200% — reflow and clipping (T-5/T-6)`, async ({ page }) => {
    await at200(page, path, live);
    await page.evaluate(() => document.fonts && document.fonts.ready);

    const [offenders, clipped] = await page.evaluate(() => {
      const doc = document.documentElement;
      const past = [];
      const clip = [];
      for (const el of document.querySelectorAll("body *")) {
        const r = el.getBoundingClientRect();
        if (r.width !== 0 && r.height !== 0 && (r.right > doc.clientWidth + 1 || r.left < -1)) {
          // ancestor-aware, for the reason spelled out in CHECKS' overflow rule
          let inScroller = false;
          for (let n = el; n && n !== document.body; n = n.parentElement) {
            if (["auto", "scroll"].includes(getComputedStyle(n).overflowX)) {
              inScroller = true;
              break;
            }
          }
          if (!inScroller) {
            past.push(`${el.tagName.toLowerCase()}.${el.className} @${Math.round(r.right)}`);
          }
        }
        if (!el.childElementCount && el.textContent && el.textContent.trim()) {
          const style = getComputedStyle(el);
          if (style.overflow !== "visible" && el.scrollHeight > el.clientHeight + 1) {
            clip.push(`${el.tagName.toLowerCase()}.${el.className} ${el.scrollHeight}>${el.clientHeight}`);
          }
        }
      }
      return [past, clip];
    });

    expect.soft(offenders, `past 360 dp at 200% text: ${offenders.join(" | ")}`).toEqual([]);
    expect.soft(clipped, `clipped at 200% text: ${clipped.join(" | ")}`).toEqual([]);
  });
}
