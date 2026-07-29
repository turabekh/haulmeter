// AI-CONTEXT: §23 entry 101 — markers move without Vue.
//
// The map re-projected every pin on every frame of a pan and wrote the result into
// reactive state as `top`/`left`: up to 300 projections, two reactive object
// replacements and a full Vue re-render per frame, using the two properties that
// force LAYOUT rather than only paint. Markers trailed the tiles they were pinned to.
//
// These tests exist because the ones that already passed could not see any of it: a
// test runner has no WebGL, so `live` is false and every mounted-canvas test exercises
// the FALLBACK path. 522 green tests had nothing to say about the code being changed
// here, which is the shape of §23 entry 42 — a suite agreeing for the wrong reason.
//
// So the arithmetic moved into core/ (§19) where it can be asserted directly, and the
// wiring is checked against the shipped source rather than a copy of it.
import { describe, it, expect } from "vitest";
import { markerTransform } from "../src/core/presentation.js";

describe("marker placement (§23 entry 101)", () => {
  it("keeps the centring translate the stylesheet relies on", () => {
    // THE one that matters. An element has a single transform: writing a bare
    // translate3d would silently drop `translate(-50%, -50%)` and hang every pin off
    // its own corner — 22 px from the place it claims to mark, on every live map,
    // while every test still passed because none of them run a GL context.
    expect(markerTransform(100, 250)).toBe(
      "translate3d(100px, 250px, 0) translate(-50%, -50%)",
    );
  });

  it("uses a compositor transform rather than layout properties", () => {
    const t = markerTransform(10, 20);
    expect(t).toContain("translate3d");
    expect(t).not.toMatch(/top|left/);
  });

  it("refuses a projection that is not a number", () => {
    // Mapbox projects to NaN for a point behind a tilted globe; writing that would
    // blank the marker with no way to tell why
    for (const bad of [
      [NaN, 10],
      [10, NaN],
      [Infinity, 10],
      [undefined, 10],
    ]) {
      expect(markerTransform(...bad), JSON.stringify(bad)).toBeNull();
    }
  });

  it("handles negative offsets, which are simply off-screen", () => {
    expect(markerTransform(-40, -12)).toBe(
      "translate3d(-40px, -12px, 0) translate(-50%, -50%)",
    );
  });
});

describe("marker hot path wiring", () => {
  it("does not put reactive state on the per-frame handler", async () => {
    // `move` fires once per animation frame. Binding the reactive settle to it is the
    // regression this whole entry is about, and it is a one-word edit away.
    const src = (await import("../src/core/components/MapCanvas.vue?raw")).default;
    const onMove = src.match(/map\.on\("move",\s*(\w+)\)/);
    expect(onMove, 'MapCanvas must bind a "move" handler').toBeTruthy();
    expect(onMove[1]).toBe("paintPositions");
  });

  it("settles the declutter read once per gesture, on moveend", async () => {
    const src = (await import("../src/core/components/MapCanvas.vue?raw")).default;
    expect(src).toMatch(/map\.on\("moveend",\s*settlePositions\)/);
  });

  it("holds marker elements outside reactivity", async () => {
    // a reactive ref map would reintroduce exactly the per-frame render this removed
    const src = (await import("../src/core/components/MapCanvas.vue?raw")).default;
    expect(src).toMatch(/const pinEls = new Map\(\)/);
    expect(src).not.toMatch(/const pinEls = (ref|reactive|shallowRef)\(/);
  });
});
