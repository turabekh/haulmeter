// AI-CONTEXT: the only check that proves the offline shell exists (§23 entry 143).
//
// Every other assertion about the PWA reads a manifest, a config or a source file —
// which is exactly how `"icons": []` shipped past a suite that parsed it happily. This
// one drives a REAL browser against the REAL build: it installs the worker, kills the
// network, and reloads. Before the shell cache, that reload was a blank page, because
// F12 caches API RESPONSES and the JavaScript needed to render them was never cached at
// all — an app that was "offline-first" everywhere except the part that draws.
//
// WHY IT IS NOT IN `layout/`. It needs the built output behind a static server, not the
// dev server the §22.3 harness drives, and the dev build deliberately generates no
// worker at all. `make ui-pwa` builds, previews and runs this; `make ci` calls it.
import { test, expect } from "@playwright/test";

test("the built app installs a worker and opens with no network", async ({ page }) => {
  await page.goto("/map", { waitUntil: "load" });

  // the worker has to be CONTROLLING, not merely registered: a registered worker that
  // never took control serves nothing, which would pass a naive check and fail a driver.
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null, null, {
    timeout: 30_000,
  });

  await page.waitForTimeout(2_500); // let the precache settle
  const cached = await page.evaluate(async () => {
    const names = await caches.keys();
    let n = 0;
    for (const name of names) n += (await (await caches.open(name)).keys()).length;
    return n;
  });
  // the shell is the two bundles, the two stylesheets, the fonts, the icons and the
  // HTML. A precache that had quietly become empty is the failure this number catches.
  expect(cached, "nothing was precached").toBeGreaterThan(8);
  console.log(`OBSERVED — worker controlling, ${cached} shell entries precached`);

  await page.context().setOffline(true);
  await page.reload({ waitUntil: "load" });
  const offline = await page.locator("#app").innerHTML();
  expect(offline.length, "the app rendered nothing offline").toBeGreaterThan(200);

  // and a DEEP route offline, which is the SPA navigation fallback rather than the
  // precache: without it every URL except the one that was cached last is a dead end.
  await page.goto("/money", { waitUntil: "load" });
  const deep = await page.locator("#app").innerHTML();
  expect(deep.length, "a deep route did not render offline").toBeGreaterThan(200);
  console.log("OBSERVED — offline reload and deep route both rendered");
});
