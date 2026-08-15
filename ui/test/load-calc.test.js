/* AI-CONTEXT: the true-profit calculator, which had no tests at all (§23 entry 154).
 *
 * THE DEFECT, measured against the live API before anything changed. The calculator's
 * whole purpose is pre-acceptance — deciding whether to TAKE a load — and in exactly that
 * case there is no active stop, `route.query.receiver` has never been set by anything, and
 * the receiver fell through to the nil UUID. The nil UUID has no dwell samples, so
 * `expected_detention_cost` returns `(0, 0)`:
 *
 *     expected_detention_cents: 0
 *     detention_sample_size:    0
 *     net_cents:                164167
 *
 * The screen rendered that as a confident **−$0.00** for detention and folded it into the
 * headline — inside the app whose entire thesis is that detention is what costs a driver.
 * The sample size was on screen, in caption grey, three lines below the figure it
 * qualified. Entry 85 fixed the accepted-load case; this is the other one.
 *
 * The same shape hides in fuel: `route_fuel_cost` returns `(0, None, "no_network_fuel")`
 * when nothing is in range. The template's `=== null` guard fires only on the OFFLINE
 * local estimate — the one path where the UI writes the nulls itself — so the two states
 * that actually occur against a working server were the two it did not cover.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import LoadCalcSurface from "../src/surfaces/LoadCalcSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout, activeStopId } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

const NIL = "00000000-0000-0000-0000-000000000000";

// what the server returns for a receiver it has never seen a stop at — measured, not
// invented: 0 cost over a 0 sample, which is not the same statement as "$0 of detention"
const NO_RECEIVER = {
  revenue_cents: 200000,
  fuel_cost_cents: 32833,
  tolls_cents: 3000,
  expected_detention_cents: 0,
  net_cents: 164167,
  rpm_after_cents: 328,
  fuel_net_cents_per_gal: 394,
  basis: {
    fuel: "m7:QuikFuel Dallas (demo)",
    detention_sample_size: 0,
    detention_confidence: "heuristic",
    detention_recovery: "assumed_none",
    rpm: "computed",
  },
};
const WITH_RECEIVER = {
  ...NO_RECEIVER,
  expected_detention_cents: 4500,
  net_cents: 159667,
  basis: { ...NO_RECEIVER.basis, detention_sample_size: 11, detention_confidence: "medium" },
};
const NO_FUEL = {
  ...WITH_RECEIVER,
  fuel_cost_cents: 0,
  fuel_net_cents_per_gal: null,
  basis: { ...WITH_RECEIVER.basis, fuel: "no_network_fuel" },
};

function jsonOk(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

function net({ profit = NO_RECEIVER, facilities = [] } = {}) {
  const calls = [];
  const fn = vi.fn((url, opts) => {
    const u = String(url);
    calls.push({ url: u, opts });
    if (u.includes("/intel/true-profit")) return jsonOk(profit);
    if (u.includes("/public/facilities")) return jsonOk(facilities);
    return jsonOk({});
  });
  fn.calls = calls;
  return fn;
}

async function mountCalc() {
  const router = createRouter({ history: createMemoryHistory(), routes });
  router.push("/load/calc");
  await router.isReady();
  const w = mount(LoadCalcSurface, { global: { plugins: [router] } });
  await flushPromises();
  return w;
}

beforeEach(() => {
  localStorage.clear();
  setToken("tok-calc");
  activeStopId.value = null; // pre-acceptance: the case this surface exists for
});
afterEach(() => {
  logout();
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("a cost the app could not compute is never rendered as zero (§11.7)", () => {
  it("says detention is not included rather than showing −$0.00", async () => {
    vi.stubGlobal("fetch", net());
    const w = await mountCalc();
    await w.find("form").trigger("submit");
    await flushPromises();

    const rows = w.findAll(".breakdown__row").map((r) => r.text());
    const detention = rows.find((r) => r.includes(en["calc.detention"]));
    expect(detention).toContain(en["calc.not_included"]);
    expect(detention).not.toContain("$0.00");
    w.unmount();
  });

  it("names what the headline figure leaves out, beside the headline", async () => {
    // the sample size existed before this, in caption grey, three lines below the figure
    vi.stubGlobal("fetch", net());
    const w = await mountCalc();
    await w.find("form").trigger("submit");
    await flushPromises();

    const excludes = w.find(".result__excludes");
    expect(excludes.exists()).toBe(true);
    expect(excludes.text()).toContain(en["calc.detention"]);
    w.unmount();
  });

  it("says the same about fuel when no network station is in range", async () => {
    // `route_fuel_cost` returns (0, None, "no_network_fuel") — a zero that means unknown
    vi.stubGlobal("fetch", net({ profit: NO_FUEL }));
    const w = await mountCalc();
    await w.find("form").trigger("submit");
    await flushPromises();

    const rows = w.findAll(".breakdown__row").map((r) => r.text());
    expect(rows.find((r) => r.includes(en["calc.fuel"]))).toContain(en["calc.not_included"]);
    expect(w.text()).toContain(en["calc.basis_no_fuel"]);
    w.unmount();
  });

  it("shows the real figures when the data IS there", async () => {
    // the opposite failure: a guard that suppresses everything is not honesty
    vi.stubGlobal("fetch", net({ profit: WITH_RECEIVER }));
    const w = await mountCalc();
    await w.find("form").trigger("submit");
    await flushPromises();

    const rows = w.findAll(".breakdown__row").map((r) => r.text());
    expect(rows.find((r) => r.includes(en["calc.detention"]))).toContain("45.00");
    expect(w.find(".result__excludes").exists()).toBe(false);
    expect(w.text()).toContain("11");
    w.unmount();
  });

  it("discloses that it assumes no detention is recovered", async () => {
    // entry 134 added `detention_recovery: "assumed_none"` as audit F-25's disclosure —
    // the figure models a world where the driver recovers NOTHING, inside the app whose
    // thesis is recovering it. The API has returned it ever since and nothing rendered it.
    vi.stubGlobal("fetch", net({ profit: WITH_RECEIVER }));
    const w = await mountCalc();
    await w.find("form").trigger("submit");
    await flushPromises();

    expect(w.text()).toContain(en["calc.basis_recovery"]);
    w.unmount();
  });
});

describe("pre-acceptance can name the dock", () => {
  it("offers a receiver search when there is no active stop", async () => {
    vi.stubGlobal("fetch", net());
    const w = await mountCalc();
    expect(w.find(".receiver").exists()).toBe(true);
    w.unmount();
  });

  it("sends the chosen facility instead of the nil UUID", async () => {
    const fetchMock = net({
      facilities: [{ id: "fac-77", name: "Blue Beacon", facility_type: "truck_stop" }],
      profit: WITH_RECEIVER,
    });
    vi.stubGlobal("fetch", fetchMock);
    const w = await mountCalc();

    await w.find(".receiver .field__input").setValue("Blue");
    await w.find(".receiver .field__input").trigger("input");
    await flushPromises();
    await w.find(".receiver__opt").trigger("click");

    await w.find("form").trigger("submit");
    await flushPromises();

    const posted = fetchMock.calls.find((c) => c.url.includes("/intel/true-profit"));
    const body = JSON.parse(posted.opts.body);
    expect(body.receiver_facility_id).toBe("fac-77");
    expect(body.receiver_facility_id).not.toBe(NIL);
    w.unmount();
  });

  it("does not ask for a receiver when the load already knows it", async () => {
    // with an active stop the load states its own dock; asking again invites a driver to
    // contradict their own load
    activeStopId.value = "stop-1";
    const fetchMock = vi.fn((url) => {
      const u = String(url);
      if (u.includes("/meter")) {
        return jsonOk({ facility_id: "fac-from-load", rate_cents: 250000, free_time_minutes: 90 });
      }
      if (u.includes("/intel/true-profit")) return jsonOk(WITH_RECEIVER);
      return jsonOk({});
    });
    vi.stubGlobal("fetch", fetchMock);
    const w = await mountCalc();
    await flushPromises();

    expect(w.find(".receiver").exists()).toBe(false);
    w.unmount();
  });
});
