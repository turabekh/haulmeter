// AI-CONTEXT: the client half of F3, which had never existed. The running product
// could emit a geofence ENTER (from the arrive button, at the facility's own
// coordinates) and could NEVER emit an EXIT, because nothing ever sent the server a
// real position. These tests hold the two properties that make the sensor safe to
// leave running: it samples rather than floods (PRD §7.3's ≤5%/day battery budget),
// and it never replays a stale position as a current one.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  bearingBetween,
  permission,
  lastFix,
  lastEvents,
  samplingMode,
  shouldSend,
  startLocationReporting,
  stopLocationReporting,
  retryLocationPermission,
  __resetForTests,
} from "../src/core/location.js";
import { setToken, logout, setActiveStop } from "../src/core/api.js";

// AI-CONTEXT: count PINGS, not requests (§23 entry 115).
//
// This throttle is the battery budget, and the assertions used to count every call the
// stub saw. Establishing a session now also PUTs the driver's detected timezone — §13.3's
// "local" had been landing on UTC for every driver — so a total is no longer a ping
// count. What the test means is "how many positions did we send", and now it says so.
function pings(fetchStub) {
  return fetchStub.mock.calls.filter(([url]) => String(url).includes("/location/ping"));
}


const DALLAS = { lat: 32.7767, lon: -96.797 };

// let the send's promise chain (fetch -> json -> assignment) actually settle
const settle = () => new Promise((r) => setTimeout(r, 0));

function fakeGeolocation() {
  const watchers = [];
  const geo = {
    watchPosition: vi.fn((onFix, onErr, opts) => {
      watchers.push({ onFix, onErr, opts });
      return watchers.length;
    }),
    clearWatch: vi.fn(),
    // drive a fix into whichever watch is currently open
    emit(coords) {
      watchers[watchers.length - 1].onFix({ coords });
    },
    fail(code) {
      watchers[watchers.length - 1].onErr({ code });
    },
    get lastOptions() {
      return watchers[watchers.length - 1].opts;
    },
    watchers,
  };
  return geo;
}

