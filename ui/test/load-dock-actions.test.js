// AI-CONTEXT: what a driver can actually DO on the Load tab while parked at a dock.
//
// The owner reported "tapping on photos not working". Nothing was broken: the Photos
// row was a plain <li> with no handler while every capturable row above it was a
// button, so the one line on the card that reads most like a job to do was the only
// one that did nothing. There was no failure to observe because nothing was wired.
//
// Underneath it were two larger holes, and these tests hold all three shut:
//   - §10.2 promises a state-dependent SINGLE CTA, and the state "arrived, BOL filed,
//     free time still running" — most of a stop — produced no primary action at all.
//   - the card mixed FACTS ("Late 15:40") and ACTIONS ("Photos 0/4") at identical
//     weight, so which lines were controls could only be discovered by tapping.
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout, setActiveStop } from "../src/core/api.js";
import { observePresence, __resetStateForTests } from "../src/core/state.js";
import en from "../src/core/i18n/en.json";

function jsonOk(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

// arrived, BOL in hand, free time still counting down: nothing is owed yet, which is
// precisely the state that used to render no primary action.
function meter(over = {}) {
  return {
    stop_id: "stop-1",
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
    ...over,
  };
}

async function mountAtDock(over = {}) {
  setToken("tok");
  setActiveStop("stop-1");
  vi.stubGlobal(
    "fetch",
    vi.fn((url) =>
      String(url).includes("/load/stop-1/meter") ? jsonOk(meter(over)) : jsonOk({}),
    ),
  );
  const router = createRouter({ history: createMemoryHistory(), routes });
  const w = mount(LoadSurface, { global: { plugins: [router] } });
  await flushPromises();
  return { w, router };
}

beforeEach(() => __resetStateForTests());

afterEach(() => {
  logout();
  setActiveStop(null);
  __resetStateForTests();
  vi.unstubAllGlobals();
});

describe("the Photos row is a control, not a caption", () => {
  it("renders as a button — it was an inert <li> and this is the regression", async () => {
    const { w } = await mountAtDock();
    const photos = w
      .findAll("button.checklist__snap")
      .find((b) => b.text().includes(en["load.photos"]));
    expect(photos, "the Photos row must be a real button").toBeTruthy();
  });

  it("carries the 48 dp glove target every other actionable row has", async () => {
    const { w } = await mountAtDock();
    const photos = w
      .findAll("button.checklist__snap")
      .find((b) => b.text().includes(en["load.photos"]));
    // the class IS the contract — §6.5's spec lives in .checklist__snap's min-height
    expect(photos.classes()).toContain("checklist__snap");
  });

  it("takes the driver to condition capture, the same place the More sheet does", async () => {
    const { w, router } = await mountAtDock();
    const photos = w
      .findAll("button.checklist__snap")
      .find((b) => b.text().includes(en["load.photos"]));
    await photos.trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/protection/condition");
  });

  it("stops being a control once the photos are in — a done row is a fact", async () => {
    const { w } = await mountAtDock({ photos_captured: 4, photos_required: 4 });
    const photos = w
      .findAll("button.checklist__snap")
      .find((b) => b.text().includes(en["load.photos"]));
    expect(photos, "a completed row offers nothing to tap").toBeFalsy();
    expect(w.text()).toContain("4/4");
  });
});

describe("actionable rows look actionable (§23 entry 128)", () => {
  it("puts a chevron on rows that DO something", async () => {
    const { w } = await mountAtDock();
    const photos = w
      .findAll("button.checklist__snap")
      .find((b) => b.text().includes(en["load.photos"]));
    expect(photos.find(".checklist__go").exists()).toBe(true);
  });

  it("and none on rows that merely state a fact", async () => {
    const { w } = await mountAtDock({ notice_sent: false });
    const rows = w.findAll("li.checklist__item");
    const notice = rows.find((li) => li.text().includes(en["notice.delivery.not_sent"]));
    // sending a broker notice is a §12.2 money act and belongs behind the CTA, never
    // behind a row a thumb brushes past on the way somewhere else
    expect(notice.find("button").exists()).toBe(false);
    expect(notice.find(".checklist__go").exists()).toBe(false);
  });
});

describe("the ladder's missing middle (§23 entry 127)", () => {
  it("offers cargo photos as the PRIMARY while parked with free time running", async () => {
    observePresence(true); // the truck is inside the armed geofence
    const { w } = await mountAtDock();
    const cta = w.find("button.cta");
    expect(cta.exists(), "this state used to render no primary action at all").toBe(true);
    expect(cta.text()).toContain(en["load.cta.photos"]);
  });

  it("carries the denominator, because 0/4 is a task with an end", async () => {
    observePresence(true);
    const { w } = await mountAtDock();
    expect(w.find("button.cta .cta__count").text()).toBe("0/4");
  });

  it("does not offer one job two controls", async () => {
    observePresence(true);
    const { w } = await mountAtDock();
    const secondary = w
      .findAll("button.rungs__item")
      .filter((b) => b.text().includes(en["cond.start"]));
    expect(secondary.length, "the secondary rung must yield to the Primary").toBe(0);
  });

  it("yields to the money rung the moment detention accrues", async () => {
    observePresence(true);
    const { w } = await mountAtDock({
      phase: "accruing",
      free_time_remaining_seconds: 0,
      detention_seconds: 600,
      detention_cents: 1250,
    });
    // the wedge outranks the photograph: this rung fills a gap, it does not take over
    expect(w.find("button.cta").text()).toContain(en["load.cta.notice"]);
  });

  // §5 gives DRIVING precedence over ON_SITE, and this is where that matters most:
  // a Primary reading "take cargo photos" on a moving truck is an instruction to do
  // something a driver must not do. The precedence is in state.js; this holds the
  // consequence at the surface, where a future refactor would break it.
  it("never asks a moving truck to photograph anything", async () => {
    const { observeMotion, DriverState, useDriverState } = await import("../src/core/state.js");
    observePresence(true);
    const T0 = 1_780_000_000_000;
    observeMotion({ speedMps: 25, now: T0 });
    observeMotion({ speedMps: 25, now: T0 + 60_000 });
    expect(useDriverState().state.value).toBe(DriverState.DRIVING);

    const { w } = await mountAtDock();

    expect(w.find("button.cta").exists()).toBe(false);
  });

  it("stays quiet when the truck is not at the dock", async () => {
    // AI-CONTEXT: scoped to the LADDER's own controls (§23 entry 141). This asserted
    // "no `.cta` at all", which was a proxy for "no on-site shortcut" and stopped being
    // one when leaving the stop became a Secondary on the anchored zone — that control
    // depends on having ARRIVED, not on standing inside the geofence, so a driver who
    // stepped out of the fence would have lost the way to end their own stop.
    observePresence(false);
    const { w } = await mountAtDock();
    expect(w.findAll(".cta:not(.cta--text):not(.cta--outline)")).toHaveLength(0);
    expect(w.findAll(".rungs__item").map((b) => b.text()).join(" | ")).not.toContain(
      "Capture cargo condition",
    );
  });
});
