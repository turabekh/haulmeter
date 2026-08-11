// AI-CONTEXT: finding F7 on the screen — the broker's "free time is nearly up" warning.
//
// The service function existed, was exported and unit-tested, and was called by nothing.
// Wiring it server-side is only half: if the ladder never offers the act, a driver-
// initiated notice is still a notice nobody sends.
//
// The boundary is the content. 31 minutes out there is nothing to warn about; inside 30
// there is, and it must say how long is left rather than the constant 30 — a driver who
// opens the tab with four minutes to go should be told four.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout, setActiveStop } from "../src/core/api.js";
import { useDriverState, DriverState, __resetStateForTests } from "../src/core/state.js";
import en from "../src/core/i18n/en.json";

function jsonOk(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

// arrived `120 - minutesLeft` minutes ago against a two-hour free window
function meter(minutesLeft) {
  const arrivedAt = new Date(Date.now() - (120 - minutesLeft) * 60000).toISOString();
  return {
    stop_id: "stop-1",
    facility_name: "Dock 4",
    counterparty: "Acme",
    appointment: null,
    arrived: true,
    arrived_at: arrivedAt,
    free_time_minutes: 120,
    rate_cents_per_hour: 7500,
    phase: "within_free_time",
    free_time_remaining_seconds: minutesLeft * 60,
    detention_seconds: 0,
    detention_cents: 0,
    notice_sent: false,
    notice_delivery: "not_sent",
    photos_captured: 4,
    photos_required: 4,
    bol_captured: true,
    filed: false,
  };
}

async function mountAt(minutesLeft, { noticeResponse } = {}) {
  setToken("tok");
  setActiveStop("stop-1");
  const posts = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url, opts) => {
      const u = String(url);
      if (u.includes("/load/stop-1/notice") && opts?.method === "POST") {
        posts.push(u);
        return jsonOk(noticeResponse ?? { sent: true, delivery: "sent", phase: "warning" });
      }
      if (u.includes("/load/stop-1/meter")) return jsonOk(meter(minutesLeft));
      return jsonOk({});
    }),
  );
  const w = mount(LoadSurface, {
    global: { plugins: [createRouter({ history: createMemoryHistory(), routes })] },
  });
  await flushPromises();
  return { w, posts };
}

function ctas(w) {
  return w.findAll("button.cta").map((b) => b.text());
}

afterEach(() => {
  vi.unstubAllGlobals();
  __resetStateForTests();
  logout();
});

describe("the broker's free-time warning", () => {
  it("is not offered with 31 minutes of free time left", async () => {
    const { w } = await mountAt(31);

    expect(ctas(w).some((text) => text.includes("Warn broker"))).toBe(false);
  });

  it("is offered inside the last half hour, naming the minutes actually left", async () => {
    const { w } = await mountAt(29);

    const cta = ctas(w).find((text) => text.includes("Warn broker"));
    expect(cta).toBeTruthy();
    // not the constant 30 — a worker that was down for twenty minutes must not tell a
    // driver they have thirty left, and the same rule applies to a tab opened late
    expect(cta).toContain("29 min");
  });

  it("retires once the warning has gone, so a second tap cannot repeat it", async () => {
    const { w, posts } = await mountAt(29);

    await w.findAll("button.cta").find((b) => b.text().includes("Warn broker")).trigger("click");
    await flushPromises();

    expect(posts.length).toBe(1);
    expect(ctas(w).some((text) => text.includes("Warn broker"))).toBe(false);
    expect(w.text()).toContain(en["load.warn_ok"]);
  });

  it("says the broker was warned, never that detention is on record", async () => {
    const { w } = await mountAt(29);

    await w.findAll("button.cta").find((b) => b.text().includes("Warn broker")).trigger("click");
    await flushPromises();

    // the start notice's copy asserts a clock that has started; this one has not
    expect(w.text()).not.toContain(en["load.notice_ok"]);
  });

  it("is suppressed in DRIVING, like every other interactive control here", async () => {
    // VERIFIED rather than assumed: the whole ladder lives inside `v-if="!isDriving"`,
    // so a new rung inherits the suppression — but a structural guarantee that nobody
    // checks is one refactor away from not being one.
    const { w } = await mountAt(29);
    expect(ctas(w).some((text) => text.includes("Warn broker"))).toBe(true);

    useDriverState().setState(DriverState.DRIVING);
    await flushPromises();

    expect(w.findAll("button.cta").length).toBe(0);
  });
});
