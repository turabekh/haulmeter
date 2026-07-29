// AI-CONTEXT: §23 entry 100 — the map survives a trip to a facility page.
//
// Owner-reported: "tapping icons or viewing a facility and coming back to the map is
// acting weird." It was, and the cause was structural rather than cosmetic: there was
// no <KeepAlive>, so navigating away DESTROYED the Mapbox GL instance and Back built
// a new one on the continental United States.
//
// These tests assert the two halves that make the fix safe:
//   · the map is cached, so returning re-activates rather than re-creates it, and
//   · nothing ELSE is cached, because Load / Money / Docs carry money, clocks and
//     evidence state that must never be a minute-old copy.
//
// The second is the one worth a test. Widening `include` later would be a one-word
// change that looks like a simplification and would quietly start serving a driver a
// stale detention clock.
import { describe, it, expect } from "vitest";
import { defineComponent, h, KeepAlive } from "vue";
import { mount } from "@vue/test-utils";

// stand-ins named exactly as the real surfaces are, so what is asserted is the
// include LIST — the thing that can drift — and not Mapbox, which has no WebGL here.
function surface(name, mounted, activated) {
  return defineComponent({
    name,
    setup() {
      mounted();
      return () => h("div", { class: name });
    },
    activated,
  });
}

function harness(include) {
  const mounts = {};
  const bump = (n) => () => (mounts[n] = (mounts[n] || 0) + 1);
  const MapSurface = surface("MapSurface", bump("MapSurface"));
  const LoadSurface = surface("LoadSurface", bump("LoadSurface"));
  const current = { value: MapSurface };
  const App = defineComponent({
    setup() {
      return () => h(KeepAlive, { include }, [h(current.value)]);
    },
  });
  return { mounts, current, MapSurface, LoadSurface, App };
}

describe("map keep-alive (§23 entry 100)", () => {
  it("does not rebuild the map when the driver comes back to it", async () => {
    const h1 = harness(["MapSurface"]);
    const w = mount(h1.App);

    expect(h1.mounts.MapSurface).toBe(1);
    h1.current.value = h1.LoadSurface;
    await w.vm.$forceUpdate();
    await w.vm.$nextTick();
    h1.current.value = h1.MapSurface;
    await w.vm.$forceUpdate();
    await w.vm.$nextTick();

    // one setup() for the whole journey: the Mapbox instance, the tiles it has
    // downloaded and the viewport it is showing all survive the round trip
    expect(h1.mounts.MapSurface).toBe(1);
  });

  it("keeps caching OFF for the surfaces that carry money and clocks", async () => {
    const h1 = harness(["MapSurface"]);
    const w = mount(h1.App);

    h1.current.value = h1.LoadSurface;
    await w.vm.$forceUpdate();
    await w.vm.$nextTick();
    h1.current.value = h1.MapSurface;
    await w.vm.$forceUpdate();
    await w.vm.$nextTick();
    h1.current.value = h1.LoadSurface;
    await w.vm.$forceUpdate();
    await w.vm.$nextTick();

    // the Load tab is built fresh every time it is opened. A cached detention clock
    // is a wrong number on a screen a driver may be about to file a claim from.
    expect(h1.mounts.LoadSurface).toBe(2);
  });

  it("names only the map in the include list", async () => {
    // reads the real App template so the assertion tracks the shipped list, not a
    // copy of it that can drift
    const app = (await import("../src/App.vue?raw")).default;
    const match = app.match(/<KeepAlive\s+:include="\[([^\]]*)\]"/);
    expect(match, "App.vue must keep exactly one KeepAlive include list").toBeTruthy();
    expect(match[1].replace(/['"\s]/g, "").split(",").filter(Boolean)).toEqual(["MapSurface"]);
  });
});
