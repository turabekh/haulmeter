// AI-CONTEXT: U-02 — a phone passed between team drivers is the NORMAL case in this
// product, and the second driver was inheriting the first one's active stop.
//
// `clearCache()` sweeps keys prefixed `longhaul.cache.`. `longhaul.active_stop` and
// `longhaul.active_fleet` sat outside that prefix and survived logout. The fix is the
// prefix, not two `removeItem` calls beside it — the convention is what failed, and an
// exception list leaves the next per-driver key exposed in exactly the same way.
//
// These assert the RENDERED state, never localStorage. The audit's recurring finding is
// tests that assert the mechanism instead of the outcome, and the mechanism here has a
// second half a storage assertion cannot see: `signOut()` routes to /login without
// reloading, so the module-scope refs outlive the logout that emptied their keys. A
// test that only checked the keys were gone would have passed over a Load tab still
// showing the previous driver's dock.
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import { routes } from "../src/router.js";
import {
  setToken,
  logout,
  setActiveStop,
  setActiveFleet,
  activeStopId,
  activeFleetId,
} from "../src/core/api.js";
import { __resetStateForTests } from "../src/core/state.js";
import en from "../src/core/i18n/en.json";

function jsonOk(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

const DRIVER_A_METER = {
  stop_id: "stop-a",
  facility_name: "CLORL — Christie Lites Orlando",
  counterparty: "Direct Traffic Solutions Inc.",
  appointment: null,
  arrived: true,
  free_time_minutes: 120,
  rate_cents_per_hour: 7500,
  phase: "free_time",
  free_time_remaining_seconds: 7073,
  detention_seconds: 0,
  detention_cents: 0,
  notice_sent: false,
  photos_captured: 0,
  photos_required: 4,
  bol_captured: true,
  checklist: [{ item: "bol", kind: "document", captured: true, required: true }],
};

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn((url) =>
      String(url).includes("/load/stop-a/meter") ? jsonOk(DRIVER_A_METER) : jsonOk({}),
    ),
  );
}

async function mountLoad() {
  const router = createRouter({ history: createMemoryHistory(), routes });
  const w = mount(LoadSurface, { global: { plugins: [router] } });
  await flushPromises();
  return w;
}

beforeEach(() => {
  __resetStateForTests();
  stubFetch();
});

afterEach(() => {
  logout();
  __resetStateForTests();
  vi.unstubAllGlobals();
});

describe("a phone handed to the next driver (U-02)", () => {
  it("shows driver B the empty Load tab, not driver A's dock", async () => {
    setToken("tok-a");
    setActiveStop("stop-a");
    const asA = await mountLoad();
    expect(
      asA.text(),
      "precondition: driver A must actually see their stop, or this proves nothing",
    ).toContain("CLORL — Christie Lites Orlando");

    logout();

    setToken("tok-b");
    const asB = await mountLoad();
    expect(asB.text()).not.toContain("CLORL — Christie Lites Orlando");
    expect(asB.text()).toContain(en["load.empty_hint"]);
  });

  it("clears the active stop from MEMORY, not only from storage", async () => {
    // signOut() routes without reloading, so a ref that survives logout is what the
    // next driver actually renders from — storage is never consulted again
    setToken("tok-a");
    setActiveStop("stop-a");
    expect(activeStopId.value).toBe("stop-a");
    logout();
    expect(activeStopId.value).toBeNull();
  });

  it("clears the active fleet the same way", async () => {
    setToken("tok-a");
    setActiveFleet("fleet-a");
    expect(activeFleetId.value).toBe("fleet-a");
    logout();
    expect(activeFleetId.value).toBeNull();
  });

  it("leaves nothing of driver A behind that is not a device preference", async () => {
    // The class-level assertion, and the one that catches the NEXT key someone adds.
    // Every longhaul.* key surviving a logout must be one of two things: a preference
    // belonging to the PHONE rather than the person, or provably empty. Anything else
    // is driver A's data sitting in front of driver B.
    const DEVICE_PREFERENCES = ["longhaul.locale", "longhaul.theme"];
    const EMPTIED_NOT_REMOVED = { "longhaul.write_queue": "[]" };

    setToken("tok-a");
    setActiveStop("stop-a");
    setActiveFleet("fleet-a");
    logout();

    const survivors = Object.keys(localStorage).filter(
      (k) => k.startsWith("longhaul.") && !k.startsWith("longhaul.cache."),
    );
    for (const key of survivors) {
      if (DEVICE_PREFERENCES.includes(key)) continue;
      expect(
        Object.hasOwn(EMPTIED_NOT_REMOVED, key),
        `${key} survived logout and is not a device preference — driver B would read it`,
      ).toBe(true);
      expect(localStorage.getItem(key)).toBe(EMPTIED_NOT_REMOVED[key]);
    }
  });
});