describe("F3 location reporting (PRD §7.3)", () => {
  let geo;

  beforeEach(() => {
    __resetForTests();
    setActiveStop(null);
    logout();
    geo = fakeGeolocation();
    vi.stubGlobal("navigator", { geolocation: geo });
  });
  afterEach(() => {
    stopLocationReporting();
    vi.unstubAllGlobals();
    setActiveStop(null);
    logout();
  });

  it("reports 'unavailable' where there is no geolocation at all", () => {
    vi.stubGlobal("navigator", {});
    startLocationReporting();
    expect(permission.value).toBe("unavailable");
  });

  it("samples significant-change while idle and high-accuracy while a stop is armed", () => {
    expect(samplingMode()).toBe("significant_change");
    startLocationReporting();
    expect(geo.lastOptions.enableHighAccuracy).toBe(false);

    // arming is exactly when ±3 minutes of arrival detection is being judged
    setActiveStop("stop-1");
    expect(samplingMode()).toBe("high_accuracy");
  });

  it("re-opens the watch when arming changes, because options are fixed at watch time", () => {
    startLocationReporting();
    expect(geo.watchers).toHaveLength(1);
    expect(geo.lastOptions.enableHighAccuracy).toBe(false);

    setActiveStop("stop-1");
    geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon, accuracy: 8 });

    expect(geo.clearWatch).toHaveBeenCalled();
    expect(geo.watchers).toHaveLength(2);
    expect(geo.lastOptions.enableHighAccuracy).toBe(true);
  });

  // AI-CONTEXT: the throttle IS the battery budget. watchPosition fires as often as
  // the OS pleases; without this the app would POST on every fix.
  describe("the sampling throttle", () => {
    it("always sends the first fix", () => {
      expect(shouldSend(DALLAS, Date.now())).toBe(true);
    });

    it("sends again once the driver has actually moved", async () => {
      setToken("tok");
      const fetchStub = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ recorded_at: "2026-07-27T00:00:00Z", events: [] }),
      });
      vi.stubGlobal("fetch", fetchStub);
      startLocationReporting();

      geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon, accuracy: 10 });
      await settle();
      expect(pings(fetchStub)).toHaveLength(1);

      // a few metres later, idle: not worth a request
      geo.emit({ latitude: DALLAS.lat + 0.0001, longitude: DALLAS.lon, accuracy: 10 });
      await settle();
      expect(pings(fetchStub)).toHaveLength(1);

      // ~1 km later: worth a request
      geo.emit({ latitude: DALLAS.lat + 0.01, longitude: DALLAS.lon, accuracy: 10 });
      await settle();
      expect(pings(fetchStub)).toHaveLength(2);
    });
  });

  it("sends the server a position and keeps the events it reports back", async () => {
    setToken("tok");
    const fetchStub = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        recorded_at: "2026-07-27T00:00:00Z",
        client_skew_ms: 12,
        events: [{ event_type: "EXIT", facility_id: "f-1", occurred_at: "2026-07-27T00:00:00Z" }],
      }),
    });
    vi.stubGlobal("fetch", fetchStub);
    startLocationReporting();

    geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon, accuracy: 6, speed: 0 });
    await settle();

    const [url, init] = pings(fetchStub)[0];
    expect(String(url)).toContain("/location/ping");
    const body = JSON.parse(init.body);
    expect(body.lat).toBeCloseTo(DALLAS.lat);
    expect(body.mode).toBe("significant_change");
    // the device clock rides along so the server can record skew — PRD §7.3 keeps
    // server time authoritative and measures the client rather than trusting it
    expect(body.client_time).toBeTruthy();

    // an EXIT is what tells a surface the driver has left the dock, without polling
    expect(lastEvents.value[0].event_type).toBe("EXIT");
    expect(permission.value).toBe("granted");
    expect(lastFix.value.lat).toBeCloseTo(DALLAS.lat);
  });

  // AI-CONTEXT: the seam that made §5's ON_SITE unreachable. The client used to learn
  // presence ONLY from an ENTER edge, so a ping carrying no events left the state
  // machine believing the truck was nowhere — which is what every reload produced,
  // and what the "I've arrived" fallback produced always.
  it("takes ON_SITE from a ping that carries no events at all", async () => {
    const { DriverState, useDriverState, __resetStateForTests } = await import(
      "../src/core/state.js"
    );
    __resetStateForTests();
    const { state } = useDriverState();
    setToken("tok");
    const fetchStub = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ recorded_at: "x", present: true, events: [] }),
    });
    vi.stubGlobal("fetch", fetchStub);
    startLocationReporting();

    geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon, accuracy: 6, speed: 0 });
    await settle();

    expect(state.value).toBe(DriverState.ON_SITE);
    __resetStateForTests();
  });

  // AI-CONTEXT: this is the one that keeps the evidence chain honest. Every other
  // write in the app queues through F12 when the signal drops; a POSITION must not,
  // because the server evaluates it against the geofence at SERVER time, so a
  // replayed ping would be judged as happening now.
  it("drops a position it cannot send rather than queueing it", async () => {
    setToken("tok");
    const fetchStub = vi.fn().mockRejectedValue(new Error("offline"));
    vi.stubGlobal("fetch", fetchStub);
    startLocationReporting();

    geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon, accuracy: 10 });
    await settle();

    const { pendingWrites } = await import("../src/core/api.js");
    expect(pendingWrites.value).toBe(0);
  });

  it("does not call the API at all without a session", async () => {
    const fetchStub = vi.fn();
    vi.stubGlobal("fetch", fetchStub);
    startLocationReporting();

    geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon, accuracy: 10 });
    await settle();

    expect(fetchStub).not.toHaveBeenCalled();
  });

  // AI-CONTEXT: the seam that makes §5 real. The state machine was inert not because
  // its logic was wrong but because nothing fed it — this asserts the sensor reaches
  // it, which is the only reason any DRIVING behaviour in the app can ever fire.
  describe("feeding the §5 state machine", () => {
    it("puts the app into DRIVING from sustained motion", async () => {
      const { DriverState, useDriverState, DRIVING_SUSTAIN_MS, __resetStateForTests } =
        await import("../src/core/state.js");
      __resetStateForTests();
      const { state } = useDriverState();
      startLocationReporting();

      const t0 = Date.now();
      vi.setSystemTime(t0);
      geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon, accuracy: 10, speed: 25 });
      expect(state.value).toBe(DriverState.IDLE); // one fix is not "sustained"

      vi.setSystemTime(t0 + DRIVING_SUSTAIN_MS);
      geo.emit({ latitude: DALLAS.lat + 0.05, longitude: DALLAS.lon, accuracy: 10, speed: 25 });

      expect(state.value).toBe(DriverState.DRIVING);
      __resetStateForTests();
      vi.useRealTimers();
    });

    it("derives speed from displacement when the device reports none", async () => {
      const { DriverState, useDriverState, DRIVING_SUSTAIN_MS, __resetStateForTests } =
        await import("../src/core/state.js");
      __resetStateForTests();
      const { state } = useDriverState();
      startLocationReporting();

      const t0 = Date.now();
      vi.setSystemTime(t0);
      // `speed` omitted entirely — a desktop browser, or a phone's first fix
      geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon, accuracy: 10 });
      vi.setSystemTime(t0 + 60_000);
      // ~0.05 degrees of latitude in a minute is roughly 90 km/h
      geo.emit({ latitude: DALLAS.lat + 0.05, longitude: DALLAS.lon, accuracy: 10 });
      vi.setSystemTime(t0 + 60_000 + DRIVING_SUSTAIN_MS);
      geo.emit({ latitude: DALLAS.lat + 0.1, longitude: DALLAS.lon, accuracy: 10 });

      expect(state.value).toBe(DriverState.DRIVING);
      __resetStateForTests();
      vi.useRealTimers();
    });
  });

  // AI-CONTEXT: heading, which this sensor never captured (§23 entry 81).
  //
  // The only heading in the product was the literal `0` two API calls defaulted to,
  // so "what is ahead of me" meant "what is north of me" for every driver, and
  // `GET /map/corridor` — which requires one — was never called at all.
  describe("§11.4 heading", () => {
    it("uses the device's own heading when it reports one", () => {
      startLocationReporting();
      geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon, accuracy: 10, heading: 271.4 });
      expect(lastFix.value.headingDeg).toBeCloseTo(271.4, 1);
    });

    it("keeps a legitimate due-north reading rather than treating 0 as absent", () => {
      // the bug this replaces WAS a 0. A device that genuinely reports 0 must not be
      // confused with one reporting nothing, or northbound drivers get the fallback.
      startLocationReporting();
      geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon, accuracy: 10, heading: 0 });
      expect(lastFix.value.headingDeg).toBe(0);
    });

    it("derives a heading from displacement when the device reports none", () => {
      // most phones report `heading` as null most of the time; without this the
      // corridor would simply never have a direction to ask about
      startLocationReporting();
      geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon, accuracy: 10, heading: null });
      expect(lastFix.value.headingDeg).toBeNull();

      // due west: same latitude, decreasing longitude
      geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon - 0.02, accuracy: 10, heading: null });
      expect(lastFix.value.headingDeg).toBeCloseTo(270, 0);
    });

    it("holds the last heading through a stop instead of spinning on GPS jitter", () => {
      // a parked truck has no heading. Deriving one from metre-scale noise would
      // point the corridor at a different quadrant every second at a dock.
      startLocationReporting();
      geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon, accuracy: 10, heading: null });
      geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon - 0.02, accuracy: 10, heading: null });
      const moving = lastFix.value.headingDeg;
      expect(moving).toBeCloseTo(270, 0);

      // ~2 m of jitter, well under MIN_HEADING_METERS
      geo.emit({
        latitude: DALLAS.lat + 0.00002,
        longitude: DALLAS.lon - 0.02,
        accuracy: 10,
        heading: null,
      });
      expect(lastFix.value.headingDeg).toBe(moving);
    });

    it("has no heading at all before the truck has moved", () => {
      // §11.7: null is the honest third state, and the corridor renders a sentence
      // for it rather than aiming itself at the north pole
      startLocationReporting();
      geo.emit({ latitude: DALLAS.lat, longitude: DALLAS.lon, accuracy: 10 });
      expect(lastFix.value.headingDeg).toBeNull();
    });
  });

  describe("bearingBetween", () => {
    it("measures clockwise from true north, like coords.heading and F11's cone", () => {
      expect(bearingBetween(0, 0, 1, 0)).toBeCloseTo(0, 0); // north
      expect(bearingBetween(0, 0, 0, 1)).toBeCloseTo(90, 0); // east
      expect(bearingBetween(0, 0, -1, 0)).toBeCloseTo(180, 0); // south
      expect(bearingBetween(0, 0, 0, -1)).toBeCloseTo(270, 0); // west
    });
  });

  // §15.5: the card is for a permission the DRIVER has to restore. A timeout or a bad
  // sky view is transient and must not light it up.
  describe("§15.5 degraded location", () => {
    it("marks permission denied only on PERMISSION_DENIED", () => {
      startLocationReporting();

      geo.fail(2); // POSITION_UNAVAILABLE
      expect(permission.value).toBe("unknown");
      geo.fail(3); // TIMEOUT
      expect(permission.value).toBe("unknown");

      geo.fail(1); // PERMISSION_DENIED
      expect(permission.value).toBe("denied");
    });

    it("the one-tap fix asks again", () => {
      startLocationReporting();
      geo.fail(1);
      expect(permission.value).toBe("denied");

      retryLocationPermission();

      expect(permission.value).toBe("unknown");
      expect(geo.watchers.length).toBeGreaterThan(1); // a fresh watch = a fresh ask
    });
  });
});
