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
