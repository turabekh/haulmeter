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

// every driver-app surface. Portals are §18 and deliberately exempt from LAW 0 —
// they are not driver screens.
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
  // §23 entry 80: the sections collapse and start collapsed, so the grid is behind a
  // disclosure. Every state that reaches a document opens its section first —
  // otherwise the harness would measure three headings and report the surface covered.
  ["docs", "/docs", { mocks: WALLET_MOCKS, open: [".group__head"], ready: ".doc" }],
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
  ["login", "/login"],
  ["evidence", "/load/00000000-0000-0000-0000-0000000000aa/evidence"],
  ["condition", "/protection/condition"],
  ["facility", "/facility/00000000-0000-0000-0000-0000000000bb"],
  // §23 entry 114 — "don't ask about this lot". A separate state rather than mocks on
  // `facility` above, which deliberately renders from fixtures: this row appears only
  // after the server answers, so it needs an intercepted route to exist at all. Every
  // other call 404s and the surface falls back to its fixtures exactly as it does today.
  ["facility-prompt-mute", "/facility/00000000-0000-0000-0000-0000000000bb", {
    mocks: {
      "/map/facility/00000000-0000-0000-0000-0000000000bb/prompt-pref": {
        facility_id: "00000000-0000-0000-0000-0000000000bb", muted: false,
      },
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
  ["sheet-ask", "/facility/00000000-0000-0000-0000-0000000000bb", {
    mocks: {}, open: [".cta--ghost"], ready: ".sheet__body",
  }],
  ["sheet-review", "/facility/00000000-0000-0000-0000-0000000000bb", {
    mocks: {}, open: [".add-review"], ready: ".sheet__body",
  }],
  ["sheet-map-report", "/", { mocks: {}, open: [".report-chip"], ready: ".sheet__body" }],
  ["sheet-map-voice", "/", { mocks: {}, open: [".voice-chip"], ready: ".sheet__body" }],
  // the sleep solver hangs off the Tonight preset, so the preset chip is step one
  ["sheet-map-sleep", "/", {
    mocks: {}, open: [{ click: ".chip", nth: 1 }, ".sleep-cta"], ready: ".sheet__body",
  }],
  ["sheet-map-relay", "/", { mocks: {}, open: [".relay-banner"], ready: ".sheet__body" }],
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
  // the sixth chip has to survive the +40% pseudo-locale in a row that already holds
  // five — the chips are icons, but the row's geometry is what this measures
  ["map-preset-service", "/", {
    mocks: mapMocks(REPAIR_PIN), open: [{ click: ".chip", nth: 5 }], ready: ".chip[aria-selected='true']",
  }],
  // A1's cross-link on the Load tab, measured because it lands on the densest driver
  // screen in the product — §10.2 is the Meter plus the stop context plus the evidence
  // checklist, and a new row there has to earn its 56 dp at 360.
  ["load-packet-waiting", "/load", {
    mocks: {
      ...LIVE_MOCKS,
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
    stop: LIVE_STOP,
    ready: ".load__packets",
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
];
const CAPTION_FLOOR_PX = 13; // §6.2: "Nothing smaller exists."
const TOUCH_MIN_PX = 48; // §6.5 glove spec
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
// · MAPBOX CONTROLS: `mapboxgl-ctrl-*` is third-party furniture injected by the map
//   library, and the attribution button and logo are required by Mapbox's terms —
//   they are not ours to resize, and hiding them would breach the licence.
const TARGET_EXEMPT = /(^|\s)(pin|mapboxgl-ctrl[\w-]*|mapboxgl-ctrl-logo)(\s|$)/;

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
      const body = live.mocks[path];
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
  await page.addInitScript(
    ([t, p, stop, storage]) => {
      try {
        localStorage.setItem("longhaul.theme", t);
        if (stop) localStorage.setItem("longhaul.active_stop", stop);
        if (p === "xx-XL") localStorage.setItem("longhaul.locale", "xx-XL");
        else if (p) localStorage.setItem("longhaul.locale", p);
        // AI-CONTEXT: some states live in storage rather than behind an endpoint —
        // §11.4's saved-for-stop queue is client-side by design, because the tap that
        // fills it happens where there may be no signal. Without this the sheet could
        // not be OPENED by the harness, and a sheet the harness cannot open is a sheet
        // that ships unmeasured at 360 dp.
        for (const [k, v] of Object.entries(storage || {})) localStorage.setItem(k, v);
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
    [theme, pseudo, live ? live.stop : null, live ? live.storage : null],
  );
}

async function settle(page, live) {
  await page.waitForLoadState("networkidle").catch(() => {});
  // the map canvas initialises asynchronously and has no layout contribution here
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
            const style = getComputedStyle(el);
            // an element that scrolls its own overflow is doing so ON PURPOSE
            // (the preset chip row, the portal rail) — that is a pattern the
            // constitution approves, not a break
            const scrolls = ["auto", "scroll"].includes(style.overflowX);
            const parentScrolls = el.parentElement
              ? ["auto", "scroll"].includes(getComputedStyle(el.parentElement).overflowX)
              : false;
            if (!scrolls && !parentScrolls) {
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
          const style = getComputedStyle(el);
          const scrolls = ["auto", "scroll"].includes(style.overflowX);
          const parentScrolls = el.parentElement
            ? ["auto", "scroll"].includes(getComputedStyle(el.parentElement).overflowX)
            : false;
          if (!scrolls && !parentScrolls) {
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
