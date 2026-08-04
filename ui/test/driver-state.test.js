// AI-CONTEXT: §5's deriver, which never existed.
//
// `state.js` has claimed since it was written that "state is derived from F3
// motion/geofence signals + time", and nothing derived anything — `setState` was
// called from tests and from no other line in the app. DriverState was therefore
// permanently IDLE in production and every DRIVING behaviour in the product was
// unreachable: §10.2's Meter-only glance, §11.4 Corridor mode, §10.3's read-only
// Money, §10.4's inspection confirm, and the withdrawal guards on seven surfaces.
// All correct, all inert. These tests hold the transitions §5 actually specifies.
import { describe, it, expect, beforeEach } from "vitest";
import {
  DriverState,
  useDriverState,
  observeMotion,
  observePresence,
  WALKING_SPEED_MPS,
  DRIVING_SUSTAIN_MS,
  STOPPED_SUSTAIN_MS,
  __resetStateForTests,
} from "../src/core/state.js";

const T0 = 1_780_000_000_000; // a fixed instant: a clock the test does not control
const { state } = useDriverState();

describe("§5 driver state machine — the deriver", () => {
  beforeEach(() => __resetStateForTests());

  it("starts IDLE, which is what production had forever", () => {
    expect(state.value).toBe(DriverState.IDLE);
  });

  it("needs motion to be SUSTAINED, not just fast once (§5, SM-1)", () => {
    // one fast fix is a GPS spike, not a journey
    observeMotion({ speedMps: 25, now: T0 });
    expect(state.value).toBe(DriverState.IDLE);

    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS - 1 });
    expect(state.value).toBe(DriverState.IDLE);

    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS });
    expect(state.value).toBe(DriverState.DRIVING);
  });

  it("ignores walking pace — §5's threshold is above WALKING speed", () => {
    for (let i = 0; i <= 5; i++) {
      observeMotion({ speedMps: WALKING_SPEED_MPS - 0.6, now: T0 + i * 60_000 });
    }
    expect(state.value).toBe(DriverState.IDLE);
  });

  // SM-1: transitions are calm. Leaving takes longer than entering, so a red light
  // does not strobe the type scale back and forth.
  it("does not leave DRIVING at the first red light", () => {
    observeMotion({ speedMps: 25, now: T0 });
    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS });
    expect(state.value).toBe(DriverState.DRIVING);

    observeMotion({ speedMps: 0, now: T0 + DRIVING_SUSTAIN_MS + 30_000 });
    expect(state.value).toBe(DriverState.DRIVING); // still stopped at the light

    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS + 45_000 });
    expect(state.value).toBe(DriverState.DRIVING); // moving again, never flickered
  });

  it("settles out of DRIVING once the truck has genuinely stopped", () => {
    observeMotion({ speedMps: 25, now: T0 });
    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS });
    const stopped = T0 + DRIVING_SUSTAIN_MS + 1000;

    observeMotion({ speedMps: 0, now: stopped });
    observeMotion({ speedMps: 0, now: stopped + STOPPED_SUSTAIN_MS });

    expect(state.value).toBe(DriverState.IDLE);
  });

  it("lands in ON_SITE rather than IDLE when the stop is where it stopped (§5)", () => {
    observeMotion({ present: true });
    observeMotion({ speedMps: 25, now: T0 });
    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS });
    expect(state.value).toBe(DriverState.DRIVING); // DRIVING outranks ON_SITE

    const stopped = T0 + DRIVING_SUSTAIN_MS + 1000;
    observeMotion({ speedMps: 0, now: stopped });
    observeMotion({ speedMps: 0, now: stopped + STOPPED_SUSTAIN_MS });

    expect(state.value).toBe(DriverState.ON_SITE);
  });

  it("returns to IDLE when the geofence says the driver has left", () => {
    observeMotion({ present: true });
    observeMotion({ speedMps: 0, now: T0 });
    expect(state.value).toBe(DriverState.ON_SITE);

    observeMotion({ present: false });
    observeMotion({ speedMps: 0, now: T0 + 1000 });
    expect(state.value).toBe(DriverState.IDLE);
  });

  // AI-CONTEXT: an unknown speed is not evidence of stopping. Desktop browsers always
  // report `coords.speed` as null and phones often do on a first fix; treating that as
  // "stopped" would drop the app out of glance mode mid-journey.
  it("holds DRIVING through fixes that carry no speed at all", () => {
    observeMotion({ speedMps: 25, now: T0 });
    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS });
    expect(state.value).toBe(DriverState.DRIVING);

    observeMotion({ speedMps: null, now: T0 + DRIVING_SUSTAIN_MS + 10 * 60_000 });

    expect(state.value).toBe(DriverState.DRIVING);
  });

  it("stamps data-state on the root so the token layer picks up glance mode (§6.2 T-1)", () => {
    observeMotion({ speedMps: 25, now: T0 });
    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS });
    expect(document.documentElement.getAttribute("data-state")).toBe("driving");

    const stopped = T0 + DRIVING_SUSTAIN_MS + 1000;
    observeMotion({ speedMps: 0, now: stopped });
    observeMotion({ speedMps: 0, now: stopped + STOPPED_SUSTAIN_MS });
    expect(document.documentElement.getAttribute("data-state")).toBe(null);
  });
});

// AI-CONTEXT: ON_SITE was reachable in these tests and effectively unreachable in a
// truck, which is the gap this block exists to close.
//
// Presence arrived ONLY as an ENTER edge in a ping response. `onSite` is module state,
// so a reload set it back to false with no edge left to restore it, and the "I've
// arrived" fallback — the path a driver takes precisely when the background sensor did
// NOT fire — produced no edge at all. Every ON_SITE behaviour in the product was
// therefore dark in normal use while looking correct here. `/location/ping` now
// answers presence as a STATE on every ping.
describe("§5 ON_SITE — presence as a state, not only an edge", () => {
  beforeEach(() => __resetStateForTests());

  it("goes ON_SITE from a plain presence fact, with no ENTER edge in sight", () => {
    expect(state.value).toBe(DriverState.IDLE);
    observePresence(true);
    expect(state.value).toBe(DriverState.ON_SITE);
  });

  it("survives what a reload used to destroy — the next ping restores it", () => {
    observePresence(true);
    __resetStateForTests(); // a cold start: module state is gone, the ENTER is history
    expect(state.value).toBe(DriverState.IDLE);

    observePresence(true); // the very next ping carries the steady state
    expect(state.value).toBe(DriverState.ON_SITE);
  });

  it("leaves ON_SITE when the fact stops being true", () => {
    observePresence(true);
    observePresence(false);
    expect(state.value).toBe(DriverState.IDLE);
  });

  it("does not interrupt DRIVING — a truck rolling through a yard is driving (SM-1)", () => {
    observeMotion({ speedMps: 25, now: T0 });
    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS });
    expect(state.value).toBe(DriverState.DRIVING);

    observePresence(true);

    expect(state.value).toBe(DriverState.DRIVING);
  });

  it("and the presence it was handed mid-drive settles in once the truck stops", () => {
    observeMotion({ speedMps: 25, now: T0 });
    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS });
    observePresence(true);

    const stopped = T0 + DRIVING_SUSTAIN_MS + 1000;
    observeMotion({ speedMps: 0, now: stopped });
    observeMotion({ speedMps: 0, now: stopped + STOPPED_SUSTAIN_MS });

    expect(state.value).toBe(DriverState.ON_SITE);
  });
});
