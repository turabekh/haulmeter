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

/* AI-CONTEXT: the manifest AS THE BROWSER RESOLVED IT, and the icons fetched from the
 * origin that serves them (§23 entry 152).
 *
 * DO NOT ADD `Page.getInstallabilityErrors` HERE. It is the obvious move, it reads like
 * the strongest possible assertion — Chromium's own verdict — and IT IS INERT IN
 * HEADLESS. Measured, both directions, in this exact container: the real app returns
 * `{"installabilityErrors":[]}`, and so does `page.setContent("<html>bare</html>")` with
 * no manifest, no icons and no service worker. It returns [] for everything. A version
 * of this file asserting `toEqual([])` was written, run against a manifest sabotaged
 * back to entry 143's `"icons": []`, AND PASSED — the precise shape of defect this repo
 * keeps cataloguing: a check that goes green while asserting nothing about the thing it
 * is named for. It was removed rather than annotated, because a check that does not
 * exist is worse than no check: it makes the next person stop looking.
 *
 * What IS observable headless, and what these two assert instead:
 *
 *   1. `Page.getAppManifest` genuinely resolves — it returns the parsed document for a
 *      real page and an empty `url` for a page without one, so it proves the manifest is
 *      LINKED, FETCHED and PARSED rather than merely present on disk. `test/pwa.test.js`
 *      reads the file; this reads what the browser made of it.
 *   2. The icons are fetched over HTTP from the origin actually serving them. This is
 *      the check a string comparison cannot make, and 124 is why it is here: Caddy's SPA
 *      `try_files` answered `/media/…` with HTTP 200 AND index.html, so every contact
 *      sheet in production was a decoded HTML page. Nothing threw and nothing logged. A
 *      200 is not proof; the content-type and the bytes are.
 */
test("the manifest the browser resolved names icons that really are images", async ({ page }) => {
  await page.goto("/map", { waitUntil: "load" });
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null, null, {
    timeout: 30_000,
  });

  const client = await page.context().newCDPSession(page);
  const res = await client.send("Page.getAppManifest");

  // an empty `url` is what a page with NO manifest returns — the first thing to rule out
  expect(res.url, "the browser resolved no manifest at all").toContain("manifest.webmanifest");
  expect(res.errors, `manifest parse errors: ${JSON.stringify(res.errors)}`).toEqual([]);
  expect(res.data, "the browser fetched no manifest body").toBeTruthy();

  const manifest = JSON.parse(res.data);
  // entry 143's defect, asserted against the browser's copy rather than the repo's
  const sizes = manifest.icons.map((i) => i.sizes);
  expect(sizes, "Chrome installs nothing without a 192 px icon").toContain("192x192");
  expect(sizes, "Chrome installs nothing without a 512 px icon").toContain("512x512");
  expect(manifest.display).toBe("standalone");

  for (const icon of manifest.icons) {
    const resp = await page.request.get(icon.src);
    expect(resp.status(), `${icon.src} did not 200`).toBe(200);
    // the 124 defect: index.html is served with status 200 and would pass a status check
    expect(resp.headers()["content-type"], `${icon.src} is not an image`).toContain("image/");
    const body = await resp.body();
    expect(body.length, `${icon.src} is empty`).toBeGreaterThan(500);
    // a PNG's magic number, because a content-type is a claim the server makes
    expect(body.subarray(1, 4).toString("ascii"), `${icon.src} is not a PNG`).toBe("PNG");
  }
  console.log(`OBSERVED — ${manifest.icons.length} icons fetched from the origin, all real PNGs`);
});
