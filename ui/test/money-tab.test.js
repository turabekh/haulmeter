// AI-CONTEXT: the Money tab, rebuilt around what a driver actually asks (§23 entry 142).
//
// What it was: a hero labelled "Delivered to you" over `recovered + fuel_saved + flagged`
// — a LIFETIME total including money an audit merely SUSPECTS is owed — above a heading
// that said "Money owed" over a list that included claims already paid, newest first,
// with no tap target on any row. §10.3 has specified a per-receivable "Next action" since
// it was written and there was none; the only way to record a payment was a button at the
// bottom asking "which claim did the broker pay?" after the driver had been looking
// straight at it.
//
// These assert the three things that make it usable: the hero is a SUM OF THE LIST, the
// list holds only what is outstanding and puts the most stuck claim first, and a row is a
// control that leads somewhere with a next step.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import MoneySurface from "../src/surfaces/MoneySurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import { __resetStateForTests, observeMotion, DRIVING_SUSTAIN_MS } from "../src/core/state.js";
import en from "../src/core/i18n/en.json";

const T0 = 1_760_000_000_000;

const OUTSTANDING = [
  {
    receivable_id: "r1", kind: "detention", state: "invoiced", amount_cents: 18750,
    aging_days: 12, counterparty_name: "Bolt Logistics", facility_name: "Harvest Foods DC",
    stop_id: "s1", history: [{ event: "invoiced", at: "2026-07-30T12:00:00+00:00" }],
  },
  {
    receivable_id: "r3", kind: "lumper", state: "escalated", amount_cents: 12500,
    aging_days: 63, counterparty_name: "Blue Road Logistics", facility_name: "Kroger DC",
    stop_id: "s3",
    history: [
      { event: "invoiced", at: "2026-06-09T12:00:00+00:00" },
      { event: "nudged", at: "2026-06-12T09:00:00+00:00" },
      { event: "firmed", at: "2026-06-19T09:00:00+00:00" },
    ],
  },
];
const SETTLED = {
  receivable_id: "r6", kind: "detention", state: "recovered", amount_cents: 8125,
  aging_days: 88, counterparty_name: "TQL", facility_name: "Old Dock", stop_id: "s6",
  history: [],
};
const EARNINGS = {
  ddd_cents: 143250, recovered_cents: 98700, fuel_saved_cents: 41050, flagged_cents: 3500,
};

