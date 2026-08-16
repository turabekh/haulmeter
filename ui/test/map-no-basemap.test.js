/* AI-CONTEXT: the map screen when the basemap cannot draw (§23 entry 159).
 *
 * REPORTED FROM A REAL PHONE at 16% battery, in Uzbek, on production. The screen showed
 * `Map · tiles pending` — a hardcoded ENGLISH literal — and nothing else. Reproduced
 * against production by disabling WebGL in a real browser: note shown, and
 * `document.querySelectorAll(".pin").length === 0`. No basemap, no pins, no list.
 *
 * THREE DEFECTS IN ONE SCREEN, and the third is the one that mattered:
 *   1. the string was a literal, so F15's six-locale law never reached it;
 *   2. "pending" is a lie when hardware acceleration is off — it is not coming;
 *   3. `emitBounds()` returned early with no map, and `map.on("load")` was its only
 *      caller on startup, so THE SURFACE NEVER FETCHED ANY PLACES AT ALL. The
 *      bounds-normalised fallback layout has existed all along and simply never
 *      received data.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

/* AI-CONTEXT: the basemap init is ASYNC — it dynamically imports 1.8 MB of mapbox-gl
   before it can fail. One `flushPromises()` is not enough on the first test in a file
   (the module is not cached yet) and is enough on the third, which is exactly the kind of
   order-dependent green this repo keeps catching. Settle explicitly instead. */
async function settled(w) {
  for (let i = 0; i < 20; i++) {
    await flushPromises();
    if (w.emitted("bounds")) return;
    await new Promise((r) => setTimeout(r, 25));
  }
}
import MapCanvas from "../src/core/components/MapCanvas.vue";
import en from "../src/core/i18n/en.json";

function pin(over = {}) {
  return {
    facility_id: "f-1", name: "Blue Beacon", facility_type: "truck_stop",
    lat: 32.7, lon: -96.8, status: "unknown", freshness: null, badges: [], ...over,
  };
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("a phone that cannot draw a basemap still gets its places", () => {
  it("asks for a viewport even though there is no map", async () => {
    /* THE DEFECT. Without this the surface is handed no bbox, fetches nothing, and the
       fallback layout renders zero pins over a blank screen. */
    const w = mount(MapCanvas, { props: { pins: [] } });
    await settled(w);

    const emitted = w.emitted("bounds");
    expect(emitted, "no viewport was ever requested").toBeTruthy();
    const b = emitted[0][0];
    for (const k of ["min_lat", "max_lat", "min_lon", "max_lon"]) {
      expect(Number.isFinite(b[k]), `${k} is not a number`).toBe(true);
    }
    expect(b.min_lat).toBeLessThan(b.max_lat);
    expect(b.min_lon).toBeLessThan(b.max_lon);
    w.unmount();
  });

  it("lays the places out even with no basemap under them", async () => {
    const w = mount(MapCanvas, { props: { pins: [pin(), pin({ facility_id: "f-2", lat: 33.1 })] } });
    await flushPromises();
    expect(w.findAll(".pin")).toHaveLength(2);
    w.unmount();
  });

  it("re-asks for the viewport when the driver's own position arrives", async () => {
    // a driver whose GPS resolves must not be stuck on the continental default
    const w = mount(MapCanvas, { props: { pins: [] } });
    await settled(w);
    const before = w.emitted("bounds").length;
    w.vm.showPlace?.({ lat: 41.9, lon: -87.6 });
    await flushPromises();
    expect(w.emitted("bounds").length).toBeGreaterThanOrEqual(before);
    w.unmount();
  });
});

describe("the note tells the truth, in the driver's language", () => {
  it("is never a hardcoded English literal", async () => {
    const w = mount(MapCanvas, { props: { pins: [] } });
    await flushPromises();
    const note = w.find(".canvas__note");
    expect(note.exists()).toBe(true);
    // the exact string the owner photographed
    expect(note.text()).not.toBe("Map · tiles pending");
    // and it must be a value the catalogue actually carries
    expect(Object.values(en)).toContain(note.text());
    w.unmount();
  });

  it("names the DEVICE when this phone cannot draw a basemap", async () => {
    /* happy-dom has no WebGL, which is exactly the driver's condition — so this is the
       case the owner photographed, asserted in the environment that reproduces it. */
    const w = mount(MapCanvas, { props: { pins: [] } });
    await settled(w);
    expect(w.find(".canvas__note").text()).toBe(en["map.basemap_no_webgl"]);
    w.unmount();
  });

  it("all six locales carry every basemap string", async () => {
    const locales = ["en", "es", "ru", "uz", "so", "pa"];
    for (const loc of locales) {
      const cat = require(`../src/core/i18n/${loc}.json`);
      for (const k of ["map.basemap_pending", "map.basemap_failed", "map.basemap_no_webgl"]) {
        expect(cat[k], `${loc} is missing ${k}`).toBeTruthy();
      }
    }
  });

  it("the permanent case does not use the word for a temporary one", () => {
    /* "pending"/"loading" tells a driver to wait for something that is not coming. The
       device case names a cause they can act on and says the list still works. */
    expect(en["map.basemap_no_webgl"].toLowerCase()).not.toContain("loading");
    expect(en["map.basemap_no_webgl"].toLowerCase()).not.toContain("pending");
    expect(en["map.basemap_no_webgl"].toLowerCase()).toContain("still work");
    expect(en["map.basemap_failed"].toLowerCase()).toContain("still work");
  });
});
