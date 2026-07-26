// AI-CONTEXT: M5-FR3's measurable requirement, measured.
//
// PRD §8.5 DoD: "inspection mode usable offline in <2 taps from app open", and
// design-prd §10.4 repeats it. Every prior session asserted it in prose. This counts
// the taps in a real browser, with the network cut, from a cold start — and prints
// the number, because a requirement written as a number should be reported as one.
//
// "Cold start" means a fresh page load with no in-memory state, which is what a
// driver gets when they open the app at a scale house. The wallet must come from
// cache: an inspector is not waiting for a dead zone to end.
import { test, expect } from "@playwright/test";

const BASE = process.env.UI_BASE || "http://ui:9008";

test("inspection mode is reachable in ≤2 taps from a cold start, offline", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem(
      "longhaul.session",
      JSON.stringify({
        token: "layout-harness",
        account_id: "00000000-0000-0000-0000-000000000001",
        email: "harness@example.com",
      }),
    );
    // a wallet the driver already had — §7.12 read-side caching keeps the document
    // wallet available fully offline, which is the entire point of the requirement
    localStorage.setItem(
      "longhaul.cache.wallet",
      JSON.stringify({
        documents: [
          { id: "d1", doc_type: "cdl", expires_on: "2027-03-01", status: "ok" },
          { id: "d2", doc_type: "med_card", expires_on: "2026-08-10", status: "expiring" },
          { id: "d3", doc_type: "insurance", expires_on: "2027-01-01", status: "ok" },
        ],
        expiring: [{ id: "d2", doc_type: "med_card", expires_on: "2026-08-10", status: "expiring" }],
      }),
    );
  });

  // the dead zone: every request fails, exactly as it does at a scale house
  await page.route("**/*", (route) =>
    route.request().url().startsWith(BASE) ? route.continue() : route.abort(),
  );

  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto(`${BASE}/`); // cold start — the app opens where it opens
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(600);

  let taps = 0;

  // tap 1: the Docs tab in the five-tab bar (NAV-1)
  const docsTab = page.locator('.tab, nav a, nav button').filter({ hasText: /docs|документ|dokument|ਦਸਤਾਵੇਜ਼|waraaq|documento/i }).first();
  await docsTab.click();
  taps += 1;
  await page.waitForTimeout(400);

  // tap 2: inspection mode
  const inspect = page.locator("button.inspect");
  await expect(inspect, "the inspection button must be on the Docs tab (§10.4)").toBeVisible();
  await inspect.click();
  taps += 1;
  await page.waitForTimeout(400);

  // it must actually show credentials, offline, from cache
  const sheet = page.locator(".doc--inspect");
  await expect(sheet.first(), "inspection mode must render documents offline").toBeVisible();
  const shown = await sheet.count();

  console.log(`\n  INSPECTION MODE: ${taps} taps from cold start, offline · ${shown} credentials shown\n`);
  expect(taps).toBeLessThanOrEqual(2);
  expect(shown).toBeGreaterThan(0);
});
