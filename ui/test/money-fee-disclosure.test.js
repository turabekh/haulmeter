// AI-CONTEXT: the paid moment on the Money tab — the fee shown, and the year figure that
// reconciles against it (J1 parts 3-4).
//
// §23 entry 142 replaced a hero that summed things the list did not show. The rule it left
// behind is that a big figure must be a sum of the rows beneath it, so a driver can add it
// up on their own screen. R1 extends that: the year figure is NET, and the fee appears as a
// visible deduction on the row it came from rather than being implied by a smaller total.
//
// The failure this guards against is the comfortable one. A gross year figure looks better
// and is wrong by exactly what we took; a fee left in the outstanding list would have
// inflated "what you are owed" with money the driver owes US.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import MoneySurface from "../src/surfaces/MoneySurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

function jsonOk(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

// one recovery of $340 with our $51 taken, and one broker still sitting on $200
const ROWS = [
  {
    receivable_id: "r-1", kind: "detention", amount_cents: 34000, state: "recovered",
    aging_days: 30, counterparty_name: "Cardinal", facility_name: "Harvest Foods DC",
    stop_id: "s-1", history: [], fee_cents: 5100, net_cents: 28900,
  },
  {
    receivable_id: "r-2", kind: "detention", amount_cents: 20000, state: "invoiced",
    aging_days: 12, counterparty_name: "Coyote", facility_name: "ACME",
    stop_id: "s-2", history: [], fee_cents: 0, net_cents: 20000,
  },
];

const EARNINGS = {
  recovered_cents: 34000, fuel_saved_cents: 0, flagged_cents: 0, ddd_cents: 34000,
  recovered_year_gross_cents: 34000, fees_year_cents: 5100,
  recovered_year_net_cents: 28900, year: 2026,
};

async function mountMoney({ rows = ROWS, earnings = EARNINGS } = {}) {
  setToken("tok-money");
  vi.stubGlobal(
    "fetch",
    vi.fn((url) => {
      const u = String(url);
      if (u.includes("/money/earnings")) return jsonOk(earnings);
      if (u.includes("/owed")) return jsonOk(rows);
      return jsonOk({});
    }),
  );
  const router = createRouter({ history: createMemoryHistory(), routes });
  router.push("/money");
  await router.isReady();
  const w = mount(MoneySurface, { global: { plugins: [router] } });
  await flushPromises();
  return w;
}

afterEach(() => {
  vi.unstubAllGlobals();
  logout();
});

describe("the paid moment, and the figure it reconciles to", () => {
  it("shows the fee as a visible deduction on the recovery it came from", async () => {
    const w = await mountMoney();
    await w.find(".settled-toggle").trigger("click");
    await flushPromises();

    const fee = w.find(".row__fee");
    expect(fee.exists()).toBe(true);
    expect(fee.text()).toContain("$51.00");
    expect(fee.text()).toContain("$289.00");
  });

  it("says plainly that the fee has not been collected", async () => {
    // a fee shown without that sentence reads as money already gone
    const w = await mountMoney();
    await w.find(".settled-toggle").trigger("click");
    await flushPromises();

    expect(w.find(".row__feenote").text()).toBe(en["money.fee_uncollected"]);
  });

  it("renders the year figure NET, not gross", async () => {
    const w = await mountMoney();

    const year = w.find(".year");
    expect(year.exists()).toBe(true);
    expect(year.text()).toContain("$289.00");
    expect(year.text()).not.toContain("$340.00");
  });

  it("the year figure equals the settled rows a driver can open", async () => {
    // entry 142's property, checked the way a driver would check it
    const w = await mountMoney();
    await w.find(".settled-toggle").trigger("click");
    await flushPromises();

    const listedNet = ROWS.filter((r) => r.state === "recovered")
      .reduce((n, r) => n + r.net_cents, 0);
    expect(w.find(".year__figure").text()).toBe("$289.00");
    expect(listedNet).toBe(28900);
  });

  it("never adds a fee to what brokers owe", async () => {
    // the defect this would otherwise have shipped: a fee receivable never leaves
    // `invoiced`, so it would have been summed into the "what you are owed" hero
    const w = await mountMoney();

    // the hero is the one outstanding claim only, not the claim plus our fee
    expect(w.find(".meter__figure").text()).toBe("$200.00");
  });

  it("shows no fee line on a recovery that never had one", async () => {
    // zero taken, whole amount kept — a deduction line of −$0.00 would be noise
    const rows = [{ ...ROWS[0], fee_cents: 0, net_cents: 34000 }];
    const w = await mountMoney({
      rows,
      earnings: { ...EARNINGS, fees_year_cents: 0, recovered_year_net_cents: 34000 },
    });
    await w.find(".settled-toggle").trigger("click");
    await flushPromises();

    expect(w.find(".row__fee").exists()).toBe(false);
    expect(w.find(".year__figure").text()).toBe("$340.00");
  });

  it("shows no year line at all before the first recovery", async () => {
    // §15.3: an empty state says what it is, and a "$0.00 recovered in 2026" would be
    // the product reporting its own failure to a driver who has just arrived
    const w = await mountMoney({
      rows: [ROWS[1]],
      earnings: { ...EARNINGS, recovered_year_gross_cents: 0, fees_year_cents: 0,
                  recovered_year_net_cents: 0 },
    });

    expect(w.find(".year").exists()).toBe(false);
  });
});
