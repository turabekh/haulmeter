// AI-CONTEXT: J1-B1's IN-APP half — the arrival path that needs no push and no sensor.
//
// The push (entry 169) can be filed by quiet hours, refused at the OS level, or never
// granted at all; the background sensor is the one mechanism v2.0 DoD #8 records as
// UNPROVEN. §15.5's rule is build for auto, degrade to one-tap, never to nothing, so the
// half that survives all of that is the Load tab itself: open the app near your
// appointment and the screen says so, with the arrival CTA already primary.
//
// THIS BEHAVIOUR ALREADY EXISTED AND NOTHING ASSERTED IT. `apptPassed`, the countdown
// label and the warning variant have been in `LoadSurface` since the meter was written,
// and a grep for `appt_passed` across the whole test tree and the layout harness returned
// nothing. Built, correct, and one refactor away from disappearing without a single test
// going red — the shape HANDOFF-122 named and this codebase keeps rediscovering. B1's
// in-app half therefore needed no new screen; it needed this file.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import TheMeter from "../src/core/components/TheMeter.vue";
import { routes } from "../src/router.js";
import { setToken, logout, setActiveStop } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

function jsonOk(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

// an ARMED stop the driver has not reached yet — the state the reminder is about
function preArrival(appointmentOffsetMinutes) {
  const appointment =
    appointmentOffsetMinutes === null
      ? null
      : new Date(Date.now() + appointmentOffsetMinutes * 60000).toISOString();
  return {
    stop_id: "stop-1",
    facility_name: "Harvest Foods DC",
    counterparty: "Cardinal",
    appointment,
    appointment_source: "rate_con_parse",
    arrived: false,
    arrived_at: null,
    free_time_minutes: 120,
    rate_cents_per_hour: 7500,
    phase: "not_arrived",
    free_time_remaining_seconds: 7200,
    detention_seconds: 0,
    detention_cents: 0,
    notice_sent: false,
    notice_delivery: "not_sent",
    photos_captured: 0,
    photos_required: 4,
    bol_captured: false,
    filed: false,
  };
}

async function mountAt(offsetMinutes) {
  setToken("tok-arrival");
  setActiveStop("stop-1");
  vi.stubGlobal(
    "fetch",
    vi.fn((url) =>
      String(url).includes("/load/stop-1/meter")
        ? jsonOk(preArrival(offsetMinutes))
        : jsonOk({}),
    ),
  );
  const router = createRouter({ history: createMemoryHistory(), routes });
  router.push("/load");
  await router.isReady();
  const w = mount(LoadSurface, { global: { plugins: [router] } });
  await flushPromises();
  return w;
}

afterEach(() => {
  vi.unstubAllGlobals();
  logout();
});

describe("the arrival path, in the app, with no push and no sensor", () => {
  it("counts down to an appointment still ahead", async () => {
    const w = await mountAt(45);

    expect(w.text()).toContain(en["load.until_appt"]);
    // and NOT the passed wording — a driver 45 minutes early is not late
    expect(w.text()).not.toContain(en["load.appt_passed"]);
    expect(w.findComponent(TheMeter).props("variant")).toBe("countdown");
    w.unmount();
  });

  it("says the appointment has passed, and says it as a WARNING", async () => {
    // the state the T-15 push exists to pre-empt. A driver who never got the push —
    // quiet hours, denied permission, no service — opens the app and the screen is
    // already saying it, which is what "degrade to one-tap, never to nothing" means.
    const w = await mountAt(-20);

    expect(w.text()).toContain(en["load.appt_passed"]);
    // §9 colours the Meter by VARIANT, applied as a token rather than a class, so the
    // prop is the honest thing to assert — reading the inline colour back would pin the
    // token name and go red the day the palette moves
    expect(w.findComponent(TheMeter).props("variant")).toBe("warning");
    w.unmount();
  });

  it("offers arrival as the PRIMARY action while the stop is unreached", async () => {
    // §13.5 says the push deep-links to /load with the arrival CTA in view. That is only
    // true if the CTA is actually primary here, which is the half a deep link cannot fix.
    const w = await mountAt(-20);

    const cta = w.find(".cta:not(.cta--text):not(.cta--outline)");
    expect(cta.exists()).toBe(true);
    expect(cta.text()).toContain(en["load.arrive"]);
    w.unmount();
  });

  it("says it is waiting when the load carries no appointment at all", async () => {
    // no appointment means nothing to be near, and inventing a countdown would be the
    // product manufacturing a deadline the contract never set
    const w = await mountAt(null);

    expect(w.text()).toContain(en["load.waiting"]);
    expect(w.text()).not.toContain(en["load.appt_passed"]);
    w.unmount();
  });
});
