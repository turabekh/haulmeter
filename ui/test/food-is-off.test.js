// AI-CONTEXT: "still like food notifications are there which we removed before" — the
// owner, from the screen, 2026-08-19 (§23 entry 223).
//
// `m13_vendor` has been FALSE in production since HANDOFF-114. Food goes BY FLAG rather
// than by deletion (v2.0 §4: "do not delete the code; the cost is sunk and the flag makes
// it free to carry") — which puts the whole weight of "is it gone" on the conditions, and
// this card had none at all. The authority card twenty lines above it has had one since
// it shipped, and `/auth/me` already carried two capability flags for exactly this.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import MoreSurface from "../src/surfaces/MoreSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

const jsonOk = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });

// `.alerts` is worn by the notifications row too (`alerts alerts--link`), so a bare
// selector would report the food card as present on a screen that has none
const foodToggle = (w) => w.findAll(".alerts").find((b) => !b.classes().includes("alerts--link"));

// the shape `mpg.test.js` drives this surface with — `/community/points` must answer with
// the payload the points card actually reads, or `onMounted` never reaches `loadMe` and
// every `me`-gated card is absent for a reason that has nothing to do with the flag
const BASE = { "/community/points": { balance: 0, level: "rookie" } };

function routedFetch(map) {
  return vi.fn((url) => {
    const u = String(url);
    const key = Object.keys(map).find((k) => u.includes(k));
    return jsonOk(map[key] ?? {});
  });
}

async function mountMore(me) {
  setToken("tok-food");
  vi.stubGlobal("fetch", routedFetch({ ...BASE, "/auth/me": me }));
  const w = mount(MoreSurface, {
    global: { plugins: [createRouter({ history: createMemoryHistory(), routes })] },
  });
  await flushPromises();
  return w;
}

afterEach(() => { vi.unstubAllGlobals(); logout(); });

describe("The More screen and a capability that is switched off", () => {
  it("does not offer food alerts when the food half is off", async () => {
    const w = await mountMore({ email: "d@x.com", food_enabled: false });

    expect(w.text()).not.toContain(en["vendor.alerts"]);
    expect(foodToggle(w)).toBeUndefined();
  });

  it("does not offer them to a client whose /me predates the flag either", async () => {
    // an older payload has no `food_enabled` at all; absent must read as OFF, never as
    // "unknown, so show it" — the same direction `is_enabled` treats an unregistered flag
    const w = await mountMore({ email: "d@x.com" });

    expect(foodToggle(w)).toBeUndefined();
  });

  it("offers them again the day the flag comes back on", async () => {
    // food goes by FLAG, not by deletion — so this card must return without a build
    const w = await mountMore({ email: "d@x.com", food_enabled: true });

    expect(foodToggle(w)).toBeTruthy();
    expect(w.text()).toContain(en["vendor.alerts"]);
  });
});
