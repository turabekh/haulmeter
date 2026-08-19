// AI-CONTEXT: the OBSERVATION the loading-state kickoff asked for, and it is not a
// layout check (§23 entry 131).
//
// "Throttle the network and look at the screen." Every one of the five findings this
// entry closes was GREEN in the suite — the standing warning at the top of the kickoff
// is that a suite proves the code does what it was written to do, and cannot see the
// thing nobody built at all. So this drives the REAL dev server with the overlay
// deliberately slowed, and captures what a driver's first frame actually looks like on
// a cold open in a bad signal area.
//
// It is a separate spec file because it asserts on CONTENT rather than geometry, but it
// DOES run inside `make ui-layout` — playwright's testDir is ./layout — and that is
// deliberate: an observation nobody re-runs decays into a screenshot in an old handoff.
// The assertions are cheap (~9 s) and they are the ones that would catch the fixtures
// coming back.
//
// The SCREENSHOTS are opt-in, because writing into docs/handoffs/assets on every sweep
// would leave `make ci` with a dirty working tree. To refresh them:
//
//   docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm \
//     --entrypoint sh -v "$PWD/docs/handoffs:/repo-docs" ui \
//     -c "npx playwright install chromium; OBSERVE_SHOTS=1 npx playwright test layout/observe-loading.spec.js"
import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// AI-CONTEXT: off by default — see above. `/repo-docs` is only mounted when a human is
// deliberately refreshing the images, so writing unconditionally would put them inside
// an ephemeral container filesystem and look like it had worked.
const SHOTS = !!process.env.OBSERVE_SHOTS;
async function shoot(page, name) {
  if (!SHOTS) return;
  await page.screenshot({ path: `/repo-docs/assets/${name}.png`, fullPage: false });
}

// AI-CONTEXT: both observations below open the MAP, which is dormant (owner decision
// D21, §23 entry 228) — `/` now lands on `/load`, so they would observe the Load tab under
// the map's name, which is the failure this whole harness exists to prevent.
//
// SKIPPED, not deleted, and read from `router.js` so the skip lifts itself the moment the
// map comes back. What they prove — that a slow or failed overlay never names a facility
// it has not loaded — is still the map's own law and is worth restoring with it.
const MAP_DORMANT = /export const MAP_DORMANT\s*=\s*true/.test(
  readFileSync(fileURLToPath(new URL("../src/router.js", import.meta.url)), "utf8"),
);
test.skip(() => MAP_DORMANT, "the map is dormant (D21) — these observe its states");

const API = "http://localhost:8008";
const SESSION = {
  token: "observe-loading",
  account_id: "00000000-0000-0000-0000-000000000001",
  email: "harness@example.com",
};

test("a cold map open on a slow network shows skeleton pins, never a facility", async ({ page }) => {
  // the overlay takes four seconds, which is a real dead-zone round trip rather than a
  // contrived one. Everything else answers normally, so this is the map's own state
  // being observed and not a broken app.
  await page.route(`${API}/**`, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes("/map/overlay")) {
      await new Promise((r) => setTimeout(r, 4000));
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          pins: [
            {
              facility_id: "00000000-0000-0000-0000-0000000000b1",
              name: "Dallas Cold Storage",
              facility_type: "shipper_receiver",
              lat: 32.78,
              lon: -96.8,
              status: null,
              badges: [],
              freshness: null,
            },
          ],
          clusters: [],
        }),
      });
    }
    return route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });

  await page.addInitScript((s) => {
    localStorage.setItem("longhaul.session", JSON.stringify(s));
    localStorage.setItem("longhaul.theme", "dark");
  }, SESSION);

  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/", { waitUntil: "commit" });

  // ---- the moment that used to render fabricated truck stops ----
  await page.waitForSelector(".skel__pin", { state: "attached", timeout: 15_000 });
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
  await page.waitForTimeout(150);
  await shoot(page, "loading-map-360dp");

  const skeletons = await page.locator(".skel__pin").count();
  const realPins = await page.locator(".pin").count();
  const body = await page.locator("body").innerText();

  expect(skeletons).toBeGreaterThan(0);
  // the whole finding: NO facility is named while the overlay is in flight
  expect(realPins).toBe(0);
  expect(body).not.toContain("Love's");
  expect(body).not.toContain("Pilot #77");
  expect(body).not.toContain("Dallas Cold Storage");
  // and it must not claim the map is empty either — that is a different lie (§15.3)
  expect(body).not.toContain("None mapped here yet");

  // ---- then the real pins arrive and the skeleton goes ----
  await page.waitForSelector(".pin", { state: "attached", timeout: 15_000 });
  await page.waitForTimeout(200);
  await shoot(page, "loaded-map-360dp");
  expect(await page.locator(".skel__pin").count()).toBe(0);
  // by data attribute, not by text: a loaded pin is a PUCK, and its name only becomes
  // page text once the facility card opens. Asserting on the name here would have been
  // asserting on a tap nobody made.
  expect(
    await page.locator('.pin[data-facility="00000000-0000-0000-0000-0000000000b1"]').count(),
  ).toBe(1);

  console.log(`OBSERVED — loading: ${skeletons} skeleton pucks, ${realPins} real pins, no facility named`);
});

test("a map whose overlay fails says so, and still names no facility", async ({ page }) => {
  await page.route(`${API}/**`, (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes("/map/overlay")) {
      return route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
    }
    return route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
  await page.addInitScript((s) => {
    localStorage.setItem("longhaul.session", JSON.stringify(s));
    localStorage.setItem("longhaul.theme", "dark");
  }, SESSION);

  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/");
  await page.waitForSelector(".map__failed", { state: "attached", timeout: 15_000 });
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
  await page.waitForTimeout(150);
  await shoot(page, "failed-map-360dp");

  const body = await page.locator("body").innerText();
  expect(await page.locator(".pin").count()).toBe(0);
  expect(await page.locator(".map__retry").count()).toBe(1); // §15.4: actionable
  expect(body).not.toContain("Love's");
  console.log(`OBSERVED — failed: error line rendered, 0 pins, retry offered`);
});
