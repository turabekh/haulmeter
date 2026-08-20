// AI-CONTEXT: the PWA, and the reason it needed building at all (§23 entry 143).
//
// THE APP WAS NEVER INSTALLABLE. `manifest.webmanifest` shipped with `"icons": []` and
// there was not one image asset anywhere in the UI. Chrome requires a 192 px and a
// 512 px icon before it offers installation, so "add to home screen" had never worked —
// while index.html's own comment, written when push shipped, said "iOS requires an
// INSTALLED PWA for push at all". Web Push on iOS was unreachable by construction, and
// the comment describing the requirement sat directly above the manifest that broke it.
//
// These assert the manifest against the actual installability rules rather than against
// itself, because a manifest that merely parses is what shipped.
import { describe, it, expect, afterEach, vi } from "vitest";
import { readFileSync, existsSync, statSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { mount } from "@vue/test-utils";
import StatusStrip from "../src/core/components/StatusStrip.vue";
import { updateReady, __resetPwaForTests } from "../src/core/pwa.js";
import en from "../src/core/i18n/en.json";

const UI = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(readFileSync(resolve(UI, "public/manifest.webmanifest"), "utf8"));
const indexHtml = readFileSync(resolve(UI, "index.html"), "utf8");

describe("The manifest makes the app installable", () => {
  it("carries the icon sizes a browser actually requires", () => {
    // the whole defect in one assertion: `"icons": []` satisfies every schema and no
    // browser.
    const sizes = manifest.icons.map((i) => i.sizes);
    expect(sizes).toContain("192x192");
    expect(sizes).toContain("512x512");
  });

  it("ships a maskable icon so a launcher's crop cannot cut the mark", () => {
    const maskable = manifest.icons.filter((i) => (i.purpose || "").includes("maskable"));
    expect(maskable.length).toBeGreaterThan(0);
    expect(maskable[0].sizes).toBe("512x512");
  });

  it("every icon it names exists and is not empty", () => {
    // a manifest pointing at a 404 is the same failure as an empty array, one layer on
    for (const icon of manifest.icons) {
      const path = resolve(UI, "public", icon.src.replace(/^\//, ""));
      expect(existsSync(path), `${icon.src} is missing`).toBe(true);
      expect(statSync(path).size, `${icon.src} is empty`).toBeGreaterThan(500);
    }
  });

  it("declares the fields installability is judged on", () => {
    expect(manifest.name).toBeTruthy();
    expect(manifest.short_name).toBeTruthy();
    expect(manifest.start_url).toBeTruthy();
    expect(manifest.display).toBe("standalone");
    // §6.1: the ink field, written out because a manifest cannot read a CSS variable
    expect(manifest.theme_color).toBe("#0E1319");
    expect(manifest.background_color).toBe("#0E1319");
  });

  it("gives iOS the four things it reads instead of the manifest", () => {
    // iOS ignores the manifest's install fields entirely, and iOS is the platform whose
    // push has been blocked on installability since entry 111.
    expect(indexHtml).toContain('rel="apple-touch-icon"');
    expect(indexHtml).toContain('name="apple-mobile-web-app-capable"');
    expect(indexHtml).toContain('name="apple-mobile-web-app-title"');
    expect(indexHtml).toContain("apple-mobile-web-app-status-bar-style");
  });

  it("the touch icon it points at exists", () => {
    const match = /apple-touch-icon"\s+href="([^"]+)"/.exec(indexHtml);
    expect(match, "no apple-touch-icon href").toBeTruthy();
    expect(existsSync(resolve(UI, "public", match[1].replace(/^\//, "")))).toBe(true);
  });
});

describe("The service worker caches the shell and nothing else", () => {
  const sw = readFileSync(resolve(UI, "src/sw.js"), "utf8");
  const viteConfig = readFileSync(resolve(UI, "vite.config.js"), "utf8");

  it("precaches from the BUILD's manifest, never a hand-written list", () => {
    // the worker's own header warns that anything clever in it can be stale on a
    // driver's phone for days. A revisioned list is the answer: a content-hashed asset
    // cannot go stale, because a changed file is a different URL.
    expect(sw).toContain("self.__WB_MANIFEST");
    expect(viteConfig).toContain('strategies: "injectManifest"');
  });

  it("does not cache the API — F12 owns that, and two caches would disagree", () => {
    expect(sw).not.toMatch(/CacheFirst|StaleWhileRevalidate|NetworkFirst/);
    expect(sw).toContain("denylist");
  });

  it("keeps the push behaviour that was already built and reviewed", () => {
    // injectManifest exists precisely so this file survives. A generated worker would
    // have replaced the lock-screen lot report and the deep-link focus rule.
    expect(sw).toContain('addEventListener("push"');
    expect(sw).toContain('addEventListener("notificationclick"');
    expect(sw).toContain("reportLotStatus");
  });

  it("never takes over on its own", () => {
    // it used to `skipWaiting()` on install. Harmless for a push-only worker; with a
    // shell cache it can swap the page under a driver photographing a BOL at a dock.
    expect(sw).not.toMatch(/addEventListener\("install",\s*\(\)\s*=>\s*self\.skipWaiting/);
    expect(sw).toContain("SKIP_WAITING");
  });

  it("is registered for EVERY driver, not only those who enabled push", () => {
    const main = readFileSync(resolve(UI, "src/main.js"), "utf8");
    expect(main).toContain("registerServiceWorker");
  });
});

describe("A waiting update is a strip, not an interruption", () => {
  afterEach(() => {
    __resetPwaForTests();
    vi.unstubAllGlobals();
  });

  it("offers no restart when there is nothing waiting", () => {
    const w = mount(StatusStrip, { props: { online: true, pending: 0, failed: 0 } });
    // the strip is always present since entry 230 — the bell lives there. A waiting
    // build is still a conditional row, and it is not waiting.
    expect(w.find(".strip").exists()).toBe(true);
    expect(w.find(".strip__update").exists()).toBe(false);
  });

  it("offers the restart when a new build is ready", () => {
    updateReady.value = true;
    const w = mount(StatusStrip, { props: { online: true, pending: 0, failed: 0 } });

    expect(w.find(".strip__update").exists()).toBe(true);
    expect(w.text()).toContain(en["system.update_ready"]);
    expect(w.text()).toContain(en["system.update_apply"]);
  });

  it("is a control the driver chooses, never a reload that happens to them", () => {
    // §8 routes persistent conditions to this strip and reserves toasts for
    // confirmations; §13.1's budget is for reaching a driver, not for the app talking
    // about itself. So this is a button, and nothing about it is automatic.
    updateReady.value = true;
    const w = mount(StatusStrip, { props: { online: true, pending: 0, failed: 0 } });
    expect(w.find(".strip__update").element.tagName).toBe("BUTTON");
  });

  it("shows beside the other strip facts rather than replacing them", () => {
    updateReady.value = true;
    const w = mount(StatusStrip, { props: { online: false, pending: 2, failed: 0 } });

    expect(w.find(".strip__offline").exists()).toBe(true);
    expect(w.find(".strip__pending").exists()).toBe(true);
    expect(w.find(".strip__update").exists()).toBe(true);
  });
});
