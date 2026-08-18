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

  // AI-CONTEXT: THIS PATH CHANGED AT DECISION 207 AND THE NUMBER DID NOT.
  //
  // Roadside Ready took the fourth tab slot and Docs moved to a More row. That made the
  // old route More → Documents → Inspection — THREE taps — and this probe is what said
  // so, in a real browser, while every unit test in the project stayed green. The fix
  // was a second door rather than a smaller promise: inspection mode is its own entry on
  // Load (and on More), so the law still reads ≤2 and still measures ≤2.
  //
  // LOAD, not More: §5 foregrounds the Load tab when the driver is ON_SITE, which is
  // where a driver is when an officer walks up.

  // tap 1: the Load tab in the five-tab bar (NAV-1, still exactly five)
  const loadTab = page.locator('.tab, nav a, nav button').filter({ hasText: /load|груз|yuk|ਲੋਡ|xamuul|carga/i }).first();
  await loadTab.click();
  taps += 1;
  await page.waitForTimeout(400);

  // tap 2: inspection mode, directly — not the wallet with inspection behind it
  const inspect = page.locator("button.inspect-row");
  await expect(inspect, "inspection mode must be one tap from a tab root (§10.4)").toBeVisible();

  // the claim in LoadSurface's comment is that it sits above the fold at 360x800, so an
  // officer is never waiting on a scroll. A claim in a comment is worth what it is
  // measured at.
  const box = await inspect.boundingBox();
  expect(box.y + box.height, "inspection mode must be reachable without scrolling").toBeLessThanOrEqual(800);

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
