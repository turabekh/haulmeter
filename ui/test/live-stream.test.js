// AI-CONTEXT: §23 entry 103 — the live channel, client side.
//
// The rule every one of these defends: **the stream is an accelerator, never a source
// of truth.** Everything it carries is also a row the REST path returns, so every
// failure mode — no EventSource, no session, Redis down, a carrier that kills
// long-lived sockets — must degrade to exactly the behaviour the app had before it
// existed. A live channel that breaks the map when it fails is worse than none.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { openStream } from "../src/core/live.js";
import { token } from "../src/core/api.js";

class FakeEventSource {
  static instances = [];
  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.closed = false;
    FakeEventSource.instances.push(this);
  }
  addEventListener(name, fn) {
    this.listeners[name] = fn;
  }
  emit(name, data) {
    this.listeners[name]?.({ data });
  }
  close() {
    this.closed = true;
  }
}

describe("live stream (§23 entry 103)", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    token.value = "tok-123";
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    token.value = null;
  });

  it("delivers an event to the caller", () => {
    const seen = [];
    openStream({ kind: "handoff", lat: 32.7, lon: -96.8, onEvent: (e) => seen.push(e) });
    FakeEventSource.instances[0].emit("handoff", JSON.stringify({ handoff_id: "h-1" }));
    expect(seen).toEqual([{ handoff_id: "h-1" }]);
  });

  it("subscribes to the driver's own position and carries the session", () => {
    openStream({ kind: "handoff", lat: 32.7, lon: -96.8, onEvent: () => {} });
    const url = FakeEventSource.instances[0].url;
    expect(url).toContain("lat=32.7");
    expect(url).toContain("lon=-96.8");
    // EventSource cannot set headers — the token has to travel in the query (§23 103)
    expect(url).toContain("access_token=tok-123");
  });

  it("does nothing at all without a session", () => {
    token.value = null;
    const stop = openStream({ lat: 32.7, lon: -96.8, onEvent: () => {} });
    expect(FakeEventSource.instances).toHaveLength(0);
    expect(typeof stop).toBe("function"); // still safe to call
    stop();
  });

  it("does nothing where EventSource does not exist", () => {
    vi.stubGlobal("EventSource", undefined);
    const stop = openStream({ lat: 32.7, lon: -96.8, onEvent: () => {} });
    expect(typeof stop).toBe("function");
    stop();
  });

  it("survives a malformed frame rather than breaking the map", () => {
    const seen = [];
    openStream({ lat: 32.7, lon: -96.8, onEvent: (e) => seen.push(e) });
    expect(() =>
      FakeEventSource.instances[0].emit("handoff", "{not json"),
    ).not.toThrow();
    expect(seen).toEqual([]);
  });

  it("closes the socket when the caller stops it", () => {
    const stop = openStream({ lat: 32.7, lon: -96.8, onEvent: () => {} });
    stop();
    expect(FakeEventSource.instances[0].closed).toBe(true);
  });

  it("backs off rather than reconnecting every five seconds forever", () => {
    vi.useFakeTimers();
    try {
      openStream({ lat: 32.7, lon: -96.8, onEvent: () => {} });
      // a server that is down must not receive one reconnect per driver per 5 s
      FakeEventSource.instances[0].onerror();
      vi.advanceTimersByTime(5_000);
      expect(FakeEventSource.instances).toHaveLength(2);

      FakeEventSource.instances[1].onerror();
      vi.advanceTimersByTime(5_000);
      expect(FakeEventSource.instances, "second retry must wait longer").toHaveLength(2);
      vi.advanceTimersByTime(5_000);
      expect(FakeEventSource.instances).toHaveLength(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it("treats the server's goodbye as a reconnect, not a failure", () => {
    vi.useFakeTimers();
    try {
      openStream({ lat: 32.7, lon: -96.8, onEvent: () => {} });
      // the server caps a stream (MAX_STREAM_SECONDS) and says bye; that is routine
      FakeEventSource.instances[0].emit("bye", "{}");
      expect(FakeEventSource.instances[0].closed).toBe(true);
      vi.advanceTimersByTime(5_000);
      expect(FakeEventSource.instances).toHaveLength(2);
    } finally {
      vi.useRealTimers();
    }
  });
});

// --- §23 entry 104: the thundering-herd guard ---
describe("coalesce (§23 entry 104)", () => {
  it("collapses a burst of events into one refetch", async () => {
    vi.useFakeTimers();
    vi.spyOn(Math, "random").mockReturnValue(0);
    try {
      const { coalesce } = await import("../src/core/live.js");
      const fn = vi.fn();
      const run = coalesce(fn, { minMs: 800, jitterMs: 2200 });

      // a busy truck stop: five drivers report within a second of each other
      run(); run(); run(); run(); run();
      expect(fn).not.toHaveBeenCalled(); // nothing fires immediately

      vi.advanceTimersByTime(900);
      expect(fn).toHaveBeenCalledTimes(1); // ...and five events cost ONE refetch
    } finally {
      vi.restoreAllMocks();
      vi.useRealTimers();
    }
  });

  it("spreads the herd so a cell does not return in one instant", async () => {
    // a ~40 km cell can hold a lot of drivers. Without jitter, one tap would produce
    // one simultaneous overlay request per phone — against the endpoint §23 98 had
    // just finished making cheap.
    const { coalesce } = await import("../src/core/live.js");
    const delays = new Set();
    const realTimeout = globalThis.setTimeout;
    vi.stubGlobal("setTimeout", (fn, ms) => {
      delays.add(ms);
      return realTimeout(() => {}, 0);
    });
    try {
      for (let i = 0; i < 20; i++) coalesce(() => {}, { minMs: 800, jitterMs: 2200 })();
      expect(delays.size).toBeGreaterThan(1);
      for (const d of delays) {
        expect(d).toBeGreaterThanOrEqual(800);
        expect(d).toBeLessThanOrEqual(3000);
      }
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("accepts new work again once the refetch has run", async () => {
    vi.useFakeTimers();
    try {
      const { coalesce } = await import("../src/core/live.js");
      const fn = vi.fn();
      const run = coalesce(fn, { minMs: 10, jitterMs: 0 });
      run();
      vi.advanceTimersByTime(20);
      run();
      vi.advanceTimersByTime(20);
      expect(fn).toHaveBeenCalledTimes(2); // not latched shut after the first
    } finally {
      vi.useRealTimers();
    }
  });
});
