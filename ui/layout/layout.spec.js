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
  ["docs", "/docs"],
  ["more", "/more"],
  ["login", "/login"],
  ["evidence", "/load/00000000-0000-0000-0000-0000000000aa/evidence"],
  ["condition", "/protection/condition"],
  ["facility", "/facility/00000000-0000-0000-0000-0000000000bb"],
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
      return body
        ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) })
        : route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
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
              const r = el.getBoundingClientRect();
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
