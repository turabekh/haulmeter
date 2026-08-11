// AI-CONTEXT: §7.2's bottom-anchored action, MEASURED (§23 entry 140).
//
// "content (scroll region) -> bottom-anchored primary action (when present, 56 dp + 16
// gutter) -> tab bar" has been §7.2's screen anatomy since it was written, and §7.3 puts
// primary and frequent actions in the bottom third. Nothing in this product implemented
// it — every surface's CTA was the last thing in the scroll region — and on the arrived
// Load tab, the densest screen here, that put "Snap BOL" and the row holding "Leave this
// stop" below the fold at a dock. Reported from a real phone.
//
// WHY THIS IS ITS OWN SPEC. `layout.spec.js` measures overflow, target sizes and
// clipping; none of those can see an element that is perfectly laid out and simply off
// the bottom of the screen. The property here is REACHABILITY WITHOUT SCROLLING, which
// is a different question and needs a different assertion — the surface is deliberately
// loaded with the worst realistic content so the check is meaningful rather than lucky.
//
// It runs inside `make ui-layout` (playwright's testDir is ./layout), which is the point:
// an anchoring nobody re-measures decays the first time a card grows.
import { test, expect } from "@playwright/test";

const API = "http://localhost:8008";
const STOP = "00000000-0000-0000-0000-0000000000aa";
const SESSION = {
  token: "observe-actions",
  account_id: "00000000-0000-0000-0000-000000000001",
  email: "harness@example.com",
};

// the worst realistic arrived stop: every checklist row unsatisfied, a long facility
// name, a next-stop preview and a broker-email row. This is what a driver actually meets
// mid-shift, and it is what pushed the CTA off the screen.
function meter() {
  return {
    stop_id: STOP,
    facility_name: "Midwest Distribution Center — Dock 4",
    counterparty: "Bolt Logistics LLC",
    appointment: new Date(Date.now() - 3600 * 1000).toISOString(),
    appointment_end: new Date(Date.now() + 3600 * 1000).toISOString(),
    appointment_source: "rate_con_parse",
    phase: "within_free_time",
    free_time_minutes: 120,
    free_time_remaining_seconds: 40,
    detention_seconds: 0,
    rate_cents_per_hour: 7500,
    detention_cents: 0,
    notice_sent: false,
    notice_delivery: "not_sent",
    bol_captured: false,
    photos_captured: 0,
    photos_required: 4,
    checklist: [
      { item: "bol", kind: "document", captured: false, required: true },
      { item: "pod", kind: "document", captured: false, required: true },
      { item: "damage", kind: "document", captured: false, required: true },
    ],
    filed: false,
    on_time: false,
    arrived_at: new Date(Date.now() - 600 * 1000).toISOString(),
    next_stop: {
      facility_name: "Metro Market Warehouse",
      appointment: new Date(Date.now() + 7200 * 1000).toISOString(),
    },
    load_id: "aaaa0000-0000-0000-0000-000000000001",
    counterparty_email: "accountspayable@boltlogistics.example",
  };
}

async function openLoadTab(page) {
  await page.route(`${API}/**`, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes("/meter")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(meter()),
      });
    }
    if (path.includes("/load/active")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ stop_id: STOP }),
      });
    }
    if (path.includes("/protection/stop-packets")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    }
    return route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
  await page.addInitScript(([s, stop]) => {
    localStorage.setItem("longhaul.session", JSON.stringify(s));
    localStorage.setItem("longhaul.theme", "dark");
    localStorage.setItem("longhaul.activeStop", JSON.stringify(stop));
  }, [SESSION, STOP]);
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/load", { waitUntil: "commit" });
  await page.waitForSelector(".actions .cta", { timeout: 15_000 });
  await page.waitForTimeout(400);
}

test("the primary action is on screen at a dock, without scrolling", async ({ page }) => {
  await openLoadTab(page);

  const cta = page.locator(".actions .cta").first();
  const box = await cta.boundingBox();
  const viewport = page.viewportSize();

  expect(box, "no primary action rendered").not.toBeNull();
  // fully inside the viewport, not merely starting inside it: half a button is not a
  // reachable button, and the bottom edge is the one that used to be off the screen.
  expect.soft(box.y, "primary starts below the fold").toBeLessThan(viewport.height);
  expect
    .soft(box.y + box.height, "primary is cut off at the bottom")
    .toBeLessThanOrEqual(viewport.height);
  // §6.5's glove spec, at the one place it matters most
  expect.soft(box.height, "primary is under 56 dp").toBeGreaterThanOrEqual(56);
  console.log(
    `OBSERVED — primary at y=${Math.round(box.y)}..${Math.round(box.y + box.height)} of ${viewport.height}`,
  );
});

test("the quick-actions row is on screen too", async ({ page }) => {
  // the owner named two things: "I have arrived" and "leave this stop". The second lives
  // behind "More for this stop", so that row has to be reachable without scrolling or
  // only half the request is met.
  await openLoadTab(page);

  const more = page.locator(".actions .rungs__item--more");
  const box = await more.boundingBox();
  const viewport = page.viewportSize();

  expect(box, "no quick-actions row rendered").not.toBeNull();
  expect.soft(box.y + box.height, "quick actions are below the fold").toBeLessThanOrEqual(
    viewport.height,
  );
  console.log(`OBSERVED — quick actions end at y=${Math.round(box.y + box.height)}`);
});

test("leaving the stop is one tap from the screen, not four from a sheet", async ({ page }) => {
  // the owner's report, twice: "Leave this stop is almost hidden, not quick action (it is
  // under more)". It was the FOURTH item inside "More for this stop" — two taps and the
  // bottom of a list — while being the second-most-frequent act on this screen.
  await openLoadTab(page);

  const leave = page.locator(".actions .cta--outline");
  const box = await leave.boundingBox();
  const viewport = page.viewportSize();

  expect(box, "no leave control on the surface").not.toBeNull();
  expect.soft(box.y + box.height, "leave is below the fold").toBeLessThanOrEqual(viewport.height);
  expect.soft(box.height, "leave is under the 56 dp Secondary height").toBeGreaterThanOrEqual(56);
  // and it is not ALSO in the sheet: one act, one control
  await page.locator(".actions .rungs__item--more").click();
  await page.waitForSelector(".more");
  const inSheet = await page.locator(".more .more__item").allInnerTexts();
  expect
    .soft(inSheet.join(" | "), "leaving is duplicated inside the More sheet")
    .not.toMatch(/Leave this stop|End load/i);
  console.log(`OBSERVED — leave at y=${Math.round(box.y)}..${Math.round(box.y + box.height)}`);
});

test("the content behind it still reaches its end", async ({ page }) => {
  // a sticky bar paints over content it has not scrolled to yet, so the risk it
  // introduces is the opposite of the one it fixes: a last row permanently hidden.
  // Scrolled to the bottom, the checklist's final control must be clear of the bar.
  await openLoadTab(page);
  await page.evaluate(() => {
    const el = document.querySelector(".app-content");
    if (el) el.scrollTop = el.scrollHeight;
  });
  await page.waitForTimeout(300);

  const link = page.locator(".card__link").last(); // "View all evidence", the card's end
  const linkBox = await link.boundingBox();
  const barBox = await page.locator(".actions").boundingBox();

  expect(linkBox, "the evidence card has no end control").not.toBeNull();
  expect
    .soft(linkBox.y + linkBox.height, "the card's last control is under the action bar")
    .toBeLessThanOrEqual(barBox.y + 1);
  console.log("OBSERVED — content clears the anchored bar at full scroll");
});