function jsonOk(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function stub(rows = [...OUTSTANDING, SETTLED], calls = {}) {
  return vi.fn((url, opts) => {
    const u = String(url);
    if (u.includes("/accessorial/owed")) return jsonOk(rows);
    if (u.includes("/money/earnings")) return jsonOk(EARNINGS);
    if (u.includes("/paid") && opts?.method === "POST") {
      calls.paid = u;
      return jsonOk({ ok: true });
    }
    if (u.includes("/me")) return jsonOk({ verified: false });
    return jsonOk({});
  });
}

async function mountMoney(fetchStub) {
  vi.stubGlobal("fetch", fetchStub);
  setToken("tok");
  const router = createRouter({ history: createMemoryHistory(), routes });
  router.push("/money");
  await router.isReady();
  const w = mount(MoneySurface, { global: { plugins: [router] } });
  await flushPromises();
  return { w, router };
}

afterEach(() => {
  vi.unstubAllGlobals();
  __resetStateForTests();
  logout();
});

describe("The big number is the one a driver came to see", () => {
  it("is what they are owed, and it is the SUM OF THE LIST below it", async () => {
    // "Delivered to you $1,432.50" was recovered + fuel saved + money an audit merely
    // suspects is owed. It told a driver they had received $1,432.50 when they had
    // received $987 — the largest, greenest figure on the screen, in Mono, wrong.
    const { w } = await mountMoney(stub());

    expect(w.find(".meter__figure").text()).toBe("$312.50"); // 18750 + 12500
    expect(w.text()).toContain(en["money.owed_label"]);
    expect(w.text()).not.toContain(en["money.delivered"]);
  });

  it("excludes what has already been paid from the figure", async () => {
    // the settled row is $81.25 and must not inflate what a driver thinks they can chase
    const { w } = await mountMoney(stub());
    expect(w.find(".meter__figure").text()).not.toContain("393");
  });

  it("says how many brokers are sitting on it", async () => {
    const { w } = await mountMoney(stub());
    expect(w.text()).toContain(en["money.owed_from"].replace("{n}", "2"));
  });

  it("still shows what was actually paid and saved, named for what they are", async () => {
    const { w } = await mountMoney(stub());
    expect(w.text()).toContain(en["money.paid_so_far"]);
    expect(w.text()).toContain("$987.00");
    expect(w.text()).toContain("$410.50");
  });
});

describe("The list is what is outstanding, most stuck first", () => {
  it("keeps settled claims out of 'Waiting on brokers'", async () => {
    // `money_owed` returns EVERY receivable, `recovered` included, and this tab rendered
    // them all under a heading that says they are owed.
    const { w } = await mountMoney(stub());

    const rows = w.findAll(".rows .row");
    expect(rows).toHaveLength(2);
    expect(rows.map((r) => r.text()).join(" | ")).not.toContain("TQL");
  });

  it("puts the oldest claim first, not the newest", async () => {
    // the API orders newest-first, which buries the claim a broker has been ignoring
    // for 63 days under one filed last week.
    const { w } = await mountMoney(stub());

    const rows = w.findAll(".rows .row");
    expect(rows[0].text()).toContain("Blue Road Logistics");
    expect(rows[0].text()).toContain(en["money.days"].replace("{n}", "63"));
  });

  it("names who owes it and whether anyone has chased them", async () => {
    const { w } = await mountMoney(stub());
    const first = w.findAll(".rows .row")[0].text();

    expect(first).toContain("Blue Road Logistics");
    expect(first).toContain(en["money.chased_many"].replace("{n}", "2"));
  });

  it("says 'Nothing sent yet' rather than implying a claim is being worked", async () => {
    // §11.7 on the screen about getting paid: a history that padded itself would tell a
    // driver their claim was moving while it sat still.
    const { w } = await mountMoney(stub([OUTSTANDING[0]]));
    expect(w.find(".rows .row").text()).toContain(en["money.chased_none"]);
  });

  it("tucks settled claims into their own section, still reachable", async () => {
    const { w } = await mountMoney(stub());

    expect(w.text()).not.toContain("TQL");
    await w.find(".settled-toggle").trigger("click");
    await flushPromises();
    expect(w.text()).toContain("TQL");
    expect(w.text()).toContain("$81.25");
  });

  it("says everything is paid when nothing is outstanding", async () => {
    // a different sentence from "nothing here yet", and one a driver has earned.
    const { w } = await mountMoney(stub([SETTLED]));
    expect(w.text()).toContain(en["money.all_paid"]);
    expect(w.find(".meter__figure").text()).toBe("$0.00");
  });
});

describe("A row leads somewhere, with a next step (§10.3)", () => {
  async function openFirst(fetchStub) {
    const { w, router } = await mountMoney(fetchStub || stub());
    await w.findAll(".rows .row")[0].trigger("click");
    await flushPromises();
    return { w, router };
  }

  it("opens the claim, with who owes it and what has been sent", async () => {
    const { w } = await openFirst();
    const sheet = w.find(".cm");

    expect(sheet.exists()).toBe(true);
    expect(sheet.text()).toContain("Blue Road Logistics");
    expect(sheet.text()).toContain("Kroger DC");
    expect(sheet.text()).toContain(en["money.ev.invoiced"]);
    expect(sheet.text()).toContain(en["money.ev.firmed"]);
  });

  it("offers ONE Primary, and it is the act that can still change the outcome", async () => {
    const { w } = await openFirst();
    const filled = w.findAll(".cm .cta").filter((b) => !b.classes().includes("cta--text"));

    expect(filled).toHaveLength(1);
    expect(filled[0].text()).toContain(en["money.act_chase"]);
  });

  it("records a payment from the claim the driver is looking at", async () => {
    // it used to be a button at the bottom of the tab that asked "which claim did the
    // broker pay?" — after they had been looking straight at it.
    const calls = {};
    const { w } = await openFirst(stub([...OUTSTANDING, SETTLED], calls));
    await w.findAll(".cm .cta--text").find((b) => b.text().includes(en["money.act_paid"])).trigger("click");
    await flushPromises();

    expect(calls.paid, "no payment was recorded").toBeTruthy();
    expect(calls.paid).toContain("r3"); // the row that was open, not a list to re-pick from
  });

  it("chasing opens the ghostwriter rather than sending a second automatic mail", async () => {
    // M11-FR3 already drafts "the firm message that unsticks pay" and sat on this tab as
    // an unnamed button called "Ghostwriter". Routing the chase through it keeps the
    // driver as the sender — no second mail beside the dunning job's own cadence.
    const { w } = await openFirst();
    await w.findAll(".cm .cta").find((b) => b.text().includes(en["money.act_chase"])).trigger("click");
    await flushPromises();

    expect(w.find(".cm").exists()).toBe(false);
    expect(w.text()).toContain(en["ghost.facts"]);
  });

  it("reaches the evidence behind the claim", async () => {
    const { w, router } = await openFirst();
    await w.findAll(".cm .cta--text").find((b) => b.text().includes(en["money.act_evidence"])).trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.path).toBe("/load/s3/evidence");
  });

  it("offers no evidence link when the claim has no stop behind it", async () => {
    // a control that can only 404 is the dead-control pattern §23 entry 72 records.
    const { w } = await mountMoney(stub([{ ...OUTSTANDING[0], stop_id: null }]));
    await w.findAll(".rows .row")[0].trigger("click");
    await flushPromises();

    expect(w.find(".cm").text()).not.toContain(en["money.act_evidence"]);
  });

  it("withdraws at speed (§10.3: read-only while DRIVING)", async () => {
    const { w } = await openFirst();
    observeMotion({ speedMps: 25, now: T0 });
    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS });
    await flushPromises();

    expect(w.find(".cm").exists()).toBe(false);
    expect(w.text()).toContain("$312.50"); // the figures stay readable, which §10.3 allows
  });
});
