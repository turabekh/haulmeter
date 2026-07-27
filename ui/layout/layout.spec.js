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
  "/load/active": { stop_id: LIVE_STOP },
  [`/load/${LIVE_STOP}/meter`]: {
    stop_id: LIVE_STOP,
    claim_id: "00000000-0000-0000-0000-0000000000dd",
    facility_name: "Dallas Cold Storage",
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
    receiver_name: "ACME Distribution Center",
    broker_name: "Coyote Logistics",
    reference_number: "L-9001",
    linehaul_cents: 250000,
    free_time_minutes: 120,
    detention_cents_per_hour: 7500,
  },
  silent_on: ["tonu"],
  facility_candidates: [
    { facility_id: "00000000-0000-0000-0000-0000000000b1", name: "ACME Distribution Ctr", address: "1 Dock Rd, Dallas TX", score: 0.68 },
    { facility_id: "00000000-0000-0000-0000-0000000000b2", name: "Dallas Distribution Center", address: "9 Loop 12, Dallas TX", score: 0.65 },
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
  // `ready` is the selector that PROVES the mocked state rendered. Without it a
  // mock that stops matching turns this surface back into a second copy of `load`,
  // and the harness goes green over the screen it was added to measure — the same
  // failure as the run that measured Vite's error page six times.
  ["load-live", "/load", { stop: LIVE_STOP, mocks: LIVE_MOCKS, ready: ".rungs__item" }],
  ["money", "/money"],
  ["docs", "/docs", { mocks: WALLET_MOCKS, ready: ".doc" }],
  ["more", "/more"],
  ["login", "/login"],
  ["evidence", "/load/00000000-0000-0000-0000-0000000000aa/evidence"],
  ["condition", "/protection/condition"],
  ["facility", "/facility/00000000-0000-0000-0000-0000000000bb"],

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
    mocks: WALLET_MOCKS, open: [".doc"], ready: ".viewer__frame",
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
      "/load/import": { document_id: RATE_CON_DRAFT.document_id, parsed: null, silent_on: [], facility_candidates: [], readable: false },
    },
    open: [".cta:not(.cta--text)", { upload: ".rc__input" }, ".rc__cta"],
    ready: ".rc__unread",
  }],
  ["sheet-viewer-edit", "/docs", {
    mocks: WALLET_MOCKS, open: [".doc", ".viewer__edit"], ready: ".viewer__form",
  }],
  // removing a document is destructive-adjacent (§17 Q16 makes it reversible), and
  // §8 gives destructive actions their own confirm sheet — this is that sheet
  ["sheet-remove", "/docs", {
    mocks: WALLET_MOCKS, open: [".doc", ".viewer__remove"], ready: ".rm__go",
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
    ([t, p, stop]) => {
      try {
        localStorage.setItem("longhaul.theme", t);
        if (stop) localStorage.setItem("longhaul.active_stop", stop);
        if (p === "xx-XL") localStorage.setItem("longhaul.locale", "xx-XL");
        else if (p) localStorage.setItem("longhaul.locale", p);
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
    [theme, pseudo, live ? live.stop : null],
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
    await page.waitForSelector(live.ready, { state: "attached", timeout: 5_000 });
  }
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
for (const [name, path, live] of SURFACES) {
  {
    const theme = "dark";
    // `pa` joins the matrix because §6.2's "metrics-compatible line-height tokens
    // verified" is a LAYOUT claim, and this harness is the only thing that can
    // answer it. Gurmukhi carries matras above AND below the baseline, so a line
    // height tuned for Latin is exactly the kind of thing that clips silently — and
    // "verified" was asserted in the constitution without anyone rendering it.
    for (const pseudo of [false, "xx-XL", "pa"]) {
      const label = `${name}${pseudo ? ` · ${pseudo}` : ""}`;

      test(`${label} — no horizontal overflow at 360 dp`, async ({ page }) => {
        await prepare(page, { theme, pseudo, live });
        await page.setViewportSize({ width: 360, height: 800 });
        await page.goto(`${BASE}${path}`);
        await settle(page, live);
        await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);

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
          return { docScroll: doc.scrollWidth, clientWidth: doc.clientWidth, offenders };
        });

        expect(overflow.offenders, `elements past 360 dp: ${overflow.offenders.join(" | ")}`)
          .toEqual([]);
        expect(overflow.docScroll).toBeLessThanOrEqual(overflow.clientWidth + 1);
      });

      test(`${label} — nothing below the 13 dp type floor`, async ({ page }) => {
        await prepare(page, { theme, pseudo, live });
        await page.setViewportSize({ width: 360, height: 800 });
        await page.goto(`${BASE}${path}`);
        await settle(page, live);

        const small = await page.evaluate((floor) => {
          const found = [];
          for (const el of document.querySelectorAll("body *")) {
            if (!el.textContent || !el.textContent.trim()) continue;
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            const size = parseFloat(getComputedStyle(el).fontSize);
            if (size && size < floor) {
              found.push(`${el.tagName.toLowerCase()}.${el.className} @${size}px`);
            }
          }
          return found;
        }, CAPTION_FLOOR_PX);

        expect(small, `§6.2 says nothing smaller than 13 dp exists: ${small.join(" | ")}`)
          .toEqual([]);
      });

      test(`${label} — text is not clipped by its line box`, async ({ page }) => {
        await prepare(page, { theme, pseudo, live });
        await page.setViewportSize({ width: 360, height: 800 });
        await page.goto(`${BASE}${path}`);
        await settle(page, live);
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

        expect(clipped, `clipped text: ${clipped.join(" | ")}`).toEqual([]);
      });

      // AI-CONTEXT: the fifth assertion, and the one with the best odds of paying for
      // its runtime. A <button> with no handler is the FIFTH instance of one bug
      // class in this project: the "suggest a cook" control with no destination,
      // `categories` collected and never read, `portions` carried through three API
      // layers to nowhere, `followers_notified` returned and rendered nowhere, and
      // the Docs capture chip. The near side of a seam gets built, the far side does
      // not, and nothing in §22.3 catches it because every one of those passes review
      // — the code looks finished from whichever side you are reading.
      //
      // A control that reports nothing when pressed is worse than an absent one: it
      // spends the driver's trust. §23 already settled the principle for the module
      // registry — a capability whose destination does not exist is LABELLED, never
      // linked — and this is that rule, enforced.
      //
      // `disabled` is an acceptable answer. Saying "not yet" is honest; saying
      // nothing is not.
      test(`${label} — every control does something, or says it cannot`, async ({ page }) => {
        await prepare(page, { theme, pseudo, live });
        await page.setViewportSize({ width: 360, height: 800 });
        await page.goto(`${BASE}${path}`);
        await settle(page, live);

        const inert = await page.evaluate(() => {
          const found = [];
          for (const el of document.querySelectorAll("button")) {
            const r = el.getBoundingClientRect();
            if (!r.width || !r.height) continue;
            if (el.disabled || el.getAttribute("aria-disabled") === "true") continue;
            // a <button type=submit> inside a form acts through the form
            if (el.type === "submit" && el.closest("form")) continue;
            // Vue compiles @click to a listener; getEventListeners is devtools-only,
            // so the reliable signal is the framework's own bookkeeping on the node
            const vue = el.__vnode || el.__vueParentComponent;
            const props = vue && vue.props;
            const hasVueHandler = !!(
              props &&
              Object.keys(props).some((k) => /^on[A-Z]/.test(k) && typeof props[k] === "function")
            );
            const hasDomHandler = typeof el.onclick === "function";
            // Mapbox attaches its own listeners imperatively, so neither Vue's
            // bookkeeping nor `onclick` can see them. Same exemption the glove-spec
            // check already carries, and for the same reason: not our furniture.
            if (el.closest(".mapboxgl-ctrl") || /mapboxgl/.test(el.className)) continue;
            if (!hasVueHandler && !hasDomHandler && !el.closest("a[href]")) {
              found.push(`${el.className || el.tagName.toLowerCase()}: "${(el.textContent || "").trim().slice(0, 32)}"`);
            }
          }
          return found;
        });

        expect(inert, `controls that do nothing when pressed: ${inert.join(" | ")}`).toEqual([]);
      });

      test(`${label} — interactive targets meet the glove spec`, async ({ page }) => {
        await prepare(page, { theme, pseudo, live });
        await page.setViewportSize({ width: 360, height: 800 });
        await page.goto(`${BASE}${path}`);
        await settle(page, live);

        const tooSmall = await page.evaluate(
          ([selector, min, exempt]) => {
            const found = [];
            for (const el of document.querySelectorAll(selector)) {
              let r = el.getBoundingClientRect();
              // AI-CONTEXT: a radio or checkbox is a GLYPH inside its target. The
              // browser delivers the tap to the enclosing <label>, so that is what
              // §6.5 governs — the rate-con confirm screen's facility radios render
              // 13×13 inside labels measuring 328×48, and reporting the glyph would
              // have sent someone to inflate a control that is already reachable.
              //
              // This narrows to radio/checkbox deliberately. It is NOT a general
              // "labels count" rule: a text input inside a label would borrow the
              // caption's height and a genuinely short field would pass. And a radio
              // with no label, or one in an undersized label, still fails here.
              if (el.tagName === "INPUT" && (el.type === "radio" || el.type === "checkbox")) {
                const label = el.closest("label");
                if (label) r = label.getBoundingClientRect();
              }
              if (r.width === 0 || r.height === 0) continue; // not rendered
              if (getComputedStyle(el).visibility === "hidden") continue;
              if (new RegExp(exempt).test(el.className) || el.closest(".mapboxgl-ctrl")) continue;
              if (r.height < min - 0.5 || r.width < min - 0.5) {
                found.push(
                  `${el.tagName.toLowerCase()}.${el.className} ${Math.round(r.width)}×${Math.round(r.height)}`,
                );
              }
            }
            return found;
          },
          [TARGET_SELECTOR, TOUCH_MIN_PX, TARGET_EXEMPT.source],
        );

        expect(tooSmall, `§6.5 glove spec — under 48 dp: ${tooSmall.join(" | ")}`).toEqual([]);
      });
    }
  }
}
