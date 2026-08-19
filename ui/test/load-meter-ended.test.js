// AI-CONTEXT: "the ticker starts correctly and converts to the paid ticker correctly,
// but when I add a BOL or other photos it goes back and freezes" — the owner, 2026-08-19.
//
// Reproduced in this component before anything was changed: with M3's THIRD phase,
// `ended`, the tab rendered "2:00:00 · Free time" while the same payload carried
// detention_cents 7500. `deriveArrival` handled `within_free_time` and `accruing` and
// fell through to the `not_arrived` branch for `ended`, so `arrivalMs` went null — and
// `state` reads `arrivalMs ?? now`, which pins elapsed at zero on every tick. Both
// halves of the report, "goes back" and "freezes", out of one missing case.
//
// Why a capture is what surfaces it: `onBolCaptured` re-reads the meter the moment a
// document lands, so a stop the server has since decided is over repaints the tab.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout, setActiveStop } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

const jsonOk = (b) => Promise.resolve({ ok: true, json: () => Promise.resolve(b) });
const BASE = {
  stop_id: "stop-1", facility_name: "Dock 4", counterparty: "Acme", appointment: null,
  arrived: true, free_time_minutes: 120, rate_cents_per_hour: 7500, notice_sent: true,
  photos_captured: 0, photos_required: 4, bol_captured: true, checklist: [], filed: false,
};
const ACCRUING = { ...BASE, phase: "accruing", free_time_remaining_seconds: 0,
  detention_seconds: 3600, detention_cents: 7500 };
const ENDED = { ...BASE, phase: "ended", free_time_remaining_seconds: 0,
  detention_seconds: 3600, detention_cents: 7500 };

async function mountMeter(payload) {
  setToken("tok");
  setActiveStop("stop-1");
  vi.stubGlobal("fetch", vi.fn((u) =>
    String(u).includes("/meter") ? jsonOk(payload) : jsonOk({})));
  const w = mount(LoadSurface, {
    global: { plugins: [createRouter({ history: createMemoryHistory(), routes })] },
  });
  await flushPromises();
  return w;
}

afterEach(() => { vi.unstubAllGlobals(); logout(); });

describe("The Meter when M3 says the visit has ENDED", () => {
  it("keeps showing money, not a restarted free-time countdown", async () => {
    const w = await mountMeter(ENDED);
    expect(w.find(".meter__figure").text()).toBe("$75.00");
    expect(w.find(".meter__label").text()).toBe(en["load.detention"]);
  });

  it("never renders the full free time it had already counted through", async () => {
    // the exact string the owner saw: 2:00:00, the whole of free time, back on the clock
    const w = await mountMeter(ENDED);
    expect(w.find(".meter__figure").text()).not.toBe("2:00:00");
    expect(w.find(".meter__label").text()).not.toBe(en["load.free_time"]);
  });

  it("shows the SERVER's final figure rather than one re-derived on the phone", async () => {
    // two arithmetics for one amount is how they come to disagree, and this is the
    // number the claim will be filed for
    const w = await mountMeter({ ...ENDED, detention_cents: 12345 });
    expect(w.find(".meter__figure").text()).toBe("$123.45");
  });

  it("says the clock stopped, and how long the stop ran", async () => {
    const w = await mountMeter(ENDED);
    const status = w.find(".meter__status").text();
    expect(status).toContain(en["load.stop_ended"]);
    expect(status).toContain("1:00:00");
  });

  it("does not tick on after the truck has left", async () => {
    vi.useFakeTimers();
    try {
      const w = await mountMeter(ENDED);
      const before = w.find(".meter__figure").text();
      vi.advanceTimersByTime(60_000);
      await flushPromises();
      expect(w.find(".meter__figure").text()).toBe(before);
    } finally {
      vi.useRealTimers();
    }
  });

  it("still offers the claim — the money is owed whether or not the truck is there", async () => {
    // `claimable` reads `accruing`, which was false under the broken derivation, so the
    // ladder lost its rung at exactly the moment the claim became fileable
    const w = await mountMeter(ENDED);
    expect(w.text()).toContain(en["load.cta.claim"]);
  });

  it("leaves the accruing case exactly as it was", async () => {
    const w = await mountMeter(ACCRUING);
    expect(w.find(".meter__figure").text()).toBe("$75.00");
    expect(w.find(".meter__label").text()).toBe(en["load.detention"]);
  });
});
