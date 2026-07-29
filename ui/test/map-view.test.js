// AI-CONTEXT: §23 entry 100 — where the map was last looking.
//
// Owner-reported: "viewing a facility and coming back to the map is acting weird."
// Nothing kept the viewport, so leaving the tab destroyed the Mapbox instance and
// returning rebuilt it on the continental United States, fetched the country,
// re-acquired GPS and flew back — two round trips and a visible jump to arrive at a
// view the driver had never left.
//
// The rules here are arithmetic and live in core/ (§19) so they are testable without
// a mounted map: a test runner has no WebGL, and a rule asserted only through a
// rendered canvas is a rule that ships unexercised.
import { describe, it, expect, beforeEach } from "vitest";
import {
  readView,
  rememberView,
  __resetForTests,
  MIN_REMEMBERED_ZOOM,
  MAX_ZOOM,
} from "../src/core/map-view.js";

describe("map viewport memory", () => {
  beforeEach(() => __resetForTests());

  it("remembers where the driver was looking", () => {
    rememberView(32.7767, -96.797, 11);
    expect(readView()).toEqual({ lat: 32.7767, lon: -96.797, zoom: 11 });
  });

  it("has nothing to say before the driver has looked anywhere", () => {
    expect(readView()).toBeNull();
  });

  it("refuses to remember a continental view", () => {
    // restoring zoom 3.5 would faithfully "remember" the very screen this exists to
    // stop a driver seeing again — the whole United States, every time they come back
    rememberView(39.8, -98.5, 3.5);
    expect(readView()).toBeNull();
  });

  it("keeps the boundary zoom itself", () => {
    rememberView(43.07, -89.4, MIN_REMEMBERED_ZOOM);
    expect(readView()?.zoom).toBe(MIN_REMEMBERED_ZOOM);
  });

  it("rejects a hand-edited or corrupt view rather than handing it to Mapbox", () => {
    // this is the one input a devtools console can reach, and a NaN centre puts the
    // GL map into a state a reload does not clear
    for (const bad of [
      { lat: NaN, lon: -96.8, zoom: 11 },
      { lat: 32.7, lon: -96.8, zoom: Infinity },
      { lat: 991, lon: -96.8, zoom: 11 },
      { lat: 32.7, lon: -400, zoom: 11 },
      { lat: 32.7, lon: -96.8, zoom: MAX_ZOOM + 5 },
      { lat: "32.7", lon: -96.8, zoom: 11 },
    ]) {
      __resetForTests();
      localStorage.setItem("longhaul.map_view", JSON.stringify(bad));
      expect(readView(), JSON.stringify(bad)).toBeNull();
    }
  });

  it("survives storage holding something that is not JSON", () => {
    localStorage.setItem("longhaul.map_view", "{{{not json");
    expect(readView()).toBeNull();
  });

  it("does not write a view it would refuse to read back", () => {
    // the write and the read agree on what is usable, so nothing can be stored that
    // only fails later, on a screen, in front of a driver
    expect(rememberView(39.8, -98.5, 3.5)).toBeNull();
    expect(rememberView(NaN, -98.5, 11)).toBeNull();
    expect(rememberView(32.7, -96.8, 11)).toEqual({ lat: 32.7, lon: -96.8, zoom: 11 });
  });

  it("keeps one view, not one per driver state", () => {
    // deliberately unlike the PRESET beside it (§23 entry 82). "What am I looking
    // for" legitimately differs between resting and rolling; "where am I looking"
    // does not become a different place because the truck started moving.
    rememberView(32.7, -96.8, 11);
    rememberView(43.07, -89.4, 9);
    expect(readView()).toEqual({ lat: 43.07, lon: -89.4, zoom: 9 });
  });
});
