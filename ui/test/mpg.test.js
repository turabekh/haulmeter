// AI-CONTEXT: the truck's own fuel economy (J1-A3, §23 entry 154).
//
// The calculator burned a hardcoded 6.0 in two places — the request model's default and
// this surface's payload — so a reefer at 5.2 and a light run at 7.5 were handed the same
// fuel cost for the same route, and nothing on screen admitted the number was ours.
//
// The load-bearing distinction under test is BLANK versus 6.0. They are not the same
// answer: blank means the driver has not told us, and that is the one case where the
// screen owes them a line saying whose number it just used.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import MoreSurface from "../src/surfaces/MoreSurface.vue";
import LoadCalcSurface from "../src/surfaces/LoadCalcSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout, setActiveStop } from "../src/core/api.js";
import { mpgError, normalizeMpg, MIN_MPG, MAX_MPG } from "../src/core/truck.js";
import en from "../src/core/i18n/en.json";

function jsonOk(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

function testRouter() {
  return createRouter({ history: createMemoryHistory(), routes });
}

function routedFetch(map, seen) {
  return vi.fn((url, opts) => {
    const u = String(url);
    if (seen) seen.push({ url: u, body: opts?.body ? JSON.parse(opts.body) : null });
    const key = Object.keys(map).find((k) => u.includes(k));
    return jsonOk(map[key] ?? {});
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  logout();
});

// --- the shared rule ---

describe("the client's mpg rule", () => {
  it("matches the server's, case for case", () => {
    expect(mpgError("6.4")).toBe(null);
    expect(mpgError("  5.2 ")).toBe(null);
    expect(mpgError("")).toBe(null); // empty means CLEAR, not invalid
    expect(mpgError(null)).toBe(null);
    expect(mpgError(String(MIN_MPG))).toBe(null); // bounds inclusive, both ends
    expect(mpgError(String(MAX_MPG))).toBe(null);
    expect(mpgError("2.9")).toBe("mpg.range");
    expect(mpgError("60")).toBe("mpg.range"); // the pickup's figure, typed by mistake
    expect(mpgError("0.6")).toBe("mpg.range"); // a decimal slip
    expect(mpgError("0")).toBe("mpg.range");
    expect(mpgError("-6")).toBe("mpg.range");
    expect(mpgError("diesel")).toBe("mpg.number");
  });

  it("names every error with a key that exists in the catalogue", () => {
    for (const raw of ["2.9", "60", "diesel"]) {
      expect(en[mpgError(raw)]).toBeTruthy();
    }
  });

  it("keeps blank distinguishable from zero on the wire", () => {
    // `Number("")` is 0, and a stored 0 would divide the route into infinite gallons
    expect(normalizeMpg("")).toBe("");
    expect(normalizeMpg("  ")).toBe("");
    expect(normalizeMpg("6.4")).toBe("6.4");
  });
});

// --- reporting it ---

describe("MoreSurface — the truck's fuel economy", () => {
  const BASE = {
    "/community/points": { balance: 0, level: "rookie" },
    "/auth/me": { verification_enabled: false, verified: false, mpg: null },
  };

  it("shows an empty field when the driver has never reported one", async () => {
    // NOT 6.0. Prefilling our own assumption into a box labelled as theirs is how the
    // app ends up holding a figure nobody chose and treating it as reported.
    setToken("tok-mpg-unset");
    vi.stubGlobal("fetch", routedFetch(BASE));
    const w = mount(MoreSurface, { global: { plugins: [testRouter()] } });
    await flushPromises();

    expect(w.vm.equip.mpg).toBe("");
    expect(w.text()).toContain(en["equipment.mpg_hint"]);
  });

  it("shows what the driver reported", async () => {
    setToken("tok-mpg-set");
    vi.stubGlobal("fetch", routedFetch({ ...BASE, "/auth/me": { ...BASE["/auth/me"], mpg: 5.2 } }));
    const w = mount(MoreSurface, { global: { plugins: [testRouter()] } });
    await flushPromises();

    expect(w.vm.equip.mpg).toBe("5.2");
  });

  it("sends it with the rest of the equipment", async () => {
    const seen = [];
    setToken("tok-mpg-save");
    vi.stubGlobal("fetch", routedFetch({ ...BASE, "/auth/equipment": { mpg: 5.2 } }, seen));
    const w = mount(MoreSurface, { global: { plugins: [testRouter()] } });
    await flushPromises();

    w.vm.equip.mpg = "5.2";
    await w.find(".equip").trigger("submit");
    await flushPromises();

    const saved = seen.find((r) => r.url.includes("/auth/equipment"));
    expect(saved.body.mpg).toBe("5.2");
  });

  it("refuses to send a typo, in the driver's own language", async () => {
    // 60 is the pickup's figure. Catching it here rather than as a 422 carrying a
    // sentence of English out of a Python exception.
    const seen = [];
    setToken("tok-mpg-typo");
    vi.stubGlobal("fetch", routedFetch(BASE, seen));
    const w = mount(MoreSurface, { global: { plugins: [testRouter()] } });
    await flushPromises();

    w.vm.equip.mpg = "60";
    await w.vm.$nextTick();

    expect(w.text()).toContain(en["mpg.range"]);
    expect(w.find(".equip button").attributes("disabled")).toBeDefined();
  });
});

// --- spending it ---

describe("LoadCalcSurface — whose fuel economy this cost came from", () => {
  const RESULT = {
    revenue_cents: 285000,
    fuel_cost_cents: 41000,
    tolls_cents: 0,
    expected_detention_cents: 0,
    net_cents: 244000,
    rpm_after_cents: 244,
    fuel_net_cents_per_gal: 390,
    basis: { fuel: "m7:Pilot", detention_sample_size: 0, rpm: "computed" },
  };

  async function mountCalc(basis, seen) {
    const router = testRouter();
    router.push("/load/calc");
    await router.isReady();
    setActiveStop("s-1");
    setToken("tok-calc-mpg");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url, opts) => {
        const u = String(url);
        if (seen) seen.push({ url: u, body: opts?.body ? JSON.parse(opts.body) : null });
        if (u.includes("/meter")) {
          return jsonOk({
            stop_id: "s-1", facility_id: "fac-77", facility_name: "Harvest Foods DC",
            rate_cents: 285000, free_time_minutes: 90, rate_cents_per_hour: 6000,
            phase: "not_arrived", detention_cents: 0, detention_seconds: 0,
            photos_captured: 0, photos_required: 4,
          });
        }
        return jsonOk({ ...RESULT, basis: { ...RESULT.basis, ...basis } });
      }),
    );
    const w = mount(LoadCalcSurface, { global: { plugins: [router] } });
    await flushPromises();
    return w;
  }

  it("stops shipping a fuel economy of its own", async () => {
    // the 6.0 that used to sit in this payload is gone: omitting the field asks the
    // server for what the DRIVER reported
    const seen = [];
    const w = await mountCalc({ mpg: 6, mpg_basis: "default" }, seen);
    await w.find(".fields").trigger("submit");
    await flushPromises();

    const asked = seen.find((r) => r.url.includes("/true-profit"));
    expect(asked.body.mpg).toBeUndefined();
  });

  it("says the number is ours when nobody told it otherwise", async () => {
    const w = await mountCalc({ mpg: 6, mpg_basis: "default" });
    await w.find(".fields").trigger("submit");
    await flushPromises();

    expect(w.text()).toContain("6");
    expect(w.find(".basis").text()).toContain("not yours");
  });

  it("stays quiet when the figure is the driver's own", async () => {
    // a driver who reported 5.2 does not need telling that we used 5.2. What needs
    // saying is only ever the opposite.
    const w = await mountCalc({ mpg: 5.2, mpg_basis: "driver" });
    await w.find(".fields").trigger("submit");
    await flushPromises();

    expect(w.find(".basis").text()).not.toContain("not yours");
  });
});
